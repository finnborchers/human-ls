#!/usr/bin/env python3

import json
import os
from datetime import datetime, timezone
from pathlib import Path

from dotenv import load_dotenv
from openai import OpenAI

from benchmark_runner_utils import (
    build_meta,
    init_run_meta,
    load_existing_results,
    load_review_records,
    write_results,
)
from models.review_labels_flat import FlatExtraction, FlatReviewAnalysisRecord, FlatReviewMetadata
from prompt_flat_v1 import SYSTEM_PROMPT_V1, build_prompt_v1


load_dotenv()
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
if not OPENAI_API_KEY:
    raise ValueError("No OpenAI API key found in .env")

client = OpenAI(api_key=OPENAI_API_KEY)

OUT_PATH = Path(
    os.getenv(
        "REVIEW_LABELS_OUT_PATH",
        "analysis/llm/benchmark_comparison/reviews_v1_10_120_labeled.json",
    )
)
MODEL = os.getenv("REVIEW_LABELS_MODEL", "gpt-4.1-mini-2025-04-14")
START_INDEX = int(os.getenv("REVIEW_LABELS_START_INDEX", "0"))
NUM_REVIEWS = int(os.getenv("REVIEW_LABELS_NUM_REVIEWS", "1000"))
SAMPLE_PATH = os.getenv(
    "REVIEW_LABELS_SAMPLE_PATH",
    "analysis/llm/samples/review_labels_benchmark_ids_120.txt",
)
TEMPERATURE = float(os.getenv("REVIEW_LABELS_TEMPERATURE", "0"))
MODE = os.getenv("V110_BATCH_MODE", "status")
WORK_DIR = Path(os.getenv("V110_BATCH_DIR", "analysis/llm/benchmark_comparison/v1_10_batch"))
INPUT_PATH = WORK_DIR / "reviews_v1_10_120_input.jsonl"
JOB_PATH = WORK_DIR / "reviews_v1_10_120_batch_job.json"
RAW_OUTPUT_PATH = WORK_DIR / "reviews_v1_10_120_output.jsonl"
RAW_ERROR_PATH = WORK_DIR / "reviews_v1_10_120_error.jsonl"


def to_plain(obj):
    if hasattr(obj, "model_dump"):
        return obj.model_dump()
    if hasattr(obj, "to_dict"):
        return obj.to_dict()
    raise TypeError(f"Unsupported object type for serialization: {type(obj)!r}")


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
        "type": "json_schema",
        "json_schema": {
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
        },
    }


def load_job_state() -> dict:
    if not JOB_PATH.exists():
        return {}
    with JOB_PATH.open("r", encoding="utf-8") as f:
        return json.load(f)


