"""Licencias y hardware — fase 2: uso real (16-11-2026).

Conectores con dobles de HTTP (Graph/Intune, Google, Okta, Jamf: nunca se llama
a la red), conciliación, estado de uso, recuperación con el motor de políticas,
cumplimiento, software no controlado, inventario del agente y permisos.
"""
from __future__ import annotations

import json
import uuid
from datetime import date, datetime, timedelta, timezone

import pytest

from app.models.alm import ALMLicense, ALMLicenseAssignment, ALMSoftwareInstall, ALMAsset, LicenseType
from app.models.alm_uso import ALMUsoConexion, ALMUsoEvidencia, ALMUsoRecuperacion, ALMSoftwareNoControlado
from app.models.user import User
from app.services.alm_uso.proveedores.base import ContextoDeLectura, ErrorDeConector
from tests.conftest import auth

ORG = "1"
AHORA = datetime.now(timezone.utc)


# ── Doble de HTTP ─────────────────────────────────────────────────────────────

class Doble:
    """Responde por el fragmento de URL. `json`: dict/lista o ErrorDeConector; `texto`: CSV."""

    def __init__(self, json_=None, texto=None, formularios=None, cabeceras=None):
        self.json = json_ or {}
        self.texto = texto or {}
        self.formularios = formularios or {}
        self.cabeceras = cabeceras or {}
        self.llamadas: list = []

    def _buscar(self, tabla, url):
        for frag in sorted(tabla, key=len, reverse=True):
            if frag in url:
                v = tabla[frag]
                if isinstance(v, Exception):
                    raise v
                if isinstance(v, list) and v and isinstance(v[0], tuple):
                    return v.pop(0) if len(v) > 1 else v[0]
                return v
        raise ErrorDeConector("NOT_FOUND", f"sin doble para {url}")

    def obtener_json(self, url, headers=None, params=None):
        self.llamadas.append(("GET", url, dict(params or {}), dict(headers or {})))
        r = self._buscar(self.json, url)
        if isinstance(r, tuple):
            return r
        return r, self.cabeceras.get(url, {})

    def obtener_texto(self, url, headers=None, params=None):
        self.llamadas.append(("GET", url, dict(params or {}), dict(headers or {})))
        return self._buscar(self.texto, url)

    def enviar_formulario(self, url, datos, headers=None):
        self.llamadas.append(("POST", url, dict(datos), dict(headers or {})))
        return self._buscar(self.formularios, url)


def _ctx(db, creds, http, configuracion=None):
    return ContextoDeLectura(db=db, organization_id=ORG, credenciales=creds, configuracion=configuracion or {},
                             http=http, max_paginas=50, periodo_dias=30, max_apps=100, ahora=AHORA)


M365_CREDS = {"tenant_id": "t-1", "client_id": "c-1", "client_secret": "s-1"}
TOKEN = {"login.microsoftonline.com": {"access_token": "tok"}}


# ── Microsoft 365 ─────────────────────────────────────────────────────────────

def _graph_m365(con_inicio=True, informes=True):
    skus = {"value": [
        {"skuId": "sku-e3", "skuPartNumber": "SPE_E3", "consumedUnits": 2,
         "prepaidUnits": {"enabled": 3, "suspended": 0, "warning": 0},
         "servicePlans": [{"servicePlanName": "EXCHANGE_S_ENTERPRISE"}, {"servicePlanName": "OFFICESUBSCRIPTION"},
                          {"servicePlanName": "TEAMS1"}]},
        {"skuId": "sku-visio", "skuPartNumber": "VISIOCLIENT", "consumedUnits": 1,
         "prepaidUnits": {"enabled": 1}, "servicePlans": [{"servicePlanName": "VISIO_CLIENT_SUBSCRIPTION"}]},
    ]}
    usuarios_pag1 = {"value": [
        {"id": "u1", "userPrincipalName": "dev@contecflow.com", "accountEnabled": True,
         "assignedLicenses": [{"skuId": "sku-e3"}, {"skuId": "sku-visio"}],
         "signInActivity": {"lastSignInDateTime": (AHORA - timedelta(days=2)).isoformat()}},
    ], "@odata.nextLink": "https://graph.microsoft.com/v1.0/users?$skiptoken=2"}
    usuarios_pag2 = {"value": [
        {"id": "u2", "userPrincipalName": "PM@contecflow.com", "accountEnabled": False,
         "assignedLicenses": [{"skuId": "sku-e3"}]},
    ]}
    json_ = {"/subscribedSkus": skus,
             "/users?$skiptoken=2": usuarios_pag2,
             "/users": usuarios_pag1 if con_inicio else ErrorDeConector("FORBIDDEN", "HTTP 403", estado_http=403)}
    texto = {}
    if informes:
        hace5 = (AHORA - timedelta(days=5)).date().isoformat()
        hace40 = (AHORA - timedelta(days=40)).date().isoformat()
        texto = {
            "getOffice365ActiveUserDetail": "﻿User Principal Name,Exchange Last Activity Date,Teams Last Activity Date,"
                                            "OneDrive Last Activity Date\n"
                                            f"dev@contecflow.com,{hace5},{hace40},\n",
            "getM365AppUserDetail": "User Principal Name,Last Activity Date,Windows,Mac\n"
                                    f"dev@contecflow.com,{hace40},Yes,No\n",
        }
    else:
        texto = {"reports/": ErrorDeConector("FORBIDDEN", "HTTP 403", estado_http=403)}
    return Doble(json_=json_, texto=texto, formularios=TOKEN)


