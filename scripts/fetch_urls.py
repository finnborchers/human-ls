#!/usr/bin/env python3
"""
Resolve canonical Google Maps place URLs from a plain-text place list.

The script reads a place list, looks up each place in Google Maps, and stores
resolved URLs in a JSON lock/log file keyed by a stable place_id.

Usage:
    python3 scripts/fetch_urls.py --headed
    python3 scripts/fetch_urls.py --places-file configs/places.txt --urls-file configs/place_urls.json
"""

from __future__ import annotations

import argparse
import json
import pathlib
import re
import shutil
import subprocess
import tempfile
import time
import unicodedata
import urllib.parse
from typing import Any

from capture_reviews import (
    CDPClient,
    DEFAULT_CHROME_PATH,
    evaluate_json,
    pump_events,
    resolve_cookie_consent,
    wait_for_json,
)


DEFAULT_PLACES_FILE = "configs/places.txt"
DEFAULT_URLS_FILE = "configs/place_urls.json"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Resolve Google Maps place URLs from a plain-text places file.")
    parser.add_argument("--places-file", default=DEFAULT_PLACES_FILE, help="Path to plain-text places file.")
    parser.add_argument("--urls-file", default=DEFAULT_URLS_FILE, help="Path to JSON URL lock/log file.")
    parser.add_argument("--chrome-path", default=DEFAULT_CHROME_PATH, help="Path to the Chrome executable.")
    parser.add_argument(
        "--headed",
        action="store_true",
        help="Launch Chrome with a visible window instead of headless mode.",
    )
    parser.add_argument("--remote-debugging-port", type=int, default=9222, help="CDP port for Chrome.")
    parser.add_argument("--lang", default="de-DE", help="Browser language to use.")
    parser.add_argument("--window-size", default="1440,2200", help="Browser window size.")
    parser.add_argument("--load-timeout", type=float, default=35.0, help="Timeout in seconds for URL resolution.")
    parser.add_argument(
        "--refresh",
        action="store_true",
        help="Force re-resolution even when a resolved URL already exists in the lock file.",
    )
    return parser.parse_args()


def utc_now_iso() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def read_places(path: pathlib.Path) -> list[str]:
    if not path.is_file():
        raise FileNotFoundError(f"Places file not found: {path}")
    lines = path.read_text(encoding="utf-8").splitlines()
    places: list[str] = []
    for raw in lines:
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        places.append(line)
    return places


