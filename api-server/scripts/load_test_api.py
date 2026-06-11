#!/usr/bin/env python3
import argparse
import concurrent.futures
import json
import statistics
import time
import urllib.error
import urllib.request


def fetch(url: str, timeout: float) -> dict:
    started_at = time.perf_counter()
    status = 0
    error = ""
    try:
        request = urllib.request.Request(url, headers={"Accept": "application/json"})
        with urllib.request.urlopen(request, timeout=timeout) as response:
            status = response.status
            response.read()
    except urllib.error.HTTPError as exc:
        status = exc.code
        error = str(exc)
    except Exception as exc:
        error = str(exc)

    elapsed_ms = round((time.perf_counter() - started_at) * 1000, 2)
    return {"status": status, "elapsed_ms": elapsed_ms, "error": error}


def percentile(values: list[float], target: int) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    index = max(round((target / 100) * len(ordered) + 0.5) - 1, 0)
    return ordered[min(index, len(ordered) - 1)]


def run_load_test(url: str, total_requests: int, concurrency: int, timeout: float) -> dict:
    started_at = time.perf_counter()
    with concurrent.futures.ThreadPoolExecutor(max_workers=concurrency) as executor:
        futures = [executor.submit(fetch, url, timeout) for _ in range(total_requests)]
        results = [future.result() for future in concurrent.futures.as_completed(futures)]

    elapsed_values = [result["elapsed_ms"] for result in results if result["status"] > 0]
    status_counts: dict[str, int] = {}
    for result in results:
        key = str(result["status"]) if result["status"] > 0 else "error"
        status_counts[key] = status_counts.get(key, 0) + 1

    return {
        "url": url,
        "total_requests": total_requests,
        "concurrency": concurrency,
        "duration_seconds": round(time.perf_counter() - started_at, 2),
        "status_counts": status_counts,
        "avg_ms": round(statistics.mean(elapsed_values), 2) if elapsed_values else 0.0,
        "p95_ms": round(percentile(elapsed_values, 95), 2),
        "max_ms": max(elapsed_values) if elapsed_values else 0.0,
        "errors": [result["error"] for result in results if result["error"]][:5],
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Simple API load test for the article read endpoint.")
    parser.add_argument("--url", default="http://localhost:8081/api/v1/articles?size=20")
    parser.add_argument("--requests", type=int, default=100)
    parser.add_argument("--concurrency", type=int, default=10)
    parser.add_argument("--timeout", type=float, default=5.0)
    parser.add_argument("--output")
    args = parser.parse_args()

    summary = run_load_test(args.url, args.requests, args.concurrency, args.timeout)
    rendered = json.dumps(summary, ensure_ascii=False, indent=2)
    print(rendered)

    if args.output:
        with open(args.output, "w", encoding="utf-8") as output_file:
            output_file.write(rendered + "\n")


if __name__ == "__main__":
    main()
