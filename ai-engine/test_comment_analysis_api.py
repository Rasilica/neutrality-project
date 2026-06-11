import asyncio
from types import SimpleNamespace

from main import get_comment_analysis
from models import Comment, CommentAnalysis


class FakeQuery:
    def __init__(self, rows=None, first_value=None):
        self.rows = rows or []
        self.first_value = first_value

    def filter(self, *_args, **_kwargs):
        return self

    def order_by(self, *_args, **_kwargs):
        return self

    def limit(self, *_args, **_kwargs):
        return self

    def first(self):
        return self.first_value

    def all(self):
        return self.rows


class FakeDb:
    def __init__(self, comments, analysis=None):
        self.comments = comments
        self.analysis = analysis

    def query(self, target):
        if target is CommentAnalysis:
            return FakeQuery(first_value=self.analysis)
        if target is Comment:
            return FakeQuery(rows=self.comments)
        raise AssertionError(f"unexpected query target: {target}")


def test_get_comment_analysis_returns_raw_comments_without_analysis():
    db = FakeDb(
        comments=[
            SimpleNamespace(content="실제 SBS 댓글", author="SBS이용자", likes=2, dislikes=0)
        ]
    )

    response = asyncio.run(get_comment_analysis(117, db))

    assert response["status"] == "success"
    assert response["data"]["article_id"] == 117
    assert response["data"]["analysis_status"] == "pending"
    assert response["data"]["total_comments"] == 1
    assert response["data"]["avg_sentiment"] is None
    assert response["data"]["top_comments"][0]["content"] == "실제 SBS 댓글"
