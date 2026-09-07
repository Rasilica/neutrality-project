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


def test_operation_routes_submit_jobs(monkeypatch):
    submitted = []

    def fake_submit(operation, task):
        submitted.append((operation, task))
        return "job-123"

    monkeypatch.setattr(main, "submit_operation", fake_submit)

    response = asyncio.run(main.crawl_rss_feeds())

    assert response == {
        "status": "accepted",
        "data": {"job_id": "job-123", "operation": "rss-crawl"},
    }
    assert submitted[0][0] == "rss-crawl"


def test_collect_comments_submits_article_id(monkeypatch):
    submitted = []

    def fake_submit(operation, task):
        submitted.append((operation, task))
        return "job-456"

    monkeypatch.setattr(main, "submit_operation", fake_submit)

    response = asyncio.run(main.collect_comments(article_id=17))

    assert response["data"] == {"job_id": "job-456", "operation": "comment-crawl"}
    assert submitted[0][0] == "comment-crawl"


def test_job_status_route_requires_existing_job(monkeypatch):
    monkeypatch.setattr(main.job_manager, "get", lambda _job_id: {"status": "running"})
    assert asyncio.run(main.get_job_status("job-123")) == {
        "status": "success",
        "data": {"status": "running"},
    }

    monkeypatch.setattr(main.job_manager, "get", lambda _job_id: None)
    with pytest.raises(HTTPException) as missing:
        asyncio.run(main.get_job_status("missing"))
    assert missing.value.status_code == 404


def test_long_running_routes_document_202_accepted():
    for path in (
        "/api/crawl",
        "/api/cluster",
        "/api/analyze",
        "/api/analyze_gpt",
        "/api/dataset/build",
        "/api/comments/collect",
        "/api/comments/analyze",
    ):
        responses = main.app.openapi()["paths"][path]["post"]["responses"]
        assert "202" in responses


@pytest.mark.parametrize(
    ("route", "operation"),
    [
        (main.crawl_rss_feeds, "rss-crawl"),
        (main.cluster_articles, "article-cluster"),
        (main.analyze_articles, "gemini-analysis"),
        (main.analyze_articles_gpt, "gpt-analysis"),
        (main.build_dataset, "dataset-build"),
        (main.analyze_comments, "comment-analysis"),
    ],
)
def test_operation_routes_return_accepted_job(monkeypatch, route, operation):
    monkeypatch.setattr(main, "submit_operation", lambda name, task: f"job-{name}")

    response = asyncio.run(route())

    assert response == {
        "status": "accepted",
        "data": {"job_id": f"job-{operation}", "operation": operation},
    }


def test_service_task_uses_fresh_session_and_closes_it(monkeypatch):
    class FakeSession:
        def __init__(self):
            self.closed = False

        def close(self):
            self.closed = True

    session = FakeSession()
    monkeypatch.setattr(main, "SessionLocal", lambda: session)
    monkeypatch.setattr(main, "RSSCrawler", FakeOperation)

    result = main._execute_service(main.RSSCrawler)

    assert result == {"db": session}
    assert session.closed is True


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
