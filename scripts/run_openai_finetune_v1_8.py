#!/usr/bin/env python3

import json
import os
from datetime import datetime, timezone
from pathlib import Path

from dotenv import load_dotenv
from openai import OpenAI


load_dotenv()
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
if not OPENAI_API_KEY:
    raise ValueError("No OpenAI API key found in .env")

client = OpenAI(api_key=OPENAI_API_KEY)

FINETUNE_DIR = Path(os.getenv("FINETUNE_OUT_DIR", "analysis/llm/finetune"))
TRAIN_JSONL_PATH = Path(
    os.getenv("FINETUNE_TRAIN_JSONL_PATH", str(FINETUNE_DIR / "reviews_v1_8_train_180.jsonl"))
)
VALID_JSONL_PATH = Path(
    os.getenv("FINETUNE_VALID_JSONL_PATH", str(FINETUNE_DIR / "reviews_v1_8_valid_20.jsonl"))
)
JOB_PATH = Path(
    os.getenv("FINETUNE_JOB_OUT_PATH", str(FINETUNE_DIR / "reviews_v1_8_finetune_job.json"))
)
BASE_MODEL = os.getenv("FINETUNE_BASE_MODEL", "gpt-4.1-mini-2025-04-14")
MODE = os.getenv("FINETUNE_MODE", "auto")
EXPLICIT_JOB_ID = os.getenv("FINETUNE_JOB_ID")


def to_plain(obj):
    if hasattr(obj, "model_dump"):
        return obj.model_dump()
    if hasattr(obj, "to_dict"):
        return obj.to_dict()
    raise TypeError(f"Unsupported object type for serialization: {type(obj)!r}")


def load_job_state() -> dict:
    if not JOB_PATH.exists():
        return {}
    with JOB_PATH.open("r", encoding="utf-8") as f:
        return json.load(f)


def save_job_state(state: dict) -> None:
    JOB_PATH.parent.mkdir(parents=True, exist_ok=True)
    state["saved_at"] = datetime.now(timezone.utc).isoformat()
    with JOB_PATH.open("w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False, indent=2)


def upload_file(path: Path) -> dict:
    with path.open("rb") as f:
        file_obj = client.files.create(file=f, purpose="fine-tune")
    return to_plain(file_obj)


def create_job(training_file_id: str, validation_file_id: str) -> dict:
    job = client.fine_tuning.jobs.create(
        model=BASE_MODEL,
        training_file=training_file_id,
        validation_file=validation_file_id,
        method={"type": "supervised"},
        metadata={
            "project": "human-ls",
            "experiment": "v1_8_paraphrase_augmentation",
            "base_prompt": "v1",
        },
        seed=20260515,
    )
    return to_plain(job)


def retrieve_job(job_id: str) -> dict:
    job = client.fine_tuning.jobs.retrieve(job_id)
    return to_plain(job)


def main() -> None:
    state = load_job_state()
    state.setdefault("base_model", BASE_MODEL)
    state.setdefault("train_jsonl_path", str(TRAIN_JSONL_PATH))
    state.setdefault("valid_jsonl_path", str(VALID_JSONL_PATH))
    state.setdefault("job_mode", MODE)

    if MODE not in {"auto", "create", "status"}:
        raise ValueError(f"Unsupported FINETUNE_MODE={MODE!r}. Use auto, create, or status.")

    if MODE == "status":
        job_id = EXPLICIT_JOB_ID or state.get("fine_tuning_job", {}).get("id")
        if not job_id:
            raise ValueError("No fine-tuning job id available for status mode.")
        state["fine_tuning_job"] = retrieve_job(job_id)
        state["fine_tuned_model"] = state["fine_tuning_job"].get("fine_tuned_model")
        save_job_state(state)
        print(f"[ok] updated fine-tuning job status: {JOB_PATH}")
        print(json.dumps(state["fine_tuning_job"], ensure_ascii=False, indent=2))
        return

    if MODE == "auto" and state.get("fine_tuned_model"):
        print(f"[ok] fine-tuned model already available: {state['fine_tuned_model']}")
        print(f"[ok] job metadata file unchanged: {JOB_PATH}")
        return

    if MODE == "auto" and state.get("fine_tuning_job", {}).get("id"):
        state["fine_tuning_job"] = retrieve_job(state["fine_tuning_job"]["id"])
        state["fine_tuned_model"] = state["fine_tuning_job"].get("fine_tuned_model")
        save_job_state(state)
        print(f"[ok] refreshed existing fine-tuning job: {JOB_PATH}")
        print(json.dumps(state["fine_tuning_job"], ensure_ascii=False, indent=2))
        return

    if not TRAIN_JSONL_PATH.exists():
        raise FileNotFoundError(f"Missing training jsonl: {TRAIN_JSONL_PATH}")
    if not VALID_JSONL_PATH.exists():
        raise FileNotFoundError(f"Missing validation jsonl: {VALID_JSONL_PATH}")

    state["training_file"] = upload_file(TRAIN_JSONL_PATH)
    state["validation_file"] = upload_file(VALID_JSONL_PATH)
    state["fine_tuning_job"] = create_job(state["training_file"]["id"], state["validation_file"]["id"])
    state["fine_tuned_model"] = state["fine_tuning_job"].get("fine_tuned_model")
    save_job_state(state)

    print(f"[ok] created fine-tuning job: {JOB_PATH}")
    print(json.dumps(state["fine_tuning_job"], ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
