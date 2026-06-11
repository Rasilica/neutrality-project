import argparse
import json
import math
import os
import statistics
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import requests


DEFAULT_MODELS = [
    "qwen3.5:4b",
    "cookieshake/a.x-4.0-light-imatrix:q4_k_m",
    "gemma4:e4b",
]

DEFAULT_OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://127.0.0.1:11434")
PROJECT_ROOT = Path(__file__).resolve().parents[1]
RAW_OUTPUT_PATH = PROJECT_ROOT / "ai-engine" / "outputs" / "ollama_model_comparison.json"
MARKDOWN_OUTPUT_PATH = PROJECT_ROOT / "docs" / "ollama_model_comparison.md"


SYSTEM_PROMPT = """당신은 한국어 뉴스 중립성 분석 모델입니다.
반드시 사용자가 요구한 JSON 객체 하나만 출력하세요.
마크다운, 코드블록, 설명 문장, XML 태그를 출력하지 마세요.
모든 설명 필드는 한국어로 작성하세요."""


BENCHMARK_CASES = [
    {
        "id": "article_policy_neutral",
        "type": "article",
        "title": "교통 혼잡 완화를 위한 버스 전용 차로 확대 검토",
        "content": (
            "서울시는 출퇴근 시간대 주요 간선도로의 교통 혼잡을 줄이기 위해 버스 전용 차로를 "
            "확대하는 방안을 검토하고 있다. 시는 통행 속도 개선 효과와 승용차 이용자의 불편을 "
            "함께 분석하겠다고 밝혔다. 시민단체는 대중교통 이용 확대를 기대했고, 일부 상인은 "
            "상권 접근성 저하를 우려했다."
        ),
        "expected_ranges": {
            "sentiment_score": (-0.25, 0.25),
            "bias_score": (0.0, 0.45),
            "factuality_score": (0.65, 1.0),
        },
    },
    {
        "id": "article_political_conflict",
        "type": "article",
        "title": "여야, 선거 제도 개편 두고 정면 충돌",
        "content": (
            "국회 정치개혁특위에서 여야가 선거 제도 개편안을 두고 강하게 맞섰다. 여당은 "
            "대표성 강화를 이유로 개편 필요성을 강조했고, 야당은 특정 정당에 유리한 설계라며 "
            "반발했다. 회의에서는 고성이 오갔고 다음 회의 일정도 확정하지 못했다."
        ),
        "expected_ranges": {
            "sentiment_score": (-0.75, -0.15),
            "bias_score": (0.35, 0.85),
            "factuality_score": (0.45, 0.9),
        },
    },
    {
        "id": "article_public_safety",
        "type": "article",
        "title": "노후 교량 정밀 점검 결과 공개",
        "content": (
            "국토부는 전국 노후 교량 120곳을 대상으로 정밀 안전 점검을 실시한 결과 9곳에서 "
            "보수 보강이 필요한 것으로 나타났다고 발표했다. 정부는 위험도가 높은 시설부터 "
            "예산을 우선 배정하고, 점검 결과를 지자체와 공유하겠다고 밝혔다."
        ),
        "expected_ranges": {
            "sentiment_score": (-0.35, 0.25),
            "bias_score": (0.0, 0.35),
            "factuality_score": (0.75, 1.0),
        },
    },
    {
        "id": "comment_negative_opinion",
        "type": "comment",
        "title": "정치권 인사, 책임론 속 사퇴 요구 직면",
        "comments": [
            "이번에는 책임지는 모습을 보여야 한다.",
            "말만 강하게 하지 말고 결과를 설명해야 한다.",
            "당장 사퇴하라는 여론이 커지는 이유를 봐야 한다.",
            "절차를 지켜서 판단해야지 감정적으로 몰아가면 안 된다.",
        ],
        "expected_ranges": {
            "avg_sentiment": (-0.85, -0.15),
            "positive_ratio": (0.0, 0.30),
            "negative_ratio": (0.35, 1.0),
            "neutral_ratio": (0.0, 0.50),
        },
    },
]


