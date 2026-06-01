#!/usr/bin/env python3
"""
Launch headless Chrome, open a Google Maps place page, and capture review-related
network requests from the Chrome DevTools Protocol (CDP).

This script captures review-loading requests and saves artifacts that can be
parsed later. By default it keeps output lean (summary, final review HTML, and
request bodies). Optional debug artifacts can be retained via flags.

Usage:
    python3 scripts/capture_reviews.py
    python3 scripts/capture_reviews.py --place-id medizinische-hochschule-hannover
    python3 scripts/capture_reviews.py --place-id medizinische-hochschule-hannover --headless
"""

from __future__ import annotations

import argparse
import base64
import html
import hashlib
import json
import os
import pathlib
import queue
import random
import re
import shutil
import socket
import ssl
import struct
import subprocess
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from typing import Any


DEFAULT_URL = (
    "https://www.google.com/maps/place/Medizinische+Hochschule+Hannover/"
    "@52.3836782,9.8023805,17z/data=!4m8!3m7!1s0x47b00c83ca3e6511:0x507859bbb59bcfe!"
    "8m2!3d52.383675!4d9.8049554!9m1!1b1!16s%2Fm%2F02q_jhp?entry=ttu&"
    "g_ep=EgoyMDI2MDMxNy4wIKXMDSoASAFQAw%3D%3D"
)
DEFAULT_CHROME_PATH = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
DEFAULT_OUTPUT_DIR = "artifacts/google-maps-review-capture"
DEFAULT_URLS_FILE = "configs/place_urls.json"
DEFAULT_ARTIFACTS_ROOT = "artifacts"


class WebSocketClient:
    """Minimal WebSocket client for CDP so the script has no extra dependencies."""

    def __init__(self, ws_url: str) -> None:
        parsed = urllib.parse.urlparse(ws_url)
        port = parsed.port or (443 if parsed.scheme == "wss" else 80)
        raw_socket = socket.create_connection((parsed.hostname, port), timeout=10)
        if parsed.scheme == "wss":
            context = ssl.create_default_context()
            self.sock = context.wrap_socket(raw_socket, server_hostname=parsed.hostname)
        else:
            self.sock = raw_socket
        self.sock.settimeout(10)
        self._handshake(parsed)

    def _handshake(self, parsed: urllib.parse.ParseResult) -> None:
        key = base64.b64encode(os.urandom(16)).decode("ascii")
        path = parsed.path or "/"
        if parsed.query:
            path += f"?{parsed.query}"
        request = (
            f"GET {path} HTTP/1.1\r\n"
            f"Host: {parsed.hostname}:{parsed.port or 80}\r\n"
            "Upgrade: websocket\r\n"
            "Connection: Upgrade\r\n"
            f"Sec-WebSocket-Key: {key}\r\n"
            "Sec-WebSocket-Version: 13\r\n"
            "\r\n"
        ).encode("ascii")
        self.sock.sendall(request)
        response = self._read_http_headers()
        if b"101" not in response.split(b"\r\n", 1)[0]:
            raise RuntimeError(f"WebSocket handshake failed: {response!r}")
        accept = None
        for line in response.decode("latin-1").split("\r\n"):
            if line.lower().startswith("sec-websocket-accept:"):
                accept = line.split(":", 1)[1].strip()
                break
        expected = base64.b64encode(
            hashlib.sha1((key + "258EAFA5-E914-47DA-95CA-C5AB0DC85B11").encode("ascii")).digest()
        ).decode("ascii")
        if accept != expected:
            raise RuntimeError("WebSocket handshake returned an unexpected accept key.")

    def _read_http_headers(self) -> bytes:
        data = bytearray()
        while b"\r\n\r\n" not in data:
            chunk = self.sock.recv(4096)
            if not chunk:
                break
            data.extend(chunk)
        return bytes(data)

    def _read_exact(self, size: int) -> bytes:
        data = bytearray()
        while len(data) < size:
            chunk = self.sock.recv(size - len(data))
            if not chunk:
                raise RuntimeError("Socket closed while reading a WebSocket frame.")
            data.extend(chunk)
        return bytes(data)

    def send_text(self, text: str) -> None:
        payload = text.encode("utf-8")
        frame = bytearray()
        frame.append(0x81)
        mask_bit = 0x80
        length = len(payload)
        if length < 126:
            frame.append(mask_bit | length)
        elif length < 65536:
            frame.append(mask_bit | 126)
            frame.extend(struct.pack("!H", length))
        else:
            frame.append(mask_bit | 127)
            frame.extend(struct.pack("!Q", length))
        mask = os.urandom(4)
        frame.extend(mask)
        frame.extend(byte ^ mask[index % 4] for index, byte in enumerate(payload))
        self.sock.sendall(frame)

    def recv_text(self) -> str | None:
        fragments: list[bytes] = []
        while True:
            first, second = self._read_exact(2)
            opcode = first & 0x0F
            masked = bool(second & 0x80)
            length = second & 0x7F
            if length == 126:
                length = struct.unpack("!H", self._read_exact(2))[0]
            elif length == 127:
                length = struct.unpack("!Q", self._read_exact(8))[0]
            mask = self._read_exact(4) if masked else b""
            payload = self._read_exact(length) if length else b""
            if masked:
                payload = bytes(byte ^ mask[index % 4] for index, byte in enumerate(payload))

            if opcode == 0x8:
                return None
            if opcode == 0x9:
                self._send_pong(payload)
                continue
            if opcode == 0xA:
                continue
            if opcode not in {0x0, 0x1}:
                continue

            fragments.append(payload)
            if first & 0x80:
                return b"".join(fragments).decode("utf-8", errors="replace")

    def _send_pong(self, payload: bytes) -> None:
        frame = bytearray([0x8A])
        length = len(payload)
        if length < 126:
            frame.append(length)
        elif length < 65536:
            frame.append(126)
            frame.extend(struct.pack("!H", length))
        else:
            frame.append(127)
            frame.extend(struct.pack("!Q", length))
        frame.extend(payload)
        self.sock.sendall(frame)

    def close(self) -> None:
        try:
            self.sock.close()
        except OSError:
            pass


class CDPClient:
    def __init__(self, ws_url: str) -> None:
        self.ws = WebSocketClient(ws_url)
        self._next_id = 0
        self._response_condition = threading.Condition()
        self._responses: dict[int, dict[str, Any]] = {}
        self._events: "queue.Queue[dict[str, Any]]" = queue.Queue()
        self._running = True
        self._reader_thread = threading.Thread(target=self._reader_loop, daemon=True)
        self._reader_thread.start()

    def _reader_loop(self) -> None:
        while self._running:
            try:
                message = self.ws.recv_text()
            except OSError:
                break
            if message is None:
                break
            parsed = json.loads(message)
            if "id" in parsed:
                with self._response_condition:
                    self._responses[parsed["id"]] = parsed
                    self._response_condition.notify_all()
            else:
                self._events.put(parsed)

    def call(self, method: str, params: dict[str, Any] | None = None, timeout: float = 15.0) -> dict[str, Any]:
        with self._response_condition:
            self._next_id += 1
            message_id = self._next_id
        payload: dict[str, Any] = {"id": message_id, "method": method}
        if params:
            payload["params"] = params
        self.ws.send_text(json.dumps(payload))

        deadline = time.time() + timeout
        with self._response_condition:
            while message_id not in self._responses:
                remaining = deadline - time.time()
                if remaining <= 0:
                    raise TimeoutError(f"Timed out waiting for CDP response: {method}")
                self._response_condition.wait(timeout=remaining)
            response = self._responses.pop(message_id)
        if "error" in response:
            raise RuntimeError(f"CDP {method} failed: {response['error']}")
        return response.get("result", {})

    def get_event(self, timeout: float = 1.0) -> dict[str, Any] | None:
        try:
            return self._events.get(timeout=timeout)
        except queue.Empty:
            return None

    def close(self) -> None:
        self._running = False
        self.ws.close()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Capture internal Google Maps review requests via Chrome automation."
    )
    parser.add_argument(
        "--url",
        help="Explicit Google Maps place URL to inspect. If omitted and --place-id is omitted, all resolved places from --urls-file are processed.",
    )
    parser.add_argument(
        "--place-id",
        help="Place id key from the URLs file (e.g. medizinische-hochschule-hannover). If set, resolves URL automatically.",
    )
    parser.add_argument(
        "--urls-file",
        default=DEFAULT_URLS_FILE,
        help="Path to JSON URL map used with --place-id.",
    )
    parser.add_argument(
        "--output-dir",
        default=DEFAULT_OUTPUT_DIR,
        help="Directory where capture artifacts will be written for single-place runs.",
    )
    parser.add_argument(
        "--artifacts-root",
        default=DEFAULT_ARTIFACTS_ROOT,
        help="Base directory for multi-place outputs (one folder per place_id).",
    )
    parser.add_argument(
        "--run-summary-out",
        help="Path to batch run summary JSON. Defaults to <artifacts-root>/capture_reviews_run_summary.json.",
    )
    parser.add_argument(
        "--chrome-path",
        default=DEFAULT_CHROME_PATH,
        help="Path to the Chrome executable.",
    )
    parser.add_argument(
        "--headed",
        action="store_true",
        dest="headed",
        help="Compatibility alias to force headed mode (headed is already the default).",
    )
    parser.add_argument(
        "--headless",
        action="store_false",
        dest="headed",
        help="Run Chrome in headless mode.",
    )
    parser.add_argument("--remote-debugging-port", type=int, default=9222, help="CDP port for Chrome.")
    parser.add_argument("--lang", default="de-DE", help="Browser language to use.")
    parser.add_argument("--window-size", default="1440,2200", help="Headless window size.")
    parser.add_argument("--load-timeout", type=float, default=25.0, help="Navigation timeout in seconds.")
    parser.add_argument("--review-timeout", type=float, default=20.0, help="Timeout for review UI steps.")
    parser.add_argument("--max-scrolls", type=int, default=250, help="Maximum number of scroll attempts in the review pane.")
    parser.add_argument(
        "--max-scroll-seconds",
        type=float,
        default=600.0,
        help="Maximum time to spend scrolling the review pane.",
    )
    parser.add_argument(
        "--stable-rounds",
        type=int,
        default=3,
        help="Minimum number of stable bottom rounds required in fallback mode.",
    )
    parser.add_argument("--scroll-delay", type=float, default=1.5, help="Delay between review pane scrolls.")
    parser.add_argument(
        "--bottom-wait-seconds",
        type=float,
        default=6.0,
        help="Wait time around bottom probes to give lazy-loading a chance to trigger.",
    )
    parser.add_argument(
        "--network-idle-seconds",
        type=float,
        default=8.0,
        help="Required quiet period for review-related network requests before stopping at bottom.",
    )
    parser.add_argument(
        "--no-growth-cycles",
        type=int,
        default=5,
        help="Number of bottom probe cycles with no growth before stopping.",
    )
    parser.add_argument(
        "--declared-total-settle-seconds",
        type=float,
        default=1.5,
        help="Passive settle wait used for fast stop when declared review total is reached at bottom.",
    )
    parser.add_argument(
        "--retry-runs",
        type=int,
        default=2,
        help="Maximum capture attempts. Additional attempts run with slower scrolling if count is low.",
    )
    parser.add_argument(
        "--keep-debug-artifacts",
        action="store_true",
        help="Keep extra debug artifacts (screenshots, growth HTML snapshots, request index JSON files).",
    )
    parser.add_argument(
        "--keep-browser-logs",
        action="store_true",
        help="Keep Chrome logs (chrome.log, chrome-netlog.json).",
    )
    parser.add_argument(
        "--keep-chrome-profile",
        action="store_true",
        help="Keep the temporary Chrome profile directory after capture.",
    )
    parser.set_defaults(headed=True)
    return parser.parse_args()


def wait_for_json(url: str, timeout: float) -> Any:
    deadline = time.time() + timeout
    last_error: Exception | None = None
    while time.time() < deadline:
        try:
            with urllib.request.urlopen(url, timeout=2) as response:
                return json.loads(response.read().decode("utf-8"))
        except (urllib.error.URLError, json.JSONDecodeError) as exc:
            last_error = exc
            time.sleep(0.2)
    raise RuntimeError(f"Timed out waiting for {url}: {last_error}")


def resolve_url_from_place_id(place_id: str, urls_file: pathlib.Path) -> str:
    if not urls_file.is_file():
        raise RuntimeError(f"URLs file not found: {urls_file}")
    try:
        payload = json.loads(urls_file.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"Could not parse URLs file {urls_file}: {exc}") from exc
    if not isinstance(payload, dict):
        raise RuntimeError(f"URLs file must be a JSON object keyed by place_id: {urls_file}")

    entry = payload.get(place_id)
    if not isinstance(entry, dict):
        raise RuntimeError(f"place_id '{place_id}' was not found in {urls_file}")

    status = str(entry.get("status") or "")
    resolved_url = entry.get("resolved_url")
    if status != "resolved" or not isinstance(resolved_url, str) or not resolved_url.strip():
        raise RuntimeError(
            f"place_id '{place_id}' is not resolved in {urls_file} (status={status!r}, resolved_url={resolved_url!r})"
        )
    return resolved_url.strip()


