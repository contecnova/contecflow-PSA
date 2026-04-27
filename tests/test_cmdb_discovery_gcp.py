import pytest

from app.services.service_desk.cmdb_discovery_service import discover_gcp


def test_discover_gcp_requires_project_id():
    with pytest.raises(ValueError, match="project_id"):
        discover_gcp({})
