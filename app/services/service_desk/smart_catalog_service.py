"""
Smart Service Catalog Service — Fase 3 ITSM Scale
==================================================
Sprint 21-22: Catálogo de servicios inteligente con recomendaciones IA,
popularidad, y sugerencias de formulario dinámico.

Capacidades:
  1. get_smart_recommendations()  — sugiere servicios relevantes al usuario
     basándose en histórico, rol y keywords del problema.
  2. get_popular_services()       — servicios más solicitados en las últimas N semanas.
  3. enrich_catalog_with_stats()  — añade métricas de uso a la respuesta del catálogo.
  4. suggest_service_for_query()  — dado un texto libre, recomienda el servicio
     más apropiado (keyword-match + IA fallback).
  5. update_service_popularity()  — Celery task que recalcula conteos periódicamente.
  6. auto_prefill_request_form()  — pre-rellena campos de formulario a partir de
     la descripción del usuario.
"""
from __future__ import annotations

import json
import logging
from collections import Counter
from datetime import datetime, timedelta, timezone
from typing import Optional

from sqlalchemy import func
from sqlalchemy.orm import Session, joinedload

from app.models.service_desk import (
    ServiceCategory,
    ServiceItem,
    Ticket,
    TicketType,
)

logger = logging.getLogger(__name__)

# ── Popularity window ─────────────────────────────────────────────────────────
_POPULARITY_WEEKS = 4


# ── Helpers ───────────────────────────────────────────────────────────────────

def _text_score(text: str, keywords: list[str]) -> int:
    """Case-insensitive keyword hit count."""
    t = text.lower()
    return sum(1 for kw in keywords if kw.lower() in t)


def _get_all_active_services(db: Session) -> list[ServiceItem]:
    return (
        db.query(ServiceItem)
        .filter(ServiceItem.is_active.is_(True))
        .options(joinedload(ServiceItem.category))
        .all()
    )


# ── Popularity ────────────────────────────────────────────────────────────────

def get_popular_services(db: Session, weeks: int = _POPULARITY_WEEKS, limit: int = 10) -> list[dict]:
    """Return top *limit* service items by ticket volume in last *weeks* weeks.

    Returns::

        [{"service_id", "service_name", "category_name", "ticket_count", "avg_csat"}, ...]
    """
    since = datetime.now(tz=timezone.utc) - timedelta(weeks=weeks)

    rows = (
        db.query(
            Ticket.service_item_id,
            func.count(Ticket.id).label("ticket_count"),
            func.avg(Ticket.csat_score).label("avg_csat"),
        )
        .filter(
            Ticket.service_item_id.isnot(None),
            Ticket.created_at >= since,
        )
        .group_by(Ticket.service_item_id)
        .order_by(func.count(Ticket.id).desc())
        .limit(limit)
        .all()
    )

    result = []
    for service_id, count, avg_csat in rows:
        svc = db.query(ServiceItem).filter(ServiceItem.id == service_id).first()
        if svc:
            result.append({
                "service_id": service_id,
                "service_name": svc.name,
                "category_name": svc.category.name if svc.category else None,
                "ticket_count": count,
                "avg_csat": round(avg_csat, 2) if avg_csat else None,
            })

    return result


def update_service_popularity(db: Session) -> dict:
    """Recalculate popularity scores and write them to ServiceItem.popularity_score.

    Only writes if the column exists (Phase 3 migration required).
    Does NOT commit — caller must commit.

    Returns:
        {"updated": N, "top_service": str}
    """
    popular = get_popular_services(db, weeks=_POPULARITY_WEEKS, limit=999)

    max_count = popular[0]["ticket_count"] if popular else 1
    updated = 0
    top_service = popular[0]["service_name"] if popular else ""

    for entry in popular:
        svc = db.query(ServiceItem).filter(ServiceItem.id == entry["service_id"]).first()
        if svc and hasattr(svc, "popularity_score"):
            # Normalize 0-100
            svc.popularity_score = round(entry["ticket_count"] / max_count * 100, 1)
            updated += 1

    db.flush()
    return {"updated": updated, "top_service": top_service}


# ── User-specific recommendations ────────────────────────────────────────────

