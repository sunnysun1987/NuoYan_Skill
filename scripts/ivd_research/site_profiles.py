from pathlib import Path
from typing import Any

from .jsonl import append_jsonl
from .status import now_iso


SITE_PROFILES: dict[str, dict[str, Any]] = {
    "cmde_regulatory": {
        "scenario_id": "cmde_regulatory",
        "entry_url": "https://www.cmde.org.cn/",
        "collection_modes": ["http", "codex_chrome", "playwright_persistent", "manual_upload"],
        "observed_access": {
            "status": "permission_required",
            "observed_on": "2026-06-08",
            "evidence_zh": "入口页 HTTP 返回 202 和安全脚本，Browser 中为近空白 DOM；不得绕过验证。",
        },
        "chrome_workflow": {
            "purpose_zh": "用于观察 CMDE 站内搜索、栏目入口、附件下载和访问限制。",
            "steps_zh": [
                "在用户 Chrome 中打开入口页或搜索结果页。",
                "如果需要登录、验证码或机构权限，不绕过，记录为受限。",
                "观察搜索框、结果列表、详情页和附件链接。",
                "把稳定入口、字段和失败原因写入 record-site-observation。",
            ],
        },
    },
    "nmpa_competitor": {
        "scenario_id": "nmpa_competitor",
        "entry_url": "https://www.nmpa.gov.cn/datasearch/home-index.html#category=ylqx",
        "collection_modes": ["codex_chrome", "playwright_persistent", "http", "manual_upload"],
        "observed_access": {
            "status": "collection_failed",
            "observed_on": "2026-06-08",
            "evidence_zh": "数据查询页在 Browser 中加载后为近空白 DOM，无法稳定观察公开搜索表单。",
        },
        "chrome_workflow": {
            "purpose_zh": "用于利用用户 Chrome 的真实页面状态观察 NMPA 数据查询页面、筛选项和结果字段。",
            "steps_zh": [
                "打开医疗器械数据查询页。",
                "观察是否出现 412、验证码、动态加载或搜索表单。",
                "只提交查询类表单，不提交修改、登录或敏感操作。",
                "记录搜索字段、结果列、详情页字段和访问限制。",
            ],
        },
    },
    "standards_current": {
        "scenario_id": "standards_current",
        "entry_url": "https://std.samr.gov.cn/",
        "collection_modes": ["http", "codex_chrome", "playwright_persistent", "manual_upload"],
        "observed_access": {
            "status": "public_search",
            "observed_on": "2026-06-08",
            "search_url_template": "https://std.samr.gov.cn/search/std?q={query}",
            "evidence_zh": "首页标准检索输入框 rid=std，提交后进入国家标准检索页，结果页含标准类型、性质、状态、行业分类和 ICS 筛选。",
        },
        "chrome_workflow": {
            "purpose_zh": "用于观察全国标准信息公共服务平台的检索框、国家标准目录查询入口和详情页字段。",
            "steps_zh": [
                "打开首页并定位标准检索或国家标准目录查询入口。",
                "输入关键词后观察结果列表、分页和详情链接。",
                "确认标准号、标准名称、状态、发布日期等字段。",
                "记录稳定 URL、表单字段、选择器和异常页面特征。",
            ],
        },
    },
    "patenthub_patents": {
        "scenario_id": "patenthub_patents",
        "entry_url": "https://www.patenthub.cn/",
        "collection_modes": ["playwright_persistent", "codex_chrome", "http", "manual_upload"],
        "observed_access": {
            "status": "needs_login",
            "observed_on": "2026-06-08",
            "search_url_template": "https://www.patenthub.cn/s?ds=cn&q={query}",
            "evidence_zh": "首页公开，提交搜索后跳转用户登录页，URL 包含 reason=blocked。",
        },
        "chrome_workflow": {
            "purpose_zh": "用于观察专利检索输入、结果列表、详情页和登录/访问限制。",
            "steps_zh": ["打开检索页。", "输入关键词。", "记录结果字段。", "遇到登录限制则停止并记录。"],
        },
    },
    "yiigle_zhjyyxzz": {
        "scenario_id": "yiigle_zhjyyxzz",
        "entry_url": "https://zhjyyxzz.yiigle.com/",
        "collection_modes": ["http", "playwright_persistent", "codex_chrome", "manual_upload"],
        "observed_access": {
            "status": "public_search",
            "observed_on": "2026-06-08",
            "search_url_template": "https://zhjyyxzz.yiigle.com/search.jspx?q={query}",
            "detail_url_pattern": "https://rs.yiigle.com/cmaid/{id}",
            "evidence_zh": "HTTP 搜索页可返回结果，详情页 meta 中包含题名、作者、日期、摘要、关键词、DOI 等字段。",
        },
        "chrome_workflow": {
            "purpose_zh": "用于观察中华检验医学杂志检索、文章详情和摘要/全文限制。",
            "steps_zh": ["打开期刊页。", "使用站内检索。", "记录标题、作者、日期、DOI、摘要和全文限制。"],
        },
    },
    "yiigle_zhsjkzz": {
        "scenario_id": "yiigle_zhsjkzz",
        "entry_url": "https://zhsjkzz.yiigle.com/",
        "collection_modes": ["http", "playwright_persistent", "codex_chrome", "manual_upload"],
        "observed_access": {
            "status": "public_search_trial_fulltext",
            "observed_on": "2026-06-08",
            "search_url_template": "https://zhsjkzz.yiigle.com/search.jspx?q={query}",
            "detail_url_pattern": "https://rs.yiigle.com/cmaid/{id}",
            "evidence_zh": "搜索页可返回结果和 cmaid 详情链接；详情页可提取摘要、关键词、DOI 和试读正文，全文末尾可能提示登录或订阅。",
        },
        "chrome_workflow": {
            "purpose_zh": "用于观察中华神经科杂志检索、文章详情和摘要/全文限制。",
            "steps_zh": ["打开期刊页。", "使用站内检索。", "记录标题、作者、日期、DOI、摘要和全文限制。"],
        },
    },
    "cma_lab_management": {
        "scenario_id": "cma_lab_management",
        "entry_url": "https://zhlcsysgldzzz.cma-cmc.com.cn/CN/2095-5820/home.shtml",
        "collection_modes": ["http", "playwright_persistent", "codex_chrome", "manual_upload"],
        "observed_access": {
            "status": "public_post_search",
            "observed_on": "2026-06-08",
            "search_url": "https://zhlcsysgldzzz.cma-cmc.com.cn/CN/searchresult",
            "evidence_zh": "高级检索页表单 search-form POST 到 /CN/searchresult，核心字段为 searchSQL。",
        },
        "chrome_workflow": {
            "purpose_zh": "用于观察中华临床实验室管理电子杂志的检索和文章字段。",
            "steps_zh": ["打开期刊页。", "观察检索入口。", "记录文章列表、摘要、DOI 和全文限制。"],
        },
    },
    "wiley_alz": {
        "scenario_id": "wiley_alz",
        "entry_url": "https://alz-journals.onlinelibrary.wiley.com/",
        "collection_modes": ["playwright_persistent", "codex_chrome", "http", "manual_upload"],
        "observed_access": {
            "status": "permission_required",
            "observed_on": "2026-06-08",
            "evidence_zh": "Browser 打开后出现 Cloudflare 安全验证，不自动绕过。",
        },
        "chrome_workflow": {
            "purpose_zh": "用于观察 Wiley 页面、Cloudflare/登录限制、搜索结果和 DOI 字段。",
            "steps_zh": ["打开 Wiley 期刊页。", "观察是否出现 Cloudflare 或机构登录。", "若受限则记录，不绕过。"],
        },
    },
    "yiigle_fulltext": {
        "scenario_id": "yiigle_fulltext",
        "entry_url": "https://www.yiigle.com/searchMobile?ind=3",
        "collection_modes": ["playwright_persistent", "codex_chrome", "http", "manual_upload"],
        "observed_access": {
            "status": "collection_failed",
            "observed_on": "2026-06-08",
            "evidence_zh": "Browser 中标题可见但 DOM 为空；后续需通过具体期刊站或用户合法上传材料补充。",
        },
        "chrome_workflow": {
            "purpose_zh": "用于观察中华医学期刊全文数据库的检索字段、登录态和全文权限。",
            "steps_zh": ["打开全文数据库检索页。", "观察篇关摘、文献类型和日期字段。", "遇到登录/权限限制时记录并请求用户上传合法材料。"],
        },
    },
}


def site_profile(scenario_id: str) -> dict[str, Any]:
    if scenario_id not in SITE_PROFILES:
        raise KeyError(f"Unknown site profile: {scenario_id}")
    return SITE_PROFILES[scenario_id]


def record_site_observation(
    task_dir: Path,
    scenario_id: str,
    observation: dict[str, Any],
) -> dict[str, Any]:
    site_profile(scenario_id)
    row = {
        "time": now_iso(),
        "scenario_id": scenario_id,
        "observation": observation,
        "source": "codex_chrome_or_browser_observation",
    }
    append_jsonl(task_dir / "logs" / "site_observations.jsonl", row)
    append_jsonl(
        task_dir / "logs" / "events.jsonl",
        {
            "time": row["time"],
            "event": "site_observation_recorded",
            "message_zh": "已记录站点页面观察结果。",
            "scenario_id": scenario_id,
        },
    )
    return {"recorded": True, "scenario_id": scenario_id}
