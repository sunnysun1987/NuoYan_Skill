from dataclasses import dataclass, field
from datetime import date
from typing import Any


METHOD_QUERY_TERMS = [
    "核酸检测试剂盒",
    "核酸检测试剂",
    "核酸检测",
    "核酸扩增",
    "检测试剂盒",
    "检测试剂",
    "PCR",
    "pcr",
    "检测",
    "试剂盒",
    "试剂",
]

# Domain stop words that do not belong in a search query.
# These are typically appended to research topic titles but would
# pollute search results on scientific and regulatory websites.
RESEARCH_STOP_WORDS = [
    "可行性调研",
    "可行性分析",
    "可行性研究",
    "立项调研",
    "立项分析",
    "项目可行性",
    "调研报告",
    "技术可行性",
    "研发立项",
    "项目调研",
    "研究报告",
    "市场调研",
]

DEFAULT_LITERATURE_TYPES = ["指南", "综述", "Meta分析", "原创论文", "病例报告"]

CN_TO_EN_KEYWORDS = {
    "肺炎支原体": "Mycoplasma pneumoniae",
    "支原体肺炎": "Mycoplasma pneumoniae pneumonia",
}


@dataclass(frozen=True)
class ScenarioQueryPlan:
    query: str
    params: dict[str, Any] = field(default_factory=dict)


def _confirmation(state: Any, key: str, default: Any = "") -> Any:
    confirmations = getattr(state, "confirmations", {}) or {}
    value = confirmations.get(key, default)
    if value is False or value is None:
        return default
    return value


def _primary_query(state: Any) -> str:
    primary = str(_confirmation(state, "primary_query", "") or "").strip()
    if primary:
        return primary
    return str(getattr(state, "topic", "") or "").strip()


def broaden_chinese_query(query: str) -> str:
    broad = str(query or "").strip()
    # Remove methodology terms (too specific, may miss results)
    for term in METHOD_QUERY_TERMS:
        broad = broad.replace(term, " ")
    # Remove research domain stop words (not searchable content)
    for term in RESEARCH_STOP_WORDS:
        broad = broad.replace(term, " ")
    return " ".join(broad.split())


def _broad_query(state: Any) -> str:
    primary = _primary_query(state)
    return broaden_chinese_query(primary) or primary


def _english_query(state: Any) -> str:
    english = str(_confirmation(state, "english_keywords", "") or "").strip()
    if english:
        return english
    broad = _broad_query(state)
    for cn, en in CN_TO_EN_KEYWORDS.items():
        if cn in broad:
            return en
    return broad


def _append_terms(base: str, *values: Any) -> str:
    terms = [str(base or "").strip()]
    for value in values:
        if isinstance(value, list):
            text = " ".join(str(item).strip() for item in value if str(item).strip())
        else:
            text = str(value or "").strip()
        if text:
            terms.append(text)
    seen: list[str] = []
    for term in terms:
        if term and term not in seen:
            seen.append(term)
    return " ".join(seen)


def _cn_business_query(state: Any) -> str:
    return _append_terms(
        _broad_query(state),
        _confirmation(state, "sample_type", ""),
        _confirmation(state, "platform", ""),
        _confirmation(state, "methodology", ""),
        _confirmation(state, "intended_use", ""),
        _confirmation(state, "chinese_synonyms", ""),
    )


def _en_business_query(state: Any) -> str:
    sample_type = str(_confirmation(state, "sample_type", "") or "").strip()
    intended_use = str(_confirmation(state, "intended_use", "") or "").strip()
    english_terms = [
        _english_query(state),
        sample_type if sample_type.isascii() else "",
        _confirmation(state, "english_method_keywords", ""),
        intended_use if intended_use.isascii() else "",
    ]
    return _append_terms(
        *english_terms,
    )


def _english_primary_query(state: Any) -> str:
    return _english_query(state)


def _literature_date_range(state: Any) -> Any:
    return _confirmation(state, "literature_date_range", "")


def _literature_retmax(state: Any) -> int | str:
    value = _confirmation(state, "literature_retmax", 100)
    if isinstance(value, str) and value.strip().lower() in {"all", "全部", "full", "unlimited"}:
        return "all"
    try:
        parsed = int(value)
        return min(max(parsed, 10), 200)
    except (TypeError, ValueError):
        return 100


def _date_range_bounds(
    date_range: Any,
    *,
    today: date | None = None,
) -> tuple[str, str]:
    if isinstance(date_range, dict):
        start = str(date_range.get("start") or "").strip()
        end = str(date_range.get("end") or "").strip()
        if start and end:
            return start, end
    if isinstance(date_range, str) and date_range.strip():
        raw = date_range.strip()
        for separator in ["TO", "至", "~", "到", ","]:
            if separator in raw:
                left, right = raw.split(separator, 1)
                start = left.strip(" []")
                end = right.strip(" []")
                if start and end:
                    return start, end
    current = today or date.today()
    try:
        years = int(date_range) if isinstance(date_range, (int, float)) else 0
    except (TypeError, ValueError):
        years = 0
    if not years:
        years = 5
    try:
        start = current.replace(year=current.year - years)
    except ValueError:
        start = current.replace(year=current.year - years, day=28)
    return start.isoformat(), current.isoformat()


