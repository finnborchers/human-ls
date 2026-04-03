#!/usr/bin/env python3
"""
Fetch a Google Maps page and save the raw HTTP response body to disk.

Usage:
    python3 scripts/fetch_google_maps_page.py
    python3 scripts/fetch_google_maps_page.py --output-dir artifacts/google-maps-page
"""

from __future__ import annotations

import argparse
import json
import pathlib
import sys
import urllib.error
import urllib.request


DEFAULT_URL = (
    "https://www.google.com/maps/place/Medizinische+Hochschule+Hannover/"
    "@52.3836782,9.8023805,17z/data=!4m8!3m7!1s0x47b00c83ca3e6511:0x507859bbb59bcfe!"
    "8m2!3d52.383675!4d9.8049554!9m1!1b1!16s%2Fm%2F02q_jhp?entry=ttu&"
    "g_ep=EgoyMDI2MDMxNy4wIKXMDSoASAFQAw%3D%3D"
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Fetch a URL and save the raw response body plus metadata."
    )
    parser.add_argument("--url", default=DEFAULT_URL, help="URL to fetch.")
    parser.add_argument(
        "--output-dir",
        default="artifacts/google-maps-page",
        help="Directory where the response files will be written.",
    )
    parser.add_argument(
        "--timeout",
        type=float,
        default=30.0,
        help="HTTP timeout in seconds.",
    )
    return parser.parse_args()


def choose_extension(content_type: str) -> str:
    content_type = content_type.lower()
    if "text/html" in content_type:
        return ".html"
    if "application/json" in content_type:
        return ".json"
    if "text/plain" in content_type:
        return ".txt"
    return ".bin"


def main() -> int:
    args = parse_args()
    output_dir = pathlib.Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    request = urllib.request.Request(
        args.url,
        headers={
            "User-Agent": (
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/123.0.0.0 Safari/537.36"
            ),
            "Accept-Language": "en-US,en;q=0.9",
        },
    )

    try:
        with urllib.request.urlopen(request, timeout=args.timeout) as response:
            body = response.read()
            content_type = response.headers.get("Content-Type", "")
            body_path = output_dir / f"response_body{choose_extension(content_type)}"
            body_path.write_bytes(body)

            metadata = {
                "requested_url": args.url,
                "final_url": response.geturl(),
                "status": response.status,
                "reason": response.reason,
                "content_type": content_type,
                "content_length": len(body),
                "headers": dict(response.headers.items()),
                "body_path": str(body_path),
            }
    except urllib.error.HTTPError as exc:
        body = exc.read()
        body_path = output_dir / "response_body_error.bin"
        body_path.write_bytes(body)
        metadata = {
            "requested_url": args.url,
            "final_url": exc.geturl(),
            "status": exc.code,
            "reason": exc.reason,
            "content_type": exc.headers.get("Content-Type", ""),
            "content_length": len(body),
            "headers": dict(exc.headers.items()),
            "body_path": str(body_path),
            "error": "HTTPError",
        }
    except urllib.error.URLError as exc:
        print(f"Request failed: {exc}", file=sys.stderr)
        return 1

    metadata_path = output_dir / "response_metadata.json"
    metadata_path.write_text(json.dumps(metadata, indent=2), encoding="utf-8")

    print(f"Saved response body to {body_path}")
    print(f"Saved metadata to {metadata_path}")
    print(f"HTTP status: {metadata['status']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
