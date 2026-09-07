import ipaddress
import logging
import os

from fastapi import Depends, FastAPI, Header, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session

from analyzer import GeminiAnalyzer
from clustering import ArticleClusterer
from comment_analyzer import CommentAnalyzer
from comment_crawler import CommentCrawler
from crawler import RSSCrawler
from database import SessionLocal, get_db
from dataset_builder import DatasetBuilder
from gpt_analyzer import GPTAnalyzer
from job_manager import JobManager
from logging_config import configure_logging
from models import Comment, CommentAnalysis
from ollama_analyzer import OllamaAnalyzer

configure_logging()
logger = logging.getLogger(__name__)
job_manager = JobManager(session_factory=SessionLocal)

app = FastAPI(
    title="AI Analytics Engine (진로탐색)",
    description="하이브리드 AI 기반 뉴스 분석 플랫폼 Python API (Gemini, Qwen3 연동용)",
    version="1.0.0",
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000",
        "http://localhost:5173",
        "http://localhost:8081",
    ],
    allow_credentials=False,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["Accept", "Content-Type", "Origin", "X-Admin-Token"],
)

ADMIN_TOKEN = os.getenv("AI_ENGINE_ADMIN_TOKEN")
ALLOWED_ADMIN_NETWORKS = [
    ipaddress.ip_network(cidr.strip())
    for cidr in os.getenv(
        "AI_ENGINE_ADMIN_CIDRS",
        "127.0.0.1/32,172.16.0.0/12,10.0.0.0/8",
    ).split(",")
    if cidr.strip()
]


def verify_admin_access(
    request: Request,
    x_admin_token: str | None = Header(default=None),
):
    client_host = request.client.host if request.client else ""
    try:
        client_ip = ipaddress.ip_address(client_host)
    except ValueError:
        logger.warning(
            "Admin API blocked because client host is invalid. host=%s", client_host
        )
        raise HTTPException(
            status_code=403, detail="Admin API is not allowed from this IP."
        )

    if not any(client_ip in network for network in ALLOWED_ADMIN_NETWORKS):
        raise HTTPException(
            status_code=403, detail="Admin API is not allowed from this IP."
        )

    if not ADMIN_TOKEN or x_admin_token != ADMIN_TOKEN:
        raise HTTPException(status_code=401, detail="Invalid admin token.")


def _execute_service(service_class, method_name="run", **kwargs):
    db = SessionLocal()
    try:
        service = service_class(db)
        return getattr(service, method_name)(**kwargs)
    finally:
        db.close()


def submit_operation(operation: str, task) -> str:
    return job_manager.submit(operation, task)


def _accepted(operation: str, job_id: str):
    return {"status": "accepted", "data": {"job_id": job_id, "operation": operation}}


@app.get("/ping")
async def health_check():
    return {"status": "ok", "message": "AI Engine is running"}


@app.get("/")
async def root():
    return {"message": "Welcome to Hybrid AI News Analyzer (AI Engine)"}


@app.post("/api/crawl", status_code=202, dependencies=[Depends(verify_admin_access)])
async def crawl_rss_feeds():
    """등록된 언론사의 RSS 피드를 수집하고 DB에 중복 없이 저장합니다."""
    job_id = submit_operation("rss-crawl", lambda: _execute_service(RSSCrawler))
    return _accepted("rss-crawl", job_id)


@app.post("/api/cluster", status_code=202, dependencies=[Depends(verify_admin_access)])
async def cluster_articles():
    """수집된 기사들을 TF-IDF 벡터화 후 DBSCAN으로 클러스터링(그룹핑)합니다."""
    job_id = submit_operation(
        "article-cluster", lambda: _execute_service(ArticleClusterer)
    )
    return _accepted("article-cluster", job_id)


@app.post("/api/analyze", status_code=202, dependencies=[Depends(verify_admin_access)])
async def analyze_articles():
    """설정된 로컬/클라우드 모델로 기사별 중립성을 평가합니다."""
    provider = os.getenv("AI_ANALYSIS_PROVIDER", "gemini").lower()
    analyzer = OllamaAnalyzer if provider == "ollama" else GeminiAnalyzer
    job_id = submit_operation(
        f"{provider}-analysis", lambda: _execute_service(analyzer)
    )
    return _accepted(f"{provider}-analysis", job_id)


