"""Busquedas guardadas y sugerencias de mencion.

Parte de `app.services.collaboration.workspaces` (auditoria 2026-11, #24): se partio por responsabilidad
sin cambiar el codigo. El paquete reexporta todos los nombres.
"""
from __future__ import annotations

from typing import Optional
from sqlalchemy import or_, func
from sqlalchemy.orm import Session
from app.models.collaboration import CollaborationChannel, CollaborationTeamMember
from app.core.timeutil import utcnow
from app.models.user import User
from app.services.collaboration._permissions import _org
from app.core.errores import ErrorDeDominio


# ── Busquedas guardadas ──────────────────────────────────────────────────────

def list_saved_searches(db: Session, user) -> list[dict]:
    """Las busquedas guardadas: primero las fijadas, luego por uso reciente.

    `nullslast()` importa: una busqueda guardada y nunca usada tiene
    `last_used_at` a nulo, y sin eso quedaria arriba en algunos motores y abajo
    en otros.
    """
    from app.models.collaboration import CollaborationSavedSearch

    filas = (
        db.query(CollaborationSavedSearch)
        .filter(CollaborationSavedSearch.user_id == user.id)
        .order_by(
            CollaborationSavedSearch.is_pinned.desc(),
            CollaborationSavedSearch.last_used_at.desc().nullslast(),
        )
        .all()
    )
    return [
        {
            "id": r.id, "name": r.name, "query": r.query,
            "parsed": r.parsed or {}, "is_pinned": r.is_pinned,
            "use_count": r.use_count, "last_used_at": r.last_used_at,
        }
        for r in filas
    ]


def save_search(db: Session, user, *, name: str, query: str, is_pinned: bool) -> dict:
    from app.models.collaboration import CollaborationSavedSearch
    from app.services.collaboration._search_query import parse as parse_query

    name = (name or "").strip()
    query = (query or "").strip()
    if not name or not query:
        raise ErrorDeDominio(400, "name + query requeridos")
    parsed = parse_query(query).to_dict()
    fila = CollaborationSavedSearch(
        organization_id=_org(user), user_id=user.id,
        name=name, query=query, parsed=parsed, is_pinned=bool(is_pinned),
    )
    db.add(fila)
    db.commit()
    return {"id": fila.id, "name": fila.name, "query": fila.query, "parsed": parsed}


def delete_saved_search(db: Session, user, saved_id: str) -> None:
    """Borra una busqueda guardada del usuario.

    No lanza si no existe: borrar dos veces lo mismo no es un error, y el
    endpoint ya se comportaba asi.
    """
    from app.models.collaboration import CollaborationSavedSearch

    fila = (
        db.query(CollaborationSavedSearch)
        .filter(
            CollaborationSavedSearch.id == saved_id,
            CollaborationSavedSearch.user_id == user.id,
        )
        .first()
    )
    if fila:
        db.delete(fila)
        db.commit()


def registrar_uso_de_busqueda(db: Session, user, saved_id: str) -> str:
    """Suma un uso a la busqueda guardada y devuelve su texto de consulta."""
    from app.models.collaboration import CollaborationSavedSearch

    fila = (
        db.query(CollaborationSavedSearch)
        .filter(
            CollaborationSavedSearch.id == saved_id,
            CollaborationSavedSearch.user_id == user.id,
        )
        .first()
    )
    if not fila:
        raise ErrorDeDominio(404, "No encontrada")
    consulta = fila.query
    fila.use_count = (fila.use_count or 0) + 1
    fila.last_used_at = utcnow()
    db.commit()
    return consulta


# ── Sugerencias de mencion ───────────────────────────────────────────────────

#: Cuantos usuarios se traen de base antes de filtrar por pertenencia al canal.
#: Se piden mas de los que se devuelven porque el filtro por miembros del equipo
#: se aplica en memoria: si se pidieran justo `limit`, un canal pequeño dentro de
#: una organizacion grande devolveria menos sugerencias de las que hay.
_CANDIDATOS_A_MENCIONAR = 50

#: Los tres grupos especiales, con su etiqueta. Se ofrecen cuando lo que se ha
#: escrito es prefijo de su nombre.
GRUPOS_DE_MENCION = (
    ("here", "@here · personas online"),
    ("channel", "@channel · todo el canal"),
    ("everyone", "@everyone · toda la conversación"),
)


def mention_suggestions(
    db: Session, user, *, q: str = "", conversation_id: Optional[str] = None,
    limit: int = 8,
) -> dict:
    """Usuarios mencionables y grupos especiales.

    Si se pasa `conversation_id` y es un canal, las sugerencias se limitan a los
    miembros de su equipo. Y **se excluye a quien pregunta**: nadie se menciona a
    si mismo.
    """
    org = _org(user)
    ids_permitidos: Optional[set] = None
    if conversation_id:
        ch = (
            db.query(CollaborationChannel)
            .filter(CollaborationChannel.conversation_id == conversation_id)
            .first()
        )
        if ch:
            ids_permitidos = {
                r[0] for r in db.query(CollaborationTeamMember.user_id).filter(
                    CollaborationTeamMember.team_id == ch.team_id
                ).all()
            }

    consulta = db.query(User).filter(User.organization_id == org)
    if q:
        ql = q.lstrip("@").lower()
        consulta = consulta.filter(or_(
            func.lower(User.username).like(f"{ql}%"),
            func.lower(User.full_name).like(f"%{ql}%"),
            func.lower(User.email).like(f"{ql}%"),
        ))
    filas = consulta.limit(_CANDIDATOS_A_MENCIONAR).all()
    if ids_permitidos is not None:
        filas = [u for u in filas if u.id in ids_permitidos]
    filas = [u for u in filas if u.id != user.id]

    usuarios = [
        {
            "id": u.id,
            "username": getattr(u, "username", None),
            "full_name": getattr(u, "full_name", None) or getattr(u, "username", None),
            "email": u.email,
        }
        for u in filas[:limit]
    ]
    qm = (q or "").lstrip("@").lower()
    grupos = [
        {"id": tag, "username": tag, "full_name": label, "is_group": True}
        for tag, label in GRUPOS_DE_MENCION
        if not qm or tag.startswith(qm)
    ]
    return {"users": usuarios, "groups": grupos}


# ── Busqueda global ──────────────────────────────────────────────────────────

#: Tope de resultados de una busqueda guardada. Tiene su propia constante y no
#: reusa `MAX_NOTIFICACIONES` aunque hoy valgan lo mismo: son dos limites de
#: cosas distintas, y compartir la constante haria que cambiar el tope del buzon
#: cambiara en silencio el de las busquedas.
MAX_RESULTADOS_DE_BUSQUEDA = 200
