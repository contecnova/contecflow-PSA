"""Tests del dominio collaboration.

Usa las fixtures del conftest (db, client, admin_token).
Cubre flujos críticos: workspace, mensajes, reacciones, pins, saved,
search + operadores, slash commands, llamadas, adjuntos AV/DLP, audit chain,
retention + legal hold, eDiscovery, OAuth providers, push, email digest.
"""
from datetime import datetime, timedelta

import pytest


def _auth_headers(token):
    return {"Authorization": f"Bearer {token}"}


def _conv_id(client, headers):
    body = client.get("/api/v1/collaboration/channels", headers=headers).json()
    chans = body.get("items") if isinstance(body, dict) else body
    return chans[0]["conversation_id"]


def test_workspace_lazy_create(client, admin_token):
    h = _auth_headers(admin_token)
    r = client.get("/api/v1/collaboration/workspace", headers=h)
    assert r.status_code == 200
    body = client.get("/api/v1/collaboration/teams", headers=h).json()
    teams = body.get("items") if isinstance(body, dict) else body
    assert len(teams) == 1


def test_send_edit_delete_message(client, admin_token):
    h = _auth_headers(admin_token)
    client.get("/api/v1/collaboration/workspace", headers=h)
    cid = _conv_id(client, h)
    r = client.post("/api/v1/collaboration/messages", json={"conversation_id": cid, "body": "hola"}, headers=h)
    assert r.status_code == 200
    mid = r.json()["id"]
    _msg_body = client.get(f"/api/v1/collaboration/conversations/{cid}/messages", headers=h).json()
    msgs = _msg_body.get("items") if isinstance(_msg_body, dict) else _msg_body
    assert any(m["id"] == mid for m in msgs)
    r = client.patch(f"/api/v1/collaboration/messages/{mid}", json={"body": "editado"}, headers=h)
    assert r.status_code == 200
    _v_body = client.get(f"/api/v1/collaboration/messages/{mid}/versions", headers=h).json()
    v = _v_body.get("items") if isinstance(_v_body, dict) else _v_body
    assert len(v) == 1
    r = client.delete(f"/api/v1/collaboration/messages/{mid}", headers=h)
    assert r.status_code == 200


def test_reactions_pins_saved(client, admin_token):
    h = _auth_headers(admin_token)
    client.get("/api/v1/collaboration/workspace", headers=h)
    cid = _conv_id(client, h)
    mid = client.post("/api/v1/collaboration/messages", json={"conversation_id": cid, "body": "test"}, headers=h).json()["id"]
    r = client.post(f"/api/v1/collaboration/messages/{mid}/reactions", json={"emoji": "👍"}, headers=h)
    assert r.json()["added"] is True
    client.post(f"/api/v1/collaboration/conversations/{cid}/pins", json={"message_id": mid}, headers=h)
    pins = client.get(f"/api/v1/collaboration/conversations/{cid}/pins", headers=h).json()
    assert any(p["message_id"] == mid for p in pins)
    client.post("/api/v1/collaboration/saved", json={"message_id": mid}, headers=h)
    saved = client.get("/api/v1/collaboration/saved", headers=h).json()["items"]
    assert any(s["message_id"] == mid for s in saved)


def test_search_with_operators(client, admin_token):
    h = _auth_headers(admin_token)
    client.get("/api/v1/collaboration/workspace", headers=h)
    cid = _conv_id(client, h)
    client.post("/api/v1/collaboration/messages", json={"conversation_id": cid, "body": "Bug en home"}, headers=h)
    client.post("/api/v1/collaboration/messages", json={"conversation_id": cid, "body": "doc https://x.com aqui"}, headers=h)
    r = client.get("/api/v1/collaboration/search", params={"q": "home"}, headers=h).json()
    assert r["total"] >= 1
    r = client.get("/api/v1/collaboration/search", params={"q": "has:link"}, headers=h).json()
    assert r["total"] >= 1


def test_saved_searches(client, admin_token):
    h = _auth_headers(admin_token)
    client.get("/api/v1/collaboration/workspace", headers=h)
    r = client.post("/api/v1/collaboration/search/saved", json={"name": "Todo bug", "query": "bug in:general"}, headers=h)
    assert r.status_code == 200
    sid = r.json()["id"]
    saved = client.get("/api/v1/collaboration/search/saved", headers=h).json()
    assert any(s["id"] == sid for s in saved)
    r = client.post(f"/api/v1/collaboration/search/saved/{sid}/run", headers=h)
    assert r.status_code == 200
    client.delete(f"/api/v1/collaboration/search/saved/{sid}", headers=h)


