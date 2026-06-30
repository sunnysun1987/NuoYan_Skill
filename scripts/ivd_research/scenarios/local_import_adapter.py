from .registry import get_scenario
from .base import ScenarioResult
from ivd_research.models import FailureType


def adapter():
    return get_scenario("local_import")


def collect(task_id, task_dir, params):
    return ScenarioResult(
        status=FailureType.NEEDS_MANUAL_REVIEW.value,
        failure_type=FailureType.NEEDS_MANUAL_REVIEW,
        message_zh=(
            "本地材料导入不是自动检索场景。请使用 import-local --path <文件或目录> 导入用户合法提供的材料。"
        ),
    )
