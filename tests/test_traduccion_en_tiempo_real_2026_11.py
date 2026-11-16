"""Traduccion en tiempo real operador <-> cliente (16-11-2026).

Sin red: el proveedor de traduccion es un doble (`proveedores.FABRICAS`) y los
proveedores HTTP (DeepL, Azure) reciben un doble de su salida HTTP. Nunca se
llama a la IA real.
"""
import json

import pytest

from app.models.settings import AppSetting
from app.models.service_desk import Ticket, TicketComment
from app.models.traduccion import MessageTranslation, TranslationCacheEntry
from app.services.traduccion import glosario, idiomas
from app.services.traduccion import proveedores as _prov
from app.services.traduccion.proveedores.base import ErrorDeTraduccion, ProveedorDeTraduccion, Traducido
from tests.conftest import auth


# ── Dobles ────────────────────────────────────────────────────────────────────

class ProveedorDoble(ProveedorDeTraduccion):
    """Traduce poniendo `[destino]` delante; detecta `zh` si hay Han, si no `es`."""
    nombre = "doble"

    def __init__(self, fallo=None):
        self.llamadas = []
        self.fallo = fallo

    def admite(self, destino):
        return True

    def traducir(self, textos, destino, origen, glosarios):
        self.llamadas.append({"textos": list(textos), "destino": destino, "origen": origen, "glosarios": glosarios})
        if self.fallo:
            raise ErrorDeTraduccion(self.fallo)
        salida = []
        for t, g in zip(textos, glosarios):
            for termino, s in g:
                t = termino.patron().sub(s, t)
            detectado = origen or ("zh" if any("一" <= c <= "鿿" for c in t) else "es")
            salida.append(Traducido(f"[{destino}] {t}", detectado))
        return salida


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


def _org(client, token, db):
    r = client.post("/api/v1/sd/tickets", headers=auth(token), json={
        "title": "empresa", "description": "empresa", "ticket_type": "incident"})
    return r.json()["data"]["id"], db.query(Ticket).filter(Ticket.id == r.json()["data"]["id"]).one().organization_id


def _activar(db, org, **extra):
    _ajuste(db, org, "TRANSLATION_ENABLED", "true")
    for k, v in extra.items():
        _ajuste(db, org, k, v)


# ── Idiomas y deteccion local ────────────────────────────────────────────────

def test_deteccion_local_por_escritura_y_palabras():
    assert idiomas.detectar("我的打印机坏了，请帮忙看一下")[0] == "zh"
    assert idiomas.detectar("プリンターが壊れました。助けてください")[0] == "ja"
    assert idiomas.detectar("Привіт, у мене не працює принтер")[0] == "uk"
    es, c_es = idiomas.detectar("Hola, la impresora no funciona desde ayer y necesito ayuda con el problema")
    en, c_en = idiomas.detectar("Hello, the printer is not working since yesterday and I need help with this issue")
    assert (es, en) == ("es", "en") and c_es > 0.6 and c_en > 0.6
    # Un texto corto no decide: lo detectara el proveedor.
    assert idiomas.detectar_si_seguro("ok", 0.6) is None


def test_normalizacion_de_codigos():
    assert idiomas.normalizar("pt-BR") == "pt"
    assert idiomas.normalizar("zh_TW") == "zh-hant"
    assert idiomas.normalizar("EN") == "en"
    assert idiomas.normalizar("xx") is None


# ── Glosario ─────────────────────────────────────────────────────────────────

def test_glosario_protege_terminos_y_los_restaura():
    t1 = glosario.Termino("Contecflow", {}, False)
    t2 = glosario.Termino("SLA", {"zh": "服务级别协议"}, True)
    pares = glosario.relevantes([t1, t2], "El SLA de contecflow vence <hoy>", "zh")
    assert [p[1] for p in pares] == ["Contecflow", "服务级别协议"]
    marcado = glosario.proteger("El SLA de contecflow vence <hoy>", pares, "<x>", "</x>")
    assert "<x>服务级别协议</x>" in marcado and "<x>Contecflow</x>" in marcado and "&lt;hoy&gt;" in marcado
    assert glosario.desproteger(marcado, "<x>", "</x>") == "El 服务级别协议 de Contecflow vence <hoy>"
    # La huella solo depende de los terminos que aparecen.
    assert glosario.huella(glosario.relevantes([t1], "nada", "zh")) == ""


