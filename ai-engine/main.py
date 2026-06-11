import ipaddress
import logging
import os

from fastapi import FastAPI, Depends, Header, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session
from database import engine, Base, get_db
from logging_config import configure_logging
from crawler import RSSCrawler
from clustering import ArticleClusterer
from analyzer import GeminiAnalyzer
from gpt_analyzer import GPTAnalyzer
from dataset_builder import DatasetBuilder
from comment_crawler import CommentCrawler
from comment_analyzer import CommentAnalyzer
from models import CommentAnalysis, Comment

configure_logging()
logger = logging.getLogger(__name__)

# DB 스키마 생성 (docker-compose init에서 처리되나 혹시 모를 상황 대비)
try:
    Base.metadata.create_all(bind=engine)
except Exception:
    logger.error("Failed to initialize database metadata.", exc_info=True)
    raise

app = FastAPI(
    title="AI Analytics Engine (진로탐색)",
    description="하이브리드 AI 기반 뉴스 분석 플랫폼 Python API (Gemini, Qwen3 연동용)",
    version="1.0.0"
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
        logger.warning("Admin API blocked because client host is invalid. host=%s", client_host)
        raise HTTPException(status_code=403, detail="Admin API is not allowed from this IP.")

    if not any(client_ip in network for network in ALLOWED_ADMIN_NETWORKS):
        raise HTTPException(status_code=403, detail="Admin API is not allowed from this IP.")

    if not ADMIN_TOKEN or x_admin_token != ADMIN_TOKEN:
        raise HTTPException(status_code=401, detail="Invalid admin token.")


def raise_logged_internal_error(operation: str, exception: Exception):
    logger.error("%s failed.", operation, exc_info=True)
    raise HTTPException(status_code=500, detail=f"{operation} 처리 중 오류가 발생했습니다.") from exception

@app.get("/ping")
async def health_check():
    return {"status": "ok", "message": "AI Engine is running"}

@app.get("/")
async def root():
    return {"message": "Welcome to Hybrid AI News Analyzer (AI Engine)"}

@app.post("/api/crawl", dependencies=[Depends(verify_admin_access)])
async def crawl_rss_feeds(db: Session = Depends(get_db)):
    """등록된 언론사의 RSS 피드를 수집하고 DB에 중복 없이 저장합니다."""
    try:
        crawler = RSSCrawler(db)
        results = crawler.run()
        return {"status": "success", "data": results}
    except Exception as exc:
        raise_logged_internal_error("RSS 수집", exc)

@app.post("/api/cluster", dependencies=[Depends(verify_admin_access)])
async def cluster_articles(db: Session = Depends(get_db)):
    """수집된 기사들을 TF-IDF 벡터화 후 DBSCAN으로 클러스터링(그룹핑)합니다."""
    try:
        clusterer = ArticleClusterer(db)
        results = clusterer.run()
        return {"status": "success", "data": results}
    except Exception as exc:
        raise_logged_internal_error("기사 클러스터링", exc)

@app.post("/api/analyze", dependencies=[Depends(verify_admin_access)])
async def analyze_articles(db: Session = Depends(get_db)):
    """Gemini API를 호출하여 기사별 중립성을 평가하고 DB에 저장합니다."""
    try:
        analyzer = GeminiAnalyzer(db)
        results = analyzer.run()
        return {"status": "success", "data": results}
    except Exception as exc:
        raise_logged_internal_error("Gemini 기사 분석", exc)

@app.post("/api/analyze_gpt", dependencies=[Depends(verify_admin_access)])
async def analyze_articles_gpt(db: Session = Depends(get_db)):
    """OpenAI(GPT) API를 호출하여 기사별 중립성을 평가하고 DB에 저장합니다."""
    try:
        analyzer = GPTAnalyzer(db)
        results = analyzer.run()
        return {"status": "success", "data": results}
    except Exception as exc:
        raise_logged_internal_error("GPT 기사 분석", exc)

@app.post("/api/dataset/build", dependencies=[Depends(verify_admin_access)])
async def build_dataset(db: Session = Depends(get_db)):
    """LLM 파인튜닝을 위한 ChatML 포맷의 JSONL 학습 데이터셋을 생성합니다."""
    try:
        builder = DatasetBuilder(db)
        results = builder.build_chatml_dataset()
        return {"status": "success", "data": results}
    except Exception as exc:
        raise_logged_internal_error("데이터셋 생성", exc)

@app.post("/api/comments/collect", dependencies=[Depends(verify_admin_access)])
async def collect_comments(article_id: int = None, db: Session = Depends(get_db)):
    """지원 출처의 뉴스 댓글을 수집하여 DB에 저장합니다. article_id 미지정 시 전체 처리."""
    try:
        crawler = CommentCrawler(db)
        results = crawler.run(article_id=article_id)
        return {"status": "success", "data": results}
    except Exception as exc:
        raise_logged_internal_error("댓글 수집", exc)

@app.post("/api/comments/analyze", dependencies=[Depends(verify_admin_access)])
async def analyze_comments(db: Session = Depends(get_db)):
    """수집된 댓글을 Gemini로 분석하여 기사별 여론 요약 및 감정 비율을 DB에 저장합니다."""
    try:
        analyzer = CommentAnalyzer(db)
        results = analyzer.run()
        return {"status": "success", "data": results}
    except Exception as exc:
        raise_logged_internal_error("댓글 여론 분석", exc)

@app.get("/api/comments/analysis/{article_id}")
async def get_comment_analysis(article_id: int, db: Session = Depends(get_db)):
    """특정 기사의 여론 분석 결과와 댓글 목록을 반환합니다."""
    analysis = db.query(CommentAnalysis).filter(CommentAnalysis.article_id == article_id).first()
    comments = db.query(Comment).filter(Comment.article_id == article_id).order_by(Comment.likes.desc()).limit(20).all()
    if not analysis and not comments:
        raise HTTPException(status_code=404, detail="해당 기사의 댓글 분석 결과가 없습니다.")

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
                    {"content": c.content, "author": c.author, "likes": c.likes, "dislikes": c.dislikes}
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
            "avg_sentiment": analysis.avg_sentiment,
            "positive_ratio": analysis.positive_ratio,
            "negative_ratio": analysis.negative_ratio,
            "neutral_ratio": analysis.neutral_ratio,
            "public_opinion": analysis.public_opinion,
            "analyzed_at": analysis.analyzed_at,
            "top_comments": [
                {"content": c.content, "author": c.author, "likes": c.likes, "dislikes": c.dislikes}
                for c in comments
            ],
        },
    }
