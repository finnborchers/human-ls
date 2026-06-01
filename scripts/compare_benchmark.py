#!/usr/bin/env python3

import json
import os
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path


BASE_DIR = Path("analysis/llm/benchmark_comparison")
PREDICTION_PATH = Path(
    os.getenv("BENCHMARK_PREDICTION_PATH", str(BASE_DIR / "reviews_v1_120_labled.json"))
)
REFERENCE_PATH = Path(
    os.getenv(
        "BENCHMARK_REFERENCE_PATH",
        str(BASE_DIR / "benchmark_v1_120_reviewed_2026-05-14T13-43-24Z.json"),
    )
)
OUT_PATH = Path(
    os.getenv("BENCHMARK_COMPARE_OUT_PATH", str(BASE_DIR / "reviews_v1_120_compare.json"))
)

BUCKETS = ("positive", "negative", "mixed_hard")
DOMAINS = (
    "access",
    "admin",
    "communication",
    "staff",
    "care",
    "coordination",
    "environment",
    "inclusion",
)


def load_json(path: Path) -> dict:
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def normalize_prediction_payload(path: Path) -> dict[str, dict]:
    data = load_json(path)

    if "records" in data:
        normalized = {}
        for review_id, record in data["records"].items():
            labels = (
                record.get("labels")
                or record.get("model_prelabels")
                or record.get("benchmark_labels")
                or {}
            )
            normalized[review_id] = {
                "review_id": review_id,
                "bucket": record.get("bucket"),
                "problem_labels": sorted(set(labels.get("problem_labels", []))),
                "strength_labels": sorted(set(labels.get("strength_labels", []))),
            }
        return normalized

    normalized = {}
    for review_id, record in data.items():
        labels = record.get("labels") or {}
        normalized[review_id] = {
            "review_id": review_id,
            "bucket": None,
            "problem_labels": sorted(set(labels.get("problem_labels", []))),
            "strength_labels": sorted(set(labels.get("strength_labels", []))),
        }
    return normalized


def normalize_reference_payload(path: Path) -> dict[str, dict]:
    data = load_json(path)
    if "records" not in data:
        raise ValueError(f"Reference file must contain a 'records' object: {path}")

    normalized = {}
    for review_id, record in data["records"].items():
        labels = record.get("benchmark_labels") or {}
        normalized[review_id] = {
            "review_id": review_id,
            "bucket": record.get("bucket"),
            "problem_labels": sorted(set(labels.get("problem_labels", []))),
            "strength_labels": sorted(set(labels.get("strength_labels", []))),
        }
    return normalized


def init_stats() -> dict:
    return {
        "total_reviews": 0,
        "exact_matches": 0,
        "non_exact_matches": 0,
        "benchmark_total_labels": 0,
        "predicted_total_labels": 0,
        "matched_labels": 0,
        "missing_labels": 0,
        "extra_labels": 0,
    }


def merge_labels(problem_labels: list[str], strength_labels: list[str]) -> set[tuple[str, str]]:
    merged = set()
    for label in problem_labels:
        merged.add(("problem", label))
    for label in strength_labels:
        merged.add(("strength", label))
    return merged


def init_domain_stats() -> dict[str, dict]:
    return {domain: init_stats() for domain in DOMAINS}


def main() -> None:
    reference = normalize_reference_payload(REFERENCE_PATH)
    prediction = normalize_prediction_payload(PREDICTION_PATH)

    overall = init_stats()
    buckets = {bucket: init_stats() for bucket in BUCKETS}
    domains = init_domain_stats()
    missing_counter = Counter()
    extra_counter = Counter()
    missing_problem_counter = Counter()
    missing_strength_counter = Counter()
    extra_problem_counter = Counter()
    extra_strength_counter = Counter()

    for review_id, reference_record in reference.items():
        predicted_record = prediction.get(review_id)
        if predicted_record is None:
            raise KeyError(f"Missing prediction for review_id={review_id}")

        bucket = reference_record["bucket"]
        if bucket not in buckets:
            raise KeyError(f"Unexpected bucket {bucket!r} for review_id={review_id}")

        ref_labels = merge_labels(
            reference_record["problem_labels"],
            reference_record["strength_labels"],
        )
        pred_labels = merge_labels(
            predicted_record["problem_labels"],
            predicted_record["strength_labels"],
        )

        missing = ref_labels - pred_labels
        extra = pred_labels - ref_labels
        matched = ref_labels & pred_labels
        exact = not missing and not extra

        for stats in (overall, buckets[bucket]):
            stats["total_reviews"] += 1
            stats["benchmark_total_labels"] += len(ref_labels)
            stats["predicted_total_labels"] += len(pred_labels)
            stats["matched_labels"] += len(matched)
            stats["missing_labels"] += len(missing)
            stats["extra_labels"] += len(extra)
            if exact:
                stats["exact_matches"] += 1
            else:
                stats["non_exact_matches"] += 1

        ref_by_domain = Counter(label.split(".", 1)[0] for _, label in ref_labels)
        pred_by_domain = Counter(label.split(".", 1)[0] for _, label in pred_labels)
        matched_by_domain = Counter(label.split(".", 1)[0] for _, label in matched)
        missing_by_domain = Counter(label.split(".", 1)[0] for _, label in missing)
        extra_by_domain = Counter(label.split(".", 1)[0] for _, label in extra)

        for domain in DOMAINS:
            domain_stats = domains[domain]
            domain_stats["total_reviews"] += 1
            domain_stats["benchmark_total_labels"] += ref_by_domain[domain]
            domain_stats["predicted_total_labels"] += pred_by_domain[domain]
            domain_stats["matched_labels"] += matched_by_domain[domain]
            domain_stats["missing_labels"] += missing_by_domain[domain]
            domain_stats["extra_labels"] += extra_by_domain[domain]
            if (
                ref_by_domain[domain] == pred_by_domain[domain] == matched_by_domain[domain]
                and missing_by_domain[domain] == 0
                and extra_by_domain[domain] == 0
            ):
                domain_stats["exact_matches"] += 1
            else:
                domain_stats["non_exact_matches"] += 1

        for polarity, label in missing:
            missing_counter[f"{polarity}:{label}"] += 1
            if polarity == "problem":
                missing_problem_counter[label] += 1
            else:
                missing_strength_counter[label] += 1
        for polarity, label in extra:
            extra_counter[f"{polarity}:{label}"] += 1
            if polarity == "problem":
                extra_problem_counter[label] += 1
            else:
                extra_strength_counter[label] += 1

    result = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "prediction_file": str(PREDICTION_PATH),
        "reference_file": str(REFERENCE_PATH),
        "overall": overall,
        "buckets": buckets,
        "domains": domains,
        "top_missing_labels": missing_counter.most_common(15),
        "top_extra_labels": extra_counter.most_common(15),
        "top_missing_problem_labels": missing_problem_counter.most_common(15),
        "top_missing_strength_labels": missing_strength_counter.most_common(15),
        "top_extra_problem_labels": extra_problem_counter.most_common(15),
        "top_extra_strength_labels": extra_strength_counter.most_common(15),
    }

    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    with OUT_PATH.open("w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)

    print(f"[ok] wrote compare summary: {OUT_PATH}")
    print(json.dumps(result["overall"], ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