def get_smart_recommendations(
    db: Session,
    user_id: str,
    query: Optional[str] = None,
    limit: int = 5,
) -> list[dict]:
    """Suggest service items most relevant to *user_id* and optional *query* text.

    Logic (layered):
      1. Services the user has requested before (personal history)
      2. Popular services matching query keywords
      3. All active services scored by query keyword match

    Returns::

        [{"service_id", "service_name", "category_name", "reason", "score"}, ...]
    """
    services = _get_all_active_services(db)

    # ── 1. Personal history ────────────────────────────────────────────────────
    personal_counts: Counter = Counter()
    user_tickets = (
        db.query(Ticket.service_item_id)
        .filter(
            Ticket.requester_user_id == user_id,
            Ticket.service_item_id.isnot(None),
        )
        .limit(200)
        .all()
    )
    for (sid,) in user_tickets:
        personal_counts[sid] += 1

    # ── 2. Score each service ─────────────────────────────────────────────────
    scored: list[tuple[float, ServiceItem, str]] = []

    for svc in services:
        score: float = 0.0
        reason = "Disponible en el catálogo"

        # Personal history bonus
        personal_hits = personal_counts.get(svc.id, 0)
        if personal_hits:
            score += min(40.0, personal_hits * 8.0)
            reason = f"Lo has solicitado {personal_hits} vez/veces"

        # Keyword match on query
        if query:
            search_text = f"{svc.name} {svc.description or ''}"
            query_keywords = query.split()
            hits = _text_score(search_text, query_keywords)
            if hits:
                score += hits * 15.0
                reason = f"Coincide con tu búsqueda ({hits} términos)"

        # Popularity bonus (if column exists)
        if hasattr(svc, "popularity_score") and svc.popularity_score:
            score += float(svc.popularity_score) * 0.3

        scored.append((score, svc, reason))

    scored.sort(key=lambda x: -x[0])

    return [
        {
            "service_id": svc.id,
            "service_name": svc.name,
            "category_name": svc.category.name if svc.category else None,
            "ticket_type": str(svc.ticket_type),
            "default_priority": str(svc.default_priority),
            "requires_approval": svc.requires_approval,
            "reason": reason,
            "score": round(sc, 1),
        }
        for sc, svc, reason in scored[:limit]
        if sc > 0 or not query
    ]


# ── AI-based service suggestion from free text ────────────────────────────────

def suggest_service_for_query(
    db: Session,
    query: str,
    use_ai: bool = True,
) -> dict:
    """Given free-text *query*, return the best matching service + reasoning.

    Tries keyword match first (fast, no AI cost). Falls back to AI if enabled
    and no clear match found.

    Returns::

        {
          "service_id": str | None,
          "service_name": str | None,
          "category_name": str | None,
          "confidence": "high"|"medium"|"low",
          "method": "keyword"|"ai"|"none",
          "alternatives": [...]  # up to 3 other options
        }
    """
    services = _get_all_active_services(db)
    query_words = query.lower().split()

    keyword_scored: list[tuple[int, ServiceItem]] = []
    for svc in services:
        search_text = f"{svc.name} {svc.description or ''}".lower()
        hits = sum(1 for w in query_words if w in search_text)
        if hits:
            keyword_scored.append((hits, svc))

    keyword_scored.sort(key=lambda x: -x[0])

    if keyword_scored and keyword_scored[0][0] >= 2:
        best = keyword_scored[0][1]
        alternatives = [
            {"service_id": s.id, "service_name": s.name}
            for _, s in keyword_scored[1:4]
        ]
        return {
            "service_id": best.id,
            "service_name": best.name,
            "category_name": best.category.name if best.category else None,
            "confidence": "high" if keyword_scored[0][0] >= 3 else "medium",
            "method": "keyword",
            "alternatives": alternatives,
        }

    # AI fallback
    if use_ai and services:
        try:
            from app.services.ai_provider_service import call_ai  # noqa: PLC0415

            catalog_summary = "\n".join(
                f"- {svc.id}: {svc.name} ({svc.description or ''})"
                for svc in services[:40]
            )
            system_prompt = (
                "Eres un asistente de soporte IT. A continuación tienes una lista de servicios "
                "disponibles en el catálogo (id: nombre — descripción). "
                "Devuelve SOLO el id del servicio más apropiado para la consulta del usuario, "
                "sin texto adicional."
            )
            messages = [
                {
                    "role": "user",
                    "content": f"Catálogo:\n{catalog_summary}\n\nConsulta: {query}",
                }
            ]
            ai_id = (call_ai(db, messages=messages, system=system_prompt, max_tokens=60) or "").strip()

            matched = next((s for s in services if s.id == ai_id), None)
            if matched:
                return {
                    "service_id": matched.id,
                    "service_name": matched.name,
                    "category_name": matched.category.name if matched.category else None,
                    "confidence": "medium",
                    "method": "ai",
                    "alternatives": [],
                }
        except Exception as exc:  # noqa: BLE001
            logger.warning("suggest_service_for_query AI call failed: %s", exc)

    # Low-confidence fallback
    if keyword_scored:
        best = keyword_scored[0][1]
        return {
            "service_id": best.id,
            "service_name": best.name,
            "category_name": best.category.name if best.category else None,
            "confidence": "low",
            "method": "keyword",
            "alternatives": [],
        }

    return {
        "service_id": None,
        "service_name": None,
        "category_name": None,
        "confidence": "low",
        "method": "none",
        "alternatives": [],
    }


