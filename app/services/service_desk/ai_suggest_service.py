import logging
from typing import Optional

from sqlalchemy.orm import Session

from app.models.service_desk import CannedResponse
from app.models.user import User


def _compute_kb_matches(db: Session, query_text: str):
    """Articulos parecidos, con el vector guardado de cada uno (ver `kb_sugerencias`)."""
    from app.services.service_desk.kb_sugerencias import sugerir
    return sugerir(db, query_text, solo_publico=False, limite=5)


def _compute_canned_matches(db: Session, query_text: str):
    canned = db.query(CannedResponse).filter(CannedResponse.is_active == True).all()
    q_words = {w for w in query_text.lower().split() if len(w) >= 4}
    canned_scored = []
    for c in canned:
        text = f"{c.title or ''} {c.body or ''} {c.shortcut or ''}".lower()
        overlap = sum(1 for w in q_words if w in text)
        if overlap > 0:
            canned_scored.append((overlap, c))
    canned_scored.sort(key=lambda x: x[0], reverse=True)
    return [
        {
            "id": c.id,
            "title": c.title,
            "body": c.body,
            "shortcut": c.shortcut,
            "score": s,
        }
        for s, c in canned_scored[:5]
    ]


def build_ai_ticket_suggestion(db: Session, ticket_id: str, payload: Optional[dict], current_user: User) -> dict:
    # Con el acotado de tickets: sin el, un empleado leia por aqui el
    # contenido de un ticket que no puede abrir.
    from app.services.service_desk.scoping import get_scoped_ticket_or_404
    ticket = get_scoped_ticket_or_404(db, current_user, ticket_id)

    req = payload or {}
    user_content = (req.get("content") or "").strip()
    query_text = user_content or f"{ticket.title}\n{ticket.description}"

    kb_matches = _compute_kb_matches(db, query_text)
    canned_matches = _compute_canned_matches(db, query_text)
    # Revisión 2026-11: el cliente común de los conectores (antes uno propio en
    # service_desk/contecmind.py). Sin contecmind, o si falla, se redacta sin documentos.
    from app.services.conectores import contecmind as _cm
    from app.services.conectores.anfitrion import ErrorDeConector
    documentos, docs_configurado, docs_error = [], True, None
    try:
        documentos = _cm.buscar(db, current_user, query_text)
    except ErrorDeConector as e:
        docs_configurado, docs_error = e.codigo != "no_configurado", (None if e.codigo == "no_configurado" else e.detalle)
    doc_context = "\n\n".join(f"[{d['title']}] {d['snippet']}" for d in documentos) or "(sin documentos)"

    kb_context = "\n\n".join(
        [f"[{k['number']}] {k['title']}\n{k.get('summary') or ''}" for k in kb_matches]
    ) or "(sin artículos KB relevantes)"
    canned_context = "\n\n".join(
        [f"[{c['title']}] {c['body']}" for c in canned_matches]
    ) or "(sin respuestas rápidas relevantes)"

    system = (
        "Eres un agente senior de Service Desk ITIL. "
        "Redacta una respuesta al cliente en español, profesional, breve y accionable. "
        "No inventes hechos. Si faltan datos, pide información concreta."
    )
    messages = [
        {
            "role": "user",
            "content": (
                f"Ticket: {ticket.number}\n"
                f"Título: {ticket.title}\n"
                f"Descripción: {ticket.description}\n\n"
                f"Contenido adicional del agente: {user_content or '(ninguno)'}\n\n"
                f"Artículos KB similares:\n{kb_context}\n\n"
                f"Documentos (contecmind):\n{doc_context}\n\n"
                f"Canned responses sugeridas:\n{canned_context}\n\n"
                "Devuélveme SOLO un borrador de respuesta listo para enviar al cliente."
            ),
        }
    ]

    try:
        from app.services.ai_provider_service import call_ai

        draft = call_ai(
            db,
            messages=messages,
            system=system,
            module="service_desk",
            user_id=current_user.id,
            max_tokens=500,
        )
        ai_error = None
        from app.services.ai_provider_service import es_aviso_de_ia
        if es_aviso_de_ia(draft):
            # Auditoria 2026-11: el aviso «no hay proveedor» se devolvia como
            # borrador y la pantalla lo pegaba en la respuesta al cliente.
            raise RuntimeError(draft)
    except Exception as exc:
        # Auditoria 2026-11: aqui se devolvia un texto generico («Estamos
        # revisando tu incidencia...») como si lo hubiera redactado la IA. Si la
        # IA no responde se dice; los articulos y documentos siguen sirviendo.
        logging.getLogger(__name__).warning("AI suggest no disponible para %s: %s", ticket_id, exc)
        draft, ai_error = None, "La IA no está disponible: revisa el proveedor en IA & Conectores."

    return {
        "ticket_id": ticket.id,
        "ticket_number": ticket.number,
        "draft": draft,
        "ai_error": ai_error,
        "kb_matches": kb_matches,
        "canned_matches": canned_matches,
        "documents": documentos,
        "documents_configured": docs_configurado,
        "documents_error": docs_error,
    }
