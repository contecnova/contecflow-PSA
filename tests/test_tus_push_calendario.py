"""Tres defectos que aparecieron al vaciar de base los endpoints de colaboración.

Auditoría 2026-08 (P3-22), últimos dos ficheros del dominio: `tus.py` y
`admin.py`.

**1. TUS era una puerta trasera a la validación de subidas.** `/attachments`
valida extensión, MIME declarado, bytes mágicos y la coherencia entre ellos, y
respeta `settings.MAX_FILE_SIZE_MB`. La vía TUS, que escribe en la MISMA tabla y
el MISMO almacén, tenía su propio tope en duro de 500 MB —cinco veces el
configurado— y **no validaba nada del contenido**. Bastaba subir por TUS para
meter un ejecutable que `/attachments` rechaza.

**2. El alta de suscripción Web Push podía dar un 500.** La columna `endpoint` es
única global, y la consulta que buscaba la fila existente quedaba acotada al
tenant por el filtro global, así que el mismo navegador usado luego por un
usuario de otra organización —un puesto compartido, un consultor con dos
cuentas— no encontraba su fila y chocaba contra la restricción única.

**3. `days` del calendario se declaraba y no se usaba.** El endpoint lo aceptaba
con rango `1..60` y consultaba a los proveedores sin límite inferior, ordenando
por fecha de inicio ascendente: lo que devolvía como «eventos próximos» eran los
**más antiguos** del calendario.
"""
from __future__ import annotations

import base64

import pytest

from app.core.config import settings


def _meta(**pares: str) -> str:
    """Cabecera `Upload-Metadata` con los pares ya en base64."""
    return ",".join(
        f"{k} {base64.b64encode(v.encode()).decode()}" for k, v in pares.items()
    )


@pytest.fixture()
def conversacion(db):
    """Una conversación a la que el administrador de los tests tiene acceso."""
    from app.models.collaboration import (
        CollaborationConversation,
        CollaborationConversationMember,
        CollaborationWorkspace,
    )
    from app.models.user import User

    admin = db.query(User).filter(User.username == "admin").first()
    assert admin is not None

    ws = CollaborationWorkspace(organization_id=admin.organization_id, name="WS TUS")
    db.add(ws)
    db.flush()
    conv = CollaborationConversation(
        organization_id=admin.organization_id, workspace_id=ws.id, kind="group")
    db.add(conv)
    db.flush()
    db.add(CollaborationConversationMember(
        organization_id=admin.organization_id, conversation_id=conv.id,
        user_id=admin.id, is_admin=True))
    db.commit()
    return conv


# ── 1. TUS ya no se salta la validación de subidas ──────────────────────────

def test_EL_HALLAZGO_tus_rechaza_un_ejecutable_renombrado(client, admin_token, conversacion):
    """Un PE de Windows con nombre `.pdf`. `/attachments` lo rechaza; TUS no.

    Es el test que habría cazado el defecto: antes este ejecutable acababa como
    adjunto porque la vía TUS no miraba el contenido en ningún momento.
    """
    from tests.conftest import auth

    contenido = b"MZ\x90\x00" + b"\x00" * 200
    r = client.post(
        "/api/v1/collaboration/tus",
        headers={
            **auth(admin_token),
            "Upload-Length": str(len(contenido)),
            "Upload-Metadata": _meta(
                conversationId=conversacion.id,
                filename="informe.pdf",
                filetype="application/pdf",
            ),
            "Tus-Resumable": "1.0.0",
        },
    )
    assert r.status_code == 201, r.text
    uid = r.headers["Location"].rsplit("/", 1)[-1]

    r = client.patch(
        f"/api/v1/collaboration/tus/{uid}",
        headers={
            **auth(admin_token),
            "Upload-Offset": "0",
            "Content-Type": "application/offset+octet-stream",
        },
        content=contenido,
    )
    assert r.status_code == 415, (
        f"TUS aceptó un ejecutable renombrado (status {r.status_code}); "
        "la vía de /attachments lo rechaza"
    )