def load_resolved_places(urls_file: pathlib.Path) -> list[dict[str, str]]:
    if not urls_file.is_file():
        raise RuntimeError(f"URLs file not found: {urls_file}")
    try:
        payload = json.loads(urls_file.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"Could not parse URLs file {urls_file}: {exc}") from exc
    if not isinstance(payload, dict):
        raise RuntimeError(f"URLs file must be a JSON object keyed by place_id: {urls_file}")

    places: list[dict[str, str]] = []
    for key in sorted(payload.keys()):
        entry = payload.get(key)
        if not isinstance(entry, dict):
            continue
        status = str(entry.get("status") or "")
        resolved_url = entry.get("resolved_url")
        if status != "resolved" or not isinstance(resolved_url, str) or not resolved_url.strip():
            continue
        place_name = entry.get("place_name")
        if not isinstance(place_name, str) or not place_name.strip():
            place_name = entry.get("resolved_name")
        if not isinstance(place_name, str) or not place_name.strip():
            place_name = key
        places.append(
            {
                "place_id": key,
                "place_name": place_name.strip(),
                "url": resolved_url.strip(),
            }
        )

    if not places:
        raise RuntimeError(f"No resolved place URLs found in {urls_file}")
    return places


def utc_now_iso() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def launch_chrome(
    args: argparse.Namespace,
    output_dir: pathlib.Path,
    startup_url: str | None = None,
) -> tuple[subprocess.Popen[bytes], pathlib.Path]:
    profile_dir = output_dir / "chrome-profile"
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
        startup_url or "about:blank",
    ]
    log_handle: Any = None
    stdout_target: Any = subprocess.DEVNULL
    if args.keep_browser_logs:
        command.append(f"--log-net-log={output_dir / 'chrome-netlog.json'}")
        log_handle = (output_dir / "chrome.log").open("wb")
        stdout_target = log_handle
    if not args.headed:
        command.insert(1, "--headless=new")
    process = subprocess.Popen(command, stdout=stdout_target, stderr=subprocess.STDOUT)
    if log_handle is not None:
        log_handle.close()
    return process, profile_dir


def choose_page_target(
    targets: list[dict[str, Any]],
    expected_url: str | None,
) -> tuple[dict[str, Any], str]:
    pages = [target for target in targets if target.get("type") == "page" and target.get("webSocketDebuggerUrl")]
    if not pages:
        raise RuntimeError("No page target with a webSocketDebuggerUrl was found.")

    if not expected_url:
        return pages[-1], "latest_page_fallback"

    expected = urllib.parse.urlparse(expected_url)
    scored: list[tuple[int, int, dict[str, Any]]] = []
    for index, target in enumerate(pages):
        url = str(target.get("url") or "")
        parsed = urllib.parse.urlparse(url)
        score = 0
        if url == expected_url:
            score += 100
        if parsed.netloc and parsed.netloc == expected.netloc:
            score += 30
        if parsed.path and parsed.path == expected.path:
            score += 20
        if "/maps/" in parsed.path:
            score += 10
        if "about:blank" in url:
            score -= 50
        scored.append((score, index, target))

    scored.sort(key=lambda item: (item[0], item[1]), reverse=True)
    best_score, _, best_target = scored[0]
    if best_score >= 100:
        strategy = "exact_url_match"
    elif best_score >= 30:
        strategy = "host_path_match"
    elif best_score >= 0:
        strategy = "maps_page_fallback"
    else:
        strategy = "latest_page_fallback"
    return best_target, strategy


def save_text(path: pathlib.Path, content: str) -> None:
    path.write_text(content, encoding="utf-8")


def evaluate_json(client: CDPClient, expression: str, timeout: float = 15.0) -> Any:
    result = client.call(
        "Runtime.evaluate",
        {
            "expression": expression,
            "returnByValue": True,
            "awaitPromise": True,
        },
        timeout=timeout,
    )
    details = result.get("result", {})
    if details.get("type") == "undefined":
        return None
    return details.get("value")


def safe_evaluate_json(client: CDPClient, expression: str, timeout: float = 5.0) -> dict[str, Any]:
    try:
        return {"ok": True, "value": evaluate_json(client, expression, timeout=timeout)}
    except Exception as exc:  # noqa: BLE001
        return {
            "ok": False,
            "errorType": type(exc).__name__,
            "error": str(exc),
        }


def wait_for_predicate(client: CDPClient, expression: str, timeout: float) -> Any:
    deadline = time.time() + timeout
    last_value = None
    while time.time() < deadline:
        last_value = evaluate_json(client, expression, timeout=10.0)
        if last_value:
            return last_value
        pump_events(client, {}, time_limit=0.2)
        time.sleep(0.25)
    return last_value


def capture_screenshot(client: CDPClient, path: pathlib.Path) -> None:
    result = client.call("Page.captureScreenshot", {"format": "png"}, timeout=20.0)
    path.write_bytes(base64.b64decode(result["data"]))


def safe_capture_screenshot(
    client: CDPClient,
    path: pathlib.Path,
    run_summary: dict[str, Any],
    key: str,
) -> None:
    try:
        capture_screenshot(client, path)
        run_summary.setdefault("screenshots", {})[key] = {"saved": True, "path": str(path)}
    except Exception as exc:  # noqa: BLE001
        run_summary.setdefault("screenshots", {})[key] = {"saved": False, "error": str(exc)}


def collect_button_snapshot(client: CDPClient) -> list[dict[str, Any]]:
    expression = r"""
        (() => {
          const nodes = [...document.querySelectorAll('button,[role="button"]')];
          return nodes.slice(0, 120).map((element) => ({
            text: (element.innerText || element.textContent || '').trim().slice(0, 160),
            ariaLabel: element.getAttribute('aria-label') || '',
            jsaction: element.getAttribute('jsaction') || '',
            className: element.className || '',
          }));
        })()
    """
    result = evaluate_json(client, expression, timeout=15.0)
    return result if isinstance(result, list) else []


def collect_review_open_candidates(client: CDPClient) -> list[dict[str, Any]]:
    expression = r"""
        (() => {
          const isVisible = (element) => {
            const style = window.getComputedStyle(element);
            const rect = element.getBoundingClientRect();
            return style.visibility !== 'hidden' && style.display !== 'none' &&
              rect.width > 0 && rect.height > 0;
          };
          const normalize = (value) => (value || '').replace(/\s+/g, ' ').trim();
          const hasWordChars = (value) => /[0-9A-Za-z\u00C0-\u024F]/.test(value);
          const bannedPattern = /\b(weitere information|offenlegung|gesetzlich|gesetzliche|disclosure|legal|rezension schreiben|write a review|help|erwahnt|erwähnt|mentioned)\b/i;
          const countPattern = /(^|\s)[0-9][0-9.,\s\u00a0]*\s*(berichte|rezensionen|bewertungen|reviews?)\b/i;
          const reviewPattern = /\b(alle rezensionen|all reviews|rezensionen|bewertungen|reviews?|berichte)\b/i;
          const exactOpenPattern = /\b(alle rezensionen|all reviews)\b/i;

          const controls = [...document.querySelectorAll('button,[role="button"],a')];
          const candidates = [];

          for (let domIndex = 0; domIndex < controls.length; domIndex += 1) {
            const element = controls[domIndex];
            if (!isVisible(element)) {
              continue;
            }
            const text = normalize(element.innerText || element.textContent || '');
            const ariaLabel = normalize(element.getAttribute('aria-label') || '');
            const title = normalize(element.getAttribute('title') || '');
            const jsaction = normalize((element.getAttribute('jsaction') || '').toLowerCase());
            const hasReviewId = Boolean(element.getAttribute('data-review-id'));
            const combined = normalize([text, ariaLabel, title].filter(Boolean).join(' '));
            if (!combined || !hasWordChars(combined)) {
              continue;
            }
            if (bannedPattern.test(combined)) {
              continue;
            }
            if (hasReviewId || jsaction.includes('review.reviewerlink') || jsaction.includes('review.actionmenu')) {
              continue;
            }

            let score = 0;
            const reasons = [];
            if (jsaction.includes('reviewchart.morereviews')) {
              score += 120;
              reasons.push('jsaction_more_reviews');
            }
            if (countPattern.test(combined) && !/\bin\s+[0-9][0-9.,\s\u00a0]*\s*(rezensionen|bewertungen|reviews?)\b/i.test(combined)) {
              score += 60;
              reasons.push('count_label');
            }
            if (exactOpenPattern.test(combined)) {
              score += 45;
              reasons.push('explicit_all_reviews');
            }
            if (reviewPattern.test(combined)) {
              score += 25;
              reasons.push('review_keyword');
            }
            if (score <= 0) {
              continue;
            }
            if (element.tagName === 'BUTTON' || element.getAttribute('role') === 'button') {
              score += 10;
              reasons.push('button_like_control');
            }

            candidates.push({
              domIndex,
              score,
              reasons,
              tagName: element.tagName,
              text,
              ariaLabel,
              title,
              jsaction,
              className: normalize(element.className || ''),
            });
          }

          candidates.sort((left, right) => right.score - left.score);
          return candidates.slice(0, 25);
        })()
    """
    result = evaluate_json(client, expression, timeout=20.0)
    return result if isinstance(result, list) else []


def click_review_open_candidate(client: CDPClient, dom_index: int) -> dict[str, Any]:
    expression = rf"""
        (() => {{
          const index = {dom_index};
          const isVisible = (element) => {{
            const style = window.getComputedStyle(element);
            const rect = element.getBoundingClientRect();
            return style.visibility !== 'hidden' && style.display !== 'none' &&
              rect.width > 0 && rect.height > 0;
          }};
          const normalize = (value) => (value || '').replace(/\s+/g, ' ').trim();
          const bannedPattern = /\b(weitere information|offenlegung|gesetzlich|gesetzliche|disclosure|legal|rezension schreiben|write a review|help)\b/i;
          const controls = [...document.querySelectorAll('button,[role="button"],a')];
          if (!Number.isInteger(index) || index < 0 || index >= controls.length) {{
            return {{clicked: false, reason: 'index_out_of_range', index}};
          }}

          const element = controls[index];
          const text = normalize(element.innerText || element.textContent || '');
          const ariaLabel = normalize(element.getAttribute('aria-label') || '');
          const title = normalize(element.getAttribute('title') || '');
          const jsaction = normalize((element.getAttribute('jsaction') || '').toLowerCase());
          const combined = normalize([text, ariaLabel, title].filter(Boolean).join(' '));
          if (!isVisible(element)) {{
            return {{clicked: false, reason: 'not_visible', index, text, ariaLabel, jsaction}};
          }}
          if (bannedPattern.test(combined)) {{
            return {{clicked: false, reason: 'banned_label', index, text, ariaLabel, jsaction}};
          }}

          element.click();
          return {{
            clicked: true,
            index,
            text,
            ariaLabel,
            title,
            jsaction,
            className: normalize(element.className || ''),
          }};
        }})()
    """
    result = evaluate_json(client, expression, timeout=20.0)
    return result if isinstance(result, dict) else {"clicked": False}


def advance_reviews_notice_or_more(client: CDPClient) -> dict[str, Any]:
    expression = r"""
        (() => {
          const normalize = (value) => (value || '').replace(/\s+/g, ' ').trim();
          const isVisible = (element) => {
            const style = window.getComputedStyle(element);
            const rect = element.getBoundingClientRect();
            return style.visibility !== 'hidden' && style.display !== 'none' &&
              rect.width > 0 && rect.height > 0;
          };
          const controls = [...document.querySelectorAll('button,[role="button"],a')];
          const continuationPattern = /\b(weitere\s+rezensionen|more\s+reviews)\b/i;
          const policyNoticePattern = /\b(entfernt|removed|richtlinien|polic(?:y|ies)|unangemessen|inappropriate)\b/i;
          const bodyText = normalize(document.body && document.body.innerText || '');
          const candidates = [];

          for (let domIndex = 0; domIndex < controls.length; domIndex += 1) {
            const element = controls[domIndex];
            if (!isVisible(element)) {
              continue;
            }
            const text = normalize(element.innerText || element.textContent || '');
            const ariaLabel = normalize(element.getAttribute('aria-label') || '');
            const title = normalize(element.getAttribute('title') || '');
            const combined = normalize([text, ariaLabel, title].filter(Boolean).join(' '));
            if (!continuationPattern.test(combined)) {
              continue;
            }
            candidates.push({
              domIndex,
              text,
              ariaLabel,
              title,
              jsaction: normalize(element.getAttribute('jsaction') || ''),
              className: normalize(element.className || ''),
            });
          }

          if (candidates.length) {
            const selected = candidates[0];
            controls[selected.domIndex].click();
            return {
              clicked: true,
              strategy: 'reviews_continuation',
              candidate: selected,
              policyNoticeDetected: policyNoticePattern.test(bodyText),
            };
          }

          return {
            clicked: false,
            visibleContinuationCount: candidates.length,
            policyNoticeDetected: policyNoticePattern.test(bodyText),
          };
        })()
    """
    result = evaluate_json(client, expression, timeout=10.0)
    return result if isinstance(result, dict) else {"clicked": False}


