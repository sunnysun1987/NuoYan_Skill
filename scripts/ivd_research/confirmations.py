from pathlib import Path
from typing import Any

from .jsonl import append_jsonl
from .status import load_task, now_iso, save_task


def update_confirmations(task_dir: Path, values: dict[str, Any]) -> dict:
    if not isinstance(values, dict):
        raise ValueError("--values-json must be a JSON object")

    state = load_task(task_dir)
    for key, value in values.items():
        if key not in state.confirmations:
            raise ValueError(f"Unknown confirmation key: {key}")
        state.confirmations[key] = value
    save_task(state)
    append_jsonl(
        task_dir / "logs" / "events.jsonl",
        {
            "time": now_iso(),
            "event": "confirmations_updated",
            "message_zh": "用户确认项已更新。",
            "values": values,
        },
    )
    return state.model_dump(mode="json")