def test_m365_lee_derechos_y_evidencias_por_sku_con_servicios_de_ese_sku(db):
    from app.services.alm_uso.proveedores.microsoft import Microsoft365
    r = Microsoft365().leer(_ctx(db, M365_CREDS, _graph_m365()))
    assert {d.sku: (d.comprados, d.consumidos) for d in r.derechos} == {"SPE_E3": (3, 2), "VISIOCLIENT": (1, 1)}
    por = {(e.titular, e.producto): e for e in r.evidencias}
    e3 = por[("dev@contecflow.com", "SPE_E3")]
    # El último uso del E3 es el del correo (hace 5 días): servicio incluido en el SKU.
    assert e3.ultimo_uso.date() == (AHORA - timedelta(days=5)).date()
    assert set(e3.servicios) >= {"exchange", "teams", "apps_escritorio", "inicio_de_sesion"}
    # Visio no incluye ningún servicio medido: se usa el inicio de sesión y baja la fiabilidad.
    visio = por[("dev@contecflow.com", "VISIOCLIENT")]
    assert visio.detalle["base"] == "inicio_de_sesion" and visio.detalle["fiabilidad_reducida"] is True
    # Segunda página (nextLink) y cuenta desactivada.
    assert por[("pm@contecflow.com", "SPE_E3")].detalle["cuenta_activa"] is False


def test_m365_sin_permiso_de_signin_ni_informes_sigue_con_avisos(db):
    from app.services.alm_uso.proveedores.microsoft import Microsoft365
    doble = _graph_m365(con_inicio=False, informes=False)
    doble.json["/users"] = [({"value": []}, {})]   # el reintento sin signInActivity

    llamadas = {"n": 0}
    original = doble.obtener_json

    def obtener(url, headers=None, params=None):
        if "/users" in url and "signInActivity" in (params or {}).get("$select", ""):
            llamadas["n"] += 1
            raise ErrorDeConector("FORBIDDEN", "HTTP 403", estado_http=403)
        return original(url, headers=headers, params=params)
    doble.obtener_json = obtener
    r = Microsoft365().leer(_ctx(db, M365_CREDS, doble))
    codigos = {a["codigo"] for a in r.avisos}
    assert {"SIGNIN_ACTIVITY_UNAVAILABLE", "REPORTS_UNAVAILABLE"} <= codigos
    assert llamadas["n"] == 1


def test_m365_detecta_nombres_ocultos_en_informes(db):
    from app.services.alm_uso.proveedores.microsoft import Microsoft365
    doble = _graph_m365()
    doble.texto["getOffice365ActiveUserDetail"] = "User Principal Name,Exchange Last Activity Date\nA1B2C3D4,2026-11-10\n"
    r = Microsoft365().leer(_ctx(db, M365_CREDS, doble))
    assert any(a["codigo"] == "REPORTS_CONCEALED" for a in r.avisos)


# ── Intune ────────────────────────────────────────────────────────────────────

def test_intune_dispositivos_con_serie_usuario_y_apps(db):
    from app.services.alm_uso.proveedores.microsoft import Intune
    doble = Doble(formularios=TOKEN, json_={
        "/deviceManagement/managedDevices": {"value": [
            {"id": "d1", "deviceName": "PC-DEV", "serialNumber": "SN-1", "userPrincipalName": "dev@contecflow.com",
             "lastSyncDateTime": AHORA.isoformat(), "operatingSystem": "Windows", "model": "Latitude 7440"}]},
        "/deviceManagement/detectedApps/a1/managedDevices": {"value": [{"id": "d1"}]},
        "/deviceManagement/detectedApps": {"value": [{"id": "a1", "displayName": "Visio", "version": "16", "deviceCount": 1}]},
    })
    r = Intune().leer(_ctx(db, M365_CREDS, doble))
    d = r.dispositivos[0]
    assert (d.serie, d.usuario, d.apps_leidas) == ("SN-1", "dev@contecflow.com", True)
    assert [a.nombre for a in d.apps] == ["Visio"]