def open_reviews_panel(client: CDPClient, requests: dict[str, dict[str, Any]], verify_timeout: float) -> dict[str, Any]:
    attempts: list[dict[str, Any]] = []
    attempted_fingerprints: set[str] = set()

    for rank in range(1, 9):
        candidates = collect_review_open_candidates(client)
        candidate = None
        for current_candidate in candidates:
            fingerprint = "|".join(
                str(current_candidate.get(key) or "")
                for key in ("text", "ariaLabel", "title", "jsaction")
            )
            if fingerprint in attempted_fingerprints:
                continue
            candidate = current_candidate
            attempted_fingerprints.add(fingerprint)
            break
        if candidate is None:
            break
        dom_index = candidate.get("domIndex")
        if not isinstance(dom_index, int):
            continue
        click_result = click_review_open_candidate(client, dom_index)
        attempt: dict[str, Any] = {
            "rank": rank,
            "candidate": candidate,
            "candidateCountBeforeClick": len(candidates),
            "clickResult": click_result,
        }
        attempts.append(attempt)
        if not click_result.get("clicked"):
            continue

        time.sleep(1.0)
        pump_events(client, requests, time_limit=2.0)
        panel = wait_for_reviews_panel(client, timeout=verify_timeout)
        attempt["reviewsPanelAfterClick"] = panel
        if panel:
            return {
                "opened": True,
                "attempts": attempts,
                "selectedCandidate": candidate,
                "selectedClick": click_result,
                "reviewsPanel": panel,
                "candidateCount": len(candidates),
            }

        continuation_attempts: list[dict[str, Any]] = []
        for _ in range(3):
            continuation = advance_reviews_notice_or_more(client)
            continuation_attempts.append(continuation)
            if not continuation.get("clicked"):
                break
            time.sleep(1.0)
            pump_events(client, requests, time_limit=2.0)
            panel = wait_for_reviews_panel(client, timeout=verify_timeout)
            if panel:
                attempt["reviewsContinuationAttempts"] = continuation_attempts
                attempt["reviewsPanelAfterContinuation"] = panel
                return {
                    "opened": True,
                    "attempts": attempts,
                    "selectedCandidate": candidate,
                    "selectedClick": click_result,
                    "selectedContinuation": continuation,
                    "reviewsPanel": panel,
                    "candidateCount": len(candidates),
                }
        if continuation_attempts:
            attempt["reviewsContinuationAttempts"] = continuation_attempts

    return {
        "opened": False,
        "attempts": attempts,
        "candidateCount": len(collect_review_open_candidates(client)),
    }


def get_cookie_consent_state(client: CDPClient) -> dict[str, Any]:
    expression = r"""
        (() => {
          const normalize = (value) => (value || '')
            .toString()
            .toLowerCase()
            .normalize('NFD')
            .replace(/[\u0300-\u036f]/g, '')
            .replace(/\s+/g, ' ')
            .trim();
          const isVisible = (element) => {
            const style = window.getComputedStyle(element);
            const rect = element.getBoundingClientRect();
            return style.visibility !== 'hidden' && style.display !== 'none' &&
              rect.width > 0 && rect.height > 0;
          };
          const extractLabel = (element) => normalize(
            [
              element.innerText || element.textContent || '',
              element.getAttribute('aria-label') || '',
              element.getAttribute('title') || '',
              element.getAttribute('value') || '',
              element.id || '',
            ].join(' ')
          );
          const controls = [...document.querySelectorAll('button,[role="button"],a,input[type="button"],input[type="submit"]')]
            .filter(isVisible)
            .map((element) => ({
              tagName: element.tagName,
              id: element.id || '',
              label: extractLabel(element),
              ariaLabel: normalize(element.getAttribute('aria-label') || ''),
              title: normalize(element.getAttribute('title') || ''),
            }))
            .filter((item) => item.label)
            .slice(0, 40);
          const pageUrl = window.location.href;
          const bodyText = normalize((document.body && document.body.innerText || '').slice(0, 2000));
          const consentNeedles = [
            'consent.google.',
            'cookies',
            'cookie',
            'datenschutz',
            'privacy',
            'alle akzeptieren',
            'accept all',
            'ich stimme zu',
            'i agree',
          ];
          const combined = normalize([pageUrl, document.title || '', bodyText, controls.map((item) => item.label).join(' ')].join(' '));
          return {
            pageUrl,
            title: document.title || '',
            controlCount: controls.length,
            controls,
            onConsentHost: pageUrl.includes('consent.google.'),
            looksLikeConsent: consentNeedles.some((needle) => combined.includes(needle)),
          };
        })()
    """
    result = safe_evaluate_json(client, expression, timeout=5.0)
    if result.get("ok") and isinstance(result.get("value"), dict):
        state = result["value"]
        state["runtimeOk"] = True
        return state
    return {
        "runtimeOk": False,
        "runtimeErrorType": result.get("errorType"),
        "runtimeError": result.get("error"),
    }


def click_cookie_consent(client: CDPClient) -> dict[str, Any]:
    expression = r"""
        (() => {
          const normalize = (value) => (value || '')
            .toString()
            .toLowerCase()
            .normalize('NFD')
            .replace(/[\u0300-\u036f]/g, '')
            .replace(/\s+/g, ' ')
            .trim();
          const isVisible = (element) => {
            const style = window.getComputedStyle(element);
            const rect = element.getBoundingClientRect();
            return style.visibility !== 'hidden' && style.display !== 'none' &&
              rect.width > 0 && rect.height > 0;
          };
          const extractLabel = (element) => normalize(
            [
              element.innerText || element.textContent || '',
              element.getAttribute('aria-label') || '',
              element.getAttribute('title') || '',
              element.getAttribute('value') || '',
              element.id || '',
            ].join(' ')
          );
          const acceptNeedles = [
            'alle akzeptieren',
            'alles akzeptieren',
            'akzeptieren',
            'ich stimme zu',
            'zustimmen',
            'einverstanden',
            'accept all',
            'accept',
            'i agree',
            'agree',
          ];
          const directSelectors = [
            '#L2AGLb',
            'button#L2AGLb',
            '#introAgreeButton',
            '#introAgree',
            'button[aria-label*="accept" i]',
            'button[aria-label*="akzeptieren" i]',
            'button[aria-label*="zustimmen" i]',
          ];
          for (const selector of directSelectors) {
            let elements = [];
            try {
              elements = [...document.querySelectorAll(selector)];
            } catch (_) {}
            for (const element of elements) {
              if (!isVisible(element)) {
                continue;
              }
              const label = extractLabel(element);
              element.click();
              return {clicked: true, action: 'accept', label, strategy: 'direct_selector', selector, pageUrl: window.location.href};
            }
          }

          const controls = [...document.querySelectorAll('button,[role="button"],a,input[type="button"],input[type="submit"]')];
          for (const element of controls) {
            if (!isVisible(element)) {
              continue;
            }
            const label = extractLabel(element);
            if (!label) {
              continue;
            }
            if (acceptNeedles.some((needle) => label.includes(needle))) {
              element.click();
              return {clicked: true, action: 'accept', label, strategy: 'label_match', pageUrl: window.location.href};
            }
          }
          return {clicked: false, pageUrl: window.location.href, visibleControlCount: controls.filter(isVisible).length};
        })()
    """
    result = safe_evaluate_json(client, expression, timeout=5.0)
    if result.get("ok") and isinstance(result.get("value"), dict):
        return result["value"]
    return {
        "clicked": False,
        "runtimeTimeout": result.get("errorType") == "TimeoutError",
        "runtimeErrorType": result.get("errorType"),
        "runtimeError": result.get("error"),
    }


def resolve_cookie_consent(client: CDPClient, requests: dict[str, dict[str, Any]]) -> dict[str, Any]:
    attempts: list[dict[str, Any]] = []
    consecutive_runtime_failures = 0
    for attempt in range(1, 8):
        state = get_cookie_consent_state(client)
        if not state.get("runtimeOk", True):
            consecutive_runtime_failures += 1
        else:
            consecutive_runtime_failures = 0

        result = click_cookie_consent(client) if state.get("looksLikeConsent") or state.get("onConsentHost") else {"clicked": False, "skipped": True}
        if result.get("runtimeTimeout") or result.get("runtimeErrorType"):
            consecutive_runtime_failures += 1

        current_url_result = safe_evaluate_json(client, "window.location.href", timeout=3.0)
        current_url = current_url_result.get("value") if current_url_result.get("ok") else state.get("pageUrl")
        on_consent_host = isinstance(current_url, str) and "consent.google." in current_url
        attempt_record = {
            "attempt": attempt,
            "state": state,
            "clickResult": result,
            "currentUrl": current_url if isinstance(current_url, str) else None,
            "onConsentHost": on_consent_host,
            "currentUrlReadOk": bool(current_url_result.get("ok")),
            "consecutiveRuntimeFailures": consecutive_runtime_failures,
        }
        attempts.append(attempt_record)

        if result.get("clicked"):
            pump_events(client, requests, time_limit=1.0)
            time.sleep(1.5)
            post_click_url = safe_evaluate_json(client, "window.location.href", timeout=4.0)
            post_click_url_value = post_click_url.get("value") if post_click_url.get("ok") else current_url
            attempt_record["postClickUrl"] = post_click_url_value if isinstance(post_click_url_value, str) else None
            return {
                "clicked": True,
                "action": result.get("action"),
                "attempts": attempts,
                "resolvedWith": result,
            }

        if consecutive_runtime_failures >= 2:
            return {
                "clicked": False,
                "attempts": attempts,
                "runtimeTimeout": True,
                "blockedOnConsentHost": on_consent_host,
                "finalUrl": current_url if isinstance(current_url, str) else None,
            }

        if not state.get("looksLikeConsent") and not on_consent_host:
            return {
                "clicked": False,
                "attempts": attempts,
                "blockedOnConsentHost": False,
                "finalUrl": current_url if isinstance(current_url, str) else None,
            }

        pump_events(client, requests, time_limit=0.5)
        if on_consent_host:
            time.sleep(1.5)
        else:
            time.sleep(0.9)
    final_url_result = safe_evaluate_json(client, "window.location.href", timeout=3.0)
    final_url = final_url_result.get("value") if final_url_result.get("ok") else None
    blocked_on_consent_host = isinstance(final_url, str) and "consent.google." in final_url
    return {
        "clicked": False,
        "attempts": attempts,
        "blockedOnConsentHost": blocked_on_consent_host,
        "finalUrl": final_url if isinstance(final_url, str) else None,
    }


def wait_for_reviews_panel(client: CDPClient, timeout: float) -> Any:
    expression = r"""
        (() => {
          const reviewNodes = document.querySelectorAll('[data-review-id], .jftiEf, .wiI7pd');
          const normalize = (value) => (value || '').replace(/\s+/g, ' ').trim();
          const bodyText = normalize(document.body && document.body.innerText || '');
          if (reviewNodes.length > 0) {
            return {
              reviewNodeCount: reviewNodes.length,
              title: document.title,
            };
          }
          const heading = [...document.querySelectorAll('h1,h2,div,span')].find((node) => {
            const text = (node.innerText || '').trim();
            return text === 'Alle Rezensionen' || text === 'All reviews';
          });
          if (heading) {
            return {
              reviewNodeCount: reviewNodes.length,
              heading: heading.innerText.trim(),
              title: document.title,
            };
          }
          const policyNoticeDetected = /\b(entfernt|removed|richtlinien|polic(?:y|ies)|diffamierung|inappropriate|unangemessen)\b/i.test(bodyText);
          const reviewsTabSelected = [...document.querySelectorAll('button,[role="tab"],[aria-selected="true"]')]
            .some((node) => {
              const label = normalize([
                node.innerText || node.textContent || '',
                node.getAttribute('aria-label') || '',
              ].join(' '));
              return /rezensionen|bewertungen|reviews/i.test(label) &&
                (node.getAttribute('aria-selected') === 'true' || /hh2c6|Gpq6kf|tXXpyf/.test(String(node.className || '')));
            });
          const hasReviewsControls = [...document.querySelectorAll('button,[role="button"]')]
            .some((node) => {
              const label = normalize([
                node.innerText || node.textContent || '',
                node.getAttribute('aria-label') || '',
              ].join(' '));
              return /\b(sortieren|in rezensionen suchen|rezension schreiben|sort|search reviews|write a review)\b/i.test(label);
            });
          if (policyNoticeDetected && (reviewsTabSelected || hasReviewsControls)) {
            return {
              reviewNodeCount: 0,
              policyNoticeDetected: true,
              reviewsTabSelected,
              hasReviewsControls,
              title: document.title,
            };
          }
          return false;
        })()
    """
    return wait_for_predicate(client, expression, timeout)


