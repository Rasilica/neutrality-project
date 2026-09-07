from types import SimpleNamespace

import pytest
from pydantic import ValidationError

from analysis_schemas import ArticleAnalysisPayload, CommentAnalysisPayload
from analyzer import GeminiAnalyzer
from comment_analyzer import CommentAnalyzer
from gpt_analyzer import GPTAnalyzer

VALID_ARTICLE_RESPONSE = {
    "sentiment_score": 0.1,
    "bias_score": 0.2,
    "factuality_score": 0.9,
    "summary": "검증된 기사 요약",
}


class RecordingDb:
    def __init__(self):
        self.added = []
        self.commits = 0
        self.rollbacks = 0

    def add(self, value):
        self.added.append(value)

    def commit(self):
        self.commits += 1

    def rollback(self):
        self.rollbacks += 1


class CommentDb(RecordingDb):
    def __init__(self, comments, total):
        super().__init__()
        self.comments = comments
        self.total = total

    def query(self, _target):
        return CommentQuery(self.comments, self.total)


class CommentQuery:
    def __init__(self, comments, total):
        self.comments = comments
        self.total = total

    def filter(self, *_expressions):
        return self

    def order_by(self, *_expressions):
        return self

    def limit(self, _value):
        return self

    def all(self):
        return self.comments

    def count(self):
        return self.total


class StaticQuery:
    def __init__(self, values):
        self.values = values

    def all(self):
        return self.values


class GeminiResponses:
    def __init__(self, texts):
        self.texts = iter(texts)
        self.calls = []

    def generate_content(self, **kwargs):
        self.calls.append(kwargs)
        return SimpleNamespace(text=next(self.texts))


def test_gemini_structured_response_retries_then_validates():
    responses = GeminiResponses(
        [
            '{"sentiment_score": 4}',
            '{"sentiment_score": 0.1, "bias_score": 0.2, "factuality_score": 0.9, "summary": "요약"}',
        ]
    )
    analyzer = GeminiAnalyzer.__new__(GeminiAnalyzer)
    analyzer.client = SimpleNamespace(models=responses)

    payload = analyzer._generate_and_validate("prompt", ArticleAnalysisPayload)

    assert payload.bias_score == 0.2
    assert len(responses.calls) == 2
    assert responses.calls[0]["config"].response_mime_type == "application/json"


def test_comment_gemini_structured_response_rejects_invalid_ratios_after_retry():
    invalid_response = (
        '{"avg_sentiment": 0, "positive_ratio": 0.8, "negative_ratio": 0.8, '
        '"neutral_ratio": 0.2, "public_opinion": "요약"}'
    )
    responses = GeminiResponses([invalid_response, invalid_response])
    analyzer = CommentAnalyzer.__new__(CommentAnalyzer)
    analyzer.client = SimpleNamespace(models=responses)

    with pytest.raises(ValidationError):
        analyzer._generate_and_validate("prompt", CommentAnalysisPayload)

    assert len(responses.calls) == 2


def test_gemini_run_persists_only_validated_payload():
    db = RecordingDb()
    article = SimpleNamespace(id=7, title="제목", content="본문")
    analyzer = GeminiAnalyzer.__new__(GeminiAnalyzer)
    analyzer.db = db
    analyzer.client = object()
    analyzer._query_eligible_articles = lambda: StaticQuery([article])
    analyzer._generate_and_validate = lambda _prompt, _schema: (
        ArticleAnalysisPayload.model_validate(VALID_ARTICLE_RESPONSE)
    )

    result = analyzer.run()

    assert result == {"status": "success", "analyzed_count": 1, "errors": 0}
    assert db.commits == 1
    assert db.added[0].bias_score == 0.2
    assert db.added[0].raw_response == VALID_ARTICLE_RESPONSE


