#!/usr/bin/env python3

import json
import os
import time
from datetime import datetime, timezone
from pathlib import Path

from dotenv import load_dotenv
from google import genai
from google.genai import types
from models.review_labels_flat import FlatExtraction, FlatReviewAnalysisRecord, FlatReviewMetadata
from prompt_flat_v1 import SYSTEM_PROMPT_V1, build_prompt_v1

from benchmark_runner_utils import (
    assess_run_completeness,
    build_meta,
    finalize_run_meta,
    init_run_meta,
    load_existing_results,
    load_json_file,
    load_review_records,
    load_sample_ids,
    now_monotonic,
    summarize_run,
    write_json_file,
    write_results,
)


load_dotenv()
load_dotenv("scripts/.env")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")
if not GEMINI_API_KEY:
    raise ValueError("No Gemini API key found in GEMINI_API_KEY or GOOGLE_API_KEY.")

client = genai.Client(api_key=GEMINI_API_KEY)

OUT_PATH = os.getenv(
    "REVIEW_LABELS_OUT_PATH",
    "analysis/llm/benchmark_comparison/reviews_model_sweep_gemini_holdout20_labeled.json",
)
MODEL = os.getenv("GEMINI_MODEL", os.getenv("REVIEW_LABELS_MODEL", "gemini-2.5-flash"))
START_INDEX = int(os.getenv("REVIEW_LABELS_START_INDEX", "0"))
NUM_REVIEWS = int(os.getenv("REVIEW_LABELS_NUM_REVIEWS", "1000"))
SAMPLE_PATH = os.getenv(
    "REVIEW_LABELS_SAMPLE_PATH",
    "analysis/llm/finetune/reviews_v1_7_holdout_ids_20.txt",
)
THINKING_BUDGET = os.getenv("GEMINI_THINKING_BUDGET")
MAX_RETRIES = int(os.getenv("GEMINI_MAX_RETRIES", "3"))
BACKOFF_SECONDS = [2, 5, 10]
FAILURE_LOG_PATH = os.getenv(
    "REVIEW_LABELS_FAILURE_LOG_PATH",
    str(Path(OUT_PATH).with_name(f"{Path(OUT_PATH).stem}_failures.json")),
)


records = load_review_records(SAMPLE_PATH, START_INDEX, NUM_REVIEWS)
results, previous_meta = load_existing_results(OUT_PATH)
expected_ids = load_sample_ids(SAMPLE_PATH)
failure_log = load_json_file(FAILURE_LOG_PATH, {"run_meta": {}, "failures": {}})
failures = failure_log.get("failures", {})

extra_meta = {"prompt_version": "v1", "runner": "analyze_llm_flat_v1_sweep_gemini.py"}
if THINKING_BUDGET is not None:
    extra_meta["thinking_budget"] = int(THINKING_BUDGET)

run_meta = init_run_meta(
    provider="gemini",
    model=MODEL,
    sample_path=SAMPLE_PATH,
    extra=extra_meta,
)
if previous_meta:
    run_meta = {**previous_meta, **run_meta}


def refresh_run_meta(*, processed: int, skipped: int, errors: int, total_request_sec: float) -> dict:
    meta = finalize_run_meta(
        run_meta,
        processed=processed,
        skipped=skipped,
        errors=errors,
        total_request_sec=total_request_sec,
    )
    completeness = assess_run_completeness(results, expected_ids)
    meta.update(
        {
            "expected_count": completeness["expected_count"],
            "completed_count": completeness["completed_count"],
            "failed_count": completeness["failed_count"],
            "is_complete": completeness["is_complete"],
        }
    )
    return meta


def write_failure_log(meta: dict) -> None:
    write_json_file(
        FAILURE_LOG_PATH,
        {
            "run_meta": meta,
            "failures": failures,
        },
    )


t_total_start = now_monotonic()
processed = 0
total_request_sec = 0.0
skipped = 0
errors = 0

