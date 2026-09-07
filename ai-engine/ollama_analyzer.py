"""Article analysis through a local Ollama HTTP API."""

import logging
import os

import requests
from pydantic import ValidationError

from analysis_schemas import ArticleAnalysisPayload
from models import AnalysisResult, Article
from source_scope import source_url_filter

logger = logging.getLogger(__name__)


class OllamaAnalyzer:
    model_name = os.getenv("OLLAMA_MODEL", "gemma4:e4b")

    def __init__(self, db):
        self.db = db
        self.base_url = os.getenv("OLLAMA_BASE_URL", "http://127.0.0.1:11434").rstrip("/")
        self.timeout = float(os.getenv("OLLAMA_TIMEOUT_SECONDS", "120"))

    def _query_eligible_articles(self):
        return (
            self.db.query(Article)
            .outerjoin(
                AnalysisResult,
                (Article.id == AnalysisResult.article_id)
                & (AnalysisResult.model_used == self.model_name),
            )
            .filter(source_url_filter(Article.url), AnalysisResult.id.is_(None))
            .distinct()
            .limit(10)
        )

    def _generate_and_validate(self, prompt: str) -> ArticleAnalysisPayload:
        response = requests.post(
            f"{self.base_url}/api/generate",
            json={
                "model": self.model_name,
                "prompt": prompt,
                "stream": False,
                "format": "json",
                "options": {"temperature": 0.1, "top_p": 0.9},
            },
            timeout=self.timeout,
        )
        response.raise_for_status()
        body = response.json()
        raw = body.get("response")
        if not isinstance(raw, str) or not raw.strip():
            raise ValueError("Ollama returned an empty response")
        return ArticleAnalysisPayload.model_validate_json(raw)

    def run(self) -> dict:
        articles = self._query_eligible_articles().all()
        if not articles:
            return {"status": "success", "message": "No new articles to analyze.", "analyzed_count": 0}

        analyzed_count = 0
        errors = 0
        for article in articles:
            prompt = f"""당신은 엄격하고 객관적인 한국어 뉴스 분석 AI입니다.
기사 제목: {article.title}
기사 본문: {article.content[:4000]}
반드시 다음 JSON 객체만 출력하세요: {{"sentiment_score": 0.0, "bias_score": 0.0, "factuality_score": 0.0, "summary": "3문장 이내 요약"}}"""
            try:
                payload = self._generate_and_validate(prompt)
                self.db.add(AnalysisResult(
                    article_id=article.id,
                    model_used=self.model_name,
                    sentiment_score=payload.sentiment_score,
                    bias_score=payload.bias_score,
                    factuality_score=payload.factuality_score,
                    summary=payload.summary,
                    raw_response=payload.model_dump(mode="json"),
                ))
                analyzed_count += 1
            except (requests.RequestException, ValueError, ValidationError):
                logger.exception("Error analyzing article with Ollama. article_id=%s", article.id)
                errors += 1

        try:
            self.db.commit()
        except Exception:
            self.db.rollback()
            logger.exception("Failed to commit Ollama analysis results.")
            return {"status": "error", "message": "Failed to commit Ollama analysis results.", "analyzed_count": analyzed_count, "errors": errors + 1}
        return {"status": "success", "analyzed_count": analyzed_count, "errors": errors, "model": self.model_name}
