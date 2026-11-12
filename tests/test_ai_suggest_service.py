"""Sugerencia de respuesta con IA.

Auditoria 2026-11: si la IA fallaba se devolvia un borrador generico como si lo
hubiese escrito la IA, y el ticket se buscaba sin el acotado (un empleado
leia por aqui el contenido de un ticket que no puede abrir).
"""
import pytest
from fastapi import HTTPException
from app.core.errores import ErrorDeDominio


def test_un_ticket_que_no_existe_o_no_se_ve_es_404(db):
    from app.models.service_desk import Ticket
    from app.models.user import User
    from app.services.service_desk.ai_suggest_service import build_ai_ticket_suggestion

    dev = db.get(User, "dev-test-id")
    with pytest.raises((HTTPException, ErrorDeDominio)) as exc:
        build_ai_ticket_suggestion(db, "nonexistent", None, dev)
    assert exc.value.status_code == 404
    db.add(Ticket(id="ajeno", number="INC-0001", ticket_type="incident", title="Nómina", description="secreto",
                  organization_id="1", requester_user_id="admin-test-id"))
    db.commit()
    with pytest.raises((HTTPException, ErrorDeDominio)) as exc:
        build_ai_ticket_suggestion(db, "ajeno", None, dev)
    assert exc.value.status_code == 404


def test_si_la_ia_no_responde_lo_dice_y_no_inventa_el_borrador(db, monkeypatch):
    from app.models.service_desk import KBArticle, Ticket
    from app.models.user import User
    from app.services import ai_provider_service
    from app.services.service_desk.ai_suggest_service import build_ai_ticket_suggestion

    def caida(*a, **k):
        raise RuntimeError("sin proveedor")
    monkeypatch.setattr(ai_provider_service, "call_ai", caida)
    db.add(KBArticle(number="KB-0001", title="Reiniciar la VPN", body="Pasos para reiniciar la VPN corporativa",
                     status="published", organization_id="1"))
    db.add(Ticket(id="t1", number="INC-0001", ticket_type="incident", title="La VPN no conecta",
                  description="No conecta la VPN", organization_id="1", requester_user_id="admin-test-id"))
    db.commit()
    r = build_ai_ticket_suggestion(db, "t1", None, db.get(User, "admin-test-id"))
    assert r["draft"] is None and "IA no está disponible" in r["ai_error"]
    assert [k["number"] for k in r["kb_matches"]] == ["KB-0001"]
    assert r["documents_configured"] is False and r["documents"] == []
