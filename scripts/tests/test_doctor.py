from ivd_research.doctor import run_doctor


def test_doctor_uses_registered_cli_name(tmp_path):
    result = run_doctor(tmp_path)
    messages = "\n".join(check["impact_zh"] for check in result["checks"])

    assert "ivd-research" not in messages
    assert "nuoyan 命令" in messages
