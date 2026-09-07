from types import SimpleNamespace

import pytest
import requests

import crawler as crawler_module
import network_security
from crawler import RSSCrawler
from models import NewsSource


class FakeResponse:
    def __init__(
        self, content=b"<rss />", status_code=200, url="https://example.com/rss"
    ):
        self.content = content
        self.status_code = status_code
        self.url = url
        self.headers = {}

    def raise_for_status(self):
        if self.status_code >= 400:
            raise requests.HTTPError(f"HTTP {self.status_code}")

    def close(self):
        return None


class FakeSourceQuery:
    def __init__(self, sources):
        self.sources = sources

    def all(self):
        return self.sources


class FakeArticleQuery:
    def __init__(self, existing=None):
        self.existing = existing

    def filter(self, *_args, **_kwargs):
        return self

    def first(self):
        return self.existing


class FakeDb:
    def __init__(self, sources, existing=None, fail_commit=False):
        self.sources = sources
        self.existing = existing
        self.fail_commit = fail_commit
        self.added = []
        self.commits = 0
        self.rollbacks = 0

    def query(self, target):
        if target is NewsSource:
            return FakeSourceQuery(self.sources)
        return FakeArticleQuery(self.existing)

    def add(self, item):
        self.added.append(item)

    def commit(self):
        if self.fail_commit:
            raise RuntimeError("commit failed")
        self.commits += 1

    def rollback(self):
        self.rollbacks += 1


def test_extract_article_content_prefers_json_ld_article_body():
    html = """
    <html>
      <head>
        <script type="application/ld+json">
          {"@type": "NewsArticle", "articleBody": "실제 기사 본문입니다. 관련 목록 문구가 섞이면 안 됩니다."}
        </script>
      </head>
      <body><p>관련 기사 목록</p></body>
    </html>
    """

    assert (
        RSSCrawler.extract_article_content(html)
        == "실제 기사 본문입니다. 관련 목록 문구가 섞이면 안 됩니다."
    )


def test_extract_article_content_uses_article_then_meta_then_paragraph_fallbacks():
    article_html = """
    <article><script>remove me</script><p>첫 문단</p><p>둘째 문단</p></article>
    """
    meta_html = (
        '<html><head><meta name="description" content=" 메타 설명 "></head></html>'
    )
    paragraph_html = "<html><body><p>첫 문단</p><p>둘째 문단</p></body></html>"

    assert RSSCrawler.extract_article_content(article_html) == "첫 문단 둘째 문단"
    assert RSSCrawler.extract_article_content(meta_html) == "메타 설명"
    assert RSSCrawler.extract_article_content(paragraph_html) == "첫 문단 둘째 문단"


def test_extract_entry_summary_strips_html_and_parse_datetime_handles_edge_cases():
    assert (
        RSSCrawler.extract_entry_summary({"summary": "<p>요약 <b>본문</b></p>"})
        == "요약 본문"
    )
    assert RSSCrawler.extract_entry_summary({}) == ""
    assert RSSCrawler.parse_entry_datetime({}) is None

    with pytest.raises(ValueError, match="Invalid date"):
        RSSCrawler.parse_entry_datetime({"published": "not-a-date"})


def test_run_counts_feed_fetch_errors(monkeypatch):
    source = SimpleNamespace(
        id=1, name="실패 RSS", rss_url="https://rss.invalid/feed.xml"
    )
    db = FakeDb([source])

    def fail_request(*_args, **_kwargs):
        raise requests.RequestException("dns failed")

    monkeypatch.setattr(network_security.requests, "get", fail_request)

    result = RSSCrawler(db).run()

    assert result["new_articles"] == 0
    assert result["errors"] == 1
    assert result["source_results"][0]["status"] == "feed_error"
    assert "dns failed" in result["source_results"][0]["error"]
    assert db.added == []


def test_parse_entry_datetime_supports_dot_separated_dates():
    parsed = RSSCrawler.parse_entry_datetime({"published": "2024.10.29"})

    assert parsed.year == 2024
    assert parsed.month == 10
    assert parsed.day == 29
    assert parsed.tzinfo is not None


