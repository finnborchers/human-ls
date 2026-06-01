#!/usr/bin/env python3

import json
import math
import os
from datetime import datetime, timezone
from pathlib import Path

from benchmark_runner_utils import build_meta, load_review_records
from prompt_flat_v1 import SYSTEM_PROMPT_V1, build_prompt_v1


OUT_DIR = Path(os.getenv("FULLRUN_OUT_DIR", "analysis/llm/full_run/v1_batch_run"))
MODEL = os.getenv("FULLRUN_MODEL", "gpt-4.1-mini")
BATCH_SIZE = int(os.getenv("FULLRUN_BATCH_SIZE", "2000"))
PILOT_SIZE = int(os.getenv("FULLRUN_PILOT_SIZE", "10000"))

SAMPLES_DIR = OUT_DIR / "samples"
INPUTS_DIR = OUT_DIR / "inputs"
JOBS_DIR = OUT_DIR / "jobs"
RAW_OUTPUTS_DIR = OUT_DIR / "raw_outputs"
RAW_ERRORS_DIR = OUT_DIR / "raw_errors"
NORMALIZED_DIR = OUT_DIR / "normalized"
MERGED_DIR = OUT_DIR / "merged"

MANIFEST_PATH = OUT_DIR / "manifest.json"
ALL_IDS_PATH = OUT_DIR / "all_review_ids.txt"
PILOT_IDS_PATH = OUT_DIR / "10000_ids.txt"
REMAINDER_IDS_PATH = OUT_DIR / "20863_ids.txt"


def review_schema() -> dict:
    enum_values = [
        "access.appointments",
        "access.waiting",
        "access.reachability",
        "access.navigation",
        "admin.registration",
        "admin.paperwork",
        "admin.costs",
        "admin.privacy",
        "communication.communication",
        "communication.explanation",
        "communication.information",
        "communication.decisions",
        "staff.friendliness",
        "staff.empathy",
        "staff.respect",
        "staff.seriousness",
        "care.diagnosis",
        "care.treatment",
        "care.medication",
        "care.symptoms",
        "care.safety",
        "care.competence",
        "coordination.coordination",
        "coordination.discharge",
        "coordination.followup",
        "environment.cleanliness",
        "environment.facilities",
        "environment.food",
        "environment.support",
        "inclusion.language",
        "inclusion.interpreting",
        "inclusion.equality",
        "inclusion.culture",
        "inclusion.asylum",
    ]
    return {
        "name": "flat_review_labels",
        "strict": True,
        "schema": {
            "type": "object",
            "additionalProperties": False,
            "properties": {
                "problem_labels": {
                    "type": "array",
                    "items": {"type": "string", "enum": enum_values},
                },
                "strength_labels": {
                    "type": "array",
                    "items": {"type": "string", "enum": enum_values},
                },
            },
            "required": ["problem_labels", "strength_labels"],
        },
    }


def write_lines(path: Path, lines: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        f.write("\n".join(lines))
        if lines:
            f.write("\n")


def write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)


def batch_name(scope: str, index: int) -> str:
    return f"{scope}_batch_{index:03d}"


def split_batches(records: list[dict], size: int) -> list[list[dict]]:
    return [records[i : i + size] for i in range(0, len(records), size)]


def make_batch_line(row: dict) -> dict:
    meta = build_meta(row)
    meta_json = json.dumps(meta, ensure_ascii=False, indent=2)
    prompt = build_prompt_v1(row["review_text"], meta_json)
    return {
        "custom_id": row["review_id"],
        "method": "POST",
        "url": "/v1/chat/completions",
        "body": {
            "model": MODEL,
            "messages": [
                {"role": "system", "content": SYSTEM_PROMPT_V1},
                {"role": "user", "content": prompt},
            ],
            "response_format": {
                "type": "json_schema",
                "json_schema": review_schema(),
            },
        },
    }


def scope_paths(scope: str, batch_index: int) -> dict:
    name = batch_name(scope, batch_index)
    return {
        "name": name,
        "sample_path": SAMPLES_DIR / f"{name}.txt",
        "input_path": INPUTS_DIR / f"{name}.jsonl",
        "job_path": JOBS_DIR / f"{name}.json",
        "raw_output_path": RAW_OUTPUTS_DIR / f"{name}.jsonl",
        "raw_error_path": RAW_ERRORS_DIR / f"{name}.jsonl",
        "normalized_path": NORMALIZED_DIR / f"{name}.json",
    }


