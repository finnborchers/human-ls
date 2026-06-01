#!/usr/bin/env python3

import json
import os
import sys
from pathlib import Path

from benchmark_runner_utils import assess_run_completeness, load_sample_ids


RUN_PATH = Path(
    os.getenv(
        "BENCHMARK_RUN_PATH",
        "analysis/llm/benchmark_comparison/reviews_gemini_2_5_pro_holdout20_labeled.json",
    )
)
SAMPLE_PATH = os.getenv(
    "BENCHMARK_SAMPLE_PATH",
    "analysis/llm/finetune/reviews_v1_7_holdout_ids_20.txt",
)


def main() -> int:
    if not RUN_PATH.exists():
        print(f"[error] run file does not exist: {RUN_PATH}")
        return 1

    with RUN_PATH.open("r", encoding="utf-8") as f:
        data = json.load(f)

    records = data.get("records", data)
    run_meta = data.get("run_meta", {})
    expected_ids = load_sample_ids(SAMPLE_PATH)
    completeness = assess_run_completeness(records, expected_ids)

    print(f"Run file: {RUN_PATH}")
    print(f"Expected reviews: {completeness['expected_count']}")
    print(f"Completed reviews: {completeness['completed_count']}")
    print(f"Malformed reviews: {len(completeness['malformed_ids'])}")
    print(f"Missing reviews: {len(completeness['missing_ids'])}")
    print(f"Run meta is_complete: {run_meta.get('is_complete')}")

    if completeness["malformed_ids"]:
        print("\nMalformed review_ids:")
        for review_id in completeness["malformed_ids"]:
            print(f"- {review_id}")

    if completeness["missing_ids"]:
        print("\nMissing review_ids:")
        for review_id in completeness["missing_ids"]:
            print(f"- {review_id}")

    if not completeness["is_complete"]:
        print(
            "\n[incomplete] Benchmark run is not complete. Rerun the labeling script to fill the missing reviews before compare/plot."
        )
        return 1

    print("\n[ok] Benchmark run is complete and ready for compare/plot.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
