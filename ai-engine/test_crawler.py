from types import SimpleNamespace

import pytest

import crawler as crawler_module
from crawler import RSSCrawler
from models import NewsSource


class FakeResponse:
    def __init__(self, content=b"<rss />", status_code=200, url="https://example.com/rss"):
        self.content = content
        self.status_code = status_code
        self.url = url

    def raise_for_status(self):
        if self.status_code >= 400:
            raise crawler_module.requests.HTTPError(f"HTTP {self.status_code}")


class FakeSourceQuery:
    def __init__(self, sources):
        self.sources = sources

    def all(self):
        return self.sources


class FakeArticleQuery:
    def filter(self, *_args, **_kwargs):
        return self

    def first(self):
        return None


class FakeDb:
    def __init__(self, sources):
        self.sources = sources
        self.added = []
        self.commits = 0
        self.rollbacks = 0

    def query(self, target):
        if target is NewsSource:
            return FakeSourceQuery(self.sources)
        return FakeArticleQuery()

    def add(self, item):
        self.added.append(item)

    def commit(self):
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

    assert RSSCrawler.extract_article_content(html) == "실제 기사 본문입니다. 관련 목록 문구가 섞이면 안 됩니다."


def test_run_counts_feed_fetch_errors(monkeypatch):
    source = SimpleNamespace(id=1, name="실패 RSS", rss_url="https://rss.invalid/feed.xml")
    db = FakeDb([source])

    def fail_request(*_args, **_kwargs):
        raise crawler_module.requests.RequestException("dns failed")

    monkeypatch.setattr(crawler_module.requests, "get", fail_request)

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
    source = SimpleNamespace(id=1, name="정상 RSS", rss_url="https://example.com/rss.xml")
    db = FakeDb([source])
    entry = {
        "link": "https://example.com/article/1",
        "title": "테스트 기사",
        "published": "Sat, 06 Jun 2026 17:40:00 +0900",
    }

    monkeypatch.setattr(crawler_module.requests, "get", lambda *_args, **_kwargs: FakeResponse())
    monkeypatch.setattr(
        crawler_module.feedparser,
        "parse",
        lambda _content: SimpleNamespace(entries=[entry], bozo=False),
    )
    monkeypatch.setattr(RSSCrawler, "scrape_article_content", lambda _self, _url: "본문")

    result = RSSCrawler(db).run()

    assert result["new_articles"] == 1
    assert result["errors"] == 0
    assert result["source_results"][0]["entries"] == 1
    assert result["source_results"][0]["new_articles"] == 1
    assert db.added[0].title == "테스트 기사"
    assert db.added[0].content == "본문"
    assert db.commits == 1


def test_run_uses_rss_summary_when_scraped_content_is_too_short(monkeypatch):
    source = SimpleNamespace(id=1, name="요약 RSS", rss_url="https://example.com/rss.xml")
    db = FakeDb([source])
    summary = "RSS에 포함된 기사 요약 본문입니다. HTML 페이지가 앱 셸만 반환할 때 이 값을 사용합니다."
    entry = {
        "link": "https://example.com/article/summary",
        "title": "요약 기사",
        "published": "2026-06-06",
        "summary": summary,
    }

    monkeypatch.setattr(crawler_module.requests, "get", lambda *_args, **_kwargs: FakeResponse())
    monkeypatch.setattr(
        crawler_module.feedparser,
        "parse",
        lambda _content: SimpleNamespace(entries=[entry], bozo=False),
    )
    monkeypatch.setattr(RSSCrawler, "scrape_article_content", lambda _self, _url: "JTBC | 진실에 닿을 때까지 멈추지 않는 질문")

    result = RSSCrawler(db).run()

    assert result["new_articles"] == 1
    assert db.added[0].content == summary
