from pydantic import BaseModel


class ActionDefinition(BaseModel):
    action_id: str
    label_zh: str
    description_zh: str
    cli_command: str
    requires_confirmation: bool = True


ACTIONS = {
    "confirm_task_info": ActionDefinition(
        action_id="confirm_task_info",
        label_zh="确认/修改任务信息",
        description_zh="确认项目对象、适用场景、目标地区和报告目的。",
        cli_command="update-confirmations",
    ),
    "confirm_keyword_pool": ActionDefinition(
        action_id="confirm_keyword_pool",
        label_zh="确认/修改关键词池",
        description_zh="确认中文、英文、缩写、方法学和疾病相关关键词。",
        cli_command="update-confirmations",
    ),
    "confirm_collection_scope": ActionDefinition(
        action_id="confirm_collection_scope",
        label_zh="确认/修改采集范围",
        description_zh="确认文献时间范围、专利范围、注册地区和场景范围。",
        cli_command="update-confirmations",
    ),
    "run_full_pipeline": ActionDefinition(
        action_id="run_full_pipeline",
        label_zh="运行完整调研流水线",
        description_zh="按已确认条件运行全部采集、整理和报告步骤。",
        cli_command="run-full-pipeline",
    ),
    "run_scenario": ActionDefinition(
        action_id="run_scenario",
        label_zh="运行指定场景",
        description_zh="运行一个或多个指定采集场景。",
        cli_command="run-scenario",
    ),
    "import_local": ActionDefinition(
        action_id="import_local",
        label_zh="导入本地材料",
        description_zh="导入本地 PDF、DOC、DOCX、TXT、HTML 等材料。",
        cli_command="import-local",
    ),
    "show_status": ActionDefinition(
        action_id="show_status",
        label_zh="查看任务状态",
        description_zh="刷新当前任务状态面板。",
        cli_command="show-status",
        requires_confirmation=False,
    ),
    "retry_failed": ActionDefinition(
        action_id="retry_failed",
        label_zh="重试失败项",
        description_zh="重试采集、下载或解析失败项。",
        cli_command="retry-failed",
    ),
    "export_review": ActionDefinition(
        action_id="export_review",
        label_zh="导出 Excel 复核表",
        description_zh="导出给研发人员复核的 Excel 工作簿。",
        cli_command="export-review",
    ),
    "import_review": ActionDefinition(
        action_id="import_review",
        label_zh="导入 Excel 人工修订",
        description_zh="导入人工修改后的复核表。",
        cli_command="import-review",
    ),
    "build_materials_report": ActionDefinition(
        action_id="build_materials_report",
        label_zh="生成材料清单 HTML",
        description_zh="生成离线材料清单报告。",
        cli_command="build-report",
    ),
    "build_feasibility_report": ActionDefinition(
        action_id="build_feasibility_report",
        label_zh="生成可行性报告 HTML",
        description_zh="生成项目可行性报告初稿。",
        cli_command="build-report",
    ),
    "show_manual_review": ActionDefinition(
        action_id="show_manual_review",
        label_zh="查看待人工复核清单",
        description_zh="查看需要用户处理或确认的事项。",
        cli_command="show-status",
    ),
    "package_task": ActionDefinition(
        action_id="package_task",
        label_zh="打包任务目录",
        description_zh="将任务目录压缩为 zip。",
        cli_command="package-task",
    ),
}


def resolve_action(text: str) -> list[str]:
    normalized = text.lower().replace(" ", "")
    if "excel" in normalized or "复核表" in normalized or "审阅表" in normalized:
        return ["export_review"]
    if "导入" in normalized and ("本地" in normalized or "材料" in normalized):
        return ["import_local"]
    has_run_intent = any(
        word in normalized
        for word in ["跑", "运行", "执行", "采集", "查询", "检索", "开始"]
    )
    if has_run_intent and (
        "标准" in normalized or "竞品" in normalized or "场景" in normalized
    ):
        return ["run_scenario"]
    if "报告" in normalized and "可行" in normalized:
        return ["build_feasibility_report"]
    if "材料" in normalized and "清单" in normalized:
        return ["build_materials_report"]
    return []
