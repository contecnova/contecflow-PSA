"""El portal de cliente corría con el aislamiento por organización apagado.

Auditoría 2026-08. `get_current_client` autentica al usuario del portal y
devuelve su fila, pero **nunca poblaba `db.info`**. Y `TenantSession` se salta
el filtro cuando `info` no trae `is_superadmin` — esa rama existe para los
trabajos de fondo y los tests («sesión no inicializada»), no para una petición
autenticada.

Con **41 dependencias** de endpoints del portal colgando de `get_current_client`,
eso significaba que **toda consulta del portal sin filtro explícito devolvía
filas de todos los clientes**. Comprobado con la sesión real de la aplicación:

    portal SIN contexto  -> db.query(Client) devuelve ['ORG-A', 'ORG-B']
    portal CON contexto  -> devuelve ['ORG-A']

Es la misma clase de defecto que el WebSocket del chat (que también creaba su
sesión a mano y la dejaba sin contexto), pero mucho mayor por el número de
endpoints que cuelgan de aquí.

El arreglo va en `get_current_client`, un solo sitio, y **después** de resolver
al cliente: `get_active_client_by_id` busca por id sin saber todavía de qué
organización es, así que esa consulta tiene que correr sin filtrar. La misma
ordenación que hizo falta en el WebSocket.

## Por qué estos tests enganchan el filtro a mano

Se registra sobre `SessionLocal` y la suite usa otra factoría, así que el filtro
no se dispara en ningún test. Sin engancharlo aquí el escenario no existe y el
test pasaría igual contra el código defectuoso.
"""
from __future__ import annotations

import pytest
from sqlalchemy import event as sa_event

ORG = "org-portal-a"
OTRA = "org-portal-b"


@pytest.fixture()
def clientes_de_dos_organizaciones(db):
    """Una fila de `Client` en cada organización."""
    from app.models.clients import Client

    creados = {}
    for org in (ORG, OTRA):
        c = Client(organization_id=org, name=f"Cliente de {org}")
        db.add(c)
        db.flush()
        creados[org] = c
    db.commit()
    return creados


def _con_filtro(db):
    """Engancha el filtro de producción a la sesión de pruebas."""
    from app.db.session import _enforce_tenant_isolation

    sa_event.listen(db, "do_orm_execute", _enforce_tenant_isolation)
    return _enforce_tenant_isolation


def test_EL_HALLAZGO_una_sesion_de_portal_sin_contexto_ve_todas_las_organizaciones(
    db, clientes_de_dos_organizaciones
):
    """El estado de antes del arreglo, para que quede medido y no contado.

    No comprueba el arreglo: comprueba **que el escenario es real**. Si esta
    aserción dejara de cumplirse, el filtro habría cambiado y los dos tests de
    abajo dejarían de probar lo que dicen.
    """
    from app.models.clients import Client

    escuchador = _con_filtro(db)
    try:
        # Sin `is_superadmin` en `info`: exactamente como quedaba la sesión del
        # portal antes del arreglo.
        vistos = {c.organization_id for c in db.query(Client).all()}
        assert vistos == {ORG, OTRA}, (
            "la rama de «sesión no inicializada» ya no deja pasar todo; "
            "revisar si este test sigue midiendo lo que dice")
    finally:
        sa_event.remove(db, "do_orm_execute", escuchador)


def test_con_el_contexto_puesto_el_portal_solo_ve_su_organizacion(
    db, clientes_de_dos_organizaciones
):
    from app.models.clients import Client

    escuchador = _con_filtro(db)
    db.info["is_superadmin"] = False
    db.info["organization_id"] = ORG
    try:
        vistos = {c.organization_id for c in db.query(Client).all()}
        assert vistos == {ORG}, f"el portal ve otras organizaciones: {vistos}"
    finally:
        sa_event.remove(db, "do_orm_execute", escuchador)
        db.info.pop("is_superadmin", None)
        db.info.pop("organization_id", None)


def test_EL_ESTRUCTURAL_get_current_client_publica_el_contexto_de_tenant(db):
    """El que impide que vuelva a quitarse.

    Se ejercita la dependencia entera con un token de cliente real y se
    comprueba que la sesión queda con la organización del cliente. Es un test de
    cableado: si alguien quita esas tres líneas, esto se pone en rojo.
    """
    from datetime import datetime, timedelta, timezone

    from jose import jwt

    from app.api.v1.endpoints.client_portal import (
        ALGORITHM,
        CLIENT_TOKEN_SECRET,
        get_current_client,
    )
    from app.models.client_portal import ClientUser

    cliente = ClientUser(
        id="cliente-contexto", organization_id=ORG,
        full_name="Cliente Contexto", email="contexto@example.com",
        hashed_password="x", is_active=True,
    )
    db.add(cliente)
    db.commit()

    token = jwt.encode(
        {
            "sub": cliente.id,
            "type": "client",
            "exp": datetime.now(timezone.utc) + timedelta(minutes=5),
        },
        CLIENT_TOKEN_SECRET, algorithm=ALGORITHM,
    )

    devuelto = get_current_client(
        authorization=f"Bearer {token}", portal_access_token=None, db=db)

    assert devuelto.id == cliente.id
    assert db.info.get("organization_id") == ORG, (
        "get_current_client no publica la organización en la sesión: el filtro "
        "de tenant se saltará en todo el portal")
    assert db.info.get("is_superadmin") is False, (
        "sin `is_superadmin` a False, TenantSession trata la sesión como no "
        "inicializada y no filtra nada")
    assert db.info.get("current_client") is devuelto


def test_un_token_que_no_es_de_cliente_no_deja_contexto(db):
    """Un token de otro tipo no autentica y no debe tocar la sesión."""
    from datetime import datetime, timedelta, timezone

    from fastapi import HTTPException
    from jose import jwt

    from app.api.v1.endpoints.client_portal import (
        ALGORITHM,
        CLIENT_TOKEN_SECRET,
        get_current_client,
    )

    token = jwt.encode(
        {
            "sub": "alguien",
            "type": "user",  # no es "client"
            "exp": datetime.now(timezone.utc) + timedelta(minutes=5),
        },
        CLIENT_TOKEN_SECRET, algorithm=ALGORITHM,
    )

    # Auditoria 2026-08: se mira que la dependencia **no cambie** el contexto,
    # no que la sesion venga vacia. Desde que la suite corre con la semantica de
    # produccion, la sesion del fixture ya trae contexto publicado —el del
    # operador del test—, asi que «no hay contexto» dejo de ser la forma de
    # comprobar «la dependencia no lo ha tocado». La propiedad que importa es la
    # misma: un token que no es de cliente no publica nada.
    antes = dict(db.info)

    with pytest.raises(HTTPException) as exc:
        get_current_client(
            authorization=f"Bearer {token}", portal_access_token=None, db=db)
    assert exc.value.status_code == 401
    assert dict(db.info) == antes
    assert "current_client" not in db.info
