from .registry import get_scenario
from .site_collect import collect_search_snapshot


def adapter():
    return get_scenario("wiley_alz")


def collect(task_id, task_dir, params):
    failure_modes = ("collection_failed", "no_results")
    return collect_search_snapshot(
        task_id=task_id,
        task_dir=task_dir,
        params=params,
        scenario_id="wiley_alz",
        material_type="literature",
        subject_zh="Wiley Alzheimer 文献",
        search_url_template="https://alz-journals.onlinelibrary.wiley.com/action/doSearch?AllField={query}",
        no_result_markers=["No results", "没有结果"],
        validation_rules=["文献详情包含英文标题、作者、DOI 或摘要", *failure_modes],
    )
