from dataclasses import dataclass, field
from datetime import date
import re
from typing import Any

from .project_profile import is_ad_project


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

LITERATURE_PROFILES = {
    "quick_scan": {
        "label_zh": "快速扫描",
        "retmax": 50,
        "similar_retmax": 3,
        "similar_article_source_limit": 20,
        "pdf_download_limit": 10,
    },
    "complete_literature": {
        "label_zh": "完整文献",
        "retmax": 200,
        "similar_retmax": 5,
        "similar_article_source_limit": 50,
        "pdf_download_limit": 50,
    },
    "fulltext_first": {
        "label_zh": "全文优先",
        "retmax": 200,
        "similar_retmax": 5,
        "similar_article_source_limit": 50,
        "pdf_download_limit": 100,
    },
    "core_must_read": {
        "label_zh": "核心必读",
        "retmax": 100,
        "similar_retmax": 5,
        "similar_article_source_limit": 30,
        "pdf_download_limit": 30,
    },
    "chinese_first": {
        "label_zh": "中文优先",
        "retmax": 100,
        "similar_retmax": 3,
        "similar_article_source_limit": 20,
        "pdf_download_limit": 20,
    },
}

CN_TO_EN_KEYWORDS = {
    "肺炎支原体": "Mycoplasma pneumoniae",
    "支原体肺炎": "Mycoplasma pneumoniae pneumonia",
}

SOURCE_SAFE_STOP_TERMS = [
    *METHOD_QUERY_TERMS,
    *RESEARCH_STOP_WORDS,
    "定量",
    "定性",
    "半定量",
    "荧光免疫层析法",
    "荧光免疫层析",
    "免疫层析法",
    "免疫层析",
    "双抗体夹心法",
    "双抗夹心",
    "POCT",
    "poct",
    "平台",
    "仪器",
    "辅助诊断",
    "辅助判断",
    "风险提示",
    "动态监测",
    "血清",
    "血浆",
    "全血",
    "尿液",
    "样本",
    "作为",
    "补充",
    "对照",
    "优先",
]

