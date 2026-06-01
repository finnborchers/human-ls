#!/usr/bin/env python3

import json
import os
from datetime import datetime, timezone
from pathlib import Path

from dotenv import load_dotenv
from openai import OpenAI

from benchmark_runner_utils import build_meta, load_review_records
from models.review_labels_flat import FlatExtraction, FlatReviewAnalysisRecord, FlatReviewMetadata


load_dotenv()
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
if not OPENAI_API_KEY:
    raise ValueError("No OpenAI API key found in .env")

client = OpenAI(api_key=OPENAI_API_KEY)

OUT_DIR = Path(os.getenv("FULLRUN_OUT_DIR", "analysis/llm/full_run/v1_batch_run"))
MANIFEST_PATH = OUT_DIR / "manifest.json"
MODE = os.getenv("FULLRUN_MODE", "status")
SCOPE = os.getenv("FULLRUN_SCOPE", "10000_ids")
SUBMIT_LIMIT = int(os.getenv("FULLRUN_SUBMIT_LIMIT", "1"))
RESUBMIT_FAILED = os.getenv("FULLRUN_RESUBMIT_FAILED", "0") == "1"


def to_plain(obj):
    if hasattr(obj, "model_dump"):
        return obj.model_dump()
    if hasattr(obj, "to_dict"):
        return obj.to_dict()
    raise TypeError(f"Unsupported object type for serialization: {type(obj)!r}")


def load_manifest() -> dict:
    with MANIFEST_PATH.open("r", encoding="utf-8") as f:
        return json.load(f)