def normalize_for_match(value: str) -> str:
    text = value.strip().lower()
    replacements = {
        "ä": "ae",
        "ö": "oe",
        "ü": "ue",
        "ß": "ss",
    }
    for source, target in replacements.items():
        text = text.replace(source, target)
    text = unicodedata.normalize("NFKD", text)
    text = "".join(char for char in text if not unicodedata.combining(char))
    text = re.sub(r"[^a-z0-9]+", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def slugify_place_id(place_name: str) -> str:
    normalized = normalize_for_match(place_name)
    if not normalized:
        return "place"
    return normalized.replace(" ", "-")


def names_match(requested_name: str, resolved_name: str) -> bool:
    left = normalize_for_match(requested_name)
    right = normalize_for_match(resolved_name)
    if not left or not right:
        return False
    return left in right or right in left


def load_url_map(path: pathlib.Path) -> dict[str, dict[str, Any]]:
    if not path.is_file():
        return {}
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError(f"URL lock file must contain a JSON object: {path}")
    result: dict[str, dict[str, Any]] = {}
    for key, value in data.items():
        if isinstance(key, str) and isinstance(value, dict):
            result[key] = value
    return result


def save_url_map(path: pathlib.Path, url_map: dict[str, dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(url_map, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")


def build_entry(place_id: str, place_name: str) -> dict[str, Any]:
    return {
        "place_id": place_id,
        "place_name": place_name,
        "query": place_name,
        "status": "pending",
        "resolved_url": None,
        "resolved_name": None,
        "last_checked_at": None,
        "error": None,
    }


def launch_chrome(args: argparse.Namespace, runtime_dir: pathlib.Path) -> tuple[subprocess.Popen[bytes], pathlib.Path]:
    profile_dir = runtime_dir / "chrome-profile"
    if profile_dir.exists():
        shutil.rmtree(profile_dir)
    profile_dir.mkdir(parents=True, exist_ok=True)

    command = [
        args.chrome_path,
        f"--remote-debugging-port={args.remote_debugging_port}",
        f"--user-data-dir={profile_dir}",
        "--no-first-run",
        "--no-default-browser-check",
        "--disable-default-apps",
        "--disable-sync",
        "--disable-background-networking",
        "--disable-component-update",
        "--disable-features=OptimizationGuideModelDownloading,MediaRouter",
        "--hide-scrollbars",
        "--mute-audio",
        f"--window-size={args.window_size}",
        f"--lang={args.lang}",
        "about:blank",
    ]
    if not args.headed:
        command.insert(1, "--headless=new")
    process = subprocess.Popen(command, stdout=subprocess.DEVNULL, stderr=subprocess.STDOUT)
    return process, profile_dir


def get_current_url(client: CDPClient) -> str:
    value = evaluate_json(client, "window.location.href")
    return value if isinstance(value, str) else ""


def get_place_title(client: CDPClient) -> str | None:
    expression = r"""
        (() => {
          const selectors = ['h1.DUwDvf', 'h1.fontHeadlineLarge', 'h1'];
          for (const selector of selectors) {
            const element = document.querySelector(selector);
            if (!element) {
              continue;
            }
            const text = (element.textContent || '').trim();
            if (text) {
              return text;
            }
          }
          const title = (document.title || '').replace(/\s*-\s*Google Maps.*$/i, '').trim();
          return title || null;
        })()
    """
    value = evaluate_json(client, expression)
    return value.strip() if isinstance(value, str) and value.strip() else None


def click_first_search_result(client: CDPClient) -> bool:
    expression = r"""
        (() => {
          const isVisible = (element) => {
            const style = window.getComputedStyle(element);
            const rect = element.getBoundingClientRect();
            return style.visibility !== 'hidden' && style.display !== 'none' &&
              rect.width > 0 && rect.height > 0;
          };
          const selectors = [
            'a.hfpxzc',
            'a[href*="/maps/place/"]',
            'div[role="article"] a[href*="/maps/place/"]',
          ];
          for (const selector of selectors) {
            for (const anchor of document.querySelectorAll(selector)) {
              if (!isVisible(anchor)) {
                continue;
              }
              anchor.click();
              return true;
            }
          }
          return false;
        })()
    """
    value = evaluate_json(client, expression)
    return bool(value)


def wait_for_stable_place_url(
    client: CDPClient,
    requests: dict[str, dict[str, Any]],
    timeout: float,
) -> tuple[str, str | None]:
    deadline = time.monotonic() + timeout
    started = time.monotonic()
    stable_count = 0
    last_place_url: str | None = None
    last_place_name: str | None = None
    clicked_fallback = False

    while time.monotonic() < deadline:
        pump_events(client, requests, time_limit=0.6)
        time.sleep(0.4)

        current_url = get_current_url(client)
        current_name = get_place_title(client)
        if current_name:
            last_place_name = current_name

        if "/maps/place/" in current_url:
            if current_url == last_place_url:
                stable_count += 1
            else:
                last_place_url = current_url
                stable_count = 1
            if stable_count >= 3 and last_place_url:
                return last_place_url, last_place_name
        elif not clicked_fallback and time.monotonic() - started >= 5.0:
            clicked_fallback = click_first_search_result(client)

    if last_place_url:
        return last_place_url, last_place_name
    raise RuntimeError("Timed out waiting for a stable Google Maps /maps/place/ URL.")


def resolve_place(client: CDPClient, place_query: str, timeout: float) -> tuple[str, str | None]:
    requests: dict[str, dict[str, Any]] = {}
    search_url = f"https://www.google.com/maps/search/?api=1&query={urllib.parse.quote_plus(place_query)}"
    client.call("Page.navigate", {"url": search_url}, timeout=timeout)
    pump_events(client, requests, time_limit=3.0)
    time.sleep(1.5)
    pump_events(client, requests, time_limit=2.0)

    consent_result = resolve_cookie_consent(client, requests)
    if consent_result.get("clicked"):
        pump_events(client, requests, time_limit=2.0)

    resolved_url, resolved_name = wait_for_stable_place_url(client, requests, timeout=timeout)
    if not resolved_name:
        resolved_name = get_place_title(client)
    return resolved_url, resolved_name


def main() -> int:
    args = parse_args()
    places_file = pathlib.Path(args.places_file)
    urls_file = pathlib.Path(args.urls_file)

    place_names = read_places(places_file)
    if not place_names:
        raise SystemExit(f"No places found in {places_file}")

    existing_map = load_url_map(urls_file)

    used_ids: set[str] = set()
    place_items: list[tuple[str, str]] = []
    for place_name in place_names:
        base_id = slugify_place_id(place_name)
        place_id = base_id
        suffix = 2
        while place_id in used_ids:
            place_id = f"{base_id}-{suffix}"
            suffix += 1
        used_ids.add(place_id)
        place_items.append((place_id, place_name))

    runtime_dir = pathlib.Path(tempfile.mkdtemp(prefix="maps-url-resolver-"))
    chrome_process, chrome_profile_dir = launch_chrome(args, runtime_dir)
    client: CDPClient | None = None

    reused_count = 0
    resolved_count = 0
    mismatch_count = 0
    error_count = 0

    try:
        wait_for_json(f"http://127.0.0.1:{args.remote_debugging_port}/json/version", timeout=15.0)
        targets = wait_for_json(f"http://127.0.0.1:{args.remote_debugging_port}/json/list", timeout=10.0)
        page_target = next(target for target in targets if target.get("type") == "page")
        client = CDPClient(page_target["webSocketDebuggerUrl"])

        client.call("Page.enable")
        client.call("Runtime.enable")
        client.call("Network.enable")

        for place_id, place_name in place_items:
            existing_entry = existing_map.get(place_id, {})
            entry = build_entry(place_id, place_name)
            entry["query"] = place_name

            prior_good_url = (
                existing_entry.get("resolved_url")
                if isinstance(existing_entry.get("resolved_url"), str) and existing_entry.get("resolved_url")
                else None
            )
            prior_good_name = (
                existing_entry.get("resolved_name")
                if isinstance(existing_entry.get("resolved_name"), str) and existing_entry.get("resolved_name")
                else None
            )

            if (
                not args.refresh
                and isinstance(existing_entry, dict)
                and existing_entry.get("status") == "resolved"
                and prior_good_url
            ):
                merged = dict(existing_entry)
                merged.update({"place_id": place_id, "place_name": place_name, "query": place_name})
                existing_map[place_id] = merged
                reused_count += 1
                print(f"[reused] {place_name} -> {prior_good_url}")
                continue

            try:
                resolved_url, resolved_name = resolve_place(client, place_name, timeout=args.load_timeout)
                checked_at = utc_now_iso()
                if resolved_name and names_match(place_name, resolved_name):
                    entry.update(
                        {
                            "status": "resolved",
                            "resolved_url": resolved_url,
                            "resolved_name": resolved_name,
                            "last_checked_at": checked_at,
                            "error": None,
                        }
                    )
                    resolved_count += 1
                    print(f"[resolved] {place_name} -> {resolved_url}")
                else:
                    entry.update(
                        {
                            "status": "mismatch",
                            "resolved_url": prior_good_url,
                            "resolved_name": prior_good_name,
                            "last_checked_at": checked_at,
                            "error": (
                                f"Name mismatch: requested '{place_name}', resolved '{resolved_name or 'unknown'}'"
                            ),
                        }
                    )
                    mismatch_count += 1
                    print(f"[mismatch] {place_name} -> {resolved_url} ({resolved_name or 'unknown'})")
            except Exception as exc:  # noqa: BLE001
                entry.update(
                    {
                        "status": "error",
                        "resolved_url": prior_good_url,
                        "resolved_name": prior_good_name,
                        "last_checked_at": utc_now_iso(),
                        "error": str(exc),
                    }
                )
                error_count += 1
                print(f"[error] {place_name}: {exc}")

            existing_map[place_id] = entry
            save_url_map(urls_file, existing_map)

        save_url_map(urls_file, existing_map)
        print(f"Saved URL lock file: {urls_file}")
        print(
            f"Summary: resolved={resolved_count}, reused={reused_count}, mismatch={mismatch_count}, error={error_count}"
        )
        return 0
    finally:
        if client is not None:
            client.close()
        chrome_process.terminate()
        try:
            chrome_process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            chrome_process.kill()
        if chrome_profile_dir.exists():
            shutil.rmtree(chrome_profile_dir, ignore_errors=True)
        if runtime_dir.exists():
            shutil.rmtree(runtime_dir, ignore_errors=True)


if __name__ == "__main__":
    raise SystemExit(main())
