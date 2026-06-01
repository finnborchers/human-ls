#!/usr/bin/env python3

import json
import os
import random
import re
from collections import Counter, defaultdict
from datetime import datetime, timezone


ARTIFACTS_ROOT = "artifacts"
SAMPLES_DIR = "analysis/llm/samples"
BENCHMARK_DIR = "analysis/llm/benchmark"
SEED = 20260513

IDS_PATH = os.path.join(SAMPLES_DIR, "review_labels_benchmark_ids_120.txt")
NOTES_PATH = os.path.join(BENCHMARK_DIR, "benchmark_v1_120_sampling_notes.txt")
PRELABELS_PATH = os.path.join(BENCHMARK_DIR, "benchmark_v1_120_prelabeled.json")
BENCHMARK_PATH = os.path.join(BENCHMARK_DIR, "benchmark_v1_120_labled.json")

MIXED_MARKERS = re.compile(r"\b(aber|jedoch|trotzdem|eigentlich|wobei)\b", re.IGNORECASE)
TOPIC_HINTS = re.compile(
    r"\b(datenschutz|privat|sprache|deutsch|rass|diskrimin|hygien|sauber|warte|termin|behandlung|diagnose|kommunik|"
    r"aufklärung|entlass|nachsorge|koordination|schmerz|respekt|unfreund|ignoriert|ernst)\w*\b",
    re.IGNORECASE,
)


def load_records() -> list[dict]:
    records = []
    for place_id in sorted(os.listdir(ARTIFACTS_ROOT)):
        reviews_path = os.path.join(ARTIFACTS_ROOT, place_id, "reviews.json")
        if not os.path.exists(reviews_path):
            continue

        try:
            with open(reviews_path, "r", encoding="utf-8") as f:
                reviews = json.load(f)
        except json.JSONDecodeError:
            continue

        for review_index, review in enumerate(reviews):
            review_text = (review.get("review_text") or "").strip()
            if not review_text:
                continue

            star_rating = review.get("star_rating")
            like_count = review.get("like_count") or 0
            has_owner_response = bool(review.get("has_owner_response"))
            records.append(
                {
                    "review_id": f"{place_id}:{review_index}",
                    "bucket": None,
                    "place_id": place_id,
                    "review_index": review_index,
                    "metadata": {
                        "place_id": place_id,
                        "clinic_name": None,
                        "star_rating": star_rating,
                        "review_time": review.get("review_time"),
                        "like_count": like_count,
                        "has_owner_response": has_owner_response,
                    },
                    "review_text": review_text,
                    "text_length": len(review_text),
                    "star_rating": star_rating,
                    "like_bin": "likes" if like_count > 0 else "no_likes",
                    "owner_bin": "owner_response" if has_owner_response else "no_owner_response",
                }
            )
    return records


def score_mixed(record: dict) -> tuple[int, int, int]:
    text = record["review_text"]
    score = 0
    if record["star_rating"] == 3:
        score += 3
    score += 2 * len(MIXED_MARKERS.findall(text))
    if TOPIC_HINTS.search(text):
        score += 1
    if record["text_length"] >= 350:
        score += 1
    if record["like_bin"] == "likes":
        score += 1
    return score, record["text_length"], record["like_bin"] == "likes"


