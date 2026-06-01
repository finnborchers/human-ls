#!/usr/bin/env python3

import json
import os
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path


OUT_DIR = Path(os.getenv("FULLRUN_OUT_DIR", "analysis/llm/full_run/v1_batch_run"))
MANIFEST_PATH = OUT_DIR / "manifest.json"
SCOPE = os.getenv("FULLRUN_SCOPE", "10000_ids")
MERGE_ALL = os.getenv("FULLRUN_MERGE_ALL", "0") == "1"


def load_json(path: str | Path):
    with Path(path).open("r", encoding="utf-8") as f:
        return json.load(f)


def write_json(path: str | Path, payload: dict) -> None:
    file_path = Path(path)
    file_path.parent.mkdir(parents=True, exist_ok=True)
    with file_path.open("w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)


def summarize_records(records: dict) -> dict:
    problem_counter = Counter()
    strength_counter = Counter()
    empty_labels = 0
    max_total_labels = 0

    for record in records.values():
        labels = record.get("labels") or {}
        problems = labels.get("problem_labels", [])
        strengths = labels.get("strength_labels", [])
        if not problems and not strengths:
            empty_labels += 1
        for label in problems:
            problem_counter[label] += 1
        for label in strengths:
            strength_counter[label] += 1
        max_total_labels = max(max_total_labels, len(problems) + len(strengths))

    return {
        "total_records": len(records),
        "empty_label_records": empty_labels,
        "max_total_labels_on_single_review": max_total_labels,
        "top_problem_labels": problem_counter.most_common(15),
        "top_strength_labels": strength_counter.most_common(15),
    }


def merge_scope(manifest: dict, scope: str) -> None:
    scope_config = manifest["scopes"][scope]
    merged = {}
    batch_summaries = []
    total_parse_errors = 0

    for batch_info in scope_config["batches"]:
        normalized_path = Path(batch_info["normalized_path"])
        if not normalized_path.exists():
            continue
        payload = load_json(normalized_path)
        records = payload.get("records", {})
        for review_id, record in records.items():
            merged[review_id] = record
        run_meta = payload.get("run_meta", {})
        batch_summaries.append(
            {
                "batch_name": batch_info["batch_name"],
                "materialized_records": run_meta.get("materialized_records", len(records)),
                "parse_errors": run_meta.get("parse_errors", 0),
            }
        )
        total_parse_errors += run_meta.get("parse_errors", 0)

    summary = summarize_records(merged)
    summary.update(
        {
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "scope": scope,
            "expected_reviews": scope_config["total_reviews"],
            "materialized_reviews": len(merged),
            "missing_reviews": scope_config["total_reviews"] - len(merged),
            "batch_count": scope_config["batch_count"],
            "completed_batch_files": len(batch_summaries),
            "parse_errors_total": total_parse_errors,
            "batch_summaries": batch_summaries,
        }
    )

    merged_payload = {
        "run_meta": {
            "provider": "openai",
            "runner": "merge_fullrun_v1_batches.py",
            "scope": scope,
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "record_count": len(merged),
        },
        "records": merged,
    }

    merged_dir = OUT_DIR / "merged"
    write_json(merged_dir / f"{scope}_labeled.json", merged_payload)
    write_json(merged_dir / f"{scope}_summary.json", summary)
    print(f"[ok] merged {scope}: {len(merged)} records")


def merge_all(manifest: dict) -> None:
    merged = {}
    scopes = []
    for scope in sorted(manifest["scopes"].keys()):
        path = OUT_DIR / "merged" / f"{scope}_labeled.json"
        if not path.exists():
            continue
        payload = load_json(path)
        scopes.append(scope)
        for review_id, record in payload.get("records", {}).items():
            merged[review_id] = record

    summary = summarize_records(merged)
    summary.update(
        {
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "scopes": scopes,
            "materialized_reviews": len(merged),
        }
    )
    merged_dir = OUT_DIR / "merged"
    write_json(
        merged_dir / "all_scopes_labeled.json",
        {
            "run_meta": {
                "provider": "openai",
                "runner": "merge_fullrun_v1_batches.py",
                "scope": "all_scopes",
                "generated_at": datetime.now(timezone.utc).isoformat(),
                "record_count": len(merged),
            },
            "records": merged,
        },
    )
    write_json(merged_dir / "all_scopes_summary.json", summary)
    print(f"[ok] merged all scopes: {len(merged)} records")


def main() -> None:
    manifest = load_json(MANIFEST_PATH)
    if MERGE_ALL:
        merge_all(manifest)
        return
    if SCOPE not in manifest.get("scopes", {}):
        available = ", ".join(sorted(manifest.get("scopes", {}).keys()))
        raise KeyError(f"Unknown FULLRUN_SCOPE={SCOPE!r}. Available: {available}")
    merge_scope(manifest, SCOPE)


if __name__ == "__main__":
    main()
