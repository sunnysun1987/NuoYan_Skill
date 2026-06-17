from .registry import get_scenario
from .site_collect import collect_yiigle_journal


def adapter():
    return get_scenario("yiigle_fulltext")


def collect(task_id, task_dir, params):
    """Collect from 中华医学期刊全文数据库.

    Uses the same search-and-detail pipeline as the per-journal collectors
    but targets the cross-journal fulltext search endpoint.  Metadata and
    abstracts are captured even when full-text PDF requires IP login.
    """
    return collect_yiigle_journal(
        task_id=task_id,
        task_dir=task_dir,
        params=params,
        scenario_id="yiigle_fulltext",
        journal_url="https://www.yiigle.com/",
        subject_zh="中华医学期刊全文数据库",
        search_url_template="https://www.yiigle.com/searchMobile?ind=3&q={query}",
    )
