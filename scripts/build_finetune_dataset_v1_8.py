#!/usr/bin/env python3

import json
import os
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal

from dotenv import load_dotenv
from instructor import from_openai
from openai import OpenAI
from pydantic import BaseModel

from models.review_labels_flat import FlatExtraction
from prompt_flat_v1 import SYSTEM_PROMPT_V1, build_prompt_v1


SOURCE_PATH = Path(
    os.getenv(
        "BENCHMARK_SOURCE_PATH",
        "analysis/llm/benchmark_comparison/benchmark_v1_120_reviewed_2026-05-14T13-43-24Z.json",
    )
)
V1_PREDICTION_PATH = Path(
    os.getenv(
        "V1_PREDICTION_PATH",
        "analysis/llm/benchmark_comparison/reviews_v1_120_labled.json",
    )
)
V17_PREDICTION_PATH = Path(
    os.getenv(
        "V17_PREDICTION_PATH",
        "analysis/llm/benchmark_comparison/reviews_v1_7_120_labeled.json",
    )
)
TRAIN_IDS_PATH = Path(
    os.getenv("FINETUNE_TRAIN_IDS_PATH", "analysis/llm/finetune/reviews_v1_7_train_ids_100.txt")
)
HOLDOUT_IDS_PATH = Path(
    os.getenv("FINETUNE_HOLDOUT_IDS_PATH", "analysis/llm/finetune/reviews_v1_7_holdout_ids_20.txt")
)
HOLDOUT_REFERENCE_PATH = Path(
    os.getenv(
        "FINETUNE_HOLDOUT_REFERENCE_PATH",
        "analysis/llm/finetune/reviews_v1_7_holdout_reference.json",
    )
)
OUT_AUG_DIR = Path(os.getenv("AUGMENTATION_OUT_DIR", "analysis/llm/augmentation"))
OUT_FINETUNE_DIR = Path(os.getenv("FINETUNE_OUT_DIR", "analysis/llm/finetune"))

SOURCE_IDS_PATH = OUT_AUG_DIR / "reviews_v1_8_source_ids_40.txt"
CANDIDATES_PATH = OUT_AUG_DIR / "reviews_v1_8_candidates.json"
AUGMENTED_PATH = OUT_AUG_DIR / "reviews_v1_8_augmented_80.json"
JUDGMENTS_PATH = OUT_AUG_DIR / "reviews_v1_8_judgments.json"
MANIFEST_PATH = OUT_AUG_DIR / "reviews_v1_8_manifest.json"

TRAIN_JSONL_PATH = OUT_FINETUNE_DIR / "reviews_v1_8_train_180.jsonl"
VALID_JSONL_PATH = OUT_FINETUNE_DIR / "reviews_v1_8_valid_20.jsonl"
DATASET_MANIFEST_PATH = OUT_FINETUNE_DIR / "reviews_v1_8_dataset_manifest.json"

PARAPHRASE_MODEL = os.getenv("V18_PARAPHRASE_MODEL", "gpt-5.1")
PARAPHRASE_REASONING_EFFORT = os.getenv("V18_PARAPHRASE_REASONING_EFFORT", "low")
JUDGE_MODEL = os.getenv("V18_JUDGE_MODEL", "gpt-5.1")
JUDGE_REASONING_EFFORT = os.getenv("V18_JUDGE_REASONING_EFFORT", "low")

SELECTED_SOURCE_COUNT = int(os.getenv("V18_SELECTED_SOURCE_COUNT", "40"))
TARGET_ACCEPTED_AUGMENTATIONS = int(os.getenv("V18_TARGET_ACCEPTED_AUGMENTATIONS", "80"))
VARIANTS_PER_REVIEW = int(os.getenv("V18_VARIANTS_PER_REVIEW", "2"))
MAX_ATTEMPTS_PER_SOURCE = int(os.getenv("V18_MAX_ATTEMPTS_PER_SOURCE", "5"))

TARGET_LABELS = {
    "staff.seriousness",
    "access.waiting",
    "care.competence",
    "communication.information",
    "communication.explanation",
    "access.reachability",
    "staff.empathy",
    "staff.friendliness",
}


class ParaphraseCandidate(BaseModel):
    paraphrased_review_text: str


class SemanticJudgment(BaseModel):
    verdict: Literal["pass", "fail"]
    meaning_preserved: bool
    sentiment_preserved: bool
    facts_preserved: bool
    label_implications_preserved: bool
    reason: str


def load_json(path: Path):
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def load_ids(path: Path) -> list[str]:
    with path.open("r", encoding="utf-8") as f:
        return [line.strip() for line in f if line.strip()]


