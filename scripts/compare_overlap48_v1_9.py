#!/usr/bin/env python3

import json
import os
from datetime import datetime, timezone
from pathlib import Path

from compare_benchmark import normalize_prediction_payload, normalize_reference_payload


BENCHMARK_PATH = Path(
    os.getenv(
        "BENCHMARK_REFERENCE_PATH",
        "analysis/llm/benchmark_comparison/benchmark_v1_120_reviewed_2026-05-14T13-43-24Z.json",
    )
)
BATCH10K_PATH = Path(
    os.getenv(
        "OVERLAP_BATCH_PATH",
        "analysis/llm/full_run/v1_batch_run/merged/10000_ids_labeled.json",
    )
)
V1_PATH = Path(
    os.getenv(
        "OVERLAP_V1_PATH",
        "analysis/llm/benchmark_comparison/reviews_v1_120_labled.json",
    )
)
V19_PATH = Path(
    os.getenv(
        "OVERLAP_V19_PATH",
        "analysis/llm/benchmark_comparison/reviews_v1_9_120_labeled.json",
    )
)
OUT_PATH = Path(
    os.getenv(
        "OVERLAP_V19_OUT_PATH",
        "analysis/llm/benchmark_comparison/reviews_v1_9_overlap48_compare.json",
    )
)


def merge_labels(problem_labels: list[str], strength_labels: list[str]) -> set[tuple[str, str]]:
    merged = set()
    for label in problem_labels:
        merged.add(("problem", label))
    for label in strength_labels:
        merged.add(("strength", label))
    return merged


def compare_subset(reference: dict[str, dict], prediction: dict[str, dict], overlap_ids: list[str]) -> dict:
    exact_matches = 0
    matched_labels = 0
    missing_labels = 0
    extra_labels = 0

    for review_id in overlap_ids:
        ref = reference[review_id]
        pred = prediction[review_id]
        ref_labels = merge_labels(ref["problem_labels"], ref["strength_labels"])
        pred_labels = merge_labels(pred["problem_labels"], pred["strength_labels"])
        missing = ref_labels - pred_labels
        extra = pred_labels - ref_labels
        matched = ref_labels & pred_labels
        if not missing and not extra:
            exact_matches += 1
        matched_labels += len(matched)
        missing_labels += len(missing)
        extra_labels += len(extra)

    return {
        "total_reviews": len(overlap_ids),
        "exact_matches": exact_matches,
        "matched_labels": matched_labels,
        "missing_labels": missing_labels,
        "extra_labels": extra_labels,
    }


def main() -> None:
    reference = normalize_reference_payload(BENCHMARK_PATH)
    batch10k = normalize_prediction_payload(BATCH10K_PATH)
    v1 = normalize_prediction_payload(V1_PATH)
    v19 = normalize_prediction_payload(V19_PATH)

    overlap_ids = sorted(set(reference) & set(batch10k))
    for name, payload in [("v1", v1), ("v1_9", v19)]:
        missing = [review_id for review_id in overlap_ids if review_id not in payload]
        if missing:
            raise KeyError(f"{name} missing overlap review ids: {missing[:5]}")

    payload = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "benchmark_reference_path": str(BENCHMARK_PATH),
        "batch10k_path": str(BATCH10K_PATH),
        "v1_path": str(V1_PATH),
        "v1_9_path": str(V19_PATH),
        "overlap_review_count": len(overlap_ids),
        "overlap_review_ids": overlap_ids,
        "results": {
            "v1_overlap48": compare_subset(reference, v1, overlap_ids),
            "batch10k_overlap48": compare_subset(reference, batch10k, overlap_ids),
            "v1_9_overlap48": compare_subset(reference, v19, overlap_ids),
        },
    }
    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    with OUT_PATH.open("w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)
    print(f"[ok] wrote overlap48 comparison: {OUT_PATH}")
    print(json.dumps(payload["results"], ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