@dataclass
class CaseResult:
    case_id: str
    case_type: str
    ok: bool
    json_valid: bool
    schema_valid: bool
    range_hits: int
    range_total: int
    korean_valid: bool
    latency_s: float
    tokens_per_second: float | None
    error: str | None
    parsed: dict[str, Any] | None
    raw_response: str


def build_prompt(case: dict[str, Any]) -> str:
    if case["type"] == "article":
        return f"""다음 뉴스 기사를 분석하세요.

[기사 제목]
{case["title"]}

[기사 본문]
{case["content"]}

아래 JSON 스키마로만 답하세요.
{{
  "sentiment_score": -1.0,
  "bias_score": 0.0,
  "factuality_score": 1.0,
  "summary": "기사 핵심 내용과 중립성 판단 근거를 2문장으로 요약"
}}"""

    comments = "\n".join(f"- {comment}" for comment in case["comments"])
    return f"""다음 뉴스 댓글 여론을 분석하세요.

[기사 제목]
{case["title"]}

[댓글 목록]
{comments}

아래 JSON 스키마로만 답하세요.
{{
  "avg_sentiment": -1.0,
  "positive_ratio": 0.0,
  "negative_ratio": 1.0,
  "neutral_ratio": 0.0,
  "public_opinion": "댓글 여론의 핵심 흐름을 2문장으로 요약"
}}"""


def extract_json_object(text: str) -> dict[str, Any]:
    cleaned = text.strip()
    cleaned = cleaned.replace("```json", "").replace("```", "").strip()
    while "<think>" in cleaned and "</think>" in cleaned:
        before, _, rest = cleaned.partition("<think>")
        _, _, after = rest.partition("</think>")
        cleaned = (before + after).strip()

    start = cleaned.find("{")
    end = cleaned.rfind("}")
    if start < 0 or end < start:
        raise ValueError("JSON object not found")
    return json.loads(cleaned[start : end + 1])


def is_korean_text(value: Any) -> bool:
    text = str(value or "").strip()
    hangul_count = sum(1 for char in text if "가" <= char <= "힣")
    return len(text) >= 20 and hangul_count >= 8


def expected_schema(case_type: str) -> list[str]:
    if case_type == "article":
        return ["sentiment_score", "bias_score", "factuality_score", "summary"]
    return ["avg_sentiment", "positive_ratio", "negative_ratio", "neutral_ratio", "public_opinion"]


def validate_schema(parsed: dict[str, Any], case_type: str) -> bool:
    keys = expected_schema(case_type)
    if not all(key in parsed for key in keys):
        return False
    text_key = "summary" if case_type == "article" else "public_opinion"
    numeric_keys = [key for key in keys if key != text_key]
    return all(isinstance(parsed.get(key), (int, float)) for key in numeric_keys) and isinstance(parsed.get(text_key), str)


def score_expected_ranges(parsed: dict[str, Any] | None, expected_ranges: dict[str, tuple[float, float]]) -> tuple[int, int]:
    if not parsed:
        return 0, len(expected_ranges)
    hits = 0
    for key, (lower, upper) in expected_ranges.items():
        value = parsed.get(key)
        if isinstance(value, (int, float)) and lower <= float(value) <= upper:
            hits += 1
    return hits, len(expected_ranges)


def build_ollama_payload(model: str, prompt: str) -> dict[str, Any]:
    return {
        "model": model,
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": prompt},
        ],
        "stream": False,
        "think": False,
        "options": {
            "temperature": 0,
            "top_p": 0.9,
            "num_predict": 320,
            "seed": 42,
        },
    }


