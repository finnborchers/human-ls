#!/usr/bin/env python3

import json
import os

from dotenv import load_dotenv
from instructor import from_openai
from models.review_labels_flat import FlatExtraction, FlatReviewAnalysisRecord, FlatReviewMetadata
from openai import OpenAI
from prompt_flat_v1 import SYSTEM_PROMPT_V1, build_prompt_v1

from benchmark_runner_utils import (
    build_meta,
    finalize_run_meta,
    init_run_meta,
    load_existing_results,
    load_review_records,
    now_monotonic,
    summarize_run,
    write_results,
)


load_dotenv()
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
if not OPENAI_API_KEY:
    raise ValueError("No OpenAI API key found in .env")

client = from_openai(OpenAI(api_key=OPENAI_API_KEY))

OUT_PATH = os.getenv(
    "REVIEW_LABELS_OUT_PATH",
    "analysis/llm/benchmark_comparison/reviews_model_sweep_openai_holdout20_labeled.json",
)
MODEL = os.getenv("REVIEW_LABELS_MODEL", "gpt-5.4-mini")
REASONING_EFFORT = os.getenv("REVIEW_LABELS_REASONING_EFFORT")
START_INDEX = int(os.getenv("REVIEW_LABELS_START_INDEX", "0"))
NUM_REVIEWS = int(os.getenv("REVIEW_LABELS_NUM_REVIEWS", "1000"))
SAMPLE_PATH = os.getenv(
    "REVIEW_LABELS_SAMPLE_PATH",
    "analysis/llm/finetune/reviews_v1_7_holdout_ids_20.txt",
)
TEMPERATURE_RAW = os.getenv("REVIEW_LABELS_TEMPERATURE")
TEMPERATURE = float(TEMPERATURE_RAW) if TEMPERATURE_RAW not in (None, "") else None


records = load_review_records(SAMPLE_PATH, START_INDEX, NUM_REVIEWS)
results, previous_meta = load_existing_results(OUT_PATH)

run_meta = init_run_meta(
    provider="openai",
    model=MODEL,
    sample_path=SAMPLE_PATH,
    temperature=TEMPERATURE,
    reasoning_effort=REASONING_EFFORT,
    extra={"prompt_version": "v1", "runner": "analyze_llm_flat_v1_sweep_openai.py"},
)
if previous_meta:
    run_meta = {**previous_meta, **run_meta}


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
        t_req_start = now_monotonic()
        request_kwargs = {
            "model": MODEL,
            "response_model": FlatExtraction,
            "messages": [
                {"role": "system", "content": SYSTEM_PROMPT_V1},
                {"role": "user", "content": prompt},
            ],
        }
        if TEMPERATURE is not None:
            request_kwargs["temperature"] = TEMPERATURE
        if REASONING_EFFORT:
            request_kwargs["reasoning_effort"] = REASONING_EFFORT

        try:
            extraction = client.chat.completions.create(**request_kwargs)
        except Exception as e:
            error_text = str(e)
            temperature_unsupported = (
                "Unsupported value: 'temperature'" in error_text
                or '"param": \'temperature\'' in error_text
                or '"param": "temperature"' in error_text
            )
            if TEMPERATURE is not None and temperature_unsupported:
                request_kwargs.pop("temperature", None)
                print(
                    f"[info] review_id={review_id} retrying without explicit temperature for model={MODEL}."
                )
                extraction = client.chat.completions.create(**request_kwargs)
            else:
                raise
        t_req = now_monotonic() - t_req_start

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
        if REASONING_EFFORT:
            record_payload["reasoning_effort"] = REASONING_EFFORT

        results[review_id] = record_payload

        current_meta = finalize_run_meta(
            run_meta,
            processed=processed + 1,
            skipped=skipped,
            errors=errors,
            total_request_sec=total_request_sec + t_req,
        )
        write_results(OUT_PATH, results, current_meta)

        processed += 1
        total_request_sec += t_req
        print(f"[ok] review_id={review_id} | {t_req:.2f}s")

    except Exception as e:
        errors += 1
        current_meta = finalize_run_meta(
            run_meta,
            processed=processed,
            skipped=skipped,
            errors=errors,
            total_request_sec=total_request_sec,
        )
        write_results(OUT_PATH, results, current_meta)
        print(f"[error] review_id={review_id}: {e}")


t_total = now_monotonic() - t_total_start
final_meta = finalize_run_meta(
    run_meta,
    processed=processed,
    skipped=skipped,
    errors=errors,
    total_request_sec=total_request_sec,
)
write_results(OUT_PATH, results, final_meta)
summarize_run(
    processed=processed,
    skipped=skipped,
    errors=errors,
    total_wall_sec=t_total,
    total_request_sec=total_request_sec,
    model=MODEL if not REASONING_EFFORT else f"{MODEL} (reasoning_effort={REASONING_EFFORT})",
    out_path=OUT_PATH,
)
