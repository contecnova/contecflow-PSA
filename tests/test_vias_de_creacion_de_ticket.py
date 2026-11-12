"""Las tres vías de creación de ticket que no podían crear un ticket.

Auditoría 2026-08. Las tres usaban `TicketStatus.open`, y ese miembro **no
existe** en el enumerado: los valores son `new`, `assigned`, `in_progress`,
`pending_client`, `pending_third`, `resolved`, `closed` y `cancelled`. Cada una
reventaba con `AttributeError: type object 'TicketStatus' has no attribute
'open'` en el momento de construir el `Ticket`:

* **correo entrante** (`inbound_email_service.build_inbound_ticket`) — la
  pasarela de correo a ticket, entera;
* **SMS entrante** (`multichannel_service.process_inbound_sms`) — lo mismo;
* **renovación de activo** (`asset_service.create_refresh_ticket`) — el ticket
  que agenda la renovación de un equipo.

Las otras tres vías de creación —el bot de colaboración, las integraciones y
los formularios públicos— usan `TicketStatus.new`, que es además el `default` de
la columna. **La asimetría entre seis sitios que hacen lo mismo es lo que
destapó esto.**

## Y por qué sobrevivieron

**Ninguna de las tres tenía un solo test.** El defecto no es sutil —es un
`AttributeError` en la primera línea útil— pero vive en un camino que nadie
ejercitaba: no lo ve `ruff`, que no resuelve el enumerado, ni el tipado, ni una
suite que no llama a la función. Estos tests son la cobertura que faltaba, no
sólo la comprobación del arreglo.

El guardián general está en `test_miembros_de_enum_existen.py`.
"""
from __future__ import annotations

import pytest
from app.core.errores import ErrorDeDominio

SECRETO = "secreto-de-la-pasarela"


@pytest.fixture()
def agente(db):
    """Un agente activo, que es a quien se asignan estos tickets."""
    from app.models.user import User, UserRole, UserStatus

    u = User(
        id="agente-vias", username="agente-vias",
        email="agente@example.com", full_name="Agente de Guardia",
        role=UserRole.admin, status=UserStatus.active, is_active=True,
        hashed_password="x", organization_id="org-vias",
    )
    db.add(u)
    db.commit()
    return u


# -- Correo entrante ---------------------------------------------------------

def test_EL_HALLAZGO_un_correo_entrante_crea_su_ticket(db, agente, monkeypatch):
    """Antes: `AttributeError` y ni un ticket por cada correo recibido.

    Desde 2026-11 el ticket entra por la numeracion comun (`INC-0001`, no
    `EML-xxxx`) y por la misma logica que la lectura del buzon.
    """
    from app.core.config import settings
    from app.models.service_desk import Ticket, TicketStatus
    from app.services.service_desk import inbound_email_service as svc

    monkeypatch.setattr(settings, "INBOUND_EMAIL_SECRET", SECRETO)
    r = svc.process_inbound_email(
        db,
        {
            "from": "Cliente Ejemplo <cliente@example.com>",
            "subject": "No puedo entrar en el portal",
            "body-plain": "Desde ayer me da error 500.",
        },
        provided_secret=SECRETO,
    )
    db.commit()
    assert r.accion == "created"
    ticket = db.get(Ticket, r.ticket_id)

    assert ticket.status in (TicketStatus.new, TicketStatus.assigned), (
        f"el estado inicial es {ticket.status!r}: `open` no existe en el enumerado")
    assert ticket.title == "No puedo entrar en el portal"
    assert ticket.requester_email == "cliente@example.com"
    assert ticket.source == "email"
    assert ticket.number == "INC-0001"


def test_un_correo_sin_asunto_ni_cuerpo_tambien_crea_ticket(db, agente, monkeypatch):
    """Los respaldos del parser, que ahora se pueden comprobar."""
    from app.core.config import settings
    from app.models.service_desk import Ticket
    from app.services.service_desk import inbound_email_service as svc

    monkeypatch.setattr(settings, "INBOUND_EMAIL_SECRET", SECRETO)
    r = svc.process_inbound_email(db, {"from": "x@example.com"}, provided_secret=SECRETO)
    db.commit()
    ticket = db.get(Ticket, r.ticket_id)

    assert ticket.title == "(sin asunto)"
    assert ticket.description == "(sin texto)"


