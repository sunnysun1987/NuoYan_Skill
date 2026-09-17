from pathlib import PureWindowsPath

from ivd_research.paths import portable_relative_path


def test_portable_relative_path_uses_forward_slashes_for_windows_paths():
    root = PureWindowsPath(r"C:\Nuoyan\task")
    path = root / "extracted_text" / "life_science_research" / "MAT-000001.txt"

    assert portable_relative_path(path, root) == (
        "extracted_text/life_science_research/MAT-000001.txt"
    )
