"""Incidencias de usuarios reales (23-11-2026): 1, 3, 5, 7, 8, 9 y 10.

(La 4 tiene su test en frontend/src/__tests__/CambiosSinGuardar.test.tsx y la 6
en tests/test_restablecer_contrasena_2026_11_23.py.)
"""
from __future__ import annotations

import inspect
from pathlib import Path

import pytest

from app.core.errores import ErrorDeDominio
from app.core.codigos_de_error import ErrorConCodigo
from tests.conftest import auth

RAIZ = Path(__file__).resolve().parents[1]
FRONT = RAIZ / "frontend" / "src"

GUID = "11111111-2222-3333-4444-555555555555"
ENTRA = "https://login.microsoftonline.com/contoso.onmicrosoft.com/v2.0/.well-known/openid-configuration"


# ── 1: el alta de ticket no pide rutas de administración ─────────────────────

def test_1_alta_de_ticket_no_pide_el_historial_sin_sd_administrar():
    src = (FRONT / "pages" / "service-desk" / "CreateTicketModal.tsx").read_text(encoding="utf-8")
    bloque = src[src.index("queryKey: ['sd-dynamic-forms-history']"):][:300]
    assert "enabled: administraSd" in bloque and "errorToast: false" in bloque
    assert "{administraSd && <Button" in src


def test_1_el_403_por_capacidad_lleva_codigo_traducible(client, db):
    from tests.conftest import _TEST_PASSWORD
    r = client.post("/api/v1/auth/login", json={"username": "pm", "password": _TEST_PASSWORD})
    if r.status_code != 200:
        pytest.skip("sin usuario pm en la semilla de pruebas")
    r = client.get("/api/v1/sd/dynamic-forms/history", headers=auth(r.cookies.get("access_token")))
    if r.status_code == 403:
        assert r.json().get("code") in ("capacidad_requerida", "roles_requeridos"), r.text


# ── 3: valores crudos del alta, traducidos ───────────────────────────────────

def test_3_claves_de_campos_dinamicos_y_cola_en_los_tres_idiomas():
    for lang in ("es", "en", "zh"):
        texto = (FRONT / "i18n" / "langs" / f"{lang}.mjs").read_text(encoding="utf-8")
        for clave in ("sd_campos_dinamicos: {", "cola_incident_l1:", "opcion_produccion:", "opcion_preproduccion:",
                      "opcion_desarrollo:", "campo_affected_environment:"):
            assert clave in texto, (lang, clave)
    for lang in ("es", "en", "zh", "fr", "de", "it", "pt", "pl"):
        texto = (FRONT / "i18n" / "portal" / f"{lang}.ts").read_text(encoding="utf-8")
        assert "psd_cola_incident_l1:" in texto and "psd_opcion_produccion:" in texto, lang


# ── 5: idioma por defecto inglés si nadie eligió ─────────────────────────────

def test_5_sin_preferencia_ni_eleccion_de_empresa_el_idioma_es_none(db):
    from app.services.settings_service.por_empresa import idioma_elegido_de_empresa
    from app.services.user_service import get_preferences_payload
    assert idioma_elegido_de_empresa(db, "1") is None
    assert get_preferences_payload("admin-test-id", db)["language"] is None


def test_5_el_idioma_que_elige_la_empresa_manda(db):
    from app.models.settings import AppSetting
    from app.services.settings_service import invalidate_cache
    from app.services.settings_service.por_empresa import idioma_elegido_de_empresa
    db.add(AppSetting(key="DEFAULT_LANGUAGE", value="zh", organization_id="1"))
    db.commit()
    invalidate_cache()
    assert idioma_elegido_de_empresa(db, "1") == "zh"


def test_5_la_fila_de_preferencias_no_congela_el_castellano(db):
    from app.models.user import UserPreference
    db.add(UserPreference(user_id="admin-test-id", theme_mode="dark"))
    db.commit()
    assert db.query(UserPreference).filter_by(user_id="admin-test-id").one().language is None


def test_5_constantes_del_frontend():
    portal = (FRONT / "i18n" / "portalTranslations.ts").read_text(encoding="utf-8")
    assert "export const IDIOMA_POR_DEFECTO: PortalLangCode = 'en'" in portal
    assert "export const IDIOMA_FUENTE: PortalLangCode = 'es'" in portal
    app = (FRONT / "i18n" / "appTranslations.ts").read_text(encoding="utf-8")
    assert "export const IDIOMA_DE_RESPALDO = 'en'" in app


# ── 7: el portal identifica al cliente con TENANT_SESION_SIN_CONTEXTO=cerrar ─

def test_7_get_current_client_del_portal_declara_contexto_de_sistema():
    from app.api.v1.endpoints import client_portal
    src = inspect.getsource(client_portal.get_current_client)
    assert "contexto_de_sistema" in src
    assert src.index("contexto_de_sistema(db") < src.index("get_active_client_by_id")


def test_7_el_cliente_del_portal_con_cookies_manda_el_testigo_csrf():
    src = (FRONT / "services" / "api" / "clienteBase.ts").read_text(encoding="utf-8")
    assert "X-CSRF-Token" in src and "extra.withCredentials" in src


# ── 8: enlaces de Configuración ──────────────────────────────────────────────

def test_8_los_enlaces_de_puesta_en_marcha_apuntan_a_secciones_que_existen():
    import re

    from app.services import puesta_en_marcha
    catalogo = (FRONT / "pages" / "settings" / "catalogoDeAjustes.tsx").read_text(encoding="utf-8")
    ids = set(re.findall(r"\{ id: '([a-z0-9-]+)', grupo", catalogo))
    enlaces = re.findall(r'"(/settings/[a-z0-9-]+)', inspect.getsource(puesta_en_marcha))
    assert enlaces
    for e in enlaces:
        assert e.split("/")[2] in ids, e


