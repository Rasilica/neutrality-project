import json

import pytest

from evaluation.evaluate_quality import (
    evaluate_predictions,
    load_predictions,
    load_records,
)


def test_load_records_validates_score_ranges(tmp_path):
    path = tmp_path / "eval.jsonl"
    path.write_text(
        json.dumps(
            {
                "id": "case-1",
                "title": "제목",
                "content": "본문",
                "gold": {
                    "sentiment_score": 0.1,
                    "bias_score": 0.2,
                    "factuality_score": 0.9,
                },
            }
        )
        + "\n",
        encoding="utf-8",
    )

    assert load_records(path)[0]["id"] == "case-1"

    path.write_text(
        '{"id":"bad","gold":{"sentiment_score":0,"bias_score":2,"factuality_score":1}}\n',
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="bias_score"):
        load_records(path)


def test_evaluate_predictions_reports_mae_and_perfect_match():
    records = [
        {
            "id": "case-1",
            "gold": {
                "sentiment_score": 0.0,
                "bias_score": 0.2,
                "factuality_score": 0.8,
            },
        },
        {
            "id": "case-2",
            "gold": {
                "sentiment_score": -0.5,
                "bias_score": 0.6,
                "factuality_score": 0.4,
            },
        },
    ]
    predictions = [
        {"id": "case-1", **records[0]["gold"]},
        {"id": "case-2", **records[1]["gold"]},
    ]

    report = evaluate_predictions(records, predictions)

    assert report["count"] == 2
    assert report["mae"] == {
        "sentiment_score": 0.0,
        "bias_score": 0.0,
        "factuality_score": 0.0,
    }


def test_evaluate_predictions_rejects_missing_prediction():
    records = [
        {
            "id": "case-1",
            "gold": {"sentiment_score": 0, "bias_score": 0, "factuality_score": 1},
        }
    ]

    with pytest.raises(ValueError, match="case-1"):
        evaluate_predictions(records, [])


def test_load_predictions_accepts_score_only_jsonl(tmp_path):
    path = tmp_path / "predictions.jsonl"
    path.write_text(
        '{"id":"case-1","sentiment_score":0,"bias_score":0.2,"factuality_score":1}\n',
        encoding="utf-8",
    )

    assert load_predictions(path)[0]["id"] == "case-1"
