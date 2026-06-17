import importlib.util
import socket
import subprocess
import sys
import uuid
from pathlib import Path
from urllib.error import URLError
from urllib.request import Request, urlopen


def module_available(name: str) -> bool:
    return importlib.util.find_spec(name) is not None


def dependency_check(
    check_id: str,
    label_zh: str,
    module_name: str,
    impact_zh: str,
    required: bool,
) -> dict:
    return {
        "id": check_id,
        "label_zh": label_zh,
        "ok": module_available(module_name),
        "required": required,
        "impact_zh": impact_zh,
    }


NETWORK_PROBES = [
    {
        "id": "ncbi_eutils",
        "label_zh": "NCBI E-utilities / PubMed",
        "host": "eutils.ncbi.nlm.nih.gov",
        "url": "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/einfo.fcgi?db=pubmed",
    },
    {
        "id": "openalex",
        "label_zh": "OpenAlex",
        "host": "api.openalex.org",
        "url": "https://api.openalex.org/works?search=Alzheimer&per-page=1",
    },
]


def run_network_doctor(timeout: int = 10) -> dict:
    probes = [_network_probe(probe, timeout=timeout) for probe in NETWORK_PROBES]
    return {
        "ok": all(probe["python_https_ok"] or probe["curl_https_ok"] for probe in probes),
        "message_zh": (
            "网络体检用于区分 Python DNS、Python HTTPS 与系统 curl 通道。"
            "若 Python DNS 失败但 curl 成功，正式采集应使用 curl/浏览器/人工导入兜底，"
            "并在交付验证中保留该网络状态。"
        ),
        "probes": probes,
    }


def _network_probe(probe: dict, *, timeout: int) -> dict:
    host = probe["host"]
    url = probe["url"]
    result = {
        "id": probe["id"],
        "label_zh": probe["label_zh"],
        "host": host,
        "url": url,
        "python_dns_ok": False,
        "python_dns_error": "",
        "python_https_ok": False,
        "python_https_status": None,
        "python_https_error": "",
        "curl_https_ok": False,
        "curl_https_error": "",
    }
    try:
        result["python_dns_address"] = socket.getaddrinfo(host, 443)[0][4][0]
        result["python_dns_ok"] = True
    except OSError as exc:
        result["python_dns_error"] = f"{type(exc).__name__}: {exc}"

    try:
        request = Request(url, headers={"User-Agent": "NuoYan-Skill/2.0 network doctor"})
        with urlopen(request, timeout=timeout) as response:
            result["python_https_status"] = response.status
            result["python_https_ok"] = 200 <= response.status < 400
    except (OSError, URLError) as exc:
        result["python_https_error"] = f"{type(exc).__name__}: {exc}"

    try:
        completed = subprocess.run(
            [
                "curl",
                "-fsSL",
                "--max-time",
                str(timeout),
                "-A",
                "NuoYan-Skill/2.0 network doctor",
                url,
            ],
            check=False,
            capture_output=True,
            text=True,
            timeout=timeout + 5,
        )
        result["curl_https_ok"] = completed.returncode == 0
        if completed.returncode != 0:
            result["curl_https_error"] = (
                completed.stderr or completed.stdout or f"curl exit {completed.returncode}"
            ).strip()[:500]
        else:
            result["curl_response_preview"] = completed.stdout[:200]
    except (OSError, subprocess.SubprocessError) as exc:
        result["curl_https_error"] = f"{type(exc).__name__}: {exc}"
    return result


def run_doctor(output_root: Path, *, include_network: bool = False) -> dict:
    checks = [
        {
            "id": "python",
            "label_zh": "Python 版本",
            "ok": sys.version_info >= (3, 11),
            "required": True,
            "impact_zh": "Python 低于 3.11 会导致 CLI 不受支持。",
        },
        dependency_check(
            "typer",
            "CLI 框架",
            "typer",
            "缺少 Typer 会导致 ivd-research 命令无法运行。",
            True,
        ),
        dependency_check(
            "pydantic",
            "Schema 校验",
            "pydantic",
            "缺少 Pydantic 会导致材料和证据卡无法校验。",
            True,
        ),
        dependency_check(
            "openpyxl",
            "Excel 读写",
            "openpyxl",
            "缺少 openpyxl 会导致 Excel 复核表无法导出或导入。",
            True,
        ),
        dependency_check(
            "jinja2",
            "HTML 渲染",
            "jinja2",
            "缺少 Jinja2 会导致 HTML 报告无法生成。",
            True,
        ),
        dependency_check(
            "httpx",
            "HTTP 采集",
            "httpx",
            "缺少 httpx 会导致网页和文件下载能力不可用。",
            True,
        ),
        dependency_check(
            "beautifulsoup4",
            "HTML 解析",
            "bs4",
            "缺少 BeautifulSoup 会影响网页内容解析。",
            False,
        ),
        dependency_check(
            "playwright",
            "浏览器采集能力",
            "playwright",
            "缺少 Playwright 会影响需要 JavaScript 或登录态的网站采集，但不影响本地导入。",
            False,
        ),
        dependency_check(
            "pypdf",
            "PDF 文本提取",
            "pypdf",
            "缺少 PDF 解析依赖会导致部分文献全文无法自动提取，但不影响材料登记。",
            False,
        ),
        dependency_check(
            "ocr",
            "可选 OCR",
            "pytesseract",
            "缺少 OCR 仅影响扫描件全文识别，材料会标记为需要 OCR。",
            False,
        ),
    ]

    try:
        output_root.mkdir(parents=True, exist_ok=True)
        probe = output_root / f".ivd-research-write-test-{uuid.uuid4().hex}"
        probe.write_text("ok", encoding="utf-8")
        writable = True
        impact_zh = "输出目录可写。"
    except OSError as exc:
        writable = False
        impact_zh = f"输出目录不可写，会导致任务无法创建：{exc}"
    finally:
        if "probe" in locals():
            probe.unlink(missing_ok=True)

    checks.append(
        {
            "id": "output_root",
            "label_zh": "输出目录权限",
            "ok": writable,
            "required": True,
            "impact_zh": impact_zh,
        }
    )

    required_ok = all(item["ok"] for item in checks if item["required"])
    result = {
        "ok": required_ok,
        "output_root": str(output_root),
        "checks": checks,
    }
    if include_network:
        network = run_network_doctor(timeout=8)
        result["network"] = network
        result["ok"] = required_ok and network["ok"]
    return result
