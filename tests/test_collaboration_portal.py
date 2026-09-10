"""El portal de cliente era una segunda vía de envío sin los controles de la primera.

Auditoría 2026-08 (P3-22). `endpoints/collaboration_portal.py` tenía 21 consultas
y escrituras directas, y **ningún test tocaba sus ocho rutas**. Al bajarlas al
servicio apareció que su envío de mensajes reimplementaba una versión pobre del
interno:

* **No indexaba el mensaje para búsqueda.** `search_engine.index()` sólo lo
  llamaba la vía interna.

  > **Corrección de mi propia lectura, y del test que escribí primero.** Lo
  > documenté como «el cliente no encontraba sus mensajes» y **eso es falso en
  > la configuración por defecto**: `SimpleSqlSearch.index()` —y el
  > `PgFtsSearch` que hereda de él— son no-op, y su búsqueda consulta la tabla,
  > así que con SQLite o Postgres los mensajes se encontraban igual. El indexado
  > sólo hace algo con `COLLAB_SEARCH_BACKEND=opensearch`. Mi primer test
  > comprobaba que la búsqueda encontraba el mensaje, y **pasaba también sin el
  > arreglo**: no discriminaba nada. El de ahora comprueba lo que de verdad
  > cambió — que el envío del portal **llama** al indexado.
* **No pasaba por el escaneo DLP**, que la vía interna sí aplica.
* **El reparto de notificaciones era parcial y con una comparación imposible.**
  Sólo avisaba en conversaciones directas, sólo a los dos usuarios internos, y se
  protegía con `uid != current_client.id`: `user_a_id`/`user_b_id` son de `users`
  y `current_client.id` es de `client_users`, así que esa comparación **nunca
  podía ser falsa**. Los clientes contraparte no recibían nada.
* No creaba hilos (`parent_message_id`).
* El ancla de paginación se buscaba por id sin acotarla a la conversación.
* El tope de 25 mensajes por minuto estaba en duro.

El arreglo no reescribe nada de eso: llama a `messages.send_message` con
`client_user_id`, que es la única vía. El aparato interno ya sabía tratar
destinatarios cliente y excluir al autor por `client_user_id` — hacía falta
usarlo, no duplicarlo.
"""
from __future__ import annotations

import pytest

ORG = "org-portal-colab"


@pytest.fixture()
def escenario(db):
    """Un cliente de portal en una conversación directa con dos internos."""
    from app.models.client_portal import ClientUser
    from app.models.collaboration import (
        CollaborationConversation,
        CollaborationDirectConversation,
        CollaborationWorkspace,
    )
    from app.models.user import User, UserRole, UserStatus

    internos = []
    for sufijo in ("a", "b"):
        u = User(
            id=f"interno-{sufijo}", username=f"interno-{sufijo}",
            email=f"interno-{sufijo}@example.com", full_name=f"Interno {sufijo}",
            role=UserRole.employee, status=UserStatus.active,
            hashed_password="x", organization_id=ORG,
        )
        db.add(u)
        internos.append(u)

    cliente = ClientUser(
        id="cliente-portal", organization_id=ORG,
        full_name="Cliente Portal", email="cliente@example.com",
        hashed_password="x", is_active=True,
    )
    otro_cliente = ClientUser(
        id="cliente-contraparte", organization_id=ORG,
        full_name="Cliente Contraparte", email="contraparte@example.com",
        hashed_password="x", is_active=True,
    )
    db.add_all([cliente, otro_cliente])
    db.flush()

    ws = CollaborationWorkspace(organization_id=ORG, name="WS portal")
    db.add(ws)
    db.flush()
    conv = CollaborationConversation(
        organization_id=ORG, workspace_id=ws.id, kind="direct")
    db.add(conv)
    db.flush()
    directo = CollaborationDirectConversation(
        organization_id=ORG, workspace_id=ws.id, conversation_id=conv.id,
        user_a_id=internos[0].id, user_b_id=internos[1].id,
        client_user_a_id=cliente.id, client_user_b_id=otro_cliente.id,
    )
    db.add(directo)
    db.commit()
    return {
        "cliente": cliente, "otro_cliente": otro_cliente,
        "internos": internos, "conv": conv, "ws": ws,
    }


class _Payload:
    """El cuerpo que el endpoint entrega al servicio."""

    def __init__(self, conversation_id, body, **extra):
        self.conversation_id = conversation_id
        self.body = body
        self.type = extra.get("type")
        self.metadata_json = extra.get("metadata_json")
        self.parent_message_id = extra.get("parent_message_id")


# ── El envío pasa por la vía única ──────────────────────────────────────────

