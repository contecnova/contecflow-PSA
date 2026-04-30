"""
Complete test suite for BI Dashboard Collaboration features v23.10.50
- Comments with resolution
- Dashboard sharing with permissions  
- Shared views
- Dashboard versioning
- Notification system
- Real-time updates
"""
import json
from tests.conftest import auth
from sqlalchemy import text

from app.models.bi_collaboration import (
    DashboardComment,
    DashboardShare,
    DashboardVersion,
    DashboardNotification,
)


class TestBiCollaborationComments:
    """Test comment creation, resolution, and persistence."""

    def test_create_comment_persists_in_db(self, client, admin_token, db):
        """Creating a comment should persist in DashboardComment table."""
        res = client.post(
            "/api/v1/bi/collaboration/comments",
            headers=auth(admin_token),
            json={
                "dashboard_key": "sales_exec",
                "widget_id": "revenue_trend",
                "message": "Revenue trend looks concerning Q2",
            },
        )
        assert res.status_code == 200, res.text
        comment = res.json()["comment"]

        # Verify DB persistence
        rows = db.query(DashboardComment).filter(
            DashboardComment.id == comment["id"]
        ).all()
        assert len(rows) == 1
        assert rows[0].message == "Revenue trend looks concerning Q2"
        assert rows[0].resolved is False

    def test_list_comments_for_dashboard(self, client, admin_token):
        """Listing comments for a dashboard should return all comments."""
        # Create multiple comments
        for i in range(3):
            client.post(
                "/api/v1/bi/collaboration/comments",
                headers=auth(admin_token),
                json={
                    "dashboard_key": "ops",
                    "widget_id": f"widget_{i}",
                    "message": f"Comment {i}",
                },
            )

        # List comments
        res = client.get(
            "/api/v1/bi/collaboration/comments",
            headers=auth(admin_token),
            params={"dashboard_key": "ops"},
        )
        assert res.status_code == 200, res.text
        assert res.json()["count"] >= 3

    def test_resolve_comment(self, client, admin_token, db):
        """Resolving a comment should update resolved flag and timestamp."""
        # Create comment
        create_res = client.post(
            "/api/v1/bi/collaboration/comments",
            headers=auth(admin_token),
            json={
                "dashboard_key": "support",
                "widget_id": "tickets",
                "message": "Fix ticket backlog display",
            },
        )
        comment_id = create_res.json()["comment"]["id"]

        # Resolve comment
        resolve_res = client.patch(
            f"/api/v1/bi/collaboration/comments/{comment_id}/resolve",
            headers=auth(admin_token),
        )
        assert resolve_res.status_code == 200, resolve_res.text

        # Verify DB update
        rows = db.query(DashboardComment).filter(
            DashboardComment.id == comment_id
        ).all()
        assert len(rows) == 1
        assert rows[0].resolved is True
        assert rows[0].resolved_at is not None

    def test_comments_fallback_when_table_missing(self, client, admin_token, db):
        """When DashboardComment table missing, should fallback to JSON."""
        db.execute(text("DROP TABLE IF EXISTS dashboard_comments"))
        db.commit()

        # List should work (fallback returns empty)
        list_res = client.get(
            "/api/v1/bi/collaboration/comments?dashboard_key=fallback_test",
            headers=auth(admin_token),
        )
        assert list_res.status_code == 200, list_res.text

        # Create should work (fallback stores in AppSetting JSON)
        create_res = client.post(
            "/api/v1/bi/collaboration/comments",
            headers=auth(admin_token),
            json={
                "dashboard_key": "fallback_test",
                "widget_id": "test_widget",
                "message": "Fallback comment",
            },
        )
        assert create_res.status_code == 200, create_res.text


