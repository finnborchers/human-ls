#!/usr/bin/env python3

import json
import os
import time

from dotenv import load_dotenv
from google import genai
from models.review_labels_flat import FlatExtraction, FlatReviewAnalysisRecord, FlatReviewMetadata
from scripts.prompt_flat_v2 import build_prompt_v2


load_dotenv()
load_dotenv("scripts/.env")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")
if not GEMINI_API_KEY:
    raise ValueError("No Gemini API key found in GEMINI_API_KEY or GOOGLE_API_KEY.")

client = genai.Client(api_key=GEMINI_API_KEY)

ARTIFACTS_ROOT = "artifacts"
OUT_PATH = os.getenv(
    "REVIEW_LABELS_OUT_PATH",
    "analysis/llm/model_comparison/review_labels_gemini25flashlite_flat_12sample.json",
)
MODEL = os.getenv("GEMINI_MODEL", "gemini-2.5-flash-lite")
START_INDEX = int(os.getenv("REVIEW_LABELS_START_INDEX", "0"))
NUM_REVIEWS = int(os.getenv("REVIEW_LABELS_NUM_REVIEWS", "20"))
SAMPLE_PATH = os.getenv("REVIEW_LABELS_SAMPLE_PATH")

os.makedirs(os.path.dirname(OUT_PATH), exist_ok=True)


records = []
for place_id in sorted(os.listdir(ARTIFACTS_ROOT)):
    reviews_path = os.path.join(ARTIFACTS_ROOT, place_id, "reviews.json")
    if not os.path.exists(reviews_path):
        continue

    try:
        with open(reviews_path, "r", encoding="utf-8") as f:
            reviews = json.load(f)
    except json.JSONDecodeError as e:
        print(f"[warn] skipping unreadable file, probably still being written: {reviews_path} ({e})")
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

if SAMPLE_PATH:
    with open(SAMPLE_PATH, "r", encoding="utf-8") as f:
        sample_ids = {line.strip() for line in f if line.strip()}

    records = [row for row in records if row["review_id"] in sample_ids]

records = records[START_INDEX : START_INDEX + NUM_REVIEWS]


if os.path.exists(OUT_PATH):
    with open(OUT_PATH, "r", encoding="utf-8") as f:
        results = json.load(f)
else:
    results = {}


t_total_start = time.time()
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

    meta = {
        "place_id": row.get("place_id"),
        "clinic_name": row.get("clinic_name"),
        "star_rating": row.get("star_rating"),
        "review_time": row.get("review_time"),
        "like_count": row.get("like_count"),
        "has_owner_response": row.get("has_owner_response"),
    }

    prompt = build_prompt_v2(review_text)

    try:
        t_req_start = time.time()
        response = client.models.generate_content(
            model=MODEL,
            contents=prompt,
            config={
                "response_mime_type": "application/json",
                "response_json_schema": FlatExtraction.model_json_schema(),
            },
        )
        t_req = time.time() - t_req_start

        if not response.text:
            raise ValueError("Gemini returned an empty response.")

        extraction = FlatExtraction.model_validate_json(response.text)

        record = FlatReviewAnalysisRecord(
            review_id=review_id,
            review_index=row["review_index"],
            metadata=FlatReviewMetadata(**meta),
            review_text=review_text,
            labels=extraction,
        )
        results[review_id] = record.model_dump()

        with open(OUT_PATH, "w", encoding="utf-8") as f:
            json.dump(results, f, ensure_ascii=False, indent=2)

        processed += 1
        total_request_sec += t_req
        print(f"[ok] review_id={review_id} | {t_req:.2f}s")

    except Exception as e:
        errors += 1
        print(f"[error] review_id={review_id}: {e}")


t_total = time.time() - t_total_start
avg_per_review = (total_request_sec / processed) if processed > 0 else 0.0
per_min = (60.0 / avg_per_review) if avg_per_review > 0 else 0.0

print("\n=== SUMMARY ===")
print(f"Processed: {processed}")
print(f"Skipped:   {skipped}")
print(f"Errors:    {errors}")
print(f"Total wall-clock: {t_total:.2f}s")
print(f"Avg request time/review: {avg_per_review:.2f}s")
print(f"Throughput: ~{per_min:.1f} reviews/min (model time)")
print(f"Output: {OUT_PATH}")
