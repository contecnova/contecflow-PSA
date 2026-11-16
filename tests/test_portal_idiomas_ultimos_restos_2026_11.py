"""Portal en 8 idiomas, ultimos restos (16-11-2026, tercera pasada).

- Errores con codigo que antes llegaban sin el: `/portal/collaboration/*`, chat
  de IA del portal, sesion del portal (formularios dinamicos), modulos de IA y
  motivo de denegacion del asistente del portal (codigo + datos).
- Comentarios del sistema en la vista del operador: en el idioma de quien mira.
- Contenido traducido para el portal: lleva el original (`original`) para la
  marca «Traducido automaticamente» con «Ver original»; wiki por bloques;
  etiquetas de los formularios dinamicos.
- Migracion 177: `portal` anadido a `TRANSLATION_CHANNELS` ya guardado.
- Aviso del chat de IA (tope de gasto) en el idioma del cliente.

El proveedor de traduccion es un doble: nunca se llama a la IA real.
"""
import importlib.util
import json
import pathlib
from types import SimpleNamespace

import pytest

from app.core import codigos_de_error as cde
from app.core.errores import ErrorDeDominio
from app.services.traduccion import proveedores as _prov
from app.services.traduccion import textos_del_sistema as tds
from app.services.traduccion.idiomas import IDIOMAS_DEL_PORTAL
from tests.conftest import auth
from tests.test_portal_idiomas_restos_2026_11 import (
    ProveedorDoble, _ajuste, _anuncio, _cliente_del_portal, _entrar,
)


@pytest.fixture
def doble(monkeypatch):
    p = ProveedorDoble()
    for nombre in ("ai", "deepl", "azure"):
        monkeypatch.setitem(_prov.FABRICAS, nombre, lambda db, org, user, _p=p: _p)
    return p


# ── 1. Errores con codigo ────────────────────────────────────────────────────

def test_codigos_nuevos_en_el_catalogo_y_en_los_8_diccionarios():
    nuevos = {"herramienta_sin_politica", "acceso_denegado", "mensaje_obligatorio", "modulo_ia_no_activado",
              "modulo_ia_desactivado", "modulo_ia_limite_diario", "sin_acceso_conversacion", "sin_acceso",
              "conversacion_obligatoria", "demasiados_mensajes"}
    assert nuevos <= set(cde.MENSAJES)
    raiz = pathlib.Path(__file__).resolve().parents[1] / "frontend" / "src" / "i18n" / "portal"
    for idioma in IDIOMAS_DEL_PORTAL:
        fuente = (raiz / f"{idioma}.ts").read_text(encoding="utf-8")
        for codigo in nuevos:
            assert f'"err_srv.{codigo}"' in fuente, (idioma, codigo)
    # `detail` sigue siendo el de antes.
    assert cde.texto("demasiados_mensajes", {"segundos": 7}) == "Portal message rate limit exceeded. Retry in 7s"
    assert cde.texto("herramienta_sin_politica", {"herramienta": "x"}) == \
        "La herramienta 'x' no tiene política de acceso: no se ejecuta."


def test_denegacion_del_asistente_con_codigo_y_datos():
    from app.services.ai_chat.tool_execution.politica import (
        codigo_de_denegacion_del_portal, denegacion_del_portal,
    )
    from app.services.service_desk.asistente_del_portal import _exigir
    activo = SimpleNamespace(is_active=True, organization_id="org-1")
    assert codigo_de_denegacion_del_portal(None, activo, "portal_ticket_status") is None
    assert codigo_de_denegacion_del_portal(None, activo, "borrar_todo") == \
        ("herramienta_sin_politica", {"herramienta": "borrar_todo"})
    assert codigo_de_denegacion_del_portal(None, None, "portal_ticket_status") == ("acceso_denegado", {})
    # El texto de siempre, para quien lo siga leyendo.
    assert denegacion_del_portal(None, None, "portal_ticket_status") == "Acceso denegado"
    with pytest.raises(ErrorDeDominio) as e:
        _exigir(None, activo, "borrar_todo")
    assert (e.value.status_code, e.value.code, e.value.params) == \
        (403, "herramienta_sin_politica", {"herramienta": "borrar_todo"})