def build_scope(scope: str, scope_records: list[dict]) -> dict:
    batches = []
    for index, batch_records in enumerate(split_batches(scope_records, BATCH_SIZE), start=1):
        paths = scope_paths(scope, index)
        review_ids = [row["review_id"] for row in batch_records]
        write_lines(paths["sample_path"], review_ids)

        with paths["input_path"].open("w", encoding="utf-8") as f:
            for row in batch_records:
                f.write(json.dumps(make_batch_line(row), ensure_ascii=False))
                f.write("\n")

        batches.append(
            {
                "batch_name": paths["name"],
                "batch_index": index,
                "review_count": len(batch_records),
                "sample_path": str(paths["sample_path"]),
                "input_path": str(paths["input_path"]),
                "job_path": str(paths["job_path"]),
                "raw_output_path": str(paths["raw_output_path"]),
                "raw_error_path": str(paths["raw_error_path"]),
                "normalized_path": str(paths["normalized_path"]),
                "first_review_id": review_ids[0],
                "last_review_id": review_ids[-1],
            }
        )
    return {
        "scope": scope,
        "total_reviews": len(scope_records),
        "batch_size": BATCH_SIZE,
        "batch_count": len(batches),
        "batches": batches,
    }


def main() -> None:
    for directory in [
        OUT_DIR,
        SAMPLES_DIR,
        INPUTS_DIR,
        JOBS_DIR,
        RAW_OUTPUTS_DIR,
        RAW_ERRORS_DIR,
        NORMALIZED_DIR,
        MERGED_DIR,
    ]:
        directory.mkdir(parents=True, exist_ok=True)

    all_records = load_review_records(sample_path=None, start_index=0, num_reviews=10**9)
    all_records = [row for row in all_records if row.get("review_text", "").strip()]
    all_review_ids = [row["review_id"] for row in all_records]

    pilot_records = all_records[:PILOT_SIZE]
    remainder_records = all_records[PILOT_SIZE:]

    pilot_scope = "10000_ids"
    remainder_scope = f"{len(remainder_records)}_ids"

    write_lines(ALL_IDS_PATH, all_review_ids)
    write_lines(PILOT_IDS_PATH, [row["review_id"] for row in pilot_records])
    write_lines(REMAINDER_IDS_PATH, [row["review_id"] for row in remainder_records])

    manifest = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "version": "v1_batch_run",
        "model": MODEL,
        "prompt_version": "v1",
        "system_prompt": SYSTEM_PROMPT_V1,
        "batch_api_endpoint": "/v1/chat/completions",
        "batch_size": BATCH_SIZE,
        "all_review_ids_path": str(ALL_IDS_PATH),
        "all_review_count": len(all_records),
        "pilot_ids_path": str(PILOT_IDS_PATH),
        "pilot_review_count": len(pilot_records),
        "remainder_ids_path": str(REMAINDER_IDS_PATH),
        "remainder_review_count": len(remainder_records),
        "scopes": {
            pilot_scope: build_scope(pilot_scope, pilot_records),
            remainder_scope: build_scope(remainder_scope, remainder_records),
        },
    }
    write_json(MANIFEST_PATH, manifest)

    print(f"[ok] wrote manifest: {MANIFEST_PATH}")
    print(f"[ok] wrote all ids: {ALL_IDS_PATH} ({len(all_records)} reviews)")
    print(f"[ok] wrote scope ids: {PILOT_IDS_PATH} ({len(pilot_records)} reviews)")
    print(f"[ok] wrote scope ids: {REMAINDER_IDS_PATH} ({len(remainder_records)} reviews)")
    print(
        f"[ok] built {manifest['scopes'][pilot_scope]['batch_count']} batches for {pilot_scope} "
        f"and {manifest['scopes'][remainder_scope]['batch_count']} batches for {remainder_scope}"
    )


if __name__ == "__main__":
    main()
