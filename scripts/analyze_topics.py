#!/usr/bin/env python3

import csv
import json
import os

os.environ.setdefault("NUMBA_CACHE_DIR", "/tmp/human-ls-numba-cache")

from bertopic import BERTopic
from bertopic.representation import KeyBERTInspired
from bertopic.vectorizers import ClassTfidfTransformer
from hdbscan import HDBSCAN
from sklearn.feature_extraction.text import CountVectorizer
from umap import UMAP


# ========== Setup ==========
ARTIFACTS_ROOT = "artifacts"
OUT_DIR = os.getenv("TOPICS_OUT_DIR", "analysis/topics")
EMBEDDING_MODEL = "paraphrase-multilingual-MiniLM-L12-v2"
MIN_TOPIC_SIZE = 35
MIN_SAMPLES = 5
TOP_N_WORDS = 12
MAX_REVIEWS_PER_SUBSET = int(os.getenv("MAX_REVIEWS_PER_SUBSET", "0")) or None
HIGH_LIKE_MIN_COUNT = 3

SUBSETS = ["negative_reviews", "positive_reviews", "liked_reviews", "high_liked_reviews"]

os.makedirs(OUT_DIR, exist_ok=True)


# ========== Load Reviews ==========
records = []

for place_id in sorted(os.listdir(ARTIFACTS_ROOT)):
    reviews_path = os.path.join(ARTIFACTS_ROOT, place_id, "reviews.json")
    if not os.path.exists(reviews_path):
        continue

    with open(reviews_path, "r", encoding="utf-8") as f:
        reviews = json.load(f)

    for review_index, review in enumerate(reviews):
        review_text = review.get("review_text", "")
        if not review_text.strip():
            continue

        records.append(
            {
                "review_id": f"{place_id}:{review_index}",
                "place_id": place_id,
                "review_index": review_index,
                "review_text": review_text,
                "star_rating": review.get("star_rating"),
                "like_count": review.get("like_count") or 0,
            }
        )


# ========== Define Subsets ==========
subsets = {
    "all": records,
    "negative_reviews": [r for r in records if r.get("star_rating") in [1, 2]],
    "positive_reviews": [r for r in records if r.get("star_rating") in [4, 5]],
    "liked_reviews": [r for r in records if (r.get("like_count") or 0) > 0],
    "high_liked_reviews": [r for r in records if (r.get("like_count") or 0) >= HIGH_LIKE_MIN_COUNT],
}


# ========== Helpers ==========
def write_csv(path: str, rows: list[dict]) -> None:
    if not rows:
        return

    fieldnames = sorted({key for row in rows for key in row.keys()})
    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def run_bertopic(subset_name: str, subset_records: list[dict]) -> dict:
    if MAX_REVIEWS_PER_SUBSET is not None:
        subset_records = subset_records[:MAX_REVIEWS_PER_SUBSET]

    docs = [r["review_text"] for r in subset_records]

    umap_model = UMAP(
        n_neighbors=15,
        n_components=5,
        min_dist=0.0,
        metric="cosine",
        random_state=42,
    )
    hdbscan_model = HDBSCAN(
        min_cluster_size=MIN_TOPIC_SIZE,
        min_samples=MIN_SAMPLES,
        metric="euclidean",
        prediction_data=True,
    )
    vectorizer_model = CountVectorizer(
        ngram_range=(1, 2),
        min_df=1,
        max_df=0.5,
    )
    ctfidf_model = ClassTfidfTransformer(reduce_frequent_words=True)
    representation_model = KeyBERTInspired()

    model = BERTopic(
        embedding_model=EMBEDDING_MODEL,
        umap_model=umap_model,
        hdbscan_model=hdbscan_model,
        vectorizer_model=vectorizer_model,
        ctfidf_model=ctfidf_model,
        representation_model=representation_model,
        min_topic_size=MIN_TOPIC_SIZE,
        top_n_words=TOP_N_WORDS,
        calculate_probabilities=False,
        verbose=True,
    )

    topic_ids, _ = model.fit_transform(docs)
    topic_info = model.get_topic_info().to_dict("records")

    assignments = []
    examples = {}

    for record, topic_id in zip(subset_records, topic_ids):
        topic_id = int(topic_id)
        assignments.append(
            {
                "review_id": record["review_id"],
                "place_id": record["place_id"],
                "review_index": record["review_index"],
                "star_rating": record["star_rating"],
                "like_count": record["like_count"],
                "topic_id": topic_id,
            }
        )

        if topic_id not in examples:
            examples[topic_id] = []
        if len(examples[topic_id]) < 3:
            examples[topic_id].append(record["review_text"][:250])

    topic_rows = []
    for topic in topic_info:
        topic_id = int(topic["Topic"])
        words = model.get_topic(topic_id) or []
        topic_rows.append(
            {
                "topic_id": topic_id,
                "count": topic["Count"],
                "name": topic["Name"],
                "top_terms": ", ".join(word for word, _ in words),
                "example_snippets": " || ".join(examples.get(topic_id, [])),
            }
        )

    write_csv(os.path.join(OUT_DIR, f"{subset_name}_topics.csv"), topic_rows)
    write_csv(os.path.join(OUT_DIR, f"{subset_name}_assignments.csv"), assignments)

    return {
        "subset": subset_name,
        "review_count": len(subset_records),
        "topic_count": len(topic_rows),
    }


# ========== Run ==========
summaries = []

print(f"[load] reviews={len(records)}")

for subset_name in SUBSETS:
    print(f"[topic] subset={subset_name}")
    summary = run_bertopic(subset_name, subsets[subset_name])
    summaries.append(summary)
    print(f"[done] {summary}")

with open(os.path.join(OUT_DIR, "topic_model_summary.json"), "w", encoding="utf-8") as f:
    json.dump(
        {
            "review_count": len(records),
            "embedding_model": EMBEDDING_MODEL,
            "min_topic_size": MIN_TOPIC_SIZE,
            "min_samples": MIN_SAMPLES,
            "top_n_words": TOP_N_WORDS,
            "high_like_min_count": HIGH_LIKE_MIN_COUNT,
            "summaries": summaries,
        },
        f,
        ensure_ascii=False,
        indent=2,
    )

print(f"[done] Output: {OUT_DIR}")
