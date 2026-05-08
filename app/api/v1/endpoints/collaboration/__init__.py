"""Collaboration API package — Teams-like internal chat.

Sub-routers:
  workspaces    — workspace, teams, channels, members, conversations, presence, drafts, search, notifications
  messages      — messages CRUD, threads, reactions, mentions, reads, pins, saved
  files         — attachments (multipart, AV/DLP, signed downloads, previews)
  calls         — voice/video via LiveKit, recordings, transcripts
  bots          — bots + slash commands + integrations
  compliance    — retention policies, legal hold, audit, eDiscovery export
  ws            — websocket gateway (realtime events)
"""
from fastapi import APIRouter

from app.api.v1.endpoints.collaboration import (
    workspaces as ws_ep,
    messages as msg_ep,
    files as files_ep,
    calls as calls_ep,
    bots as bots_ep,
    compliance as comp_ep,
    ws as ws_gw,
    tus as tus_ep,
    admin as admin_ep,
)

router = APIRouter()
router.include_router(ws_ep.router)
router.include_router(msg_ep.router)
router.include_router(files_ep.router)
router.include_router(calls_ep.router)
router.include_router(bots_ep.router)
router.include_router(comp_ep.router)
router.include_router(tus_ep.router)
router.include_router(admin_ep.router)
router.include_router(ws_gw.router)