def test_slash_commands(client, admin_token):
    h = _auth_headers(admin_token)
    client.get("/api/v1/collaboration/workspace", headers=h)
    cid = _conv_id(client, h)
    r = client.post("/api/v1/collaboration/slash", json={"conversation_id": cid, "command": "poll", "args": "Q? | A | B"}, headers=h).json()
    assert r["success"]
    r = client.post("/api/v1/collaboration/slash", json={"conversation_id": cid, "command": "decision", "args": "X"}, headers=h).json()
    assert r["success"]
    r = client.post("/api/v1/collaboration/slash", json={"conversation_id": cid, "command": "recap", "args": ""}, headers=h).json()
    assert r["success"]


def test_attachment_av_block(client, admin_token):
    h = _auth_headers(admin_token)
    client.get("/api/v1/collaboration/workspace", headers=h)
    cid = _conv_id(client, h)
    eicar = b"X5O!P%@AP[4\\PZX54(P^)7CC)7}$EICAR-STANDARD-ANTIVIRUS-TEST-FILE!$H+H*"
    r = client.post(
        "/api/v1/collaboration/attachments",
        data={"conversation_id": cid},
        files={"file": ("t.txt", eicar, "text/plain")},
        headers=h,
    )
    body = r.json()
    assert body["av_status"] == "infected"
    assert body["is_quarantined"] is True


def test_attachment_dlp_block(client, admin_token):
    h = _auth_headers(admin_token)
    client.get("/api/v1/collaboration/workspace", headers=h)
    cid = _conv_id(client, h)
    body = b"IBAN: ES7620770024003102575766 transfer me"
    r = client.post(
        "/api/v1/collaboration/attachments",
        data={"conversation_id": cid},
        files={"file": ("n.txt", body, "text/plain")},
        headers=h,
    )
    j = r.json()
    assert j["dlp_status"] == "blocked"


def test_attachment_filename_sanitized_in_storage_key(client, admin_token, db):
    from app.models.collaboration import CollaborationAttachment

    h = _auth_headers(admin_token)
    client.get("/api/v1/collaboration/workspace", headers=h)
    cid = _conv_id(client, h)
    r = client.post(
        "/api/v1/collaboration/attachments",
        data={"conversation_id": cid},
        files={"file": ("../../evil.txt", b"safe-content", "text/plain")},
        headers=h,
    )
    assert r.status_code == 200
    att_id = r.json()["id"]
    att = db.query(CollaborationAttachment).filter(CollaborationAttachment.id == att_id).first()
    assert att is not None
    assert att.name == "evil.txt"
    assert ".." not in att.storage_key
    assert "\\" not in att.storage_key


def test_tus_filename_sanitized_in_storage_key(client, admin_token, db):
    import base64
    from app.models.collaboration import CollaborationAttachment
    from app.models.user import User

    h = _auth_headers(admin_token)
    client.get("/api/v1/collaboration/workspace", headers=h)
    cid = _conv_id(client, h)

    meta = ",".join([
        f"filename {base64.b64encode('../../evil_tus.pdf'.encode()).decode()}",
        f"conversationId {base64.b64encode(cid.encode()).decode()}",
        f"filetype {base64.b64encode('application/pdf'.encode()).decode()}",
    ])

    create = client.post(
        "/api/v1/collaboration/tus",
        headers={
            **h,
            "Tus-Resumable": "1.0.0",
            "Upload-Length": "4",
            "Upload-Metadata": meta,
        },
    )
    assert create.status_code == 201
    location = create.headers.get("Location")
    assert location
    uid = location.rsplit("/", 1)[-1]

    patch = client.patch(
        f"/api/v1/collaboration/tus/{uid}",
        content=b"%PDF",
        headers={
            **h,
            "Tus-Resumable": "1.0.0",
            "Upload-Offset": "0",
            "Content-Type": "application/offset+octet-stream",
        },
    )
    assert patch.status_code == 204

    user = db.query(User).filter(User.username == "admin").first()
    att = (
        db.query(CollaborationAttachment)
        .filter(
            CollaborationAttachment.conversation_id == cid,
            CollaborationAttachment.uploaded_by_user_id == user.id,
            CollaborationAttachment.name == "evil_tus.pdf",
        )
        .order_by(CollaborationAttachment.created_at.desc())
        .first()
    )
    assert att is not None
    assert ".." not in att.storage_key
    assert "\\" not in att.storage_key


