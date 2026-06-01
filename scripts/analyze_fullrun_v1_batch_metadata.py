#!/usr/bin/env python3

import csv
import json
import os
from collections import Counter, defaultdict
from datetime import datetime, timezone
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
        "FULLRUN_METADATA_INPUT_PATH",
        "analysis/llm/full_run/v1_batch_run/merged/all_scopes_labeled.json",
    )
)
OUT_DIR = Path(
    os.getenv(
        "FULLRUN_METADATA_OUT_DIR",
        "analysis/llm/full_run/metadata_analysis",
    )
)
TOP_K = int(os.getenv("FULLRUN_METADATA_TOP_K", "8"))

PROBLEM_COLOR = "#E76F51"
STRENGTH_COLOR = "#2A9D8F"
NEUTRAL_COLOR = "#264653"
MIXED_COLOR = "#8AB17D"
NO_LABEL_COLOR = "#C9C9C9"

LIKE_BUCKETS = ("0", "1", "2-4", "5-9", "10-24", "25+")
STAR_ORDER = (1, 2, 3, 4, 5, None)
STAR_LABELS = {1: "1★", 2: "2★", 3: "3★", 4: "4★", 5: "5★", None: "Unknown"}
OWNER_ORDER = (False, True)
OWNER_LABELS = {False: "No owner response", True: "Owner response"}


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


def like_bucket(like_count: int) -> str:
    if like_count <= 0:
        return "0"
    if like_count == 1:
        return "1"
    if 2 <= like_count <= 4:
        return "2-4"
    if 5 <= like_count <= 9:
        return "5-9"
    if 10 <= like_count <= 24:
        return "10-24"
    return "25+"


def empty_group() -> dict:
    return {
        "reviews": 0,
        "problem_total": 0,
        "strength_total": 0,
        "no_label": 0,
        "problem_only": 0,
        "strength_only": 0,
        "mixed": 0,
        "likes_sum": 0,
        "star_sum": 0,
        "star_n": 0,
        "problem_counter": Counter(),
        "strength_counter": Counter(),
    }


def finalize_group_row(group_key, group_label: str, stats: dict, include_star_mean: bool = False) -> dict:
    reviews = stats["reviews"]
    row = {
        "group_key": group_key,
        "group_label": group_label,
        "reviews": reviews,
        "review_pct": pct(reviews, TOTAL_REVIEWS),
        "avg_problem_labels": round2(stats["problem_total"] / reviews) if reviews else 0.0,
        "avg_strength_labels": round2(stats["strength_total"] / reviews) if reviews else 0.0,
        "problem_only_reviews": stats["problem_only"],
        "problem_only_pct": pct(stats["problem_only"], reviews),
        "strength_only_reviews": stats["strength_only"],
        "strength_only_pct": pct(stats["strength_only"], reviews),
        "mixed_reviews": stats["mixed"],
        "mixed_pct": pct(stats["mixed"], reviews),
        "no_label_reviews": stats["no_label"],
        "no_label_pct": pct(stats["no_label"], reviews),
        "avg_likes": round2(stats["likes_sum"] / reviews) if reviews else 0.0,
    }
    if include_star_mean:
        row["avg_star_rating"] = round2(stats["star_sum"] / stats["star_n"]) if stats["star_n"] else None
    return row


def top_label_rows_by_group(groups: dict, order: tuple, label_kind: str, top_k: int) -> list[dict]:
    rows = []
    counter_key = "problem_counter" if label_kind == "problem" else "strength_counter"
    for key in order:
        stats = groups[key]
        label = STAR_LABELS.get(key, str(key))
        for rank, (name, count) in enumerate(stats[counter_key].most_common(top_k), start=1):
            rows.append(
                {
                    "group_key": key,
                    "group_label": label,
                    "rank": rank,
                    "label": name,
                    "count": count,
                }
            )
    return rows


