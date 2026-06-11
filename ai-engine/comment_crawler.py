import re
import json
import logging
import html
import os
import requests
from urllib.parse import parse_qs, urlparse
from sqlalchemy.orm import Session

from models import Article, Comment

logger = logging.getLogger(__name__)


class CommentCrawler:
    """뉴스 기사 댓글을 공개 API를 통해 수집하는 크롤러."""

    # 네이버 뉴스 URL에서 oid(언론사 코드)와 aid(기사 ID)를 추출하는 패턴
    NAVER_URL_PATTERN = re.compile(r'n(?:ews)?\.naver\.com/(?:mnews/)?article/(\d+)/(\d+)')
    NAVER_COMMENT_API_URL = "https://apis.naver.com/commentBox/cbox/web_naver_list_jsonp.json"
    SBS_COMMENT_API_URL = "https://api-gw.sbsdlab.co.kr/v1/news_front_api/comment/{article_id}"
    SBS_PAGE_SIZE = 100
    SBS_MAX_PAGES = 10
    DEFAULT_BATCH_SIZE = int(os.getenv("COMMENT_CRAWL_BATCH_SIZE", "200"))

    def __init__(self, db: Session):
        self.db = db
        self.headers = {
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36",
            "Referer": "https://news.naver.com",
        }

    def _extract_naver_ids(self, url: str):
        """URL에서 네이버 뉴스 oid, aid를 추출. 비-네이버 URL이면 (None, None) 반환."""
        match = self.NAVER_URL_PATTERN.search(url)
        if match:
            return match.group(1), match.group(2)
        return None, None

    def _extract_sbs_target(self, url: str):
        """SBS 뉴스 URL에서 댓글 API 호출에 필요한 기사 정보를 추출."""
        parsed = urlparse(url)
        if "news.sbs.co.kr" not in parsed.netloc:
            return None

        params = parse_qs(parsed.query)
        pathname = parsed.path or ""

        if "article_id" in params:
            return {
                "provider": "sbs",
                "article_id": params["article_id"][0],
                "category": "EA",
                "news_type": "E",
            }

        news_id = self._first_query_value(params, "news_id", "newsId", "id")
        if news_id:
            return {
                "provider": "sbs",
                "article_id": news_id,
                "category": "NA",
                "news_type": "N",
            }

        article_match = re.match(r"^/article/([A-Z]\d+)", pathname)
        if article_match:
            article_id = article_match.group(1)
            is_news = article_id.startswith("N")
            return {
                "provider": "sbs",
                "article_id": article_id,
                "category": "NA" if is_news else "EA",
                "news_type": "N" if is_news else "E",
            }

        return None

    def _detect_comment_target(self, url: str):
        """지원 가능한 댓글 출처와 식별자를 반환. 미지원 출처는 None."""
        oid, aid = self._extract_naver_ids(url)
        if oid and aid:
            return {
                "provider": "naver",
                "oid": oid,
                "aid": aid,
            }

        return self._extract_sbs_target(url)

    @staticmethod
    def _first_query_value(params: dict, *names: str):
        for name in names:
            values = params.get(name)
            if values and values[0]:
                return values[0]
        return None

    @staticmethod
    def _safe_int(value, default: int = 0) -> int:
        try:
            return int(value or default)
        except (TypeError, ValueError):
            return default

    @staticmethod
    def _clean_comment_content(content: str) -> str:
        text = str(content or "")
        text = re.sub(r"<br\s*/?>", "\n", text, flags=re.IGNORECASE)
        text = re.sub(r"<[^>]+>", "", text)
        return html.unescape(text).strip()

    def _normalize_naver_comment(self, raw_comment: dict):
        content = self._clean_comment_content(raw_comment.get("contents", ""))
        if not content:
            return None

        return {
            "content": content,
            "author": raw_comment.get("maskedUserId", "익명"),
            "likes": self._safe_int(raw_comment.get("sympathyCount")),
            "dislikes": self._safe_int(raw_comment.get("antipathyCount")),
        }

    def _normalize_sbs_comment(self, raw_comment: dict):
        status = str(raw_comment.get("STATUS", "")).upper()
        if status.startswith("D"):
            return None

        content = self._clean_comment_content(raw_comment.get("CONTENT", ""))
        if not content or content == "작성자가 삭제한 댓글입니다.":
            return None

        return {
            "content": content,
            "author": raw_comment.get("USER_NAME", "익명"),
            "likes": self._safe_int(raw_comment.get("LIKE_CNT")),
            "dislikes": self._safe_int(raw_comment.get("DISLIKE_CNT")),
        }

    def _flatten_sbs_comments(self, raw_comments: list) -> list:
        flattened = []
        for raw_comment in raw_comments:
            flattened.append(raw_comment)
            replies = raw_comment.get("replyList", [])
            if isinstance(replies, list):
                flattened.extend(replies)
        return flattened

    def _fetch_comments(self, oid: str, aid: str) -> list:
        """네이버 댓글 API 호출 후 댓글 리스트 반환."""
        params = {
            "ticket": "news",
            "templateId": "default_society",
            "pool": "cbox5",
            "lang": "ko",
            "country": "KR",
            "objectId": f"news{oid},{aid}",
            "pageSize": 100,
            "sort": "OBJECT",  # 공감순 정렬
            "page": 1,
        }
        try:
            resp = requests.get(
                self.NAVER_COMMENT_API_URL, params=params, headers=self.headers, timeout=10
            )
            resp.raise_for_status()

            # 응답이 JSONP 포맷인 경우 콜백 래퍼 제거 후 파싱
            text = resp.text.strip()
            if text.startswith("{"):
                data = json.loads(text)
            else:
                # _callback(...) 형태에서 JSON 본문만 추출
                json_str = re.sub(r'^[^(]+\(', '', text).rstrip(');')
                data = json.loads(json_str)

            return data.get("result", {}).get("commentList", [])
        except Exception:
            logger.error("Naver comment API 호출 실패. oid=%s aid=%s", oid, aid, exc_info=True)
            return []

    def _fetch_sbs_comments(self, target: dict) -> list:
        """SBS 공개 댓글 API를 호출해 댓글 리스트를 반환."""
        article_id = target["article_id"]
        api_url = self.SBS_COMMENT_API_URL.format(article_id=article_id)
        comments = []
        headers = {
            **self.headers,
            "Referer": f"https://news.sbs.co.kr/news/endPage.do?news_id={article_id}",
            "Origin": "https://news.sbs.co.kr",
        }

        for page in range(1, self.SBS_MAX_PAGES + 1):
            params = {
                "category": target["category"],
                "newsType": target["news_type"],
                "articleId": article_id,
                "orderType": "N",
                "offset": page,
                "limit": self.SBS_PAGE_SIZE,
            }
            try:
                resp = requests.get(api_url, params=params, headers=headers, timeout=10)
                resp.raise_for_status()
                page_comments = resp.json()
            except Exception:
                logger.error("SBS comment API 호출 실패. article_id=%s page=%s", article_id, page, exc_info=True)
                return comments

            if not isinstance(page_comments, list) or not page_comments:
                break

            comments.extend(page_comments)
            total_count = self._safe_int(page_comments[0].get("TOTAL_COMMENT_COUNT"))
            top_count = self._safe_int(page_comments[0].get("TOP_COMMENT_COUNT"))
            expected_count = max(total_count, top_count)
            if len(page_comments) < self.SBS_PAGE_SIZE or (expected_count and len(comments) >= expected_count):
                break

        return comments

    def _existing_comment_signatures(self, article_id: int) -> set:
        rows = (
            self.db.query(Comment.content, Comment.author)
            .filter(Comment.article_id == article_id)
            .all()
        )
        return {(content, author) for content, author in rows}

    def run(self, article_id: int = None) -> dict:
        """
        DB에 저장된 기사의 댓글을 수집합니다.
        article_id 지정 시 해당 기사만, 없으면 댓글 미수집 기사 기본 200건을 처리합니다.
        """
        if article_id:
            articles = self.db.query(Article).filter(Article.id == article_id).all()
        else:
            # 댓글이 아직 하나도 없는 기사만 대상으로 함
            articles = (
                self.db.query(Article)
                .outerjoin(Comment, Article.id == Comment.article_id)
                .filter(Comment.id == None)
                .limit(self.DEFAULT_BATCH_SIZE)
                .all()
            )

        collected_total = 0
        skipped_unsupported = 0
        errors = 0
        duplicates = 0
        articles_processed = 0
        provider_results = {
            "naver": {"articles": 0, "comments": 0},
            "sbs": {"articles": 0, "comments": 0},
            "unsupported": {"articles": 0, "comments": 0},
        }

        for article in articles:
            target = self._detect_comment_target(article.url)
            if not target:
                skipped_unsupported += 1
                provider_results["unsupported"]["articles"] += 1
                continue

            try:
                provider = target["provider"]
                if provider == "naver":
                    raw_comments = self._fetch_comments(target["oid"], target["aid"])
                    normalized_comments = [
                        comment
                        for comment in (self._normalize_naver_comment(raw) for raw in raw_comments)
                        if comment
                    ]
                elif provider == "sbs":
                    raw_comments = self._fetch_sbs_comments(target)
                    normalized_comments = [
                        comment
                        for comment in (self._normalize_sbs_comment(raw) for raw in self._flatten_sbs_comments(raw_comments))
                        if comment
                    ]
                else:
                    skipped_unsupported += 1
                    provider_results["unsupported"]["articles"] += 1
                    continue

                articles_processed += 1
                provider_results[provider]["articles"] += 1
                provider_results[provider]["comments"] += len(normalized_comments)
                existing_signatures = self._existing_comment_signatures(article.id)

                for normalized in normalized_comments:
                    signature = (normalized["content"], normalized["author"])
                    if signature in existing_signatures:
                        duplicates += 1
                        continue

                    comment = Comment(
                        article_id=article.id,
                        content=normalized["content"],
                        author=normalized["author"],
                        likes=normalized["likes"],
                        dislikes=normalized["dislikes"],
                    )
                    self.db.add(comment)
                    existing_signatures.add(signature)
                    collected_total += 1

                self.db.commit()
            except Exception:
                logger.error("기사 댓글 수집 중 오류. article_id=%s", article.id, exc_info=True)
                self.db.rollback()
                errors += 1

        return {
            "status": "success",
            "collected_total": collected_total,
            "articles_processed": articles_processed,
            "skipped_unsupported": skipped_unsupported,
            "skipped_non_naver": skipped_unsupported,
            "duplicates": duplicates,
            "provider_results": provider_results,
            "errors": errors,
        }