def test_call_lifecycle(client, admin_token):
    h = _auth_headers(admin_token)
    client.get("/api/v1/collaboration/workspace", headers=h)
    cid = _conv_id(client, h)
    r = client.post("/api/v1/collaboration/calls/start", json={"conversation_id": cid, "kind": "video"}, headers=h).json()
    assert "livekit_token" in r
    cid_call = r["call_id"]
    client.post(f"/api/v1/collaboration/calls/{cid_call}/leave", headers=h)
    client.post(f"/api/v1/collaboration/calls/{cid_call}/end", headers=h)
    s = client.get(f"/api/v1/collaboration/calls/{cid_call}", headers=h).json()
    assert s["status"] == "ended"


def test_audit_chain(client, admin_token):
    h = _auth_headers(admin_token)
    client.get("/api/v1/collaboration/workspace", headers=h)
    cid = _conv_id(client, h)
    client.post("/api/v1/collaboration/messages", json={"conversation_id": cid, "body": "audit test"}, headers=h)
    res = client.get("/api/v1/collaboration/audit/verify", headers=h).json()
    assert res["is_valid"] is True


def test_retention_run(client, admin_token, db):
    h = _auth_headers(admin_token)
    client.get("/api/v1/collaboration/workspace", headers=h)
    cid = _conv_id(client, h)
    mid = client.post("/api/v1/collaboration/messages", json={"conversation_id": cid, "body": "old"}, headers=h).json()["id"]
    from app.models.collaboration import CollaborationMessage
    m = db.query(CollaborationMessage).filter(CollaborationMessage.id == mid).first()
    m.sent_at = datetime.utcnow() - timedelta(days=400)
    db.commit()
    client.post("/api/v1/collaboration/retention", json={"name": "12m", "retention_months": 12}, headers=h)
    res = client.post("/api/v1/collaboration/retention/run", headers=h).json()
    assert res["deleted"] >= 1


def test_legal_hold_protects(client, admin_token, db):
    h = _auth_headers(admin_token)
    client.get("/api/v1/collaboration/workspace", headers=h)
    cid = _conv_id(client, h)
    mid = client.post("/api/v1/collaboration/messages", json={"conversation_id": cid, "body": "old hold"}, headers=h).json()["id"]
    from app.models.collaboration import CollaborationMessage
    from app.models.user import User
    m = db.query(CollaborationMessage).filter(CollaborationMessage.id == mid).first()
    m.sent_at = datetime.utcnow() - timedelta(days=400)
    user_id = db.query(User).filter(User.username == "admin").first().id
    db.commit()
    client.post("/api/v1/collaboration/legal-holds", json={"case_reference": "C1", "custodian_user_ids": [user_id]}, headers=h)
    client.post("/api/v1/collaboration/retention", json={"name": "12m", "retention_months": 12}, headers=h)
    client.post("/api/v1/collaboration/retention/run", headers=h)
    db.expire_all()
    m = db.query(CollaborationMessage).filter(CollaborationMessage.id == mid).first()
    assert m.status != "deleted"


def test_ediscovery_export(client, admin_token):
    h = _auth_headers(admin_token)
    client.get("/api/v1/collaboration/workspace", headers=h)
    cid = _conv_id(client, h)
    client.post("/api/v1/collaboration/messages", json={"conversation_id": cid, "body": "discovery xx"}, headers=h)
    r = client.post("/api/v1/collaboration/ediscovery/export", json={"keywords": ["discovery"]}, headers=h)
    assert r.status_code == 200
    assert r.json()["total"] >= 1


def test_search_query_parser_unit():
    from app.services.collaboration._search_query import parse
    p = parse("from:admin in:#general before:2026-05-01 has:attachment is:pinned bug")
    assert p.from_author == "admin"
    assert p.in_target == "#general"
    assert p.before is not None
    assert p.has_attachment is True
    assert p.is_pinned is True
    assert "bug" in p.text