def canonicalize_labels(raw_labels: dict) -> dict:
    labels = FlatExtraction(
        problem_labels=raw_labels.get("problem_labels", []),
        strength_labels=raw_labels.get("strength_labels", []),
    )
    return labels.model_dump()


def merge_labels(raw_labels: dict) -> set[tuple[str, str]]:
    labels = canonicalize_labels(raw_labels)
    merged = {("problem", label) for label in labels["problem_labels"]}
    merged.update({("strength", label) for label in labels["strength_labels"]})
    return merged


def normalize_prediction_payload(path: Path) -> dict[str, dict]:
    data = load_json(path)
    records = data.get("records", data)
    normalized = {}

    for review_id, record in records.items():
        labels = record.get("labels") or record.get("benchmark_labels") or record.get("model_prelabels") or {}
        normalized[review_id] = canonicalize_labels(labels)

    return normalized


def review_has_missed_label(reference_labels: dict, predicted_labels: dict) -> bool:
    return len(merge_labels(reference_labels) - merge_labels(predicted_labels)) > 0


def review_has_extra_label(reference_labels: dict, predicted_labels: dict) -> bool:
    return len(merge_labels(predicted_labels) - merge_labels(reference_labels)) > 0


def selection_score(review_id: str, record: dict, v1_predictions: dict, v17_predictions: dict) -> tuple[int, dict]:
    labels = canonicalize_labels(record["benchmark_labels"])
    score = 0

    if record["bucket"] == "mixed_hard":
        score += 3

    label_hits = sorted(
        label
        for label in labels["problem_labels"] + labels["strength_labels"]
        if label in TARGET_LABELS
    )
    score += 2 * len(label_hits)

    v1_miss = review_has_missed_label(labels, v1_predictions[review_id])
    if v1_miss:
        score += 2

    v17_extra = review_has_extra_label(labels, v17_predictions[review_id])
    if v17_extra:
        score += 2

    mixed_polarity = bool(labels["problem_labels"]) and bool(labels["strength_labels"])
    if mixed_polarity:
        score += 1

    details = {
        "bucket": record["bucket"],
        "target_label_hits": label_hits,
        "v1_missed_any": v1_miss,
        "v17_added_extra_any": v17_extra,
        "mixed_problem_and_strength": mixed_polarity,
    }
    return score, details


def build_paraphrase_prompt(review_text: str) -> str:
    return f"""
Du formulierst Krankenhausbewertungen auf Deutsch um.

Wichtige Regeln:
- Erhalte die Bedeutung vollständig.
- Erhalte die gleiche positive, negative oder gemischte Bewertungstendenz.
- Erhalte alle relevanten Tatsachen und Bewertungen.
- Verändere nur Formulierung, Satzbau und Wortwahl.
- Füge keine neuen Fakten hinzu.
- Lasse keine Fakten weg.
- Verstärke oder schwäche keine Kritik und kein Lob.
- Übersetze nicht.
- Fasse nicht zusammen.
- Gib ausschließlich den umformulierten Review-Text zurück.

Originalbewertung:
{review_text}
""".strip()


def build_judge_prompt(original_text: str, candidate_text: str, labels: dict, metadata: dict) -> str:
    labels_json = json.dumps(canonicalize_labels(labels), ensure_ascii=False, indent=2)
    metadata_json = json.dumps(metadata, ensure_ascii=False, indent=2)

    return f"""
Prüfe, ob die umformulierte Krankenhausbewertung inhaltlich gleichbedeutend mit der Originalbewertung ist.

Bewerte streng nach diesen Kriterien:
- meaning_preserved: alle relevanten Aussagen bleiben erhalten
- sentiment_preserved: positives, negatives und gemischtes Framing bleibt gleich
- facts_preserved: keine Fakten hinzugefügt, entfernt oder verändert
- label_implications_preserved: die unten angegebenen Labels würden weiterhin auf dieselben Textsignale passen

Gib ein `fail`, sobald einer der Punkte nicht erfüllt ist.

Metadata:
{metadata_json}

Original labels:
{labels_json}

Original review:
{original_text}

Candidate paraphrase:
{candidate_text}
""".strip()


def normalize_text(text: str) -> str:
    return re.sub(r"\s+", " ", text.strip()).lower()


def record_to_jsonl_line(review_text: str, metadata: dict, benchmark_labels: dict) -> str:
    meta_json = json.dumps(metadata, ensure_ascii=False, indent=2)
    prompt = build_prompt_v1(review_text, meta_json)
    labels = canonicalize_labels(benchmark_labels)
    payload = {
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT_V1},
            {"role": "user", "content": prompt},
            {"role": "assistant", "content": json.dumps(labels, ensure_ascii=False, separators=(",", ":"))},
        ]
    }
    return json.dumps(payload, ensure_ascii=False)