@app.post(
    "/api/analyze_gpt", status_code=202, dependencies=[Depends(verify_admin_access)]
)
async def analyze_articles_gpt():
    """OpenAI(GPT) API를 호출하여 기사별 중립성을 평가하고 DB에 저장합니다."""
    job_id = submit_operation("gpt-analysis", lambda: _execute_service(GPTAnalyzer))
    return _accepted("gpt-analysis", job_id)


@app.post(
    "/api/dataset/build", status_code=202, dependencies=[Depends(verify_admin_access)]
)
async def build_dataset():
    """LLM 파인튜닝을 위한 ChatML 포맷의 JSONL 학습 데이터셋을 생성합니다."""
    job_id = submit_operation(
        "dataset-build",
        lambda: _execute_service(DatasetBuilder, "build_chatml_dataset"),
    )
    return _accepted("dataset-build", job_id)


@app.post(
    "/api/comments/collect",
    status_code=202,
    dependencies=[Depends(verify_admin_access)],
)
async def collect_comments(article_id: int = None):
    """지원 출처의 뉴스 댓글을 수집하여 DB에 저장합니다. article_id 미지정 시 전체 처리."""
    job_id = submit_operation(
        "comment-crawl",
        lambda: _execute_service(CommentCrawler, article_id=article_id),
    )
    return _accepted("comment-crawl", job_id)


@app.post(
    "/api/comments/analyze",
    status_code=202,
    dependencies=[Depends(verify_admin_access)],
)
async def analyze_comments():
    """수집된 댓글을 Gemini로 분석하여 기사별 여론 요약 및 감정 비율을 DB에 저장합니다."""
    job_id = submit_operation(
        "comment-analysis", lambda: _execute_service(CommentAnalyzer)
    )
    return _accepted("comment-analysis", job_id)


@app.get("/api/jobs/{job_id}", dependencies=[Depends(verify_admin_access)])
async def get_job_status(job_id: str):
    job = job_manager.get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="작업을 찾을 수 없습니다.")
    return {"status": "success", "data": job}


@app.get("/api/comments/analysis/{article_id}")
async def get_comment_analysis(article_id: int, db: Session = Depends(get_db)):
    """특정 기사의 여론 분석 결과와 댓글 목록을 반환합니다."""
    analysis = (
        db.query(CommentAnalysis)
        .filter(CommentAnalysis.article_id == article_id)
        .first()
    )
    comments = (
        db.query(Comment)
        .filter(Comment.article_id == article_id)
        .order_by(Comment.likes.desc())
        .limit(20)
        .all()
    )
    if not analysis and not comments:
        raise HTTPException(
            status_code=404, detail="해당 기사의 댓글 분석 결과가 없습니다."
        )

    if not analysis:
        return {
            "status": "success",
            "data": {
                "article_id": article_id,
                "analysis_status": "pending",
                "total_comments": len(comments),
                "avg_sentiment": None,
                "positive_ratio": None,
                "negative_ratio": None,
                "neutral_ratio": None,
                "public_opinion": "댓글은 수집되었고 AI 여론 분석은 아직 실행되지 않았습니다.",
                "analyzed_at": None,
                "top_comments": [
                    {
                        "content": c.content,
                        "author": c.author,
                        "likes": c.likes,
                        "dislikes": c.dislikes,
                    }
                    for c in comments
                ],
            },
        }

    return {
        "status": "success",
        "data": {
            "article_id": article_id,
            "analysis_status": "ready",
            "total_comments": analysis.total_comments,
            "analyzed_comments": getattr(analysis, "analyzed_comments", analysis.total_comments),
            "avg_sentiment": analysis.avg_sentiment,
            "positive_ratio": analysis.positive_ratio,
            "negative_ratio": analysis.negative_ratio,
            "neutral_ratio": analysis.neutral_ratio,
            "public_opinion": analysis.public_opinion,
            "analyzed_at": analysis.analyzed_at,
            "top_comments": [
                {
                    "content": c.content,
                    "author": c.author,
                    "likes": c.likes,
                    "dislikes": c.dislikes,
                }
                for c in comments
            ],
        },
    }