def test_oauth_providers(client, admin_token):
    h = _auth_headers(admin_token)
    r = client.get("/api/v1/collaboration/integrations/providers", headers=h).json()
    assert "jira" in r["providers"]
    assert "github" in r["providers"]
    assert "google_calendar" in r["providers"]


def test_email_digest_dry_run(client, admin_token):
    h = _auth_headers(admin_token)
    client.get("/api/v1/collaboration/workspace", headers=h)
    r = client.post("/api/v1/collaboration/admin/email-digest/run", params={"dry_run": True}, headers=h)
    assert r.status_code == 200
    body = r.json()
    assert "sent" in body and "skipped" in body


def test_push_public_key(client, admin_token):
    h = _auth_headers(admin_token)
    r = client.get("/api/v1/collaboration/push/public-key", headers=h).json()
    assert "configured" in r


# ── Tests de las features añadidas en la 2ª ronda ──────────────────────────
def test_mention_suggestions(client, admin_token):
    h = _auth_headers(admin_token)
    client.get("/api/v1/collaboration/workspace", headers=h)
    # query vacío: aparecen los 3 grupos especiales
    r = client.get("/api/v1/collaboration/mention-suggestions", headers=h).json()
    assert "users" in r and "groups" in r
    assert any(g["username"] == "everyone" for g in r["groups"])
    assert any(g["username"] == "channel" for g in r["groups"])


def test_link_message_to_task(client, admin_token, db):
    h = _auth_headers(admin_token)
    client.get("/api/v1/collaboration/workspace", headers=h)
    cid = _conv_id(client, h)
    msg_id = client.post("/api/v1/collaboration/messages", json={"conversation_id": cid, "body": "anchor me"}, headers=h).json()["id"]
    from datetime import date
    from app.models.project import Project, ProjectType, ProjectStatus
    from app.models.task import Task
    p = Project(
        id="test-p", code="TESTP", name="Test", organization_id=1,
        project_type=ProjectType.development, status=ProjectStatus.active,
        start_date=date.today(), created_by="admin-test-id",
    )
    db.add(p); db.commit()
    t = Task(id="task-1", code="T-1", title="x", project_id=p.id, status="todo", priority="medium", created_by="admin-test-id")
    db.add(t); db.commit()
    r = client.post(f"/api/v1/collaboration/messages/{msg_id}/link", json={"kind": "task", "id": t.id}, headers=h)
    assert r.status_code == 200
    msgs = client.get(f"/api/v1/collaboration/conversations/{cid}/messages", headers=h).json()["items"]
    linked = next(m for m in msgs if m["id"] == msg_id)
    assert linked["linked_task_id"] == t.id


def test_link_candidates(client, admin_token, db):
    h = _auth_headers(admin_token)
    client.get("/api/v1/collaboration/workspace", headers=h)
    cid = _conv_id(client, h)
    msg_id = client.post("/api/v1/collaboration/messages", json={"conversation_id": cid, "body": "hi"}, headers=h).json()["id"]
    r = client.get(f"/api/v1/collaboration/messages/{msg_id}/link/candidates", params={"kind": "task"}, headers=h)
    assert r.status_code == 200
    assert isinstance(r.json(), list)


def test_decisions_endpoint(client, admin_token):
    h = _auth_headers(admin_token)
    client.get("/api/v1/collaboration/workspace", headers=h)
    cid = _conv_id(client, h)
    client.post("/api/v1/collaboration/slash", json={"conversation_id": cid, "command": "decision", "args": "Migrar Postgres 16"}, headers=h)
    r = client.get("/api/v1/collaboration/decisions", headers=h)
    assert r.status_code == 200
    items = r.json()["items"]
    assert any("Postgres 16" in (d.get("text") or "") for d in items)


def test_calendar_events_no_providers(client, admin_token):
    h = _auth_headers(admin_token)
    r = client.get("/api/v1/collaboration/calendar/events", headers=h)
    assert r.status_code == 200
    body = r.json()
    assert body["events"] == []