def get_reviews_scroll_state(client: CDPClient) -> dict[str, Any]:
    expression = r"""
        (() => {
          const reviewIds = [...document.querySelectorAll('[data-review-id]')]
            .map((element) => element.getAttribute('data-review-id'))
            .filter(Boolean);
          const uniqueReviewIds = [...new Set(reviewIds)];

          const findTarget = () => {
            let node = document.querySelector('[data-review-id], .jftiEf, .wiI7pd');
            while (node) {
              if (node.scrollHeight > node.clientHeight + 100) {
                return node;
              }
              node = node.parentElement;
            }

            const candidates = [...document.querySelectorAll('*')]
              .filter((element) => element.scrollHeight > element.clientHeight + 80 && element.clientHeight > 180)
              .map((element) => ({
                element,
                score: element.scrollHeight - element.clientHeight,
              }))
              .sort((left, right) => right.score - left.score);
            return candidates.length > 0 ? candidates[0].element : null;
          };

          const target = findTarget();
          const state = {
            title: document.title,
            reviewNodeCount: document.querySelectorAll('[data-review-id], .jftiEf, .wiI7pd').length,
            uniqueReviewIdCount: uniqueReviewIds.length,
          };

          if (!target) {
            return {...state, foundTarget: false};
          }

          const distanceToBottom = Math.max(
            target.scrollHeight - (target.scrollTop + target.clientHeight),
            0
          );
          return {
            ...state,
            foundTarget: true,
            className: target.className || '',
            tagName: target.tagName,
            scrollTop: target.scrollTop,
            scrollHeight: target.scrollHeight,
            clientHeight: target.clientHeight,
            distanceToBottom,
          };
        })()
    """
    result = evaluate_json(client, expression, timeout=20.0)
    return result if isinstance(result, dict) else {"foundTarget": False}


def get_declared_review_total(client: CDPClient) -> dict[str, Any]:
    expression = r"""
        (() => {
          const parseNumber = (text) => {
            const digits = text.replace(/[^\d]/g, '');
            if (!digits) {
              return NaN;
            }
            return Number.parseInt(digits, 10);
          };

          // Most reliable source: star-distribution labels in the review filters.
          const histogramPattern = /(?:^|\b)([1-5])\s*(?:Stern|Sterne|star|stars)\s*[,;:]\s*([0-9][0-9.,\s\u00a0]*)\s*(?:Rezensionen|Bewertungen|reviews?)\b/i;
          const histogramByStar = {};
          for (const element of document.querySelectorAll('[aria-label]')) {
            const label = (element.getAttribute('aria-label') || '').replace(/\s+/g, ' ').trim();
            if (!label) {
              continue;
            }
            const match = label.match(histogramPattern);
            if (!match) {
              continue;
            }
            const star = Number.parseInt(match[1], 10);
            const count = parseNumber(match[2]);
            if (!Number.isFinite(star) || !Number.isFinite(count) || count < 0) {
              continue;
            }
            histogramByStar[star] = count;
          }
          const histogramStars = Object.keys(histogramByStar).map((value) => Number.parseInt(value, 10)).filter(Number.isFinite);
          if (histogramStars.length >= 2) {
            const histogramTotal = histogramStars.reduce((sum, star) => sum + (histogramByStar[star] || 0), 0);
            if (Number.isFinite(histogramTotal) && histogramTotal > 0) {
              return {
                found: true,
                declaredReviewTotal: histogramTotal,
                sourceKind: 'rating-histogram',
                histogramByStar,
                histogramStarCount: histogramStars.length,
              };
            }
          }

          const labelPattern = /(?:^|\b)(?:Alle\s+)?([0-9][0-9.,\s\u00a0]*)\s*(Rezensionen|Bewertungen|reviews?)\b/i;
          const candidateTags = new Set(['BUTTON', 'A', 'SPAN', 'DIV', 'H1', 'H2', 'H3', 'LABEL']);
          const candidates = [];

          const parseCandidate = (element, sourceKind, rawText) => {
            const normalizedText = rawText.replace(/\s+/g, ' ').trim();
            if (!normalizedText) {
              return null;
            }
            if (/\b(erwähnt|mentioned)\b/i.test(normalizedText)) {
              return null;
            }
            const match = normalizedText.match(labelPattern);
            if (!match) {
              return null;
            }
            const total = parseNumber(match[1]);
            if (!Number.isFinite(total) || total <= 0) {
              return null;
            }
            const rect = element.getBoundingClientRect();
            if (rect.width <= 0 || rect.height <= 0) {
              return null;
            }
            return {
              total,
              sourceKind,
              matchedText: normalizedText,
              tagName: element.tagName,
              className: element.className || '',
              top: rect.top,
              left: rect.left,
            };
          };

          for (const element of document.querySelectorAll('button, a, span, div, h1, h2, h3, label')) {
            if (!candidateTags.has(element.tagName)) {
              continue;
            }
            if (element.closest('[data-review-id], .jftiEf, .wiI7pd')) {
              continue;
            }

            const texts = [];
            const ariaLabel = (element.getAttribute('aria-label') || '').trim();
            const title = (element.getAttribute('title') || '').trim();
            const innerText = (element.innerText || '').trim();
            if (ariaLabel) {
              texts.push(['aria-label', ariaLabel]);
            }
            if (title && title !== ariaLabel) {
              texts.push(['title', title]);
            }
            if (innerText && innerText.length <= 120) {
              texts.push(['innerText', innerText]);
            }

            for (const [sourceKind, text] of texts) {
              const parsed = parseCandidate(element, sourceKind, text);
              if (parsed) {
                candidates.push(parsed);
                break;
              }
            }
          }

          const preferred = candidates.filter((candidate) => candidate.top >= -20 && candidate.top <= 900 && candidate.left >= -20 && candidate.left <= 1400);
          const score = (candidate) => {
            let value = 0;
            if (candidate.sourceKind === 'aria-label') {
              value += 2;
            }
            if (candidate.total >= 10) {
              value += 4;
            }
            value += Math.min(candidate.total / 25, 4);
            if (candidate.top >= 40 && candidate.top <= 500) {
              value += 2;
            }
            return value;
          };
          const pool = preferred.length > 0 ? preferred : candidates;
          const chosen = pool.slice().sort((left, right) => score(right) - score(left))[0];
          if (!chosen) {
            return {
              found: false,
              candidateCount: candidates.length,
            };
          }
          return {
            found: true,
            declaredReviewTotal: chosen.total,
            sourceKind: chosen.sourceKind,
            sourceText: chosen.matchedText,
            tagName: chosen.tagName,
            className: chosen.className,
            top: chosen.top,
            left: chosen.left,
            candidateCount: candidates.length,
            preferredCandidateCount: preferred.length,
          };
        })()
    """
    result = evaluate_json(client, expression, timeout=20.0)
    return result if isinstance(result, dict) else {"found": False}


def scroll_reviews(client: CDPClient) -> dict[str, Any]:
    expression = r"""
        (() => {
          const reviewIds = [...document.querySelectorAll('[data-review-id]')]
            .map((element) => element.getAttribute('data-review-id'))
            .filter(Boolean);
          const uniqueReviewIds = [...new Set(reviewIds)];

          const findTarget = () => {
            let node = document.querySelector('[data-review-id], .jftiEf, .wiI7pd');
            while (node) {
              if (node.scrollHeight > node.clientHeight + 100) {
                return node;
              }
              node = node.parentElement;
            }

            const candidates = [...document.querySelectorAll('*')]
              .filter((element) => element.scrollHeight > element.clientHeight + 80 && element.clientHeight > 180)
              .map((element) => ({
                element,
                score: element.scrollHeight - element.clientHeight,
              }))
              .sort((left, right) => right.score - left.score);
            return candidates.length > 0 ? candidates[0].element : null;
          };

          const target = findTarget();
          if (!target) {
            window.scrollTo(0, document.body.scrollHeight);
            return {
              scrolledWindow: true,
              strategy: 'window_to_bottom',
              uniqueReviewIdCount: uniqueReviewIds.length,
              reviewNodeCount: document.querySelectorAll('[data-review-id], .jftiEf, .wiI7pd').length,
            };
          }
          const before = target.scrollTop;
          target.scrollTop = target.scrollHeight;
          target.dispatchEvent(new Event('scroll', {bubbles: true}));
          target.dispatchEvent(new WheelEvent('wheel', {
            deltaY: Math.max(target.clientHeight, 240),
            bubbles: true,
            cancelable: true,
          }));
          const distanceToBottom = Math.max(
            target.scrollHeight - (target.scrollTop + target.clientHeight),
            0
          );
          return {
            scrolled: true,
            strategy: 'pane_to_bottom',
            before,
            after: target.scrollTop,
            className: target.className || '',
            tagName: target.tagName,
            scrollHeight: target.scrollHeight,
            clientHeight: target.clientHeight,
            distanceToBottom,
            reviewNodeCount: document.querySelectorAll('[data-review-id], .jftiEf, .wiI7pd').length,
            uniqueReviewIdCount: uniqueReviewIds.length,
          };
        })()
    """
    result = evaluate_json(client, expression, timeout=20.0)
    return result if isinstance(result, dict) else {"scrolled": False}


def nudge_reviews_loading(client: CDPClient) -> dict[str, Any]:
    expression = r"""
        (() => {
          const findTarget = () => {
            let node = document.querySelector('[data-review-id], .jftiEf, .wiI7pd');
            while (node) {
              if (node.scrollHeight > node.clientHeight + 100) {
                return node;
              }
              node = node.parentElement;
            }

            const candidates = [...document.querySelectorAll('*')]
              .filter((element) => element.scrollHeight > element.clientHeight + 80 && element.clientHeight > 180)
              .map((element) => ({
                element,
                score: element.scrollHeight - element.clientHeight,
              }))
              .sort((left, right) => right.score - left.score);
            return candidates.length > 0 ? candidates[0].element : null;
          };

          const target = findTarget();
          if (!target) {
            return {nudged: false};
          }

          const before = target.scrollTop;
          const delta = Math.min(Math.max(target.clientHeight * 0.4, 120), 260);
          target.scrollTop = Math.max(target.scrollTop - delta, 0);
          return {
            nudged: true,
            before,
            after: target.scrollTop,
            scrollHeight: target.scrollHeight,
            clientHeight: target.clientHeight,
          };
        })()
    """
    result = evaluate_json(client, expression, timeout=20.0)
    return result if isinstance(result, dict) else {"nudged": False}


def get_page_html(client: CDPClient) -> str:
    expression = "document.documentElement.outerHTML"
    result = evaluate_json(client, expression, timeout=20.0)
    return result if isinstance(result, str) else ""


def expand_all_review_texts(client: CDPClient) -> dict[str, Any]:
    expression = r"""
        (() => {
          const isVisible = (element) => {
            const style = window.getComputedStyle(element);
            const rect = element.getBoundingClientRect();
            return style.visibility !== 'hidden' && style.display !== 'none' &&
              rect.width > 0 && rect.height > 0;
          };

          const buttons = [...document.querySelectorAll('button[jsaction*="expandReview"], button[aria-label*="Mehr"], button[aria-label*="more"]')];
          let clickedCount = 0;
          for (const button of buttons) {
            if (!isVisible(button)) {
              continue;
            }
            if (button.getAttribute('aria-expanded') === 'true') {
              continue;
            }
            button.click();
            clickedCount += 1;
          }
          return {
            buttonCount: buttons.length,
            clickedCount,
          };
        })()
    """
    result = evaluate_json(client, expression, timeout=20.0)
    return result if isinstance(result, dict) else {"buttonCount": 0, "clickedCount": 0}


def summarize_post_data(post_data: str | None) -> dict[str, Any]:
    if not post_data:
        return {}
    parsed = urllib.parse.parse_qs(post_data, keep_blank_values=True)
    summary: dict[str, Any] = {"raw_length": len(post_data)}
    if "f.req" in parsed:
        f_req = parsed["f.req"][0]
        summary["f_req_length"] = len(f_req)
        summary["f_req_preview"] = f_req[:800]
        summary["looks_review_related"] = "review" in f_req.lower() or "rev" in f_req.lower()
    if "at" in parsed:
        summary["has_at_token"] = True
    return summary