def save_job_state(state: dict) -> None:
    JOB_PATH.parent.mkdir(parents=True, exist_ok=True)
    state["saved_at"] = datetime.now(timezone.utc).isoformat()
    with JOB_PATH.open("w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False, indent=2)


def upload_batch_input(path: Path) -> dict:
    with path.open("rb") as f:
        file_obj = client.files.create(file=f, purpose="batch")
    return to_plain(file_obj)


def create_batch(input_file_id: str) -> dict:
    batch = client.batches.create(
        input_file_id=input_file_id,
        endpoint="/v1/chat/completions",
        completion_window="24h",
        metadata={
            "project": "human-ls",
            "experiment": "v1_10_batch_control",
            "prompt_version": "v1",
        },
    )
    return to_plain(batch)


def retrieve_batch(batch_id: str) -> dict:
    return to_plain(client.batches.retrieve(batch_id))


def file_text(file_id: str) -> str:
    response = client.files.content(file_id)
    text_attr = getattr(response, "text", None)
    if isinstance(text_attr, str):
        return text_attr
    if callable(text_attr):
        return text_attr()
    content = getattr(response, "content", None)
    if isinstance(content, (bytes, bytearray)):
        return bytes(content).decode("utf-8")
    read = getattr(response, "read", None)
    if callable(read):
        raw = read()
        if isinstance(raw, (bytes, bytearray)):
            return bytes(raw).decode("utf-8")
        return str(raw)
    raise TypeError(f"Unable to extract text content from file response: {type(response)!r}")


def parse_jsonl(text: str) -> list[dict]:
    rows = []
    for line in text.splitlines():
        if not line.strip():
            continue
        rows.append(json.loads(line))
    return rows


def build_input_jsonl(records: list[dict]) -> None:
    INPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    with INPUT_PATH.open("w", encoding="utf-8") as f:
        for row in records:
            meta = build_meta(row)
            prompt = build_prompt_v1(row["review_text"], json.dumps(meta, ensure_ascii=False, indent=2))
            payload = {
                "custom_id": row["review_id"],
                "method": "POST",
                "url": "/v1/chat/completions",
                "body": {
                    "model": MODEL,
                    "temperature": TEMPERATURE,
                    "response_format": review_schema(),
                    "messages": [
                        {"role": "system", "content": SYSTEM_PROMPT_V1},
                        {"role": "user", "content": prompt},
                    ],
                },
            }
            f.write(json.dumps(payload, ensure_ascii=False))
            f.write("\n")


def materialize(records: list[dict]) -> None:
    state = load_job_state()
    batch_state = state.get("batch") or {}
    output_file_id = batch_state.get("output_file_id")
    error_file_id = batch_state.get("error_file_id")
    if not output_file_id:
        raise ValueError("No output_file_id available for fetch.")

    raw_output_text = file_text(output_file_id)
    RAW_OUTPUT_PATH.write_text(raw_output_text, encoding="utf-8")
    if error_file_id:
        RAW_ERROR_PATH.write_text(file_text(error_file_id), encoding="utf-8")

    results, previous_meta = load_existing_results(str(OUT_PATH))
    run_meta = init_run_meta(
        provider="openai",
        model=MODEL,
        sample_path=SAMPLE_PATH,
        temperature=TEMPERATURE,
        extra={"prompt_version": "v1", "runner": "analyze_llm_flat_v1_10_batch_gpt.py"},
    )
    if previous_meta:
        run_meta = {**previous_meta, **run_meta}

    row_lookup = {row["review_id"]: row for row in records}
    parse_errors = []

    for item in parse_jsonl(raw_output_text):
        review_id = item.get("custom_id")
        response = item.get("response") or {}
        error = item.get("error")
        status_code = response.get("status_code")
        if error or status_code != 200:
            parse_errors.append({"review_id": review_id, "status_code": status_code, "error": error})
            continue

        body = response.get("body") or {}
        choices = body.get("choices") or []
        if not choices:
            parse_errors.append({"review_id": review_id, "status_code": status_code, "error": "missing_choices"})
            continue

        content = choices[0].get("message", {}).get("content")
        if not isinstance(content, str):
            parse_errors.append({"review_id": review_id, "status_code": status_code, "error": "missing_content"})
            continue

        try:
            extraction = FlatExtraction(**json.loads(content))
        except Exception as exc:
            parse_errors.append({"review_id": review_id, "status_code": status_code, "error": str(exc)})
            continue

        row = row_lookup.get(review_id)
        if not row:
            parse_errors.append({"review_id": review_id, "status_code": status_code, "error": "unknown_review_id"})
            continue

        meta = build_meta(row)
        record = FlatReviewAnalysisRecord(
            review_id=review_id,
            review_index=row["review_index"],
            metadata=FlatReviewMetadata(**meta),
            review_text=row["review_text"],
            labels=extraction,
        )
        results[review_id] = record.model_dump()

    run_meta.update(
        {
            "processed": len(results),
            "skipped": 0,
            "errors": len(parse_errors),
            "updated_at": datetime.now(timezone.utc).isoformat(),
            "batch_id": batch_state.get("id"),
            "output_file_id": output_file_id,
            "error_file_id": error_file_id,
        }
    )
    write_results(str(OUT_PATH), results, run_meta)

    parse_error_path = WORK_DIR / "reviews_v1_10_120_parse_errors.json"
    with parse_error_path.open("w", encoding="utf-8") as f:
        json.dump(parse_errors, f, ensure_ascii=False, indent=2)

    print(f"[ok] materialized benchmark batch output: {OUT_PATH}")
    print(f"[ok] parse errors: {len(parse_errors)} -> {parse_error_path}")


def main() -> None:
    if MODE not in {"submit", "status", "fetch"}:
        raise ValueError("V110_BATCH_MODE must be one of: submit, status, fetch")

    records = load_review_records(SAMPLE_PATH, START_INDEX, NUM_REVIEWS)
    records = [row for row in records if row.get("review_text", "").strip()]

    if MODE == "submit":
        state = load_job_state()
        if state.get("batch", {}).get("id"):
            print(f"[ok] batch already exists: {JOB_PATH}")
            print(json.dumps(state["batch"], ensure_ascii=False, indent=2))
            return

        build_input_jsonl(records)
        uploaded = upload_batch_input(INPUT_PATH)
        batch = create_batch(uploaded["id"])
        state = {
            "model": MODEL,
            "sample_path": SAMPLE_PATH,
            "review_count": len(records),
            "input_jsonl_path": str(INPUT_PATH),
            "uploaded_input_file": uploaded,
            "batch": batch,
        }
        save_job_state(state)
        print(f"[ok] created V1.10 batch control job: {JOB_PATH}")
        print(json.dumps(batch, ensure_ascii=False, indent=2))
        return

    state = load_job_state()
    batch_id = state.get("batch", {}).get("id")
    if not batch_id:
        raise ValueError(f"No batch id found in {JOB_PATH}; run submit first.")

    if MODE == "status":
        state["batch"] = retrieve_batch(batch_id)
        save_job_state(state)
        print(f"[ok] updated V1.10 batch status: {JOB_PATH}")
        print(json.dumps(state["batch"], ensure_ascii=False, indent=2))
        return

    state["batch"] = retrieve_batch(batch_id)
    save_job_state(state)
    if state["batch"].get("status") != "completed":
        raise ValueError(f"Batch status is {state['batch'].get('status')!r}; fetch requires completed.")
    materialize(records)


if __name__ == "__main__":
    main()