def test_scheduled_message_does_not_notify_immediately(client, admin_token, db):
    """Mensaje programado al futuro: no fan-out de notificaciones inmediato."""
    from datetime import datetime, timedelta
    from app.models.collaboration import CollaborationNotification
    h = _auth_headers(admin_token)
    client.get("/api/v1/collaboration/workspace", headers=h)
    cid = _conv_id(client, h)
    future = (datetime.utcnow() + timedelta(hours=1)).isoformat()
    r = client.post(
        "/api/v1/collaboration/messages",
        json={"conversation_id": cid, "body": "futuro", "scheduled_for": future},
        headers=h,
    )
    assert r.status_code == 200
    msg_id = r.json()["id"]
    notifs = db.query(CollaborationNotification).filter(CollaborationNotification.message_id == msg_id).count()
    assert notifs == 0  # ningún fan-out hasta que el scheduler lo entregue


def test_project_auto_channel(client, admin_token, db):
    """Crear un proyecto debe disparar la creación de un team+canal collaboration."""
    from datetime import date
    from app.models.project import Project, ProjectType, ProjectStatus
    from app.models.collaboration import CollaborationChannel, CollaborationTeam
    from app.services.collaboration._project_sync import on_project_created
    from app.models.user import User

    creator = db.query(User).filter(User.username == "admin").first()
    proj = Project(
        id="auto-p", code="AUTO", name="AutoProj", organization_id=1,
        project_type=ProjectType.development, status=ProjectStatus.active,
        start_date=date.today(), created_by=creator.id,
    )
    db.add(proj); db.commit()
    on_project_created(db, proj, creator)
    db.commit()

    team = db.query(CollaborationTeam).filter(CollaborationTeam.project_id == proj.id).first()
    chan = db.query(CollaborationChannel).filter(CollaborationChannel.project_id == proj.id).first()
    assert team is not None
    assert chan is not None
    assert chan.channel_type == "project"


def test_search_query_advanced_operators():
    from app.services.collaboration._search_query import parse
    p = parse("type:bot is:saved")
    assert p.type_filter == "bot"
    assert p.is_saved is True


def test_permission_cache_invalidation():
    from app.services.collaboration._permissions import _cache_get, _cache_set, invalidate_membership
    _cache_set("team:T1:user-X", True)
    assert _cache_get("team:T1:user-X") is True
    invalidate_membership("user-X")
    assert _cache_get("team:T1:user-X") is None


def test_text_extract_plain_text():
    from app.services.collaboration._text_extract import extract_text
    text = extract_text(b"Hola mundo, este es texto plano.", "test.txt", "text/plain")
    assert "Hola mundo" in text


# ── Tests de bugs cazados en revisión final ─────────────────────────────────
def test_upload_creates_visible_message(client, admin_token):
    """Bug fix: subir archivo sin message_id debe crear un mensaje en la conversación."""
    h = _auth_headers(admin_token)
    client.get("/api/v1/collaboration/workspace", headers=h)
    cid = _conv_id(client, h)
    # Snapshot de mensajes antes
    before = client.get(f"/api/v1/collaboration/conversations/{cid}/messages", headers=h).json()
    # El endpoint devuelve el envelope paginado canónico {"items": [...], "meta": {...}}.
    before_count = len(before["items"])
    # Sube un archivo limpio
    r = client.post(
        "/api/v1/collaboration/attachments",
        data={"conversation_id": cid},
        files={"file": ("plan.txt", b"contenido limpio", "text/plain")},
        headers=h,
    )
    assert r.status_code == 200
    att_id = r.json()["id"]
    # Tras la subida, debe haber un mensaje nuevo tipo "file" con el adjunto enlazado
    after = client.get(f"/api/v1/collaboration/conversations/{cid}/messages", headers=h).json()
    after_items = after["items"]
    assert len(after_items) == before_count + 1
    new_msg = after_items[-1]
    assert new_msg["type"] == "file"
    assert new_msg["has_attachments"] is True
    assert any(a["id"] == att_id for a in new_msg["attachments"])


def test_self_direct_blocked(client, admin_token, db):
    """Bug fix: no se puede abrir un chat directo contigo mismo."""
    from app.models.user import User
    h = _auth_headers(admin_token)
    me = db.query(User).filter(User.username == "admin").first()
    client.get("/api/v1/collaboration/workspace", headers=h)
    r = client.post("/api/v1/collaboration/direct/open", json={"user_id": me.id}, headers=h)
    assert r.status_code == 400