def test_modulo_de_ia_apagado_con_codigo(monkeypatch):
    from app.core import modulos_ia
    from app.services import governance_service
    monkeypatch.setattr(governance_service, "config_de_modulo",
                        lambda db, org, modulo: SimpleNamespace(is_enabled=False, max_actions_per_day=None))
    with pytest.raises(ErrorDeDominio) as e:
        modulos_ia.comprobar_modulo(None, "org-1", "portal_ai")
    assert (e.value.status_code, e.value.code, e.value.params) == (403, "modulo_ia_desactivado", {"modulo": "portal_ai"})
    assert e.value.detail == "El módulo de IA «portal_ai» está desactivado en Gobierno de IA"


def test_chat_de_ia_del_portal_sin_mensaje_con_codigo(client, admin_token, db):
    email, clave, _, _ = _cliente_del_portal(client, admin_token, db, code="PUC")
    _entrar(client, email, clave)
    r = client.post("/api/v1/portal/ai-chat", json={"message": ""})
    assert r.status_code == 400
    cuerpo = r.json()
    assert (cuerpo["code"], cuerpo["detail"]) == ("mensaje_obligatorio", "message required")


def test_mensajes_del_portal_con_codigo(client, admin_token, db):
    email, clave, _, _ = _cliente_del_portal(client, admin_token, db, code="PUM")
    _entrar(client, email, clave)
    r = client.get("/api/v1/portal/collaboration/conversations/no-existe/messages")
    assert r.status_code == 403 and r.json()["code"] == "sin_acceso_conversacion"
    r = client.post("/api/v1/portal/collaboration/messages", json={"body": "hola"})
    assert r.status_code == 400 and r.json()["code"] == "conversacion_obligatoria"
    r = client.post("/api/v1/portal/collaboration/messages", json={"conversation_id": "no-existe", "body": "hola"})
    assert r.status_code == 404 and r.json()["code"] == "conversacion_no_encontrada"
    r = client.post("/api/v1/portal/collaboration/messages/no-existe/reactions", json={"emoji": "ok"})
    assert r.status_code == 404 and r.json()["code"] == "mensaje_no_encontrado"
    r = client.post("/api/v1/portal/collaboration/conversations/no-existe/read", json={"last_message_id": "x"})
    assert r.status_code == 403 and r.json()["code"] == "sin_acceso"


def test_formularios_dinamicos_sin_sesion_con_codigo(client):
    client.cookies.clear()
    r = client.get("/api/v1/sd/dynamic-forms/public")
    assert r.status_code == 401
    assert (r.json()["code"], r.json()["detail"]) == ("sesion_invalida", "Autenticacion requerida")


# ── 2. Comentarios del sistema en la vista del operador ──────────────────────

def test_comentarios_en_idioma_solo_toca_los_del_sistema():
    campos = tds.comentario("escalado", {"level": "L2", "reason": "Caída"}, "it")
    c = SimpleNamespace(id="c1", **{k: campos[k] for k in ("system_template", "system_params")})
    ticket = SimpleNamespace(system_template="alm_request", system_params="{}", comments=[c])
    salida = {"title": "Titulo", "comments": [{"id": "c1", "body": campos["body"]}, {"id": "c2", "body": "x"}]}
    tds.comentarios_en_idioma(salida, ticket, "zh")
    assert salida["comments"][0]["body"] == "已升级至 L2：Caída" and salida["comments"][0]["language"] == "zh"
    assert salida["comments"][1]["body"] == "x" and salida["title"] == "Titulo"


