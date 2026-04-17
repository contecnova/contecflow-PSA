"""
Service helpers for Microsoft 365 integration endpoints.
Encapsulates database queries used by the m365 router.
"""
import httpx
from datetime import date
from typing import List

from sqlalchemy.orm import Session
from app.core.config import settings
from app.models.financial import ProjectMilestone
from app.models.task import Task
from fastapi import HTTPException

GRAPH_BASE = "https://graph.microsoft.com/v1.0"


def m365_configured() -> bool:
    return bool(settings.AZURE_TENANT_ID and settings.AZURE_CLIENT_ID and settings.AZURE_CLIENT_SECRET)


def require_m365() -> None:
    if not m365_configured():
        raise HTTPException(503, detail={
            "error": "M365_NOT_CONFIGURED",
            "message": "Configura las variables de entorno: AZURE_TENANT_ID, AZURE_CLIENT_ID, AZURE_CLIENT_SECRET",
            "docs_url": "https://learn.microsoft.com/en-us/graph/auth-v2-service",
        })


async def get_graph_token() -> str:
    url = f"https://login.microsoftonline.com/{settings.AZURE_TENANT_ID}/oauth2/v2.0/token"
    data = {
        "grant_type": "client_credentials",
        "client_id": settings.AZURE_CLIENT_ID,
        "client_secret": settings.AZURE_CLIENT_SECRET,
        "scope": "https://graph.microsoft.com/.default",
    }
    async with httpx.AsyncClient(timeout=15) as client:
        resp = await client.post(url, data=data)
    if resp.status_code != 200:
        raise HTTPException(502, "Error obteniendo token de Azure AD")
    return resp.json()["access_token"]


def get_graph_token_sync() -> str:
    url = f"https://login.microsoftonline.com/{settings.AZURE_TENANT_ID}/oauth2/v2.0/token"
    data = {
        "grant_type": "client_credentials",
        "client_id": settings.AZURE_CLIENT_ID,
        "client_secret": settings.AZURE_CLIENT_SECRET,
        "scope": "https://graph.microsoft.com/.default",
    }
    with httpx.Client(timeout=15) as client:
        resp = client.post(url, data=data)
    if resp.status_code != 200:
        raise HTTPException(502, "Error obteniendo token de Azure AD")
    return resp.json()["access_token"]


async def graph_get(path: str) -> dict:
    token = await get_graph_token()
    async with httpx.AsyncClient(timeout=20) as client:
        resp = await client.get(f"{GRAPH_BASE}{path}", headers={"Authorization": f"Bearer {token}"})
    resp.raise_for_status()
    return resp.json()


async def graph_post(path: str, payload: dict) -> dict:
    token = await get_graph_token()
    async with httpx.AsyncClient(timeout=20) as client:
        resp = await client.post(f"{GRAPH_BASE}{path}", json=payload, headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"})
    resp.raise_for_status()
    return resp.json()


async def graph_patch(path: str, payload: dict) -> dict:
    token = await get_graph_token()
    async with httpx.AsyncClient(timeout=20) as client:
        resp = await client.patch(f"{GRAPH_BASE}{path}", json=payload, headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"})
    resp.raise_for_status()
    return resp.json()


async def graph_delete(path: str) -> None:
    token = await get_graph_token()
    async with httpx.AsyncClient(timeout=20) as client:
        resp = await client.delete(f"{GRAPH_BASE}{path}", headers={"Authorization": f"Bearer {token}"})
    if resp.status_code not in (200, 204):
        resp.raise_for_status()


def graph_get_sync(path: str) -> dict:
    token = get_graph_token_sync()
    with httpx.Client(timeout=20) as client:
        resp = client.get(f"{GRAPH_BASE}{path}", headers={"Authorization": f"Bearer {token}"})
    resp.raise_for_status()
    return resp.json()


def graph_post_sync(path: str, payload: dict) -> dict:
    token = get_graph_token_sync()
    with httpx.Client(timeout=20) as client:
        resp = client.post(f"{GRAPH_BASE}{path}", json=payload, headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"})
    resp.raise_for_status()
    return resp.json()


def get_upcoming_milestones(db: Session, cutoff: date, limit: int = 50) -> list:
    """Return milestones with due_date up to cutoff."""
    return (
        db.query(ProjectMilestone)
        .filter(ProjectMilestone.due_date <= cutoff)
        .limit(limit)
        .all()
    )


def get_active_tasks_for_project(db: Session, project_id: str, limit: int = 200) -> list:
    """Return non-terminal tasks for a project."""
    return (
        db.query(Task)
        .filter(
            Task.project_id == project_id,
            Task.status.notin_(["done", "cancelled", "closed"]),
        )
        .limit(limit)
        .all()
    )