def test_EL_HALLAZGO_tus_respeta_el_tope_configurado(client, admin_token, conversacion):
    """Un `Upload-Length` por encima de `MAX_FILE_SIZE_MB` se rechaza al crear.

    Antes el tope propio de TUS era 500 MB en duro, así que con el ajuste en 100
    se aceptaban sesiones de hasta 500.
    """
    from tests.conftest import auth

    demasiado = settings.MAX_FILE_SIZE_MB * 1024 * 1024 + 1
    r = client.post(
        "/api/v1/collaboration/tus",
        headers={
            **auth(admin_token),
            "Upload-Length": str(demasiado),
            "Upload-Metadata": _meta(conversationId=conversacion.id, filename="x.pdf"),
            "Tus-Resumable": "1.0.0",
        },
    )
    assert r.status_code == 413, r.text


def test_tus_anuncia_el_tope_real_y_no_uno_fijo(client):
    """`Tus-Max-Size` es el valor configurado: anunciar más es engañar al cliente,
    que trocea la subida contando con ese número."""
    r = client.options("/api/v1/collaboration/tus")
    assert r.status_code == 204
    assert r.headers["Tus-Max-Size"] == str(settings.MAX_FILE_SIZE_MB * 1024 * 1024)


def test_tus_acepta_un_pdf_de_verdad(client, admin_token, conversacion, db):
    """La validación no rompe el camino bueno: un PDF real se materializa.

    Comprueba además que el adjunto se crea por la vía única
    (`files.crear_adjunto`) con la acción de auditoría propia de TUS.
    """
    from tests.conftest import auth
    from app.models.collaboration import CollaborationAttachment, CollaborationAuditEvent

    contenido = b"%PDF-1.4\n" + b"0" * 500 + b"\n%%EOF\n"
    r = client.post(
        "/api/v1/collaboration/tus",
        headers={
            **auth(admin_token),
            "Upload-Length": str(len(contenido)),
            "Upload-Metadata": _meta(
                conversationId=conversacion.id,
                filename="contrato.pdf",
                filetype="application/pdf",
            ),
            "Tus-Resumable": "1.0.0",
        },
    )
    assert r.status_code == 201, r.text
    uid = r.headers["Location"].rsplit("/", 1)[-1]

    r = client.patch(
        f"/api/v1/collaboration/tus/{uid}",
        headers={
            **auth(admin_token),
            "Upload-Offset": "0",
            "Content-Type": "application/offset+octet-stream",
        },
        content=contenido,
    )
    assert r.status_code == 204, r.text
    assert r.headers["Upload-Offset"] == str(len(contenido))

    att = (
        db.query(CollaborationAttachment)
        .filter(CollaborationAttachment.conversation_id == conversacion.id)
        .first()
    )
    assert att is not None, "la subida completa no creó el adjunto"
    assert att.name == "contrato.pdf"

    acciones = {
        e.action for e in db.query(CollaborationAuditEvent)
        .filter(CollaborationAuditEvent.entity_id == att.id).all()
    }
    assert "attachment.uploaded.tus" in acciones


def test_tus_no_construye_rutas_con_texto_de_la_peticion(client, admin_token):
    """Un identificador que no es UUID da 404 y no llega al sistema de ficheros."""
    from tests.conftest import auth

    r = client.request(
        "HEAD", "/api/v1/collaboration/tus/..%2F..%2Fetc%2Fpasswd",
        headers=auth(admin_token))
    assert r.status_code == 404


# ── 2. Suscripción push: el mismo navegador en otra organización ────────────