# ── Google Workspace ──────────────────────────────────────────────────────────

@pytest.fixture
def clave_google():
    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives.asymmetric import rsa
    k = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    pem = k.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8,
                          serialization.NoEncryption()).decode()
    return json.dumps({"client_email": "sa@proj.iam.gserviceaccount.com", "private_key": pem,
                       "token_uri": "https://oauth2.googleapis.com/token"})


def test_google_licencias_uso_y_apps_autorizadas(db, clave_google):
    from app.services.alm_uso.proveedores.google import GoogleWorkspace
    doble = Doble(formularios={"oauth2.googleapis.com/token": {"access_token": "g"}}, json_={
        "/admin/directory/v1/users": {"users": [{"primaryEmail": "dev@contecflow.com", "id": "g1",
                                                  "lastLoginTime": (AHORA - timedelta(days=3)).isoformat()}]},
        "/apps/licensing/v1/product/Google-Apps/users": {"items": [
            {"userId": "dev@contecflow.com", "productId": "Google-Apps", "skuId": "1010020027", "skuName": "Workspace Business Starter"}]},
        "/usage/users/all/dates/": {"usageReports": [{"entity": {"userEmail": "dev@contecflow.com"}, "parameters": [
            {"name": "gmail:last_interaction_time", "datetimeValue": (AHORA - timedelta(days=4)).isoformat()},
            {"name": "accounts:last_login_time", "datetimeValue": (AHORA - timedelta(days=3)).isoformat()}]}]},
        "/applications/token": {"items": [{"actor": {"email": "dev@contecflow.com"}, "id": {"time": AHORA.isoformat()},
                                           "events": [{"parameters": [{"name": "app_name", "value": "Miro"}]}]}]},
    })
    ctx = _ctx(db, {"service_account_json": clave_google, "admin_email": "admin@contecflow.com",
                    "customer_id": "my_customer"}, doble, configuracion={"dominio": "contecflow.com"})
    r = GoogleWorkspace().leer(ctx)
    ev = r.evidencias[0]
    assert (ev.producto, ev.asignada, ev.detalle["base"]) == ("1010020027", True, "informes_de_uso")
    assert "gmail" in ev.servicios
    assert [(a.nombre, a.usuarios) for a in r.aplicaciones] == [("Miro", 1)]
    # La aserción JWT va firmada; el secreto nunca viaja en claro.
    post = next(c for c in doble.llamadas if c[0] == "POST")
    assert post[2]["grant_type"].endswith("jwt-bearer") and "private_key" not in json.dumps(post[2])


def test_google_sin_dominio_mide_por_producto_con_aviso(db, clave_google):
    from app.services.alm_uso.proveedores.google import GoogleWorkspace
    doble = Doble(formularios={"oauth2.googleapis.com/token": {"access_token": "g"}}, json_={
        "/admin/directory/v1/users": {"users": [{"primaryEmail": "dev@contecflow.com"}]},
        "/usage/users/all/dates/": {"usageReports": []},
        "/applications/token": {"items": []},
    })
    r = GoogleWorkspace().leer(_ctx(db, {"service_account_json": clave_google, "admin_email": "a@b.c"}, doble))
    assert any(a["codigo"] == "LICENSING_NEEDS_DOMAIN" for a in r.avisos)
    assert r.evidencias[0].producto == "Google-Apps"


def test_google_clave_ilegible_es_error_de_credenciales(db):
    from app.services.alm_uso.proveedores.google import GoogleWorkspace
    with pytest.raises(ErrorDeConector) as e:
        GoogleWorkspace().leer(_ctx(db, {"service_account_json": "no-json", "admin_email": "a@b.c"}, Doble()))
    assert e.value.codigo == "BAD_CREDENTIALS"


# ── Okta ──────────────────────────────────────────────────────────────────────