def test_el_operador_lee_el_comentario_del_sistema_en_su_idioma(client, admin_token, db):
    from app.models.service_desk import TicketComment
    from app.models.user import User, UserPreference
    email, clave, _, _ = _cliente_del_portal(client, admin_token, db, code="PUO", idioma="it")
    _entrar(client, email, clave)
    r = client.post("/api/v1/sd/tickets/client", json={
        "title": "No funciona", "description": "Desde ayer", "ticket_type": "incident"})
    assert r.status_code == 200, r.text
    tid = r.json()["data"]["id"]
    from app.models.service_desk import Ticket
    ticket = db.get(Ticket, tid)
    db.add(TicketComment(ticket_id=tid, organization_id=ticket.organization_id, is_public=False,
                         **tds.comentario("escalado", {"level": "L2", "reason": "Caída"}, "it")))
    admin = db.query(User).filter(User.username == "admin").one()
    pref = db.query(UserPreference).filter(UserPreference.user_id == admin.id).first()
    if pref is None:
        pref = UserPreference(user_id=admin.id, organization_id=admin.organization_id)
        db.add(pref)
    pref.language = "en"
    db.commit()

    detalle = client.get(f"/api/v1/sd/tickets/{tid}", headers=auth(admin_token)).json()["data"]
    item = next(x for x in detalle["comments"] if x["body"].startswith("Escalated"))
    assert item["body"] == "Escalated to L2: Caída" and item["language"] == "en"
    assert item["author_type"] == "system"


def test_traduccion_bajo_demanda_de_un_comentario_del_sistema():
    from app.services.traduccion.mensajes import Mensaje, _de_plantilla
    campos = tds.comentario("ia_resolucion_automatica", {"text": "Reinicia"}, "es")
    fila = SimpleNamespace(**{k: campos[k] for k in ("system_template", "system_params")})
    m = Mensaje("ticket_comment", "c1", "org", {"body": campos["body"]}, "es", "ticket", fila)
    salida = []
    assert _de_plantilla(m, "en", salida)
    assert salida[0]["field"] == "body" and salida[0]["origin"] == "system"
    assert salida[0]["text"] == "**Automatic resolution by AI:**\n\nReinicia"


# ── 3. Contenido traducido con su original ───────────────────────────────────

def test_avisos_traducidos_llevan_el_original(client, admin_token, db, doble):
    email, clave, cliente, _ = _cliente_del_portal(client, admin_token, db, code="PUA")
    _ajuste(db, cliente.organization_id, "TRANSLATION_ENABLED", "true")
    aid = _anuncio(client, admin_token)
    _entrar(client, email, clave)
    a = next(x for x in client.get("/api/v1/sd/announcements", params={"lang": "pl"}).json()["items"]
             if x["id"] == aid)
    assert a["title"] == "[pl] Mantenimiento el sábado" and a["translated_from"]
    assert a["original"] == {"title": "Mantenimiento el sábado", "body": "El portal no estará disponible."}


def test_aviso_sin_traducir_no_lleva_original(client, admin_token, db, doble):
    email, clave, _, _ = _cliente_del_portal(client, admin_token, db, code="PUN")
    aid = _anuncio(client, admin_token)
    _entrar(client, email, clave)
    a = next(x for x in client.get("/api/v1/sd/announcements", params={"lang": "pl"}).json()["items"]
             if x["id"] == aid)
    assert "original" not in a and "translated_from" not in a


def test_wiki_en_bloques_traducida_bloque_a_bloque(client, admin_token, db, doble):
    from app.models.epics import WikiPage, WikiSpace
    email, clave, cliente, pid = _cliente_del_portal(client, admin_token, db, code="PUW")
    _ajuste(db, cliente.organization_id, "TRANSLATION_ENABLED", "true")
    espacio = WikiSpace(project_id=pid, name="Espacio", slug="espacio-puw", is_active=True,
                        organization_id=cliente.organization_id)
    db.add(espacio)
    db.flush()
    bloques = [{"type": "heading1", "content": "Acceso"}, {"type": "paragraph", "content": "Entra con tu correo."},
               {"type": "code", "content": "ssh usuario@host"}]
    pagina = WikiPage(space_id=espacio.id, title="Guía", slug="guia-puw", content=json.dumps(bloques),
                      content_text="Acceso", visibility="portal", is_published=True, is_active=True,
                      organization_id=cliente.organization_id)
    db.add(pagina)
    db.commit()
    _entrar(client, email, clave)
    d = client.get(f"/api/v1/portal/wiki/pages/{pagina.id}", params={"lang": "en"}).json()["data"]
    assert isinstance(d["content"], list)
    assert d["title"] == "[en] Guía" and d["original"] == {"title": "Guía"}
    titulo, parrafo, codigo = d["content"]
    assert titulo["content"] == "[en] Acceso" and titulo["original"] == {"content": "Acceso"}
    assert parrafo["content"] == "[en] Entra con tu correo."
    assert codigo["content"] == "ssh usuario@host" and "translated_from" not in codigo
    # Nunca se manda el JSON entero al proveedor.
    assert not any("[{" in t for llamada in doble.llamadas for t in llamada["textos"])


