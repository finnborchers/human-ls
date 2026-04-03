#!/usr/bin/env python3
"""
Launch headless Chrome, open a Google Maps place page, and capture review-related
network requests from the Chrome DevTools Protocol (CDP).

This script is intended for inspection and debugging. It saves the matched
request metadata, post bodies, response snippets, screenshots, and a small run
summary so the request flow can be studied afterward.

Usage:
    python3 scripts/capture_google_maps_review_requests.py
"""

from __future__ import annotations

import argparse
import base64
import hashlib
import json
import os
import pathlib
import queue
import random
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
        description="Capture internal Google Maps review requests via headless Chrome."
    )
    parser.add_argument("--url", default=DEFAULT_URL, help="Google Maps place URL to inspect.")
    parser.add_argument(
        "--output-dir",
        default="artifacts/google-maps-review-capture",
        help="Directory where capture artifacts will be written.",
    )
    parser.add_argument(
        "--chrome-path",
        default=DEFAULT_CHROME_PATH,
        help="Path to the Chrome executable.",
    )
    parser.add_argument(
        "--headed",
        action="store_true",
        help="Launch Chrome with a visible window instead of headless mode.",
    )
    parser.add_argument("--remote-debugging-port", type=int, default=9222, help="CDP port for Chrome.")
    parser.add_argument("--lang", default="de-DE", help="Browser language to use.")
    parser.add_argument("--window-size", default="1440,2200", help="Headless window size.")
    parser.add_argument("--load-timeout", type=float, default=25.0, help="Navigation timeout in seconds.")
    parser.add_argument("--review-timeout", type=float, default=20.0, help="Timeout for review UI steps.")
    parser.add_argument("--scroll-count", type=int, default=5, help="Number of scroll attempts in the review pane.")
    parser.add_argument("--scroll-delay", type=float, default=2.0, help="Delay between review pane scrolls.")
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


def launch_chrome(args: argparse.Namespace, output_dir: pathlib.Path) -> subprocess.Popen[bytes]:
    profile_dir = output_dir / "chrome-profile"
    if profile_dir.exists():
        shutil.rmtree(profile_dir)
    profile_dir.mkdir(parents=True, exist_ok=True)

    chrome_log = output_dir / "chrome.log"
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
        f"--log-net-log={output_dir / 'chrome-netlog.json'}",
        "about:blank",
    ]
    if not args.headed:
        command.insert(1, "--headless=new")
    handle = chrome_log.open("wb")
    return subprocess.Popen(command, stdout=handle, stderr=subprocess.STDOUT)


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


def click_review_ui(client: CDPClient) -> dict[str, Any]:
    expression = r"""
        (() => {
          const isVisible = (element) => {
            const style = window.getComputedStyle(element);
            const rect = element.getBoundingClientRect();
            return style.visibility !== 'hidden' && style.display !== 'none' &&
              rect.width > 0 && rect.height > 0;
          };
          const clickCandidates = [
            'button[jsaction*="reviewChart.moreReviews"]',
            '[jsaction*="reviewChart.moreReviews"]',
            'button[aria-label*="Rezension"]',
            'button[aria-label*="review"]',
            '[role="button"][aria-label*="Rezension"]',
            '[role="button"][aria-label*="review"]',
          ];
          for (const selector of clickCandidates) {
            for (const element of document.querySelectorAll(selector)) {
              const label = (element.innerText || element.getAttribute('aria-label') || '').trim();
              if (!isVisible(element)) {
                continue;
              }
              element.click();
              return {clicked: true, strategy: 'selector', selector, label};
            }
          }

          const textNeedles = ['Alle Rezensionen', 'All reviews', 'Rezensionen', 'reviews'];
          for (const element of document.querySelectorAll('button,[role="button"],a')) {
            const label = ((element.innerText || element.textContent || '') + ' ' +
              (element.getAttribute('aria-label') || '')).trim();
            if (!label || !isVisible(element)) {
              continue;
            }
            if (textNeedles.some((needle) => label.includes(needle))) {
              element.click();
              return {clicked: true, strategy: 'text', label};
            }
          }

          return {clicked: false};
        })()
    """
    result = evaluate_json(client, expression, timeout=20.0)
    return result if isinstance(result, dict) else {"clicked": False}


def click_cookie_consent(client: CDPClient) -> dict[str, Any]:
    expression = r"""
        (() => {
          const labels = [
            'Alle akzeptieren',
            'Ich stimme zu',
            'Akzeptieren',
            'Accept all',
            'I agree',
            'Accept',
          ];
          for (const element of document.querySelectorAll('button,[role="button"]')) {
            const label = ((element.innerText || element.textContent || '') + ' ' +
              (element.getAttribute('aria-label') || '')).trim();
            if (!label) {
              continue;
            }
            if (labels.some((needle) => label.includes(needle))) {
              element.click();
              return {clicked: true, label};
            }
          }
          return {clicked: false};
        })()
    """
    result = evaluate_json(client, expression, timeout=15.0)
    return result if isinstance(result, dict) else {"clicked": False}


def wait_for_reviews_panel(client: CDPClient, timeout: float) -> Any:
    expression = r"""
        (() => {
          const reviewNodes = document.querySelectorAll('[data-review-id], .jftiEf, .wiI7pd');
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
          return false;
        })()
    """
    return wait_for_predicate(client, expression, timeout)


