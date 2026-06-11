from analyzer import GeminiAnalyzer
from comment_analyzer import CommentAnalyzer
from gpt_analyzer import GPTAnalyzer
from models import AnalysisResult, Article, Comment


class RecordingQuery:
    def __init__(self):
        self.joins = []
        self.outerjoins = []
        self.filters = []
        self.distinct_called = False
        self.limit_value = None

    def join(self, *args):
        self.joins.append(args)
        return self

    def outerjoin(self, *args):
        self.outerjoins.append(args)
        return self

    def filter(self, *expressions):
        self.filters.extend(expressions)
        return self

    def distinct(self):
        self.distinct_called = True
        return self

    def limit(self, value):
        self.limit_value = value
        return self


class FakeDb:
    def __init__(self):
        self.query_obj = RecordingQuery()

    def query(self, target):
        assert target is Article
        return self.query_obj


def filter_contains_like_value(filters, expected):
    return any(getattr(getattr(expression, "right", None), "value", None) == expected for expression in filters)


def first_join_targets(query):
    return [join_args[0] for join_args in query.joins]


def test_gemini_article_analysis_scope_requires_sbs_article_with_comments():
    db = FakeDb()
    analyzer = GeminiAnalyzer.__new__(GeminiAnalyzer)
    analyzer.db = db

    query = analyzer._query_eligible_articles()

    assert Comment in first_join_targets(query)
    assert filter_contains_like_value(query.filters, "%news.sbs.co.kr%")
    assert query.outerjoins[0][0] is AnalysisResult
    assert query.distinct_called is True
    assert query.limit_value == 10


def test_gpt_article_analysis_scope_requires_sbs_article_with_comments():
    db = FakeDb()
    analyzer = GPTAnalyzer.__new__(GPTAnalyzer)
    analyzer.db = db
    analyzer.model_name = "gpt-4o-mini"

    query = analyzer._query_eligible_articles()

    assert Comment in first_join_targets(query)
    assert filter_contains_like_value(query.filters, "%news.sbs.co.kr%")
    assert query.outerjoins[0][0] is AnalysisResult
    assert query.distinct_called is True
    assert query.limit_value == 10


def test_comment_analysis_scope_requires_sbs_article_comments_and_article_analysis():
    db = FakeDb()
    analyzer = CommentAnalyzer.__new__(CommentAnalyzer)
    analyzer.db = db

    query = analyzer._query_eligible_articles()

    join_targets = first_join_targets(query)
    assert Comment in join_targets
    assert AnalysisResult in join_targets
    assert filter_contains_like_value(query.filters, "%news.sbs.co.kr%")
    assert query.distinct_called is True
    assert query.limit_value == 5
