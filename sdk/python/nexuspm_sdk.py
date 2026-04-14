"""
Clarive Python SDK
==================
Official Python client for the Clarive PSA REST API.

Usage::

    from nexuspm_sdk import ClariveClient

    client = ClariveClient(base_url="https://clarive.example.com", token="your-jwt-token")

    # List projects
    projects = client.projects.list()

    # Create a task
    task = client.tasks.create(project_id="proj-123", title="New task", status="todo")

    # Log hours
    client.imputations.create(task_id=task["id"], user_id="usr-1", hours=3.5, date="2024-01-15")

    # AI overrun prediction
    prediction = client.ai.overrun_prediction("proj-123")
    print(prediction["cost_overrun_prob"])

Requirements: requests>=2.28
"""

from __future__ import annotations

import os
import json
from typing import Any, Dict, List, Optional, Union
from urllib.parse import urljoin

try:
    import requests
    from requests import Response
except ImportError as exc:
    raise ImportError("Install the 'requests' package: pip install requests") from exc

__version__ = "1.0.0"
__all__ = ["ClariveClient", "ClariveError", "AuthError", "NotFoundError",
           # Backwards-compat aliases
           "NexusPMClient", "NexusPMError"]

# ── Exceptions ────────────────────────────────────────────────────────────────

class ClariveError(Exception):
    """Base exception for Clarive SDK errors."""
    def __init__(self, message: str, status_code: int = 0, response: Optional[Response] = None):
        super().__init__(message)
        self.status_code = status_code
        self.response = response


class AuthError(ClariveError):
    """Raised when authentication fails (401/403)."""


class NotFoundError(ClariveError):
    """Raised when a resource is not found (404)."""


# ── HTTP base ─────────────────────────────────────────────────────────────────

class _BaseResource:
    def __init__(self, client: "ClariveClient") -> None:
        self._client = client

    def _get(self, path: str, params: Optional[Dict] = None) -> Any:
        return self._client._request("GET", path, params=params)

    def _post(self, path: str, json: Optional[Dict] = None) -> Any:
        return self._client._request("POST", path, json=json)

    def _patch(self, path: str, json: Optional[Dict] = None) -> Any:
        return self._client._request("PATCH", path, json=json)

    def _delete(self, path: str) -> Any:
        return self._client._request("DELETE", path)


# ── Resource namespaces ───────────────────────────────────────────────────────

class ProjectsResource(_BaseResource):
    def list(self, status: Optional[str] = None, search: Optional[str] = None) -> List[Dict]:
        """List all accessible projects."""
        params = {}
        if status:
            params["status"] = status
        if search:
            params["search"] = search
        return self._get("/projects", params=params)

    def get(self, project_id: str) -> Dict:
        """Get a single project by ID."""
        return self._get(f"/projects/{project_id}")

    def create(self, name: str, code: str, **kwargs) -> Dict:
        """Create a new project."""
        return self._post("/projects", json={"name": name, "code": code, **kwargs})

    def update(self, project_id: str, **kwargs) -> Dict:
        """Update project fields."""
        return self._patch(f"/projects/{project_id}", json=kwargs)

    def delete(self, project_id: str) -> Dict:
        """Delete a project."""
        return self._delete(f"/projects/{project_id}")


class TasksResource(_BaseResource):
    def list(self, project_id: Optional[str] = None, assignee_id: Optional[str] = None,
             status: Optional[str] = None, skip: int = 0, limit: int = 100) -> List[Dict]:
        """List tasks with optional filters."""
        params = {"skip": skip, "limit": limit}
        if project_id:
            params["project_id"] = project_id
        if assignee_id:
            params["assignee_id"] = assignee_id
        if status:
            params["status"] = status
        return self._get("/tasks", params=params)

    def get(self, task_id: str) -> Dict:
        """Get a task by ID."""
        return self._get(f"/tasks/{task_id}")

    def create(self, project_id: str, title: str, **kwargs) -> Dict:
        """Create a task. Pass any Task schema fields as kwargs."""
        return self._post("/tasks", json={"project_id": project_id, "title": title, **kwargs})

    def update(self, task_id: str, **kwargs) -> Dict:
        """Update task fields."""
        return self._patch(f"/tasks/{task_id}", json=kwargs)

    def bulk_update_dates(self, updates: List[Dict]) -> Dict:
        """Bulk patch task dates. updates = [{"id": ..., "start_date": ..., "due_date": ...}]"""
        return self._patch("/tasks/bulk-dates", json={"updates": updates})