# ── Servicio ─────────────────────────────────────────────────────────────────

def test_activada_por_defecto_y_apagada_no_sale_nada(client, admin_token, db, doble):
    """16-11-2026: viene activada por defecto; si la empresa la apaga, no sale nada."""
    from app.core.config import settings
    from app.services.traduccion.servicio import traducir
    assert settings.TRANSLATION_ENABLED is True
    _, org = _org(client, admin_token, db)
    _ajuste(db, org, "TRANSLATION_ENABLED", "false")
    r = traducir(db, org, ["你好"], "es", canal="ticket")
    assert r[0].estado == "disabled" and doble.llamadas == []


def test_traduce_cachea_y_no_paga_dos_veces(client, admin_token, db, doble):
    from app.services.traduccion.servicio import traducir
    _, org = _org(client, admin_token, db)
    _activar(db, org)
    a = traducir(db, org, ["我的打印机坏了"], "es", canal="ticket")[0]
    b = traducir(db, org, ["我的打印机坏了"], "es", canal="ticket")[0]
    assert a.estado == b.estado == "translated" and a.origen == "zh"
    assert b.desde_cache and len(doble.llamadas) == 1
    assert db.query(TranslationCacheEntry).filter(TranslationCacheEntry.organization_id == org).count() == 1
    # Mismo idioma: ni proveedor ni cache.
    c = traducir(db, org, ["Hola, la impresora no funciona desde ayer y necesito ayuda"], "es", canal="ticket")[0]
    assert c.estado == "same_language" and len(doble.llamadas) == 1


def test_canal_desactivado(client, admin_token, db, doble):
    from app.services.traduccion.servicio import traducir
    _, org = _org(client, admin_token, db)
    _activar(db, org, TRANSLATION_CHANNELS="ticket")
    assert traducir(db, org, ["你好"], "es", canal="whatsapp")[0].motivo == "channel_disabled"


def test_tope_de_gasto_agotado_degrada(client, admin_token, db, doble, monkeypatch):
    from app.services import ai_provider_service as ia
    from app.services.traduccion.servicio import traducir

    def agotado(db_, org_):
        raise ia.PresupuestoDeIAAgotado("tope")
    monkeypatch.setattr(ia, "_exigir_presupuesto", agotado)
    _, org = _org(client, admin_token, db)
    _activar(db, org)
    r = traducir(db, org, ["你好世界"], "es", canal="ticket")[0]
    assert (r.estado, r.motivo, r.texto) == ("unavailable", "budget_exhausted", None)
    assert doble.llamadas == []


def test_fallo_del_proveedor_nunca_es_parcial(client, admin_token, db, monkeypatch):
    from app.services.traduccion.servicio import traducir
    malo = ProveedorDoble(fallo="timeout")
    monkeypatch.setitem(_prov.FABRICAS, "ai", lambda db_, o, u: malo)
    _, org = _org(client, admin_token, db)
    _activar(db, org)
    rs = traducir(db, org, ["你好", "再见"], "es", canal="ticket")
    assert [r.estado for r in rs] == ["unavailable", "unavailable"]
    assert {r.motivo for r in rs} == {"timeout"}


def test_glosario_llega_al_proveedor(client, admin_token, db, doble):
    from app.services.traduccion.servicio import traducir
    _, org = _org(client, admin_token, db)
    _activar(db, org)
    r = client.post("/api/v1/translation/glossary", headers=auth(admin_token),
                    json={"term": "Contecflow", "translations": {}})
    assert r.status_code == 200, r.text
    traducir(db, org, ["Contecflow 坏了"], "es", canal="ticket")
    assert doble.llamadas[0]["glosarios"][0][0][1] == "Contecflow"


# ── Proveedores con dobles HTTP ──────────────────────────────────────────────