def test_EL_HALLAZGO_el_envio_del_portal_indexa_el_mensaje(db, escenario, monkeypatch):
    """El envío del portal tiene que pasar por el indexado.

    Se comprueba **espiando la llamada**, no consultando la búsqueda: con el
    motor por defecto la búsqueda lee la tabla y encontraría el mensaje
    estuviera indexado o no, así que un test por resultado no distinguiría el
    arreglo del defecto. Con `COLLAB_SEARCH_BACKEND=opensearch` sí importa, y es
    ahí donde los mensajes del portal eran invisibles.
    """
    from app.services.collaboration import messages as mod_mensajes
    from app.services.collaboration import portal as svc

    indexados: list[str] = []

    class _MotorEspia:
        def index(self, db, message_id):
            indexados.append(message_id)

        def remove(self, db, message_id):
            pass

    monkeypatch.setattr(mod_mensajes, "search_engine", _MotorEspia())

    msg = svc.send_message(
        db, escenario["cliente"],
        _Payload(escenario["conv"].id, "el presupuesto del proyecto Zeta"))

    assert indexados == [msg.id], (
        "el envio del portal no paso por el indexado de busqueda")


def test_la_busqueda_del_portal_encuentra_el_mensaje_del_cliente(db, escenario):
    """Complementario del anterior: el camino completo funciona.

    Con el motor por defecto esto pasaba ya antes del arreglo —la busqueda lee
    la tabla—, asi que no prueba el arreglo; prueba que no lo he roto.
    """
    from app.services.collaboration import portal as svc

    svc.send_message(
        db, escenario["cliente"],
        _Payload(escenario["conv"].id, "el presupuesto del proyecto Zeta"))

    hits = svc.search(db, escenario["cliente"], query="Zeta", limit=10)
    assert hits, "la búsqueda del portal no encuentra el mensaje del propio cliente"


def test_EL_HALLAZGO_se_avisa_al_cliente_contraparte(db, escenario):
    """Los clientes del otro lado no recibían nada, y el autor no debe recibirse.

    La comparación que había —un id de `users` contra uno de `client_users`—
    nunca podía ser falsa, así que ni filtraba al autor ni alcanzaba a los
    clientes.
    """
    from app.models.collaboration import CollaborationNotification
    from app.services.collaboration import portal as svc

    svc.send_message(
        db, escenario["cliente"], _Payload(escenario["conv"].id, "hola"))

    avisos = db.query(CollaborationNotification).filter(
        CollaborationNotification.conversation_id == escenario["conv"].id).all()
    destinatarios_cliente = {n.client_user_id for n in avisos if n.client_user_id}
    destinatarios_internos = {n.user_id for n in avisos if n.user_id}

    assert escenario["otro_cliente"].id in destinatarios_cliente, (
        "el cliente contraparte no recibió aviso")
    assert escenario["cliente"].id not in destinatarios_cliente, (
        "el autor recibió aviso de su propio mensaje")
    assert destinatarios_internos == {u.id for u in escenario["internos"]}


def test_el_mensaje_queda_a_nombre_del_cliente_y_no_de_un_usuario(db, escenario):
    from app.services.collaboration import portal as svc

    msg = svc.send_message(
        db, escenario["cliente"], _Payload(escenario["conv"].id, "firmado"))
    assert msg.client_user_id == escenario["cliente"].id
    assert msg.user_id is None
    assert msg.organization_id == ORG


def test_un_cliente_que_no_participa_no_puede_escribir(db, escenario):
    from fastapi import HTTPException

    from app.models.client_portal import ClientUser
    from app.services.collaboration import portal as svc

    intruso = ClientUser(
        id="cliente-intruso", organization_id=ORG, full_name="Intruso",
        email="intruso@example.com", hashed_password="x", is_active=True)
    db.add(intruso)
    db.commit()

    with pytest.raises(HTTPException) as exc:
        svc.send_message(db, intruso, _Payload(escenario["conv"].id, "cuela?"))
    assert exc.value.status_code == 403


def test_el_envio_exige_conversacion(db, escenario):
    from fastapi import HTTPException

    from app.services.collaboration import portal as svc

    with pytest.raises(HTTPException) as exc:
        svc.send_message(db, escenario["cliente"], _Payload(None, "sin destino"))
    assert exc.value.status_code == 400


# ── Listados ────────────────────────────────────────────────────────────────

def test_las_conversaciones_del_cliente_llevan_su_titulo(db, escenario):
    from app.services.collaboration import portal as svc

    filas = svc.list_conversations(db, escenario["cliente"])
    assert len(filas) == 1
    assert filas[0]["id"] == escenario["conv"].id
    assert filas[0]["kind"] == "direct"
    # Hay un interno al otro lado, así que el cliente lo ve como soporte.
    assert filas[0]["title"] == svc.TITULO_DIRECTO_CON_INTERNO