def choose_bucket(
    candidates: list[dict],
    n: int,
    rng: random.Random,
    place_cap: int,
    diversify_fields: tuple[str, ...],
    scored: bool = False,
) -> list[dict]:
    by_place = Counter()
    chosen = []
    target_mix = defaultdict(lambda: max(1, n // 4))
    seen_mix = Counter()

    pool = candidates[:]
    if scored:
        pool.sort(key=score_mixed, reverse=True)
        head = pool[: min(len(pool), n * 4)]
        rng.shuffle(head)
        tail = pool[min(len(pool), n * 4) :]
        pool = head + tail
    else:
        rng.shuffle(pool)

    for row in pool:
        place_id = row["place_id"]
        if by_place[place_id] >= place_cap:
            continue

        mix_key = tuple(row[field] for field in diversify_fields)
        if seen_mix[mix_key] >= target_mix[mix_key]:
            continue

        chosen.append(row)
        by_place[place_id] += 1
        seen_mix[mix_key] += 1

        if len(chosen) == n:
            return chosen

    for row in pool:
        if row in chosen:
            continue
        place_id = row["place_id"]
        if by_place[place_id] >= place_cap:
            continue
        chosen.append(row)
        by_place[place_id] += 1
        if len(chosen) == n:
            return chosen

    raise RuntimeError(f"Could not sample {n} items for bucket.")


def build_samples(records: list[dict]) -> list[dict]:
    rng = random.Random(SEED)

    negative_candidates = [
        row
        for row in records
        if row["star_rating"] in {1, 2} and row["text_length"] >= 120
    ]
    positive_candidates = [
        row
        for row in records
        if row["star_rating"] in {4, 5} and row["text_length"] >= 120
    ]
    mixed_candidates = [
        row
        for row in records
        if (
            row["star_rating"] == 3
            or MIXED_MARKERS.search(row["review_text"])
            or (row["text_length"] >= 350 and TOPIC_HINTS.search(row["review_text"]))
        )
    ]

    negative = choose_bucket(
        negative_candidates,
        n=40,
        rng=rng,
        place_cap=2,
        diversify_fields=("like_bin", "owner_bin"),
    )
    negative_ids = {row["review_id"] for row in negative}

    positive = choose_bucket(
        [row for row in positive_candidates if row["review_id"] not in negative_ids],
        n=40,
        rng=rng,
        place_cap=2,
        diversify_fields=("like_bin", "owner_bin"),
    )
    used_ids = negative_ids | {row["review_id"] for row in positive}

    mixed = choose_bucket(
        [row for row in mixed_candidates if row["review_id"] not in used_ids],
        n=40,
        rng=rng,
        place_cap=2,
        diversify_fields=("like_bin", "owner_bin"),
        scored=True,
    )

    for row in negative:
        row["bucket"] = "negative"
    for row in positive:
        row["bucket"] = "positive"
    for row in mixed:
        row["bucket"] = "mixed_hard"

    return sorted(negative + positive + mixed, key=lambda row: (row["bucket"], row["place_id"], row["review_index"]))


def write_ids_file(sample_rows: list[dict]) -> None:
    os.makedirs(SAMPLES_DIR, exist_ok=True)
    with open(IDS_PATH, "w", encoding="utf-8") as f:
        for row in sample_rows:
            f.write(f"{row['review_id']}\n")


def write_notes(sample_rows: list[dict]) -> None:
    os.makedirs(BENCHMARK_DIR, exist_ok=True)
    bucket_counter = Counter(row["bucket"] for row in sample_rows)
    place_counter = Counter(row["place_id"] for row in sample_rows)
    with open(NOTES_PATH, "w", encoding="utf-8") as f:
        f.write("Benchmark sampling notes\n")
        f.write(f"seed: {SEED}\n")
        f.write(f"created_at: {datetime.now(timezone.utc).isoformat()}\n")
        f.write(f"bucket_counts: {dict(bucket_counter)}\n")
        f.write(f"unique_places: {len(place_counter)}\n")
        f.write(f"max_reviews_per_place: {max(place_counter.values())}\n")
        f.write("\nTop places in sample:\n")
        for place_id, count in place_counter.most_common(20):
            f.write(f"- {place_id}: {count}\n")


def build_benchmark_records(sample_rows: list[dict], prelabels: dict) -> dict:
    created_at = datetime.now(timezone.utc).isoformat()
    records = {}
    for row in sample_rows:
        review_id = row["review_id"]
        pre = prelabels.get(review_id)
        if not pre:
            raise KeyError(f"Missing prelabels for {review_id}")

        model_prelabels = pre["labels"]
        records[review_id] = {
            "review_id": review_id,
            "bucket": row["bucket"],
            "metadata": row["metadata"],
            "review_text": row["review_text"],
            "model_prelabels": model_prelabels,
            "benchmark_labels": {
                "problem_labels": list(model_prelabels["problem_labels"]),
                "strength_labels": list(model_prelabels["strength_labels"]),
            },
            "benchmark_notes": "",
            "benchmark_status": "prelabeled",
        }

    return {
        "benchmark_name": "benchmark_v1_120",
        "created_at": created_at,
        "source_model": "gpt-4.1-mini",
        "prompt_version": "flat_v1",
        "sampling_seed": SEED,
        "records": records,
    }


def main() -> None:
    os.makedirs(BENCHMARK_DIR, exist_ok=True)

    records = load_records()
    sample_rows = build_samples(records)
    write_ids_file(sample_rows)
    write_notes(sample_rows)

    print(f"[ok] wrote ids file: {IDS_PATH}")
    print(f"[ok] wrote notes file: {NOTES_PATH}")
    print(f"[info] bucket counts: {Counter(row['bucket'] for row in sample_rows)}")
    print(f"[info] unique places: {len({row['place_id'] for row in sample_rows})}")

    if not os.path.exists(PRELABELS_PATH):
        print(f"[next] run V1 prelabeling and write to: {PRELABELS_PATH}")
        return

    with open(PRELABELS_PATH, "r", encoding="utf-8") as f:
        prelabels = json.load(f)

    benchmark = build_benchmark_records(sample_rows, prelabels)
    with open(BENCHMARK_PATH, "w", encoding="utf-8") as f:
        json.dump(benchmark, f, ensure_ascii=False, indent=2)

    print(f"[ok] wrote benchmark file: {BENCHMARK_PATH}")


if __name__ == "__main__":
    main()
