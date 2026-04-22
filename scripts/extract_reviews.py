#!/usr/bin/env python3
"""
Extract readable Google Maps reviews from a saved capture response body.

The script is intentionally tailored to the current captured Maps response
shape, but it can be reused on future capture folders as long as Google keeps
roughly the same nested review structure.

Usage:
    python3 scripts/extract_reviews.py
    python3 scripts/extract_reviews.py --input-dir artifacts/google-maps-review-capture-headed-2
    python3 scripts/extract_reviews.py --input-file artifacts/.../request_bodies/21077.211_response.txt
"""

from __future__ import annotations

import argparse
import html
import json
import re
import sys
from pathlib import Path
from typing import Any


DEFAULT_INPUT_DIR = "artifacts/google-maps-review-capture-headed-2"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Extract a clean review JSON file from a saved Google Maps capture response."
    )
    parser.add_argument(
        "--input-dir",
        default=DEFAULT_INPUT_DIR,
        help="Capture directory containing request_bodies/ and other saved artifacts.",
    )
    parser.add_argument(
        "--input-file",
        help="Explicit response-body file to parse. Overrides --input-dir selection.",
    )
    parser.add_argument(
        "--output",
        help="Output JSON path. Defaults to reviews.json in the chosen capture directory.",
    )
    return parser.parse_args()


def fail(message: str) -> "NoReturn":
    raise SystemExit(message)


def strip_xssi_prefix(text: str) -> str:
    if text.startswith(")]}'"):
        parts = text.split("\n", 1)
        return parts[1] if len(parts) == 2 else ""
    return text


def list_input_files(input_dir: Path) -> list[Path]:
    request_bodies_dir = input_dir / "request_bodies"
    if not request_bodies_dir.is_dir():
        fail(f"No request_bodies directory found under {input_dir}")

    candidates = sorted(request_bodies_dir.glob("*_response.txt"))
    if not candidates:
        fail(f"No *_response.txt files found under {request_bodies_dir}")
    return candidates