def build_yiigle_fulltext_expression(
    *,
    keyword: str,
    date_range: Any,
    today: date | None = None,
) -> str:
    start, end = _date_range_bounds(date_range, today=today)
    type_clause = " OR ".join(
        f"文献类型=({literature_type})"
        for literature_type in DEFAULT_LITERATURE_TYPES
    )
    return (
        f"篇关摘=({keyword}) AND ({type_clause}) "
        f"AND 出版日期=[{start} TO {end}]"
    )


def _short_query(query: str, max_terms: int = 3) -> str:
    """Extract the first few core Chinese terms from a long query.

    Academic journal search engines perform poorly with long mixed-language
    queries.  This picks the leading Chinese-only (or ASCII) words, skipping
    numbers, unit annotations like (cTnI), and English abbreviations.
    """
    import re as _re

    # Split on whitespace or common separators
    parts = _re.split(r"[\s]+", str(query or "").strip())
    core: list[str] = []
    for part in parts:
        part = part.strip("()（）,，")
        if not part:
            continue
        # Accept pure Chinese or pure ASCII alphabetic terms
        if _re.search(r"[一-鿿]", part) or _re.fullmatch(r"[A-Za-z0-9-]+", part):
            if part not in core:
                core.append(part)
        if len(core) >= max_terms:
            break
    return " ".join(core) if core else query


def _journal_plans(state: Any) -> list[ScenarioQueryPlan]:
    primary = _primary_query(state)
    broad = _cn_business_query(state)
    short = _short_query(broad, max_terms=3)
    plans = [ScenarioQueryPlan(query=broad, params={"query_role": "broad_cn"})]
    # Add a short-query fallback for academic journal search engines
    if short and short != broad:
        plans.append(
            ScenarioQueryPlan(query=short, params={"query_role": "short_cn"})
        )
    if primary and primary != broad:
        plans.append(
            ScenarioQueryPlan(query=primary, params={"query_role": "method_specific_cn"})
        )
    return plans


def scenario_query_plans(state: Any) -> dict[str, list[ScenarioQueryPlan]]:
    broad = _cn_business_query(state)
    primary = _primary_query(state)
    methodology = str(_confirmation(state, "methodology", "") or "").strip()
    patent_scope = str(_confirmation(state, "patent_scope", "全球") or "全球").strip()
    literature_date_range = _literature_date_range(state) or _confirmation(state, "literature_years", 5)
    literature_retmax = _literature_retmax(state)
    fulltext_expression = build_yiigle_fulltext_expression(
        keyword=broad,
        date_range=literature_date_range,
    )

    common_broad = [ScenarioQueryPlan(query=broad, params={"query_role": "broad_cn"})]
    return {
        "cmde_regulatory": common_broad,
        "standards_current": common_broad,
        "nmpa_competitor": [
            ScenarioQueryPlan(
                query=broad,
                params={
                    "query_role": "broad_cn",
                    "methodology": methodology,
                    "registration_types": [
                        "境内医疗器械（注册）",
                        "进口医疗器械（注册）",
                    ],
                },
            )
        ],
        "patenthub_patents": [
            ScenarioQueryPlan(
                query=broad,
                params={"query_role": "patent_cn", "patent_scope": patent_scope or "全球"},
            )
        ],
        "yiigle_zhjyyxzz": _journal_plans(state),
        "yiigle_zhsjkzz": _journal_plans(state),
        "cma_lab_management": _journal_plans(state),
        "wiley_alz": [
            ScenarioQueryPlan(
                query=_en_business_query(state),
                params={"query_role": "english_keywords"},
            )
        ],
        "pubmed_literature": [
            ScenarioQueryPlan(
                query=_english_primary_query(state),
                params={
                    "query_role": "pubmed_keywords",
                    "retmax": literature_retmax,
                    "date_range": literature_date_range,
                },
            )
        ],
        "pmc_fulltext": [
            ScenarioQueryPlan(
                query=_english_primary_query(state),
                params={
                    "query_role": "pmc_keywords",
                    "retmax": literature_retmax,
                    "date_range": literature_date_range,
                },
            )
        ],
        "openalex_literature": [
            ScenarioQueryPlan(
                query=_en_business_query(state),
                params={
                    "query_role": "openalex_keywords",
                    "retmax": literature_retmax,
                    "date_range": literature_date_range,
                },
            )
        ],
        "yiigle_fulltext": [
            ScenarioQueryPlan(
                query=fulltext_expression,
                params={
                    "query_role": "yiigle_fulltext_expression",
                    "base_keyword": broad,
                    "literature_types": DEFAULT_LITERATURE_TYPES,
                    "literature_date_range": literature_date_range,
                },
            )
        ],
    }


def default_query_plan(state: Any) -> list[ScenarioQueryPlan]:
    primary = _primary_query(state)
    return [ScenarioQueryPlan(query=primary, params={"query_role": "primary"})]
