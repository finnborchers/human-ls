#!/usr/bin/env python3

import json
import os
import time
from datetime import datetime, timezone
from pathlib import Path


ARTIFACTS_ROOT = "artifacts"


def load_review_records(sample_path: str | None, start_index: int, num_reviews: int) -> list[dict]:
    records = []
    for place_id in sorted(os.listdir(ARTIFACTS_ROOT)):
        reviews_path = os.path.join(ARTIFACTS_ROOT, place_id, "reviews.json")
        if not os.path.exists(reviews_path):
            continue

        try:
            with open(reviews_path, "r", encoding="utf-8") as f:
                reviews = json.load(f)
        except json.JSONDecodeError as e:
            print(
                f"[warn] skipping unreadable file, probably still being written: {reviews_path} ({e})"
            )
            continue

        for review_index, review in enumerate(reviews):
            records.append(
                {
                    "review_id": f"{place_id}:{review_index}",
                    "place_id": place_id,
                    "clinic_name": None,
                    "review_index": review_index,
                    "star_rating": review.get("star_rating"),
                    "review_time": review.get("review_time"),
                    "like_count": review.get("like_count"),
                    "has_owner_response": review.get("has_owner_response"),
                    "review_text": review.get("review_text", ""),
                }
            )

    if sample_path:
        with open(sample_path, "r", encoding="utf-8") as f:
            sample_ids = {line.strip() for line in f if line.strip()}

        records = [row for row in records if row["review_id"] in sample_ids]

    return records[start_index : start_index + num_reviews]


def load_existing_results(out_path: str) -> tuple[dict, dict]:
    path = Path(out_path)
    if not path.exists():
        return {}, {}

    with path.open("r", encoding="utf-8") as f:
        data = json.load(f)

    if "records" in data:
        return data["records"], data.get("run_meta", {})

    return data, {}


def load_json_file(path: str, default):
    file_path = Path(path)
    if not file_path.exists():
        return default

    with file_path.open("r", encoding="utf-8") as f:
        return json.load(f)


def write_json_file(path: str, payload) -> None:
    file_path = Path(path)
    file_path.parent.mkdir(parents=True, exist_ok=True)
    with file_path.open("w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)


def load_sample_ids(sample_path: str | None) -> list[str]:
    if not sample_path:
        return []

    with open(sample_path, "r", encoding="utf-8") as f:
        return [line.strip() for line in f if line.strip()]


def build_meta(row: dict) -> dict:
    return {
        "place_id": row.get("place_id"),
        "clinic_name": row.get("clinic_name"),
        "star_rating": row.get("star_rating"),
        "review_time": row.get("review_time"),
        "like_count": row.get("like_count"),
        "has_owner_response": row.get("has_owner_response"),
    }


def write_results(out_path: str, records: dict, run_meta: dict) -> None:
    path = Path(out_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        json.dump(
            {
                "run_meta": run_meta,
                "records": records,
            },
            f,
            ensure_ascii=False,
            indent=2,
        )


def init_run_meta(
    *,
    provider: str,
    model: str,
    sample_path: str | None,
    temperature: float | None = None,
    reasoning_effort: str | None = None,
    extra: dict | None = None,
) -> dict:
    run_meta = {
        "provider": provider,
        "model": model,
        "sample_path": sample_path,
        "temperature": temperature,
        "reasoning_effort": reasoning_effort,
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }
    if extra:
        run_meta.update(extra)
    return run_meta


def finalize_run_meta(run_meta: dict, *, processed: int, skipped: int, errors: int, total_request_sec: float):
    updated = dict(run_meta)
    updated["processed"] = processed
    updated["skipped"] = skipped
    updated["errors"] = errors
    updated["total_request_sec"] = round(total_request_sec, 4)
    updated["avg_request_sec"] = round(total_request_sec / processed, 4) if processed else 0.0
    updated["updated_at"] = datetime.now(timezone.utc).isoformat()
    return updated


def summarize_run(*, processed: int, skipped: int, errors: int, total_wall_sec: float, total_request_sec: float, model: str, out_path: str) -> None:
    avg_per_review = (total_request_sec / processed) if processed > 0 else 0.0
    per_min = (60.0 / avg_per_review) if avg_per_review > 0 else 0.0

    print("\n=== SUMMARY ===")
    print(f"Processed: {processed}")
    print(f"Skipped:   {skipped}")
    print(f"Errors:    {errors}")
    print(f"Model:     {model}")
    print(f"Total wall-clock: {total_wall_sec:.2f}s")
    print(f"Avg request time/review: {avg_per_review:.2f}s")
    print(f"Throughput: ~{per_min:.1f} reviews/min (model time)")
    print(f"Output: {out_path}")


def now_monotonic() -> float:
    return time.time()


def assess_run_completeness(records: dict, expected_ids: list[str]) -> dict:
    missing_ids = [review_id for review_id in expected_ids if review_id not in records]
    malformed_ids = []

    for review_id, record in records.items():
        labels = record.get("labels")
        if not isinstance(labels, dict):
            malformed_ids.append(review_id)
            continue
        if not isinstance(labels.get("problem_labels", []), list):
            malformed_ids.append(review_id)
            continue
        if not isinstance(labels.get("strength_labels", []), list):
            malformed_ids.append(review_id)

    return {
        "expected_count": len(expected_ids),
        "completed_count": len(records),
        "missing_ids": missing_ids,
        "malformed_ids": malformed_ids,
        "failed_count": len(missing_ids) + len(malformed_ids),
        "is_complete": not missing_ids and not malformed_ids and len(records) == len(expected_ids),
    }