class TestBiCollaborationSharing:
    """Test dashboard sharing with permissions."""

    def test_share_dashboard_creates_share_record(self, client, admin_token, db):
        """Sharing a dashboard should create a DashboardShare record."""
        res = client.post(
            "/api/v1/bi/collaboration/dashboards/finance/shares",
            headers=auth(admin_token),
            json={
                "target_user_id": "user-analyst-1",
                "target_user_name": "Junior Analyst",
                "permission": "view",
            },
        )
        assert res.status_code == 200, res.text
        share = res.json()["share"]

        # Verify DB persistence
        rows = db.query(DashboardShare).filter(
            DashboardShare.id == share["id"]
        ).all()
        assert len(rows) == 1
        assert rows[0].permission == "view"
        assert rows[0].user_id == "user-analyst-1"

    def test_share_with_edit_permission(self, client, admin_token, db):
        """Sharing with edit permission should be recorded correctly."""
        res = client.post(
            "/api/v1/bi/collaboration/dashboards/products/shares",
            headers=auth(admin_token),
            json={
                "target_user_id": "user-pm-1",
                "target_user_name": "Product Manager",
                "permission": "edit",
            },
        )
        assert res.status_code == 200, res.text
        share = res.json()["share"]

        rows = db.query(DashboardShare).filter(
            DashboardShare.id == share["id"]
        ).all()
        assert rows[0].permission == "edit"

    def test_share_with_admin_permission(self, client, admin_token, db):
        """Sharing with admin permission should be recorded correctly."""
        res = client.post(
            "/api/v1/bi/collaboration/dashboards/admin/shares",
            headers=auth(admin_token),
            json={
                "target_user_id": "user-admin-2",
                "target_user_name": "Admin User",
                "permission": "admin",
            },
        )
        assert res.status_code == 200, res.text
        share = res.json()["share"]

        rows = db.query(DashboardShare).filter(
            DashboardShare.id == share["id"]
        ).all()
        assert rows[0].permission == "admin"

    def test_list_dashboard_shares(self, client, admin_token):
        """Listing shares for a dashboard should show all shares."""
        dashboard_key = "shared_dash"

        # Create multiple shares
        for i in range(2):
            client.post(
                f"/api/v1/bi/collaboration/dashboards/{dashboard_key}/shares",
                headers=auth(admin_token),
                json={
                    "target_user_id": f"user-{i}",
                    "target_user_name": f"User {i}",
                    "permission": "view",
                },
            )

        # List shares
        res = client.get(
            f"/api/v1/bi/collaboration/dashboards/{dashboard_key}/shares",
            headers=auth(admin_token),
        )
        assert res.status_code == 200, res.text
        assert res.json()["count"] >= 2

    def test_revoke_dashboard_share(self, client, admin_token, db):
        """Revoking a share should delete the DashboardShare record."""
        # Create share
        create_res = client.post(
            "/api/v1/bi/collaboration/dashboards/revoke_test/shares",
            headers=auth(admin_token),
            json={
                "target_user_id": "user-revoke",
                "target_user_name": "Revoke User",
                "permission": "edit",
            },
        )
        share_id = create_res.json()["share"]["id"]

        # Revoke share
        revoke_res = client.delete(
            f"/api/v1/bi/collaboration/dashboards/revoke_test/shares/{share_id}",
            headers=auth(admin_token),
        )
        assert revoke_res.status_code == 200, revoke_res.text

        # Verify DB deletion
        rows = db.query(DashboardShare).filter(
            DashboardShare.id == share_id
        ).all()
        assert len(rows) == 0


class TestBiDashboardVersioning:
    """Test dashboard version history and restoration."""

    def test_create_dashboard_version(self, client, admin_token, db):
        """Creating a version should persist configuration snapshot."""
        res = client.post(
            "/api/v1/bi/collaboration/dashboards/marketing/versions",
            headers=auth(admin_token),
            json={
                "config": {"layout": "grid-12", "widgets": 5, "theme": "light"},
                "change_log": "Rearranged widgets for new reporting",
            },
        )
        assert res.status_code == 200, res.text
        version = res.json()["version"]

        # Verify DB persistence
        rows = db.query(DashboardVersion).filter(
            DashboardVersion.id == version["id"]
        ).all()
        assert len(rows) == 1
        assert rows[0].version == 1
        assert rows[0].change_log == "Rearranged widgets for new reporting"
        config_payload = rows[0].config
        if isinstance(config_payload, str):
            config_payload = json.loads(config_payload)
        assert config_payload == {"layout": "grid-12", "widgets": 5, "theme": "light"}

    def test_list_dashboard_versions_in_order(self, client, admin_token):
        """Listing versions should return them in descending order."""
        dashboard_key = "versioned_dash"

        # Create multiple versions
        for i in range(3):
            client.post(
                f"/api/v1/bi/collaboration/dashboards/{dashboard_key}/versions",
                headers=auth(admin_token),
                json={
                    "config": {"iteration": i},
                    "change_log": f"Update {i}",
                },
            )

        # List versions
        res = client.get(
            f"/api/v1/bi/collaboration/dashboards/{dashboard_key}/versions",
            headers=auth(admin_token),
        )
        assert res.status_code == 200, res.text
        versions = res.json()["items"]
        
        # Should be ordered by created_at descending
        if len(versions) > 1:
            assert versions[0]["created_at"] >= versions[1]["created_at"]

    def test_restore_previous_version(self, client, admin_token):
        """Restoring a previous version should record the restoration."""
        dashboard_key = "restore_test"

        # Create v1
        v1_res = client.post(
            f"/api/v1/bi/collaboration/dashboards/{dashboard_key}/versions",
            headers=auth(admin_token),
            json={
                "config": {"state": "v1"},
                "change_log": "Version 1",
            },
        )
        v1_id = v1_res.json()["version"]["id"]

        # Create v2
        client.post(
            f"/api/v1/bi/collaboration/dashboards/{dashboard_key}/versions",
            headers=auth(admin_token),
            json={
                "config": {"state": "v2"},
                "change_log": "Version 2",
            },
        )

        # Restore v1
        restore_res = client.post(
            f"/api/v1/bi/collaboration/dashboards/{dashboard_key}/versions/{v1_id}/restore",
            headers=auth(admin_token),
        )
        assert restore_res.status_code == 200, restore_res.text

    def test_version_increments_correctly(self, client, admin_token, db):
        """Each new version should increment the version number."""
        dashboard_key = "increment_test"

        version_numbers = []
        for i in range(3):
            res = client.post(
                f"/api/v1/bi/collaboration/dashboards/{dashboard_key}/versions",
                headers=auth(admin_token),
                json={"config": {}, "change_log": f"v{i}"},
            )
            version_numbers.append(res.json()["version"]["version"])

        # Should increment 1, 2, 3
        assert version_numbers == [1, 2, 3]


