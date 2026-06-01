#!/usr/bin/env python3

import json
import os

from dotenv import load_dotenv
from openai import OpenAI

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
from models.review_labels_flat import FlatExtraction, FlatReviewAnalysisRecord, FlatReviewMetadata
from prompt_flat_v1 import SYSTEM_PROMPT_V1, build_prompt_v1


load_dotenv()
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
if not OPENAI_API_KEY:
    raise ValueError("No OpenAI API key found in .env")

client = OpenAI(api_key=OPENAI_API_KEY)

OUT_PATH = os.getenv(
    "REVIEW_LABELS_OUT_PATH",
    "analysis/llm/benchmark_comparison/reviews_v1_9_120_labeled.json",
)
MODEL = os.getenv("REVIEW_LABELS_MODEL", "gpt-4.1-mini-2025-04-14")
START_INDEX = int(os.getenv("REVIEW_LABELS_START_INDEX", "0"))
NUM_REVIEWS = int(os.getenv("REVIEW_LABELS_NUM_REVIEWS", "1000"))
SAMPLE_PATH = os.getenv(
    "REVIEW_LABELS_SAMPLE_PATH",
    "analysis/llm/samples/review_labels_benchmark_ids_120.txt",
)
TEMPERATURE = float(os.getenv("REVIEW_LABELS_TEMPERATURE", "0"))


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


def extract_json_content(response) -> dict:
    message = response.choices[0].message
    content = getattr(message, "content", None)
    if isinstance(content, str):
        return json.loads(content)

    if isinstance(content, list):
        text_parts = []
        for item in content:
            if isinstance(item, dict):
                text = item.get("text")
                if isinstance(text, str):
                    text_parts.append(text)
            else:
                text = getattr(item, "text", None)
                if isinstance(text, str):
                    text_parts.append(text)
        if text_parts:
            return json.loads("".join(text_parts))

    parsed = getattr(message, "parsed", None)
    if isinstance(parsed, dict):
        return parsed
    if hasattr(parsed, "model_dump"):
        return parsed.model_dump()

    raise ValueError("Unable to extract JSON content from chat completion response.")


def main() -> None:
    records = load_review_records(SAMPLE_PATH, START_INDEX, NUM_REVIEWS)
    results, previous_meta = load_existing_results(OUT_PATH)

    run_meta = init_run_meta(
        provider="openai",
        model=MODEL,
        sample_path=SAMPLE_PATH,
        temperature=TEMPERATURE,
        extra={"prompt_version": "v1", "runner": "analyze_llm_flat_v1_9_gpt.py"},
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
            response = client.chat.completions.create(
                model=MODEL,
                temperature=TEMPERATURE,
                response_format=review_schema(),
                messages=[
                    {"role": "system", "content": SYSTEM_PROMPT_V1},
                    {"role": "user", "content": prompt},
                ],
            )
            payload = extract_json_content(response)
            extraction = FlatExtraction(**payload)
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
        model=MODEL,
        out_path=OUT_PATH,
    )


if __name__ == "__main__":
    main()
