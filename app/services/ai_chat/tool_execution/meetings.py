"""Herramienta de reuniones para Nexus (19-11-2026): buscar en las reuniones que
la persona puede ver (mismo acotado que `GET /meeting-assistant/search`) y,
con `meeting_id`, traer su resumen, decisiones, acciones y la transcripción
recortada para responder preguntas sobre ella."""
from __future__ import annotations


def _search_meetings(tool_input, db, user, now, is_financial_role):
    from app.services.reuniones import consultas, servicio
    from app.services.reuniones.transcripcion import a_texto
    reunion_id = (tool_input.get("meeting_id") or "").strip()
    if reunion_id:
        try:
            m = consultas.obtener(db, user, reunion_id)
        except Exception:  # noqa: BLE001 - fuera de lo visible es «no existe»
            return {"error": "Reunión no encontrada"}
        if m.consent_required and not consultas.consentimiento_completo(m):
            return {"error": "La reunión espera consentimientos: no se puede consultar su contenido"}
        return {"meeting": {
            "id": m.id, "title": m.title, "date": m.meeting_date.isoformat() if m.meeting_date else None,
            "status": m.status, "summary": m.summary,
            "decisions": consultas._json(m.decisions), "risks": consultas._json(m.risks_mentioned),
            "open_questions": consultas._json(m.open_questions),
            "actions": [{"description": a.description, "assignee": a.assignee_name,
                         "due_date": a.due_date.date().isoformat() if a.due_date else a.due_date_text}
                        for a in m.actions],
            "transcript_excerpt": a_texto(m.segmentos)[:12000],
        }}
    consulta = (tool_input.get("query") or "").strip()
    limite = min(int(tool_input.get("limit") or 10), 30)
    if consulta:
        return {"results": servicio.buscar(db, user, consulta, limite)}
    from app.models.ai_chat import AIMeeting
    filas = consultas.visibles(db, user).order_by(AIMeeting.created_at.desc()).limit(limite).all()
    return {"results": [{"meeting_id": m.id, "title": m.title, "status": m.status,
                         "meeting_date": m.meeting_date.isoformat() if m.meeting_date else None,
                         "summary": (m.summary or "")[:300]} for m in filas]}


HANDLERS = {"search_meetings": _search_meetings}
