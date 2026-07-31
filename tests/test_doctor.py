from twinops.doctor import run_doctor


def test_run_doctor_returns_core_checks() -> None:
    checks = run_doctor()
    names = {item.name for item in checks}
    assert "twinopsctl" in names or "python:yaml" in names
    assert "python:yaml" in names
    assert "mqtt-topic-catalog" in names
    catalog = next(item for item in checks if item.name == "mqtt-topic-catalog")
    assert catalog.ok is True
    assert all(item.detail for item in checks)