def test_8_credenciales_del_buzon_abren_su_proveedor():
    src = (FRONT / "pages" / "service-desk" / "ConfigCorreoEntrante.tsx").read_text(encoding="utf-8")
    assert "/settings/integrations?sub=sd_mailbox" in src
    sec = (FRONT / "pages" / "settings-sections" / "SettingsAdvancedSections.tsx").read_text(encoding="utf-8")
    assert "IntegrationCredentialsSection({ subInicial }" in sec


# ── 9: SSO de Azure AD / Entra ID ────────────────────────────────────────────

def test_9_EL_HALLAZGO_guardar_azure_ad_no_da_500(client, admin_token, db):
    r = client.post("/api/v1/enterprise/sso", headers=auth(admin_token), json={
        "provider": "azure_ad", "name": "Entra", "oidc_client_id": GUID, "oidc_client_secret": "s3cr3t",
        "oidc_discovery_url": ENTRA, "is_active": True, "allowed_domains": "Contoso.com, @fabrikam.es",
        "role_mapping": {"Admins": "admin", "PMs": "pm"}, "default_role": "employee"})
    assert r.status_code == 200, r.text
    datos = r.json()["data"]
    assert datos["provider"] == "azure_ad"
    assert datos["allowed_domains"] == "contoso.com,fabrikam.es"
    assert datos["has_oidc_secret"] is True and "s3cr3t" not in r.text
    from app.models.enterprise import SSOConfig, SSOProvider
    fila = db.query(SSOConfig).filter_by(id=datos["id"]).one()
    assert fila.provider == SSOProvider.azure and fila.oidc_client_secret != "s3cr3t"
    r = client.patch(f"/api/v1/enterprise/sso/{datos['id']}", headers=auth(admin_token), json={"name": "Entra ID"})
    assert r.status_code == 200, r.text


@pytest.mark.parametrize("cambio, codigo", [
    ({"oidc_discovery_url": "https://login.microsoftonline.com/{tenant-id}/v2.0/.well-known/openid-configuration"},
     "sso_discovery_no_valida"),
    ({"oidc_discovery_url": "https://idp.example.com/.well-known/openid-configuration"}, "sso_discovery_entra_no_valida"),
    ({"oidc_client_id": "no-es-un-guid"}, "sso_client_id_no_valido"),
    ({"allowed_domains": "contoso, bien.com"}, "sso_dominio_no_valido"),
    ({"role_mapping": {"Admins": "jefazo"}}, "sso_rol_no_valido"),
    ({"default_role": "jefazo"}, "sso_rol_no_valido"),
    ({"oidc_client_secret": None}, "sso_falta_dato"),
])
def test_9_entrada_no_valida_da_422_con_codigo(client, admin_token, db, cambio, codigo):
    cuerpo = {"provider": "azure_ad", "oidc_client_id": GUID, "oidc_client_secret": "s",
              "oidc_discovery_url": ENTRA, "is_active": True, **cambio}
    r = client.post("/api/v1/enterprise/sso", headers=auth(admin_token), json=cuerpo)
    assert r.status_code == 422, r.text
    assert r.json().get("code") == codigo, r.text


def test_9_proveedor_acepta_valor_y_nombre():
    from app.models.enterprise import SSOProvider
    from app.services.enterprise_service.sso import _proveedor
    assert _proveedor("azure_ad") is SSOProvider.azure
    assert _proveedor("azure") is SSOProvider.azure
    with pytest.raises(ErrorDeDominio):
        _proveedor("saml2")


# ── 10: buzón del Service Desk ───────────────────────────────────────────────

def test_10_la_sonda_del_buzon_existe_y_devuelve_codigo(db, monkeypatch):
    from app.services import integration_test_service as its
    assert "sd_mailbox" in its._PROBES
    r = its.test_provider_connection(db, "sd_mailbox", org_id="1")
    assert r["ok"] is False and r["code"] == "buzon_sin_configurar"
    monkeypatch.delitem(its._PROBES, "sd_mailbox")
    r = its.test_provider_connection(db, "sd_mailbox", org_id="1")
    assert r["code"] == "integracion_sin_prueba" and r["params"] == {"proveedor": "sd_mailbox"}


@pytest.mark.parametrize("clave, valor, codigo", [
    ("port", "novecientos", "integracion_valor_no_numerico"),
    ("port", "70000", "integracion_puerto_no_valido"),
    ("protocol", "pop3", "buzon_protocolo_no_valido"),
])
def test_10_credenciales_del_buzon_se_validan_al_guardar(clave, valor, codigo):
    from app.services.integration_credentials_service import set_credential
    with pytest.raises(ErrorConCodigo) as e:
        set_credential(None, "sd_mailbox", clave, valor, "1")
    assert e.value.codigo == codigo


def test_10_credenciales_del_buzon_se_guardan(client, admin_token, db):
    for clave, valor in (("protocol", "IMAP"), ("port", "993"), ("host", "imap.example.com"), ("folder", "INBOX")):
        r = client.put(f"/api/v1/settings/integrations/sd_mailbox/{clave}", headers=auth(admin_token),
                       json={"value": valor})
        assert r.status_code in (200, 400), r.text  # 400 solo si el host no resuelve (guardia SSRF sin red)
    r = client.get("/api/v1/settings/integrations/sd_mailbox", headers=auth(admin_token))
    assert r.status_code == 200
    valores = {i["key"]: i.get("value") for i in r.json()["data"]["items"]}
    assert valores["protocol"] == "imap" and str(valores["port"]) == "993"
