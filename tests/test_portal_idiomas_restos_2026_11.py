"""Portal en 8 idiomas, restos (16-11-2026).

- Errores que ve el cliente: llegan con codigo estable y datos
  (`{detail, code, params}`); `detail` sigue en castellano.
- Comentarios automaticos de un ticket (IA, escalado): guardan plantilla y
  datos; el portal los pinta en el idioma del cliente.
- Contenido de operadores (avisos, wiki del portal, catalogo): traducido al
  idioma del cliente con el servicio de traduccion (doble del proveedor: nunca
  se llama a la IA real), con cache, y el original si la empresa no traduce.
"""
import json
from types import SimpleNamespace

import pytest

from app.core import codigos_de_error as cde
from app.models.settings import AppSetting
from app.services.traduccion import proveedores as _prov
from app.services.traduccion import textos_del_sistema as tds
from app.services.traduccion.idiomas import IDIOMAS_DEL_PORTAL
from app.services.traduccion.proveedores.base import ProveedorDeTraduccion, Traducido
from tests.conftest import auth


# ── Dobles y ayudas ──────────────────────────────────────────────────────────

class ProveedorDoble(ProveedorDeTraduccion):
    """Traduce poniendo `[destino]` delante; dice que el origen es `es`."""
    nombre = "doble"

    def __init__(self):
        self.llamadas = []

    def admite(self, destino):
        return True

    def traducir(self, textos, destino, origen, glosarios):
        self.llamadas.append({"textos": list(textos), "destino": destino})
        return [Traducido(f"[{destino}] {t}", origen or "es") for t in textos]


@pytest.fixture
def doble(monkeypatch):
    p = ProveedorDoble()
    for nombre in ("ai", "deepl", "azure"):
        monkeypatch.setitem(_prov.FABRICAS, nombre, lambda db, org, user, _p=p: _p)
    return p


def _ajuste(db, org, clave, valor):
    from app.services.settings_service import invalidate_cache
    fila = db.query(AppSetting).filter(AppSetting.key == clave, AppSetting.organization_id == org).first()
    if fila is None:
        db.add(AppSetting(key=clave, value=str(valor), organization_id=org))
    else:
        fila.value = str(valor)
    db.commit()
    invalidate_cache(clave)


def _proyecto(client, token, code):
    r = client.post("/api/v1/projects", headers=auth(token), json={
        "name": f"Proyecto {code}", "code": code, "description": "x", "status": "active",
        "billing_type": "time_material", "is_billable": True})
    assert r.status_code in (200, 201), r.text
    return r.json()["data"]["id"]


def _cliente_del_portal(client, token, db, code="PIR", idioma="fr"):
    """Crea un cliente del portal (con su proyecto) y devuelve (email, clave, ClientUser, id del proyecto)."""
    from app.models.client_portal import ClientUser
    pid = _proyecto(client, token, code)
    # .test es un dominio reservado: email-validator lo rechaza (422); se usa uno normal.
    email, clave = f"{code.lower()}@cliente-portal.com", "ClavePortal123!"
    r = client.post("/api/v1/portal/clients", headers=auth(token), json={
        "project_ids": [pid], "full_name": "Cliente Portal", "email": email, "password": clave,
        "can_request_changes": True, "language": idioma})
    assert r.status_code in (200, 201), r.text
    return email, clave, db.query(ClientUser).filter(ClientUser.email == email).one(), pid


def _entrar(client, email, clave):
    r = client.post("/api/v1/portal/auth/login", json={"email": email, "password": clave})
    assert r.status_code == 200, r.text


# ── Errores con codigo ───────────────────────────────────────────────────────

def test_catalogo_de_codigos_y_textos():
    assert cde.texto("contrasena_corta", {"n": 12}) == "La contraseña debe tener al menos 12 caracteres"
    e = cde.error(404, "ticket_no_encontrado")
    assert (e.status_code, e.detail, e.code, e.params) == (404, "Ticket no encontrado", "ticket_no_encontrado", {})
    # `ErrorConCodigo` sigue siendo un ValueError con el texto de siempre.
    v = cde.ErrorConCodigo("encuesta_ya_respondida")
    assert isinstance(v, ValueError) and str(v) == "Esta encuesta ya ha sido respondida"
    d = cde.desde_valor(400, v)
    assert (d.status_code, d.code, d.detail) == (400, "encuesta_ya_respondida", str(v))
    # Un ValueError cualquiera: el texto tal cual, sin codigo.
    assert cde.desde_valor(404, ValueError("otra cosa")).code is None