def normalize_review_text(text: str) -> str:
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def normalize_review_time(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    normalized = html.unescape(value).replace("\xa0", " ")
    normalized = re.sub(r"\s+", " ", normalized).strip()
    return normalized or None


def normalize_star_rating(value: Any) -> int | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value if 1 <= value <= 5 else None
    if isinstance(value, float):
        rounded = int(value)
        if abs(value - rounded) < 1e-9 and 1 <= rounded <= 5:
            return rounded
    return None


def parse_star_rating_label(label: str | None) -> int | None:
    if not isinstance(label, str):
        return None
    decoded = html.unescape(label).replace("\xa0", " ").strip()
    if not re.search(r"\b(?:Stern|Sterne|star|stars)\b", decoded, flags=re.I):
        return None
    match = re.search(r"\b([1-5])\b", decoded)
    if not match:
        return None
    return int(match.group(1))


def extract_star_rating_from_structured_metadata(reviewer_metadata: Any) -> int | None:
    if not isinstance(reviewer_metadata, list):
        return None
    try:
        return normalize_star_rating(reviewer_metadata[13][4])
    except (IndexError, TypeError):
        return None


def extract_review_time_from_structured_metadata(reviewer_metadata: Any) -> str | None:
    if not isinstance(reviewer_metadata, list):
        return None
    try:
        return normalize_review_time(reviewer_metadata[6])
    except (IndexError, TypeError):
        return None


def extract_star_rating_from_html_fragment(fragment: str) -> int | None:
    match = re.search(
        r'aria-label="(?P<label>[^"]*(?:Stern|Sterne|star|stars)[^"]*)"',
        fragment,
        flags=re.I,
    )
    if not match:
        return None
    return parse_star_rating_label(match.group("label"))


def extract_review_time_from_html_fragment(fragment: str) -> str | None:
    match = re.search(
        r'<span class="rsqaWe">(?P<time>.*?)</span>',
        fragment,
        flags=re.I | re.S,
    )
    if not match:
        return None
    raw_time = strip_html_tags(match.group("time"))
    return normalize_review_time(raw_time)


def is_review_id(value: Any) -> bool:
    return isinstance(value, str) and value.startswith("Ci9DQUlR")


def looks_like_reviewer_block(value: Any) -> bool:
    if not isinstance(value, list) or len(value) < 6:
        return False
    name = value[0]
    profile_image = value[1]
    profile_links = value[2]
    return (
        isinstance(name, str)
        and bool(name.strip())
        and isinstance(profile_image, str)
        and "googleusercontent.com" in profile_image
        and isinstance(profile_links, list)
    )


def looks_like_text_block(value: Any) -> bool:
    if not isinstance(value, list) or len(value) < 16:
        return False
    language = value[14]
    content = value[15]
    return isinstance(language, list) and isinstance(content, list)


def extract_text_from_text_block(text_block: list[Any]) -> str | None:
    candidates = text_block[15] if len(text_block) > 15 else None
    if not isinstance(candidates, list):
        return None
    for candidate in candidates:
        if isinstance(candidate, list) and candidate:
            maybe_text = candidate[0]
            if isinstance(maybe_text, str) and maybe_text.strip():
                return normalize_review_text(maybe_text)
    return None


def extract_structured_reviews(data: Any) -> list[dict[str, Any]]:
    reviews: list[dict[str, Any]] = []

    def walk(node: Any) -> None:
        if isinstance(node, list):
            if node and isinstance(node[0], list):
                first = node[0]
                if (
                    isinstance(first, list)
                    and len(first) >= 2
                    and isinstance(first[0], list)
                    and first[0]
                    and is_review_id(first[0][0])
                    and isinstance(first[0][1], list)
                ):
                    for item in node:
                        review = parse_review_entry(item)
                        if review is not None:
                            reviews.append(review)
            for child in node:
                walk(child)
        elif isinstance(node, dict):
            for child in node.values():
                walk(child)

    walk(data)
    return dedupe_reviews(reviews)


def parse_review_entry(entry: Any) -> dict[str, Any] | None:
    if not isinstance(entry, list) or not entry:
        return None

    head = entry[0]
    if not isinstance(head, list) or len(head) < 3:
        return None

    review_id = head[0]
    reviewer_metadata = head[1]
    text_block = head[2]
    if not is_review_id(review_id) or not isinstance(reviewer_metadata, list):
        return None

    reviewer_name: str | None = None
    review_text: str | None = None
    star_rating: int | None = extract_star_rating_from_structured_metadata(reviewer_metadata)
    review_time: str | None = extract_review_time_from_structured_metadata(reviewer_metadata)

    # Known current shape:
    # head[1][4][5][0] -> reviewer name
    # head[2][15][0][0] -> review text
    try:
        reviewer_block = reviewer_metadata[4][5]
        if looks_like_reviewer_block(reviewer_block):
            reviewer_name = reviewer_block[0].strip()
    except (IndexError, TypeError):
        reviewer_name = None

    try:
        if looks_like_text_block(text_block):
            review_text = extract_text_from_text_block(text_block)
    except (IndexError, TypeError):
        review_text = None

    # Fallback: walk for a reviewer-like block and text block if the exact
    # offsets drift slightly in future captures.
    if not reviewer_name or not review_text:
        fallback_name, fallback_text = parse_review_entry_fallback(head)
        reviewer_name = reviewer_name or fallback_name
        review_text = review_text or fallback_text

    if not reviewer_name or not review_text:
        return None

    return {
        "review_id": review_id,
        "reviewer_name": reviewer_name,
        "review_text": review_text,
        "star_rating": star_rating,
        "review_time": review_time,
    }


def parse_review_entry_fallback(metadata: list[Any]) -> tuple[str | None, str | None]:
    reviewer_name: str | None = None
    review_text: str | None = None

    def walk(node: Any) -> None:
        nonlocal reviewer_name, review_text
        if reviewer_name and review_text:
            return
        if isinstance(node, list):
            if reviewer_name is None and looks_like_reviewer_block(node):
                reviewer_name = node[0].strip()
            if review_text is None and looks_like_text_block(node):
                review_text = extract_text_from_text_block(node)
            for child in node:
                walk(child)

    walk(metadata)
    return reviewer_name, review_text


def dedupe_reviews(reviews: list[dict[str, Any]]) -> list[dict[str, Any]]:
    unique_reviews: dict[str | tuple[str, str], dict[str, Any]] = {}
    for review in reviews:
        normalized_review = {
            "review_id": review.get("review_id"),
            "reviewer_name": review["reviewer_name"].strip(),
            "review_text": normalize_review_text(review["review_text"]),
            "star_rating": normalize_star_rating(review.get("star_rating")),
            "review_time": normalize_review_time(review.get("review_time")),
        }
        review_id = review.get("review_id")
        key: str | tuple[str, str]
        if isinstance(review_id, str) and review_id:
            key = review_id
        else:
            key = (
                normalized_review["reviewer_name"].casefold(),
                normalized_review["review_text"].casefold(),
            )

        existing = unique_reviews.get(key)
        if existing is None:
            unique_reviews[key] = normalized_review
            continue

        if len(normalized_review["review_text"]) > len(existing["review_text"]):
            winner = dict(normalized_review)
            loser = existing
        else:
            winner = dict(existing)
            loser = normalized_review
        if winner.get("star_rating") is None and loser.get("star_rating") is not None:
            winner["star_rating"] = loser["star_rating"]
        if winner.get("review_time") is None and loser.get("review_time") is not None:
            winner["review_time"] = loser["review_time"]
        unique_reviews[key] = winner

    return list(unique_reviews.values())


def serialize_reviews(reviews: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        {
            "reviewer_name": review["reviewer_name"],
            "review_text": review["review_text"],
            "star_rating": review.get("star_rating"),
            "review_time": review.get("review_time"),
        }
        for review in reviews
    ]


def load_response_json(input_file: Path) -> Any:
    raw_text = input_file.read_text(encoding="utf-8", errors="ignore")
    cleaned_text = strip_xssi_prefix(raw_text)
    try:
        return json.loads(cleaned_text)
    except json.JSONDecodeError as exc:
        raise ValueError(f"Could not parse JSON from {input_file}: {exc}") from exc


def strip_html_tags(text: str) -> str:
    return re.sub(r"<[^>]+>", "", text)


def extract_reviews_from_saved_html(input_file: Path) -> list[dict[str, Any]]:
    text = input_file.read_text(encoding="utf-8", errors="ignore")
    matches = re.finditer(
        r'<div class="jftiEf fontBodyMedium [^"]*" aria-label="(?P<name>[^"]+)" data-review-id="(?P<review_id>[^"]+)".*?<span class="wiI7pd">(?P<text>.*?)</span>',
        text,
        flags=re.S,
    )

    reviews: list[dict[str, Any]] = []
    for match in matches:
        reviewer_name = html.unescape(match.group("name")).strip()
        review_text = html.unescape(strip_html_tags(match.group("text")))
        review_text = normalize_review_text(review_text)
        star_rating = extract_star_rating_from_html_fragment(match.group(0))
        review_time = extract_review_time_from_html_fragment(match.group(0))
        if not reviewer_name or not review_text:
            continue
        reviews.append(
            {
                "review_id": match.group("review_id"),
                "reviewer_name": reviewer_name,
                "review_text": review_text,
                "star_rating": star_rating,
                "review_time": review_time,
            }
        )
    return dedupe_reviews(reviews)


def main() -> int:
    args = parse_args()

    if args.input_file:
        input_file = Path(args.input_file)
        if not input_file.is_file():
            fail(f"Input file not found: {input_file}")
        capture_dir = input_file.parent.parent if input_file.parent.name == "request_bodies" else input_file.parent
        input_files = [input_file]
    else:
        capture_dir = Path(args.input_dir)
        if not capture_dir.is_dir():
            fail(f"Input directory not found: {capture_dir}")
        input_files = list_input_files(capture_dir)

    output_path = Path(args.output) if args.output else capture_dir / "reviews.json"

    parsed_source_files: list[str] = []
    reviews_by_file: list[dict[str, Any]] = []

    for candidate in input_files:
        try:
            data = load_response_json(candidate)
        except ValueError as exc:
            if args.input_file:
                fail(str(exc))
            continue

        file_reviews = extract_structured_reviews(data)
        if not file_reviews:
            continue

        parsed_source_files.append(str(candidate))
        reviews_by_file.extend(file_reviews)

    if not args.input_file:
        html_candidates = [capture_dir / "page_reviews_after_scroll.html", capture_dir / "page_reviews.html"]
        html_candidates.extend(sorted(capture_dir.glob("page_reviews_growth_*.html")))
        for html_path in html_candidates:
            if not html_path.is_file():
                continue
            html_reviews = extract_reviews_from_saved_html(html_path)
            if not html_reviews:
                continue
            parsed_source_files.append(str(html_path))
            reviews_by_file.extend(html_reviews)

    reviews = dedupe_reviews(reviews_by_file)
    if not reviews:
        if args.input_file:
            fail(f"No reviews found in {input_file}")
        fail(f"No reviews found in any response file under {capture_dir / 'request_bodies'}")

    serialized_reviews = serialize_reviews(reviews)

    result = {
        "source_files": parsed_source_files,
        "parsed_file_count": len(parsed_source_files),
        "review_count": len(serialized_reviews),
        "reviews": serialized_reviews,
    }

    output_path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Saved extracted reviews to {output_path}")
    print(f"Review count: {len(reviews)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
