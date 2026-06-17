from .registry import get_scenario


def adapter():
    return get_scenario("local_import")