def test_codigos_traducidos_en_los_8_diccionarios_del_portal():
    """Cada codigo tiene su `err_srv.<codigo>` en los 8 idiomas del portal."""
    import pathlib
    import re
    raiz = pathlib.Path(__file__).resolve().parents[1] / "frontend" / "src" / "i18n" / "portal"
    for idioma in IDIOMAS_DEL_PORTAL:
        fuente = (raiz / f"{idioma}.ts").read_text(encoding="utf-8")
        claves = set(re.findall(r'"err_srv\.([a-z_]+)"\s*:', fuente))
        assert set(cde.MENSAJES) <= claves, (idioma, set(cde.MENSAJES) - claves)


def test_login_fallido_llega_con_codigo(client, admin_token, db):
    email, _, _, _ = _cliente_del_portal(client, admin_token, db, code="PIL")
    # La clave mal puesta ha de cumplir el esquema (min. 8): con «mal» el 422 salia antes que el 401.
    r = client.post("/api/v1/portal/auth/login", json={"email": email, "password": "ClaveMala123!"})
    assert r.status_code == 401
    cuerpo = r.json()
    assert cuerpo["code"] == "credenciales_incorrectas" and cuerpo["params"] == {}
    assert cuerpo["detail"] == "Email o contraseña incorrectos"


def test_ticket_ajeno_o_inexistente_llega_con_codigo(client, admin_token, db):
    email, clave, _, _ = _cliente_del_portal(client, admin_token, db, code="PIT")
    _entrar(client, email, clave)
    r = client.get("/api/v1/sd/tickets/client/no-existe")
    assert r.status_code == 404
    assert (r.json()["code"], r.json()["detail"]) == ("ticket_no_encontrado", "Ticket no encontrado")


def test_encuesta_inexistente_llega_con_codigo(client, admin_token, db):
    email, clave, _, _ = _cliente_del_portal(client, admin_token, db, code="PIE")
    _entrar(client, email, clave)
    r = client.post("/api/v1/portal/surveys/no-existe/respond", json={"satisfaction_score": 5})
    assert r.status_code in (404, 422)
    if r.status_code == 404:
        assert r.json()["code"] == "encuesta_no_encontrada"


def test_error_sin_codigo_no_cambia_la_respuesta(client, admin_token):
    # 22-11-2026: este 404 ya lleva código (`no_encontrado`, que=ticket; cuota de
    # errores sin código a cero). Lo que se sigue exigiendo: el `detail` en
    # castellano no cambia (compatibilidad) y el código va aparte, con sus params.
    r = client.get("/api/v1/sd/tickets/no-existe", headers=auth(admin_token))
    assert r.status_code == 404
    assert r.json()["detail"] == "Ticket no encontrado"
    assert (r.json()["code"], r.json()["params"]) == ("no_encontrado", {"que": "ticket"})


# ── Comentarios automaticos ──────────────────────────────────────────────────

def test_plantillas_de_comentario_en_los_8_idiomas():
    for codigo, plantilla in tds.COMENTARIOS.items():
        assert set(IDIOMAS_DEL_PORTAL) <= set(plantilla), codigo
        for texto in plantilla.values():
            assert "🤖" not in texto and "🔺" not in texto


def test_comentario_guarda_plantilla_y_se_repinta_en_otro_idioma():
    campos = tds.comentario("escalado", {"level": "L2", "reason": "Caída general"}, "es")
    assert campos["body"] == "Escalado a L2: Caída general" and campos["language"] == "es"
    assert campos["system_template"] == "escalado"
    comentario = SimpleNamespace(id="c1", **{k: campos[k] for k in ("system_template", "system_params")})
    ticket = SimpleNamespace(system_template=None, system_params=None, comments=[comentario])
    salida = {"title": "t", "comments": [{"id": "c1", "body": campos["body"], "author_type": "agent"},
                                         {"id": "c2", "body": "escrito por una persona"}]}
    tds.en_idioma(salida, ticket, "de")
    assert salida["comments"][0]["body"] == "Eskaliert an L2: Caída general"
    assert salida["comments"][0]["author_type"] == "system" and salida["comments"][0]["language"] == "de"
    assert salida["comments"][1]["body"] == "escrito por una persona"