def pump_events(client: CDPClient, requests: dict[str, dict[str, Any]], time_limit: float) -> None:
    deadline = time.time() + time_limit
    while time.time() < deadline:
        event = client.get_event(timeout=0.1)
        if event is None:
            continue
        method = event.get("method")
        params = event.get("params", {})

        if method == "Network.requestWillBeSent":
            request = params.get("request", {})
            request_id = params.get("requestId")
            if request_id:
                requests.setdefault(request_id, {}).update(
                    {
                        "requestId": request_id,
                        "url": request.get("url"),
                        "method": request.get("method"),
                        "headers": request.get("headers", {}),
                        "hasPostData": request.get("hasPostData", False),
                        "postData": request.get("postData"),
                        "type": params.get("type"),
                        "wallTime": params.get("wallTime"),
                    }
                )
        elif method == "Network.responseReceived":
            request_id = params.get("requestId")
            response = params.get("response", {})
            if request_id:
                requests.setdefault(request_id, {}).update(
                    {
                        "status": response.get("status"),
                        "statusText": response.get("statusText"),
                        "mimeType": response.get("mimeType"),
                        "responseHeaders": response.get("headers", {}),
                    }
                )
        elif method == "Network.loadingFinished":
            request_id = params.get("requestId")
            if request_id:
                requests.setdefault(request_id, {}).update({"loadingFinished": True})


def is_review_related_request(request: dict[str, Any]) -> bool:
    url = str(request.get("url", ""))
    req_type = str(request.get("type") or "")
    is_xhr_like = req_type in {"XHR", "Fetch"} or not req_type
    if "MapsWizUi/data/batchexecute" in url:
        return is_xhr_like
    if "/maps/preview/" in url:
        return is_xhr_like
    body = str(request.get("postData") or "")
    if not is_xhr_like:
        return False
    return "review" in body.lower() or "other_user_google_review_posts" in body.lower()


def request_matches(request: dict[str, Any]) -> bool:
    return is_review_related_request(request)


def latest_review_request_wall_time(
    requests: dict[str, dict[str, Any]],
    since_wall_time: float | None,
) -> float | None:
    latest: float | None = None
    for request in requests.values():
        if not is_review_related_request(request):
            continue
        wall_time = request.get("wallTime")
        if not isinstance(wall_time, (int, float)):
            continue
        if since_wall_time is not None and wall_time < since_wall_time:
            continue
        if latest is None or wall_time > latest:
            latest = float(wall_time)
    return latest


def count_review_requests_since(
    requests: dict[str, dict[str, Any]],
    previous_wall_time: float | None,
    since_wall_time: float | None,
) -> int:
    count = 0
    for request in requests.values():
        if not is_review_related_request(request):
            continue
        wall_time = request.get("wallTime")
        if not isinstance(wall_time, (int, float)):
            continue
        if since_wall_time is not None and wall_time < since_wall_time:
            continue
        if previous_wall_time is None or wall_time > previous_wall_time + 1e-9:
            count += 1
    return count


def perform_bottom_probe(
    client: CDPClient,
    requests: dict[str, dict[str, Any]],
    wait_seconds: float,
) -> dict[str, Any]:
    half_wait = max(wait_seconds / 2.0, 0.5)
    probe: dict[str, Any] = {"waitSeconds": wait_seconds}

    time.sleep(half_wait)
    pump_events(client, requests, time_limit=1.0)
    probe["nudgeUp"] = nudge_reviews_loading(client)

    time.sleep(0.6)
    pump_events(client, requests, time_limit=1.0)
    probe["scrollDown"] = scroll_reviews(client)

    time.sleep(half_wait)
    pump_events(client, requests, time_limit=1.5)
    probe["stateAfterProbe"] = get_reviews_scroll_state(client)
    return probe


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


