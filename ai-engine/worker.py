import logging

from apscheduler.schedulers.blocking import BlockingScheduler

from analyzer import GeminiAnalyzer
from clustering import ArticleClusterer
from comment_analyzer import CommentAnalyzer
from comment_crawler import CommentCrawler
from crawler import RSSCrawler
from database import SessionLocal
from gpt_analyzer import GPTAnalyzer
from logging_config import configure_logging

configure_logging()
logger = logging.getLogger(__name__)


def scheduled_pipeline():
    logger.info("Starting worker pipeline: Crawl -> Cluster -> Analyze -> Comments")
    db = SessionLocal()

    try:
        pipeline_steps = [
            ("RSS crawl", lambda: RSSCrawler(db).run()),
            ("Article clustering", lambda: ArticleClusterer(db).run()),
            ("Gemini article analysis", lambda: GeminiAnalyzer(db).run()),
            ("GPT article analysis", lambda: GPTAnalyzer(db).run()),
            ("Comment crawl", lambda: CommentCrawler(db).run()),
            ("Comment analysis", lambda: CommentAnalyzer(db).run()),
        ]

        for step_name, step in pipeline_steps:
            try:
                result = step()
                logger.info("Worker step completed. step=%s result=%s", step_name, result)
            except Exception:
                logger.error("Worker step failed. step=%s", step_name, exc_info=True)
                db.rollback()

        logger.info("Worker pipeline completed.")
    except Exception:
        logger.error("Worker pipeline failed.", exc_info=True)
        db.rollback()
    finally:
        db.close()


if __name__ == "__main__":
    scheduler = BlockingScheduler()
    scheduler.add_job(
        scheduled_pipeline,
        "interval",
        hours=8,
        id="news_pipeline",
        max_instances=1,
        coalesce=True,
    )
    logger.info("AI engine worker started.")
    try:
        scheduled_pipeline()
        scheduler.start()
    except (KeyboardInterrupt, SystemExit):
        logger.info("AI engine worker stopped.")
    except Exception:
        logger.error("AI engine scheduler crashed.", exc_info=True)