def test_mention_suggestions_excludes_self(client, admin_token):
    """Bug fix: las sugerencias de @mention no deben incluir al usuario actual."""
    h = _auth_headers(admin_token)
    client.get("/api/v1/collaboration/workspace", headers=h)
    r = client.get("/api/v1/collaboration/mention-suggestions", headers=h).json()
    # Ningún user de la lista debe ser el admin actual
    me_in_list = any(u.get("username") == "admin" for u in r["users"])
    assert not me_in_list


def test_signed_url_token_cleanup(db):
    """Defensa contra memory leak: tokens caducados se purgan al firmar nuevos."""
    import time
    from app.services.collaboration._storage import (
        _SIGNED, _purge_expired_signed_tokens, storage,
    )
    _SIGNED.clear()
    # Forzar uno expirado y uno fresco
    storage.signed_url("a/b", ttl_seconds=3600)
    _SIGNED["expired-token"] = {"key": "x", "mode": "download", "expires_at": time.time() - 60}
    assert "expired-token" in _SIGNED
    n = _purge_expired_signed_tokens()
    assert n == 1
    assert "expired-token" not in _SIGNED


def test_push_subscription_purge(db):
    """Las push-subs is_active=False creadas hace > 30 días se eliminan."""
    from datetime import datetime, timedelta
    from app.models.collaboration import CollaborationPushSubscription
    from app.models.user import User
    from app.services.collaboration._push import purge_stale_subscriptions

    me = db.query(User).filter(User.username == "admin").first()
    org = me.organization_id

    # Limpia el estado para no contaminar otras tests
    db.query(CollaborationPushSubscription).delete()
    db.commit()

    db.add(CollaborationPushSubscription(
        organization_id=org, user_id=me.id,
        endpoint="https://stale.example/x", p256dh_key="p", auth_key="a",
        is_active=False, created_at=datetime.utcnow() - timedelta(days=40),
    ))
    db.add(CollaborationPushSubscription(
        organization_id=org, user_id=me.id,
        endpoint="https://recent-deactivated.example/x", p256dh_key="p", auth_key="a",
        is_active=False, created_at=datetime.utcnow() - timedelta(days=2),
    ))
    db.add(CollaborationPushSubscription(
        organization_id=org, user_id=me.id,
        endpoint="https://active.example/x", p256dh_key="p", auth_key="a",
        is_active=True, created_at=datetime.utcnow() - timedelta(days=40),
    ))
    db.commit()

    n = purge_stale_subscriptions(db, days=30)
    assert n == 1
    remaining_endpoints = {
        s.endpoint for s in db.query(CollaborationPushSubscription).all()
    }
    assert "https://stale.example/x" not in remaining_endpoints
    assert "https://recent-deactivated.example/x" in remaining_endpoints
    assert "https://active.example/x" in remaining_endpoints


def test_audit_chain_lock_present_and_per_org():
    """El lock por-org existe y es reentrante por el mismo hilo dentro de una
    misma org; instancias independientes para orgs distintas."""
    from app.services.collaboration._audit import _lock_for
    lock_a = _lock_for("org-a")
    lock_b = _lock_for("org-b")
    assert lock_a is not None and lock_b is not None
    # Misma org → mismo objeto lock (idempotente)
    assert _lock_for("org-a") is lock_a
    # Org distinta → lock distinto (no se serializan entre sí)
    assert lock_a is not lock_b


