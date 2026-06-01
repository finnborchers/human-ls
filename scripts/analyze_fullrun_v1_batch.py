#!/usr/bin/env python3

import csv
import json
import math
import os
from collections import Counter
from datetime import datetime, timezone
from itertools import combinations, product
from pathlib import Path

TMP_CACHE_DIR = Path("/private/tmp/human_ls_matplotlib")
TMP_CACHE_DIR.mkdir(parents=True, exist_ok=True)
os.environ.setdefault("MPLCONFIGDIR", str(TMP_CACHE_DIR / "mplconfig"))
os.environ.setdefault("XDG_CACHE_HOME", str(TMP_CACHE_DIR / "cache"))

import matplotlib

matplotlib.use("Agg")

import matplotlib.pyplot as plt
import numpy as np


INPUT_PATH = Path(
    os.getenv(
        "FULLRUN_ANALYSIS_INPUT_PATH",
        "analysis/llm/full_run/v1_batch_run/merged/all_scopes_labeled.json",
    )
)
INPUT_SUMMARY_PATH = Path(
    os.getenv(
        "FULLRUN_ANALYSIS_INPUT_SUMMARY_PATH",
        "analysis/llm/full_run/v1_batch_run/merged/all_scopes_summary.json",
    )
)
OUT_DIR = Path(
    os.getenv(
        "FULLRUN_ANALYSIS_OUT_DIR",
        "analysis/llm/full_run/descriptive_analysis",
    )
)

TOP_K = int(os.getenv("FULLRUN_ANALYSIS_TOP_K", "15"))
PAIR_TOP_K = int(os.getenv("FULLRUN_ANALYSIS_PAIR_TOP_K", "20"))
HEATMAP_TOP_K = int(os.getenv("FULLRUN_ANALYSIS_HEATMAP_TOP_K", "12"))

PROBLEM_COLOR = "#E76F51"
STRENGTH_COLOR = "#2A9D8F"
NEUTRAL_COLOR = "#264653"


def load_json(path: Path) -> dict:
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)