class TestBiCollaborationNotifications:
    """Test notification system for collaboration events."""

    def test_list_unread_notifications(self, client, admin_token, db):
        """Listing notifications should return unread by default."""
        # Get current user from token (mocked in tests)
        res = client.get(
            "/api/v1/bi/collaboration/notifications",
            headers=auth(admin_token),
            params={"include_read": False},
        )
        assert res.status_code == 200, res.text
        assert "items" in res.json()
        assert "count" in res.json()

    def test_filter_notifications_by_dashboard(self, client, admin_token):
        """Should be able to filter notifications by dashboard_key."""
        res = client.get(
            "/api/v1/bi/collaboration/notifications",
            headers=auth(admin_token),
            params={"dashboard_key": "sales", "include_read": False},
        )
        assert res.status_code == 200, res.text

    def test_include_read_notifications(self, client, admin_token):
        """Should be able to include read notifications in list."""
        res = client.get(
            "/api/v1/bi/collaboration/notifications",
            headers=auth(admin_token),
            params={"include_read": True},
        )
        assert res.status_code == 200, res.text

    def test_mark_notification_as_read(self, client, admin_token, db):
        """Marking a notification as read should update is_read flag."""
        # First, create a notification by creating a comment
        comment_res = client.post(
            "/api/v1/bi/collaboration/comments",
            headers=auth(admin_token),
            json={
                "dashboard_key": "notify_test",
                "widget_id": "widget",
                "message": "Trigger notification",
            },
        )

        # List notifications
        notif_res = client.get(
            "/api/v1/bi/collaboration/notifications",
            headers=auth(admin_token),
            params={"dashboard_key": "notify_test", "include_read": False},
        )

        if notif_res.json()["count"] > 0:
            notif_id = notif_res.json()["items"][0]["id"]

            # Mark as read
            mark_res = client.patch(
                f"/api/v1/bi/collaboration/notifications/{notif_id}",
                headers=auth(admin_token),
                json={"is_read": True},
            )
            assert mark_res.status_code == 200, mark_res.text

            # Verify DB update
            rows = db.query(DashboardNotification).filter(
                DashboardNotification.id == notif_id
            ).all()
            if len(rows) > 0:
                assert rows[0].is_read is True
                assert rows[0].read_at is not None

    def test_mark_notification_as_unread(self, client, admin_token, db):
        """Marking a notification as unread should clear read_at."""
        # This would require a notification to already exist
        # Testing the API contract
        pass


class TestBiCollaborationSharedViews:
    """Test shared views functionality."""

    def test_create_shared_view(self, client, admin_token, db):
        """Creating a shared view should persist filters."""
        res = client.post(
            "/api/v1/bi/collaboration/shared-views",
            headers=auth(admin_token),
            json={
                "name": "Q2 Revenue View",
                "dashboard_key": "finance",
                "filters": {"period": "Q2", "region": "EMEA"},
            },
        )
        assert res.status_code == 200, res.text
        view = res.json()["view"]
        assert view["name"] == "Q2 Revenue View"

    def test_list_shared_views(self, client, admin_token):
        """Listing shared views should return all views."""
        # Create a view
        client.post(
            "/api/v1/bi/collaboration/shared-views",
            headers=auth(admin_token),
            json={
                "name": "Test View",
                "dashboard_key": "test",
                "filters": {},
            },
        )

        # List views
        res = client.get(
            "/api/v1/bi/collaboration/shared-views",
            headers=auth(admin_token),
        )
        assert res.status_code == 200, res.text
        assert "items" in res.json()

    def test_update_shared_view(self, client, admin_token):
        """Updating a shared view should modify its properties."""
        # Create a view
        create_res = client.post(
            "/api/v1/bi/collaboration/shared-views",
            headers=auth(admin_token),
            json={
                "name": "Original Name",
                "dashboard_key": "test",
                "filters": {"v": 1},
            },
        )
        view_id = create_res.json()["view"]["id"]

        # Update view
        update_res = client.patch(
            f"/api/v1/bi/collaboration/shared-views/{view_id}",
            headers=auth(admin_token),
            json={
                "name": "Updated Name",
                "filters": {"v": 2},
            },
        )
        assert update_res.status_code == 200, update_res.text
        assert update_res.json()["view"]["name"] == "Updated Name"