def test_deepl_url_del_plan_glosario_xml_y_deteccion(db):
    from app.services.traduccion.proveedores.deepl import ProveedorDeepL
    hechas = []

    def http(db_, url, **kw):
        hechas.append({"url": url, **kw})
        return {"translations": [{"detected_source_language": "ZH", "text": "La <x>SLA</x> vence"}]}
    p = ProveedorDeepL(db, "org", credenciales={"api_key": "k:fx", "base_url": None}, http=http)
    salida = p.traducir(["SLA 到期"], "es", None, [[(glosario.Termino("SLA", {}, True), "SLA")]])
    assert hechas[0]["url"] == "https://api-free.deepl.com/v2/translate"
    assert hechas[0]["json"]["target_lang"] == "ES" and hechas[0]["json"]["tag_handling"] == "xml"
    assert hechas[0]["headers"]["Authorization"] == "DeepL-Auth-Key k:fx"
    assert (salida[0].texto, salida[0].origen) == ("La SLA vence", "zh")
    with pytest.raises(ErrorDeTraduccion) as e:
        ProveedorDeepL(db, "org", credenciales={"api_key": None}, http=http).traducir(["x"], "es", None, [[]])
    assert e.value.codigo == "provider_not_configured"


def test_deepl_respuesta_incompleta_es_error(db):
    from app.services.traduccion.proveedores.deepl import ProveedorDeepL
    p = ProveedorDeepL(db, "org", credenciales={"api_key": "k"}, http=lambda *a, **k: {"translations": []})
    with pytest.raises(ErrorDeTraduccion) as e:
        p.traducir(["a", "b"], "en", None, [[], []])
    assert e.value.codigo == "incomplete_response"


def test_azure_parametros_region_y_codigos(db):
    from app.services.traduccion.proveedores.azure import ProveedorAzure
    hechas = []

    def http(db_, url, **kw):
        hechas.append({"url": url, **kw})
        return [{"detectedLanguage": {"language": "es"}, "translations": [{"text": "你好", "to": "zh-Hans"}]}]
    p = ProveedorAzure(db, "org", credenciales={"api_key": "k", "region": "westeurope", "endpoint": None}, http=http)
    salida = p.traducir(["hola"], "zh", None, [[]])
    assert hechas[0]["url"] == "https://api.cognitive.microsofttranslator.com/translate"
    assert hechas[0]["params"]["to"] == "zh-Hans" and "textType" not in hechas[0]["params"]
    assert hechas[0]["headers"]["Ocp-Apim-Subscription-Region"] == "westeurope"
    assert (salida[0].texto, salida[0].origen) == ("你好", "es")


def test_proveedor_ia_lee_json_y_rechaza_respuestas_incompletas(monkeypatch, db):
    from app.services import ai_provider_service as ia
    from app.services.traduccion.proveedores.ia import ProveedorIA, instrucciones
    monkeypatch.setattr(ia, "call_ai", lambda *a, **k: 'ok {"items": [{"lang": "zh", "text": "Hola"}]}')
    salida = ProveedorIA(db, "org").traducir(["你好"], "es", None, [[]])
    assert (salida[0].texto, salida[0].origen) == ("Hola", "zh")
    monkeypatch.setattr(ia, "call_ai", lambda *a, **k: '{"items": []}')
    with pytest.raises(ErrorDeTraduccion):
        ProveedorIA(db, "org").traducir(["你好"], "es", None, [[]])
    # Las instrucciones nombran el destino; no hay un texto fijo por idioma.
    assert "Spanish" in instrucciones("es", None, []) and "Chinese" in instrucciones("zh", None, [])


def test_credenciales_solo_de_la_propia_empresa(db):
    from app.core.encryption import encrypt_value
    from app.models.settings import IntegrationCredential
    from app.services.traduccion.proveedores.base import credenciales_de_la_empresa
    db.add(IntegrationCredential(provider="deepl", key="api_key", organization_id=None,
                                 value_encrypted=encrypt_value("GLOBAL")))
    db.commit()
    assert credenciales_de_la_empresa(db, "deepl", "1")["api_key"] is None


# ── Entrada: mensajes en el idioma de quien mira ─────────────────────────────

def test_comentario_del_cliente_traducido_al_idioma_del_operador(client, admin_token, db, doble):
    tid, org = _org(client, admin_token, db)
    _activar(db, org)
    db.add(TicketComment(ticket_id=tid, organization_id=org, body="我的打印机坏了，请帮忙看一下", is_public=True,
                         author_name="客户"))
    db.commit()
    c = db.query(TicketComment).filter(TicketComment.ticket_id == tid).one()
    assert c.language == "zh"   # detectado al guardar, sin red
    r = client.post("/api/v1/translation/messages", headers=auth(admin_token),
                    json={"items": [{"type": "ticket_comment", "id": c.id}], "target_language": "es"})
    assert r.status_code == 200, r.text
    item = r.json()["data"]["items"][0]
    assert item["status"] == "translated" and item["text"].startswith("[es]") and item["origin"] == "auto"
    # Otro idioma de operador: su propia traduccion, guardada aparte.
    r2 = client.post("/api/v1/translation/messages", headers=auth(admin_token),
                     json={"items": [{"type": "ticket_comment", "id": c.id}], "target_language": "en"})
    assert r2.json()["data"]["items"][0]["text"].startswith("[en]")
    assert db.query(MessageTranslation).filter(MessageTranslation.message_id == c.id).count() == 2
    # La tercera vez no se paga.
    client.post("/api/v1/translation/messages", headers=auth(admin_token),
                json={"items": [{"type": "ticket_comment", "id": c.id}], "target_language": "es"})
    assert len(doble.llamadas) == 2


