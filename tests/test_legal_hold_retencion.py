"""El legal hold no retenía lo que decía retener.

Auditoría 2026-08 (P3-22). Al mover los 18 accesos a base de
`endpoints/collaboration/compliance.py` al servicio apareció esto en
`_legal_held_message_ids`:

```python
user_ids, client_ids, channel_ids = set(), set(), set()
for r in casos_activos:
    user_ids.update(r.custodian_user_ids or [])
    client_ids.update(r.custodian_client_ids or [])      # recogido y NO usado
    channel_ids.update(r.channel_ids or [])              # recogido y NO usado
msg_q = db.query(CollaborationMessage.id).filter(...organization_id...)
if user_ids:
    msg_q = msg_q.filter(CollaborationMessage.user_id.in_(user_ids))
return {r[0] for r in msg_q.all()}
```

**Dos defectos en la misma función, y en direcciones opuestas:**

1. Un caso que nombra sólo **clientes** o sólo **canales** no protegía nada. Sus
   mensajes entraban en el barrido de retención y se marcaban como borrados con
   el cuerpo sustituido por `[retention purge]` — es decir, **destrucción de
   material bajo retención legal**, que es exactamente lo que un legal hold
   existe para impedir.
2. Y un caso **sin custodios de usuario** dejaba la retención sin efecto: con la
   lista vacía no se añadía filtro, la consulta devolvía **todos** los mensajes
   de la organización, y el barrido los consideraba retenidos. No se borraba
   nada nunca.

Ninguno de los dos daba error. El primero borra callando; el segundo no borra
callando.

La semántica correcta es la **disyunción** de las tres custodias: un mensaje está
retenido si lo escribió un usuario custodio, **o** lo escribió un cliente
custodio, **o** pertenece a la conversación de un canal retenido. Y un caso que
no nombra a nadie no retiene nada.

Estos tests fijan las dos direcciones. El de la custodia por canal es el que
habría cazado el defecto original.
"""
from __future__ import annotations

from datetime import timedelta

import pytest

from app.core.timeutil import utcnow
from app.services.collaboration import compliance as svc
from app.core.errores import ErrorDeDominio


@pytest.fixture()
def entorno(db):
    """Una organización con un canal, su conversación y tres mensajes.

    Los tres mensajes son de autores distintos —un usuario, otro usuario y un
    cliente— y están **todos vencidos** para el barrido de retención, así que lo
    único que decide si sobreviven es el legal hold.
    """
    from app.models.collaboration import (
        CollaborationChannel, CollaborationConversation, CollaborationMessage,
        CollaborationTeam, CollaborationWorkspace,
    )
    from app.models.user import User

    org_id = db.query(User.organization_id).filter(User.username == "admin").scalar()
    assert org_id, "el administrador de los tests no tiene organización"

    ws = CollaborationWorkspace(organization_id=org_id, name="WS retención")
    db.add(ws)
    db.flush()

    # El canal exige equipo: `team_id` es NOT NULL en el modelo.
    equipo = CollaborationTeam(
        organization_id=org_id, workspace_id=ws.id, name="Equipo", slug="equipo")
    db.add(equipo)
    db.flush()

    conv = CollaborationConversation(
        organization_id=org_id, workspace_id=ws.id, kind="channel")
    db.add(conv)
    db.flush()

    canal = CollaborationChannel(
        organization_id=org_id, workspace_id=ws.id, team_id=equipo.id,
        conversation_id=conv.id,
        name="finanzas", slug="finanzas", channel_type="public",
    )
    db.add(canal)
    db.flush()

    viejo = utcnow() - timedelta(days=400)
    mensajes = {
        "de_custodio": CollaborationMessage(
            organization_id=org_id, conversation_id=conv.id,
            user_id="usuario-custodio", body="lo escribió el custodio",
            sent_at=viejo, status="visible", type="text",
        ),
        "de_otro": CollaborationMessage(
            organization_id=org_id, conversation_id=conv.id,
            user_id="usuario-cualquiera", body="lo escribió otro",
            sent_at=viejo, status="visible", type="text",
        ),
        "de_cliente": CollaborationMessage(
            organization_id=org_id, conversation_id=conv.id,
            client_user_id="cliente-custodio", body="lo escribió un cliente",
            sent_at=viejo, status="visible", type="text",
        ),
    }
    for m in mensajes.values():
        db.add(m)
    db.commit()
    return {"org_id": org_id, "canal": canal, "conv": conv, "mensajes": mensajes}