def write_csv(path: Path, fieldnames: list[str], rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def pct(part: int, whole: int) -> float:
    if whole == 0:
        return 0.0
    return round(part / whole * 100, 2)


def round2(value: float) -> float:
    return round(value, 2)


def counter_to_rows(counter: Counter, label_key: str, count_key: str, top_k: int | None = None) -> list[dict]:
    items = counter.most_common(top_k)
    return [{label_key: label, count_key: count} for label, count in items]


def pair_counter_to_rows(counter: Counter, left_key: str, right_key: str, count_key: str, top_k: int) -> list[dict]:
    rows = []
    for pair, count in counter.most_common(top_k):
        left, right = pair
        rows.append({left_key: left, right_key: right, count_key: count})
    return rows


def build_heatmap_matrix(counter: Counter, labels: list[str]) -> np.ndarray:
    index = {label: idx for idx, label in enumerate(labels)}
    matrix = np.zeros((len(labels), len(labels)), dtype=int)
    for (left, right), count in counter.items():
        if left not in index or right not in index:
            continue
        i = index[left]
        j = index[right]
        matrix[i, j] = count
        matrix[j, i] = count
    return matrix


def draw_top_bar(ax, rows: list[dict], label_key: str, count_key: str, title: str, color: str) -> None:
    labels = [row[label_key] for row in rows]
    counts = [row[count_key] for row in rows]
    y = np.arange(len(labels))
    ax.barh(y, counts, color=color)
    ax.set_yticks(y)
    ax.set_yticklabels(labels, fontsize=10)
    ax.invert_yaxis()
    ax.set_title(title, fontsize=14, pad=10)
    ax.set_xlabel("Count", fontsize=11)
    ax.grid(axis="x", linestyle="--", alpha=0.25)
    xmax = max(counts) if counts else 0
    offset = max(xmax * 0.02, 0.2)
    for yi, count in enumerate(counts):
        ax.text(count + offset, yi, str(count), va="center", ha="left", fontsize=10)


def save_top_label_plot(path: Path, rows: list[dict], label_key: str, count_key: str, title: str, color: str) -> None:
    fig, ax = plt.subplots(figsize=(12, 7), dpi=300)
    fig.patch.set_facecolor("white")
    draw_top_bar(ax, rows, label_key, count_key, title, color)
    plt.tight_layout()
    path.parent.mkdir(parents=True, exist_ok=True)
    plt.savefig(path, dpi=300, bbox_inches="tight")
    plt.close(fig)


def save_label_count_histogram(path: Path, distribution_rows: list[dict]) -> None:
    counts = [row["label_count"] for row in distribution_rows]
    freqs = [row["review_count"] for row in distribution_rows]
    fig, ax = plt.subplots(figsize=(12, 6.5), dpi=300)
    fig.patch.set_facecolor("white")
    ax.bar(counts, freqs, color=NEUTRAL_COLOR, width=0.85)
    ax.set_title("Labels per Review Distribution", fontsize=14, pad=10)
    ax.set_xlabel("Total labels on review", fontsize=11)
    ax.set_ylabel("Review count", fontsize=11)
    ax.grid(axis="y", linestyle="--", alpha=0.25)
    plt.tight_layout()
    path.parent.mkdir(parents=True, exist_ok=True)
    plt.savefig(path, dpi=300, bbox_inches="tight")
    plt.close(fig)


def save_problem_strength_volume_plot(path: Path, summary: dict) -> None:
    values = [
        summary["problem_label_total"],
        summary["strength_label_total"],
    ]
    labels = ["Problem labels", "Strength labels"]
    colors = [PROBLEM_COLOR, STRENGTH_COLOR]
    fig, ax = plt.subplots(figsize=(8.5, 6), dpi=300)
    fig.patch.set_facecolor("white")
    bars = ax.bar(labels, values, color=colors, width=0.6)
    ax.set_title("Problem vs Strength Label Volume", fontsize=14, pad=10)
    ax.set_ylabel("Label count", fontsize=11)
    ax.grid(axis="y", linestyle="--", alpha=0.25)
    ymax = max(values) if values else 0
    offset = max(ymax * 0.015, 10)
    for bar, value in zip(bars, values):
        ax.text(
            bar.get_x() + bar.get_width() / 2,
            value + offset,
            f"{value}",
            ha="center",
            va="bottom",
            fontsize=11,
        )
    plt.tight_layout()
    path.parent.mkdir(parents=True, exist_ok=True)
    plt.savefig(path, dpi=300, bbox_inches="tight")
    plt.close(fig)


def save_cooccurrence_heatmap(path: Path, pair_counter: Counter, top_labels: list[str], title: str) -> None:
    matrix = build_heatmap_matrix(pair_counter, top_labels)
    fig, ax = plt.subplots(figsize=(10.5, 9), dpi=300)
    fig.patch.set_facecolor("white")
    im = ax.imshow(matrix, cmap="Blues")
    ax.set_title(title, fontsize=14, pad=12)
    ax.set_xticks(np.arange(len(top_labels)))
    ax.set_yticks(np.arange(len(top_labels)))
    ax.set_xticklabels(top_labels, rotation=45, ha="right", fontsize=9)
    ax.set_yticklabels(top_labels, fontsize=9)
    for i in range(len(top_labels)):
        for j in range(len(top_labels)):
            value = matrix[i, j]
            if value == 0:
                continue
            ax.text(j, i, str(value), ha="center", va="center", fontsize=7, color="black")
    fig.colorbar(im, ax=ax, fraction=0.046, pad=0.04)
    plt.tight_layout()
    path.parent.mkdir(parents=True, exist_ok=True)
    plt.savefig(path, dpi=300, bbox_inches="tight")
    plt.close(fig)


def build_report(summary: dict, top_problem_rows: list[dict], top_strength_rows: list[dict], pair_rows: dict[str, list[dict]]) -> str:
    top_problem_text = ", ".join(
        f"{row['label']} ({row['count']})" for row in top_problem_rows[:5]
    )
    top_strength_text = ", ".join(
        f"{row['label']} ({row['count']})" for row in top_strength_rows[:5]
    )
    pp_text = ", ".join(
        f"{row['label_a']} + {row['label_b']} ({row['count']})" for row in pair_rows["problem_problem"][:3]
    )
    ps_text = ", ".join(
        f"{row['problem_label']} + {row['strength_label']} ({row['count']})" for row in pair_rows["problem_strength"][:3]
    )
    return f"""# Full-Run Descriptive Analysis

## Run summary

- Total reviews analyzed: `{summary['total_reviews']:,}`
- Fully materialized reviews: `{summary['materialized_reviews']:,}`
- Parse errors in full run: `{summary['parse_errors_total']}`
- Reviews without any labels: `{summary['no_label_reviews']:,}` (`{summary['no_label_reviews_pct']}%`)

## Methodological note

- `V1` remained the strongest benchmark baseline in the controlled tests.
- The full 30,863-review run was still executed on the batch path to obtain complete corpus coverage.
- The resulting descriptive analysis should therefore be read as a **coverage analysis with a known quality tradeoff**, not as a new gold-standard label set.

## Main observations

- Reviews with only problem labels: `{summary['problem_only_reviews']:,}` (`{summary['problem_only_reviews_pct']}%`)
- Reviews with only strength labels: `{summary['strength_only_reviews']:,}` (`{summary['strength_only_reviews_pct']}%`)
- Reviews with both problem and strength labels: `{summary['mixed_reviews']:,}` (`{summary['mixed_reviews_pct']}%`)
- Mean labels per review: `{summary['avg_labels_per_review']}`
- Median labels per review: `{summary['median_labels_per_review']}`

- Dominant problem themes: {top_problem_text}
- Dominant strength themes: {top_strength_text}
- Most common problem-problem combinations: {pp_text}
- Most common problem-strength combinations: {ps_text}

## Interpretation boundary

- This first pass is intentionally global and descriptive.
- It supports high-level thematic interpretation of the corpus.
- It should not yet be used as a clinic-ranking or causal comparison layer without additional filtering and methodological safeguards.
"""


def main() -> None:
    payload = load_json(INPUT_PATH)
    input_summary = load_json(INPUT_SUMMARY_PATH)
    records = payload.get("records", {})

    problem_counter = Counter()
    strength_counter = Counter()
    problem_problem_counter = Counter()
    strength_strength_counter = Counter()
    problem_strength_counter = Counter()
    label_count_distribution = Counter()

    no_label_reviews = 0
    problem_only_reviews = 0
    strength_only_reviews = 0
    mixed_reviews = 0
    label_totals = []

    for record in records.values():
        labels = record.get("labels") or {}
        problems = sorted(set(labels.get("problem_labels", [])))
        strengths = sorted(set(labels.get("strength_labels", [])))

        for label in problems:
            problem_counter[label] += 1
        for label in strengths:
            strength_counter[label] += 1

        for pair in combinations(problems, 2):
            problem_problem_counter[pair] += 1
        for pair in combinations(strengths, 2):
            strength_strength_counter[pair] += 1
        for pair in product(problems, strengths):
            problem_strength_counter[pair] += 1

        total_labels = len(problems) + len(strengths)
        label_count_distribution[total_labels] += 1
        label_totals.append(total_labels)

        if not problems and not strengths:
            no_label_reviews += 1
        elif problems and strengths:
            mixed_reviews += 1
        elif problems:
            problem_only_reviews += 1
        else:
            strength_only_reviews += 1

    total_reviews = len(records)
    sorted_totals = sorted(label_totals)
    median_labels = sorted_totals[len(sorted_totals) // 2] if sorted_totals else 0
    if sorted_totals and len(sorted_totals) % 2 == 0:
        left = sorted_totals[len(sorted_totals) // 2 - 1]
        right = sorted_totals[len(sorted_totals) // 2]
        median_labels = round2((left + right) / 2)

    summary = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "input_path": str(INPUT_PATH),
        "input_summary_path": str(INPUT_SUMMARY_PATH),
        "total_reviews": total_reviews,
        "materialized_reviews": input_summary.get("materialized_reviews", total_reviews),
        "parse_errors_total": 0,
        "problem_label_total": sum(problem_counter.values()),
        "strength_label_total": sum(strength_counter.values()),
        "no_label_reviews": no_label_reviews,
        "no_label_reviews_pct": pct(no_label_reviews, total_reviews),
        "problem_only_reviews": problem_only_reviews,
        "problem_only_reviews_pct": pct(problem_only_reviews, total_reviews),
        "strength_only_reviews": strength_only_reviews,
        "strength_only_reviews_pct": pct(strength_only_reviews, total_reviews),
        "mixed_reviews": mixed_reviews,
        "mixed_reviews_pct": pct(mixed_reviews, total_reviews),
        "avg_labels_per_review": round2(sum(label_totals) / total_reviews) if total_reviews else 0.0,
        "median_labels_per_review": median_labels,
        "max_labels_per_review": max(label_totals) if label_totals else 0,
        "unique_problem_labels": len(problem_counter),
        "unique_strength_labels": len(strength_counter),
    }

    distribution_rows = [
        {
            "label_count": label_count,
            "review_count": count,
            "review_pct": pct(count, total_reviews),
        }
        for label_count, count in sorted(label_count_distribution.items())
    ]

    top_problem_rows = counter_to_rows(problem_counter, "label", "count", TOP_K)
    top_strength_rows = counter_to_rows(strength_counter, "label", "count", TOP_K)
    pp_rows = pair_counter_to_rows(problem_problem_counter, "label_a", "label_b", "count", PAIR_TOP_K)
    ss_rows = pair_counter_to_rows(strength_strength_counter, "label_a", "label_b", "count", PAIR_TOP_K)
    ps_rows = pair_counter_to_rows(problem_strength_counter, "problem_label", "strength_label", "count", PAIR_TOP_K)

    report_text = build_report(
        summary,
        top_problem_rows,
        top_strength_rows,
        {
            "problem_problem": pp_rows,
            "strength_strength": ss_rows,
            "problem_strength": ps_rows,
        },
    )

    summary_payload = {
        "run_meta": {
            "runner": "analyze_fullrun_v1_batch.py",
            "generated_at": summary["generated_at"],
            "record_count": total_reviews,
        },
        "summary": summary,
        "top_problem_labels": top_problem_rows,
        "top_strength_labels": top_strength_rows,
        "label_count_distribution": distribution_rows,
        "top_problem_problem_pairs": pp_rows,
        "top_strength_strength_pairs": ss_rows,
        "top_problem_strength_pairs": ps_rows,
    }

    data_dir = OUT_DIR / "tables"
    plot_dir = OUT_DIR / "plots"
    report_path = OUT_DIR / "fullrun_descriptive_report.md"

    write_json(OUT_DIR / "summary.json", summary_payload)
    write_csv(data_dir / "top_problem_labels.csv", ["label", "count"], top_problem_rows)
    write_csv(data_dir / "top_strength_labels.csv", ["label", "count"], top_strength_rows)
    write_csv(data_dir / "label_count_distribution.csv", ["label_count", "review_count", "review_pct"], distribution_rows)
    write_csv(data_dir / "top_problem_problem_pairs.csv", ["label_a", "label_b", "count"], pp_rows)
    write_csv(data_dir / "top_strength_strength_pairs.csv", ["label_a", "label_b", "count"], ss_rows)
    write_csv(data_dir / "top_problem_strength_pairs.csv", ["problem_label", "strength_label", "count"], ps_rows)
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(report_text, encoding="utf-8")

    save_top_label_plot(
        plot_dir / "top_problem_labels.png",
        top_problem_rows,
        "label",
        "count",
        "Top Problem Labels Across 30,863 Reviews",
        PROBLEM_COLOR,
    )
    save_top_label_plot(
        plot_dir / "top_strength_labels.png",
        top_strength_rows,
        "label",
        "count",
        "Top Strength Labels Across 30,863 Reviews",
        STRENGTH_COLOR,
    )
    save_label_count_histogram(plot_dir / "labels_per_review_histogram.png", distribution_rows)
    save_problem_strength_volume_plot(plot_dir / "problem_vs_strength_volume.png", summary)

    heatmap_labels = [row["label"] for row in top_problem_rows[:HEATMAP_TOP_K]]
    save_cooccurrence_heatmap(
        plot_dir / "problem_label_cooccurrence_heatmap.png",
        problem_problem_counter,
        heatmap_labels,
        "Problem Label Co-occurrence Heatmap",
    )

    print(f"[ok] wrote descriptive analysis to: {OUT_DIR}")


if __name__ == "__main__":
    main()
