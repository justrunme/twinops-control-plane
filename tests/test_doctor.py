from twinops.doctor import run_doctor


def test_run_doctor_returns_core_checks() -> None:
    checks = run_doctor()
    names = {item.name for item in checks}
    assert "twinopsctl" in names or "python:yaml" in names
    assert "python:yaml" in names
    assert all(item.detail for item in checks)