def write_jsonl(path: Path, items: list[dict]) -> None:
    with path.open("w", encoding="utf-8") as f:
        for item in items:
            f.write(
                record_to_jsonl_line(
                    review_text=item["review_text"],
                    metadata=item["metadata"],
                    benchmark_labels=item["benchmark_labels"],
                )
            )
            f.write("\n")


def main() -> None:
    load_dotenv()
    openai_api_key = os.getenv("OPENAI_API_KEY")
    if not openai_api_key:
        raise ValueError("No OpenAI API key found in .env")

    client = from_openai(OpenAI(api_key=openai_api_key))

    source = load_json(SOURCE_PATH)
    source_records = source["records"]
    train_ids = load_ids(TRAIN_IDS_PATH)
    holdout_ids = set(load_ids(HOLDOUT_IDS_PATH))

    v1_predictions = normalize_prediction_payload(V1_PREDICTION_PATH)
    v17_predictions = normalize_prediction_payload(V17_PREDICTION_PATH)

    if any(review_id in holdout_ids for review_id in train_ids):
        raise ValueError("Train ids unexpectedly overlap with holdout ids.")

    scored = []
    for review_id in train_ids:
        record = source_records[review_id]
        score, details = selection_score(review_id, record, v1_predictions, v17_predictions)
        scored.append((score, review_id, details))

    scored.sort(key=lambda item: (-item[0], item[1]))
    primary_source_ids = [review_id for _, review_id, _ in scored[:SELECTED_SOURCE_COUNT]]
    reserve_source_ids = [review_id for _, review_id, _ in scored[SELECTED_SOURCE_COUNT:]]
    source_rank_lookup = {
        review_id: rank + 1 for rank, (_, review_id, _) in enumerate(scored)
    }
    selection_details_lookup = {review_id: details for _, review_id, details in scored}

    OUT_AUG_DIR.mkdir(parents=True, exist_ok=True)
    OUT_FINETUNE_DIR.mkdir(parents=True, exist_ok=True)

    with SOURCE_IDS_PATH.open("w", encoding="utf-8") as f:
        for review_id in primary_source_ids:
            f.write(review_id)
            f.write("\n")

    accepted = []
    candidates = []
    judgments = []
    accepted_texts = {normalize_text(source_records[review_id]["review_text"]) for review_id in train_ids}
    accepted_per_source: dict[str, int] = {}
    used_source_ids: list[str] = []

    ranked_source_ids = primary_source_ids + reserve_source_ids
    candidate_counter = 0

    for review_id in ranked_source_ids:
        if len(accepted) >= TARGET_ACCEPTED_AUGMENTATIONS:
            break

        record = source_records[review_id]
        accepted_per_source.setdefault(review_id, 0)
        used_source_ids.append(review_id)

        for attempt in range(1, MAX_ATTEMPTS_PER_SOURCE + 1):
            if accepted_per_source[review_id] >= VARIANTS_PER_REVIEW:
                break
            if len(accepted) >= TARGET_ACCEPTED_AUGMENTATIONS:
                break

            candidate_counter += 1
            candidate_id = f"cand_{candidate_counter:04d}"

            candidate = client.chat.completions.create(
                model=PARAPHRASE_MODEL,
                reasoning_effort=PARAPHRASE_REASONING_EFFORT,
                response_model=ParaphraseCandidate,
                messages=[
                    {"role": "system", "content": "You rewrite German review texts and respond only with JSON."},
                    {"role": "user", "content": build_paraphrase_prompt(record["review_text"])},
                ],
            )

            candidate_text = candidate.paraphrased_review_text.strip()
            normalized_candidate_text = normalize_text(candidate_text)

            candidate_entry = {
                "candidate_id": candidate_id,
                "source_review_id": review_id,
                "source_rank": source_rank_lookup[review_id],
                "source_bucket": record["bucket"],
                "source_is_reserve": review_id not in primary_source_ids,
                "attempt_number": attempt,
                "generator_model": PARAPHRASE_MODEL,
                "generator_reasoning_effort": PARAPHRASE_REASONING_EFFORT,
                "generated_at": datetime.now(timezone.utc).isoformat(),
                "original_review_text": record["review_text"],
                "paraphrased_review_text": candidate_text,
                "benchmark_labels": canonicalize_labels(record["benchmark_labels"]),
                "metadata": record["metadata"],
            }
            candidates.append(candidate_entry)

            if normalized_candidate_text in accepted_texts:
                judgments.append(
                    {
                        "candidate_id": candidate_id,
                        "source_review_id": review_id,
                        "judge_model": JUDGE_MODEL,
                        "judge_reasoning_effort": JUDGE_REASONING_EFFORT,
                        "judged_at": datetime.now(timezone.utc).isoformat(),
                        "verdict": "fail",
                        "meaning_preserved": False,
                        "sentiment_preserved": False,
                        "facts_preserved": False,
                        "label_implications_preserved": False,
                        "reason": "candidate text duplicates the original or an already accepted text",
                        "accepted": False,
                    }
                )
                continue

            judgment = client.chat.completions.create(
                model=JUDGE_MODEL,
                reasoning_effort=JUDGE_REASONING_EFFORT,
                response_model=SemanticJudgment,
                messages=[
                    {"role": "system", "content": "You judge semantic equivalence and respond only with JSON."},
                    {
                        "role": "user",
                        "content": build_judge_prompt(
                            original_text=record["review_text"],
                            candidate_text=candidate_text,
                            labels=record["benchmark_labels"],
                            metadata=record["metadata"],
                        ),
                    },
                ],
            )

            accept = (
                judgment.verdict == "pass"
                and judgment.meaning_preserved
                and judgment.sentiment_preserved
                and judgment.facts_preserved
                and judgment.label_implications_preserved
            )

            judgments.append(
                {
                    "candidate_id": candidate_id,
                    "source_review_id": review_id,
                    "judge_model": JUDGE_MODEL,
                    "judge_reasoning_effort": JUDGE_REASONING_EFFORT,
                    "judged_at": datetime.now(timezone.utc).isoformat(),
                    "verdict": judgment.verdict,
                    "meaning_preserved": judgment.meaning_preserved,
                    "sentiment_preserved": judgment.sentiment_preserved,
                    "facts_preserved": judgment.facts_preserved,
                    "label_implications_preserved": judgment.label_implications_preserved,
                    "reason": judgment.reason,
                    "accepted": accept,
                }
            )

            if not accept:
                continue

            accepted_per_source[review_id] += 1
            variant_id = accepted_per_source[review_id]
            accepted_texts.add(normalized_candidate_text)

            accepted.append(
                {
                    "synthetic_review_id": f"{review_id}__aug_{variant_id}",
                    "source_review_id": review_id,
                    "variant_id": variant_id,
                    "source_rank": source_rank_lookup[review_id],
                    "source_bucket": record["bucket"],
                    "source_is_reserve": review_id not in primary_source_ids,
                    "review_text": candidate_text,
                    "metadata": record["metadata"],
                    "benchmark_labels": canonicalize_labels(record["benchmark_labels"]),
                    "generator_model": PARAPHRASE_MODEL,
                    "generator_reasoning_effort": PARAPHRASE_REASONING_EFFORT,
                    "judge_model": JUDGE_MODEL,
                    "judge_reasoning_effort": JUDGE_REASONING_EFFORT,
                    "accepted_at": datetime.now(timezone.utc).isoformat(),
                }
            )

    if len(accepted) != TARGET_ACCEPTED_AUGMENTATIONS:
        raise RuntimeError(
            f"Expected {TARGET_ACCEPTED_AUGMENTATIONS} accepted augmentations, got {len(accepted)}."
        )

    train_records = []
    for review_id in train_ids:
        record = source_records[review_id]
        train_records.append(
            {
                "review_id": review_id,
                "review_text": record["review_text"],
                "metadata": record["metadata"],
                "benchmark_labels": canonicalize_labels(record["benchmark_labels"]),
            }
        )

    synthetic_records = [
        {
            "review_id": item["synthetic_review_id"],
            "review_text": item["review_text"],
            "metadata": item["metadata"],
            "benchmark_labels": item["benchmark_labels"],
        }
        for item in accepted
    ]

    holdout_records = []
    for review_id in load_ids(HOLDOUT_IDS_PATH):
        record = source_records[review_id]
        holdout_records.append(
            {
                "review_id": review_id,
                "review_text": record["review_text"],
                "metadata": record["metadata"],
                "benchmark_labels": canonicalize_labels(record["benchmark_labels"]),
            }
        )

    write_jsonl(TRAIN_JSONL_PATH, train_records + synthetic_records)
    write_jsonl(VALID_JSONL_PATH, holdout_records)

    candidates_payload = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "generator_model": PARAPHRASE_MODEL,
        "generator_reasoning_effort": PARAPHRASE_REASONING_EFFORT,
        "items": candidates,
    }
    judgments_payload = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "judge_model": JUDGE_MODEL,
        "judge_reasoning_effort": JUDGE_REASONING_EFFORT,
        "items": judgments,
    }
    augmented_payload = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "items": accepted,
    }

    manifest = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "version": "v1_8",
        "source_benchmark_path": str(SOURCE_PATH),
        "v1_prediction_path": str(V1_PREDICTION_PATH),
        "v1_7_prediction_path": str(V17_PREDICTION_PATH),
        "train_ids_path": str(TRAIN_IDS_PATH),
        "holdout_ids_path": str(HOLDOUT_IDS_PATH),
        "selected_source_count": SELECTED_SOURCE_COUNT,
        "target_accepted_augmentations": TARGET_ACCEPTED_AUGMENTATIONS,
        "variants_per_review": VARIANTS_PER_REVIEW,
        "max_attempts_per_source": MAX_ATTEMPTS_PER_SOURCE,
        "paraphrase_model": PARAPHRASE_MODEL,
        "paraphrase_reasoning_effort": PARAPHRASE_REASONING_EFFORT,
        "judge_model": JUDGE_MODEL,
        "judge_reasoning_effort": JUDGE_REASONING_EFFORT,
        "target_labels": sorted(TARGET_LABELS),
        "primary_source_ids": primary_source_ids,
        "reserve_source_ids": reserve_source_ids,
        "used_source_ids": used_source_ids,
        "accepted_source_ids": sorted({item["source_review_id"] for item in accepted}),
        "selection_details": {
            review_id: {
                "score": next(score for score, rid, _ in scored if rid == review_id),
                **selection_details_lookup[review_id],
            }
            for _, review_id, _ in scored
        },
        "artifacts": {
            "source_ids_path": str(SOURCE_IDS_PATH),
            "candidates_path": str(CANDIDATES_PATH),
            "augmented_path": str(AUGMENTED_PATH),
            "judgments_path": str(JUDGMENTS_PATH),
            "train_jsonl_path": str(TRAIN_JSONL_PATH),
            "valid_jsonl_path": str(VALID_JSONL_PATH),
        },
    }

    dataset_manifest = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "version": "v1_8",
        "base_model": "gpt-4.1-mini-2025-04-14",
        "prompt_version": "v1",
        "system_prompt": SYSTEM_PROMPT_V1,
        "train_total_reviews": len(train_records),
        "synthetic_total_reviews": len(synthetic_records),
        "combined_train_total_reviews": len(train_records) + len(synthetic_records),
        "holdout_total_reviews": len(holdout_records),
        "source_manifest_path": str(MANIFEST_PATH),
        "train_jsonl_path": str(TRAIN_JSONL_PATH),
        "valid_jsonl_path": str(VALID_JSONL_PATH),
    }

    with CANDIDATES_PATH.open("w", encoding="utf-8") as f:
        json.dump(candidates_payload, f, ensure_ascii=False, indent=2)
    with AUGMENTED_PATH.open("w", encoding="utf-8") as f:
        json.dump(augmented_payload, f, ensure_ascii=False, indent=2)
    with JUDGMENTS_PATH.open("w", encoding="utf-8") as f:
        json.dump(judgments_payload, f, ensure_ascii=False, indent=2)
    with MANIFEST_PATH.open("w", encoding="utf-8") as f:
        json.dump(manifest, f, ensure_ascii=False, indent=2)
    with DATASET_MANIFEST_PATH.open("w", encoding="utf-8") as f:
        json.dump(dataset_manifest, f, ensure_ascii=False, indent=2)

    print(f"[ok] wrote selected source ids: {SOURCE_IDS_PATH}")
    print(f"[ok] wrote candidates: {CANDIDATES_PATH}")
    print(f"[ok] wrote accepted augmentations: {AUGMENTED_PATH}")
    print(f"[ok] wrote judgments: {JUDGMENTS_PATH}")
    print(f"[ok] wrote augmentation manifest: {MANIFEST_PATH}")
    print(f"[ok] wrote train jsonl: {TRAIN_JSONL_PATH}")
    print(f"[ok] wrote valid jsonl: {VALID_JSONL_PATH}")
    print(f"[ok] wrote dataset manifest: {DATASET_MANIFEST_PATH}")
    print(
        json.dumps(
            {
                "selected_source_reviews": len(primary_source_ids),
                "accepted_augmentations": len(accepted),
                "combined_train_total_reviews": len(train_records) + len(synthetic_records),
                "holdout_total_reviews": len(holdout_records),
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
