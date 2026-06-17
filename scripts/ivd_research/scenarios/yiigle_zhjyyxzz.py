from .registry import get_scenario
from .site_collect import collect_yiigle_journal


def adapter():
    return get_scenario("yiigle_zhjyyxzz")


def collect(task_id, task_dir, params):
    failure_modes = ("collection_failed", "no_results")
    _ = failure_modes
    return collect_yiigle_journal(
        task_id=task_id,
        task_dir=task_dir,
        params=params,
        scenario_id="yiigle_zhjyyxzz",
        journal_url="https://zhjyyxzz.yiigle.com/",
        subject_zh="中华检验医学杂志文献",
    )
