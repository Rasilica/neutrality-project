import os
import json
import logging
from sqlalchemy.orm import Session
from openai import OpenAI

from models import Article, AnalysisResult, Comment

logger = logging.getLogger(__name__)

SBS_NEWS_URL_PATTERN = "%news.sbs.co.kr%"

class GPTAnalyzer:
    def __init__(self, db: Session):
        self.db = db
        self.api_key = os.getenv("OPENAI_API_KEY")
        if self.api_key:
            self.client = OpenAI(api_key=self.api_key)
            self.model_name = "gpt-4o-mini"
        else:
            self.client = None
            logger.warning("OPENAI_API_KEY is not set.")

    def _query_eligible_articles(self):
        return (
            self.db.query(Article)
            .join(Comment, Article.id == Comment.article_id)
            .outerjoin(
                AnalysisResult,
                (Article.id == AnalysisResult.article_id) & (AnalysisResult.model_used == self.model_name),
            )
            .filter(Article.url.like(SBS_NEWS_URL_PATTERN), AnalysisResult.id == None)
            .distinct()
            .limit(10)
        )

    def run(self) -> dict:
        """
        GPT를 사용하여 아직 GPT로 분석되지 않은 기사들의 3단계 중립성 평가 점수를 도출합니다.
        """
        if not self.client:
            return {"status": "error", "message": "OPENAI_API_KEY is missing."}

        # SBS 기사 중 댓글이 있고 이 모델(gpt)로 아직 분석되지 않은 기사 10건 조회
        un_analyzed = self._query_eligible_articles().all()

        if not un_analyzed:
            return {"status": "success", "message": "No new articles to analyze with GPT.", "analyzed_count": 0}

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
                response = self.client.chat.completions.create(
                    model=self.model_name,
                    messages=[
                        {"role": "system", "content": "You are a helpful and strict JSON answering assistant."},
                        {"role": "user", "content": prompt}
                    ],
                    response_format={"type": "json_object"}
                )
                
                response_text = response.choices[0].message.content.strip()
                result_data = json.loads(response_text)

                analysis_result = AnalysisResult(
                    article_id=article.id,
                    model_used=self.model_name,
                    sentiment_score=float(result_data.get("sentiment_score", 0.0)),
                    bias_score=float(result_data.get("bias_score", 0.0)),
                    factuality_score=float(result_data.get("factuality_score", 0.0)),
                    summary=str(result_data.get("summary", "")),
                    raw_response=result_data
                )
                self.db.add(analysis_result)
                analyzed_count += 1
            except Exception:
                logger.error("Error analyzing article with GPT. article_id=%s", article.id, exc_info=True)
                errors += 1
                
        try:
            self.db.commit()
        except Exception:
            logger.error("Failed to commit GPT analysis results.", exc_info=True)
            self.db.rollback()
            return {
                "status": "error",
                "message": "Failed to commit GPT analysis results.",
                "analyzed_count": analyzed_count,
                "errors": errors + 1
            }
        
        return {
            "status": "success",
            "analyzed_count": analyzed_count,
            "errors": errors
        }
