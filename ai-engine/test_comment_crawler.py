from types import SimpleNamespace

import comment_crawler as comment_crawler_module
from comment_crawler import CommentCrawler
from models import Article, Comment


class FakeResponse:
    def __init__(self, payload, status_code=200):
        self.payload = payload
        self.status_code = status_code
        self.text = str(payload)
        self.headers = {"content-type": "application/json"}

    def raise_for_status(self):
        if self.status_code >= 400:
            raise comment_crawler_module.requests.HTTPError(f"HTTP {self.status_code}")

    def json(self):
        return self.payload


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
    def filter(self, *_args, **_kwargs):
        return self

    def all(self):
        return []


class FakeDb:
    def __init__(self, articles):
        self.articles = articles
        self.added = []
        self.commits = 0
        self.rollbacks = 0

    def query(self, *targets):
        if targets and targets[0] is Article:
            return FakeArticleQuery(self.articles)
        return FakeCommentQuery()

    def add(self, item):
        self.added.append(item)

    def commit(self):
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
    assert crawler._normalize_sbs_comment({"CONTENT": "작성자가 삭제한 댓글입니다.", "STATUS": "D1"}) is None


def test_fetch_sbs_comments_paginates_until_total_count(monkeypatch):
    crawler = CommentCrawler(SimpleNamespace())
    crawler.SBS_PAGE_SIZE = 2
    calls = []

    def fake_get(url, params, headers, timeout):
        calls.append((url, params.copy(), headers, timeout))
        if params["offset"] == 1:
            return FakeResponse(
                [
                    {"CONTENT": "첫 댓글", "STATUS": "V1", "TOTAL_COMMENT_COUNT": 3},
                    {"CONTENT": "둘째 댓글", "STATUS": "V1", "TOTAL_COMMENT_COUNT": 3},
                ]
            )
        return FakeResponse([{"CONTENT": "셋째 댓글", "STATUS": "V1", "TOTAL_COMMENT_COUNT": 3}])

    monkeypatch.setattr(comment_crawler_module.requests, "get", fake_get)

    comments = crawler._fetch_sbs_comments(
        {
            "article_id": "N1008597091",
            "category": "NA",
            "news_type": "N",
        }
    )

    assert [comment["CONTENT"] for comment in comments] == ["첫 댓글", "둘째 댓글", "셋째 댓글"]
    assert [call[1]["offset"] for call in calls] == [1, 2]
    assert calls[0][0].endswith("/comment/N1008597091")


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