def save_star_distribution_plot(path: Path, rows: list[dict]) -> None:
    labels = [row["group_label"] for row in rows]
    counts = [row["reviews"] for row in rows]
    fig, ax = plt.subplots(figsize=(10, 6), dpi=300)
    fig.patch.set_facecolor("white")
    bars = ax.bar(labels, counts, color=NEUTRAL_COLOR, width=0.7)
    ax.set_title("Review Distribution by Star Rating", fontsize=14, pad=10)
    ax.set_ylabel("Review count", fontsize=11)
    ax.grid(axis="y", linestyle="--", alpha=0.25)
    ymax = max(counts) if counts else 0
    offset = max(ymax * 0.01, 20)
    for bar, count in zip(bars, counts):
        ax.text(bar.get_x() + bar.get_width() / 2, count + offset, str(count), ha="center", va="bottom", fontsize=10)
    plt.tight_layout()
    path.parent.mkdir(parents=True, exist_ok=True)
    plt.savefig(path, dpi=300, bbox_inches="tight")
    plt.close(fig)


def save_review_mix_by_star_plot(path: Path, rows: list[dict]) -> None:
    labels = [row["group_label"] for row in rows]
    problem_only = np.array([row["problem_only_pct"] for row in rows])
    mixed = np.array([row["mixed_pct"] for row in rows])
    strength_only = np.array([row["strength_only_pct"] for row in rows])
    no_label = np.array([row["no_label_pct"] for row in rows])

    fig, ax = plt.subplots(figsize=(11, 6.5), dpi=300)
    fig.patch.set_facecolor("white")
    ax.bar(labels, problem_only, color=PROBLEM_COLOR, label="Problem only")
    ax.bar(labels, mixed, bottom=problem_only, color=MIXED_COLOR, label="Mixed")
    ax.bar(labels, strength_only, bottom=problem_only + mixed, color=STRENGTH_COLOR, label="Strength only")
    ax.bar(labels, no_label, bottom=problem_only + mixed + strength_only, color=NO_LABEL_COLOR, label="No label")
    ax.set_title("Review-Type Composition by Star Rating", fontsize=14, pad=10)
    ax.set_ylabel("Share of reviews (%)", fontsize=11)
    ax.set_ylim(0, 100)
    ax.grid(axis="y", linestyle="--", alpha=0.25)
    ax.legend(frameon=False, ncol=2, fontsize=10)
    plt.tight_layout()
    path.parent.mkdir(parents=True, exist_ok=True)
    plt.savefig(path, dpi=300, bbox_inches="tight")
    plt.close(fig)


def save_avg_labels_by_star_plot(path: Path, rows: list[dict]) -> None:
    labels = [row["group_label"] for row in rows]
    problem_values = np.array([row["avg_problem_labels"] for row in rows])
    strength_values = np.array([row["avg_strength_labels"] for row in rows])
    x = np.arange(len(labels))
    width = 0.36
    fig, ax = plt.subplots(figsize=(11, 6), dpi=300)
    fig.patch.set_facecolor("white")
    bars_p = ax.bar(x - width / 2, problem_values, width, color=PROBLEM_COLOR, label="Problem labels")
    bars_s = ax.bar(x + width / 2, strength_values, width, color=STRENGTH_COLOR, label="Strength labels")
    ax.set_xticks(x)
    ax.set_xticklabels(labels)
    ax.set_title("Average Labels per Review by Star Rating", fontsize=14, pad=10)
    ax.set_ylabel("Average labels per review", fontsize=11)
    ax.grid(axis="y", linestyle="--", alpha=0.25)
    ax.legend(frameon=False, fontsize=10)
    ymax = max(problem_values.max(), strength_values.max()) if len(problem_values) else 0
    offset = max(ymax * 0.02, 0.05)
    for bars in (bars_p, bars_s):
        for bar in bars:
            height = bar.get_height()
            ax.text(bar.get_x() + bar.get_width() / 2, height + offset, f"{height:.2f}", ha="center", va="bottom", fontsize=9)
    plt.tight_layout()
    path.parent.mkdir(parents=True, exist_ok=True)
    plt.savefig(path, dpi=300, bbox_inches="tight")
    plt.close(fig)