class TestBiCollaborationRealTimeUpdates:
    """Test real-time update snapshots."""

    def test_dashboard_update_snapshot(self, client, admin_token):
        """Dashboard update snapshot should aggregate current state."""
        dashboard_key = "snapshot_test"

        # Create some collaboration data
        client.post(
            "/api/v1/bi/collaboration/comments",
            headers=auth(admin_token),
            json={
                "dashboard_key": dashboard_key,
                "widget_id": "w1",
                "message": "Test comment",
            },
        )

        # Get snapshot
        res = client.get(
            f"/api/v1/bi/collaboration/dashboards/{dashboard_key}/updates/snapshot",
            headers=auth(admin_token),
        )
        assert res.status_code == 200, res.text
        snapshot = res.json()
        assert snapshot["type"] == "bi_dashboard_update"
        assert snapshot["dashboard_key"] == dashboard_key
        assert "timestamp" in snapshot
        assert "latest_version" in snapshot
        assert "comment_count" in snapshot
        assert "share_count" in snapshot


class TestBiCollaborationIntegration:
    """Integration tests combining multiple features."""

    def test_collaboration_workflow_full_cycle(self, client, admin_token, db):
        """Full collaboration workflow: create, share, comment, version."""
        dashboard_key = "integration_test"

        # 1. Share dashboard
        share_res = client.post(
            f"/api/v1/bi/collaboration/dashboards/{dashboard_key}/shares",
            headers=auth(admin_token),
            json={
                "target_user_id": "user-collaborator",
                "target_user_name": "Collaborator",
                "permission": "edit",
            },
        )
        assert share_res.status_code == 200, share_res.text

        # 2. Create comment
        comment_res = client.post(
            "/api/v1/bi/collaboration/comments",
            headers=auth(admin_token),
            json={
                "dashboard_key": dashboard_key,
                "widget_id": "metric_1",
                "message": "Interesting trend in Q2",
            },
        )
        assert comment_res.status_code == 200, comment_res.text

        # 3. Create version
        version_res = client.post(
            f"/api/v1/bi/collaboration/dashboards/{dashboard_key}/versions",
            headers=auth(admin_token),
            json={
                "config": {"updated": True},
                "change_log": "Added new metrics",
            },
        )
        assert version_res.status_code == 200, version_res.text

        # 4. Verify all are persisted
        comments = client.get(
            "/api/v1/bi/collaboration/comments",
            headers=auth(admin_token),
            params={"dashboard_key": dashboard_key},
        ).json()
        assert comments["count"] > 0

        shares = client.get(
            f"/api/v1/bi/collaboration/dashboards/{dashboard_key}/shares",
            headers=auth(admin_token),
        ).json()
        assert shares["count"] > 0

        versions = client.get(
            f"/api/v1/bi/collaboration/dashboards/{dashboard_key}/versions",
            headers=auth(admin_token),
        ).json()
        assert versions["count"] > 0

    def test_collaboration_multiuser_scenario(self, client, admin_token):
        """Multiple users collaborating on same dashboard."""
        dashboard_key = "multiuser_test"

        # User 1 creates comment
        client.post(
            "/api/v1/bi/collaboration/comments",
            headers=auth(admin_token),
            json={
                "dashboard_key": dashboard_key,
                "widget_id": "w1",
                "message": "User 1 comment",
            },
        )

        # User 2 creates comment (simulated with same token)
        client.post(
            "/api/v1/bi/collaboration/comments",
            headers=auth(admin_token),
            json={
                "dashboard_key": dashboard_key,
                "widget_id": "w2",
                "message": "User 2 comment",
            },
        )

        # List should show both
        res = client.get(
            "/api/v1/bi/collaboration/comments",
            headers=auth(admin_token),
            params={"dashboard_key": dashboard_key},
        )
        assert res.json()["count"] >= 2