def call_ollama(base_url: str, model: str, prompt: str, timeout: int) -> tuple[str, dict[str, Any], float]:
    started = time.perf_counter()
    response = requests.post(
        f"{base_url.rstrip('/')}/api/chat",
        json=build_ollama_payload(model, prompt),
        timeout=timeout,
    )
    latency = time.perf_counter() - started
    response.raise_for_status()
    payload = response.json()
    return payload.get("message", {}).get("content", ""), payload, latency


def evaluate_case(base_url: str, model: str, case: dict[str, Any], timeout: int) -> CaseResult:
    prompt = build_prompt(case)
    try:
        raw_response, payload, latency = call_ollama(base_url, model, prompt, timeout)
        try:
            parsed = extract_json_object(raw_response)
            json_valid = True
        except Exception as exc:
            parsed = None
            json_valid = False
            schema_valid = False
            range_hits, range_total = score_expected_ranges(None, case["expected_ranges"])
            return CaseResult(
                case_id=case["id"],
                case_type=case["type"],
                ok=False,
                json_valid=False,
                schema_valid=schema_valid,
                range_hits=range_hits,
                range_total=range_total,
                korean_valid=False,
                latency_s=latency,
                tokens_per_second=extract_tokens_per_second(payload),
                error=str(exc),
                parsed=None,
                raw_response=raw_response,
            )

        schema_valid = validate_schema(parsed, case["type"])
        range_hits, range_total = score_expected_ranges(parsed, case["expected_ranges"])
        text_key = "summary" if case["type"] == "article" else "public_opinion"
        korean_valid = is_korean_text(parsed.get(text_key))
        return CaseResult(
            case_id=case["id"],
            case_type=case["type"],
            ok=json_valid and schema_valid,
            json_valid=json_valid,
            schema_valid=schema_valid,
            range_hits=range_hits,
            range_total=range_total,
            korean_valid=korean_valid,
            latency_s=latency,
            tokens_per_second=extract_tokens_per_second(payload),
            error=None,
            parsed=parsed,
            raw_response=raw_response,
        )
    except Exception as exc:
        return CaseResult(
            case_id=case["id"],
            case_type=case["type"],
            ok=False,
            json_valid=False,
            schema_valid=False,
            range_hits=0,
            range_total=len(case["expected_ranges"]),
            korean_valid=False,
            latency_s=math.nan,
            tokens_per_second=None,
            error=str(exc),
            parsed=None,
            raw_response="",
        )


def extract_tokens_per_second(payload: dict[str, Any]) -> float | None:
    eval_count = payload.get("eval_count")
    eval_duration = payload.get("eval_duration")
    if not eval_count or not eval_duration:
        return None
    seconds = float(eval_duration) / 1_000_000_000
    if seconds <= 0:
        return None
    return float(eval_count) / seconds


def fetch_model_metadata(base_url: str, timeout: int = 10) -> dict[str, dict[str, Any]]:
    try:
        response = requests.get(f"{base_url.rstrip('/')}/api/tags", timeout=timeout)
        response.raise_for_status()
        payload = response.json()
    except Exception:
        return {}

    metadata = {}
    for model in payload.get("models", []):
        details = model.get("details", {})
        size = model.get("size")
        metadata[model.get("name") or model.get("model")] = {
            "size_gb": float(size) / 1_000_000_000 if isinstance(size, (int, float)) else None,
            "parameter_size": details.get("parameter_size"),
            "quantization_level": details.get("quantization_level"),
        }
    return metadata


def summarize_model(model: str, results: list[CaseResult]) -> dict[str, Any]:
    total = len(results)
    range_hits = sum(result.range_hits for result in results)
    range_total = sum(result.range_total for result in results)
    latencies = [result.latency_s for result in results if not math.isnan(result.latency_s)]
    speeds = [result.tokens_per_second for result in results if result.tokens_per_second is not None]
    return {
        "model": model,
        "cases": total,
        "json_valid_rate": sum(result.json_valid for result in results) / total,
        "schema_valid_rate": sum(result.schema_valid for result in results) / total,
        "expected_range_rate": range_hits / range_total if range_total else 0.0,
        "korean_summary_rate": sum(result.korean_valid for result in results) / total,
        "avg_latency_s": statistics.mean(latencies) if latencies else math.nan,
        "avg_tokens_per_second": statistics.mean(speeds) if speeds else None,
        "errors": sum(1 for result in results if result.error),
    }