def test_EL_HALLAZGO_endpoint_push_de_otra_organizacion_no_da_500(db):
    """El mismo navegador, luego usado por alguien de otra organización.

    `endpoint` es único global. La fila ajena era invisible al filtro de tenant,
    así que el alta intentaba un INSERT y chocaba con la restricción única. Ahora
    la fila se traspasa, y el traspaso se audita en las dos organizaciones.

    El filtro global de tenant se **activa a mano** en la sesión: en los tests
    `session.info` viene sin inicializar y `do_orm_execute` se salta el filtro,
    con lo que sin esto el escenario no se reproduciría y el test pasaría
    igualmente contra el código defectuoso. Es justo el filtro lo que hacía
    invisible la fila ajena, así que sin activarlo no se prueba nada.
    """
    from app.models.collaboration import (
        CollaborationAuditEvent,
        CollaborationPushSubscription,
    )
    from app.models.user import User
    from app.services.collaboration import admin as svc

    admin = db.query(User).filter(User.username == "admin").first()
    endpoint = "https://push.example/endpoint-compartido"

    # La suscripción ya existe a nombre de otra organización.
    ajena = CollaborationPushSubscription(
        organization_id="otra-organizacion", user_id="usuario-de-la-otra",
        endpoint=endpoint, p256dh_key="k-vieja", auth_key="a-vieja",
    )
    db.add(ajena)
    db.commit()

    # El filtro global de aislamiento por tenant esta registrado sobre
    # `SessionLocal`, y la suite usa otra factoria (`TestSession`), asi que en
    # los tests NO se ejecuta. Se engancha a esta sesion y sólo a ella para
    # reproducir la condicion de produccion: sin el filtro activo el escenario
    # no existe y el test pasaria igual contra el codigo defectuoso.
    from sqlalchemy import event as sa_event

    from app.db.session import _enforce_tenant_isolation

    # Se resuelve el `organization_id` ANTES de enganchar el filtro: `admin`
    # quedo expirado en el `commit` de arriba y leer el atributo dispara un
    # refresco, que con el filtro ya puesto y la sesion aun sin `org_id`
    # entraria por la rama de «usuario sin organizacion».
    org_de_quien_llama = admin.organization_id
    sa_event.listen(db, "do_orm_execute", _enforce_tenant_isolation)
    db.info["is_superadmin"] = False
    db.info["organization_id"] = org_de_quien_llama
    try:
        # Con el filtro activo, una consulta ORM por endpoint NO ve la fila
        # ajena: es la condicion exacta que provocaba el choque de unicidad.
        assert (
            db.query(CollaborationPushSubscription)
            .filter(CollaborationPushSubscription.endpoint == endpoint)
            .first()
        ) is None, "el filtro de tenant no esta actuando; el test no probaria nada"

        resultado = svc.guardar_suscripcion_push(db, admin, {
            "subscription": {"endpoint": endpoint,
                             "keys": {"p256dh": "k-nueva", "auth": "a-nueva"}},
        })
        assert resultado["reasignada"] is True
    finally:
        sa_event.remove(db, "do_orm_execute", _enforce_tenant_isolation)
        db.info.pop("is_superadmin", None)
        db.info.pop("organization_id", None)

    fila = (
        db.query(CollaborationPushSubscription)
        .filter(CollaborationPushSubscription.endpoint == endpoint)
        .one()
    )
    assert fila.organization_id == admin.organization_id, (
        "la fila tendría que haber pasado a la organización de quien llama")
    assert fila.user_id == admin.id
    assert fila.p256dh_key == "k-nueva"

    # La organización que PIERDE las notificaciones tiene que verlo en su propia
    # auditoría, no sólo la que las gana.
    acciones = {
        (e.organization_id, e.action)
        for e in db.query(CollaborationAuditEvent)
        .filter(CollaborationAuditEvent.entity_id == fila.id).all()
    }
    assert (admin.organization_id, "push.subscription.reassigned") in acciones
    assert ("otra-organizacion", "push.subscription.released") in acciones


def test_renovar_la_propia_suscripcion_no_ensucia_la_auditoria(db):
    """El caso habitual —el mismo usuario refrescando sus claves— no se audita."""
    from app.models.collaboration import (
        CollaborationAuditEvent,
        CollaborationPushSubscription,
    )
    from app.models.user import User
    from app.services.collaboration import admin as svc

    admin = db.query(User).filter(User.username == "admin").first()
    cuerpo = {"subscription": {"endpoint": "https://push.example/mio",
                               "keys": {"p256dh": "k1", "auth": "a1"}}}

    assert svc.guardar_suscripcion_push(db, admin, cuerpo)["reasignada"] is False
    cuerpo["subscription"]["keys"]["p256dh"] = "k2"
    assert svc.guardar_suscripcion_push(db, admin, cuerpo)["reasignada"] is False

    fila = (
        db.query(CollaborationPushSubscription)
        .filter(CollaborationPushSubscription.endpoint == "https://push.example/mio")
        .one()
    )
    assert fila.p256dh_key == "k2"
    eventos = (
        db.query(CollaborationAuditEvent)
        .filter(CollaborationAuditEvent.action.like("push.subscription.%"))
        .count()
    )
    assert eventos == 0