class ImputationsResource(_BaseResource):
    def list(self, project_id: Optional[str] = None, user_id: Optional[str] = None,
             start_date: Optional[str] = None, end_date: Optional[str] = None) -> List[Dict]:
        """List time imputations."""
        params = {}
        for k, v in [("project_id", project_id), ("user_id", user_id),
                     ("start_date", start_date), ("end_date", end_date)]:
            if v:
                params[k] = v
        return self._get("/imputations", params=params)

    def create(self, task_id: str, user_id: str, hours: float, date: str, **kwargs) -> Dict:
        """Log hours to a task."""
        return self._post("/imputations", json={
            "task_id": task_id, "user_id": user_id, "hours": hours, "date": date, **kwargs
        })

    def update(self, imputation_id: str, **kwargs) -> Dict:
        return self._patch(f"/imputations/{imputation_id}", json=kwargs)

    def delete(self, imputation_id: str) -> Dict:
        return self._delete(f"/imputations/{imputation_id}")


class UsersResource(_BaseResource):
    def list(self, active: Optional[bool] = None) -> List[Dict]:
        """List all users."""
        params = {}
        if active is not None:
            params["active"] = active
        return self._get("/users", params=params)

    def get(self, user_id: str) -> Dict:
        return self._get(f"/users/{user_id}")

    def me(self) -> Dict:
        """Get the authenticated user's profile."""
        return self._get("/users/me")


class ResourcesResource(_BaseResource):
    def list(self) -> List[Dict]:
        return self._get("/resources")

    def get(self, resource_id: str) -> Dict:
        return self._get(f"/resources/{resource_id}")

    def capacity(self, resource_id: str, start_date: str, end_date: str) -> Dict:
        """Get capacity for a resource in a date range."""
        return self._get(f"/resources/{resource_id}/capacity",
                         params={"start_date": start_date, "end_date": end_date})

    def utilization_trend(self) -> List[Dict]:
        """Get team utilization trend data."""
        return self._get("/resources/utilization-trend")


class FinancialsResource(_BaseResource):
    def profitability(self, project_id: str) -> Dict:
        return self._get(f"/projects/{project_id}/profitability")

    def evm(self, project_id: str) -> Dict:
        """Earned Value Management metrics for a project."""
        return self._get(f"/evm/{project_id}")

    def revenue_journal(self, project_id: str) -> Dict:
        """GAAP double-entry journal entries (ASC 606 / IFRS 15)."""
        return self._get(f"/revenue/journal/{project_id}")

    def revenue_journal_csv(self, project_id: str) -> str:
        """Export journal entries as CSV string."""
        return self._get(f"/revenue/journal/{project_id}/export")["csv"]

    def milestone_billing(self, project_id: str) -> List[Dict]:
        return self._get(f"/milestone-billing/{project_id}")

    def invoices(self, project_id: Optional[str] = None) -> List[Dict]:
        params = {}
        if project_id:
            params["project_id"] = project_id
        return self._get("/invoices", params=params)


class AIResource(_BaseResource):
    def overrun_prediction(self, project_id: str) -> Dict:
        """AI cost & schedule overrun prediction for a project."""
        return self._post("/ai/overrun-prediction", json={"project_id": project_id})

    def chat(self, message: str, context: Optional[Dict] = None) -> Dict:
        """Send a message to NexusAgent AI."""
        payload: Dict = {"message": message}
        if context:
            payload["context"] = context
        return self._post("/ai/chat", json=payload)

    def summarize_project(self, project_id: str) -> Dict:
        """Generate an AI summary of project health."""
        return self._post("/ai/summarize", json={"project_id": project_id})

    def detect_burnout(self) -> List[Dict]:
        """Detect potential burnout signals across team members."""
        return self._get("/ai/burnout-detection")


