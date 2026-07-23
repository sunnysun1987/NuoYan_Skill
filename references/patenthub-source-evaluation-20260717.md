# PatentHub 专利汇信源升级评估（2026-07-17）

## 结论

PatentHub 适合作为诺研专利信源补强，但应按两级能力接入：

1. 优先级一：合法 API TOKEN 模式。适合稳定采集搜索结果、专利详情、权利要求、说明书、法律状态、引用、相似专利、PDF 地址、同族和统计分析。
2. 优先级二：登录态浏览器 workflow。适合没有 API TOKEN 但用户已合法登录网页时，采集可见结果和详情页信息。

未登录匿名网页采集不应作为正式采集路径。2026-07-17 实测显示，首页可访问，搜索页、精确专利号检索、专利详情页均返回用户登录页。

## 已验证页面与接口

- 首页：https://www.patenthub.cn/
- OpenSearch：https://www.patenthub.cn/opensearch.xml
- 检索帮助：https://www.patenthub.cn/help/index.html
- API 文档：https://www.patenthub.cn/api/interface.html
- 中国检索测试：https://www.patenthub.cn/s?ds=cn&q=甲型流感%20抗原检测
- 全球检索测试：https://www.patenthub.cn/s?ds=all&q=NT-proBNP%20immunoassay
- 精确专利号检索测试：https://www.patenthub.cn/s?ds=cn&q=CN111344253A
- 详情页测试：https://www.patenthub.cn/patent/CN111344253A.html
- API 无 token 测试：https://www.patenthub.cn/api/s?ds=cn&t=&q=石墨烯&v=1

## 站点能力

### 网页检索

首页检索表单使用：

- `action="/s"`
- `q`：检索式
- `ds`：数据范围

首页数据范围包括：

- `cn`：中国
- `all`：全球
- `us`：美国
- `jp`：日本
- `ep`：欧盟
- `kr`：韩国
- `wo`：WIPO
- `tw`：台湾省

公开帮助页显示支持：

- 直接输入申请号、公开号或授权号；号码前可不加 `ZL` 或 `CN`。
- 多专利号可使用 `OR`。
- 默认空格近似 `AND`。
- 可用英文双引号关闭自动分词。
- 支持 `AND`、`OR`、`NOT` 和括号。
- 支持时间范围：`applicationDate:[2014 TO 2015]`、`applicationYear:[2010 TO 2012]`。
- 支持字段限定：`applicant:"清华大学"`、`mainIpc3:"C01B"`、`legalStatus:"有效专利"` 等。

### 关键检索字段

可用于诺研分层检索的字段包括：

- 专利号：`number` / `n`
- 申请号：`applicationNumber` / `an`
- 文献号：`documentNumber` / `dn`
- 申请日/年：`applicationDate` / `ad`，`applicationYear` / `ay`
- 公开日/年：`documentDate` / `dd`，`documentYear`
- IPC：`ipc`、`ipc1`、`ipc2`、`ipc3`、`ipc4`、`ipc5`
- 主 IPC：`mainIpc`、`mainIpc1`、`mainIpc2`、`mainIpc3`、`mainIpc4`、`mainIpc5`
- 申请人：`applicant`
- 第一申请人：`firstApplicant`
- 专利权人：`assignee`
- 发明人：`inventor` / `inv`
- 标题：`title` / `ti` / `t`
- 摘要：`summary` / `ab` / `s`
- 权利要求：`claims` / `cl` / `c`
- 说明书：`description` / `desc` / `d`
- 复合字段：`ta` / `ts`、`tac` / `tsc`、`tacd` / `tscd`
- 法律状态：`legalStatus` / `ls`
- 国家/省市：`countryCode` / `cc`、`country`、`province`、`city`

## API 能力

API 文档公开可读，但正式调用需要 TOKEN。无 token 实测返回：

```json
{"code":201,"success":false}
```

错误码文档说明 `201` 为 `token为空`，`202` 为非法 token，`208` 为没有访问权限，`207` 为当天访问次数用尽，`211` 为年度专利总数量用尽。

可用于诺研的主要接口：

- `/api/s`：搜索接口，支持 `ds`、`t`、`q`、`p`、`ps`、`s`、`hl`、`v`。每页最大 50 条，最多返回前 1000 条；超过 1000 条应按时间、申请人、IPC 或主题拆分检索式。
- `/api/patent/base`：专利基本信息接口。
- `/api/patent/claims`：权利要求接口。
- `/api/patent/desc`：说明书全文接口。
- `/api/patent/tx`：专利法律信息接口。
- `/api/patent/citing`：专利引用数据接口。
- `/api/patent/like`：相似专利接口。
- `/api/pdf`：PDF 全文下载接口。
- `/api/img`：摘要附图接口。
- `/api/patent/drawings`：说明书附图列表。
- `/api/pic`：说明书附图下载。
- `/api/ration`：统计分析接口，支持国家、申请人、发明人、法律状态、申请年、公开年、IPC、专利类型等维度。
- `/api/ls`：法律状态批量查询。
- `/api/patent/detail`：专利详情接口。
- `/api/patent/family`：专利同族接口。

