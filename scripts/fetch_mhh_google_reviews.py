#!/usr/bin/env python3
"""
Fetch the Google Places details and available public reviews for Hannover Medical School.

This script uses the official Google Places API instead of scraping Google Maps.
Google only returns up to five reviews for a place through the Places API.

Usage:
    export GOOGLE_MAPS_API_KEY="your-key"
    python3 scripts/fetch_mhh_google_reviews.py

Optional:
    python3 scripts/fetch_mhh_google_reviews.py --query "Medizinische Hochschule Hannover"
    python3 scripts/fetch_mhh_google_reviews.py --output mhh_reviews.json
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from typing import Any


TEXT_SEARCH_URL = "https://places.googleapis.com/v1/places:searchText"
PLACE_DETAILS_URL = "https://places.googleapis.com/v1/places/{place_id}"
DEFAULT_QUERY = "Medizinische Hochschule Hannover"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Search for Hannover Medical School via Google Places and fetch "
            "the available public review data."
        )
    )
    parser.add_argument(
        "--query",
        default=DEFAULT_QUERY,
        help="Text query used for the Google Places text search.",
    )
    parser.add_argument(
        "--language-code",
        default="de",
        help="Language code for search and reviews, for example 'de' or 'en'.",
    )
    parser.add_argument(
        "--region-code",
        default="DE",
        help="CLDR region code, defaults to Germany.",
    )
    parser.add_argument(
        "--delay-seconds",
        type=float,
        default=1.5,
        help="Small pause between API calls.",
    )
    parser.add_argument(
        "--output",
        help="Optional JSON output path.",
    )
    return parser.parse_args()


def get_api_key() -> str:
    api_key = os.environ.get("GOOGLE_MAPS_API_KEY")
    if not api_key:
        sys.exit("Missing GOOGLE_MAPS_API_KEY environment variable.")
    return api_key


def post_json(url: str, payload: dict[str, Any], headers: dict[str, str]) -> dict[str, Any]:
    data = json.dumps(payload).encode("utf-8")
    request = urllib.request.Request(url, data=data, headers=headers, method="POST")
    return read_json(request)


def get_json(url: str, headers: dict[str, str]) -> dict[str, Any]:
    request = urllib.request.Request(url, headers=headers, method="GET")
    return read_json(request)


def read_json(request: urllib.request.Request) -> dict[str, Any]:
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            return json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        raise SystemExit(f"Google API request failed with {exc.code}: {body}") from exc
    except urllib.error.URLError as exc:
        raise SystemExit(f"Could not reach Google API: {exc}") from exc


def search_place(api_key: str, query: str, language_code: str, region_code: str) -> dict[str, Any]:
    headers = {
        "Content-Type": "application/json",
        "X-Goog-Api-Key": api_key,
        "X-Goog-FieldMask": ",".join(
            [
                "places.id",
                "places.displayName",
                "places.formattedAddress",
                "places.googleMapsUri",
                "places.primaryTypeDisplayName",
            ]
        ),
    }
    payload = {
        "textQuery": query,
        "languageCode": language_code,
        "regionCode": region_code,
        "maxResultCount": 1,
    }
    response = post_json(TEXT_SEARCH_URL, payload, headers)
    places = response.get("places", [])
    if not places:
        raise SystemExit(f"No place found for query: {query}")
    return places[0]


def fetch_place_details(api_key: str, place_id: str, language_code: str, region_code: str) -> dict[str, Any]:
    headers = {
        "X-Goog-Api-Key": api_key,
        "X-Goog-FieldMask": ",".join(
            [
                "id",
                "displayName",
                "formattedAddress",
                "googleMapsUri",
                "location",
                "nationalPhoneNumber",
                "rating",
                "userRatingCount",
                "websiteUri",
                "reviews",
            ]
        ),
    }
    params = urllib.parse.urlencode(
        {
            "languageCode": language_code,
            "regionCode": region_code,
        }
    )
    url = PLACE_DETAILS_URL.format(place_id=urllib.parse.quote(place_id, safe="")) + f"?{params}"
    return get_json(url, headers)


def main() -> None:
    args = parse_args()
    api_key = get_api_key()

    place = search_place(
        api_key=api_key,
        query=args.query,
        language_code=args.language_code,
        region_code=args.region_code,
    )
    time.sleep(args.delay_seconds)
    details = fetch_place_details(
        api_key=api_key,
        place_id=place["id"],
        language_code=args.language_code,
        region_code=args.region_code,
    )

    reviews = details.get("reviews", [])
    result = {
        "query": args.query,
        "place": {
            "id": details.get("id"),
            "name": details.get("displayName", {}).get("text"),
            "address": details.get("formattedAddress"),
            "google_maps_uri": details.get("googleMapsUri"),
            "website_uri": details.get("websiteUri"),
            "national_phone_number": details.get("nationalPhoneNumber"),
            "rating": details.get("rating"),
            "user_rating_count": details.get("userRatingCount"),
            "review_count_returned": len(reviews),
            "api_note": "Google Places returns up to five reviews for a place.",
        },
        "reviews": reviews,
    }

    if args.output:
        with open(args.output, "w", encoding="utf-8") as handle:
            json.dump(result, handle, ensure_ascii=False, indent=2)
        print(f"Saved output to {args.output}")
    else:
        print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
