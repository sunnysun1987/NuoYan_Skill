import re
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from .constants import DEFAULT_OUTPUT_ROOT_NAME


def default_output_root() -> Path:
    return Path.home() / "Documents" / DEFAULT_OUTPUT_ROOT_NAME


def safe_topic(topic: str) -> str:
    value = re.sub(r"[\\/:*?\"<>|]+", "-", topic.strip())
    value = re.sub(r"\s+", "-", value)
    return value[:60] or "ivd-task"


def new_task_id(now: datetime | None = None) -> str:
    current = now or datetime.now(ZoneInfo("Asia/Shanghai"))
    return "TASK-" + current.strftime("%Y%m%d%H%M%S%f")


def new_task_dir(output_root: Path, topic: str, now: datetime | None = None) -> Path:
    current = now or datetime.now(ZoneInfo("Asia/Shanghai"))
    base = output_root / f"{current.strftime('%Y%m%d-%H%M')}_{safe_topic(topic)}"
    if not base.exists():
        return base

    index = 2
    while True:
        candidate = output_root / f"{base.name}-{index}"
        if not candidate.exists():
            return candidate
        index += 1