for row in records:
    review_id = row["review_id"]
    if review_id in results:
        skipped += 1
        print(f"[skip] review_id={review_id} already done.")
        continue

    review_text = row.get("review_text", "")
    if not review_text.strip():
        skipped += 1
        print(f"[skip] review_id={review_id} has empty text.")
        continue

    meta = build_meta(row)
    prompt = build_prompt_v1(review_text, json.dumps(meta, ensure_ascii=False, indent=2))

    try:
        config_kwargs = {
            "system_instruction": SYSTEM_PROMPT_V1,
            "response_mime_type": "application/json",
            "response_json_schema": FlatExtraction.model_json_schema(),
        }
        if THINKING_BUDGET is not None:
            config_kwargs["thinking_config"] = types.ThinkingConfig(
                thinking_budget=int(THINKING_BUDGET)
            )

        last_error = None
        extraction = None
        t_req = 0.0

        for attempt in range(1, MAX_RETRIES + 1):
            t_req_start = now_monotonic()
            try:
                response = client.models.generate_content(
                    model=MODEL,
                    contents=prompt,
                    config=types.GenerateContentConfig(**config_kwargs),
                )
                t_req = now_monotonic() - t_req_start

                if not response.text:
                    raise ValueError("Gemini returned an empty response.")

                extraction = FlatExtraction.model_validate_json(response.text)

                if review_id in failures:
                    del failures[review_id]
                break
            except Exception as e:
                t_req = now_monotonic() - t_req_start
                last_error = e
                failures[review_id] = {
                    "review_id": review_id,
                    "model": MODEL,
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                    "attempt_number": attempt,
                    "exception": str(e),
                }
                current_meta = refresh_run_meta(
                    processed=processed,
                    skipped=skipped,
                    errors=errors + 1,
                    total_request_sec=total_request_sec,
                )
                write_failure_log(current_meta)

                if attempt >= MAX_RETRIES:
                    raise

                backoff_sec = BACKOFF_SECONDS[min(attempt - 1, len(BACKOFF_SECONDS) - 1)]
                print(
                    f"[warn] review_id={review_id} attempt={attempt} failed; retrying in {backoff_sec}s"
                )
                time.sleep(backoff_sec)

        if extraction is None:
            raise last_error or RuntimeError("Gemini extraction failed without a captured exception.")

        record = FlatReviewAnalysisRecord(
            review_id=review_id,
            review_index=row["review_index"],
            metadata=FlatReviewMetadata(**meta),
            review_text=review_text,
            labels=extraction,
        )
        record_payload = record.model_dump()
        record_payload["request_duration_sec"] = round(t_req, 4)
        record_payload["model_name"] = MODEL
        if THINKING_BUDGET is not None:
            record_payload["thinking_budget"] = int(THINKING_BUDGET)

        results[review_id] = record_payload

        current_meta = refresh_run_meta(
            processed=processed + 1,
            skipped=skipped,
            errors=errors,
            total_request_sec=total_request_sec + t_req,
        )
        write_results(OUT_PATH, results, current_meta)
        write_failure_log(current_meta)

        processed += 1
        total_request_sec += t_req
        print(f"[ok] review_id={review_id} | {t_req:.2f}s")

    except Exception as e:
        errors += 1
        current_meta = refresh_run_meta(
            processed=processed,
            skipped=skipped,
            errors=errors,
            total_request_sec=total_request_sec,
        )
        write_results(OUT_PATH, results, current_meta)
        write_failure_log(current_meta)
        print(f"[error] review_id={review_id}: {e}")


t_total = now_monotonic() - t_total_start
final_meta = refresh_run_meta(
    processed=processed,
    skipped=skipped,
    errors=errors,
    total_request_sec=total_request_sec,
)
write_results(OUT_PATH, results, final_meta)
write_failure_log(final_meta)
summarize_run(
    processed=processed,
    skipped=skipped,
    errors=errors,
    total_wall_sec=t_total,
    total_request_sec=total_request_sec,
    model=MODEL,
    out_path=OUT_PATH,
)