def test_resolucion_por_ia_en_el_idioma_del_cliente(client, admin_token, db):
    from app.models.service_desk import Ticket, TicketComment
    from app.services.service_desk.ai_auto_resolution_service import _post_resolution_comment
    email, clave, cliente, _ = _cliente_del_portal(client, admin_token, db, code="PIA", idioma="it")
    _entrar(client, email, clave)
    r = client.post("/api/v1/sd/tickets/client", json={
        "title": "No puedo entrar", "description": "Desde ayer", "ticket_type": "incident"})
    assert r.status_code == 200, r.text
    tid = r.json()["data"]["id"]
    ticket = db.get(Ticket, tid)
    _post_resolution_comment(db, ticket, "Restablece la contraseña desde el enlace.", is_auto=True)
    db.commit()
    c = db.query(TicketComment).filter(TicketComment.ticket_id == tid,
                                       TicketComment.system_template.isnot(None)).one()
    assert c.system_template == "ia_resolucion_automatica"
    assert json.loads(c.system_params) == {"text": "Restablece la contraseña desde el enlace."}
    # Se guarda en el idioma del solicitante (su ficha: italiano).
    assert c.language == "it" and c.body.startswith("**Risoluzione automatica tramite IA:**")

    # El cliente cambia su ficha a polaco: el portal lo pinta en polaco.
    cliente.language = "pl"
    db.commit()
    detalle = client.get(f"/api/v1/sd/tickets/client/{tid}").json()["data"]
    item = next(x for x in detalle["comments"] if x["id"] == c.id)
    assert item["body"].startswith("**Automatyczne rozwiązanie przez AI:**")
    assert item["author_type"] == "system"


# ── Contenido de operadores, traducido ───────────────────────────────────────

def _anuncio(client, token, titulo="Mantenimiento el sábado", cuerpo="El portal no estará disponible."):
    r = client.post("/api/v1/sd/announcements", headers=auth(token), json={
        "title": titulo, "body": cuerpo, "type": "info", "show_to_clients": True})
    assert r.status_code == 200, r.text
    return r.json()["data"]["id"]


def test_avisos_sin_traduccion_activada_salen_tal_cual(client, admin_token, db, doble):
    email, clave, cliente, _ = _cliente_del_portal(client, admin_token, db, code="PAV")
    # TRANSLATION_ENABLED es True por defecto desde el 16-11-2026: se apaga a proposito.
    _ajuste(db, cliente.organization_id, "TRANSLATION_ENABLED", "false")
    aid = _anuncio(client, admin_token)
    _entrar(client, email, clave)
    items = client.get("/api/v1/sd/announcements", params={"lang": "fr"}).json()["items"]
    a = next(x for x in items if x["id"] == aid)
    assert a["title"] == "Mantenimiento el sábado" and "translated_from" not in a
    assert doble.llamadas == []


def test_avisos_traducidos_al_idioma_del_portal_y_cacheados(client, admin_token, db, doble):
    email, clave, cliente, _ = _cliente_del_portal(client, admin_token, db, code="PAT")
    _ajuste(db, cliente.organization_id, "TRANSLATION_ENABLED", "true")
    aid = _anuncio(client, admin_token)
    _entrar(client, email, clave)

    items = client.get("/api/v1/sd/announcements", params={"lang": "de"}).json()["items"]
    a = next(x for x in items if x["id"] == aid)
    assert a["title"] == "[de] Mantenimiento el sábado"
    assert a["body"] == "[de] El portal no estará disponible."
    assert a["language"] == "de" and a["translated_from"]
    pagadas = len(doble.llamadas)
    assert pagadas >= 1

    # Segunda lectura: de la cache, sin volver a llamar al proveedor.
    client.get("/api/v1/sd/announcements", params={"lang": "de"})
    assert len(doble.llamadas) == pagadas

    # Sin `lang`: el idioma de la ficha del cliente (fr).
    items = client.get("/api/v1/sd/announcements").json()["items"]
    assert next(x for x in items if x["id"] == aid)["title"] == "[fr] Mantenimiento el sábado"