def test_per_conversation_mute_silences_notifications(client, admin_token, pm_token, db):
    """Bug fix: una rule scope=conversation con notify_messages=none silencia
    notificaciones para esa conversación. Las menciones (everyone) rompen el silencio."""
    from app.models.user import User
    from app.models.collaboration import CollaborationNotification
    h_admin = _auth_headers(admin_token)
    h_pm = _auth_headers(pm_token)
    client.get("/api/v1/collaboration/workspace", headers=h_admin)
    client.get("/api/v1/collaboration/workspace", headers=h_pm)

    pm = db.query(User).filter(User.username == "pm_test").first()

    # 1) Admin abre directo con PM
    r = client.post(
        "/api/v1/collaboration/direct/open",
        json={"user_id": pm.id}, headers=h_admin,
    )
    assert r.status_code == 200
    conv_id = r.json()["conversation_id"]

    # 2) PM silencia esa conversación
    r = client.put(
        "/api/v1/collaboration/notification-rules",
        json={"scope": "conversation", "target_id": conv_id,
              "notify_messages": "none", "desktop_push": False, "email_digest": "weekly"},
        headers=h_pm,
    )
    assert r.status_code == 200, r.text

    # Limpiar notificaciones previas del PM
    db.query(CollaborationNotification).filter(
        CollaborationNotification.user_id == pm.id,
    ).delete()
    db.commit()

    # 3) Admin envía mensaje normal — PM NO debe recibir notificación
    r = client.post(
        "/api/v1/collaboration/messages",
        json={"conversation_id": conv_id, "body": "hola en silencio"}, headers=h_admin,
    )
    assert r.status_code == 200
    pm_notifs = db.query(CollaborationNotification).filter(
        CollaborationNotification.user_id == pm.id,
        CollaborationNotification.conversation_id == conv_id,
    ).count()
    assert pm_notifs == 0, "Mute scope=conversation debería bloquear notificación normal"

    # 4) Admin envía mensaje con @everyone — PM SÍ debe recibir mención
    r = client.post(
        "/api/v1/collaboration/messages",
        json={"conversation_id": conv_id, "body": "atención @everyone", "is_everyone": True},
        headers=h_admin,
    )
    assert r.status_code == 200
    pm_mentions = db.query(CollaborationNotification).filter(
        CollaborationNotification.user_id == pm.id,
        CollaborationNotification.conversation_id == conv_id,
        CollaborationNotification.kind == "mention",
    ).count()
    assert pm_mentions == 1, "Las menciones deben romper el silencio"


def test_conversations_include_unread_count_and_mark_all_read_updates_it(client, admin_token, pm_token, db):
    from app.models.user import User

    h_admin = _auth_headers(admin_token)
    h_pm = _auth_headers(pm_token)

    client.get("/api/v1/collaboration/workspace", headers=h_admin)
    client.get("/api/v1/collaboration/workspace", headers=h_pm)

    # Abrimos un directo admin <-> pm y enviamos un mensaje al PM para generar notificación.
    pm = db.query(User).filter(User.username == "pm_test").first()
    assert pm is not None
    direct = client.post(
        "/api/v1/collaboration/direct/open",
        json={"user_id": pm.id},
        headers=h_admin,
    )
    assert direct.status_code == 200
    conv_id = direct.json()["conversation_id"]

    sent = client.post(
        "/api/v1/collaboration/messages",
        json={"conversation_id": conv_id, "body": "mensaje no leido"},
        headers=h_admin,
    )
    assert sent.status_code == 200

    convs_pm = client.get("/api/v1/collaboration/conversations", headers=h_pm)
    assert convs_pm.status_code == 200
    row = next(c for c in convs_pm.json() if c["id"] == conv_id)
    assert row.get("unread_count", 0) >= 1

    mark = client.post("/api/v1/collaboration/notifications/mark-all-read", headers=h_pm)
    assert mark.status_code == 200

    convs_pm_after = client.get("/api/v1/collaboration/conversations", headers=h_pm)
    assert convs_pm_after.status_code == 200
    row_after = next(c for c in convs_pm_after.json() if c["id"] == conv_id)
    assert row_after.get("unread_count", 0) == 0


def test_mark_read_clears_conversation_unread_count_immediately(client, admin_token, pm_token, db):
    from app.models.user import User

    h_admin = _auth_headers(admin_token)
    h_pm = _auth_headers(pm_token)

    client.get("/api/v1/collaboration/workspace", headers=h_admin)
    client.get("/api/v1/collaboration/workspace", headers=h_pm)

    pm = db.query(User).filter(User.username == "pm_test").first()
    assert pm is not None

    direct = client.post(
        "/api/v1/collaboration/direct/open",
        json={"user_id": pm.id},
        headers=h_admin,
    )
    assert direct.status_code == 200
    conv_id = direct.json()["conversation_id"]

    sent = client.post(
        "/api/v1/collaboration/messages",
        json={"conversation_id": conv_id, "body": "mensaje pendiente"},
        headers=h_admin,
    )
    assert sent.status_code == 200
    mid = sent.json()["id"]

    before = client.get("/api/v1/collaboration/conversations", headers=h_pm)
    assert before.status_code == 200
    before_row = next(c for c in before.json() if c["id"] == conv_id)
    assert before_row.get("unread_count", 0) >= 1

    mark = client.post(
        f"/api/v1/collaboration/conversations/{conv_id}/read",
        json={"last_message_id": mid},
        headers=h_pm,
    )
    assert mark.status_code == 200

    after = client.get("/api/v1/collaboration/conversations", headers=h_pm)
    assert after.status_code == 200
    after_row = next(c for c in after.json() if c["id"] == conv_id)
    assert after_row.get("unread_count", 0) == 0