def test_okta_asignaciones_accesos_sso_y_paginacion_por_link(db):
    from app.services.alm_uso.proveedores.okta import Okta
    base = "https://acme.okta.com"
    sig = f"{base}/api/v1/users?after=2"
    doble = Doble(json_={
        "/api/v1/users?after=2": [{"id": "o2", "status": "SUSPENDED", "profile": {"login": "pm@contecflow.com"}}],
        "/api/v1/users": [{"id": "o1", "status": "ACTIVE", "lastLogin": AHORA.isoformat(),
                           "profile": {"login": "dev@contecflow.com"}}],
        "/api/v1/apps/app1/users": [{"id": "o1"}],
        "/api/v1/apps": [{"id": "app1", "label": "Figma"}],
        "/api/v1/logs": [{"published": (AHORA - timedelta(days=1)).isoformat(), "actor": {"alternateId": "dev@contecflow.com"},
                          "target": [{"type": "AppInstance", "id": "app1", "displayName": "Figma"}]}],
    }, cabeceras={f"{base}/api/v1/users": {"link": f'<{sig}>; rel="next"'}})
    r = Okta().leer(_ctx(db, {"base_url": base, "api_token": "t"}, doble))
    por = {(e.titular, e.producto): e for e in r.evidencias}
    assert por[("pm@contecflow.com", "okta")].asignada is False
    figma = por[("dev@contecflow.com", "app:app1")]
    assert (figma.nombre_producto, figma.frecuencia, figma.asignada) == ("Figma", 1, True)
    assert all(c[3].get("Authorization") == "SSWS t" for c in doble.llamadas)


def test_okta_rechaza_url_sin_https(db):
    from app.services.alm_uso.proveedores.okta import Okta
    with pytest.raises(ErrorDeConector):
        Okta().leer(_ctx(db, {"base_url": "http://acme.okta.com", "api_token": "t"}, Doble()))


# ── Jamf ──────────────────────────────────────────────────────────────────────

def test_jamf_inventario_por_paginas(db):
    from app.services.alm_uso.proveedores.jamf import Jamf
    doble = Doble(formularios={"/api/oauth/token": {"access_token": "j"}}, json_={
        "/api/v1/computers-inventory": {"totalCount": 1, "results": [{
            "id": 7, "general": {"name": "MAC-1", "lastContactTime": AHORA.isoformat()},
            "hardware": {"serialNumber": "C02X", "model": "MacBook Pro"},
            "userAndLocation": {"email": "dev@contecflow.com"},
            "applications": [{"name": "Microsoft Excel", "version": "16.8"}]}]}})
    r = Jamf().leer(_ctx(db, {"base_url": "https://acme.jamfcloud.com", "client_id": "x", "client_secret": "y"}, doble))
    d = r.dispositivos[0]
    assert (d.serie, d.usuario, d.apps_leidas, d.apps[0].nombre) == ("C02X", "dev@contecflow.com", True, "Microsoft Excel")


# ── Datos de ALM para conciliar ───────────────────────────────────────────────

def _licencia(db, nombre="Microsoft 365 E3", sku="SPE_E3", metric="named_user", seats=10, coste=3600.0, **kw):
    lic = ALMLicense(id=str(uuid.uuid4()), organization_id=ORG, name=nombre, product_name=kw.pop("product_name", nombre),
                     type=LicenseType.subscription, metric=metric, sku=sku, total_seats=seats, annual_cost=coste, **kw)
    db.add(lic)
    db.flush()
    return lic


def _asignar(db, lic, user_id=None, asset_id=None, dias=120):
    a = ALMLicenseAssignment(id=str(uuid.uuid4()), organization_id=ORG, resource_type="license", license_id=lic.id,
                             holder_type="user" if user_id else "asset", holder_user_id=user_id, holder_asset_id=asset_id,
                             status="active", mode="assignment", quantity=1,
                             valid_from=date.today() - timedelta(days=dias), source="manual")
    db.add(a)
    db.flush()
    return a


def _evidencia(db, lic, user_id, dias_sin_uso, fuente="m365", fiabilidad="alta", **kw):
    e = ALMUsoEvidencia(organization_id=ORG, fuente=fuente, titular_tipo="persona",
                        titular_externo=kw.pop("titular", f"{user_id}@x"), user_id=user_id, producto=kw.pop("producto", "SPE_E3"),
                        license_id=lic.id, ultimo_uso_at=(AHORA - timedelta(days=dias_sin_uso)) if dias_sin_uso is not None else None,
                        fiabilidad=fiabilidad, leido_at=kw.pop("leido_at", AHORA), vista_en_ultima_lectura=True, **kw)
    db.add(e)
    db.flush()
    return e


# ── Sincronización y conciliación ─────────────────────────────────────────────

def _conexion(db, proveedor="m365", activa=True):
    c = ALMUsoConexion(organization_id=ORG, proveedor=proveedor, activa=activa)
    db.add(c)
    db.flush()
    return c


def _creds_m365(db):
    from app.services.integration_credentials_service import set_credential
    for k, v in M365_CREDS.items():
        set_credential(db, "alm_m365", k, v, ORG, "admin-test-id")