def add_project_fit_scores(summaries: list[dict[str, Any]]) -> list[dict[str, Any]]:
    best_speed = max((summary["avg_tokens_per_second"] or 0 for summary in summaries), default=0)
    finite_latencies = [summary["avg_latency_s"] for summary in summaries if not math.isnan(summary["avg_latency_s"])]
    best_latency = min(finite_latencies) if finite_latencies else math.nan

    for summary in summaries:
        speed_score = ((summary["avg_tokens_per_second"] or 0) / best_speed * 100) if best_speed else 0
        latency_score = (best_latency / summary["avg_latency_s"] * 100) if finite_latencies and summary["avg_latency_s"] else 0
        summary["speed_score"] = speed_score
        summary["latency_score"] = latency_score
        summary["project_fit_score"] = (
            summary["schema_valid_rate"] * 100 * 0.30
            + summary["expected_range_rate"] * 100 * 0.30
            + summary["korean_summary_rate"] * 100 * 0.20
            + speed_score * 0.10
            + latency_score * 0.10
        )
    return summaries


def format_percent(value: float) -> str:
    return f"{value * 100:.0f}%"


def format_float(value: float | None, digits: int = 2) -> str:
    if value is None or (isinstance(value, float) and math.isnan(value)):
        return "-"
    return f"{value:.{digits}f}"


