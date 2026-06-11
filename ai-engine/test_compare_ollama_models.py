import math

from compare_ollama_models import (
    CaseResult,
    add_project_fit_scores,
    build_ollama_payload,
    extract_json_object,
    fetch_model_metadata,
    render_markdown,
    score_expected_ranges,
    validate_schema,
)


def test_extract_json_object_strips_thinking_and_code_fence():
    text = """<think>분석 과정은 출력하면 안 된다.</think>
```json
{
  "sentiment_score": 0.1,
  "bias_score": 0.2,
  "factuality_score": 0.8,
  "summary": "서울시는 정책 효과와 우려를 함께 설명했다. 기사 표현은 전반적으로 중립적이다."
}
```"""

    parsed = extract_json_object(text)

    assert parsed["sentiment_score"] == 0.1
    assert parsed["bias_score"] == 0.2
    assert parsed["factuality_score"] == 0.8
    assert parsed["summary"].startswith("서울시는")


def test_validate_schema_accepts_article_and_comment_shapes():
    article = {
        "sentiment_score": -0.1,
        "bias_score": 0.25,
        "factuality_score": 0.9,
        "summary": "기사 핵심 내용을 한국어로 충분히 요약한다.",
    }
    comment = {
        "avg_sentiment": -0.4,
        "positive_ratio": 0.1,
        "negative_ratio": 0.7,
        "neutral_ratio": 0.2,
        "public_opinion": "댓글 여론은 비판적인 흐름이 강하다.",
    }

    assert validate_schema(article, "article") is True
    assert validate_schema(comment, "comment") is True


def test_validate_schema_rejects_missing_or_wrong_numeric_types():
    parsed = {
        "sentiment_score": "negative",
        "bias_score": 0.25,
        "summary": "숫자 필드 타입이 맞지 않는 응답이다.",
    }

    assert validate_schema(parsed, "article") is False


def test_score_expected_ranges_counts_numeric_hits_only():
    parsed = {
        "sentiment_score": -0.2,
        "bias_score": 0.9,
        "factuality_score": "높음",
    }
    expected = {
        "sentiment_score": (-0.5, 0.0),
        "bias_score": (0.0, 0.5),
        "factuality_score": (0.7, 1.0),
    }

    assert score_expected_ranges(parsed, expected) == (1, 3)


def test_build_ollama_payload_disables_thinking_for_json_outputs():
    payload = build_ollama_payload("test-model", "JSON으로 답하세요.")

    assert payload["model"] == "test-model"
    assert payload["stream"] is False
    assert payload["think"] is False
    assert payload["options"]["temperature"] == 0
    assert payload["messages"][0]["role"] == "system"
    assert payload["messages"][1]["content"] == "JSON으로 답하세요."


def test_fetch_model_metadata_reads_size_and_parameter_details(monkeypatch):
    class FakeResponse:
        def raise_for_status(self):
            return None

        def json(self):
            return {
                "models": [
                    {
                        "name": "model-a",
                        "size": 1_500_000_000,
                        "details": {
                            "parameter_size": "4B",
                            "quantization_level": "Q4_K_M",
                        },
                    }
                ]
            }

    def fake_get(url, timeout):
        assert url == "http://ollama.test/api/tags"
        assert timeout == 10
        return FakeResponse()

    monkeypatch.setattr("compare_ollama_models.requests.get", fake_get)

    metadata = fetch_model_metadata("http://ollama.test")

    assert metadata["model-a"]["size_gb"] == 1.5
    assert metadata["model-a"]["parameter_size"] == "4B"
    assert metadata["model-a"]["quantization_level"] == "Q4_K_M"


def test_add_project_fit_scores_prefers_schema_range_korean_and_speed():
    summaries = [
        {
            "model": "slow-accurate",
            "schema_valid_rate": 1.0,
            "expected_range_rate": 1.0,
            "korean_summary_rate": 1.0,
            "avg_latency_s": 10.0,
            "avg_tokens_per_second": 10.0,
        },
        {
            "model": "fast-inaccurate",
            "schema_valid_rate": 0.25,
            "expected_range_rate": 0.25,
            "korean_summary_rate": 0.25,
            "avg_latency_s": 1.0,
            "avg_tokens_per_second": 100.0,
        },
    ]

    scored = add_project_fit_scores(summaries)

    accurate = next(row for row in scored if row["model"] == "slow-accurate")
    inaccurate = next(row for row in scored if row["model"] == "fast-inaccurate")
    assert accurate["project_fit_score"] > inaccurate["project_fit_score"]


def test_render_markdown_ranks_best_model_first():
    summaries = [
        {
            "model": "model-a",
            "schema_valid_rate": 1.0,
            "expected_range_rate": 1.0,
            "korean_summary_rate": 1.0,
            "avg_latency_s": 1.0,
            "avg_tokens_per_second": 50.0,
            "errors": 0,
            "project_fit_score": 100.0,
        },
        {
            "model": "model-b",
            "schema_valid_rate": 0.5,
            "expected_range_rate": 0.5,
            "korean_summary_rate": 0.5,
            "avg_latency_s": math.nan,
            "avg_tokens_per_second": None,
            "errors": 1,
            "project_fit_score": 40.0,
        },
    ]
    results = {
        summary["model"]: [
            CaseResult(
                case_id="case",
                case_type="article",
                ok=True,
                json_valid=True,
                schema_valid=True,
                range_hits=3,
                range_total=3,
                korean_valid=True,
                latency_s=1.0,
                tokens_per_second=50.0,
                error=None,
                parsed={},
                raw_response="{}",
            )
        ]
        for summary in summaries
    }

    markdown = render_markdown(summaries, results)

    assert "추천 모델: **model-a**" in markdown
    assert "| 1 | `model-a` |" in markdown
