import os
import json
import logging
from sqlalchemy import select
from sqlalchemy.orm import Session
import google.generativeai as genai

from models import Article, AnalysisResult, Comment, CommentAnalysis

logger = logging.getLogger(__name__)

# 댓글 감정 분석 시 AI에 한 번에 넘길 최대 댓글 수 (프롬프트 길이 제한 고려)
MAX_COMMENTS_PER_REQUEST = 80
SBS_NEWS_URL_PATTERN = "%news.sbs.co.kr%"


class CommentAnalyzer:
    """
    수집된 댓글을 Gemini API로 일괄 분석하여
    개별 감정 비율과 여론 종합 요약을 comment_analysis 테이블에 저장하는 분석기.
    """

    def __init__(self, db: Session):
        self.db = db
        self.api_key = os.getenv("GEMINI_API_KEY")
        if self.api_key:
            genai.configure(api_key=self.api_key)
            self.model = genai.GenerativeModel("gemini-2.5-flash")
        else:
            logger.warning("GEMINI_API_KEY is not set.")

    def _query_eligible_articles(self):
        analyzed_ids = select(CommentAnalysis.article_id)
        return (
            self.db.query(Article)
            .join(Comment, Article.id == Comment.article_id)
            .join(AnalysisResult, Article.id == AnalysisResult.article_id)
            .filter(Article.url.like(SBS_NEWS_URL_PATTERN), Article.id.not_in(analyzed_ids))
            .distinct()
            .limit(5)
        )

    def _generate_and_parse_json(self, prompt: str) -> dict:
        last_error = None
        for attempt in range(2):
            response = self.model.generate_content(prompt)
            response_text = response.text.replace("```json", "").replace("```", "").strip()
            try:
                return json.loads(response_text)
            except json.JSONDecodeError as exc:
                last_error = exc
                if attempt == 0:
                    logger.warning("Gemini returned invalid JSON. Retrying once.")
        raise last_error

    def run(self) -> dict:
        """
        댓글이 존재하지만 아직 여론 분석이 수행되지 않은 기사를 최대 5건 처리합니다.
        기사별 전체 댓글을 Gemini에 넘겨 감정 비율과 여론 요약을 도출합니다.
        """
        if not self.api_key:
            return {"status": "error", "message": "GEMINI_API_KEY is missing."}

        # SBS 기사 중 댓글과 기사 분석이 있고 아직 댓글 여론 분석이 없는 기사만 처리
        articles = self._query_eligible_articles().all()

        if not articles:
            return {"status": "success", "message": "No new comments to analyze.", "analyzed_count": 0}

        analyzed_count = 0
        errors = 0

        for article in articles:
            try:
                comments = (
                    self.db.query(Comment)
                    .filter(Comment.article_id == article.id)
                    .order_by(Comment.likes.desc())  # 공감 많은 댓글 우선
                    .limit(MAX_COMMENTS_PER_REQUEST)
                    .all()
                )
                total_in_db = self.db.query(Comment).filter(Comment.article_id == article.id).count()

                comment_block = "\n".join([f"- {c.content}" for c in comments])

                prompt = f"""당신은 한국 뉴스 댓글 여론 분석 전문가입니다.
다음은 뉴스 기사에 달린 댓글 목록입니다.

[기사 제목]: {article.title}

[댓글 목록]:
{comment_block}

위 댓글들을 분석하여 아래 항목을 평가하고, 반드시 주어진 형식의 JSON 문자열로만 응답하세요. (마크다운 블록이나 다른 텍스트는 절대 출력하지 마세요)

1. avg_sentiment: 전체 댓글의 평균 감정 점수 (-1.0 매우 부정 ~ 1.0 매우 긍정)
2. positive_ratio: 긍정적인 댓글의 비율 (0.0 ~ 1.0)
3. negative_ratio: 부정적인 댓글의 비율 (0.0 ~ 1.0)
4. neutral_ratio: 중립적인 댓글의 비율 (0.0 ~ 1.0, positive+negative+neutral=1.0)
5. public_opinion: 댓글 여론의 핵심 흐름을 3문장 이내로 종합 요약한 텍스트 (한국어)

{{
  "avg_sentiment": 0.0,
  "positive_ratio": 0.0,
  "negative_ratio": 0.0,
  "neutral_ratio": 0.0,
  "public_opinion": "여론 요약"
}}"""

                result_data = self._generate_and_parse_json(prompt)

                analysis = CommentAnalysis(
                    article_id=article.id,
                    total_comments=total_in_db,
                    avg_sentiment=float(result_data.get("avg_sentiment", 0.0)),
                    positive_ratio=float(result_data.get("positive_ratio", 0.0)),
                    negative_ratio=float(result_data.get("negative_ratio", 0.0)),
                    neutral_ratio=float(result_data.get("neutral_ratio", 0.0)),
                    public_opinion=str(result_data.get("public_opinion", "")),
                    raw_response=result_data,
                )
                self.db.add(analysis)
                analyzed_count += 1

            except Exception:
                logger.error("기사 댓글 여론 분석 중 오류. article_id=%s", article.id, exc_info=True)
                errors += 1

        try:
            self.db.commit()
        except Exception:
            logger.error("Failed to commit comment analysis results.", exc_info=True)
            self.db.rollback()
            return {
                "status": "error",
                "message": "Failed to commit comment analysis results.",
                "analyzed_count": analyzed_count,
                "errors": errors + 1,
            }

        return {
            "status": "success",
            "analyzed_count": analyzed_count,
            "errors": errors,
        }