def render_markdown(summaries: list[dict[str, Any]], all_results: dict[str, list[CaseResult]]) -> str:
    ranked = sorted(summaries, key=lambda row: row["project_fit_score"], reverse=True)
    best = ranked[0]["model"] if ranked else "-"
    lines = [
        "# Ollama 로컬 모델 비교 결과",
        "",
        "비교 목적: 한국어 뉴스 중립성 분석 및 댓글 여론 분석 파인튜닝 후보 모델 선정",
        "",
        f"추천 모델: **{best}**",
        "",
        "| 순위 | 모델 | 크기(GB) | 파라미터 | 프로젝트 적합도 | JSON/스키마 | 예상 점수 범위 적중 | 한국어 요약 | 평균 지연(s) | 평균 tok/s | 오류 |",
        "|---:|---|---:|---|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for index, summary in enumerate(ranked, start=1):
        lines.append(
            "| {rank} | `{model}` | {size_gb} | {parameter_size} | {fit} | {schema} | {range_rate} | {korean} | {latency} | {speed} | {errors} |".format(
                rank=index,
                model=summary["model"],
                size_gb=format_float(summary.get("size_gb"), 1),
                parameter_size=summary.get("parameter_size") or "-",
                fit=f'{summary["project_fit_score"]:.1f}',
                schema=format_percent(summary["schema_valid_rate"]),
                range_rate=format_percent(summary["expected_range_rate"]),
                korean=format_percent(summary["korean_summary_rate"]),
                latency=format_float(summary["avg_latency_s"]),
                speed=format_float(summary["avg_tokens_per_second"]),
                errors=summary["errors"],
            )
        )

    lines.extend(
        [
            "",
            "## 평가 기준",
            "",
            "- JSON/스키마: 프로젝트 API에 바로 저장 가능한 JSON 필드와 타입을 지키는지 평가",
            "- 예상 점수 범위 적중: 사람이 정한 합리적 점수 범위에 numeric score가 들어오는지 평가",
            "- 한국어 요약: `summary` 또는 `public_opinion`이 충분한 한국어 문장인지 평가",
            "- 프로젝트 적합도: 스키마 30%, 점수 적중 30%, 한국어 20%, 속도 10%, 지연시간 10%",
            "",
            "## 케이스별 결과",
            "",
        ]
    )

    for summary in ranked:
        model = summary["model"]
        lines.append(f"### {model}")
        lines.append("")
        lines.append("| 케이스 | JSON | 스키마 | 점수 범위 | 한국어 | 지연(s) | tok/s | 오류 |")
        lines.append("|---|---:|---:|---:|---:|---:|---:|---|")
        for result in all_results[model]:
            lines.append(
                "| {case} | {json_valid} | {schema} | {ranges} | {korean} | {latency} | {speed} | {error} |".format(
                    case=result.case_id,
                    json_valid="Y" if result.json_valid else "N",
                    schema="Y" if result.schema_valid else "N",
                    ranges=f"{result.range_hits}/{result.range_total}",
                    korean="Y" if result.korean_valid else "N",
                    latency=format_float(result.latency_s),
                    speed=format_float(result.tokens_per_second),
                    error=(result.error or "").replace("|", "/")[:80],
                )
            )
        lines.append("")

    return "\n".join(lines)


def serialize_results(summaries: list[dict[str, Any]], all_results: dict[str, list[CaseResult]]) -> dict[str, Any]:
    return {
        "summaries": summaries,
        "cases": BENCHMARK_CASES,
        "results": {
            model: [
                {
                    "case_id": result.case_id,
                    "case_type": result.case_type,
                    "ok": result.ok,
                    "json_valid": result.json_valid,
                    "schema_valid": result.schema_valid,
                    "range_hits": result.range_hits,
                    "range_total": result.range_total,
                    "korean_valid": result.korean_valid,
                    "latency_s": result.latency_s,
                    "tokens_per_second": result.tokens_per_second,
                    "error": result.error,
                    "parsed": result.parsed,
                    "raw_response": result.raw_response,
                }
                for result in results
            ]
            for model, results in all_results.items()
        },
    }


def run_comparison(models: list[str], base_url: str, timeout: int) -> tuple[list[dict[str, Any]], dict[str, list[CaseResult]]]:
    all_results: dict[str, list[CaseResult]] = {}
    summaries: list[dict[str, Any]] = []
    model_metadata = fetch_model_metadata(base_url)
    for model in models:
        model_results = []
        for case in BENCHMARK_CASES:
            print(f"[compare] model={model} case={case['id']}", flush=True)
            model_results.append(evaluate_case(base_url, model, case, timeout))
        all_results[model] = model_results
        summary = summarize_model(model, model_results)
        summary.update(model_metadata.get(model, {}))
        summaries.append(summary)
    return add_project_fit_scores(summaries), all_results


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Compare local Ollama models for the Korean news analysis project.")
    parser.add_argument("--models", nargs="+", default=DEFAULT_MODELS)
    parser.add_argument("--ollama-base-url", default=DEFAULT_OLLAMA_BASE_URL)
    parser.add_argument("--timeout", type=int, default=240)
    parser.add_argument("--raw-output", default=str(RAW_OUTPUT_PATH))
    parser.add_argument("--markdown-output", default=str(MARKDOWN_OUTPUT_PATH))
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    summaries, all_results = run_comparison(args.models, args.ollama_base_url, args.timeout)

    raw_output_path = Path(args.raw_output)
    raw_output_path.parent.mkdir(parents=True, exist_ok=True)
    raw_output_path.write_text(
        json.dumps(serialize_results(summaries, all_results), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    markdown_output_path = Path(args.markdown_output)
    markdown_output_path.parent.mkdir(parents=True, exist_ok=True)
    markdown = render_markdown(summaries, all_results)
    markdown_output_path.write_text(markdown, encoding="utf-8")
    print(markdown)
    print(f"\n[written] {markdown_output_path}")
    print(f"[written] {raw_output_path}")


if __name__ == "__main__":
    main()