def test_contenido_de_wiki():
    from app.services.client_portal_service.wiki_y_encuestas import contenido_de_wiki
    assert contenido_de_wiki(None) == []
    assert contenido_de_wiki('[{"type": "paragraph", "content": "x"}]') == [{"type": "paragraph", "content": "x"}]
    assert contenido_de_wiki("Texto plano") == "Texto plano"
    assert contenido_de_wiki('"cadena"') == '"cadena"'


def test_etiquetas_de_formularios_dinamicos_traducidas(client, admin_token, db, doble):
    email, clave, cliente, _ = _cliente_del_portal(client, admin_token, db, code="PUF")
    _ajuste(db, cliente.organization_id, "TRANSLATION_ENABLED", "true")
    _entrar(client, email, clave)
    reglas = client.get("/api/v1/sd/dynamic-forms/public", params={"lang": "de"}).json()["data"]
    campo = next(f for f in reglas["fields"] if f["id"] == "affected_environment")
    assert campo["label"] == "[de] Entorno afectado" and campo["original"] == {"label": "Entorno afectado"}
    # Las opciones son valores que se guardan: no se traducen.
    assert campo["options"] == ["produccion", "preproduccion", "desarrollo"]


# ── 4. Migracion 177: canal `portal` en los valores guardados ────────────────

def _migracion_177():
    ruta = pathlib.Path(__file__).resolve().parents[1] / "alembic" / "versions" / "177_portal_idiomas_restos.py"
    spec = importlib.util.spec_from_file_location("migracion_177", ruta)
    modulo = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(modulo)
    return modulo


def test_migracion_177_anade_y_quita_el_canal_portal():
    m = _migracion_177()
    assert m.con_canal("ticket,kb") == "ticket,kb,portal"
    assert m.con_canal(" ticket , email ") == "ticket,email,portal"
    assert m.con_canal("ticket,portal") is None          # sin duplicar
    assert m.con_canal("ticket,PORTAL") is None
    assert m.con_canal("") is None and m.con_canal(None) is None   # vacio: ningun canal, se respeta
    assert m.sin_canal("ticket,kb,portal") == "ticket,kb"
    assert m.sin_canal("portal") == ""
    assert m.sin_canal("ticket,kb") is None


def test_migracion_177_reescribe_app_settings():
    import sqlalchemy as sa
    m = _migracion_177()
    motor = sa.create_engine("sqlite://")
    with motor.begin() as con:
        con.execute(sa.text("CREATE TABLE app_settings (id TEXT PRIMARY KEY, key TEXT, value TEXT)"))
        con.execute(sa.text("INSERT INTO app_settings VALUES ('1', 'TRANSLATION_CHANNELS', 'ticket,kb'), "
                            "('2', 'TRANSLATION_CHANNELS', 'kb,portal'), ('3', 'TRANSLATION_CHANNELS', ''), "
                            "('4', 'OTRA', 'ticket')"))
        m._reescribir(con, m.con_canal)
        valores = dict(con.execute(sa.text("SELECT id, value FROM app_settings")).fetchall())
        assert valores == {"1": "ticket,kb,portal", "2": "kb,portal", "3": "", "4": "ticket"}
        m._reescribir(con, m.sin_canal)
        valores = dict(con.execute(sa.text("SELECT id, value FROM app_settings")).fetchall())
        assert valores == {"1": "ticket,kb", "2": "kb", "3": "", "4": "ticket"}


# ── Aviso del chat de IA en el idioma del cliente ────────────────────────────

def test_aviso_de_limite_de_ia_en_los_8_idiomas():
    assert set(IDIOMAS_DEL_PORTAL) <= set(tds.AVISOS["ia_limite_de_uso"])
    assert tds.aviso("ia_limite_de_uso", "de").startswith("Der Assistent")
    assert tds.aviso("ia_limite_de_uso", "ja") == tds.AVISOS["ia_limite_de_uso"]["es"]
