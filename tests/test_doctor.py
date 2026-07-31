from twinops.doctor import run_doctor


def test_run_doctor_returns_core_checks() -> None:
    checks = run_doctor()
    names = {item.name for item in checks}
    assert "twinopsctl" in names or "python:yaml" in names
    assert "python:yaml" in names
    assert "mqtt-topic-catalog" in names
    assert "mqtt-acl-profile" in names
    assert "helm-umbrella" in names
    assert "mqtt-tls-profile" in names
    assert "demo-gitops-script" in names
    catalog = next(item for item in checks if item.name == "mqtt-topic-catalog")
    assert catalog.ok is True
    assert next(item for item in checks if item.name == "mqtt-acl-profile").ok is True
    assert next(item for item in checks if item.name == "helm-umbrella").ok is True
    assert next(item for item in checks if item.name == "mqtt-tls-profile").ok is True
    assert next(item for item in checks if item.name == "demo-gitops-script").ok is True
    assert all(item.detail for item in checks)
