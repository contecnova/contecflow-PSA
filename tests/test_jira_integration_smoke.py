from app.models.jira_integration import JiraSyncDirection, JiraSyncStatus, JiraSyncEventType


def test_jira_sync_enums_have_expected_values():
    assert JiraSyncDirection.bidirectional.value == "bidirectional"
    assert JiraSyncStatus.pending.value == "pending"
    assert JiraSyncEventType.updated.value == "updated"
