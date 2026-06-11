import feedparser
import json
import requests
from bs4 import BeautifulSoup
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from sqlalchemy.orm import Session
import logging

from models import NewsSource, Article

logger = logging.getLogger(__name__)

class RSSCrawler:
    MIN_USEFUL_CONTENT_LENGTH = 100

    REQUEST_HEADERS = {
        "User-Agent": (
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
            "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0 Safari/537.36"
        ),
        "Accept": "application/rss+xml, application/xml, text/xml, text/html;q=0.8, */*;q=0.5",
    }

    def __init__(self, db: Session):
        self.db = db

    @staticmethod
    def _normalize_text(value: str) -> str:
        return " ".join(str(value or "").split())

    @classmethod
    def _walk_json(cls, value):
        if isinstance(value, dict):
            yield value
            for child in value.values():
                yield from cls._walk_json(child)
        elif isinstance(value, list):
            for item in value:
                yield from cls._walk_json(item)

    @classmethod
    def extract_article_content(cls, html: str) -> str:
        soup = BeautifulSoup(html, "lxml")

        for script in soup.find_all("script", attrs={"type": "application/ld+json"}):
            raw_json = script.string or script.get_text()
            if not raw_json:
                continue
            try:
                data = json.loads(raw_json.strip())
            except json.JSONDecodeError:
                continue
            for node in cls._walk_json(data):
                article_body = node.get("articleBody")
                if article_body:
                    return cls._normalize_text(article_body)[:5000]

        selectors = [
            ".article_cont_area .text_area",
            ".main_text .text_area",
            "[itemprop='articleBody']",
            "article",
        ]
        for selector in selectors:
            article_node = soup.select_one(selector)
            if not article_node:
                continue
            for removable in article_node.select(
                "script, style, noscript, [data-nosnippet], .copyrightsbs, .page_promotion_banner"
            ):
                removable.decompose()
            content = cls._normalize_text(article_node.get_text(" ", strip=True))
            if content:
                return content[:5000]

        description = soup.find("meta", attrs={"name": "description"})
        if description and description.get("content"):
            return cls._normalize_text(description["content"])[:5000]

        paragraphs = [
            cls._normalize_text(p.get_text(" ", strip=True))
            for p in soup.find_all("p")
        ]
        return cls._normalize_text(" ".join(p for p in paragraphs if p))[:5000]

    def fetch_feed(self, source: NewsSource):
        response = requests.get(source.rss_url, headers=self.REQUEST_HEADERS, timeout=10)
        response.raise_for_status()
        feed = feedparser.parse(response.content)
        try:
            feed["http_status"] = response.status_code
            feed["resolved_url"] = response.url
        except TypeError:
            setattr(feed, "http_status", response.status_code)
            setattr(feed, "resolved_url", response.url)
        return feed

    @classmethod
    def extract_entry_summary(cls, entry) -> str:
        summary = entry.get("summary") or entry.get("description") or ""
        if not summary:
            return ""
        if "<" not in summary and ">" not in summary:
            return cls._normalize_text(summary)[:5000]
        text = BeautifulSoup(summary, "lxml").get_text(" ", strip=True)
        return cls._normalize_text(text)[:5000]

    @classmethod
    def parse_entry_datetime(cls, entry):
        published_raw = entry.get("published") or entry.get("updated")
        if not published_raw:
            return None

        try:
            parsed = parsedate_to_datetime(published_raw)
            return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)
        except (TypeError, ValueError):
            pass

        for date_format in ("%Y.%m.%d", "%Y-%m-%d", "%Y.%m.%d %H:%M", "%Y-%m-%d %H:%M"):
            try:
                return datetime.strptime(published_raw, date_format).replace(tzinfo=timezone.utc)
            except ValueError:
                continue

        raise ValueError(f'Invalid date value or format "{published_raw}"')

    def scrape_article_content(self, url: str) -> str:
        """기사 원문 페이지에서 간단하게 본문을 추출합니다."""
        try:
            response = requests.get(url, headers=self.REQUEST_HEADERS, timeout=10)
            response.raise_for_status()
            return self.extract_article_content(response.text)
        except Exception:
            logger.error("Failed to scrape article content. url=%s", url, exc_info=True)
            return ""

    def run(self) -> dict:
        """저장된 뉴스 출처(news_sources)의 RSS 피드를 모두 크롤링합니다."""
        sources = self.db.query(NewsSource).all()
        results = {
            "total_sources": len(sources),
            "new_articles": 0,
            "errors": 0,
            "source_results": [],
        }

        for source in sources:
            source_result = {
                "source_id": source.id,
                "source": source.name,
                "rss_url": source.rss_url,
                "entries": 0,
                "new_articles": 0,
                "duplicates": 0,
                "errors": 0,
                "status": "success",
            }
            try:
                feed = self.fetch_feed(source)
                entries = list(getattr(feed, "entries", []) or [])
                source_result["entries"] = len(entries)

                bozo_exception = getattr(feed, "bozo_exception", None)
                if getattr(feed, "bozo", False):
                    source_result["warning"] = str(bozo_exception)[:300]
                    logger.warning(
                        "RSS feed has parse warning. source=%s status=%s entries=%s warning=%s",
                        source.name,
                        getattr(feed, "http_status", None),
                        len(entries),
                        bozo_exception,
                    )

                if not entries:
                    error_message = str(bozo_exception or "RSS feed returned no entries.")
                    raise ValueError(error_message)

                for entry in entries:
                    link = entry.get('link')
                    if not link:
                        source_result["errors"] += 1
                        results["errors"] += 1
                        logger.warning("RSS entry skipped because link is missing. source=%s", source.name)
                        continue
                    
                    # 날짜 파싱
                    published_at = None
                    try:
                        published_at = self.parse_entry_datetime(entry)
                    except ValueError:
                        source_result["errors"] += 1
                        results["errors"] += 1
                        logger.error(
                            "Failed to parse published date. source=%s link=%s",
                            source.name,
                            link,
                            exc_info=True,
                        )

                    fallback_content = self.extract_entry_summary(entry)

                    # 중복 기사 필터링 (URL 기준). 기존 데이터가 비어 있으면 보정합니다.
                    existing_article = self.db.query(Article).filter(Article.url == link).first()
                    if existing_article:
                        source_result["duplicates"] += 1
                        updated_existing = False
                        if published_at and not existing_article.published_at:
                            existing_article.published_at = published_at
                            updated_existing = True
                        if len(existing_article.content or "") < self.MIN_USEFUL_CONTENT_LENGTH:
                            content = self.scrape_article_content(link)
                            if len(content) < self.MIN_USEFUL_CONTENT_LENGTH and fallback_content:
                                content = fallback_content
                            if content and content != existing_article.content:
                                existing_article.content = content
                                updated_existing = True
                        if updated_existing:
                            source_result["updated_articles"] = source_result.get("updated_articles", 0) + 1
                        continue
                    
                    title = entry.get('title', 'No Title')
                    
                    # (선택) 기사 본문 스크래핑
                    content = self.scrape_article_content(link)
                    if len(content) < self.MIN_USEFUL_CONTENT_LENGTH and fallback_content:
                        content = fallback_content

                    # DB 저장
                    article = Article(
                        source_id=source.id,
                        title=title,
                        content=content,
                        url=link,
                        published_at=published_at
                    )
                    self.db.add(article)
                    results["new_articles"] += 1
                    source_result["new_articles"] += 1
                
                self.db.commit()
            except Exception as exc:
                source_result["status"] = "feed_error"
                source_result["errors"] += 1
                source_result["error"] = str(exc)[:300] or "RSS 처리 중 오류가 발생했습니다."
                results["errors"] += 1
                logger.error("Error processing RSS for source. source=%s", source.name, exc_info=True)
                self.db.rollback()
            finally:
                results["source_results"].append(source_result)
                
        return results
