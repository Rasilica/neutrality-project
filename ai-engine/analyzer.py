import logging
import os
from typing import TypeVar

from google import genai
from google.genai import types
from pydantic import BaseModel, ValidationError
from sqlalchemy.orm import Session

from analysis_schemas import ArticleAnalysisPayload
from models import AnalysisResult, Article, Comment
from source_scope import source_url_filter

logger = logging.getLogger(__name__)

PayloadT = TypeVar("PayloadT", bound=BaseModel)


class GeminiAnalyzer:
    model_name = "gemini-2.5-flash"

    def __init__(self, db: Session):
        self.db = db
        # 컨테이너 환경변수에서 API 키를 가져옵니다.
        self.api_key = os.getenv("GEMINI_API_KEY")
        if self.api_key:
            self.client = genai.Client(api_key=self.api_key)
        else:
            self.client = None
            logger.warning("GEMINI_API_KEY is not set.")

    def _query_eligible_articles(self):
        return (
            self.db.query(Article)
            .join(Comment, Article.id == Comment.article_id)
            .outerjoin(
                AnalysisResult,
                (Article.id == AnalysisResult.article_id)
                & (AnalysisResult.model_used == self.model_name),
            )
            .filter(source_url_filter(Article.url), AnalysisResult.id.is_(None))
            .distinct()
            .limit(10)
        )

    def _generate_and_validate(self, prompt: str, schema: type[PayloadT]) -> PayloadT:
        last_error = None
        for attempt in range(2):
            try:
                response = self.client.models.generate_content(
                    model=self.model_name,
                    contents=prompt,
                    config=types.GenerateContentConfig(
                        response_mime_type="application/json",
                        response_json_schema=schema.model_json_schema(),
                    ),
                )
                return schema.model_validate_json(response.text)
            except ValidationError as exc:
                last_error = exc
                if attempt == 0:
                    logger.warning(
                        "Gemini returned an invalid structured response. Retrying once."
                    )
        raise last_error

    def run(self) -> dict:
        """
        아직 분석되지 않은 기사들을 조회하여 Gemini 객체에 전달하고
        3단계 중립성 평가 점수를 받아 DB에 저장합니다.
        """
        if not self.client:
            return {"status": "error", "message": "GEMINI_API_KEY is missing."}

        # SBS 기사 중 댓글이 있고 아직 기사 분석이 없는 기사만 우선 가져옵니다. (비용/시간 최적화)
        un_analyzed = self._query_eligible_articles().all()

        if not un_analyzed:
            return {
                "status": "success",
                "message": "No new articles to analyze.",
                "analyzed_count": 0,
            }

        analyzed_count = 0
        errors = 0

        for article in un_analyzed:
            prompt = f"""
당신은 엄격하고 객관적인 뉴스 분석 AI입니다.
다음은 뉴스 기사의 제목과 본문입니다.

[기사 제목]: {article.title}
[기사 본문]: {article.content[:4000]}

이 기사를 바탕으로 다음 3가지 항목을 분석하고, 반드시 주어진 형식의 JSON 문자열로만 응답하세요. (마크다운 블록이나 다른 텍스트는 절대 출력하지 마세요)

1. 감정 점수 (sentiment_score): -1.0 (매우 부정) ~ 1.0 (매우 긍정) 사이의 소수
2. 편향 점수 (bias_score): 0.0 (완전 중립) ~ 1.0 (매우 편향됨) 사이의 소수
3. 사실성 점수 (factuality_score): 0.0 (주관 위주) ~ 1.0 (사실/데이터 위주) 사이의 소수
4. 요약 (summary): 기사의 핵심 내용 3문장 요약 (문자열)

{{
  "sentiment_score": 0.0,
  "bias_score": 0.0,
  "factuality_score": 0.0,
  "summary": "요약 내용"
            }}
"""
            try:
                payload = self._generate_and_validate(prompt, ArticleAnalysisPayload)
                result_data = payload.model_dump(mode="json")

                analysis_result = AnalysisResult(
                    article_id=article.id,
                    model_used=self.model_name,
                    sentiment_score=payload.sentiment_score,
                    bias_score=payload.bias_score,
                    factuality_score=payload.factuality_score,
                    summary=payload.summary,
                    raw_response=result_data,
                )
                self.db.add(analysis_result)
                analyzed_count += 1
            except Exception:
                logger.error(
                    "Error analyzing article with Gemini. article_id=%s",
                    article.id,
                    exc_info=True,
                )
                errors += 1

        try:
            self.db.commit()
        except Exception:
            logger.error("Failed to commit Gemini analysis results.", exc_info=True)
            self.db.rollback()
            return {
                "status": "error",
                "message": "Failed to commit Gemini analysis results.",
                "analyzed_count": analyzed_count,
                "errors": errors + 1,
            }

        return {"status": "success", "analyzed_count": analyzed_count, "errors": errors}
