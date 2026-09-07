import json
from types import SimpleNamespace

import requests

import network_security
from comment_crawler import CommentCrawler
from models import Article


class FakeResponse:
    def __init__(self, payload, status_code=200, text=None):
        self.payload = payload
        self.status_code = status_code
        self.text = str(payload) if text is None else text
        self.headers = {"content-type": "application/json"}

    def raise_for_status(self):
        if self.status_code >= 400:
            raise requests.HTTPError(f"HTTP {self.status_code}")

    def json(self):
        return self.payload

    def close(self):
        return None


class FakeArticleQuery:
    def __init__(self, articles):
        self.articles = articles

    def outerjoin(self, *_args, **_kwargs):
        return self

    def filter(self, *_args, **_kwargs):
        return self

    def limit(self, *_args, **_kwargs):
        return self

    def all(self):
        return self.articles


class FakeCommentQuery:
    def __init__(self, rows=None):
        self.rows = rows or []

    def filter(self, *_args, **_kwargs):
        return self

    def all(self):
        return self.rows


class FakeDb:
    def __init__(self, articles, existing_comments=None, fail_commit=False):
        self.articles = articles
        self.existing_comments = existing_comments or []
        self.fail_commit = fail_commit
        self.added = []
        self.commits = 0
        self.rollbacks = 0

    def query(self, *targets):
        if targets and targets[0] is Article:
            return FakeArticleQuery(self.articles)
        return FakeCommentQuery(self.existing_comments)

    def add(self, item):
        self.added.append(item)

    def commit(self):
        if self.fail_commit:
            raise RuntimeError("commit failed")
        self.commits += 1

    def rollback(self):
        self.rollbacks += 1


def test_detect_comment_target_supports_naver_sbs_and_unsupported_sources():
    crawler = CommentCrawler(SimpleNamespace())

    assert crawler._detect_comment_target(
        "https://n.news.naver.com/mnews/article/001/0015420978"
    ) == {
        "provider": "naver",
        "oid": "001",
        "aid": "0015420978",
    }

    assert crawler._detect_comment_target(
        "https://news.sbs.co.kr/news/endPage.do?news_id=N1008597091&plink=RSSLINK"
    ) == {
        "provider": "sbs",
        "article_id": "N1008597091",
        "category": "NA",
        "news_type": "N",
    }

    assert (
        crawler._detect_comment_target(
            "https://news.jtbc.co.kr/article/article.aspx?news_id=NB12220953"
        )
        is None
    )


def test_detect_comment_target_rejects_lookalike_hosts_and_credentials():
    crawler = CommentCrawler(SimpleNamespace())

    unsafe_urls = [
        "https://news.sbs.co.kr.attacker.test/news/endPage.do?news_id=N1008597091",
        "https://attacker.test/n.news.naver.com/article/001/0015420978",
        "https://user@news.sbs.co.kr/news/endPage.do?news_id=N1008597091",
        "javascript:https://n.news.naver.com/article/001/0015420978",
    ]

    assert all(crawler._detect_comment_target(url) is None for url in unsafe_urls)


def test_detect_comment_target_supports_sbs_path_and_article_id_variants():
    crawler = CommentCrawler(SimpleNamespace())

    assert crawler._detect_comment_target(
        "https://news.sbs.co.kr/article/N1008597091"
    ) == {
        "provider": "sbs",
        "article_id": "N1008597091",
        "category": "NA",
        "news_type": "N",
    }
    assert crawler._detect_comment_target(
        "https://news.sbs.co.kr/news/endPage.do?article_id=12345678"
    ) == {
        "provider": "sbs",
        "article_id": "12345678",
        "category": "EA",
        "news_type": "E",
    }
    assert (
        crawler._detect_comment_target(
            "https://news.sbs.co.kr/news/endPage.do?news_id=../../admin"
        )
        is None
    )
    assert (
        crawler._detect_comment_target(
            "https://news.sbs.co.kr/article/N1008597091unexpected"
        )
        is None
    )


def test_normalize_sbs_comment_strips_html_and_skips_deleted_comments():
    crawler = CommentCrawler(SimpleNamespace())

    normalized = crawler._normalize_sbs_comment(
        {
            "CONTENT": "첫줄<br>둘째 &amp; 셋째",
            "USER_NAME": "홍길동",
            "LIKE_CNT": 3,
            "DISLIKE_CNT": 1,
            "STATUS": "V1",
        }
    )

    assert normalized == {
        "content": "첫줄\n둘째 & 셋째",
        "author": "홍길동",
        "likes": 3,
        "dislikes": 1,
    }
    assert (
        crawler._normalize_sbs_comment(
            {"CONTENT": "작성자가 삭제한 댓글입니다.", "STATUS": "D1"}
        )
        is None
    )


def test_normalize_naver_comment_and_flatten_sbs_replies():
    crawler = CommentCrawler(SimpleNamespace())

    assert crawler._normalize_naver_comment(
        {
            "contents": "<b>좋은</b> 기사",
            "maskedUserId": "user***",
            "sympathyCount": "4",
            "antipathyCount": "invalid",
        }
    ) == {
        "content": "좋은 기사",
        "author": "user***",
        "likes": 4,
        "dislikes": 0,
    }
    assert crawler._normalize_naver_comment({"contents": ""}) is None
    flattened = crawler._flatten_sbs_comments(
        [{"CONTENT": "부모", "replyList": [{"CONTENT": "답글"}]}]
    )
    assert [item["CONTENT"] for item in flattened] == ["부모", "답글"]