def write_json(path: str | Path, payload: dict) -> None:
    file_path = Path(path)
    file_path.parent.mkdir(parents=True, exist_ok=True)
    with file_path.open("w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)


def load_json(path: str | Path, default):
    file_path = Path(path)
    if not file_path.exists():
        return default
    with file_path.open("r", encoding="utf-8") as f:
        return json.load(f)


def upload_batch_input(input_path: Path) -> dict:
    with input_path.open("rb") as f:
        file_obj = client.files.create(file=f, purpose="batch")
    return to_plain(file_obj)


def create_batch(input_file_id: str, scope: str, batch_name: str) -> dict:
    batch = client.batches.create(
        input_file_id=input_file_id,
        endpoint="/v1/chat/completions",
        completion_window="24h",
        metadata={
            "project": "human-ls",
            "experiment": "v1_batch_run",
            "prompt_version": "v1",
            "scope": scope,
            "batch_name": batch_name,
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


def build_record_lookup() -> dict[str, dict]:
    rows = load_review_records(sample_path=None, start_index=0, num_reviews=10**9)
    rows = [row for row in rows if row.get("review_text", "").strip()]
    return {row["review_id"]: row for row in rows}


def parse_jsonl(text: str) -> list[dict]:
    items = []
    for line in text.splitlines():
        if not line.strip():
            continue
        items.append(json.loads(line))
    return items


def materialize_batch(batch_info: dict, record_lookup: dict) -> dict:
    job_state = load_json(batch_info["job_path"], {})
    batch_state = job_state.get("batch") or {}
    output_file_id = batch_state.get("output_file_id")
    error_file_id = batch_state.get("error_file_id")
    if not output_file_id:
        raise ValueError(f"No output_file_id for batch {batch_info['batch_name']}")

    raw_output_text = file_text(output_file_id)
    Path(batch_info["raw_output_path"]).write_text(raw_output_text, encoding="utf-8")

    raw_error_text = ""
    if error_file_id:
        raw_error_text = file_text(error_file_id)
        Path(batch_info["raw_error_path"]).write_text(raw_error_text, encoding="utf-8")

    output_lines = parse_jsonl(raw_output_text)
    normalized = {}
    parse_errors = []

    for item in output_lines:
        custom_id = item.get("custom_id")
        error = item.get("error")
        response = item.get("response") or {}
        status_code = response.get("status_code")
        if error or status_code != 200:
            parse_errors.append(
                {
                    "custom_id": custom_id,
                    "status_code": status_code,
                    "error": error,
                }
            )
            continue

        body = response.get("body") or {}
        choices = body.get("choices") or []
        if not choices:
            parse_errors.append({"custom_id": custom_id, "status_code": status_code, "error": "missing_choices"})
            continue

        content = choices[0].get("message", {}).get("content")
        if not isinstance(content, str):
            parse_errors.append({"custom_id": custom_id, "status_code": status_code, "error": "missing_content"})
            continue

        try:
            payload = json.loads(content)
            extraction = FlatExtraction(**payload)
        except Exception as exc:
            parse_errors.append({"custom_id": custom_id, "status_code": status_code, "error": str(exc)})
            continue

        row = record_lookup.get(custom_id)
        if row is None:
            parse_errors.append({"custom_id": custom_id, "status_code": status_code, "error": "unknown_review_id"})
            continue

        meta = build_meta(row)
        record = FlatReviewAnalysisRecord(
            review_id=custom_id,
            review_index=row["review_index"],
            metadata=FlatReviewMetadata(**meta),
            review_text=row["review_text"],
            labels=extraction,
        )
        normalized[custom_id] = record.model_dump()

    payload = {
        "run_meta": {
            "provider": "openai",
            "runner": "run_openai_batch_v1.py",
            "scope": SCOPE,
            "batch_name": batch_info["batch_name"],
            "model": job_state.get("model"),
            "batch_id": batch_state.get("id"),
            "completed_at": datetime.now(timezone.utc).isoformat(),
            "output_file_id": output_file_id,
            "error_file_id": error_file_id,
            "materialized_records": len(normalized),
            "parse_errors": len(parse_errors),
        },
        "records": normalized,
        "errors": parse_errors,
    }
    write_json(batch_info["normalized_path"], payload)
    return payload


def submit_scope(scope_config: dict) -> None:
    submitted_now = 0
    for batch_info in scope_config["batches"]:
        if submitted_now >= SUBMIT_LIMIT:
            break

        job_path = Path(batch_info["job_path"])
        existing = load_json(job_path, {})
        existing_batch = existing.get("batch", {})
        existing_status = existing_batch.get("status")
        existing_errors = (existing_batch.get("errors") or {}).get("data") or []
        failed_due_to_queue = any(
            item.get("code") == "token_limit_exceeded" for item in existing_errors if isinstance(item, dict)
        )

        if existing_batch.get("id") and not (
            RESUBMIT_FAILED and existing_status == "failed" and failed_due_to_queue
        ):
            print(f"[skip] {batch_info['batch_name']} already submitted (status={existing_status}).")
            continue

        uploaded = upload_batch_input(Path(batch_info["input_path"]))
        batch = create_batch(uploaded["id"], scope_config["scope"], batch_info["batch_name"])
        state = {
            "scope": scope_config["scope"],
            "batch_name": batch_info["batch_name"],
            "model": load_manifest()["model"],
            "input_path": batch_info["input_path"],
            "sample_path": batch_info["sample_path"],
            "review_count": batch_info["review_count"],
            "uploaded_input_file": uploaded,
            "batch": batch,
            "saved_at": datetime.now(timezone.utc).isoformat(),
        }
        write_json(job_path, state)
        print(f"[ok] submitted {batch_info['batch_name']} -> {job_path}")
        submitted_now += 1


def status_scope(scope_config: dict) -> None:
    for batch_info in scope_config["batches"]:
        job_path = Path(batch_info["job_path"])
        state = load_json(job_path, {})
        batch_id = state.get("batch", {}).get("id")
        if not batch_id:
            print(f"[skip] {batch_info['batch_name']} not submitted yet.")
            continue
        state["batch"] = retrieve_batch(batch_id)
        state["saved_at"] = datetime.now(timezone.utc).isoformat()
        write_json(job_path, state)
        error_data = (state["batch"].get("errors") or {}).get("data") or []
        error_suffix = ""
        if error_data:
            first_error = error_data[0]
            error_suffix = f" error={first_error.get('code')}"
        print(
            f"[ok] {batch_info['batch_name']} status={state['batch'].get('status')} "
            f"completed={state['batch'].get('request_counts', {}).get('completed')} "
            f"failed={state['batch'].get('request_counts', {}).get('failed')}"
            f"{error_suffix}"
        )


def fetch_scope(scope_config: dict) -> None:
    record_lookup = build_record_lookup()
    for batch_info in scope_config["batches"]:
        state = load_json(batch_info["job_path"], {})
        batch = state.get("batch") or {}
        status = batch.get("status")
        if status != "completed":
            print(f"[skip] {batch_info['batch_name']} status={status!r}, not ready.")
            continue
        if Path(batch_info["normalized_path"]).exists():
            print(f"[skip] {batch_info['batch_name']} already materialized.")
            continue
        payload = materialize_batch(batch_info, record_lookup)
        print(
            f"[ok] materialized {batch_info['batch_name']} "
            f"records={payload['run_meta']['materialized_records']} parse_errors={payload['run_meta']['parse_errors']}"
        )


def main() -> None:
    if MODE not in {"submit", "status", "fetch"}:
        raise ValueError("FULLRUN_MODE must be one of: submit, status, fetch")

    manifest = load_manifest()
    scope_config = manifest.get("scopes", {}).get(SCOPE)
    if not scope_config:
        available = ", ".join(sorted(manifest.get("scopes", {}).keys()))
        raise KeyError(f"Unknown FULLRUN_SCOPE={SCOPE!r}. Available: {available}")

    if MODE == "submit":
        submit_scope(scope_config)
    elif MODE == "status":
        status_scope(scope_config)
    else:
        fetch_scope(scope_config)


if __name__ == "__main__":
    main()