def test_un_secreto_que_no_cuadra_no_crea_nada(db, agente, monkeypatch):
    """La puerta de la pasarela: se comprueba antes de tocar la base."""
    from fastapi import HTTPException

    from app.core.config import settings
    from app.models.service_desk import Ticket
    from app.services.service_desk import inbound_email_service as svc

    monkeypatch.setattr(settings, "INBOUND_EMAIL_SECRET", SECRETO)
    with pytest.raises((HTTPException, ErrorDeDominio)) as exc:
        svc.process_inbound_email(db, {"from": "x@example.com", "subject": "hola"}, provided_secret="otro")
    assert exc.value.status_code in (401, 403)
    assert db.query(Ticket).count() == 0


# -- SMS entrante ------------------------------------------------------------

def test_EL_HALLAZGO_un_sms_entrante_crea_su_ticket(db, agente):
    from app.models.service_desk import Ticket, TicketStatus
    from app.services.service_desk import multichannel_service as svc

    resultado = svc.process_inbound_sms(
        db, from_phone="+34600111222", body="La impresora no imprime")
    db.commit()

    assert resultado, "el SMS no ha devuelto nada"
    ticket = db.query(Ticket).first()
    assert ticket is not None, "no se ha creado el ticket del SMS"
    assert ticket.status in (TicketStatus.new, TicketStatus.assigned)
    assert ticket.source == "sms"
    assert ticket.number == "INC-0001", "fuera de la numeracion comun (antes SMS-xxxx)"
    assert "+34600111222" in ticket.description


def test_un_sms_vacio_tambien_crea_ticket(db, agente):
    from app.models.service_desk import Ticket
    from app.services.service_desk import multichannel_service as svc

    svc.process_inbound_sms(db, from_phone="+34600111222", body="   ")
    db.commit()

    ticket = db.query(Ticket).first()
    assert ticket is not None
    assert ticket.title == "(SMS sin cuerpo)"


# -- Renovación de un activo -------------------------------------------------

def test_EL_HALLAZGO_la_renovacion_de_un_activo_crea_su_ticket(db, agente):
    from app.models.alm import ALMAsset
    from app.models.service_desk import Ticket, TicketStatus
    from app.services.alm_ciclo_de_vida import abrir_ticket_de_renovacion

    activo = ALMAsset(id="act-vias", name="Portatil de dirección", type="laptop", organization_id="org-vias")
    db.add(activo)
    db.commit()

    resultado = abrir_ticket_de_renovacion(db, activo, agente.id)
    db.commit()

    assert resultado["created"], "la renovación no ha devuelto nada"
    ticket = db.query(Ticket).first()
    assert ticket is not None, "no se ha creado el ticket de renovación"
    assert ticket.status == TicketStatus.new
    assert ticket.ticket_type == "service_request"
    assert ticket.requester_user_id == agente.id
    assert ticket.organization_id == "org-vias"


# -- La asimetría que lo destapó --------------------------------------------

def test_EL_ESTRUCTURAL_las_seis_vias_usan_el_mismo_estado_inicial():
    """Tres usaban `new` y tres `open`. Que no vuelva a divergir.

    Se comprueba por AST sobre las construcciones de `Ticket` que fijan el
    estado a mano, saltando la siembra —que crea tickets en todos los estados a
    propósito—. El mismo guardián está en `test_miembros_de_enum_existen.py`;
    aquí queda junto a las vías que rompió.
    """
    import ast
    import io
    from pathlib import Path

    culpables = []
    for ruta in Path("app").rglob("*.py"):
        if "__pycache__" in ruta.parts or "seed_parts" in ruta.parts:
            continue
        try:
            arbol = ast.parse(io.open(ruta, encoding="utf-8").read())
        except SyntaxError:
            continue
        for nodo in ast.walk(arbol):
            if not (isinstance(nodo, ast.Call)
                    and isinstance(nodo.func, ast.Name)
                    and nodo.func.id == "Ticket"):
                continue
            for kw in nodo.keywords:
                if kw.arg == "status" and isinstance(kw.value, ast.Attribute):
                    if kw.value.attr != "new":
                        culpables.append(
                            f"{ruta.as_posix()}:{nodo.lineno} -> "
                            f"status=TicketStatus.{kw.value.attr}")

    assert not culpables, (
        "estas vías de creación fijan un estado inicial distinto de `new`: "
        + "; ".join(culpables))