def test_sincronizacion_concilia_titulares_licencias_y_asignaciones(db):
    from app.services.alm_uso import sincronizacion
    lic = _licencia(db)
    dev = db.query(User).filter(User.id == "dev-test-id").one()
    a = _asignar(db, lic, user_id=dev.id)
    _creds_m365(db)
    c = _conexion(db)
    db.commit()
    s = sincronizacion.iniciar(db, c, "manual", "admin-test-id")
    db.commit()
    r = sincronizacion.ejecutar(db, s.id, http=_graph_m365())
    assert r["estado"] in ("ok", "parcial") and r["nuevas"] >= 3
    ev = db.query(ALMUsoEvidencia).filter(ALMUsoEvidencia.fuente == "m365", ALMUsoEvidencia.user_id == dev.id,
                                          ALMUsoEvidencia.producto == "SPE_E3").one()
    assert (ev.license_id, ev.assignment_id, ev.fiabilidad) == (lic.id, a.id, "alta")
    # Visio no está en ALM: queda sin licencia y como candidato de software no controlado.
    assert r["sin_licencia"] >= 1
    assert db.query(ALMSoftwareNoControlado).filter(ALMSoftwareNoControlado.clave == "visioclient").first() is not None
    # Una segunda lectura sin la persona la marca como no vista (le quitaron la licencia).
    doble = _graph_m365()
    doble.json["/users"] = {"value": []}
    s2 = sincronizacion.iniciar(db, c, "manual", "admin-test-id")
    db.commit()
    sincronizacion.ejecutar(db, s2.id, http=doble)
    db.refresh(ev)
    assert ev.vista_en_ultima_lectura is False


def test_sincronizacion_sin_credenciales_queda_en_error_registrado(db):
    from app.services.alm_uso import sincronizacion
    c = _conexion(db)
    db.commit()
    s = sincronizacion.iniciar(db, c, "manual")
    db.commit()
    r = sincronizacion.ejecutar(db, s.id, http=Doble())
    assert r["estado"] == "error" and r["errores"][0]["codigo"] == "MISSING_CREDENTIALS"
    db.refresh(c)
    assert c.ultimo_estado == "error" and "MISSING_CREDENTIALS" in c.ultimo_error


def test_las_credenciales_son_solo_de_la_empresa_nunca_las_globales(db):
    """Una fila global (sin empresa) de `alm_m365` no la usa ninguna empresa."""
    from app.services.alm_uso.conexiones import credenciales
    from app.services.integration_credentials_service import set_credential
    from tests.conftest import fila_global
    # La sesion del fixture publica la empresa 1 y el sellado al insertar rellena
    # el `organization_id=None`: sin `fila_global` la fila "global" nacia de la
    # empresa 1 y el test no probaba lo que dice (fallaba por su preparacion).
    with fila_global(db):
        set_credential(db, "alm_m365", "client_secret", "secreto-global", None, "admin-test-id")
    assert credenciales(db, "alm_m365", ORG)["client_secret"] is None
    set_credential(db, "alm_m365", "client_secret", "secreto-propio", ORG, "admin-test-id")
    assert credenciales(db, "alm_m365", ORG)["client_secret"] == "secreto-propio"


def test_inventario_crea_activo_instalacion_y_retira_lo_que_desaparece(db):
    from app.services.alm_uso.conciliacion import conciliar
    from app.services.alm_uso.proveedores.base import AppInstalada, Dispositivo, ResultadoDeLectura
    lic = _licencia(db, nombre="Microsoft Visio", sku=None, metric="device")
    c = _conexion(db, "jamf")
    d = Dispositivo(externo_id="7", nombre="MAC-1", serie="C02X", modelo="MacBook Pro", usuario="dev@contecflow.com",
                    ultimo_contacto=AHORA, apps=[AppInstalada(nombre="Microsoft Visio", version="16")], apps_leidas=True)
    conciliar(db, ORG, "jamf", c, "alta", ResultadoDeLectura(dispositivos=[d]), AHORA, True)
    activo = db.query(ALMAsset).filter(ALMAsset.serial_number == "C02X").one()
    assert activo.type.value == "laptop"
    inst = db.query(ALMSoftwareInstall).filter(ALMSoftwareInstall.asset_id == activo.id,
                                               ALMSoftwareInstall.license_id == lic.id).one()
    assert inst.is_active
    d.apps = []
    conciliar(db, ORG, "jamf", c, "alta", ResultadoDeLectura(dispositivos=[d]), AHORA, True)
    db.refresh(inst)
    assert inst.is_active is False


# ── Estado de uso ─────────────────────────────────────────────────────────────