# ── Auto-prefill form ─────────────────────────────────────────────────────────

def auto_prefill_request_form(
    db: Session,
    description: str,
    service_id: Optional[str] = None,
) -> dict:
    """Pre-fill ticket creation form fields based on free-text description.

    Uses pattern matching + optional AI to suggest title, priority, and
    custom field values.

    Returns::

        {
          "suggested_title": str,
          "suggested_priority": str,
          "suggested_urgency": str,
          "custom_fields": dict,
          "method": "pattern"|"ai",
        }
    """
    # Pattern-based priority hints
    priority = "p3_medium"
    urgency = "u3_medium"

    desc_lower = description.lower()

    # Critical signals
    if any(w in desc_lower for w in ("urgente", "urgent", "producción caída", "caída total",
                                      "down", "fuera de servicio", "p1", "bloqueando")):
        priority = "p1_critical"
        urgency = "u1_critical"
    elif any(w in desc_lower for w in ("importante", "impacto alto", "p2", "afecta al equipo",
                                        "muchos usuarios")):
        priority = "p2_high"
        urgency = "u2_high"
    elif any(w in desc_lower for w in ("cuando puedas", "no urgente", "baja prioridad", "p4")):
        priority = "p4_low"
        urgency = "u4_low"

    # Title: first sentence / first 100 chars
    first_sentence = description.split(".")[0].strip()[:100]
    suggested_title = first_sentence or description[:80]

    # Custom fields from service definition
    custom_fields: dict = {}
    if service_id:
        svc = db.query(ServiceItem).filter(ServiceItem.id == service_id).first()
        if svc and svc.custom_fields:
            try:
                schema = json.loads(svc.custom_fields)
                # Pre-fill fields where we can infer values
                for field in schema if isinstance(schema, list) else []:
                    fname = field.get("name", "")
                    if "nombre" in fname.lower() or "name" in fname.lower():
                        custom_fields[fname] = ""
            except (json.JSONDecodeError, TypeError):
                pass

    return {
        "suggested_title": suggested_title,
        "suggested_priority": priority,
        "suggested_urgency": urgency,
        "custom_fields": custom_fields,
        "method": "pattern",
    }


# ── Catalog enriched with stats ───────────────────────────────────────────────

def enrich_catalog_with_stats(
    db: Session,
    catalog: list[dict],
    weeks: int = _POPULARITY_WEEKS,
) -> list[dict]:
    """Add ``ticket_count`` and ``avg_csat`` stats to each service in *catalog*.

    *catalog* is the list returned by ``catalog_service.list_catalog_payload``.

    Returns mutated catalog (same structure, services have extra keys).
    """
    popular = get_popular_services(db, weeks=weeks, limit=999)
    stats_by_id = {p["service_id"]: p for p in popular}

    for category in catalog:
        for svc in category.get("services", []):
            stats = stats_by_id.get(svc["id"], {})
            svc["ticket_count_recent"] = stats.get("ticket_count", 0)
            svc["avg_csat_recent"] = stats.get("avg_csat")

    return catalog
