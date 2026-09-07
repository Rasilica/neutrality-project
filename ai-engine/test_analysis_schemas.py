import math

import pytest
from pydantic import ValidationError

from analysis_schemas import ArticleAnalysisPayload, CommentAnalysisPayload


def test_article_analysis_payload_accepts_valid_bounded_scores():
    payload = ArticleAnalysisPayload.model_validate(
        {
            "sentiment_score": -0.25,
            "bias_score": 0.4,
            "factuality_score": 0.9,
            "summary": "핵심 내용을 요약했습니다.",
        }
    )

    assert payload.model_dump()["factuality_score"] == 0.9


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("sentiment_score", -1.01),
        ("sentiment_score", 1.01),
        ("bias_score", -0.01),
        ("bias_score", 1.01),
        ("factuality_score", -0.01),
        ("factuality_score", 1.01),
    ],
)
def test_article_analysis_payload_rejects_out_of_range_scores(field, value):
    data = {
        "sentiment_score": 0.0,
        "bias_score": 0.5,
        "factuality_score": 0.5,
        "summary": "요약",
    }
    data[field] = value

    with pytest.raises(ValidationError):
        ArticleAnalysisPayload.model_validate(data)


def test_article_analysis_payload_rejects_non_finite_scores_and_extra_fields():
    with pytest.raises(ValidationError):
        ArticleAnalysisPayload.model_validate(
            {
                "sentiment_score": math.nan,
                "bias_score": 0.5,
                "factuality_score": 0.5,
                "summary": "요약",
                "unexpected": "value",
            }
        )


def test_comment_analysis_payload_accepts_ratios_that_sum_to_one():
    payload = CommentAnalysisPayload.model_validate(
        {
            "avg_sentiment": 0.1,
            "positive_ratio": 0.45,
            "negative_ratio": 0.3,
            "neutral_ratio": 0.25,
            "public_opinion": "전반적으로 의견이 엇갈립니다.",
        }
    )

    assert payload.positive_ratio == 0.45


def test_comment_analysis_payload_rejects_ratios_that_do_not_sum_to_one():
    with pytest.raises(ValidationError):
        CommentAnalysisPayload.model_validate(
            {
                "avg_sentiment": 0.1,
                "positive_ratio": 0.7,
                "negative_ratio": 0.3,
                "neutral_ratio": 0.2,
                "public_opinion": "요약",
            }
        )