def normalize_review_time(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    normalized = html.unescape(value).replace("\xa0", " ")
    normalized = re.sub(r"\s+", " ", normalized).strip()
    return normalized or None


def normalize_review_text(value: Any) -> str:
    if not isinstance(value, str):
        return ""
    normalized = html.unescape(value).replace("\xa0", " ")
    normalized = re.sub(r"<[^>]+>", "", normalized)
    return re.sub(r"\s+", " ", normalized).strip()


def extract_tag_attr(tag: str, attr: str) -> str | None:
    match = re.search(rf'\b{re.escape(attr)}="(?P<value>[^"]*)"', tag, flags=re.S)
    if not match:
        return None
    return html.unescape(match.group("value")).replace("\xa0", " ").strip()


def extract_star_rating_from_fragment(fragment: str) -> int | None:
    rating_match = re.search(
        r'aria-label="(?P<label>[^"]*(?:Stern|Sterne|star|stars)[^"]*)"',
        fragment,
        flags=re.I,
    )
    if not rating_match:
        return None
    return parse_star_rating_label(rating_match.group("label"))


def extract_review_time_from_fragment(fragment: str) -> str | None:
    match = re.search(
        r'<span class="rsqaWe">(?P<time>.*?)</span>',
        fragment,
        flags=re.I | re.S,
    )
    if not match:
        return None
    raw_time = re.sub(r"<[^>]+>", "", match.group("time"))
    return normalize_review_time(raw_time)


def parse_like_count_label(label: str | None) -> int | None:
    if not isinstance(label, str):
        return None
    decoded = html.unescape(label).replace("\xa0", " ")
    decoded = re.sub(r"\s+", " ", decoded).strip()
    if decoded == "Gefällt mir":
        return 0
    if "Gefällt mir" not in decoded:
        return None
    match = re.search(r"\b(?P<count>\d[\d.]*)\b", decoded)
    if not match:
        return None
    return int(match.group("count").replace(".", ""))


def normalize_like_count(value: Any) -> int | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value if value >= 0 else None
    if isinstance(value, str):
        return parse_like_count_label(value)
    return None


def extract_like_count_from_fragment(fragment: str, review_id: str) -> int | None:
    button_match = re.search(
        r'<button\b(?=[^>]*\bdata-review-id="'
        + re.escape(review_id)
        + r'")(?=[^>]*review\.toggleThumbsUp)[^>]*>',
        fragment,
        flags=re.S,
    )
    if not button_match:
        return None
    button_tag = button_match.group(0)
    aria_like_count = parse_like_count_label(extract_tag_attr(button_tag, "aria-label"))
    if aria_like_count is not None:
        return aria_like_count
    return parse_like_count_label(extract_tag_attr(button_tag, "title"))


def extract_owner_response_from_fragment(fragment: str) -> dict[str, Any]:
    anchor = fragment.find("Antwort vom Inhaber")
    if anchor < 0:
        return {
            "has_owner_response": False,
            "owner_response_time": None,
            "owner_response_text": None,
        }

    tail = fragment[anchor + len("Antwort vom Inhaber") :]
    time_match = re.search(r"<span\b[^>]*>(?P<time>.*?)</span>", tail, flags=re.S)
    response_time = normalize_review_time(time_match.group("time")) if time_match else None
    text_search_start = time_match.end() if time_match else 0
    text_match = re.search(
        r"<div\b[^>]*>(?P<text>.*?)</div>",
        tail[text_search_start:],
        flags=re.S,
    )
    response_text = normalize_review_text(text_match.group("text")) if text_match else None
    return {
        "has_owner_response": True,
        "owner_response_time": response_time,
        "owner_response_text": response_text or None,
    }


def iter_review_fragments(text: str) -> list[tuple[str, str, str]]:
    start_pattern = re.compile(
        r'<div\b(?=[^>]*\baria-label="(?P<name>[^"]+)")'
        r'(?=[^>]*\bdata-review-id="(?P<review_id>[^"]+)")'
        r'(?=[^>]*\bjslog="21866(?:;|"))[^>]*>',
        flags=re.S,
    )
    matches = list(start_pattern.finditer(text))
    fragments: list[tuple[str, str, str]] = []
    for index, match in enumerate(matches):
        end = matches[index + 1].start() if index + 1 < len(matches) else len(text)
        fragments.append(
            (
                html.unescape(match.group("name")).strip(),
                match.group("review_id"),
                text[match.start() : end],
            )
        )
    return fragments


def parse_reviews_from_html(path: pathlib.Path) -> list[dict[str, Any]]:
    if not path.is_file():
        return []
    text = path.read_text(encoding="utf-8", errors="ignore")

    reviews: list[dict[str, Any]] = []
    for reviewer_name, review_id, fragment in iter_review_fragments(text):
        content_end_candidates = [
            position
            for position in (fragment.find("review.toggleThumbsUp"), fragment.find("Antwort vom Inhaber"))
            if position >= 0
        ]
        review_content_fragment = fragment[: min(content_end_candidates)] if content_end_candidates else fragment
        text_match = re.search(
            r'<span\b(?=[^>]*\bclass="[^"]*\bwiI7pd\b[^"]*")[^>]*>(?P<text>.*?)</span>',
            review_content_fragment,
            flags=re.S,
        )
        review_text = normalize_review_text(text_match.group("text")) if text_match else ""
        star_rating = extract_star_rating_from_fragment(fragment)
        review_time = extract_review_time_from_fragment(fragment)
        owner_response = extract_owner_response_from_fragment(fragment)
        if not reviewer_name or not review_text:
            continue
        reviews.append(
            {
                "review_id": review_id,
                "reviewer_name": reviewer_name,
                "review_text": review_text,
                "star_rating": star_rating,
                "review_time": review_time,
                "like_count": extract_like_count_from_fragment(fragment, review_id),
                **owner_response,
            }
        )
    return reviews


def dedupe_review_records(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    deduped: dict[str | tuple[str, str], dict[str, Any]] = {}
    for record in records:
        review_id = record.get("review_id")
        key: str | tuple[str, str]
        if isinstance(review_id, str) and review_id:
            key = review_id
        else:
            key = (
                record.get("reviewer_name", "").strip().casefold(),
                re.sub(r"\s+", " ", record.get("review_text", "").strip()).casefold(),
            )

        normalized_record = {
            "review_id": record.get("review_id", ""),
            "reviewer_name": record.get("reviewer_name", "").strip(),
            "review_text": re.sub(r"\s+", " ", record.get("review_text", "").strip()),
            "star_rating": normalize_star_rating(record.get("star_rating")),
            "review_time": normalize_review_time(record.get("review_time")),
            "like_count": normalize_like_count(record.get("like_count")),
            "has_owner_response": bool(record.get("has_owner_response")),
            "owner_response_time": normalize_review_time(record.get("owner_response_time")),
            "owner_response_text": normalize_review_text(record.get("owner_response_text")) or None,
        }
        existing = deduped.get(key)
        if existing is None:
            deduped[key] = normalized_record
            continue

        if len(normalized_record.get("review_text", "")) > len(existing.get("review_text", "")):
            winner = dict(normalized_record)
            loser = existing
        else:
            winner = dict(existing)
            loser = normalized_record
        if winner.get("star_rating") is None and loser.get("star_rating") is not None:
            winner["star_rating"] = loser["star_rating"]
        if winner.get("review_time") is None and loser.get("review_time") is not None:
            winner["review_time"] = loser["review_time"]
        if winner.get("like_count") is None and loser.get("like_count") is not None:
            winner["like_count"] = loser["like_count"]
        elif loser.get("like_count") is not None and winner.get("like_count") is not None:
            winner["like_count"] = max(winner["like_count"], loser["like_count"])
        if not winner.get("has_owner_response") and loser.get("has_owner_response"):
            winner["has_owner_response"] = True
        if winner.get("owner_response_time") is None and loser.get("owner_response_time") is not None:
            winner["owner_response_time"] = loser["owner_response_time"]
        if winner.get("owner_response_text") is None and loser.get("owner_response_text") is not None:
            winner["owner_response_text"] = loser["owner_response_text"]
        deduped[key] = winner
    return list(deduped.values())


def enrich_requests(
    client: CDPClient,
    requests: dict[str, dict[str, Any]],
    output_dir: pathlib.Path,
) -> list[dict[str, Any]]:
    matched: list[dict[str, Any]] = []
    request_bodies_dir = output_dir / "request_bodies"
    request_bodies_dir.mkdir(parents=True, exist_ok=True)

    for request_id, request in requests.items():
        if not request_matches(request):
            continue

        entry = dict(request)
        if entry.get("hasPostData") and not entry.get("postData"):
            try:
                entry["postData"] = client.call(
                    "Network.getRequestPostData",
                    {"requestId": request_id},
                    timeout=8.0,
                )["postData"]
                post_data_path = request_bodies_dir / f"{request_id}_post.txt"
                save_text(post_data_path, entry["postData"])
                entry["postDataPath"] = str(post_data_path)
            except Exception as exc:  # noqa: BLE001
                entry["postDataError"] = str(exc)

        if entry.get("loadingFinished"):
            try:
                body_result = client.call(
                    "Network.getResponseBody",
                    {"requestId": request_id},
                    timeout=8.0,
                )
                entry["responseBodyBase64"] = body_result.get("base64Encoded", False)
                body_text = body_result.get("body", "")
                entry["responseBodyPreview"] = body_text[:2000]
                entry["responseBodyLength"] = len(body_text)
                body_path = request_bodies_dir / f"{request_id}_response.txt"
                save_text(body_path, body_text)
                entry["responseBodyPath"] = str(body_path)
            except Exception as exc:  # noqa: BLE001
                entry["responseBodyError"] = str(exc)

        entry["postDataSummary"] = summarize_post_data(entry.get("postData"))
        matched.append(entry)

    matched.sort(key=lambda item: item.get("wallTime") or 0.0)
    return matched


def collect_review_phase_xhr_requests(
    requests: dict[str, dict[str, Any]],
    review_phase_started_at: float | None,
) -> list[dict[str, Any]]:
    results: list[dict[str, Any]] = []
    for request in requests.values():
        wall_time = request.get("wallTime")
        if review_phase_started_at is not None and isinstance(wall_time, (int, float)) and wall_time < review_phase_started_at:
            continue
        if request.get("type") not in {"XHR", "Fetch"}:
            continue
        url = str(request.get("url", ""))
        if "/maps/preview/" not in url and "MapsWizUi/data/batchexecute" not in url:
            continue
        results.append(
            {
                "requestId": request.get("requestId"),
                "url": url,
                "method": request.get("method"),
                "type": request.get("type"),
                "wallTime": request.get("wallTime"),
                "status": request.get("status"),
                "statusText": request.get("statusText"),
                "mimeType": request.get("mimeType"),
                "hasPostData": request.get("hasPostData", False),
            }
        )
    results.sort(key=lambda item: item.get("wallTime") or 0.0)
    return results


def run_capture_once(
    args: argparse.Namespace,
    output_dir: pathlib.Path,
    scroll_delay: float,
) -> dict[str, Any]:
    output_dir.mkdir(parents=True, exist_ok=True)
    chrome_process, chrome_profile_dir = launch_chrome(args, output_dir, startup_url=args.url)
    client: CDPClient | None = None
    requests: dict[str, dict[str, Any]] = {}
    run_summary: dict[str, Any] = {
        "url": args.url,
        "placeId": args.place_id,
        "startedAt": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "scrollDelayUsed": scroll_delay,
    }

    def finalize_early_failure(reason: str, review_phase_started_at: float | None = None) -> dict[str, Any]:
        run_summary["failureReason"] = reason
        run_summary["scrollStopReason"] = reason
        run_summary["captureSuccessful"] = False
        run_summary["finishedAt"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())

        all_xhr_requests: list[dict[str, Any]] = []
        if review_phase_started_at is not None:
            all_xhr_requests = collect_review_phase_xhr_requests(requests, review_phase_started_at)
        run_summary["reviewPhaseXhrCount"] = len(all_xhr_requests)
        run_summary["matchedRequestCount"] = 0
        run_summary["batchexecuteCount"] = 0

        save_text(output_dir / "run_summary.json", json.dumps(run_summary, indent=2, ensure_ascii=False))
        if args.keep_debug_artifacts and all_xhr_requests:
            save_text(output_dir / "all_xhr_requests.json", json.dumps(all_xhr_requests, indent=2, ensure_ascii=False))
            print(f"Saved review-phase XHR requests to {output_dir / 'all_xhr_requests.json'}")
        print(f"Saved run summary to {output_dir / 'run_summary.json'}")
        print(f"Capture stopped early: {reason}")
        return {
            "outputDir": str(output_dir),
            "runSummary": run_summary,
        }

    try:
        version = wait_for_json(f"http://127.0.0.1:{args.remote_debugging_port}/json/version", timeout=15.0)
        targets = wait_for_json(f"http://127.0.0.1:{args.remote_debugging_port}/json/list", timeout=10.0)
        page_target, target_strategy = choose_page_target(targets, args.url)
        client = CDPClient(page_target["webSocketDebuggerUrl"])

        client.call("Page.enable")
        client.call("Runtime.enable")
        client.call(
            "Network.enable",
            {
                "maxTotalBufferSize": 100_000_000,
                "maxResourceBufferSize": 10_000_000,
                "maxPostDataSize": 200_000,
            },
        )

        run_summary["browserVersion"] = version.get("Browser")
        run_summary["pageTargetId"] = page_target.get("id")
        run_summary["selectedTargetId"] = page_target.get("id")
        run_summary["selectedTargetUrl"] = page_target.get("url")
        run_summary["targetSelectionStrategy"] = target_strategy

        client.call("Page.navigate", {"url": args.url}, timeout=args.load_timeout)
        pump_events(client, requests, time_limit=4.0)
        time.sleep(2.5)
        pump_events(client, requests, time_limit=4.0)

        if args.keep_debug_artifacts:
            safe_capture_screenshot(client, output_dir / "01_loaded.png", run_summary, "loaded")
            save_text(output_dir / "page_loaded.html", get_page_html(client))
            button_snapshot = collect_button_snapshot(client)
            save_text(output_dir / "button_snapshot.json", json.dumps(button_snapshot, indent=2, ensure_ascii=False))

        consent_result = resolve_cookie_consent(client, requests)
        run_summary["cookieConsent"] = consent_result
        if consent_result.get("clicked"):
            pump_events(client, requests, time_limit=3.0)
        elif consent_result.get("runtimeTimeout"):
            run_summary["reviewClick"] = {"clicked": False, "reason": "cookie_consent_runtime_timeout"}
            run_summary["reviewsPanel"] = False
            run_summary["reviewOpenAttempts"] = []
            if args.keep_debug_artifacts:
                safe_capture_screenshot(client, output_dir / "02_reviews.png", run_summary, "reviews_opened")
                save_text(output_dir / "page_reviews.html", get_page_html(client))
            return finalize_early_failure("cookie_consent_runtime_timeout")
        elif consent_result.get("blockedOnConsentHost"):
            run_summary["reviewClick"] = {"clicked": False, "reason": "cookie_consent_unresolved"}
            run_summary["reviewsPanel"] = False
            run_summary["reviewOpenAttempts"] = []
            if args.keep_debug_artifacts:
                safe_capture_screenshot(client, output_dir / "02_reviews.png", run_summary, "reviews_opened")
                save_text(output_dir / "page_reviews.html", get_page_html(client))
            return finalize_early_failure("cookie_consent_unresolved")

        review_phase_started_at = time.time()
        verify_timeout = max(min(args.review_timeout, 6.0), 2.0)
        review_open = open_reviews_panel(client, requests, verify_timeout=verify_timeout)
        run_summary["reviewOpenAttempts"] = review_open.get("attempts", [])
        run_summary["reviewOpenCandidateCount"] = review_open.get("candidateCount", 0)
        if review_open.get("opened"):
            selected_click = review_open.get("selectedClick")
            selected_candidate = review_open.get("selectedCandidate")
            run_summary["reviewClick"] = {
                "clicked": True,
                "strategy": "candidate",
                "label": (selected_click or {}).get("text") or (selected_click or {}).get("ariaLabel"),
                "domIndex": (selected_click or {}).get("index"),
                "candidateScore": (selected_candidate or {}).get("score"),
                "candidateReasons": (selected_candidate or {}).get("reasons"),
                "jsaction": (selected_click or {}).get("jsaction"),
            }
            reviews_panel = review_open.get("reviewsPanel")
        else:
            run_summary["reviewClick"] = {
                "clicked": False,
                "reason": "reviews_panel_not_opened",
            }
            run_summary["reviewsPanel"] = False
            if args.keep_debug_artifacts:
                safe_capture_screenshot(client, output_dir / "02_reviews.png", run_summary, "reviews_opened")
                save_text(output_dir / "page_reviews.html", get_page_html(client))
            return finalize_early_failure("reviews_panel_not_opened", review_phase_started_at=review_phase_started_at)

        run_summary["reviewsPanel"] = reviews_panel
        if args.keep_debug_artifacts:
            safe_capture_screenshot(client, output_dir / "02_reviews.png", run_summary, "reviews_opened")
            save_text(output_dir / "page_reviews.html", get_page_html(client))
        initial_scroll_state = get_reviews_scroll_state(client)
        run_summary["initialReviewsState"] = initial_scroll_state
        declared_review_total_info = get_declared_review_total(client)
        declared_review_total = declared_review_total_info.get("declaredReviewTotal")
        run_summary["declaredReviewTotalInfo"] = declared_review_total_info
        run_summary["declaredReviewTotal"] = declared_review_total
        run_summary["declaredTotalSettleSeconds"] = args.declared_total_settle_seconds
        run_summary["declaredTotalFastStopUsed"] = False
        run_summary["declaredTotalFinalCheck"] = None
        fallback_stable_rounds = max(args.no_growth_cycles, args.stable_rounds)
        run_summary["fallbackStableRoundsRequired"] = fallback_stable_rounds

        scroll_results: list[dict[str, Any]] = []
        growth_events: list[dict[str, Any]] = []
        network_events_during_scroll = 0
        no_growth_cycles = 0
        growth_snapshot_count = 0

        last_scroll_height = initial_scroll_state.get("scrollHeight")
        last_unique_review_count = initial_scroll_state.get("uniqueReviewIdCount")

        scroll_started_at = time.monotonic()
        stop_reason = "max_scrolls_reached"
        exhausted = False
        safety_timeout_hit = False

        latest_wall = latest_review_request_wall_time(requests, review_phase_started_at)
        last_network_activity_time = time.monotonic() if latest_wall is not None else scroll_started_at

        for iteration in range(args.max_scrolls):
            if declared_review_total is None:
                declared_review_total_info = get_declared_review_total(client)
                declared_review_total = declared_review_total_info.get("declaredReviewTotal")
                if declared_review_total is not None:
                    run_summary["declaredReviewTotalInfo"] = declared_review_total_info
                    run_summary["declaredReviewTotal"] = declared_review_total

            before_latest_wall = latest_review_request_wall_time(requests, review_phase_started_at)
            scroll_result = scroll_reviews(client)
            scroll_result["iteration"] = iteration + 1
            scroll_result["declaredReviewTotal"] = declared_review_total

            time.sleep(scroll_delay)
            pump_events(client, requests, time_limit=2.0)
            current_state = get_reviews_scroll_state(client)
            scroll_result["stateAfterDelay"] = current_state

            after_latest_wall = latest_review_request_wall_time(requests, review_phase_started_at)
            new_network_events = count_review_requests_since(
                requests,
                before_latest_wall,
                review_phase_started_at,
            )
            if new_network_events > 0:
                network_events_during_scroll += new_network_events
                last_network_activity_time = time.monotonic()

            current_scroll_height = current_state.get("scrollHeight")
            current_unique_review_count = current_state.get("uniqueReviewIdCount")
            distance_to_bottom = current_state.get("distanceToBottom")
            at_bottom = isinstance(distance_to_bottom, (int, float)) and distance_to_bottom <= 120
            declared_total_reached = (
                isinstance(declared_review_total, int)
                and isinstance(current_unique_review_count, int)
                and current_unique_review_count >= declared_review_total
            )
            declared_total_fast_stop_ready = False

            grew = (
                isinstance(current_scroll_height, (int, float))
                and isinstance(last_scroll_height, (int, float))
                and current_scroll_height > last_scroll_height
            ) or (
                isinstance(current_unique_review_count, int)
                and isinstance(last_unique_review_count, int)
                and current_unique_review_count > last_unique_review_count
            )

            if grew:
                no_growth_cycles = 0
                growth_snapshot_count += 1
                growth_event: dict[str, Any] = {
                    "iteration": iteration + 1,
                    "uniqueReviewIdCount": current_unique_review_count,
                    "scrollHeight": current_scroll_height,
                }
                if args.keep_debug_artifacts:
                    growth_snapshot_path = output_dir / f"page_reviews_growth_{growth_snapshot_count:03d}.html"
                    save_text(growth_snapshot_path, get_page_html(client))
                    growth_event["snapshotPath"] = str(growth_snapshot_path)
                growth_events.append(growth_event)
            elif at_bottom:
                if declared_total_reached:
                    settle_before = {
                        "uniqueReviewIdCount": current_unique_review_count,
                        "scrollHeight": current_scroll_height,
                        "distanceToBottom": distance_to_bottom,
                    }
                    settle_wait_seconds = max(args.declared_total_settle_seconds, 0.2)
                    time.sleep(settle_wait_seconds)
                    pump_events(client, requests, time_limit=min(max(settle_wait_seconds, 0.5), 2.0))
                    settled_state = get_reviews_scroll_state(client)
                    scroll_result["declaredTotalSettle"] = {
                        "waitSeconds": settle_wait_seconds,
                        "stateAfterSettle": settled_state,
                    }
                    current_state = settled_state
                    current_scroll_height = current_state.get("scrollHeight")
                    current_unique_review_count = current_state.get("uniqueReviewIdCount")
                    distance_to_bottom = current_state.get("distanceToBottom")
                    at_bottom = isinstance(distance_to_bottom, (int, float)) and distance_to_bottom <= 120
                    declared_total_reached = (
                        isinstance(declared_review_total, int)
                        and isinstance(current_unique_review_count, int)
                        and current_unique_review_count >= declared_review_total
                    )
                    settled_grew = (
                        isinstance(current_scroll_height, (int, float))
                        and isinstance(last_scroll_height, (int, float))
                        and current_scroll_height > last_scroll_height
                    ) or (
                        isinstance(current_unique_review_count, int)
                        and isinstance(last_unique_review_count, int)
                        and current_unique_review_count > last_unique_review_count
                    )
                    run_summary["declaredTotalFinalCheck"] = {
                        "iteration": iteration + 1,
                        "before": settle_before,
                        "after": {
                            "uniqueReviewIdCount": current_unique_review_count,
                            "scrollHeight": current_scroll_height,
                            "distanceToBottom": distance_to_bottom,
                        },
                        "settleSeconds": settle_wait_seconds,
                        "grewDuringSettle": settled_grew,
                        "atBottomAfterSettle": at_bottom,
                        "declaredTotalReachedAfterSettle": declared_total_reached,
                    }
                    if settled_grew:
                        no_growth_cycles = 0
                        growth_snapshot_count += 1
                        growth_event = {
                            "iteration": iteration + 1,
                            "viaDeclaredSettle": True,
                            "uniqueReviewIdCount": current_unique_review_count,
                            "scrollHeight": current_scroll_height,
                        }
                        if args.keep_debug_artifacts:
                            growth_snapshot_path = output_dir / f"page_reviews_growth_{growth_snapshot_count:03d}.html"
                            save_text(growth_snapshot_path, get_page_html(client))
                            growth_event["snapshotPath"] = str(growth_snapshot_path)
                        growth_events.append(growth_event)
                    else:
                        declared_total_fast_stop_ready = at_bottom and declared_total_reached
                else:
                    probe = perform_bottom_probe(client, requests, args.bottom_wait_seconds)
                    scroll_result["bottomProbe"] = probe
                    probed_state = probe.get("stateAfterProbe")
                    if isinstance(probed_state, dict):
                        current_state = probed_state
                        scroll_result["stateAfterProbe"] = probed_state
                        current_scroll_height = current_state.get("scrollHeight")
                        current_unique_review_count = current_state.get("uniqueReviewIdCount")
                        distance_to_bottom = current_state.get("distanceToBottom")
                        at_bottom = isinstance(distance_to_bottom, (int, float)) and distance_to_bottom <= 120
                    after_probe_wall = latest_review_request_wall_time(requests, review_phase_started_at)
                    probe_network_events = count_review_requests_since(
                        requests,
                        after_latest_wall,
                        review_phase_started_at,
                    )
                    if probe_network_events > 0:
                        network_events_during_scroll += probe_network_events
                        last_network_activity_time = time.monotonic()
                        after_latest_wall = after_probe_wall

                    grew_after_probe = (
                        isinstance(current_scroll_height, (int, float))
                        and isinstance(last_scroll_height, (int, float))
                        and current_scroll_height > last_scroll_height
                    ) or (
                        isinstance(current_unique_review_count, int)
                        and isinstance(last_unique_review_count, int)
                        and current_unique_review_count > last_unique_review_count
                    )
                    if grew_after_probe:
                        no_growth_cycles = 0
                        growth_snapshot_count += 1
                        growth_event = {
                            "iteration": iteration + 1,
                            "viaProbe": True,
                            "uniqueReviewIdCount": current_unique_review_count,
                            "scrollHeight": current_scroll_height,
                        }
                        if args.keep_debug_artifacts:
                            growth_snapshot_path = output_dir / f"page_reviews_growth_{growth_snapshot_count:03d}.html"
                            save_text(growth_snapshot_path, get_page_html(client))
                            growth_event["snapshotPath"] = str(growth_snapshot_path)
                        growth_events.append(growth_event)
                    else:
                        no_growth_cycles += 1
            else:
                no_growth_cycles = 0

            if isinstance(current_scroll_height, (int, float)):
                if not isinstance(last_scroll_height, (int, float)) or current_scroll_height > last_scroll_height:
                    last_scroll_height = current_scroll_height
            if isinstance(current_unique_review_count, int):
                if not isinstance(last_unique_review_count, int) or current_unique_review_count > last_unique_review_count:
                    last_unique_review_count = current_unique_review_count

            network_idle_seconds = time.monotonic() - last_network_activity_time
            scroll_result["noGrowthCycles"] = no_growth_cycles
            scroll_result["networkIdleSeconds"] = network_idle_seconds
            scroll_result["declaredTotalReached"] = declared_total_reached
            scroll_result["declaredTotalFastStopReady"] = declared_total_fast_stop_ready
            scroll_results.append(scroll_result)

            if declared_total_fast_stop_ready:
                run_summary["declaredTotalFastStopUsed"] = True
                stop_reason = "declared_total_reached_fast"
                break
            if (
                at_bottom
                and no_growth_cycles >= fallback_stable_rounds
                and network_idle_seconds >= args.network_idle_seconds
            ):
                stop_reason = "exhausted_no_growth_at_bottom"
                exhausted = True
                break
            if time.monotonic() - scroll_started_at >= args.max_scroll_seconds:
                stop_reason = "safety_timeout_reached"
                safety_timeout_hit = True
                break

        run_summary["scrollResults"] = scroll_results
        run_summary["scrollStopReason"] = stop_reason
        run_summary["exhausted"] = exhausted
        run_summary["scrollSafetyTimeoutHit"] = safety_timeout_hit
        run_summary["growthEvents"] = growth_events
        run_summary["networkEventsDuringScroll"] = network_events_during_scroll
        run_summary["finalNetworkIdleSeconds"] = time.monotonic() - last_network_activity_time
        run_summary["noGrowthCycles"] = no_growth_cycles
        final_reviews_state = get_reviews_scroll_state(client)
        run_summary["finalReviewsState"] = final_reviews_state
        run_summary["reachedDeclaredReviewTotal"] = (
            isinstance(run_summary.get("declaredReviewTotal"), int)
            and isinstance(final_reviews_state.get("uniqueReviewIdCount"), int)
            and final_reviews_state["uniqueReviewIdCount"] >= run_summary["declaredReviewTotal"]
        )
        run_summary["reachedReviewPaneEnd"] = (
            isinstance(final_reviews_state.get("distanceToBottom"), (int, float))
            and final_reviews_state["distanceToBottom"] <= 120
        )
        run_summary["finalUniqueReviewIdCount"] = final_reviews_state.get("uniqueReviewIdCount")
        run_summary["finalScrollTop"] = final_reviews_state.get("scrollTop")
        run_summary["finalScrollHeight"] = final_reviews_state.get("scrollHeight")
        review_expansion = expand_all_review_texts(client)
        run_summary["reviewExpansion"] = review_expansion
        if review_expansion.get("clickedCount"):
            time.sleep(1.5)
            pump_events(client, requests, time_limit=2.0)
        if args.keep_debug_artifacts:
            safe_capture_screenshot(client, output_dir / "03_reviews_scrolled.png", run_summary, "reviews_scrolled")
        save_text(output_dir / "page_reviews_after_scroll.html", get_page_html(client))

        matched_requests = enrich_requests(client, requests, output_dir)
        batchexecute_requests = [
            request
            for request in matched_requests
            if "MapsWizUi/data/batchexecute" in str(request.get("url", ""))
        ]
        all_xhr_requests = collect_review_phase_xhr_requests(requests, review_phase_started_at)

        run_summary["matchedRequestCount"] = len(matched_requests)
        run_summary["batchexecuteCount"] = len(batchexecute_requests)
        run_summary["reviewPhaseXhrCount"] = len(all_xhr_requests)
        run_summary["captureSuccessful"] = True
        run_summary["finishedAt"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())

        save_text(output_dir / "run_summary.json", json.dumps(run_summary, indent=2, ensure_ascii=False))
        if args.keep_debug_artifacts:
            save_text(output_dir / "matched_requests.json", json.dumps(matched_requests, indent=2, ensure_ascii=False))
            save_text(
                output_dir / "batchexecute_requests.json",
                json.dumps(batchexecute_requests, indent=2, ensure_ascii=False),
            )
            save_text(output_dir / "all_xhr_requests.json", json.dumps(all_xhr_requests, indent=2, ensure_ascii=False))

        print(f"Saved run summary to {output_dir / 'run_summary.json'}")
        if args.keep_debug_artifacts:
            print(f"Saved matched requests to {output_dir / 'matched_requests.json'}")
            print(f"Saved batchexecute requests to {output_dir / 'batchexecute_requests.json'}")
            print(f"Saved review-phase XHR requests to {output_dir / 'all_xhr_requests.json'}")
        print(f"Matched requests: {len(matched_requests)}")
        print(f"Matched batchexecute requests: {len(batchexecute_requests)}")
        return {
            "outputDir": str(output_dir),
            "runSummary": run_summary,
        }
    except Exception as exc:  # noqa: BLE001
        reason = "unexpected_capture_exception"
        run_summary["failureReason"] = reason
        run_summary["scrollStopReason"] = reason
        run_summary["captureSuccessful"] = False
        run_summary["exceptionType"] = type(exc).__name__
        run_summary["exception"] = str(exc)
        run_summary["finishedAt"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        run_summary.setdefault("matchedRequestCount", 0)
        run_summary.setdefault("batchexecuteCount", 0)
        run_summary.setdefault("reviewPhaseXhrCount", 0)
        save_text(output_dir / "run_summary.json", json.dumps(run_summary, indent=2, ensure_ascii=False))
        print(f"Saved run summary to {output_dir / 'run_summary.json'}")
        print(f"Capture stopped early: {reason} ({type(exc).__name__}: {exc})")
        return {
            "outputDir": str(output_dir),
            "runSummary": run_summary,
        }
    finally:
        if client is not None:
            client.close()
        chrome_process.terminate()
        try:
            chrome_process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            chrome_process.kill()
        if not args.keep_chrome_profile and chrome_profile_dir.exists():
            shutil.rmtree(chrome_profile_dir, ignore_errors=True)
        if not args.keep_browser_logs:
            for path in (output_dir / "chrome.log", output_dir / "chrome-netlog.json"):
                if path.exists():
                    path.unlink(missing_ok=True)


def gather_attempt_reviews(attempt_dir: pathlib.Path) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    html_candidates = [attempt_dir / "page_reviews_after_scroll.html", attempt_dir / "page_reviews.html"]
    html_candidates.extend(sorted(attempt_dir.glob("page_reviews_growth_*.html")))
    for path in html_candidates:
        records.extend(parse_reviews_from_html(path))
    return dedupe_review_records(records)


def count_reviews_in_file(path: pathlib.Path) -> int | None:
    if not path.is_file():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return len(payload) if isinstance(payload, list) else None


def load_successful_capture_metadata(output_dir: pathlib.Path) -> dict[str, Any] | None:
    run_summary_path = output_dir / "run_summary.json"
    reviews_path = output_dir / "reviews.json"
    if not run_summary_path.is_file() or not reviews_path.is_file():
        return None
    try:
        run_summary = json.loads(run_summary_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    if not bool(run_summary.get("captureSuccessful")):
        return None
    return {
        "review_count": count_reviews_in_file(reviews_path),
        "scroll_stop_reason": run_summary.get("scrollStopReason"),
        "failure_reason": run_summary.get("failureReason"),
        "declared_review_total": run_summary.get("declaredReviewTotal"),
        "final_unique_review_id_count": run_summary.get("finalUniqueReviewIdCount"),
        "run_summary_path": str(run_summary_path),
        "reviews_path": str(reviews_path),
    }


def run_single_capture(
    args: argparse.Namespace,
    url: str,
    place_id: str | None,
    output_dir: pathlib.Path,
) -> dict[str, Any]:
    run_args = argparse.Namespace(**vars(args))
    run_args.url = url
    run_args.place_id = place_id

    output_dir = pathlib.Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    attempts: list[dict[str, Any]] = []
    max_attempts = max(run_args.retry_runs, 1)
    low_count_threshold = 12
    latest_declared_review_total: int | None = None

    for attempt_index in range(max_attempts):
        attempt_number = attempt_index + 1
        attempt_output_dir = output_dir if attempt_number == 1 else output_dir / f"retry_{attempt_number}"
        delay_multiplier = 1.0 + (0.5 * attempt_index)
        attempt_scroll_delay = run_args.scroll_delay * delay_multiplier

        try:
            attempt_result = run_capture_once(run_args, attempt_output_dir, attempt_scroll_delay)
        except Exception as exc:  # noqa: BLE001
            attempt_output_dir.mkdir(parents=True, exist_ok=True)
            run_summary = {
                "url": run_args.url,
                "placeId": run_args.place_id,
                "startedAt": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                "finishedAt": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                "scrollDelayUsed": attempt_scroll_delay,
                "captureSuccessful": False,
                "failureReason": "capture_attempt_exception",
                "scrollStopReason": "capture_attempt_exception",
                "exceptionType": type(exc).__name__,
                "exception": str(exc),
                "matchedRequestCount": 0,
                "batchexecuteCount": 0,
                "reviewPhaseXhrCount": 0,
            }
            save_text(attempt_output_dir / "run_summary.json", json.dumps(run_summary, indent=2, ensure_ascii=False))
            print(f"Saved run summary to {attempt_output_dir / 'run_summary.json'}")
            print(f"Capture attempt failed before cleanup could complete: {type(exc).__name__}: {exc}")
            attempt_result = {
                "outputDir": str(attempt_output_dir),
                "runSummary": run_summary,
            }
        run_summary = attempt_result["runSummary"]
        attempts.append(
            {
                "attempt": attempt_number,
                "outputDir": str(attempt_output_dir),
                "scrollDelayUsed": attempt_scroll_delay,
                "captureSuccessful": bool(run_summary.get("captureSuccessful")),
                "failureReason": run_summary.get("failureReason"),
                "finalUniqueReviewIdCount": run_summary.get("finalUniqueReviewIdCount", 0),
                "scrollStopReason": run_summary.get("scrollStopReason"),
                "declaredReviewTotal": run_summary.get("declaredReviewTotal"),
            }
        )

        final_count = int(run_summary.get("finalUniqueReviewIdCount") or 0)
        stop_reason = str(run_summary.get("scrollStopReason") or "")
        capture_successful = bool(run_summary.get("captureSuccessful"))
        latest_declared_review_total = run_summary.get("declaredReviewTotal") if isinstance(run_summary.get("declaredReviewTotal"), int) else latest_declared_review_total
        if capture_successful and stop_reason in {"declared_total_reached_fast", "exhausted_no_growth_at_bottom"}:
            break
        if capture_successful and isinstance(latest_declared_review_total, int):
            if final_count >= latest_declared_review_total:
                break
        elif capture_successful and final_count >= low_count_threshold:
            break

    merged_records: list[dict[str, Any]] = []
    for attempt in attempts:
        merged_records.extend(gather_attempt_reviews(pathlib.Path(attempt["outputDir"])))
    merged_records = dedupe_review_records(merged_records)

    merged_output = [
        {
            "reviewer_name": record["reviewer_name"],
            "review_text": record["review_text"],
            "star_rating": record.get("star_rating"),
            "review_time": record.get("review_time"),
            "like_count": record.get("like_count"),
            "has_owner_response": record.get("has_owner_response", False),
            "owner_response_time": record.get("owner_response_time"),
            "owner_response_text": record.get("owner_response_text"),
        }
        for record in merged_records
    ]
    reviews_path = output_dir / "reviews.json"
    successful_attempts = [attempt for attempt in attempts if attempt.get("captureSuccessful")]
    if merged_output and successful_attempts:
        save_text(reviews_path, json.dumps(merged_output, ensure_ascii=False, indent=2))
    elif reviews_path.exists():
        reviews_path.unlink(missing_ok=True)

    primary_summary_path = output_dir / "run_summary.json"
    if primary_summary_path.is_file():
        primary_summary = json.loads(primary_summary_path.read_text(encoding="utf-8"))
    else:
        primary_summary = {}
    primary_summary["retryRunsRequested"] = run_args.retry_runs
    primary_summary["retryRunsExecuted"] = len(attempts)
    primary_summary["retryAttempts"] = attempts
    primary_summary["mergedReviewCountAcrossAttempts"] = len(merged_output)
    primary_summary["reviewsPath"] = str(reviews_path) if reviews_path.exists() else None
    primary_summary["latestDeclaredReviewTotalAcrossAttempts"] = latest_declared_review_total
    save_text(primary_summary_path, json.dumps(primary_summary, ensure_ascii=False, indent=2))

    save_text(output_dir / "retry_summary.json", json.dumps({"attempts": attempts}, ensure_ascii=False, indent=2))

    if reviews_path.exists():
        print(f"Saved reviews to {reviews_path}")
    else:
        print("No successful review capture; reviews.json was not written.")
    print(f"Review count across attempts: {len(merged_output)}")
    return {
        "exitCode": 0 if reviews_path.exists() else 1,
        "success": reviews_path.exists(),
        "outputDir": str(output_dir),
        "reviewsPath": str(reviews_path) if reviews_path.exists() else None,
        "reviewCount": len(merged_output),
        "declaredReviewTotal": latest_declared_review_total,
        "finalUniqueReviewIdCount": attempts[-1].get("finalUniqueReviewIdCount") if attempts else None,
        "scrollStopReason": attempts[-1].get("scrollStopReason") if attempts else None,
        "failureReason": None if reviews_path.exists() else (attempts[-1].get("failureReason") if attempts else None),
        "retryAttempts": attempts,
    }


def write_batch_summary(path: pathlib.Path, summary: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    save_text(path, json.dumps(summary, ensure_ascii=False, indent=2))


def main() -> int:
    args = parse_args()
    urls_file = pathlib.Path(args.urls_file)
    artifacts_root = pathlib.Path(args.artifacts_root)

    if args.url:
        place_id = args.place_id if isinstance(args.place_id, str) and args.place_id.strip() else None
        output_dir = pathlib.Path(args.output_dir)
        if place_id and args.output_dir == DEFAULT_OUTPUT_DIR:
            output_dir = artifacts_root / place_id
        result = run_single_capture(args, args.url, place_id, output_dir)
        return int(result["exitCode"])

    if args.place_id:
        resolved_url = resolve_url_from_place_id(args.place_id, urls_file)
        output_dir = pathlib.Path(args.output_dir)
        if args.output_dir == DEFAULT_OUTPUT_DIR:
            output_dir = artifacts_root / args.place_id
        result = run_single_capture(args, resolved_url, args.place_id, output_dir)
        return int(result["exitCode"])

    places = load_resolved_places(urls_file)
    artifacts_root.mkdir(parents=True, exist_ok=True)
    run_summary_out = (
        pathlib.Path(args.run_summary_out)
        if isinstance(args.run_summary_out, str) and args.run_summary_out.strip()
        else artifacts_root / "capture_reviews_run_summary.json"
    )

    batch_started_at = utc_now_iso()
    batch_started_monotonic = time.monotonic()
    batch_summary: dict[str, Any] = {
        "mode": "all_resolved_places",
        "startedAt": batch_started_at,
        "finishedAt": None,
        "urlsFile": str(urls_file),
        "artifactsRoot": str(artifacts_root),
        "runSummaryOut": str(run_summary_out),
        "totalPlaces": len(places),
        "processedPlaces": 0,
        "successCount": 0,
        "skippedCount": 0,
        "failedCount": 0,
        "totalElapsedSeconds": 0.0,
        "places": [],
    }
    write_batch_summary(run_summary_out, batch_summary)

    for index, place in enumerate(places, start=1):
        place_id = place["place_id"]
        place_name = place["place_name"]
        url = place["url"]
        output_dir = artifacts_root / place_id
        place_started_at = utc_now_iso()
        place_started_monotonic = time.monotonic()

        print(f"[{index}/{len(places)}] START {place_id} ({place_name})")
        existing = load_successful_capture_metadata(output_dir)

        if existing is not None:
            elapsed_seconds = round(time.monotonic() - place_started_monotonic, 2)
            entry = {
                "place_id": place_id,
                "place_name": place_name,
                "status": "skipped",
                "skipped_reason": "already_successful",
                "output_dir": str(output_dir),
                "started_at": place_started_at,
                "finished_at": utc_now_iso(),
                "elapsed_seconds": elapsed_seconds,
                "review_count": existing.get("review_count"),
                "declared_review_total": existing.get("declared_review_total"),
                "final_unique_review_id_count": existing.get("final_unique_review_id_count"),
                "scroll_stop_reason": existing.get("scroll_stop_reason"),
                "failure_reason": existing.get("failure_reason"),
                "run_summary_path": existing.get("run_summary_path"),
                "reviews_path": existing.get("reviews_path"),
            }
            batch_summary["skippedCount"] += 1
            print(
                f"[{index}/{len(places)}] SKIP {place_id} elapsed={elapsed_seconds}s "
                f"reviews={entry['review_count']} reason=already_successful"
            )
        else:
            elapsed_seconds = round(time.monotonic() - place_started_monotonic, 2)
            try:
                result = run_single_capture(args, url, place_id, output_dir)
            except Exception as exc:  # noqa: BLE001
                output_dir.mkdir(parents=True, exist_ok=True)
                failure_summary = {
                    "url": url,
                    "placeId": place_id,
                    "startedAt": place_started_at,
                    "finishedAt": utc_now_iso(),
                    "captureSuccessful": False,
                    "failureReason": "batch_place_exception",
                    "scrollStopReason": "batch_place_exception",
                    "exceptionType": type(exc).__name__,
                    "exception": str(exc),
                    "matchedRequestCount": 0,
                    "batchexecuteCount": 0,
                    "reviewPhaseXhrCount": 0,
                }
                save_text(output_dir / "run_summary.json", json.dumps(failure_summary, indent=2, ensure_ascii=False))
                result = {
                    "exitCode": 1,
                    "success": False,
                    "outputDir": str(output_dir),
                    "reviewsPath": None,
                    "reviewCount": 0,
                    "declaredReviewTotal": None,
                    "finalUniqueReviewIdCount": None,
                    "scrollStopReason": "batch_place_exception",
                    "failureReason": f"{type(exc).__name__}: {exc}",
                    "retryAttempts": [],
                }
            elapsed_seconds = round(time.monotonic() - place_started_monotonic, 2)
            status = "done" if result.get("success") else "failed"
            entry = {
                "place_id": place_id,
                "place_name": place_name,
                "status": status,
                "skipped_reason": None,
                "output_dir": str(output_dir),
                "started_at": place_started_at,
                "finished_at": utc_now_iso(),
                "elapsed_seconds": elapsed_seconds,
                "review_count": result.get("reviewCount"),
                "declared_review_total": result.get("declaredReviewTotal"),
                "final_unique_review_id_count": result.get("finalUniqueReviewIdCount"),
                "scroll_stop_reason": result.get("scrollStopReason"),
                "failure_reason": result.get("failureReason"),
                "run_summary_path": str(output_dir / "run_summary.json"),
                "reviews_path": result.get("reviewsPath"),
            }
            if status == "done":
                batch_summary["successCount"] += 1
                print(
                    f"[{index}/{len(places)}] DONE {place_id} elapsed={elapsed_seconds}s "
                    f"reviews={entry['review_count']} reason={entry['scroll_stop_reason']}"
                )
            else:
                batch_summary["failedCount"] += 1
                print(
                    f"[{index}/{len(places)}] FAIL {place_id} elapsed={elapsed_seconds}s "
                    f"reviews={entry['review_count']} reason={entry['failure_reason'] or entry['scroll_stop_reason']}"
                )

        batch_summary["places"].append(entry)
        batch_summary["processedPlaces"] = len(batch_summary["places"])
        batch_summary["totalElapsedSeconds"] = round(time.monotonic() - batch_started_monotonic, 2)
        write_batch_summary(run_summary_out, batch_summary)

        print(
            "Totals: "
            f"success={batch_summary['successCount']} "
            f"skipped={batch_summary['skippedCount']} "
            f"failed={batch_summary['failedCount']} "
            f"processed={batch_summary['processedPlaces']}/{batch_summary['totalPlaces']} "
            f"elapsed={batch_summary['totalElapsedSeconds']}s"
        )

    batch_summary["finishedAt"] = utc_now_iso()
    batch_summary["totalElapsedSeconds"] = round(time.monotonic() - batch_started_monotonic, 2)
    write_batch_summary(run_summary_out, batch_summary)
    print(f"Saved batch summary to {run_summary_out}")
    print(
        "Batch complete: "
        f"success={batch_summary['successCount']} "
        f"skipped={batch_summary['skippedCount']} "
        f"failed={batch_summary['failedCount']}"
    )
    return 0 if batch_summary["failedCount"] == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