def test_fetch_naver_comments_parses_json_and_jsonp(monkeypatch):
    crawler = CommentCrawler(SimpleNamespace())
    payload = {"result": {"commentList": [{"contents": "댓글"}]}}
    responses = iter(
        [
            FakeResponse(payload, text=json.dumps(payload)),
            FakeResponse(payload, text=f"callback({json.dumps(payload)});"),
        ]
    )

    def fake_get(_url, **_kwargs):
        return next(responses)

    monkeypatch.setattr(network_security.requests, "get", fake_get)

    assert (
        crawler._fetch_comments("001", "12345678") == payload["result"]["commentList"]
    )
    assert (
        crawler._fetch_comments("001", "12345678") == payload["result"]["commentList"]
    )


def test_fetch_comment_apis_return_empty_results_on_http_errors(monkeypatch):
    crawler = CommentCrawler(SimpleNamespace())

    def fake_get(_url, **_kwargs):
        return FakeResponse({}, status_code=500)

    monkeypatch.setattr(network_security.requests, "get", fake_get)

    assert crawler._fetch_comments("001", "12345678") == []
    assert (
        crawler._fetch_sbs_comments(
            {"article_id": "N1008597091", "category": "NA", "news_type": "N"}
        )
        == []
    )


def test_fetch_sbs_comments_paginates_until_total_count(monkeypatch):
    crawler = CommentCrawler(SimpleNamespace())
    crawler.SBS_PAGE_SIZE = 2
    calls = []

    def fake_get(url, params, headers, timeout, allow_redirects):
        calls.append((url, params.copy(), headers, timeout, allow_redirects))
        if params["offset"] == 1:
            return FakeResponse(
                [
                    {"CONTENT": "첫 댓글", "STATUS": "V1", "TOTAL_COMMENT_COUNT": 3},
                    {"CONTENT": "둘째 댓글", "STATUS": "V1", "TOTAL_COMMENT_COUNT": 3},
                ]
            )
        return FakeResponse(
            [{"CONTENT": "셋째 댓글", "STATUS": "V1", "TOTAL_COMMENT_COUNT": 3}]
        )

    monkeypatch.setattr(network_security.requests, "get", fake_get)

    comments = crawler._fetch_sbs_comments(
        {
            "article_id": "N1008597091",
            "category": "NA",
            "news_type": "N",
        }
    )

    assert [comment["CONTENT"] for comment in comments] == [
        "첫 댓글",
        "둘째 댓글",
        "셋째 댓글",
    ]
    assert [call[1]["offset"] for call in calls] == [1, 2]
    assert calls[0][0].endswith("/comment/N1008597091")
    assert calls[0][4] is False


def test_run_collects_sbs_comments_and_counts_unsupported_sources(monkeypatch):
    articles = [
        SimpleNamespace(
            id=1,
            url="https://news.sbs.co.kr/news/endPage.do?news_id=N1008597091",
        ),
        SimpleNamespace(
            id=2,
            url="https://news.jtbc.co.kr/article/article.aspx?news_id=NB12220953",
        ),
    ]
    db = FakeDb(articles)
    crawler = CommentCrawler(db)

    monkeypatch.setattr(
        crawler,
        "_fetch_sbs_comments",
        lambda _target: [
            {
                "CONTENT": "실제 SBS 댓글",
                "USER_NAME": "SBS이용자",
                "LIKE_CNT": 2,
                "DISLIKE_CNT": 0,
                "STATUS": "V1",
            }
        ],
    )

    result = crawler.run()

    assert result["collected_total"] == 1
    assert result["articles_processed"] == 1
    assert result["skipped_unsupported"] == 1
    assert result["provider_results"]["sbs"]["comments"] == 1
    assert result["provider_results"]["unsupported"]["articles"] == 1
    assert db.added[0].article_id == 1
    assert db.added[0].content == "실제 SBS 댓글"
    assert db.commits == 1


def test_run_skips_duplicate_naver_comments_and_rolls_back_commit_errors(monkeypatch):
    article = SimpleNamespace(
        id=3,
        url="https://n.news.naver.com/mnews/article/001/0015420978",
    )
    db = FakeDb(
        [article], existing_comments=[("기존 댓글", "user***")], fail_commit=True
    )
    crawler = CommentCrawler(db)
    monkeypatch.setattr(
        crawler,
        "_fetch_comments",
        lambda _oid, _aid: [
            {"contents": "기존 댓글", "maskedUserId": "user***"},
            {"contents": "새 댓글", "maskedUserId": "new***"},
        ],
    )

    result = crawler.run(article_id=3)

    assert result["duplicates"] == 1
    assert result["collected_total"] == 1
    assert result["errors"] == 1
    assert db.added[0].content == "새 댓글"
    assert db.rollbacks == 1