def test_gpt_run_uses_parsed_structured_output():
    db = RecordingDb()
    article = SimpleNamespace(id=8, title="제목", content="본문")
    payload = ArticleAnalysisPayload.model_validate(VALID_ARTICLE_RESPONSE)
    parse_calls = []

    def parse(**kwargs):
        parse_calls.append(kwargs)
        return SimpleNamespace(output_parsed=payload)

    analyzer = GPTAnalyzer.__new__(GPTAnalyzer)
    analyzer.db = db
    analyzer.client = SimpleNamespace(responses=SimpleNamespace(parse=parse))
    analyzer.model_name = "gpt-4o-mini"
    analyzer._query_eligible_articles = lambda: StaticQuery([article])

    result = analyzer.run()

    assert result == {"status": "success", "analyzed_count": 1, "errors": 0}
    assert parse_calls[0]["text_format"] is ArticleAnalysisPayload
    assert db.added[0].summary == "검증된 기사 요약"


def test_gpt_run_does_not_persist_an_empty_structured_output():
    db = RecordingDb()
    article = SimpleNamespace(id=9, title="제목", content="본문")
    analyzer = GPTAnalyzer.__new__(GPTAnalyzer)
    analyzer.db = db
    analyzer.client = SimpleNamespace(
        responses=SimpleNamespace(
            parse=lambda **_kwargs: SimpleNamespace(output_parsed=None)
        )
    )
    analyzer.model_name = "gpt-4o-mini"
    analyzer._query_eligible_articles = lambda: StaticQuery([article])

    result = analyzer.run()

    assert result == {"status": "success", "analyzed_count": 0, "errors": 1}
    assert db.added == []


@pytest.mark.parametrize(
    "analyzer_type", [GeminiAnalyzer, GPTAnalyzer, CommentAnalyzer]
)
def test_analyzers_report_missing_provider_keys(monkeypatch, analyzer_type):
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)

    analyzer = analyzer_type(RecordingDb())
    result = analyzer.run()

    assert result["status"] == "error"
    assert "missing" in result["message"]


def test_gemini_run_returns_without_committing_when_no_articles_exist():
    db = RecordingDb()
    analyzer = GeminiAnalyzer.__new__(GeminiAnalyzer)
    analyzer.db = db
    analyzer.client = object()
    analyzer._query_eligible_articles = lambda: StaticQuery([])

    result = analyzer.run()

    assert result["analyzed_count"] == 0
    assert db.commits == 0


def test_comment_run_persists_validated_ratios():
    db = CommentDb([SimpleNamespace(content="댓글", likes=3)], total=4)
    article = SimpleNamespace(id=10, title="기사")
    payload = CommentAnalysisPayload.model_validate(
        {
            "avg_sentiment": -0.1,
            "positive_ratio": 0.25,
            "negative_ratio": 0.5,
            "neutral_ratio": 0.25,
            "public_opinion": "부정 의견이 우세합니다.",
        }
    )
    analyzer = CommentAnalyzer.__new__(CommentAnalyzer)
    analyzer.db = db
    analyzer.client = object()
    analyzer._query_eligible_articles = lambda: StaticQuery([article])
    analyzer._generate_and_validate = lambda _prompt, _schema: payload

    result = analyzer.run()

    assert result == {"status": "success", "analyzed_count": 1, "errors": 0}
    assert db.added[0].total_comments == 4
    assert db.added[0].negative_ratio == 0.5


def test_comment_run_counts_invalid_provider_output_as_an_error():
    db = CommentDb([SimpleNamespace(content="댓글", likes=3)], total=1)
    article = SimpleNamespace(id=11, title="기사")
    analyzer = CommentAnalyzer.__new__(CommentAnalyzer)
    analyzer.db = db
    analyzer.client = object()
    analyzer._query_eligible_articles = lambda: StaticQuery([article])
    analyzer._generate_and_validate = lambda _prompt, _schema: (_ for _ in ()).throw(
        ValidationError.from_exception_data("invalid", [])
    )

    result = analyzer.run()

    assert result["errors"] == 1
    assert db.added == []
