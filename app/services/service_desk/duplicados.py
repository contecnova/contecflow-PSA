"""Candidatos a duplicado de un ticket (mejoras de mercado 16-11-2026).

`POST /sd/tickets/{id}/deduplicate` solo reconocia el duplicado exacto de una
alerta (mismo CI, categoria y prioridad). El agente necesita ver los tickets
*parecidos* de su empresa para decidir si fusionar: este modulo los puntua por
el texto (titulo y descripcion) y por lo que comparten (solicitante, CI,
servicio del catalogo) y explica por que salen.

La fusion es la de siempre (`POST /sd/tickets/{destino}/merge`); aqui solo se
proponen candidatos. Los umbrales son ajustes por empresa:

* `SD_DUPLICATE_WINDOW_DAYS`: dias hacia atras desde la apertura del ticket.
* `SD_DUPLICATE_MIN_SIMILARITY`: puntuacion minima (0-1) para proponerlo.
* `SD_DUPLICATE_MAX_CANDIDATES`: cuantos se devuelven como mucho.
"""
from __future__ import annotations

import re
import unicodedata
from datetime import timedelta

from sqlalchemy.orm import Session

from app.models.service_desk import Ticket
from app.models.service_desk._enums import TicketStatus
from app.models.user import User
from app.services.service_desk.scoping import get_scoped_ticket_or_404, scope_ticket_query

#: Tickets como mucho que se comparan por peticion (los mas recientes de la ventana).
TOPE_DE_COMPARACION = 500

#: Lo que suma a la puntuacion compartir cada dato. Son pesos del modelo, no
#: umbrales de negocio: el umbral que decide es `SD_DUPLICATE_MIN_SIMILARITY`.
PESOS = {"same_requester": 0.15, "same_ci": 0.20, "same_service": 0.10}

_PALABRA = re.compile(r"[a-z0-9]{3,}")


def _normalizar(texto: str) -> set[str]:
    sin_tildes = unicodedata.normalize("NFD", (texto or "").lower())
    sin_tildes = "".join(c for c in sin_tildes if unicodedata.category(c) != "Mn")
    return set(_PALABRA.findall(sin_tildes))


def similitud_de_texto(a: str, b: str) -> float:
    """Jaccard de las palabras de tres letras o mas (sin tildes ni mayusculas)."""
    pa, pb = _normalizar(a), _normalizar(b)
    if not pa or not pb:
        return 0.0
    return len(pa & pb) / len(pa | pb)


def _ajustes(db: Session, org_id) -> tuple[int, float, int]:
    from app.services import settings_service as s
    return (
        int(s.get_runtime_int(db, "SD_DUPLICATE_WINDOW_DAYS", org_id) or 0),
        float(s.get_runtime_float(db, "SD_DUPLICATE_MIN_SIMILARITY", org_id) or 0),
        int(s.get_runtime_int(db, "SD_DUPLICATE_MAX_CANDIDATES", org_id) or 0),
    )


def _texto(t: Ticket) -> str:
    return f"{t.title or ''} {t.description or ''}"


def puntuar(origen: Ticket, otro: Ticket) -> tuple[float, list[str]]:
    texto = similitud_de_texto(_texto(origen), _texto(otro))
    motivos = ["similar_text"] if texto > 0 else []
    puntos = texto
    if origen.requester_user_id and origen.requester_user_id == otro.requester_user_id \
            or origen.requester_client_id and origen.requester_client_id == otro.requester_client_id:
        puntos += PESOS["same_requester"]
        motivos.append("same_requester")
    if origen.ci_id and origen.ci_id == otro.ci_id:
        puntos += PESOS["same_ci"]
        motivos.append("same_ci")
    if origen.service_item_id and origen.service_item_id == otro.service_item_id:
        puntos += PESOS["same_service"]
        motivos.append("same_service")
    return min(1.0, round(puntos, 4)), motivos


def candidatos_a_duplicado(db: Session, current_user: User, ticket_id: str) -> dict:
    """Los tickets de la empresa que se parecen a este, del mas al menos parecido.

    Solo los que quien pregunta puede ver (misma regla que el listado) y que no
    estan cancelados: uno cancelado ya no es el original de nada.
    """
    ticket = get_scoped_ticket_or_404(db, current_user, ticket_id)
    dias, minimo, maximo = _ajustes(db, ticket.organization_id)
    q = scope_ticket_query(db.query(Ticket), db, current_user).filter(
        Ticket.id != ticket.id,
        Ticket.status != TicketStatus.cancelled,
    )
    if ticket.organization_id is not None:
        q = q.filter(Ticket.organization_id == ticket.organization_id)
    if dias > 0 and ticket.created_at is not None:
        q = q.filter(Ticket.created_at >= ticket.created_at - timedelta(days=dias))
    otros = q.order_by(Ticket.created_at.desc()).limit(TOPE_DE_COMPARACION).all()

    puntuados = []
    for otro in otros:
        puntos, motivos = puntuar(ticket, otro)
        if puntos >= minimo and "similar_text" in motivos:
            puntuados.append({
                "id": otro.id, "number": otro.number, "title": otro.title,
                "status": getattr(otro.status, "value", otro.status),
                "priority": getattr(otro.priority, "value", otro.priority),
                "created_at": otro.created_at.isoformat() if otro.created_at else None,
                "score": puntos, "reasons": motivos,
            })
    puntuados.sort(key=lambda c: c["score"], reverse=True)
    return {
        "ticket_id": ticket.id, "ticket_number": ticket.number,
        "min_similarity": minimo, "window_days": dias,
        "candidates": puntuados[:maximo] if maximo > 0 else puntuados,
    }
