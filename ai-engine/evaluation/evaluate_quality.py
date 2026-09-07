import argparse
import json
import math
from pathlib import Path

SCORE_KEYS = ("sentiment_score", "bias_score", "factuality_score")
SCORE_RANGES = {
    "sentiment_score": (-1.0, 1.0),
    "bias_score": (0.0, 1.0),
    "factuality_score": (0.0, 1.0),
}


def load_records(path: str | Path) -> list[dict]:
    records = []
    seen_ids = set()
    for line_number, line in enumerate(
        Path(path).read_text(encoding="utf-8").splitlines(), 1
    ):
        if not line.strip():
            continue
        try:
            record = json.loads(line)
        except json.JSONDecodeError as exc:
            raise ValueError(f"Invalid JSON on line {line_number}.") from exc
        if not isinstance(record, dict) or not record.get("id"):
            raise ValueError(f"Evaluation record on line {line_number} needs an id.")
        record_id = str(record["id"])
        if record_id in seen_ids:
            raise ValueError(f"Duplicate evaluation id: {record_id}")
        gold = record.get("gold")
        if not isinstance(gold, dict):
            raise ValueError(f"Evaluation record {record_id} needs a gold object.")
        _validate_scores(gold, record_id)
        seen_ids.add(record_id)
        records.append({**record, "id": record_id})
    if not records:
        raise ValueError("Evaluation dataset is empty.")
    return records


def evaluate_predictions(records: list[dict], predictions: list[dict]) -> dict:
    predictions_by_id = {str(item.get("id")): item for item in predictions}
    missing = [
        str(record["id"])
        for record in records
        if str(record["id"]) not in predictions_by_id
    ]
    if missing:
        raise ValueError(f"Missing predictions for: {', '.join(missing)}")

    errors = {key: [] for key in SCORE_KEYS}
    for record in records:
        prediction = predictions_by_id[str(record["id"])]
        _validate_scores(prediction, record["id"])
        for key in SCORE_KEYS:
            errors[key].append(abs(float(prediction[key]) - float(record["gold"][key])))

    return {
        "count": len(records),
        "mae": {
            key: round(sum(values) / len(values), 6) for key, values in errors.items()
        },
    }


def load_predictions(path: str | Path) -> list[dict]:
    predictions = []
    seen_ids = set()
    for line_number, line in enumerate(
        Path(path).read_text(encoding="utf-8").splitlines(), 1
    ):
        if not line.strip():
            continue
        try:
            prediction = json.loads(line)
        except json.JSONDecodeError as exc:
            raise ValueError(f"Invalid JSON on line {line_number}.") from exc
        if not isinstance(prediction, dict) or not prediction.get("id"):
            raise ValueError(f"Prediction on line {line_number} needs an id.")
        prediction_id = str(prediction["id"])
        if prediction_id in seen_ids:
            raise ValueError(f"Duplicate prediction id: {prediction_id}")
        _validate_scores(prediction, prediction_id)
        seen_ids.add(prediction_id)
        predictions.append({**prediction, "id": prediction_id})
    return predictions


def _validate_scores(scores: dict, record_id: str):
    for key in SCORE_KEYS:
        value = scores.get(key)
        if (
            not isinstance(value, (int, float))
            or isinstance(value, bool)
            or not math.isfinite(value)
        ):
            raise ValueError(f"{record_id} has an invalid {key}.")
        lower, upper = SCORE_RANGES[key]
        if not lower <= value <= upper:
            raise ValueError(f"{record_id} has an invalid {key} range.")


def main():
    parser = argparse.ArgumentParser(
        description="Evaluate neutrality model predictions."
    )
    parser.add_argument("dataset", type=Path)
    parser.add_argument("predictions", type=Path)
    args = parser.parse_args()
    records = load_records(args.dataset)
    predictions = load_predictions(args.predictions)
    print(
        json.dumps(
            evaluate_predictions(records, predictions), ensure_ascii=False, indent=2
        )
    )


if __name__ == "__main__":
    main()
