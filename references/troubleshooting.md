# 排错说明

| failure_type | 用户解释 | 下一步 |
| --- | --- | --- |
| collection_failed | 采集过程失败，可能是网络、DNS、页面结构或网站限制 | 先缩短/改写检索式重试；再尝试公开网页/官方页面检索并用 import-finding 导入；必要时执行浏览器观察并记录；仍失败则进入补证任务 |
| no_results | 查询成功但没有结果 | 调整关键词或时间范围 |
| no_valid_materials | 有结果但不满足材料规则 | 人工确认是否放宽规则 |
| download_failed | 找到材料但下载失败 | 让用户提供合法文件或链接 |
| parse_failed | 文件已取得但解析失败 | 尝试转换格式或人工摘录 |
| permission_required | 需要权限或机构访问 | 不绕过限制，请用户提供合法访问材料 |
| needs_login | 需要登录 | 让用户登录或上传合法取得的文件 |
| needs_ocr | 扫描件需要 OCR | 安装 OCR 或人工摘录 |
| needs_manual_review | 需要人工判断 | 放入 Excel 复核表 |

对外说明必须具体到失败步骤、已完成内容、未完成内容和可继续的最小下一步。

## DNS / 外网访问异常

DNS 异常、`Could not resolve host`、HTTP 429、连接超时都不能直接解释为“无文献”或“无证据”。处理顺序：

1. 先运行 `nuoyan doctor --network --json`，确认是 Python DNS、Python HTTPS、curl 通道还是目标站点限流/拦截。
2. 改写检索式：去掉过长的中文段落、减少限定词，先用英文核心词、靶标、疾病、样本类型检索。
3. 重试官方 API：PubMed/PMC 用 NCBI E-utilities，OpenAlex 用 API；失败原因必须进入 logs。
4. 使用网页兜底：通过公开网页、期刊官网、DOI 页面、PubMed 页面或 PMC 页面获取题录/摘要/全文线索。
5. 用 `import-finding` 导入可追溯来源；不得把搜索结果摘要直接作为强证据。
6. 如仍失败，在报告“缺口与任务”和 Excel 中形成补证任务，写明责任角色、来源、检索式和下一步动作。

缺少上述兜底记录时，`verify-package` 应保持 `fallback_ready=false`，最终 `business_ready=false`。

## Chrome 相关问题

- Chrome 插件不可用：说明当前环境不能读取用户登录态页面，改用公开 HTTP、用户上传文件或稍后重试。
- 页面需要验证码：停止自动化，请用户决定是否人工处理；不要绕过。
- 页面需要登录或机构权限：请求用户在 Chrome 中合法登录，或上传合法取得的材料。
- 页面结构未知：使用 Chrome 观察并记录 `site_observations.jsonl`，再开发稳定 adapter。
- HTTP 200 但页面为空/拦截页：记录为 `collection_failed` 或 `permission_required`，不要当作成功采集。