def test_mensaje_de_otra_empresa_es_404(client, admin_token, db, doble):
    from app.models.mfa import Organization
    db.add(Organization(id="org-ajena", name="Ajena", slug="ajena"))
    db.add(Ticket(id="t-ajeno", organization_id="org-ajena", number="INC-9999", ticket_type="incident",
                  title="x", description="y"))
    db.add(TicketComment(id="c-ajeno", ticket_id="t-ajeno", organization_id="org-ajena", body="你好"))
    db.commit()
    r = client.post("/api/v1/translation/messages", headers=auth(admin_token),
                    json={"items": [{"type": "ticket_comment", "id": "c-ajeno"}]})
    assert r.status_code == 404


def test_subcontratado_no_traduce_tickets(client, sub_token):
    r = client.post("/api/v1/translation/messages", headers=auth(sub_token),
                    json={"items": [{"type": "ticket_comment", "id": "x"}]})
    assert r.status_code == 403


# ── Salida: vista previa y envio en el idioma del cliente ────────────────────

def _detectado_en_chino(db, tid, org):
    db.add(TicketComment(ticket_id=tid, organization_id=org, body="我的打印机坏了，请帮忙看一下", is_public=True,
                         author_name="客户"))
    db.commit()


def test_vista_previa_y_envio_editado(client, admin_token, db, doble):
    tid, org = _org(client, admin_token, db)
    _activar(db, org)
    _detectado_en_chino(db, tid, org)
    texto = "Hola, hemos reiniciado el servidor de impresión y ya debería funcionar"
    r = client.post("/api/v1/translation/outbound/preview", headers=auth(admin_token),
                    json={"context_type": "ticket", "context_id": tid, "text": texto})
    datos = r.json()["data"]
    assert (datos["target_language"], datos["target_source"], datos["status"]) == ("zh", "detected", "translated")
    r = client.post(f"/api/v1/sd/tickets/{tid}/comments", headers=auth(admin_token), json={
        "body": texto, "is_public": True, "client_text": "你好，打印服务器已重启", "client_language": "zh"})
    assert r.status_code == 200, r.text
    assert (r.json()["data"]["body"], r.json()["data"]["language"]) == ("你好，打印服务器已重启", "zh")
    autor = db.query(MessageTranslation).filter(MessageTranslation.message_id == r.json()["data"]["id"]).one()
    assert (autor.origin, autor.text, autor.target_language) == ("author", texto, "es")
    from app.models.enterprise import AuditLog
    entrada = db.query(AuditLog).filter(AuditLog.action == "TRANSLATE",
                                        AuditLog.resource_id == r.json()["data"]["id"]).one()
    assert json.loads(entrada.new_values)["origin"] == "edited"


def test_respuesta_sin_vista_previa_se_traduce_sola(client, admin_token, db, doble):
    tid, org = _org(client, admin_token, db)
    _activar(db, org)
    _detectado_en_chino(db, tid, org)
    texto = "Hola, hemos reiniciado el servidor de impresión y ya debería funcionar"
    r = client.post(f"/api/v1/sd/tickets/{tid}/comments", headers=auth(admin_token),
                    json={"body": texto, "is_public": True})
    assert r.json()["data"]["body"].startswith("[zh]") and r.json()["data"]["language"] == "zh"


def test_nota_interna_jamas_se_traduce_hacia_fuera(client, admin_token, db, doble):
    tid, org = _org(client, admin_token, db)
    _activar(db, org)
    _detectado_en_chino(db, tid, org)
    texto = "Nota interna: el cliente tiene la impresora fuera de garantía, revisarlo con compras"
    r = client.post(f"/api/v1/sd/tickets/{tid}/comments", headers=auth(admin_token), json={
        "body": texto, "is_public": False, "client_text": "不应发送", "client_language": "zh"})
    assert r.json()["data"]["body"] == texto
    assert doble.llamadas == []


