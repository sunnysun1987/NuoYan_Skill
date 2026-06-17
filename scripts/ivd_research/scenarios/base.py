from datetime import datetime
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

from pydantic import BaseModel, Field

from ivd_research.models import FailureType, Material


def now_iso() -> str:
    return datetime.now(ZoneInfo("Asia/Shanghai")).isoformat(timespec="seconds")


class ScenarioResult(BaseModel):
    status: str
    materials: list[Material] = Field(default_factory=list)
    failure_type: FailureType | None = None
    message_zh: str = ""
    collection_errors: list[dict[str, Any]] = Field(default_factory=list)


class ScenarioAdapter(BaseModel):
    scenario_id: str
    label_zh: str
    material_type: str
    adapter_id: str
    adapter_version: str
    required_confirmations: list[str] = Field(default_factory=list)
    keyword_types: list[str] = Field(default_factory=list)
    default_scope_zh: str = ""
    content_validation_rules: list[str]

    def run(
        self,
        task_id: str,
        task_dir: Path,
        params: dict[str, Any],
    ) -> ScenarioResult:
        return ScenarioResult(
            status="needs_manual_review",
            failure_type=FailureType.NEEDS_MANUAL_REVIEW,
            message_zh=f"{self.label_zh} 尚未配置具体采集器，未生成材料。",
        )