def _hold(db, org_id, **custodias):
    from app.models.collaboration import CollaborationLegalHold

    fila = CollaborationLegalHold(
        organization_id=org_id, case_reference="CASO-1",
        custodian_user_ids=custodias.get("usuarios") or [],
        custodian_client_ids=custodias.get("clientes") or [],
        channel_ids=custodias.get("canales") or [],
        is_active=True,
    )
    db.add(fila)
    db.commit()
    return fila


# ── Sin ningún caso activo no se retiene nada ───────────────────────────────

def test_sin_casos_activos_no_hay_nada_retenido(db, entorno):
    assert svc.legal_held_message_ids(db, entorno["org_id"]) == set()


def test_un_caso_cerrado_no_retiene(db, entorno):
    """`is_active=False` significa cerrado: deja de proteger."""
    from app.models.collaboration import CollaborationLegalHold

    db.add(CollaborationLegalHold(
        organization_id=entorno["org_id"], case_reference="CERRADO",
        custodian_user_ids=["usuario-custodio"], custodian_client_ids=[],
        channel_ids=[], is_active=False,
    ))
    db.commit()
    assert svc.legal_held_message_ids(db, entorno["org_id"]) == set()


# ── Las tres custodias, una a una ───────────────────────────────────────────

def test_custodia_por_usuario_retiene_sus_mensajes(db, entorno):
    """Es la única que funcionaba antes."""
    _hold(db, entorno["org_id"], usuarios=["usuario-custodio"])
    retenidos = svc.legal_held_message_ids(db, entorno["org_id"])
    assert entorno["mensajes"]["de_custodio"].id in retenidos
    assert entorno["mensajes"]["de_otro"].id not in retenidos


def test_EL_HALLAZGO_custodia_por_CLIENTE_retiene_sus_mensajes(db, entorno):
    """Antes no retenía nada: `custodian_client_ids` se recogía y no se usaba,
    así que los mensajes de un cliente bajo custodia se purgaban."""
    _hold(db, entorno["org_id"], clientes=["cliente-custodio"])
    retenidos = svc.legal_held_message_ids(db, entorno["org_id"])
    assert entorno["mensajes"]["de_cliente"].id in retenidos, (
        "la custodia por cliente sigue sin retener: sus mensajes se purgarían"
    )
    assert entorno["mensajes"]["de_otro"].id not in retenidos


def test_EL_HALLAZGO_custodia_por_CANAL_retiene_la_conversacion_entera(db, entorno):
    """El que habría cazado el defecto original.

    Un canal bajo custodia retiene **todos** sus mensajes, incluidos los de quien
    no es custodio: es el canal lo que está retenido. Antes no retenía ninguno.
    """
    _hold(db, entorno["org_id"], canales=[entorno["canal"].id])
    retenidos = svc.legal_held_message_ids(db, entorno["org_id"])
    for clave in ("de_custodio", "de_otro", "de_cliente"):
        assert entorno["mensajes"][clave].id in retenidos, (
            "la custodia por canal no retiene %s" % clave
        )


def test_las_tres_custodias_son_una_disyuncion(db, entorno):
    """Con usuario y canal a la vez se retiene la unión, no la intersección.

    Si fuera intersección, un canal bajo custodia sólo protegería los mensajes de
    los custodios nombrados — y el resto de la conversación se purgaría.
    """
    _hold(db, entorno["org_id"], usuarios=["usuario-custodio"],
          canales=[entorno["canal"].id])
    retenidos = svc.legal_held_message_ids(db, entorno["org_id"])
    assert len(retenidos) == 3


# ── El caso que dejaba la retención sin efecto ──────────────────────────────

def test_EL_HALLAZGO_un_caso_sin_custodios_no_retiene_TODO(db, entorno):
    """El segundo defecto, por el otro lado.

    Un caso activo con las tres listas vacías no añadía ningún filtro, así que la
    consulta devolvía **todos** los mensajes de la organización y el barrido no
    borraba nada nunca. Ahora no retiene nada, que es lo que significa no nombrar
    a nadie.
    """
    _hold(db, entorno["org_id"])
    retenidos = svc.legal_held_message_ids(db, entorno["org_id"])
    assert retenidos == set(), (
        "un caso sin custodios retiene %d mensajes: la retención vuelve a quedar "
        "sin efecto" % len(retenidos)
    )