def test_con_original_debajo_el_cliente_ve_los_dos(client, admin_token, db, doble):
    from app.services.traduccion.salida import SEPARADOR_DEL_ORIGINAL, texto_para_cliente
    tid, org = _org(client, admin_token, db)
    _activar(db, org, TRANSLATION_INCLUDE_ORIGINAL="true")
    _detectado_en_chino(db, tid, org)
    r = client.post(f"/api/v1/sd/tickets/{tid}/comments", headers=auth(admin_token), json={
        "body": "Ya está arreglado", "is_public": True, "client_text": "已修复", "client_language": "zh"})
    cid = r.json()["data"]["id"]
    assert texto_para_cliente(db, org, "ticket_comment", cid, "已修复") == f"已修复{SEPARADOR_DEL_ORIGINAL}Ya está arreglado"


# ── Glosario y administracion: minimo privilegio ─────────────────────────────

def test_glosario_solo_lo_cambia_un_admin(client, admin_token, dev_token):
    assert client.post("/api/v1/translation/glossary", headers=auth(dev_token), json={"term": "X"}).status_code == 403
    r = client.post("/api/v1/translation/glossary", headers=auth(admin_token),
                    json={"term": "ACME Cloud", "translations": {"zh": "ACME 云"}, "case_sensitive": True})
    assert r.status_code == 200 and r.json()["data"]["translations"] == {"zh": "ACME 云"}
    assert client.post("/api/v1/translation/glossary", headers=auth(admin_token),
                       json={"term": "ACME Cloud"}).json().get("detail") == "trad_termino_duplicado"
    assert client.get("/api/v1/translation/glossary", headers=auth(dev_token)).status_code == 200
    assert client.get("/api/v1/translation/usage", headers=auth(dev_token)).status_code == 403


def test_texto_suelto_del_editor(client, admin_token, db, doble):
    _, org = _org(client, admin_token, db)
    _activar(db, org)
    r = client.post("/api/v1/translation/text", headers=auth(admin_token),
                    json={"text": "Hola equipo, mañana revisamos el informe", "target_language": "ja"})
    assert r.json()["data"]["status"] == "translated" and r.json()["data"]["text"].startswith("[ja]")
    assert client.post("/api/v1/translation/text", headers=auth(admin_token),
                       json={"text": "x", "target_language": "ja", "channel": "whatsapp"}).status_code == 422


# ── Textos del sistema ───────────────────────────────────────────────────────

def test_plantillas_del_sistema_en_cada_idioma():
    from app.services.traduccion.textos_del_sistema import PLANTILLAS, renderizar
    params = {"name": "Portátil 14", "tag": "A-1", "serial": None, "person": "Ana", "due": "2026-12-01",
              "reason": None, "offboarding": "1"}
    es = renderizar("alm_return", params, "es")
    zh = renderizar("alm_return", params, "zh")
    assert es[0] == "Devolución de Portátil 14 (A-1) — Ana" and "Motivo" not in es[1] and "Baja de la persona." in es[1]
    assert zh[0].startswith("归还") and "—" in zh[1]   # sin numero de serie: guion
    for codigo, por_idioma in PLANTILLAS.items():
        assert set(por_idioma) == set(idiomas.IDIOMAS_DEL_PORTAL), codigo


def test_ticket_del_sistema_se_pinta_en_el_idioma_de_quien_mira(client, admin_token, db, doble):
    from app.services.traduccion.textos_del_sistema import aplicar
    tid, org = _org(client, admin_token, db)
    t = db.get(Ticket, tid)
    aplicar(db, t, "alm_breakdown", {"name": "Monitor", "tag": None, "serial": "SN1", "text": "No enciende"}, "es")
    db.commit()
    assert t.title == "Avería: Monitor"
    r = client.post("/api/v1/translation/messages", headers=auth(admin_token),
                    json={"items": [{"type": "ticket", "id": tid}], "target_language": "en"})
    titulo = next(i for i in r.json()["data"]["items"] if i["field"] == "title")
    assert (titulo["text"], titulo["origin"]) == ("Breakdown: Monitor", "system")
    assert doble.llamadas == []