def scroll_reviews(client: CDPClient) -> dict[str, Any]:
    expression = r"""
        (() => {
          const candidates = [...document.querySelectorAll('*')]
            .filter((element) => element.scrollHeight > element.clientHeight + 300)
            .map((element) => ({
              element,
              scrollHeight: element.scrollHeight,
              clientHeight: element.clientHeight,
              score: element.scrollHeight - element.clientHeight,
            }))
            .sort((left, right) => right.score - left.score);

          const target = candidates.length > 0 ? candidates[0].element : null;
          if (!target) {
            window.scrollTo(0, document.body.scrollHeight);
            return {scrolledWindow: true};
          }
          const before = target.scrollTop;
          target.scrollTop = target.scrollTop + Math.max(target.clientHeight * 0.9, 600);
          return {
            scrolled: true,
            before,
            after: target.scrollTop,
            className: target.className || '',
            tagName: target.tagName,
            scrollHeight: target.scrollHeight,
            clientHeight: target.clientHeight,
          };
        })()
    """
    result = evaluate_json(client, expression, timeout=20.0)
    return result if isinstance(result, dict) else {"scrolled": False}


def get_page_html(client: CDPClient) -> str:
    expression = "document.documentElement.outerHTML"
    result = evaluate_json(client, expression, timeout=20.0)
    return result if isinstance(result, str) else ""


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


def request_matches(request: dict[str, Any]) -> bool:
    url = str(request.get("url", ""))
    if "MapsWizUi/data/batchexecute" in url:
        return True
    if "preview/place" in url:
        return True
    body = str(request.get("postData") or "")
    return "review" in body.lower() or "other_user_google_review_posts" in body.lower()


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


def main() -> int:
    args = parse_args()
    output_dir = pathlib.Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    chrome_process = launch_chrome(args, output_dir)
    client: CDPClient | None = None
    requests: dict[str, dict[str, Any]] = {}
    run_summary: dict[str, Any] = {
        "url": args.url,
        "startedAt": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    }

    try:
        version = wait_for_json(f"http://127.0.0.1:{args.remote_debugging_port}/json/version", timeout=15.0)
        targets = wait_for_json(f"http://127.0.0.1:{args.remote_debugging_port}/json/list", timeout=10.0)
        page_target = next(target for target in targets if target.get("type") == "page")
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

        client.call("Page.navigate", {"url": args.url}, timeout=args.load_timeout)
        pump_events(client, requests, time_limit=4.0)
        time.sleep(2.5)
        pump_events(client, requests, time_limit=4.0)

        capture_screenshot(client, output_dir / "01_loaded.png")
        save_text(output_dir / "page_loaded.html", get_page_html(client))
        button_snapshot = collect_button_snapshot(client)
        save_text(output_dir / "button_snapshot.json", json.dumps(button_snapshot, indent=2, ensure_ascii=False))

        consent_result = click_cookie_consent(client)
        run_summary["cookieConsent"] = consent_result
        if consent_result.get("clicked"):
            time.sleep(2.0)
            pump_events(client, requests, time_limit=3.0)

        review_click = click_review_ui(client)
        run_summary["reviewClick"] = review_click
        time.sleep(3.0)
        pump_events(client, requests, time_limit=5.0)

        reviews_panel = wait_for_reviews_panel(client, timeout=args.review_timeout)
        run_summary["reviewsPanel"] = reviews_panel
        capture_screenshot(client, output_dir / "02_reviews.png")
        save_text(output_dir / "page_reviews.html", get_page_html(client))

        scroll_results: list[dict[str, Any]] = []
        for _ in range(args.scroll_count):
            scroll_result = scroll_reviews(client)
            scroll_results.append(scroll_result)
            time.sleep(args.scroll_delay)
            pump_events(client, requests, time_limit=2.0)
        run_summary["scrollResults"] = scroll_results

        matched_requests = enrich_requests(client, requests, output_dir)
        batchexecute_requests = [
            request
            for request in matched_requests
            if "MapsWizUi/data/batchexecute" in str(request.get("url", ""))
        ]

        run_summary["matchedRequestCount"] = len(matched_requests)
        run_summary["batchexecuteCount"] = len(batchexecute_requests)
        run_summary["finishedAt"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())

        save_text(output_dir / "run_summary.json", json.dumps(run_summary, indent=2, ensure_ascii=False))
        save_text(output_dir / "matched_requests.json", json.dumps(matched_requests, indent=2, ensure_ascii=False))
        save_text(
            output_dir / "batchexecute_requests.json",
            json.dumps(batchexecute_requests, indent=2, ensure_ascii=False),
        )

        print(f"Saved run summary to {output_dir / 'run_summary.json'}")
        print(f"Saved matched requests to {output_dir / 'matched_requests.json'}")
        print(f"Saved batchexecute requests to {output_dir / 'batchexecute_requests.json'}")
        print(f"Matched requests: {len(matched_requests)}")
        print(f"Matched batchexecute requests: {len(batchexecute_requests)}")
        return 0
    finally:
        if client is not None:
            client.close()
        chrome_process.terminate()
        try:
            chrome_process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            chrome_process.kill()


if __name__ == "__main__":
    raise SystemExit(main())