def save_like_salience_plot(path: Path, rows: list[dict]) -> None:
    labels = [row["group_label"] for row in rows]
    avg_star = np.array([row["avg_star_rating"] for row in rows], dtype=float)
    avg_problem = np.array([row["avg_problem_labels"] for row in rows], dtype=float)
    avg_strength = np.array([row["avg_strength_labels"] for row in rows], dtype=float)
    x = np.arange(len(labels))
    fig, axes = plt.subplots(1, 2, figsize=(14, 5.8), dpi=300)
    fig.patch.set_facecolor("white")

    axes[0].plot(x, avg_star, marker="o", color=NEUTRAL_COLOR, linewidth=2.2)
    axes[0].set_xticks(x)
    axes[0].set_xticklabels(labels)
    axes[0].set_title("Average Star Rating by Like Bucket", fontsize=14, pad=10)
    axes[0].set_xlabel("Like bucket (number of likes)", fontsize=11)
    axes[0].set_ylabel("Average star rating", fontsize=11)
    axes[0].set_ylim(0, 5.2)
    axes[0].grid(axis="y", linestyle="--", alpha=0.25)

    width = 0.36
    axes[1].bar(x - width / 2, avg_problem, width, color=PROBLEM_COLOR, label="Problem labels")
    axes[1].bar(x + width / 2, avg_strength, width, color=STRENGTH_COLOR, label="Strength labels")
    axes[1].set_xticks(x)
    axes[1].set_xticklabels(labels)
    axes[1].set_title("Average Label Density by Like Bucket", fontsize=14, pad=10)
    axes[1].set_xlabel("Like bucket (number of likes)", fontsize=11)
    axes[1].set_ylabel("Average labels per review", fontsize=11)
    axes[1].grid(axis="y", linestyle="--", alpha=0.25)
    axes[1].legend(frameon=False, fontsize=10)

    plt.tight_layout()
    path.parent.mkdir(parents=True, exist_ok=True)
    plt.savefig(path, dpi=300, bbox_inches="tight")
    plt.close(fig)


def save_owner_response_plot(path: Path, rows: list[dict]) -> None:
    labels = [row["group_label"] for row in rows]
    problem_values = np.array([row["avg_problem_labels"] for row in rows])
    strength_values = np.array([row["avg_strength_labels"] for row in rows])
    avg_likes = np.array([row["avg_likes"] for row in rows])
    x = np.arange(len(labels))
    width = 0.36
    fig, axes = plt.subplots(1, 2, figsize=(13.5, 5.8), dpi=300)
    fig.patch.set_facecolor("white")

    axes[0].bar(x - width / 2, problem_values, width, color=PROBLEM_COLOR, label="Problem labels")
    axes[0].bar(x + width / 2, strength_values, width, color=STRENGTH_COLOR, label="Strength labels")
    axes[0].set_xticks(x)
    axes[0].set_xticklabels(labels)
    axes[0].set_title("Average Labels by Owner Response", fontsize=14, pad=10)
    axes[0].set_ylabel("Average labels per review", fontsize=11)
    axes[0].grid(axis="y", linestyle="--", alpha=0.25)
    axes[0].legend(frameon=False, fontsize=10)

    bars = axes[1].bar(labels, avg_likes, color=NEUTRAL_COLOR, width=0.6)
    axes[1].set_title("Average Likes by Owner Response", fontsize=14, pad=10)
    axes[1].set_ylabel("Average likes", fontsize=11)
    axes[1].grid(axis="y", linestyle="--", alpha=0.25)
    ymax = max(avg_likes) if len(avg_likes) else 0
    offset = max(ymax * 0.02, 0.05)
    for bar, val in zip(bars, avg_likes):
        axes[1].text(bar.get_x() + bar.get_width() / 2, val + offset, f"{val:.2f}", ha="center", va="bottom", fontsize=10)

    plt.tight_layout()
    path.parent.mkdir(parents=True, exist_ok=True)
    plt.savefig(path, dpi=300, bbox_inches="tight")
    plt.close(fig)