# ── El barrido, de extremo a extremo ────────────────────────────────────────

def _usuario_admin(db):
    from app.models.user import User
    return db.query(User).filter(User.username == "admin").first()


def test_el_barrido_borra_lo_vencido_cuando_no_hay_custodia(db, entorno):
    """Control de que el barrido funciona: sin hold, los tres se purgan."""
    r = svc.run_retention(db, _usuario_admin(db))
    assert r["deleted"] >= 3
    for m in entorno["mensajes"].values():
        db.refresh(m)
        assert m.status == "deleted"
        assert m.body == "[retention purge]"


def test_EL_BARRIDO_respeta_la_custodia_por_canal(db, entorno):
    """La consecuencia real del defecto, medida donde duele.

    Con el canal bajo custodia, el barrido no puede tocar ninguno de sus
    mensajes. Antes los borraba los tres y sustituía el cuerpo por
    `[retention purge]` — material bajo retención legal, destruido sin aviso.
    """
    _hold(db, entorno["org_id"], canales=[entorno["canal"].id])
    svc.run_retention(db, _usuario_admin(db))
    for clave, m in entorno["mensajes"].items():
        db.refresh(m)
        assert m.status == "visible", "%s se ha purgado estando bajo custodia" % clave
        assert m.body != "[retention purge]"


def test_EL_BARRIDO_respeta_la_custodia_por_cliente(db, entorno):
    _hold(db, entorno["org_id"], clientes=["cliente-custodio"])
    svc.run_retention(db, _usuario_admin(db))
    db.refresh(entorno["mensajes"]["de_cliente"])
    assert entorno["mensajes"]["de_cliente"].status == "visible"
    # Y los que no están bajo custodia sí se purgan: el hold protege lo que
    # nombra, no todo.
    db.refresh(entorno["mensajes"]["de_otro"])
    assert entorno["mensajes"]["de_otro"].status == "deleted"


def test_un_caso_sin_custodios_no_paraliza_la_retencion(db, entorno):
    """El segundo defecto visto desde el barrido: antes no borraba nada."""
    _hold(db, entorno["org_id"])
    r = svc.run_retention(db, _usuario_admin(db))
    assert r["deleted"] >= 3, (
        "un caso vacío ha vuelto a paralizar la retención: %d borrados" % r["deleted"]
    )


# ── Los topes de configuración, que también son de seguridad ────────────────

def test_los_meses_de_retencion_nunca_bajan_de_uno(db):
    """Un cero o un negativo darían un corte en el futuro y el barrido borraría
    **todos** los mensajes, incluidos los de ayer."""
    from app.models.user import User

    org_id = db.query(User.organization_id).filter(User.username == "admin").scalar()
    for entrada in ({"default_months": 0, "max_months": 0},
                    {"default_months": -5, "max_months": -1}):
        v = svc.set_retention_settings(db, org_id, entrada)
        assert v["default_months"] >= 1
        assert v["max_months"] >= 1


def test_un_ajuste_ilegible_cae_a_los_valores_por_defecto(db):
    """Un JSON corrupto en la fila de ajustes no puede dejar la retención sin
    valores ni propagar una excepción a quien pide el barrido."""
    from app.models.settings import AppSetting
    from app.models.user import User

    org_id = db.query(User.organization_id).filter(User.username == "admin").scalar()
    db.add(AppSetting(
        organization_id=org_id, key=svc.RETENTION_SETTINGS_KEY,
        value="{esto no es json",
    ))
    db.commit()
    assert svc.get_retention_settings(db, org_id) == svc.RETENCION_POR_DEFECTO


def test_no_se_puede_crear_una_politica_por_encima_del_tope(db):
    from fastapi import HTTPException

    from app.models.user import User

    usuario = db.query(User).filter(User.username == "admin").first()
    svc.set_retention_settings(db, usuario.organization_id,
                               {"default_months": 12, "max_months": 24})
    with pytest.raises((HTTPException, ErrorDeDominio)) as e:
        svc.create_policy(db, usuario, {
            "name": "demasiado", "scope": "workspace", "target_id": None,
            "retention_months": 99, "apply_to": "messages",
        })
    assert e.value.status_code == 422