class JiraResource(_BaseResource):
    def config(self) -> Dict:
        """Get stored Jira configuration (token masked)."""
        return self._get("/jira/config")

    def save_config(self, jira_url: str, jira_email: str, jira_api_token: str,
                    jira_project_key: str) -> Dict:
        """Save Jira credentials."""
        return self._post("/jira/config", json={
            "jira_url": jira_url, "jira_email": jira_email,
            "jira_api_token": jira_api_token, "jira_project_key": jira_project_key,
        })

    def test_connection(self) -> Dict:
        """Test Jira connectivity."""
        return self._get("/jira/test")

    def issues(self, jql: Optional[str] = None) -> Dict:
        """List Jira issues (proxied)."""
        params = {}
        if jql:
            params["jql"] = jql
        return self._get("/jira/issues", params=params)

    def sync_from_jira(self, project_id: Optional[str] = None) -> Dict:
        """Pull Jira issues → create/update Clarive tasks."""
        payload = {}
        if project_id:
            payload["project_id"] = project_id
        return self._post("/jira/sync", json=payload)

    def push_to_jira(self) -> Dict:
        """Push unlinked Clarive tasks → create Jira issues."""
        return self._post("/jira/push")

    def linked_tasks(self) -> Dict:
        """List all tasks with a Jira issue key."""
        return self._get("/jira/linked")


# ── Main client ───────────────────────────────────────────────────────────────

class ClariveClient:
    """
    Main entry point for the Clarive Python SDK.

    Args:
        base_url: Base URL of the Clarive instance, e.g. "https://clarive.example.com"
        token:    JWT access token. If omitted, reads CLARIVE_TOKEN (or legacy NEXUSPM_TOKEN) env variable.
        timeout:  Request timeout in seconds (default: 30).
        verify:   TLS certificate verification (default: True).
    """

    def __init__(
        self,
        base_url: str,
        token: Optional[str] = None,
        timeout: int = 30,
        verify: bool = True,
    ) -> None:
        if not base_url:
            raise ValueError("base_url is required")
        self._base_url = base_url.rstrip("/") + "/api/v1"
        self._token = token or os.environ.get("CLARIVE_TOKEN") or os.environ.get("NEXUSPM_TOKEN", "")
        self._timeout = timeout
        self._verify = verify
        self._session = requests.Session()

        # Resource namespaces
        self.projects     = ProjectsResource(self)
        self.tasks        = TasksResource(self)
        self.imputations  = ImputationsResource(self)
        self.users        = UsersResource(self)
        self.resources    = ResourcesResource(self)
        self.financials   = FinancialsResource(self)
        self.ai           = AIResource(self)
        self.jira         = JiraResource(self)

    def login(self, email: str, password: str) -> str:
        """Authenticate and store the returned JWT token. Returns the token."""
        # Avoid logging the raw password
        data = self._session.post(
            f"{self._base_url}/auth/login",
            json={"email": email, "password": password},
            timeout=self._timeout,
            verify=self._verify,
        )
        self._raise_for_status(data)
        token = data.json().get("access_token", "")
        self._token = token
        return token

    def _request(self, method: str, path: str,
                 params: Optional[Dict] = None,
                 json: Optional[Dict] = None) -> Any:
        url = urljoin(self._base_url + "/", path.lstrip("/"))
        headers: Dict[str, str] = {"Content-Type": "application/json"}
        if self._token:
            headers["Authorization"] = f"Bearer {self._token}"

        response = self._session.request(
            method, url,
            headers=headers,
            params=params,
            json=json,
            timeout=self._timeout,
            verify=self._verify,
        )
        self._raise_for_status(response)
        if response.status_code == 204:
            return {}
        return response.json()

    @staticmethod
    def _raise_for_status(response: Response) -> None:
        if response.status_code < 400:
            return
        try:
            detail = response.json().get("detail", response.text)
        except ValueError:
            detail = response.text
        msg = f"HTTP {response.status_code}: {detail}"
        if response.status_code in (401, 403):
            raise AuthError(msg, response.status_code, response)
        if response.status_code == 404:
            raise NotFoundError(msg, response.status_code, response)
        raise ClariveError(msg, response.status_code, response)


# ── Backwards-compat aliases ──────────────────────────────────────────────────
NexusPMClient = ClariveClient
NexusPMError = ClariveError