def test_un_cliente_sin_conversaciones_no_consulta_de_mas(db):
    """Sin conversaciones se devuelve la lista vacía **sin** ir a por los tres
    tipos: el `in_([])` de cada uno serían tres consultas para nada."""
    from app.models.client_portal import ClientUser
    from app.services.collaboration import portal as svc

    solo = ClientUser(
        id="cliente-solo", organization_id=ORG, full_name="Solo",
        email="solo@example.com", hashed_password="x", is_active=True)
    db.add(solo)
    db.commit()
    assert svc.list_conversations(db, solo) == []
    assert svc.search(db, solo, query="lo que sea", limit=10) == []


def test_los_mensajes_se_devuelven_del_mas_antiguo_al_ultimo(db, escenario):
    from app.services.collaboration import portal as svc

    for texto in ("primero", "segundo", "tercero"):
        svc.send_message(db, escenario["cliente"],
                         _Payload(escenario["conv"].id, texto))

    filas = svc.list_messages(db, escenario["cliente"], escenario["conv"].id)
    assert [m.body for m in filas] == ["primero", "segundo", "tercero"]


def test_EL_HALLAZGO_el_ancla_de_paginacion_se_acota_a_la_conversacion(db, escenario):
    """El ancla se buscaba por id a secas, así que un id de otra conversación
    desplazaba la ventana con una fecha ajena."""
    from app.models.collaboration import CollaborationConversation, CollaborationMessage
    from app.services.collaboration import portal as svc

    for texto in ("uno", "dos"):
        svc.send_message(db, escenario["cliente"],
                         _Payload(escenario["conv"].id, texto))

    otra = CollaborationConversation(
        organization_id=ORG, workspace_id=escenario["ws"].id, kind="group")
    db.add(otra)
    db.flush()
    ajeno = CollaborationMessage(
        organization_id=ORG, conversation_id=otra.id, body="ajeno",
        type="text", status="visible")
    db.add(ajeno)
    db.commit()

    # Con un ancla que no es de esta conversacion se ignora y se devuelve todo,
    # en vez de recortar la ventana con la fecha de un mensaje ajeno.
    filas = svc.list_messages(
        db, escenario["cliente"], escenario["conv"].id, before=ajeno.id)
    assert [m.body for m in filas] == ["uno", "dos"]


def test_un_cliente_que_no_participa_no_lee_los_mensajes(db, escenario):
    from fastapi import HTTPException

    from app.models.client_portal import ClientUser
    from app.services.collaboration import portal as svc

    intruso = ClientUser(
        id="cliente-mirón", organization_id=ORG, full_name="Mirón",
        email="miron@example.com", hashed_password="x", is_active=True)
    db.add(intruso)
    db.commit()

    with pytest.raises(HTTPException) as exc:
        svc.list_messages(db, intruso, escenario["conv"].id)
    assert exc.value.status_code == 403


# ── Reacciones, lectura y notificaciones ────────────────────────────────────

def test_la_reaccion_se_pone_y_se_quita(db, escenario):
    from app.services.collaboration import portal as svc

    msg = svc.send_message(
        db, escenario["cliente"], _Payload(escenario["conv"].id, "reacciona"))

    assert svc.toggle_reaction(db, escenario["cliente"], msg.id, "👍")["added"] is True
    assert svc.toggle_reaction(db, escenario["cliente"], msg.id, "👍")["added"] is False


def test_marcar_leido_es_idempotente(db, escenario):
    from app.models.collaboration import CollaborationRead
    from app.services.collaboration import portal as svc

    msg = svc.send_message(
        db, escenario["cliente"], _Payload(escenario["conv"].id, "leeme"))

    svc.mark_read(db, escenario["cliente"], escenario["conv"].id, msg.id)
    svc.mark_read(db, escenario["cliente"], escenario["conv"].id, msg.id)

    filas = db.query(CollaborationRead).filter(
        CollaborationRead.conversation_id == escenario["conv"].id,
        CollaborationRead.client_user_id == escenario["cliente"].id,
    ).all()
    assert len(filas) == 1, "se creó una fila de lectura por llamada"
    assert filas[0].last_message_id == msg.id


def test_las_notificaciones_del_cliente_se_listan_y_se_marcan(db, escenario):
    from app.services.collaboration import portal as svc

    # Un aviso para el cliente contraparte: lo genera el envío del primero.
    svc.send_message(db, escenario["cliente"], _Payload(escenario["conv"].id, "eh"))

    contraparte = escenario["otro_cliente"]
    sin_leer = svc.list_notifications(db, contraparte, unread_only=True)
    assert len(sin_leer) == 1

    assert svc.mark_all_notifications_read(db, contraparte) == 1
    assert svc.list_notifications(db, contraparte, unread_only=True) == []
    # Y siguen ahí, marcadas: marcar no borra.
    assert len(svc.list_notifications(db, contraparte)) == 1


def test_el_tope_de_mensajes_por_minuto_sale_de_la_configuracion():
    """Estaba en duro a 25 en el endpoint."""
    from app.core.config import settings

    assert settings.COLLAB_PORTAL_MESSAGE_PER_MIN >= 1