def build_report(summary_by_star: list[dict], summary_by_like_bucket: list[dict], summary_by_owner_response: list[dict]) -> str:
    star1 = next(row for row in summary_by_star if row["group_key"] == 1)
    star3 = next(row for row in summary_by_star if row["group_key"] == 3)
    star5 = next(row for row in summary_by_star if row["group_key"] == 5)
    likes0 = next(row for row in summary_by_like_bucket if row["group_key"] == "0")
    likes25 = next(row for row in summary_by_like_bucket if row["group_key"] == "25+")
    owner_false = next(row for row in summary_by_owner_response if row["group_key"] is False)
    owner_true = next(row for row in summary_by_owner_response if row["group_key"] is True)
    return f"""# Full-Run Metadata Analysis

## Methodological note

- This analysis remains descriptive and corpus-level.
- The results refer to the labeled full-run corpus and should be interpreted as **associations within a coverage analysis with known model tradeoffs**.
- No causal interpretation is appropriate for owner responses, likes, or star-rating effects.

## Main observations

- `1★` reviews are strongly problem-dominated:
  - average problem labels: `{star1['avg_problem_labels']}`
  - average strength labels: `{star1['avg_strength_labels']}`
  - problem-only share: `{star1['problem_only_pct']}%`
- `5★` reviews are strongly strength-dominated:
  - average problem labels: `{star5['avg_problem_labels']}`
  - average strength labels: `{star5['avg_strength_labels']}`
  - strength-only share: `{star5['strength_only_pct']}%`
- `3★` reviews show the strongest mixed pattern:
  - mixed share: `{star3['mixed_pct']}%`

- Reviews with `0` likes have an average star rating of `{likes0['avg_star_rating']}`.
- Reviews with `25+` likes have an average star rating of `{likes25['avg_star_rating']}`.
- Across the like buckets, higher visibility is descriptively linked to lower star ratings and higher problem-label density.

- Reviews with owner responses show:
  - average strength labels: `{owner_true['avg_strength_labels']}`
  - no-label share: `{owner_true['no_label_pct']}%`
- Reviews without owner responses show:
  - average likes: `{owner_false['avg_likes']}`

## Interpretation boundary

- Star ratings behave as a strong polarity signal in the labeled corpus.
- Likes appear to correlate with more conflict-heavy and problem-oriented reviews.
- Owner response should be treated as a selection signal, not an intervention effect.
"""


payload = load_json(INPUT_PATH)
RECORDS = payload.get("records", {})
TOTAL_REVIEWS = len(RECORDS)