def test_el_alta_push_exige_las_tres_partes_de_la_suscripcion(db):
    from fastapi import HTTPException
    from app.models.user import User
    from app.services.collaboration import admin as svc

    admin = db.query(User).filter(User.username == "admin").first()
    with pytest.raises(HTTPException) as exc:
        svc.guardar_suscripcion_push(db, admin, {"endpoint": "https://push/x"})
    assert exc.value.status_code == 400


# ── 3. La ventana del calendario se aplica de verdad ────────────────────────

@pytest.mark.asyncio
async def test_EL_HALLAZGO_la_ventana_de_dias_llega_al_proveedor(db, monkeypatch):
    """`days` tiene que convertirse en `timeMin`/`timeMax` en la petición.

    Sin límite inferior, `orderBy=startTime` devuelve los eventos más antiguos
    del calendario. Este test fija que la ventana viaja y que sus extremos se
    corresponden con los días pedidos.
    """
    from datetime import datetime

    from app.models.collaboration import CollaborationIntegration, CollaborationWorkspace
    from app.models.user import User
    from app.services.collaboration import admin as svc

    admin = db.query(User).filter(User.username == "admin").first()
    ws = CollaborationWorkspace(organization_id=admin.organization_id, name="WS cal")
    db.add(ws)
    db.flush()
    db.add(CollaborationIntegration(
        organization_id=admin.organization_id, workspace_id=ws.id,
        kind="google_calendar", name="Google", is_enabled=True, config={}))
    db.commit()

    recibido: dict = {}

    async def falso_google(integration, max_results=10, *, desde_iso=None, hasta_iso=None):
        recibido.update(max_results=max_results, desde=desde_iso, hasta=hasta_iso)
        return {"ok": True, "body": {"items": [
            {"id": "e1", "summary": "Reunión",
             "start": {"dateTime": "2026-09-10T10:00:00Z"},
             "end": {"dateTime": "2026-09-10T11:00:00Z"},
             "htmlLink": "https://cal/e1"},
        ]}}

    monkeypatch.setattr(
        "app.services.collaboration._integrations_clients.google_calendar_list",
        falso_google)

    datos = await svc.eventos_de_calendario(db, admin, 14)

    assert recibido["desde"] and recibido["hasta"], "la ventana no llegó al proveedor"
    desde = datetime.fromisoformat(recibido["desde"])
    hasta = datetime.fromisoformat(recibido["hasta"])
    assert (hasta - desde).days == 14
    assert recibido["max_results"] == settings.COLLAB_CALENDAR_MAX_EVENTS
    assert datos["window_days"] == 14
    assert [e["id"] for e in datos["events"]] == ["e1"]
    assert datos["events"][0]["source"] == "google"


@pytest.mark.asyncio
async def test_EL_HALLAZGO_un_proveedor_con_el_token_caducado_deja_de_mentir(db, monkeypatch):
    """Una integración habilitada que responde con error no figura como conectada.

    Antes el bucle tenía un `except: continue` mudo y los clientes devuelven
    `{"error": ...}` sin lanzar: la integración aportaba cero eventos mientras
    seguía apareciendo en `providers_connected`.
    """
    from app.models.collaboration import CollaborationIntegration, CollaborationWorkspace
    from app.models.user import User
    from app.services.collaboration import admin as svc

    admin = db.query(User).filter(User.username == "admin").first()
    ws = CollaborationWorkspace(organization_id=admin.organization_id, name="WS cal 2")
    db.add(ws)
    db.flush()
    db.add(CollaborationIntegration(
        organization_id=admin.organization_id, workspace_id=ws.id,
        kind="google_calendar", name="Google", is_enabled=True, config={}))
    db.commit()

    async def google_caducado(integration, max_results=10, *, desde_iso=None, hasta_iso=None):
        return {"error": "Google no autenticado"}

    monkeypatch.setattr(
        "app.services.collaboration._integrations_clients.google_calendar_list",
        google_caducado)

    datos = await svc.eventos_de_calendario(db, admin, 7)

    assert datos["events"] == []
    assert datos["providers_connected"] == [], (
        "una integración que responde con error seguía anunciándose como conectada")
    assert datos["providers"][0]["ok"] is False
    assert datos["providers"][0]["error"] == "Google no autenticado"


# ── 4. El propio filtro de aislamiento por tenant ───────────────────────────