def test_uso_de_licencia_cumple_el_contrato_de_renovaciones(db):
    from app.services import alm_uso
    lic = _licencia(db)
    for uid, dias in (("dev-test-id", 2), ("pm-test-id", 45), ("hr-test-id", 200)):
        _asignar(db, lic, user_id=uid)
        _evidencia(db, lic, uid, dias)
    _asignar(db, lic, user_id="admin-test-id")          # sin evidencias
    db.commit()
    r = alm_uso.uso_de_licencia(db, lic.id, ORG)
    for clave in ("asignados", "total", "en_uso", "infrautilizadas", "sin_uso", "sin_datos", "pico_concurrente",
                  "fuente", "medido_en"):
        assert clave in r
    assert (r["asignados"], r["en_uso"], r["infrautilizadas"], r["sin_uso"], r["sin_datos"]) == (4, 1, 1, 1, 1)
    assert r["fuente"] == "m365"


def test_las_ausencias_aprobadas_no_cuentan_como_dias_sin_uso(db):
    from app.models.resources import Absence, AbsenceStatus
    from app.services import alm_uso
    lic = _licencia(db)
    a = _asignar(db, lic, user_id="dev-test-id")
    _evidencia(db, lic, "dev-test-id", 70)
    hoy = date.today()
    db.add(Absence(organization_id=ORG, user_id="dev-test-id", type="sick", status=AbsenceStatus.approved,
                   start_date=hoy - timedelta(days=60), end_date=hoy - timedelta(days=21), working_days=30))
    db.commit()
    u = alm_uso.uso_de_asignacion(db, a.id, ORG)
    assert u["dias_sin_uso"] == 70 and u["dias_sin_uso_efectivos"] == 70 - 40
    assert u["estado"] == "infrautilizada"


def test_instalado_sin_medida_de_uso_es_sin_datos_no_sin_uso(db):
    from app.services.alm_uso.estado import evaluar
    from app.services.alm_uso._comun import umbrales
    e = ALMUsoEvidencia(organization_id=ORG, fuente="jamf", titular_tipo="dispositivo", titular_externo="sn",
                        producto="visio", fiabilidad="alta", leido_at=AHORA, vista_en_ultima_lectura=True,
                        detalle=json.dumps({"solo_presencia": True}), created_at=AHORA - timedelta(days=300))
    r = evaluar([e], umbrales(db, ORG), date.today())
    assert (r["estado"], r["motivo"]) == ("sin_datos", "instalada_sin_medida_de_uso")


def test_cuenta_desactivada_en_la_fuente_es_sin_uso(db):
    from app.services import alm_uso
    lic = _licencia(db)
    a = _asignar(db, lic, user_id="pm-test-id")
    _evidencia(db, lic, "pm-test-id", 1, detalle=json.dumps({"cuenta_activa": False}))
    db.commit()
    u = alm_uso.uso_de_asignacion(db, a.id, ORG)
    assert (u["estado"], u["motivo"]) == ("sin_uso", "cuenta_desactivada")


# ── Recuperación con el motor de políticas ────────────────────────────────────

def _politica_de_recuperacion(db, requiere_aprobacion=True):
    from app.services.politicas import servicio
    from app.services.politicas.dominios.licencias import ejemplos
    admin = db.query(User).filter(User.id == "admin-test-id").one()
    doc = ejemplos(db, admin)["politicas"][0]
    doc["reglas"][0]["resultados"][0].update(dias_hasta_responsable=0, dias_hasta_liberar=0,
                                              requiere_aprobacion=requiere_aprobacion)
    p = servicio.crear(db, admin, doc)
    servicio.publicar(db, admin, p["id"])
    db.commit()
    return admin


def test_recuperacion_avisa_escala_y_libera_con_aprobacion(db):
    from app.services.alm_uso import recuperacion
    admin = _politica_de_recuperacion(db)
    lic = _licencia(db)
    a = _asignar(db, lic, user_id="dev-test-id")
    _evidencia(db, lic, "dev-test-id", 90)
    db.commit()
    r1 = recuperacion.pasada(db, ORG)
    assert r1["abiertas"] == 1
    rec = db.query(ALMUsoRecuperacion).filter(ALMUsoRecuperacion.assignment_id == a.id).one()
    assert rec.estado == "aviso_persona"
    recuperacion.pasada(db, ORG)                      # plazo 0: pasa al responsable
    db.refresh(rec)
    assert rec.estado == "aviso_responsable"
    recuperacion.pasada(db, ORG)                      # y a pendiente de aprobación
    db.refresh(rec)
    assert rec.estado == "pendiente_aprobacion"
    recuperacion.decidir(db, admin, rec.id, True, "sin uso")
    db.refresh(rec)
    db.refresh(a)
    assert rec.estado == "liberada" and a.status == "ended" and a.end_kind == "released"


