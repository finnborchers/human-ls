#!/usr/bin/env python3

import os
import time
from datetime import datetime, timezone
from pathlib import Path

import merge_fullrun_v1_batches as merge_runner
import run_openai_batch_v1 as batch_runner


SCOPE = os.getenv("FULLRUN_SCOPE", "10000_ids")
POLL_SECONDS = int(os.getenv("FULLRUN_POLL_SECONDS", "300"))
SUBMIT_LIMIT = int(os.getenv("FULLRUN_SUBMIT_LIMIT", "1"))
RESUBMIT_FAILED = os.getenv("FULLRUN_RESUBMIT_FAILED")


ACTIVE_STATUSES = {"validating", "in_progress", "finalizing"}
DONE_STATUSES = {"completed"}
TERMINAL_FAILED_STATUSES = {"failed", "cancelled", "expired"}


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def scope_config() -> dict:
    manifest = batch_runner.load_manifest()
    config = manifest.get("scopes", {}).get(SCOPE)
    if not config:
        available = ", ".join(sorted(manifest.get("scopes", {}).keys()))
        raise KeyError(f"Unknown FULLRUN_SCOPE={SCOPE!r}. Available: {available}")
    return config


def should_resubmit_failed() -> bool:
    if RESUBMIT_FAILED is not None:
        return RESUBMIT_FAILED == "1"
    return SCOPE == "10000_ids"


def batch_state(batch_info: dict) -> dict:
    return batch_runner.load_json(batch_info["job_path"], {})


def batch_status(state: dict) -> str | None:
    return (state.get("batch") or {}).get("status")


def batch_queue_failed(state: dict) -> bool:
    errors = ((state.get("batch") or {}).get("errors") or {}).get("data") or []
    return any(item.get("code") == "token_limit_exceeded" for item in errors if isinstance(item, dict))


def is_materialized(batch_info: dict) -> bool:
    return Path(batch_info["normalized_path"]).exists()


def classify_batches(config: dict) -> dict[str, list[str]]:
    groups = {
        "active": [],
        "completed_unfetched": [],
        "materialized": [],
        "failed_queue": [],
        "failed_other": [],
        "pending": [],
    }

    for batch_info in config["batches"]:
        state = batch_state(batch_info)
        status = batch_status(state)
        name = batch_info["batch_name"]

        if is_materialized(batch_info):
            groups["materialized"].append(name)
            continue

        if status in ACTIVE_STATUSES:
            groups["active"].append(name)
        elif status in DONE_STATUSES:
            groups["completed_unfetched"].append(name)
        elif status in TERMINAL_FAILED_STATUSES:
            if batch_queue_failed(state):
                groups["failed_queue"].append(name)
            else:
                groups["failed_other"].append(name)
        else:
            groups["pending"].append(name)

    return groups


def print_cycle_summary(config: dict, groups: dict[str, list[str]]) -> None:
    print(
        f"[{utc_now()}] scope={SCOPE} "
        f"active={len(groups['active'])} "
        f"completed_unfetched={len(groups['completed_unfetched'])} "
        f"materialized={len(groups['materialized'])} "
        f"failed_queue={len(groups['failed_queue'])} "
        f"failed_other={len(groups['failed_other'])} "
        f"pending={len(groups['pending'])} "
        f"target={config['total_reviews']}"
    )
    if groups["active"]:
        print(f"[info] active batches: {', '.join(groups['active'])}")
    if groups["failed_other"]:
        print(f"[warn] terminal failed batches: {', '.join(groups['failed_other'])}")


def all_finished(config: dict, groups: dict[str, list[str]]) -> bool:
    total = config["batch_count"]
    done_count = len(groups["materialized"]) + len(groups["failed_other"])
    return done_count == total and not groups["active"] and not groups["completed_unfetched"] and not groups["pending"] and not groups["failed_queue"]


def perform_status_and_fetch(config: dict) -> None:
    batch_runner.SCOPE = SCOPE
    batch_runner.status_scope(config)
    batch_runner.fetch_scope(config)


def maybe_submit_next(config: dict, groups: dict[str, list[str]]) -> bool:
    if groups["active"] or groups["completed_unfetched"]:
        print("[wait] no submit while another batch is active or waiting to be fetched.")
        return False

    batch_runner.SCOPE = SCOPE
    batch_runner.SUBMIT_LIMIT = SUBMIT_LIMIT
    batch_runner.RESUBMIT_FAILED = should_resubmit_failed()
    before = {
        batch_info["batch_name"]: batch_status(batch_state(batch_info))
        for batch_info in config["batches"]
    }
    batch_runner.submit_scope(config)
    after = {
        batch_info["batch_name"]: batch_status(batch_state(batch_info))
        for batch_info in config["batches"]
    }
    submitted = [name for name in after if before.get(name) != after.get(name) and after.get(name) is not None]
    if submitted:
        print(f"[ok] submitted next batch: {', '.join(submitted)}")
        return True

    print("[done] no submit candidate available in this cycle.")
    return False


def main() -> None:
    print(
        f"[start] FULLRUN autopilot scope={SCOPE} poll_seconds={POLL_SECONDS} "
        f"submit_limit={SUBMIT_LIMIT} resubmit_failed={int(should_resubmit_failed())}"
    )

    while True:
        config = scope_config()
        perform_status_and_fetch(config)
        groups = classify_batches(config)
        print_cycle_summary(config, groups)

        if all_finished(config, groups):
            print(f"[ok] scope {SCOPE} fully settled. merging outputs...")
            merge_runner.SCOPE = SCOPE
            merge_runner.merge_scope(batch_runner.load_manifest(), SCOPE)
            print(f"[ok] autopilot finished for scope {SCOPE}")
            return

        maybe_submit_next(config, groups)
        print(f"[sleep] waiting {POLL_SECONDS}s before next cycle.")
        time.sleep(POLL_SECONDS)


if __name__ == "__main__":
    main()
