#!/usr/bin/env python3

import json
import os
from pathlib import Path

TMP_CACHE_DIR = Path("/private/tmp/human_ls_matplotlib")
TMP_CACHE_DIR.mkdir(parents=True, exist_ok=True)
os.environ.setdefault("MPLCONFIGDIR", str(TMP_CACHE_DIR / "mplconfig"))
os.environ.setdefault("XDG_CACHE_HOME", str(TMP_CACHE_DIR / "cache"))

import matplotlib

matplotlib.use("Agg")

import matplotlib.pyplot as plt
import numpy as np


BASE_DIR = Path("analysis/llm/benchmark_comparison")
COMPARE_PATH = Path(
    os.getenv("BENCHMARK_COMPARE_PATH", str(BASE_DIR / "reviews_v1_120_compare.json"))
)
OUT_PATH = Path(
    os.getenv("BENCHMARK_PLOT_OUT_PATH", str(BASE_DIR / "reviews_v1_120_plot.png"))
)

BUCKETS = ("positive", "negative", "mixed_hard")
BUCKET_LABELS = ("Positive", "Negative", "Mixed")
DOMAINS = ("access", "admin", "communication", "staff", "care", "coordination", "environment", "inclusion")
DOMAIN_LABELS = ("Access", "Admin", "Communication", "Staff", "Care", "Coordination", "Environment", "Inclusion")

BENCHMARK_COLOR = "#2A9D8F"
MODEL_COLOR = "#E76F51"


def load_json(path: Path) -> dict:
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def draw_grouped_totals(ax, keys, display_labels, stats_lookup, title):
    x = np.arange(len(keys))
    width = 0.34

    benchmark = np.array([stats_lookup[key]["benchmark_total_labels"] for key in keys])
    model = np.array([stats_lookup[key]["predicted_total_labels"] for key in keys])

    bars_b = ax.bar(x - width / 2, benchmark, width, color=BENCHMARK_COLOR)
    bars_m = ax.bar(x + width / 2, model, width, color=MODEL_COLOR)

    ymax = max(benchmark.max(), model.max()) if len(benchmark) else 0
    offset = max(ymax * 0.015, 2)
    ax.set_ylim(0, ymax * 1.18 if ymax else 1)

    for bar in list(bars_b) + list(bars_m):
        height = bar.get_height()
        ax.text(
            bar.get_x() + bar.get_width() / 2,
            height + offset,
            f"{int(height)}",
            ha="center",
            va="bottom",
            fontsize=10,
        )

    ax.set_xticks(x)
    ax.set_xticklabels(display_labels, rotation=20 if len(keys) > 4 else 0, ha="right" if len(keys) > 4 else "center")
    ax.set_title(title, fontsize=13, pad=10)
    ax.set_ylabel("Labels", fontsize=11)
    ax.grid(axis="y", linestyle="--", alpha=0.25)
    ax.tick_params(axis="both", labelsize=10)


def draw_top_labels(ax, items, title, color):
    top_items = items[:8]
    if not top_items:
        ax.set_title(title, fontsize=13, pad=10)
        ax.text(0.5, 0.5, "No labels", ha="center", va="center", fontsize=11)
        ax.set_axis_off()
        return

    labels = [label for label, _ in top_items]
    counts = [count for _, count in top_items]
    y = np.arange(len(labels))

    ax.barh(y, counts, color=color)
    ax.set_yticks(y)
    ax.set_yticklabels(labels, fontsize=10)
    ax.invert_yaxis()
    ax.set_title(title, fontsize=13, pad=10)
    ax.set_xlabel("Count", fontsize=11)
    ax.grid(axis="x", linestyle="--", alpha=0.25)
    ax.tick_params(axis="x", labelsize=10)

    xmax = max(counts)
    offset = max(xmax * 0.03, 0.15)
    for yi, count in enumerate(counts):
        ax.text(count + offset, yi, str(count), va="center", ha="left", fontsize=10)


def main() -> None:
    data = load_json(COMPARE_PATH)
    overall = data["overall"]

    plt.rcParams.update(
        {
            "font.size": 11,
            "axes.titlesize": 13,
            "axes.labelsize": 11,
            "xtick.labelsize": 10,
            "ytick.labelsize": 10,
        }
    )

    fig, axes = plt.subplots(3, 2, figsize=(16.5, 11.7), dpi=300)
    fig.patch.set_facecolor("white")
    fig.suptitle(
        (
            f"Benchmark Comparison for {overall['total_reviews']} Reviews\n"
            f"Benchmark (B) total: {overall['benchmark_total_labels']} | "
            f"Model (M) total: {overall['predicted_total_labels']} | "
            f"Exact review matches: {overall['exact_matches']}/{overall['total_reviews']}"
        ),
        fontsize=16,
        y=0.985,
    )

    draw_grouped_totals(axes[0, 0], BUCKETS, BUCKET_LABELS, data["buckets"], "Bucket totals")
    draw_grouped_totals(axes[0, 1], DOMAINS, DOMAIN_LABELS, data["domains"], "Domain totals")
    draw_top_labels(axes[1, 0], data["top_missing_problem_labels"], "Top missing problem labels", MODEL_COLOR)
    draw_top_labels(axes[1, 1], data["top_missing_strength_labels"], "Top missing strength labels", MODEL_COLOR)
    draw_top_labels(axes[2, 0], data["top_extra_problem_labels"], "Top extra problem labels", MODEL_COLOR)
    draw_top_labels(axes[2, 1], data["top_extra_strength_labels"], "Top extra strength labels", MODEL_COLOR)

    legend_handles = [
        plt.Rectangle((0, 0), 1, 1, color=BENCHMARK_COLOR),
        plt.Rectangle((0, 0), 1, 1, color=MODEL_COLOR),
    ]
    fig.legend(
        legend_handles,
        ["Benchmark (B)", "Model (M)"],
        loc="upper right",
        bbox_to_anchor=(0.985, 0.985),
        frameon=False,
        fontsize=11,
        ncol=2,
        handlelength=1.6,
        columnspacing=1.2,
    )

    plt.tight_layout(rect=(0, 0, 1, 0.94))
    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    plt.savefig(OUT_PATH, dpi=300, bbox_inches="tight")
    plt.close(fig)
    print(f"[ok] wrote plot: {OUT_PATH}")


if __name__ == "__main__":
    main()