OPENALEX_STOP_TOKENS = {
    "and",
    "or",
    "the",
    "a",
    "an",
    "kit",
    "kits",
    "test",
    "testing",
    "quantitative",
    "qualitative",
    "point-of-care",
    "point",
    "care",
    "poc",
    "poct",
    "serum",
    "plasma",
    "whole",
    "blood",
    "urine",
    "diagnosis",
    "screening",
    "monitoring",
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


def _dedupe(values: list[str]) -> list[str]:
    seen: list[str] = []
    for value in values:
        clean = " ".join(str(value or "").split()).strip()
        if clean and clean not in seen:
            seen.append(clean)
    return seen


def _profile_text(state: Any) -> str:
    return _append_terms(
        _primary_query(state),
        _broad_query(state),
        _confirmation(state, "chinese_synonyms", ""),
        _confirmation(state, "english_keywords", ""),
        _confirmation(state, "english_method_keywords", ""),
    )


def _strip_source_noise(text: str) -> str:
    clean = str(text or "")
    for term in SOURCE_SAFE_STOP_TERMS:
        clean = clean.replace(term, " ")
    clean = re.sub(r"[；;、，,。:：/|()（）\[\]【】\"'“”]+", " ", clean)
    return " ".join(clean.split())


def _hcg_core_queries(text: str) -> list[str]:
    lowered = text.lower()
    if not any(
        signal in lowered
        for signal in [
            "hcg",
            "β-hcg",
            "beta-hcg",
            "beta hcg",
            "chorionic gonadotropin",
        ]
    ) and "绒毛膜促性腺激素" not in text:
        return []
    return ["人绒毛膜促性腺激素", "β-hCG", "hCG"]


def _core_chinese_queries(state: Any, *, max_candidates: int = 4) -> list[str]:
    text = _profile_text(state)
    hcg_queries = _hcg_core_queries(text)
    if hcg_queries:
        return hcg_queries[:max_candidates]

    cleaned = _strip_source_noise(_broad_query(state) or _primary_query(state))
    parts = re.findall(r"[一-鿿A-Za-z0-9α-ωΑ-ΩβΒτΤ\-]+", cleaned)
    core: list[str] = []
    for part in parts:
        token = part.strip("-")
        if not token:
            continue
        lower = token.lower()
        if lower in {item.lower() for item in SOURCE_SAFE_STOP_TERMS}:
            continue
        if token.upper() in {"IVD", "POCT"}:
            continue
        if len(token) == 1 and not re.search(r"[A-Za-z0-9]", token):
            continue
        core.append(token)
        if len(core) >= 3:
            break
    candidates: list[str] = []
    if core:
        candidates.append(" ".join(core[:2]))
        candidates.append(" ".join(core[:3]))
    short = _short_query(cleaned, max_terms=2)
    if short:
        candidates.append(short)
    broad = _broad_query(state)
    if broad:
        candidates.append(broad)
    return _dedupe(candidates)[:max_candidates]


def _openalex_core_query(state: Any) -> str:
    text = _profile_text(state)
    if _hcg_core_queries(text):
        return "human chorionic gonadotropin beta hCG immunoassay"

    query = _openalex_query(state)
    tokens: list[str] = []
    for token in re.findall(r"[A-Za-z0-9α-ωΑ-ΩβΒτΤ\-]+", query):
        normalized = token.strip("-")
        lower = normalized.lower()
        if not normalized or lower in OPENALEX_STOP_TOKENS:
            continue
        if lower not in {item.lower() for item in tokens}:
            tokens.append(normalized)
        if len(" ".join(tokens)) >= 140 or len(tokens) >= 12:
            break
    return " ".join(tokens) or _english_primary_query(state)


def requires_wiley_alzheimer_source(state: Any) -> bool:
    return is_ad_project(state)


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


def _openalex_query(state: Any) -> str:
    import re as _re

    query = _en_business_query(state)
    replacements = {
        "AND": " ",
        "OR": " ",
    }
    for old, new in replacements.items():
        query = _re.sub(rf"\b{old}\b", new, query, flags=_re.IGNORECASE)
    query = query.replace("*", " ")
    query = _re.sub(r"[\"()（）]", " ", query)
    query = _re.sub(r"\s+", " ", query).strip()
    if len(query) > 220:
        terms = []
        for token in query.split():
            normalized = token.strip(" ,;；")
            if normalized and normalized.lower() not in {item.lower() for item in terms}:
                terms.append(normalized)
            if len(" ".join(terms)) >= 220:
                break
        query = " ".join(terms)
    return query or _english_primary_query(state)


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


def _literature_profile(state: Any) -> dict[str, Any]:
    profile_id = str(_confirmation(state, "literature_profile", "complete_literature") or "complete_literature").strip()
    profile = LITERATURE_PROFILES.get(profile_id, LITERATURE_PROFILES["complete_literature"])
    requested_retmax = _literature_retmax(state)
    result = {"profile_id": profile_id, **profile}
    result["retmax"] = requested_retmax
    return result


def _date_range_bounds(
    date_range: Any,
    *,
    today: date | None = None,
) -> tuple[str, str]:
    if isinstance(date_range, dict):
        start = str(date_range.get("start") or date_range.get("from") or "").strip()
        end = str(date_range.get("end") or date_range.get("to") or "").strip()
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
    core_queries = _core_chinese_queries(state)
    short = _short_query(broad, max_terms=3)
    plans = [
        ScenarioQueryPlan(query=query, params={"query_role": "core_cn"})
        for query in core_queries
    ]
    plans.append(ScenarioQueryPlan(query=broad, params={"query_role": "broad_cn"}))
    # Add a short-query fallback for academic journal search engines
    if short and short != broad:
        plans.append(
            ScenarioQueryPlan(query=short, params={"query_role": "short_cn"})
        )
    if primary and primary != broad:
        plans.append(
            ScenarioQueryPlan(query=primary, params={"query_role": "method_specific_cn"})
        )
    deduped: list[ScenarioQueryPlan] = []
    seen: set[str] = set()
    for plan in plans:
        if plan.query and plan.query not in seen:
            deduped.append(plan)
            seen.add(plan.query)
    return deduped


def _source_safe_cn_plans(state: Any, *, include_product_hint: bool = True) -> list[ScenarioQueryPlan]:
    primary = _primary_query(state)
    broad = _cn_business_query(state)
    core_queries = _core_chinese_queries(state)
    plans = [
        ScenarioQueryPlan(query=query, params={"query_role": "core_cn"})
        for query in core_queries
    ]
    if include_product_hint:
        for query in core_queries[:2]:
            hinted = _append_terms(query, "测定试剂盒")
            plans.append(
                ScenarioQueryPlan(query=hinted, params={"query_role": "core_product_cn"})
            )
    short = _short_query(_strip_source_noise(broad), max_terms=3)
    if short:
        plans.append(ScenarioQueryPlan(query=short, params={"query_role": "short_cn"}))
    if broad:
        plans.append(ScenarioQueryPlan(query=broad, params={"query_role": "broad_cn"}))
    if primary and primary != broad:
        plans.append(ScenarioQueryPlan(query=primary, params={"query_role": "primary_cn"}))
    deduped: list[ScenarioQueryPlan] = []
    seen: set[str] = set()
    for plan in plans:
        if plan.query and plan.query not in seen:
            deduped.append(plan)
            seen.add(plan.query)
    return deduped


def _openalex_plans(state: Any, literature_profile: dict[str, Any], literature_date_range: Any) -> list[ScenarioQueryPlan]:
    retmax = literature_profile["retmax"]
    common_params = {
        "retmax": retmax,
        "date_range": literature_date_range,
        "literature_profile": literature_profile["profile_id"],
    }
    core = _openalex_core_query(state)
    broad = _openalex_query(state)
    plans = [
        ScenarioQueryPlan(
            query=core,
            params={"query_role": "openalex_core_keywords", **common_params},
        )
    ]
    if broad and broad != core:
        plans.append(
            ScenarioQueryPlan(
                query=broad,
                params={"query_role": "openalex_broad_keywords", **common_params},
            )
        )
    return plans


def scenario_query_plans(state: Any) -> dict[str, list[ScenarioQueryPlan]]:
    broad = _cn_business_query(state)
    primary = _primary_query(state)
    short = _short_query(broad, max_terms=3)
    methodology = str(_confirmation(state, "methodology", "") or "").strip()
    patent_scope = str(_confirmation(state, "patent_scope", "全球") or "全球").strip()
    literature_date_range = _literature_date_range(state) or _confirmation(state, "literature_years", 5)
    literature_profile = _literature_profile(state)
    literature_retmax = literature_profile["retmax"]
    fulltext_expression = build_yiigle_fulltext_expression(
        keyword=broad,
        date_range=literature_date_range,
    )

    common_broad = [ScenarioQueryPlan(query=broad, params={"query_role": "broad_cn"})]
    if short and short != broad:
        common_broad.append(ScenarioQueryPlan(query=short, params={"query_role": "short_cn"}))
    if primary and primary not in {broad, short}:
        common_broad.append(ScenarioQueryPlan(query=primary, params={"query_role": "primary_cn"}))
    source_safe_cn = _source_safe_cn_plans(state)
    standard_safe_cn = _source_safe_cn_plans(state, include_product_hint=True)
    fulltext_short_expression = build_yiigle_fulltext_expression(
        keyword=(_core_chinese_queries(state) or [broad])[0],
        date_range=literature_date_range,
    )
    plans = {
        "cmde_regulatory": source_safe_cn,
        "standards_current": standard_safe_cn,
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
        "cma_lab_management": _journal_plans(state),
        "pubmed_literature": [
            ScenarioQueryPlan(
                query=_english_primary_query(state),
                params={
                    "query_role": "pubmed_keywords",
                    "retmax": literature_retmax,
                    "date_range": literature_date_range,
                    "literature_profile": literature_profile["profile_id"],
                    "similar_retmax": literature_profile["similar_retmax"],
                    "similar_article_source_limit": literature_profile["similar_article_source_limit"],
                    "pdf_download_limit": literature_profile["pdf_download_limit"],
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
                    "literature_profile": literature_profile["profile_id"],
                    "pdf_download_limit": literature_profile["pdf_download_limit"],
                },
            )
        ],
        "openalex_literature": _openalex_plans(state, literature_profile, literature_date_range),
        "yiigle_fulltext": [
            ScenarioQueryPlan(
                query=fulltext_short_expression,
                params={
                    "query_role": "yiigle_fulltext_core_expression",
                    "base_keyword": (_core_chinese_queries(state) or [broad])[0],
                    "literature_types": DEFAULT_LITERATURE_TYPES,
                    "literature_date_range": literature_date_range,
                },
            ),
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
    from .project_profile import is_neurology_project

    if is_neurology_project(state):
        plans["yiigle_zhsjkzz"] = _journal_plans(state)
    if requires_wiley_alzheimer_source(state):
        plans["wiley_alz"] = [
            ScenarioQueryPlan(
                query=_en_business_query(state),
                params={"query_role": "english_keywords"},
            )
        ]
    return plans


def default_query_plan(state: Any) -> list[ScenarioQueryPlan]:
    primary = _primary_query(state)
    return [ScenarioQueryPlan(query=primary, params={"query_role": "primary"})]
