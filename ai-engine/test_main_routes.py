import asyncio
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

import main
from models import Comment, CommentAnalysis


class FakeOperation:
    def __init__(self, db):
        self.db = db

    def run(self, **kwargs):
        return {"db": self.db, **kwargs}

    def build_chatml_dataset(self):
        return {"db": self.db, "built": True}


@pytest.mark.parametrize(
    ("symbol", "route", "expected"),
    [
        ("RSSCrawler", main.crawl_rss_feeds, {"db": "db"}),
        ("ArticleClusterer", main.cluster_articles, {"db": "db"}),
        ("GeminiAnalyzer", main.analyze_articles, {"db": "db"}),
        ("GPTAnalyzer", main.analyze_articles_gpt, {"db": "db"}),
        ("DatasetBuilder", main.build_dataset, {"db": "db", "built": True}),
        ("CommentAnalyzer", main.analyze_comments, {"db": "db"}),
    ],
)
def test_operation_routes_return_service_results(monkeypatch, symbol, route, expected):
    monkeypatch.setattr(main, symbol, FakeOperation)

    response = asyncio.run(route("db"))

    assert response == {"status": "success", "data": expected}


def test_collect_comments_passes_optional_article_id(monkeypatch):
    monkeypatch.setattr(main, "CommentCrawler", FakeOperation)

    response = asyncio.run(main.collect_comments(article_id=17, db="db"))

    assert response["data"] == {"db": "db", "article_id": 17}


def test_operation_route_returns_generic_http_error(monkeypatch):
    class FailedOperation(FakeOperation):
        def run(self, **_kwargs):
            raise RuntimeError("sensitive internal failure")

    monkeypatch.setattr(main, "RSSCrawler", FailedOperation)

    with pytest.raises(HTTPException) as error:
        asyncio.run(main.crawl_rss_feeds("db"))

    assert error.value.status_code == 500
    assert error.value.detail == "RSS 수집 처리 중 오류가 발생했습니다."
    assert "sensitive" not in error.value.detail


def test_health_and_root_routes():
    assert asyncio.run(main.health_check())["status"] == "ok"
    assert "Hybrid AI" in asyncio.run(main.root())["message"]


def test_verify_admin_access_rejects_invalid_external_and_missing_token(monkeypatch):
    monkeypatch.setattr(main, "ADMIN_TOKEN", "secret")
    local_request = SimpleNamespace(client=SimpleNamespace(host="127.0.0.1"))
    external_request = SimpleNamespace(client=SimpleNamespace(host="8.8.8.8"))
    invalid_request = SimpleNamespace(client=SimpleNamespace(host="not-an-ip"))

    main.verify_admin_access(local_request, "secret")
    with pytest.raises(HTTPException) as missing_token:
        main.verify_admin_access(local_request, None)
    with pytest.raises(HTTPException) as external:
        main.verify_admin_access(external_request, "secret")
    with pytest.raises(HTTPException) as invalid:
        main.verify_admin_access(invalid_request, "secret")

    assert missing_token.value.status_code == 401
    assert external.value.status_code == 403
    assert invalid.value.status_code == 403


class FakeQuery:
    def __init__(self, rows=None, first_value=None):
        self.rows = rows or []
        self.first_value = first_value

    def filter(self, *_args):
        return self

    def order_by(self, *_args):
        return self

    def limit(self, _value):
        return self

    def first(self):
        return self.first_value

    def all(self):
        return self.rows


class CommentDb:
    def __init__(self, analysis, comments):
        self.analysis = analysis
        self.comments = comments

    def query(self, target):
        if target is CommentAnalysis:
            return FakeQuery(first_value=self.analysis)
        if target is Comment:
            return FakeQuery(rows=self.comments)
        raise AssertionError(target)


def test_get_comment_analysis_returns_ready_payload_and_not_found():
    analysis = SimpleNamespace(
        total_comments=3,
        avg_sentiment=0.2,
        positive_ratio=0.5,
        negative_ratio=0.25,
        neutral_ratio=0.25,
        public_opinion="의견 요약",
        analyzed_at="now",
    )
    comments = [SimpleNamespace(content="댓글", author="user", likes=2, dislikes=0)]

    ready = asyncio.run(main.get_comment_analysis(5, CommentDb(analysis, comments)))

    assert ready["data"]["analysis_status"] == "ready"
    assert ready["data"]["positive_ratio"] == 0.5
    with pytest.raises(HTTPException) as not_found:
        asyncio.run(main.get_comment_analysis(6, CommentDb(None, [])))
    assert not_found.value.status_code == 404