API 文档特别说明：只有通过搜索接口获取到的专利唯一 ID，才能在 `/api/patent/base` 等接口中获取对应数据，且有效时间为 60 分钟；直接访问详情类接口可能返回 `215`。

## 对诺研 skill 的适配建议

### 查询策略

专利检索不应使用完整项目画像长串。建议沿用产品型来源分层：

1. 核心靶标词：如 `NT-proBNP`、`甲型流感`、`Aβ42`。
2. 产品提示词：如 `检测试剂盒`、`免疫检测`、`抗原检测`。
3. 方法学提示：如 `胶体金`、`荧光免疫层析`、`化学发光`、`PCR`。
4. 字段限定组合：`title:`、`summary:`、`claims:`、`applicant:`、`mainIpc:`、`legalStatus:`。
5. 范围限定：`ds=cn` 优先服务中国项目，`ds=all` 用于全球/FTO 初筛。

示例：

- `甲型流感 AND 抗原检测`
- `title:"NT-proBNP" OR summary:"NT-proBNP"`
- `tac:NT-proBNP AND immunoassay`
- `甲型流感 AND 检测试剂盒 AND legalStatus:"有效专利"`
- `applicationYear:[2018 TO 2026] AND 甲型流感 AND 抗原`

### 材料字段映射

建议 Material.raw_fields 至少保留：

- `source_site_id`
- `query`
- `ds`
- `patent_id`
- `document_number`
- `application_number`
- `title`
- `summary`
- `claims`
- `description_status`
- `applicant`
- `assignee`
- `current_assignee`
- `inventor`
- `application_date`
- `document_date`
- `ipc`
- `main_ipc`
- `type`
- `legal_status`
- `current_status`
- `pdf_list`
- `family_id`
- `extended_family_id`
- `api_code`
- `api_error_message`

### 采集状态

建议区分以下状态：

- `api_ready`：配置了合法 TOKEN，API 可采集。
- `needs_api_token`：API 未配置 token 或返回 token 相关错误。
- `needs_login`：网页路径返回用户登录页。
- `permission_required`：需要 VIP、付费、机构权限或接口权限。
- `rate_limited`：当天或年度调用次数用尽。
- `partial_visible_only`：只取得网页可见信息，未取得权利要求、说明书或 PDF。
- `no_results`：仅当同一来源完成多层检索且接口返回 206 或页面明确无结果时使用。

### 护栏

- 未登录搜索页和未登录详情页不得生成专利 Material。
- 详情页标题或正文包含“用户登录”“注册登录后可以查看更多专利信息”时，应直接记录 `needs_login`。
- 解析器不能仅凭 URL 中的公开号生成专利材料；必须同时存在标题、申请人、摘要、法律状态或其他有效详情字段。
- 未取得权利要求、说明书或 PDF 时，报告只能形成“专利线索/FTO 待复核”，不能形成自由实施结论。
- API token 不得写入报告、日志、材料包或长期记忆。
- API 单次最多前 1000 条结果；超量必须拆分检索式，不得无限分页。

## 后续改造清单

1. 新增 `patenthub_api` adapter，优先读取环境变量或本地安全配置中的 token。
2. 保留现有 `patenthub_patents` 浏览器 workflow 作为登录态兜底。
3. 更新 `source_sites`：PatentHub 增加 `api` 优先、`browser_workflow` 兜底、`manual_import` 兜底。
4. 扩展 query plan：为专利场景生成 `ds=cn` 与 `ds=all` 两套分层检索式。
5. 增加登录页防误采集测试。
6. 增加 API 无 token、非法 token、权限不足、次数用尽、无结果的状态映射测试。
7. 报告层将 PatentHub 结果明确区分为“线索”“权利要求已取”“说明书已取”“PDF 已取”“FTO 待人工复核”。

## 2026-07-17 实施进展

- 已加固 PatentHub 登录页识别：搜索页或详情页出现登录提示时返回 `needs_login`，不再根据 URL 中的公开号生成伪材料。
- 已增加详情有效性门槛：有效公开号、非占位标题和至少一个真实专利字段同时满足后才允许生成 Material。
- 已在浏览器采集层记录无效详情和登录失效原因；合法登录后可复用持久化 profile 进行无头采集。
- 已增加自动化测试，覆盖搜索登录页、详情登录页、正常专利详情、无效材料拦截和登录文案分类。
- 尚未完成账号登录后的真实结果页 DOM 与批量翻页验证；需要用户在可见浏览器中完成一次合法登录，并提供首轮检索关键词后继续。
