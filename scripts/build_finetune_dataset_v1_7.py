#!/usr/bin/env python3

import json
import os
import random
from datetime import datetime, timezone
from pathlib import Path

from models.review_labels_flat import FlatExtraction
from prompt_flat_v1 import SYSTEM_PROMPT_V1, build_prompt_v1


SOURCE_PATH = Path(
    os.getenv(
        "BENCHMARK_SOURCE_PATH",
        "analysis/llm/benchmark_comparison/benchmark_v1_120_reviewed_2026-05-14T13-43-24Z.json",
    )
)
OUT_DIR = Path(os.getenv("FINETUNE_OUT_DIR", "analysis/llm/finetune"))
SPLIT_SEED = int(os.getenv("FINETUNE_SPLIT_SEED", "20260514"))

TRAIN_IDS_PATH = OUT_DIR / "reviews_v1_7_train_ids_100.txt"
HOLDOUT_IDS_PATH = OUT_DIR / "reviews_v1_7_holdout_ids_20.txt"
HOLDOUT_REFERENCE_PATH = OUT_DIR / "reviews_v1_7_holdout_reference.json"
TRAIN_JSONL_PATH = OUT_DIR / "reviews_v1_7_train_100.jsonl"
VALID_JSONL_PATH = OUT_DIR / "reviews_v1_7_valid_20.jsonl"
MANIFEST_PATH = OUT_DIR / "reviews_v1_7_dataset_manifest.json"

HOLDOUT_COUNTS = {
    "positive": 7,
    "negative": 7,
    "mixed_hard": 6,
}


def load_source() -> dict:
    with SOURCE_PATH.open("r", encoding="utf-8") as f:
        return json.load(f)


def canonicalize_labels(raw_labels: dict) -> dict:
    labels = FlatExtraction(
        problem_labels=raw_labels.get("problem_labels", []),
        strength_labels=raw_labels.get("strength_labels", []),
    )
    return labels.model_dump()


def select_holdout_ids(records: dict[str, dict]) -> list[str]:
    by_bucket: dict[str, list[str]] = {bucket: [] for bucket in HOLDOUT_COUNTS}
    for review_id, record in records.items():
        bucket = record["bucket"]
        if bucket not in by_bucket:
            raise KeyError(f"Unexpected bucket {bucket!r} for review_id={review_id}")
        by_bucket[bucket].append(review_id)

    holdout_ids: list[str] = []
    for bucket, count in HOLDOUT_COUNTS.items():
        candidates = sorted(by_bucket[bucket])
        rng = random.Random(f"{SPLIT_SEED}:{bucket}")
        shuffled = candidates[:]
        rng.shuffle(shuffled)
        selected = sorted(shuffled[:count])
        if len(selected) != count:
            raise ValueError(f"Bucket {bucket!r} produced {len(selected)} holdout ids, expected {count}")
        holdout_ids.extend(selected)

    return sorted(holdout_ids)


def build_subset_reference(source: dict, holdout_ids: list[str]) -> dict:
    holdout_records = {review_id: source["records"][review_id] for review_id in holdout_ids}
    subset = dict(source)
    subset["records"] = holdout_records
    subset["benchmark_name"] = f"{source.get('benchmark_name', 'benchmark')}_holdout20"
    subset["working_file_role"] = "holdout_reference_subset"
    subset["source_file"] = str(SOURCE_PATH)
    subset["saved_at"] = datetime.now(timezone.utc).isoformat()
    subset["holdout_split_seed"] = SPLIT_SEED
    subset["holdout_total_reviews"] = len(holdout_ids)
    return subset


def record_to_jsonl_line(record: dict) -> str:
    meta_json = json.dumps(record["metadata"], ensure_ascii=False, indent=2)
    prompt = build_prompt_v1(record["review_text"], meta_json)
    labels = canonicalize_labels(record["benchmark_labels"])
    payload = {
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT_V1},
            {"role": "user", "content": prompt},
            {"role": "assistant", "content": json.dumps(labels, ensure_ascii=False, separators=(",", ":"))},
        ]
    }
    return json.dumps(payload, ensure_ascii=False)


def write_jsonl(path: Path, records: list[dict]) -> None:
    with path.open("w", encoding="utf-8") as f:
        for record in records:
            f.write(record_to_jsonl_line(record))
            f.write("\n")


def write_ids(path: Path, review_ids: list[str]) -> None:
    with path.open("w", encoding="utf-8") as f:
        for review_id in review_ids:
            f.write(review_id)
            f.write("\n")


def main() -> None:
    source = load_source()
    records = source["records"]

    holdout_ids = select_holdout_ids(records)
    holdout_set = set(holdout_ids)
    train_ids = sorted(review_id for review_id in records if review_id not in holdout_set)

    train_records = [records[review_id] for review_id in train_ids]
    holdout_records = [records[review_id] for review_id in holdout_ids]

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    write_ids(TRAIN_IDS_PATH, train_ids)
    write_ids(HOLDOUT_IDS_PATH, holdout_ids)
    write_jsonl(TRAIN_JSONL_PATH, train_records)
    write_jsonl(VALID_JSONL_PATH, holdout_records)

    holdout_reference = build_subset_reference(source, holdout_ids)
    with HOLDOUT_REFERENCE_PATH.open("w", encoding="utf-8") as f:
        json.dump(holdout_reference, f, ensure_ascii=False, indent=2)

    manifest = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "source_benchmark_path": str(SOURCE_PATH),
        "base_model": "gpt-4.1-mini-2025-04-14",
        "prompt_version": "v1",
        "system_prompt": SYSTEM_PROMPT_V1,
        "split_seed": SPLIT_SEED,
        "holdout_counts": HOLDOUT_COUNTS,
        "train_total_reviews": len(train_ids),
        "holdout_total_reviews": len(holdout_ids),
        "train_ids_path": str(TRAIN_IDS_PATH),
        "holdout_ids_path": str(HOLDOUT_IDS_PATH),
        "train_jsonl_path": str(TRAIN_JSONL_PATH),
        "valid_jsonl_path": str(VALID_JSONL_PATH),
        "holdout_reference_path": str(HOLDOUT_REFERENCE_PATH),
        "train_ids": train_ids,
        "holdout_ids": holdout_ids,
    }
    with MANIFEST_PATH.open("w", encoding="utf-8") as f:
        json.dump(manifest, f, ensure_ascii=False, indent=2)

    print(f"[ok] wrote train ids: {TRAIN_IDS_PATH}")
    print(f"[ok] wrote holdout ids: {HOLDOUT_IDS_PATH}")
    print(f"[ok] wrote train jsonl: {TRAIN_JSONL_PATH}")
    print(f"[ok] wrote valid jsonl: {VALID_JSONL_PATH}")
    print(f"[ok] wrote holdout reference: {HOLDOUT_REFERENCE_PATH}")
    print(f"[ok] wrote dataset manifest: {MANIFEST_PATH}")
    print(
        json.dumps(
            {
                "train_total_reviews": len(train_ids),
                "holdout_total_reviews": len(holdout_ids),
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