def test_recuperacion_no_reclama_a_quien_esta_ausente_ni_a_una_asignacion_reciente(db):
    from app.models.resources import Absence, AbsenceStatus
    from app.services.alm_uso import recuperacion
    _politica_de_recuperacion(db)
    lic = _licencia(db)
    _asignar(db, lic, user_id="dev-test-id")
    _evidencia(db, lic, "dev-test-id", 90)
    hoy = date.today()
    db.add(Absence(organization_id=ORG, user_id="dev-test-id", type="vacation", status=AbsenceStatus.approved,
                   start_date=hoy - timedelta(days=2), end_date=hoy + timedelta(days=5), working_days=6))
    nueva = _asignar(db, lic, user_id="pm-test-id", dias=5)    # periodo de gracia
    _evidencia(db, lic, "pm-test-id", None, created_at=AHORA - timedelta(days=200))
    db.commit()
    r = recuperacion.pasada(db, ORG)
    assert r["abiertas"] == 0
    assert db.query(ALMUsoRecuperacion).count() == 0
    sim = recuperacion.previsualizar(db, ORG)
    assert all(i["accion"] in ("protegida", "sin_politica") for i in sim["items"])
    # La asignación de hace 5 días, nunca usada, aún no se puede juzgar: ni aparece.
    assert all(i["assignment_id"] != nueva.id for i in sim["items"])


def test_conservar_lo_protege_durante_el_plazo(db):
    from app.services.alm_uso import recuperacion
    _politica_de_recuperacion(db)
    lic = _licencia(db)
    _asignar(db, lic, user_id="dev-test-id")
    _evidencia(db, lic, "dev-test-id", 90)
    db.commit()
    recuperacion.pasada(db, ORG)
    rec = db.query(ALMUsoRecuperacion).one()
    dev = db.query(User).filter(User.id == "dev-test-id").one()
    recuperacion.conservar(db, dev, rec.id, "Lo uso en el cierre trimestral", es_gestor=False)
    assert recuperacion.pasada(db, ORG)["abiertas"] == 0


def test_simulador_no_escribe(db):
    from app.services.alm_uso import recuperacion
    _politica_de_recuperacion(db)
    lic = _licencia(db)
    _asignar(db, lic, user_id="dev-test-id")
    _evidencia(db, lic, "dev-test-id", 90)
    db.commit()
    sim = recuperacion.previsualizar(db, ORG)
    assert sim["resumen"]["iniciaria"] == 1 and sim["resumen"]["ahorro_anual_potencial"] == 360.0
    assert db.query(ALMUsoRecuperacion).count() == 0


# ── Ajuste de nivel ───────────────────────────────────────────────────────────

def test_ajuste_propone_bajar_si_no_usa_los_servicios_que_justifican(db):
    from app.services.alm_uso import ajuste
    e3 = _licencia(db, nombre="M365 E3", sku="SPE_E3", coste=3600, seats=10, product_name="Microsoft 365", tier="E3", tier_rank=3)
    e1 = _licencia(db, nombre="M365 E1", sku="STANDARDPACK", coste=1200, seats=10, product_name="Microsoft 365", tier="E1", tier_rank=1)
    _asignar(db, e3, user_id="dev-test-id")
    reciente = (AHORA - timedelta(days=3)).isoformat()
    _evidencia(db, e3, "dev-test-id", 3, servicios=json.dumps({"exchange": reciente, "teams": reciente}))
    admin = db.query(User).filter(User.id == "admin-test-id").one()
    db.commit()
    assert [s["license_inferior_id"] for s in ajuste.sugerencias(db, ORG)] == [e1.id]
    ajuste.guardar_regla(db, admin, {"license_superior_id": e3.id, "license_inferior_id": e1.id,
                                     "servicios": ["apps_escritorio"]})
    p = ajuste.propuestas(db, ORG)
    assert len(p["items"]) == 1 and p["items"][0]["ahorro_anual"] == 240.0


# ── Cumplimiento ──────────────────────────────────────────────────────────────

def test_cumplimiento_cuenta_quien_usa_sin_asignacion_y_da_deficit(db):
    from app.services.alm_uso import cumplimiento
    lic = _licencia(db, seats=1, coste=1200)
    _asignar(db, lic, user_id="dev-test-id")
    _evidencia(db, lic, "dev-test-id", 1)
    _evidencia(db, lic, None, 1, titular="externo@otra.com", asignada_en_fuente=True)
    db.commit()
    fila = next(f for f in cumplimiento.posicion(db, ORG)["items"] if f["license_id"] == lic.id)
    assert (fila["consumo"], fila["posicion"], fila["estado"], fila["exposicion"]) == (2, -1, "deficit", 1200.0)