def test_group_add_and_remove_members(client, admin_token, pm_token, dev_token, db):
    """Bug fix: se pueden añadir y quitar miembros de un grupo ya creado."""
    from app.models.user import User
    h_admin = _auth_headers(admin_token)
    client.get("/api/v1/collaboration/workspace", headers=h_admin)

    pm = db.query(User).filter(User.username == "pm_test").first()
    dev = db.query(User).filter(User.username == "dev_test").first()

    # 1) Admin crea un grupo solo con el PM
    r = client.post(
        "/api/v1/collaboration/groups",
        json={"title": "Equipo de prueba", "user_ids": [pm.id], "client_user_ids": []},
        headers=h_admin,
    )
    assert r.status_code == 200
    conv_id = r.json()["conversation_id"]

    # 2) Listar miembros: deben ser admin + pm (2)
    r = client.get(f"/api/v1/collaboration/conversations/{conv_id}/members", headers=h_admin)
    assert r.status_code == 200
    members = r.json()
    user_ids = {m["user_id"] for m in members if m.get("user_id")}
    assert pm.id in user_ids
    # admin auto-incluido al crear
    me = db.query(User).filter(User.username == "admin").first()
    assert me.id in user_ids

    # 3) Añadir al dev
    r = client.post(
        f"/api/v1/collaboration/conversations/{conv_id}/members",
        json={"user_ids": [dev.id]},
        headers=h_admin,
    )
    assert r.status_code == 200, r.text
    assert r.json()["added"] == 1

    # 4) Listar de nuevo: ahora 3
    r = client.get(f"/api/v1/collaboration/conversations/{conv_id}/members", headers=h_admin)
    user_ids = {m["user_id"] for m in r.json() if m.get("user_id")}
    assert dev.id in user_ids
    assert len(user_ids) == 3

    # 5) Re-añadir el mismo dev: idempotente, devuelve added=0
    r = client.post(
        f"/api/v1/collaboration/conversations/{conv_id}/members",
        json={"user_ids": [dev.id]},
        headers=h_admin,
    )
    assert r.status_code == 200
    assert r.json()["added"] == 0

    # 6) Un no-admin no puede expulsar a otro
    h_pm = _auth_headers(pm_token)
    r = client.delete(
        f"/api/v1/collaboration/conversations/{conv_id}/members/{dev.id}",
        headers=h_pm,
    )
    assert r.status_code == 403

    # 7) El admin sí puede
    r = client.delete(
        f"/api/v1/collaboration/conversations/{conv_id}/members/{dev.id}",
        headers=h_admin,
    )
    assert r.status_code == 200

    # 8) Cualquier miembro puede salirse a sí mismo
    h_dev = _auth_headers(dev_token)
    # Re-añadir al dev primero
    client.post(
        f"/api/v1/collaboration/conversations/{conv_id}/members",
        json={"user_ids": [dev.id]},
        headers=h_admin,
    )
    r = client.delete(
        f"/api/v1/collaboration/conversations/{conv_id}/members/{dev.id}",
        headers=h_dev,
    )
    assert r.status_code == 200

    # 9) No se permite añadir miembros a un canal vía esta ruta
    workspace = client.get("/api/v1/collaboration/workspace", headers=h_admin).json()
    # /teams devuelve el envelope paginado canónico {"items": [...], "meta": {...}}.
    teams = client.get("/api/v1/collaboration/teams", headers=h_admin).json()["items"]
    if teams:
        ch = client.post(
            "/api/v1/collaboration/channels",
            json={"team_id": teams[0]["id"], "name": "test-add-block", "channel_type": "public"},
            headers=h_admin,
        ).json()
        ch_conv_id = ch["conversation_id"]
        r = client.post(
            f"/api/v1/collaboration/conversations/{ch_conv_id}/members",
            json={"user_ids": [dev.id]},
            headers=h_admin,
        )
        assert r.status_code == 400
    assert workspace