def main() -> None:
    star_groups = {key: empty_group() for key in STAR_ORDER}
    like_groups = {key: empty_group() for key in LIKE_BUCKETS}
    owner_groups = {key: empty_group() for key in OWNER_ORDER}

    for record in RECORDS.values():
        metadata = record.get("metadata") or {}
        labels = record.get("labels") or {}
        problems = list(labels.get("problem_labels", []))
        strengths = list(labels.get("strength_labels", []))
        star_value = metadata.get("star_rating")
        if star_value not in star_groups:
            star_value = None
        likes = metadata.get("like_count") or 0
        owner_value = bool(metadata.get("has_owner_response"))

        targets = (
            star_groups[star_value],
            like_groups[like_bucket(likes)],
            owner_groups[owner_value],
        )

        for group in targets:
            group["reviews"] += 1
            group["problem_total"] += len(problems)
            group["strength_total"] += len(strengths)
            group["likes_sum"] += likes
            group["problem_counter"].update(problems)
            group["strength_counter"].update(strengths)
            if star_value is not None:
                group["star_sum"] += star_value
                group["star_n"] += 1
            if not problems and not strengths:
                group["no_label"] += 1
            elif problems and strengths:
                group["mixed"] += 1
            elif problems:
                group["problem_only"] += 1
            else:
                group["strength_only"] += 1

    summary_by_star = [
        finalize_group_row(key, STAR_LABELS[key], star_groups[key]) for key in STAR_ORDER
    ]
    summary_by_like_bucket = [
        finalize_group_row(key, key, like_groups[key], include_star_mean=True) for key in LIKE_BUCKETS
    ]
    summary_by_owner_response = [
        finalize_group_row(key, OWNER_LABELS[key], owner_groups[key]) for key in OWNER_ORDER
    ]

    top_problem_labels_by_star = top_label_rows_by_group(star_groups, STAR_ORDER, "problem", TOP_K)
    top_strength_labels_by_star = top_label_rows_by_group(star_groups, STAR_ORDER, "strength", TOP_K)

    summary_payload = {
        "run_meta": {
            "runner": "analyze_fullrun_v1_batch_metadata.py",
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "record_count": TOTAL_REVIEWS,
            "input_path": str(INPUT_PATH),
        },
        "summary_by_star": summary_by_star,
        "summary_by_like_bucket": summary_by_like_bucket,
        "summary_by_owner_response": summary_by_owner_response,
        "top_problem_labels_by_star": top_problem_labels_by_star,
        "top_strength_labels_by_star": top_strength_labels_by_star,
    }

    tables_dir = OUT_DIR / "tables"
    plots_dir = OUT_DIR / "plots"
    report_path = OUT_DIR / "metadata_analysis_report.md"

    write_json(OUT_DIR / "summary.json", summary_payload)
    write_csv(
        tables_dir / "summary_by_star.csv",
        [
            "group_key",
            "group_label",
            "reviews",
            "review_pct",
            "avg_problem_labels",
            "avg_strength_labels",
            "problem_only_reviews",
            "problem_only_pct",
            "strength_only_reviews",
            "strength_only_pct",
            "mixed_reviews",
            "mixed_pct",
            "no_label_reviews",
            "no_label_pct",
            "avg_likes",
        ],
        summary_by_star,
    )
    write_csv(
        tables_dir / "summary_by_like_bucket.csv",
        [
            "group_key",
            "group_label",
            "reviews",
            "review_pct",
            "avg_problem_labels",
            "avg_strength_labels",
            "problem_only_reviews",
            "problem_only_pct",
            "strength_only_reviews",
            "strength_only_pct",
            "mixed_reviews",
            "mixed_pct",
            "no_label_reviews",
            "no_label_pct",
            "avg_likes",
            "avg_star_rating",
        ],
        summary_by_like_bucket,
    )
    write_csv(
        tables_dir / "summary_by_owner_response.csv",
        [
            "group_key",
            "group_label",
            "reviews",
            "review_pct",
            "avg_problem_labels",
            "avg_strength_labels",
            "problem_only_reviews",
            "problem_only_pct",
            "strength_only_reviews",
            "strength_only_pct",
            "mixed_reviews",
            "mixed_pct",
            "no_label_reviews",
            "no_label_pct",
            "avg_likes",
        ],
        summary_by_owner_response,
    )
    write_csv(
        tables_dir / "top_problem_labels_by_star.csv",
        ["group_key", "group_label", "rank", "label", "count"],
        top_problem_labels_by_star,
    )
    write_csv(
        tables_dir / "top_strength_labels_by_star.csv",
        ["group_key", "group_label", "rank", "label", "count"],
        top_strength_labels_by_star,
    )

    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(
        build_report(summary_by_star, summary_by_like_bucket, summary_by_owner_response),
        encoding="utf-8",
    )

    save_star_distribution_plot(plots_dir / "star_distribution.png", summary_by_star)
    save_review_mix_by_star_plot(plots_dir / "review_mix_by_star.png", summary_by_star)
    save_avg_labels_by_star_plot(plots_dir / "avg_labels_by_star.png", summary_by_star)
    save_like_salience_plot(plots_dir / "like_bucket_salience.png", summary_by_like_bucket)
    save_owner_response_plot(plots_dir / "owner_response_profile.png", summary_by_owner_response)

    print(f"[ok] wrote metadata analysis to: {OUT_DIR}")


if __name__ == "__main__":
    main()
