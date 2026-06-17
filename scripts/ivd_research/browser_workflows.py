from typing import Any
from urllib.parse import quote

from .models import FailureType


BROWSER_WORKFLOWS: dict[str, dict[str, Any]] = {
    "cmde_regulatory": {
        "scenario_id": "cmde_regulatory",
        "entry_url": "https://www.cmde.org.cn/",
        "requires_persistent_session": False,
        "requires_user_login": False,
        "search_url_template": "https://www.cmde.org.cn/search/?keywords={query}",
        "search_types_zh": ["审评报告", "指导原则文本库", "征求意见"],
        "blocking_ui_zh": ["普通 HTTP 可能返回 202 安全脚本；浏览器渲染页面可访问"],
        "result_strategy_zh": "使用站内搜索结果页，逐页采集标题前缀为【审评报告】、【指导原则文本库】、【征求意见】的条目；不得用同类 IVD 指导原则冒充命中结果。",
        "download_strategy_zh": "详情页存在 doc/docx/pdf 附件时下载原文；docx 尽量抽取全文。",
    },
    "patenthub_patents": {
        "scenario_id": "patenthub_patents",
        "entry_url": "https://www.patenthub.cn/",
        "requires_persistent_session": True,
        "requires_user_login": True,
        "search_url_template": "https://www.patenthub.cn/s?ds=all&q={query}",
        "search_types_zh": ["全球专利检索"],
        "blocking_ui_zh": [
            "PatentHub 可能跳转登录页；需要用户在可见浏览器中完成登录。",
            "关注微信公众号弹窗可点击右上角 X 或“稍后关注”关闭。",
        ],
        "result_strategy_zh": "进入搜索结果页后只采集 /patent/<公开号>.html 专利详情页，排除 PDF/claim/description 等功能链接；保存可见基本信息和摘要全文。",
        "download_strategy_zh": "PDF 全文下载可能需要 VIP/权限；不能下载时记录页面可见信息、限制原因和本地 extracted_text 路径。",
        "login_guidance_zh": (
            "当状态为 needs_login 时，agent 应先执行 open-browser-session --scenario patenthub_patents "
            "--background 打开持久化浏览器，引导用户手动登录 PatentHub。用户完成登录/验证后通知 agent 继续，"
            "agent 再重新运行 PatentHub 采集。"
        ),
    },
    "wiley_alz": {
        "scenario_id": "wiley_alz",
        "entry_url": "https://alz-journals.onlinelibrary.wiley.com/",
        "requires_persistent_session": True,
        "requires_user_login": False,
        "search_url_template": "https://alz-journals.onlinelibrary.wiley.com/action/doSearch?AllField={query}",
        "search_types_zh": ["站内全文检索"],
        "blocking_ui_zh": ["Cloudflare 真人验证", "机构登录或付费访问提示"],
        "result_strategy_zh": "多页文献结果，优先识别 Free Access/Open Access 条目，进入详情提取标题、作者、日期、DOI、摘要。",
        "download_strategy_zh": "可开放访问时使用 /doi/pdfdirect/<doi>?download=true 下载 PDF；受限时记录摘要和限制。",
    },
    "nmpa_competitor": {
        "scenario_id": "nmpa_competitor",
        "entry_url": "https://www.nmpa.gov.cn/datasearch/home-index.html#category=ylqx",
        "requires_persistent_session": True,
        "requires_user_login": False,
        "search_url_template": "",
        "search_types_zh": ["境内医疗器械（注册）", "进口医疗器械（注册）"],
        "blocking_ui_zh": ["安全脚本导致空白 DOM", "动态页面加载失败"],
        "result_strategy_zh": "选择指定注册类型，输入关键词搜索，多页穷尽详情，按用户确认的方法学过滤。",
        "download_strategy_zh": "无文件下载，采集详情页完整注册信息。",
    },
}


def browser_workflow(scenario_id: str) -> dict[str, Any]:
    try:
        return BROWSER_WORKFLOWS[scenario_id]
    except KeyError as exc:
        raise KeyError(f"Unknown browser workflow: {scenario_id}") from exc


def search_url_for_workflow(workflow: dict[str, Any], query: str) -> str:
    template = workflow.get("search_url_template", "")
    if not template:
        return workflow["entry_url"]
    return template.format(query=quote(query))


def classify_browser_page(
    scenario_id: str,
    url: str,
    title: str,
    text: str,
) -> dict[str, str]:
    normalized = f"{url} {title} {text}".lower()
    if (
        "cloudflare" in normalized
        or "安全验证" in normalized
        or "cf-turnstile" in normalized
        or "__cf_chl" in normalized
    ):
        return {
            "status": FailureType.PERMISSION_REQUIRED.value,
            "reason_zh": "页面出现 Cloudflare 或真人验证，需要用户在可见浏览器中手动完成。",
        }
    if scenario_id == "patenthub_patents" and (
        "reason=blocked" in normalized
        or "/user/login" in normalized
        or ("用户登录" in text and "密码" in text)
    ):
        return {
            "status": FailureType.NEEDS_LOGIN.value,
            "reason_zh": BROWSER_WORKFLOWS["patenthub_patents"]["login_guidance_zh"],
        }
    if (
        "access denied" in normalized
        or "permission denied" in normalized
        or "institutional login" in normalized
        or "subscription access" in normalized
        or "requires institutional" in normalized
        or "机构登录" in normalized
        or "订阅" in normalized
        or "权限" in normalized
        or "付费" in normalized
    ):
        return {
            "status": FailureType.PERMISSION_REQUIRED.value,
            "reason_zh": "页面要求机构权限、订阅或付费访问，只能记录可见信息和受限原因。",
        }
    if "reason=blocked" in normalized or ("用户登录" in text and "密码" in text):
        return {
            "status": FailureType.NEEDS_LOGIN.value,
            "reason_zh": "页面要求登录，需要用户在持久化浏览器会话中手动登录。",
        }
    if not text.strip():
        return {
            "status": FailureType.COLLECTION_FAILED.value,
            "reason_zh": "页面正文为空，可能是动态加载失败或安全脚本阻挡。",
        }
    if scenario_id == "patenthub_patents" and "/s?" in url:
        return {"status": "search_results", "reason_zh": "已进入 PatentHub 搜索结果页。"}
    if scenario_id == "wiley_alz" and "action/dosearch" in url.lower():
        return {"status": "search_results", "reason_zh": "已进入 Wiley 搜索结果页。"}
    return {"status": "page_ready", "reason_zh": "页面可读，等待场景 workflow 继续处理。"}


def page_probe_result(
    *,
    scenario_id: str,
    query: str,
    final_url: str,
    title: str,
    text: str,
) -> dict[str, Any]:
    workflow = browser_workflow(scenario_id)
    classification = classify_browser_page(scenario_id, final_url, title, text)
    return {
        "scenario_id": scenario_id,
        "target_url": search_url_for_workflow(workflow, query) if query else workflow["entry_url"],
        "final_url": final_url,
        "title": title,
        "text_length": len(text),
        **classification,
    }