def test_run_processes_valid_feed_entries(monkeypatch):
    source = SimpleNamespace(
        id=1, name="정상 RSS", rss_url="https://example.com/rss.xml"
    )
    db = FakeDb([source])
    entry = {
        "link": "https://example.com/article/1",
        "title": "테스트 기사",
        "published": "Sat, 06 Jun 2026 17:40:00 +0900",
    }

    monkeypatch.setattr(
        network_security.requests, "get", lambda *_args, **_kwargs: FakeResponse()
    )
    monkeypatch.setattr(
        crawler_module.feedparser,
        "parse",
        lambda _content: SimpleNamespace(entries=[entry], bozo=False),
    )
    monkeypatch.setattr(
        RSSCrawler, "scrape_article_content", lambda _self, _url: "본문"
    )

    result = RSSCrawler(db).run()

    assert result["new_articles"] == 1
    assert result["errors"] == 0
    assert result["source_results"][0]["entries"] == 1
    assert result["source_results"][0]["new_articles"] == 1
    assert db.added[0].title == "테스트 기사"
    assert db.added[0].content == "본문"
    assert db.commits == 1


def test_run_uses_rss_summary_when_scraped_content_is_too_short(monkeypatch):
    source = SimpleNamespace(
        id=1, name="요약 RSS", rss_url="https://example.com/rss.xml"
    )
    db = FakeDb([source])
    summary = "RSS에 포함된 기사 요약 본문입니다. HTML 페이지가 앱 셸만 반환할 때 이 값을 사용합니다."
    entry = {
        "link": "https://example.com/article/summary",
        "title": "요약 기사",
        "published": "2026-06-06",
        "summary": summary,
    }

    monkeypatch.setattr(
        network_security.requests, "get", lambda *_args, **_kwargs: FakeResponse()
    )
    monkeypatch.setattr(
        crawler_module.feedparser,
        "parse",
        lambda _content: SimpleNamespace(entries=[entry], bozo=False),
    )
    monkeypatch.setattr(
        RSSCrawler,
        "scrape_article_content",
        lambda _self, _url: "JTBC | 진실에 닿을 때까지 멈추지 않는 질문",
    )

    result = RSSCrawler(db).run()

    assert result["new_articles"] == 1
    assert db.added[0].content == summary


def test_scrape_article_content_blocks_private_network_before_request(monkeypatch):
    crawler = RSSCrawler(FakeDb([]))
    crawler.allowed_hosts = ("127.0.0.1",)
    request_called = False

    def fake_get(*_args, **_kwargs):
        nonlocal request_called
        request_called = True

    monkeypatch.setattr(network_security.requests, "get", fake_get)

    assert crawler.scrape_article_content("http://127.0.0.1/admin") == ""
    assert request_called is False


def test_run_skips_missing_links_and_reports_empty_feeds(monkeypatch):
    sources = [
        SimpleNamespace(id=1, name="링크 없음", rss_url="https://example.com/missing"),
        SimpleNamespace(id=2, name="빈 피드", rss_url="https://example.com/empty"),
    ]
    db = FakeDb(sources)
    crawler = RSSCrawler(db)
    feeds = iter(
        [
            SimpleNamespace(entries=[{"title": "링크 없음"}], bozo=False),
            SimpleNamespace(
                entries=[], bozo=True, bozo_exception=ValueError("broken xml")
            ),
        ]
    )
    monkeypatch.setattr(crawler, "fetch_feed", lambda _source: next(feeds))

    result = crawler.run()

    assert result["errors"] == 2
    assert result["source_results"][0]["status"] == "success"
    assert result["source_results"][1]["status"] == "feed_error"
    assert db.rollbacks == 1


def test_run_updates_incomplete_duplicate_and_rolls_back_commit_failure(monkeypatch):
    source = SimpleNamespace(id=1, name="중복", rss_url="https://example.com/rss.xml")
    existing = SimpleNamespace(published_at=None, content="짧음")
    db = FakeDb([source], existing=existing, fail_commit=True)
    crawler = RSSCrawler(db)
    entry = {
        "link": "https://example.com/article/1",
        "title": "중복 기사",
        "published": "2026-06-06",
        "summary": "대체 요약",
    }
    monkeypatch.setattr(
        crawler,
        "fetch_feed",
        lambda _source: SimpleNamespace(entries=[entry], bozo=False),
    )
    monkeypatch.setattr(
        crawler, "scrape_article_content", lambda _url: "보강된 본문" * 30
    )

    result = crawler.run()

    assert existing.published_at is not None
    assert existing.content.startswith("보강된 본문")
    assert result["source_results"][0]["duplicates"] == 1
    assert result["source_results"][0]["status"] == "feed_error"
    assert db.rollbacks == 1
