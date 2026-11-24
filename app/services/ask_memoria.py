"""Memoria de conversación de Ask-the-Data (23-11-2026, migración 207).

Lo que contecintelligence tenía y aquí faltaba: preguntas de seguimiento.
«¿Cuántas horas imputó el equipo en septiembre?» y luego «¿y en octubre?»: la
segunda solo se entiende con la primera. Cada pregunta va a una conversación
(`AskDataConversation`) de la persona en su empresa; al modelo se le dan las
últimas `ASK_DATA_CONTEXT_TURNS` preguntas de esa conversación con la consulta
que las respondió (0 = sin memoria).

GRC:
- Aislamiento: la conversación es de (empresa, persona). Se busca SIEMPRE por
  las dos; la de otra persona o de otra empresa es «no encontrada».
- Datos: se guarda la pregunta, la consulta, cuántas filas y el error. NO las
  filas del resultado.
- Retención: tipo `ask_data_conversations` (desde la última pregunta; sus
  preguntas se van en cascada). Bloqueo legal por conversación o persona.
- RGPD: la persona borra una o todas; la supresión borra todas las suyas
  (`suprimir_persona`). Los borrados se auditan sin el texto de las preguntas.
"""
from __future__ import annotations

from typing import Optional

from sqlalchemy.orm import Session

from app.core.codigos_de_error import error
from app.models.ai_chat import AskDataConversation, AskDataTurn

#: Largo máximo de la consulta de cada pregunta anterior que se da al modelo.
_SQL_EN_CONTEXTO = 1500


def turnos_de_contexto(db: Session, org_id: Optional[str]) -> int:
    from app.core.config import settings
    from app.services.settings_service import get_runtime_int
    n = get_runtime_int(db, "ASK_DATA_CONTEXT_TURNS", org_id)
    return max(0, int(settings.ASK_DATA_CONTEXT_TURNS if n is None else n))


def _de_la_persona(db: Session, org_id: Optional[str], user_id: str):
    q = db.query(AskDataConversation).filter(AskDataConversation.user_id == user_id)
    return q.filter(AskDataConversation.organization_id == org_id) if org_id else \
        q.filter(AskDataConversation.organization_id.is_(None))


def abrir(db: Session, org_id: Optional[str], user_id: str, conversation_id: Optional[str],
          primera_pregunta: str) -> AskDataConversation:
    """La conversación pedida (de esta persona y empresa) o una nueva. No confirma."""
    if conversation_id:
        conv = _de_la_persona(db, org_id, user_id).filter(AskDataConversation.id == conversation_id).first()
        if conv is None:
            raise error(404, "no_encontrado", detail="Conversación no encontrada", que="conversacion")
        return conv
    conv = AskDataConversation(organization_id=org_id, user_id=user_id, title=(primera_pregunta or "")[:200])
    db.add(conv)
    db.flush()
    return conv


def contexto(db: Session, conv: AskDataConversation, n: int) -> str:
    """Las últimas `n` preguntas de la conversación con su consulta, para el modelo ('' si no hay)."""
    if n <= 0 or conv.id is None:
        return ""
    previas = (db.query(AskDataTurn).filter(AskDataTurn.conversation_id == conv.id)
               .order_by(AskDataTurn.created_at.desc()).limit(n).all())
    if not previas:
        return ""
    lineas = ["Conversación previa (de la más antigua a la más reciente). La pregunta actual puede ser "
              "de seguimiento: complétala con este contexto (mismo tema, filtros y agrupación salvo "
              "lo que cambie)."]
    for t in reversed(previas):
        lineas.append(f"Pregunta: {t.question}")
        if t.sql:
            lineas.append(f"SQL usada: {t.sql[:_SQL_EN_CONTEXTO]}")
    return "\n".join(lineas)


def guardar_turno(db: Session, conv: AskDataConversation, pregunta: str, resultado: dict) -> AskDataTurn:
    """Apunta la pregunta y cómo se respondió (sin filas). Confirma."""
    from app.core.timeutil import utcnow
    turno = AskDataTurn(organization_id=conv.organization_id, conversation_id=conv.id, question=pregunta[:4000],
                        sql=(resultado.get("model_sql") or resultado.get("sql") or None),
                        row_count=resultado.get("row_count"), error=resultado.get("error"),
                        # Hora con microsegundos desde la aplicación: `now()` del servidor va
                        # por segundos en SQLite y dos preguntas seguidas empataban, así que
                        # «las últimas n» podían ser las primeras.
                        created_at=utcnow())
    db.add(turno)
    conv.updated_at = utcnow()
    db.commit()
    return turno


def listar(db: Session, org_id: Optional[str], user_id: str, limite: int = 50) -> list[dict]:
    convs = (_de_la_persona(db, org_id, user_id).order_by(AskDataConversation.updated_at.desc())
             .limit(max(1, min(limite, 200))).all())
    return [{"id": c.id, "title": c.title, "updated_at": c.updated_at.isoformat() if c.updated_at else None,
             "turns": len(c.turns)} for c in convs]


def detalle(db: Session, org_id: Optional[str], user_id: str, conversation_id: str) -> dict:
    conv = _de_la_persona(db, org_id, user_id).filter(AskDataConversation.id == conversation_id).first()
    if conv is None:
        raise error(404, "no_encontrado", detail="Conversación no encontrada", que="conversacion")
    return {"id": conv.id, "title": conv.title,
            "turns": [{"id": t.id, "question": t.question, "sql": t.sql, "row_count": t.row_count,
                       "error": t.error, "created_at": t.created_at.isoformat() if t.created_at else None}
                      for t in conv.turns]}


def _exigir_sin_bloqueo(db: Session, org_id: Optional[str], conv: AskDataConversation) -> None:
    from app.db.bloqueo_legal import BloqueoLegalActivo, bloqueos_activos
    # El `before_flush` de `app/models/governance.py` también lo impide; aquí se
    # comprueba antes para no borrar la mitad y fallar en la otra.
    for b in bloqueos_activos(db, org_id):
        if (b.entity in ("*", "ask_data_conversations") and b.field in ("id", "user_id")
                and str(getattr(conv, b.field, "")) == b.value):
            raise BloqueoLegalActivo(b.case_reference)


def borrar(db: Session, usuario, conversation_id: Optional[str] = None) -> int:
    """Borra una conversación de la persona (o todas, sin id). Auditado sin el texto. Confirma."""
    from app.services.audit import audit_log
    org_id = getattr(usuario, "organization_id", None)
    q = _de_la_persona(db, org_id, usuario.id)
    if conversation_id:
        q = q.filter(AskDataConversation.id == conversation_id)
    convs = q.all()
    if conversation_id and not convs:
        raise error(404, "no_encontrado", detail="Conversación no encontrada", que="conversacion")
    for c in convs:
        _exigir_sin_bloqueo(db, org_id, c)
    for c in convs:
        audit_log(db, usuario, "DELETE", "ask_data_conversation", c.id, None,
                  metadata={"turnos": len(c.turns), "motivo": "borrado_por_su_titular"})
        db.delete(c)
    db.commit()
    return len(convs)


def suprimir_persona(db: Session, user_id: str) -> int:
    """Supresión RGPD: todas las conversaciones de la persona, en todas sus empresas. No confirma.

    El bloqueo legal ya lo comprobó `supresion_service` antes de tocar nada.
    """
    from app.db.session import sin_filtro_de_tenant
    with sin_filtro_de_tenant(db):
        convs = db.query(AskDataConversation).filter(AskDataConversation.user_id == user_id).all()
        for c in convs:
            db.delete(c)
        db.flush()
    return len(convs)