def test_canal_portal_desactivado_sale_el_original(client, admin_token, db, doble):
    email, clave, cliente, _ = _cliente_del_portal(client, admin_token, db, code="PAC")
    _ajuste(db, cliente.organization_id, "TRANSLATION_ENABLED", "true")
    _ajuste(db, cliente.organization_id, "TRANSLATION_CHANNELS", "ticket,kb")
    aid = _anuncio(client, admin_token)
    _entrar(client, email, clave)
    items = client.get("/api/v1/sd/announcements", params={"lang": "de"}).json()["items"]
    assert next(x for x in items if x["id"] == aid)["title"] == "Mantenimiento el sábado"
    assert doble.llamadas == []


def test_el_operador_lee_los_avisos_sin_traducir(client, admin_token, db, doble):
    _, _, cliente, _ = _cliente_del_portal(client, admin_token, db, code="PAO")
    _ajuste(db, cliente.organization_id, "TRANSLATION_ENABLED", "true")
    aid = _anuncio(client, admin_token)
    items = client.get("/api/v1/sd/announcements", headers=auth(admin_token), params={"lang": "de"}).json()["items"]
    assert next(x for x in items if x["id"] == aid)["title"] == "Mantenimiento el sábado"
    assert doble.llamadas == []


def test_catalogo_traducido_con_sus_servicios(client, admin_token, db, doble):
    email, clave, cliente, _ = _cliente_del_portal(client, admin_token, db, code="PCA")
    _ajuste(db, cliente.organization_id, "TRANSLATION_ENABLED", "true")
    r = client.post("/api/v1/sd/catalog/categories", headers=auth(admin_token),
                    json={"name": "Accesos", "description": "Altas y bajas"})
    assert r.status_code == 200, r.text
    cat_id = r.json()["data"]["id"]
    r = client.post("/api/v1/sd/catalog/services", headers=auth(admin_token), json={
        "category_id": cat_id, "name": "Alta de usuario", "description": "Crear la cuenta",
        "is_visible_to_clients": True})
    assert r.status_code == 200, r.text
    _entrar(client, email, clave)
    items = client.get("/api/v1/sd/catalog", params={"public_only": True, "lang": "de"}).json()["items"]
    cat = next(c for c in items if c["id"] == cat_id)
    assert cat["name"] == "[de] Accesos" and cat["description"] == "[de] Altas y bajas"
    serv = cat["services"][0]
    assert serv["name"] == "[de] Alta de usuario" and serv["description"] == "[de] Crear la cuenta"


def test_wiki_del_portal_traducida(client, admin_token, db, doble):
    from app.models.epics import WikiPage, WikiSpace
    email, clave, cliente, pid = _cliente_del_portal(client, admin_token, db, code="PWK")
    _ajuste(db, cliente.organization_id, "TRANSLATION_ENABLED", "true")
    espacio = WikiSpace(project_id=pid, name="Espacio", slug="espacio-pwk", is_active=True,
                        organization_id=cliente.organization_id)
    db.add(espacio)
    db.flush()
    pagina = WikiPage(space_id=espacio.id, title="Guía de acceso", slug="guia-pwk", content="Entra con tu correo.",
                      content_text="Entra con tu correo.", visibility="portal", is_published=True, is_active=True,
                      organization_id=cliente.organization_id)
    db.add(pagina)
    db.commit()
    _entrar(client, email, clave)
    lista = client.get("/api/v1/portal/wiki/pages", params={"lang": "en"}).json()["items"]
    assert next(p for p in lista if p["id"] == pagina.id)["title"] == "[en] Guía de acceso"
    detalle = client.get(f"/api/v1/portal/wiki/pages/{pagina.id}", params={"lang": "en"}).json()["data"]
    assert (detalle["title"], detalle["content"]) == ("[en] Guía de acceso", "[en] Entra con tu correo.")


def test_idioma_del_lector():
    from app.services.traduccion.contenido_del_portal import idioma_del_lector
    cliente = SimpleNamespace(language="pl")
    assert idioma_del_lector(cliente, "it") == "it"
    assert idioma_del_lector(cliente, "ja") == "pl"      # no es del portal: el de la ficha
    assert idioma_del_lector(cliente, None) == "pl"
    assert idioma_del_lector(SimpleNamespace(language=None), None) is None