def test_exportar_cumplimiento_csv(client, admin_token, db):
    _licencia(db)
    db.commit()
    r = client.get("/api/v1/alm/uso/cumplimiento/exportar?formato=csv", headers=auth(admin_token))
    assert r.status_code == 200 and "attachment" in r.headers["content-disposition"]
    assert "Licencia" in r.content.decode("utf-8-sig")


# ── Software no controlado ────────────────────────────────────────────────────

def test_gastos_de_software_fuera_de_alm_son_candidatos(db):
    from app.models.expenses import Expense, ExpenseCategory, ExpenseStatus
    from app.services.alm_uso import no_controlado
    _licencia(db, nombre="Adobe Acrobat")
    for i, (desc, uid) in enumerate((("Licencia Figma anual", "dev-test-id"), ("Suscripción Figma", "pm-test-id"),
                                     ("Renovación Adobe Acrobat", "dev-test-id"))):
        db.add(Expense(organization_id=ORG, code=f"EXP-9{i}", user_id=uid, category=ExpenseCategory.software,
                       description=desc, amount=100, currency="EUR", expense_date=date.today(),
                       status=ExpenseStatus.approved))
    db.commit()
    no_controlado.detectar_gastos(db, ORG)
    db.commit()
    lista = no_controlado.listar(db, ORG)
    assert [c["clave"] for c in lista["items"]] == ["figma"]
    assert lista["items"][0]["importe"] == 200.0 and lista["items"][0]["usuarios"] == 2


# ── Agente de inventario ──────────────────────────────────────────────────────

def test_checkin_del_agente_alimenta_activos_e_instalaciones(client, db):
    from app.services.cmdb.models import generate_agent_token
    lic = _licencia(db, nombre="7-Zip", sku=None, metric="device")
    tok = generate_agent_token(db, name="pc", organization_id=ORG)["token"]
    db.commit()
    r = client.post("/api/v1/sd/cmdb/agents/checkin", headers={"Authorization": f"Bearer {tok}"}, json={
        "hostname": "PC-42", "os_type": "windows", "serial_number": "SN-42", "model": "OptiPlex 7010",
        "primary_user": "dev@contecflow.com", "software": [{"name": "7-Zip", "version": "23.01"}]})
    assert r.status_code == 200, r.text
    assert r.json()["data"]["alm"]["inventario"] == "ok"
    activo = db.query(ALMAsset).filter(ALMAsset.serial_number == "SN-42").one()
    assert db.query(ALMSoftwareInstall).filter(ALMSoftwareInstall.asset_id == activo.id,
                                               ALMSoftwareInstall.license_id == lic.id).count() == 1


# ── Permisos ──────────────────────────────────────────────────────────────────

def test_un_empleado_no_ve_el_uso_de_los_demas(client, dev_token):
    for ruta in ("/api/v1/alm/uso/panel", "/api/v1/alm/uso/licencias", "/api/v1/alm/uso/recuperaciones",
                 "/api/v1/alm/uso/cumplimiento", "/api/v1/alm/uso/no-controlado"):
        assert client.get(ruta, headers=auth(dev_token)).status_code == 403, ruta
    assert client.get("/api/v1/alm/uso/recuperaciones/mias", headers=auth(dev_token)).status_code == 200


def test_solo_un_administrador_configura_fuentes_y_nunca_ve_un_secreto(client, admin_token, pm_token):
    assert client.get("/api/v1/alm/uso/conexiones", headers=auth(pm_token)).status_code == 403
    r = client.put("/api/v1/alm/uso/conexiones/okta", headers=auth(admin_token),
                   json={"credenciales": {"base_url": "https://acme.okta.com", "api_token": "super-secreto"}})
    assert r.status_code == 200, r.text
    okta = r.json()["data"]
    assert okta["lista"] is True and "super-secreto" not in r.text
    token = next(c for c in okta["credenciales"] if c["clave"] == "api_token")
    assert token["configurado"] is True and token["valor"] is None


def test_activar_sin_credenciales_se_niega(client, admin_token):
    r = client.put("/api/v1/alm/uso/conexiones/jamf", headers=auth(admin_token), json={"activa": True})
    assert r.status_code == 422
    assert r.json()["detail"]["code"] == "ALM_USAGE_MISSING_CREDENTIALS"


def test_el_dominio_licencias_esta_registrado_con_recuperar():
    from app.services.politicas import catalogo
    d = catalogo.dominio("licencias")
    assert d.resultado_propio("recuperar") is not None
    assert {"dias_sin_uso_efectivos", "en_ausencia", "fiabilidad", "coste_anual"} <= {c.clave for c in d.campos}
