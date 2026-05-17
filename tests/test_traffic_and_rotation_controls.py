from datetime import timedelta

from app.models.settings import AppSetting
from app.services.key_management import (
    INTEGRATION_ROTATION_KEY,
    get_integration_rotation_status,
)
from app.services.traffic_control_service import consume_quota


def test_consume_quota_blocks_after_limit(db):
    tenant = "org-test"
    scope = "test.scope"
    subject = "user-1"

    first = consume_quota(db, scope=scope, tenant_id=tenant, subject=subject, limit=2, window_seconds=60)
    second = consume_quota(db, scope=scope, tenant_id=tenant, subject=subject, limit=2, window_seconds=60)
    third = consume_quota(db, scope=scope, tenant_id=tenant, subject=subject, limit=2, window_seconds=60)

    assert first["allowed"] is True
    assert second["allowed"] is True
    assert third["allowed"] is False
    assert third["retry_after"] >= 0


def test_rotation_status_marks_overdue(db):
    from app.services.key_management import _dt_to_str, _now

    old = _now() - timedelta(days=180)
    row = db.query(AppSetting).filter(AppSetting.key == INTEGRATION_ROTATION_KEY).first()
    if not row:
        row = AppSetting(key=INTEGRATION_ROTATION_KEY, value=_dt_to_str(old), description="test")
        db.add(row)
    else:
        row.value = _dt_to_str(old)
    db.commit()

    status = get_integration_rotation_status(db)
    assert status["is_overdue"] is True
    assert status["alert_level"] in {"critical", "warning"}
