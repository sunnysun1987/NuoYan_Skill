# 动作清单

| action_id | 中文名称 | CLI |
| --- | --- | --- |
| confirm_task_info | 确认/修改任务信息 | update-confirmations |
| confirm_keyword_pool | 确认/修改关键词池 | update-confirmations |
| confirm_collection_scope | 确认/修改采集范围 | update-confirmations |
| confirm_search_profile | 补全/确认完整检索画像 | update-confirmations |
| run_full_pipeline | 运行完整调研流水线 | run-full-pipeline |
| run_delivery_pipeline | 运行 V2 标准交付流水线 | run-delivery-pipeline |
| run_scenario | 运行指定场景 | run-scenario |
| retry_failed | 按失败场景重试并记录结果 | run-scenario / run-delivery-pipeline |
| fallback_import_finding | 外部公开来源兜底导入 | import-finding |
| import_local | 导入本地材料 | import-local |
| show_status | 查看任务状态 | show-status |
| export_review | 导出 Excel 复核表 | export-review |
| import_review | 导入 Excel 人工修订 | import-review |
| build_materials_report | 生成材料清单 HTML | build-report --type materials |
| build_feasibility_report | 生成可行性报告 HTML | build-report --type feasibility |
| build_standard_delivery | 生成 V2 标准三件套交付 | build-standard-delivery |
| verify_delivery | 验证交付物和业务就绪状态 | verify-package |
| show_manual_review | 查看待人工复核清单 | show-status |
| package_task | 打包任务目录 | package-task |

动作执行前，如果任务范围、关键词、地区、时间范围、专利范围或文献范围尚未确认，应先向用户给出选项确认。

## 动作门禁

- `run_full_pipeline`、`run_delivery_pipeline`、正式 `run_scenario` 执行前，必须完成 `confirm_search_profile`。
- `build_standard_delivery` 前必须已有材料、证据卡、场景状态和标准审阅表；否则只能生成草稿，并在报告首页显示缺口。
- `verify_delivery` 是最终回复前的必要动作；最终回复必须说明 `delivery_artifacts_ready`、`scenario_coverage_ready`、`final_review_ready` 和 `business_ready`。
- `fallback_import_finding` 只能导入可回溯公开来源或用户合法提供材料，不得导入搜索摘要本身作为强证据。