def test_EL_HALLAZGO_una_sesion_sin_organizacion_no_revienta(db):
    """Un usuario normal sin organización tiene que no ver filas, no dar un 500.

    Auditoría 2026-08. La rama de `_enforce_tenant_isolation` que decía
    «Regular user with no org → block any data return» pasaba `object` como
    objetivo de `with_loader_criteria`, y SA acaba llamando a
    `type.__subclasses__()` sin instancia:

        TypeError: unbound method type.__subclasses__() needs an argument

    Así que no bloqueaba: reventaba **cualquier** consulta ORM de esa sesión. Se
    llega ahí con un usuario sin organización asignada y también con un simple
    refresco de atributos antes de que la sesión tenga su `organization_id`.

    Este test engancha el filtro a la sesión de pruebas porque está registrado
    sobre `SessionLocal` y la suite usa otra factoría: **el aislamiento por
    tenant no lo ejercita ninguna prueba de la suite**. Queda anotado como hueco
    de cobertura aparte; aquí sólo se fija esta rama.
    """
    from sqlalchemy import event as sa_event

    from app.db.session import _enforce_tenant_isolation
    from app.models.collaboration import CollaborationPushSubscription

    db.add(CollaborationPushSubscription(
        organization_id="una-organizacion", user_id="alguien",
        endpoint="https://push.example/aislamiento", p256dh_key="k", auth_key="a"))
    db.commit()

    sa_event.listen(db, "do_orm_execute", _enforce_tenant_isolation)
    try:
        db.info["is_superadmin"] = False
        db.info["organization_id"] = None
        assert db.query(CollaborationPushSubscription).count() == 0

        # Y con organización sí ve lo suyo: la rama arreglada no rompe la otra.
        db.info["organization_id"] = "una-organizacion"
        assert db.query(CollaborationPushSubscription).count() == 1
    finally:
        sa_event.remove(db, "do_orm_execute", _enforce_tenant_isolation)
        db.info.pop("is_superadmin", None)
        db.info.pop("organization_id", None)


def test_EL_HALLAZGO_el_filtro_de_tenant_no_cachea_la_organizacion_de_otro(db):
    """Dos organizaciones seguidas en el mismo proceso: cada una ve la suya.

    Auditoría 2026-08, el hallazgo más grave de esta tanda. El criterio del
    filtro global se escribía así:

        lambda cls, _org=org_id: cls.organization_id == _org

    La organización iba en un **argumento por defecto**. El sistema de lambdas
    de SQLAlchemy analiza las variables de cierre para convertirlas en
    parámetros ligados, pero no los argumentos por defecto: ésos se evalúan al
    crear la lambda y quedan cocidos en la sentencia compilada, que vive en la
    caché del engine —de proceso, compartida por todas las peticiones—.

    Efecto medido antes del arreglo: la primera organización que pasaba por el
    filtro fijaba el valor, y la siguiente **recibía las filas de la primera**.

        sesión 1 (ORG-A) -> ['ORG-A']
        sesión 2 (ORG-B) -> ['ORG-A']   <-- datos de otro tenant

    Este test recorre A, B, A y la rama sin organización, en ese orden y en el
    mismo proceso, que es lo que hacía falta para verlo: una sola organización
    nunca lo delata.
    """
    from sqlalchemy import event as sa_event

    from app.db.session import _enforce_tenant_isolation
    from app.models.collaboration import CollaborationPushSubscription

    for org in ("ORG-A", "ORG-B"):
        db.add(CollaborationPushSubscription(
            organization_id=org, user_id=f"u-{org}",
            endpoint=f"https://push.example/{org}", p256dh_key="k", auth_key="a"))
    db.commit()

    sa_event.listen(db, "do_orm_execute", _enforce_tenant_isolation)
    db.info["is_superadmin"] = False
    try:
        def visto(org):
            db.info["organization_id"] = org
            return sorted(
                f.organization_id
                for f in db.query(CollaborationPushSubscription).all()
            )

        assert visto("ORG-A") == ["ORG-A"]
        assert visto("ORG-B") == ["ORG-B"], (
            "una organización está viendo filas de otra: el criterio del filtro "
            "quedó cacheado con el valor de la primera")
        assert visto("ORG-A") == ["ORG-A"]
        assert visto(None) == []
        assert visto("ORG-B") == ["ORG-B"]
    finally:
        sa_event.remove(db, "do_orm_execute", _enforce_tenant_isolation)
        db.info.pop("is_superadmin", None)
        db.info.pop("organization_id", None)
