"""Microsoft 365 / Entra ID e Intune por Microsoft Graph (permisos de aplicación).

Credenciales: proveedor `alm_m365` de la empresa (tenant, client id, secreto).
Token: flujo client credentials contra `MICROSOFT_OAUTH_BASE/<tenant>`.

Microsoft 365 (`m365`) lee:
  1. `GET /subscribedSkus` → derechos: comprados (`prepaidUnits.enabled`),
     consumidos, suspendidos; y los planes de servicio de cada SKU.
  2. `GET /users?$select=…assignedLicenses,signInActivity` → quién tiene cada
     SKU, si la cuenta está activa y su último inicio de sesión. Sin permiso
     para `signInActivity` (AuditLog.Read.All y Entra ID P1) se repite sin él y
     queda un aviso: el resto sigue valiendo.
  3. Informes de uso (Reports.Read.All): `getOffice365ActiveUserDetail` (último
     uso de Exchange, OneDrive, SharePoint, Teams, Yammer, Skype) y
     `getM365AppUserDetail` (aplicaciones de escritorio). Si la empresa oculta
     los nombres en los informes (opción de privacidad del centro de
     administración), las filas no se pueden atribuir: aviso y se ignoran.

  Una evidencia por (usuario, SKU). El último uso de un SKU es el más reciente
  de los servicios que ESE SKU incluye (por sus planes de servicio): usar el
  correo no prueba que se use Visio. Si el SKU no incluye ningún servicio que
  los informes midan, se usa el último inicio de sesión y la evidencia baja un
  nivel de fiabilidad (`detalle.base = inicio_de_sesion`).

Intune (`intune`) lee `GET /deviceManagement/managedDevices` (nº de serie,
último check-in, usuario principal, sistema) y `detectedApps` con sus
dispositivos (hasta `ALM_USAGE_INTUNE_MAX_APPS` aplicaciones, las más
extendidas primero; si hay más, el software de esa lectura queda incompleto y
no se retira ninguna instalación).
"""
from __future__ import annotations

import csv
import io
from typing import Optional

from app.core.config import settings
from app.services.alm_uso._comun import a_fecha_hora, max_fecha
from app.services.alm_uso.proveedores.base import (
    AppInstalada, ContextoDeLectura, Derecho, Dispositivo, ErrorDeConector, Evidencia, ProveedorDeUso,
    ResultadoDeLectura,
)

#: Prefijo del nombre de un plan de servicio de Microsoft → servicio que miden
#: los informes de uso. Es el catálogo público de planes de Microsoft
#: (https://learn.microsoft.com/entra/identity/users/licensing-service-plan-reference),
#: no un umbral: una empresa puede añadir prefijos con la opción `planes_extra`.
PLANES_A_SERVICIO = (
    ("EXCHANGE", "exchange"),
    ("SHAREPOINT", "sharepoint"),
    ("ONEDRIVE", "onedrive"),
    ("TEAMS", "teams"),
    ("MCOSTANDARD", "skype"),
    ("YAMMER", "yammer"),
    ("OFFICESUBSCRIPTION", "apps_escritorio"),
    ("OFFICE_BUSINESS", "apps_escritorio"),
)

#: Columna del informe `getOffice365ActiveUserDetail` → servicio.
COLUMNAS_O365 = {
    "Exchange Last Activity Date": "exchange",
    "OneDrive Last Activity Date": "onedrive",
    "SharePoint Last Activity Date": "sharepoint",
    "Skype For Business Last Activity Date": "skype",
    "Yammer Last Activity Date": "yammer",
    "Teams Last Activity Date": "teams",
}

#: Periodos que aceptan los informes de Graph.
PERIODOS = (7, 30, 90, 180)


def _graph() -> str:
    return f"{settings.MICROSOFT_GRAPH_BASE}/v1.0"


def token(ctx: ContextoDeLectura) -> str:
    c = ctx.credenciales
    url = f"{settings.MICROSOFT_OAUTH_BASE}/{c['tenant_id']}/oauth2/v2.0/token"
    r = ctx.http.enviar_formulario(url, {
        "grant_type": "client_credentials", "client_id": c["client_id"], "client_secret": c["client_secret"],
        "scope": f"{settings.MICROSOFT_GRAPH_BASE}/.default"})
    t = (r or {}).get("access_token")
    if not t:
        raise ErrorDeConector("AUTH_FAILED", "Microsoft no devolvió un token")
    return t


def paginas(ctx: ContextoDeLectura, url: str, tok: str, res: Optional[ResultadoDeLectura] = None,
            params: Optional[dict] = None, cabeceras: Optional[dict] = None) -> list:
    """Todos los `value` siguiendo `@odata.nextLink`, hasta `max_paginas`."""
    salida: list = []
    h = {"Authorization": f"Bearer {tok}", **(cabeceras or {})}
    siguiente, n = url, 0
    while siguiente:
        if n >= ctx.max_paginas:
            if res is not None:
                res.avisar("TRUNCATED", f"Lectura cortada tras {ctx.max_paginas} páginas ({url.split('?')[0]})")
            break
        cuerpo, _ = ctx.http.obtener_json(siguiente, headers=h, params=params if n == 0 else None)
        salida.extend(cuerpo.get("value") or [])
        siguiente = cuerpo.get("@odata.nextLink")
        n += 1
    return salida


def periodo_de_informe(dias: int) -> str:
    return f"D{next((p for p in PERIODOS if p >= dias), PERIODOS[-1])}"


def _csv(texto: str) -> list[dict]:
    texto = (texto or "").lstrip("﻿")
    return list(csv.DictReader(io.StringIO(texto))) if texto.strip() else []


def _servicios_de_planes(planes: list, extra: dict) -> set:
    tabla = list(PLANES_A_SERVICIO) + [(k.upper(), v) for k, v in (extra or {}).items()]
    salida = set()
    for p in planes or []:
        nombre = str(p.get("servicePlanName") or "").upper()
        for prefijo, servicio in tabla:
            if nombre.startswith(prefijo):
                salida.add(servicio)
    return salida


class Microsoft365(ProveedorDeUso):
    clave = "m365"
    etiqueta = "Microsoft 365 / Entra ID"
    credencial = "alm_m365"
    obligatorias = ("tenant_id", "client_id", "client_secret")
    fiabilidad = "alta"
    permisos = ("Organization.Read.All (subscribedSkus)", "User.Read.All (usuarios y licencias asignadas)",
                "AuditLog.Read.All (signInActivity; requiere Entra ID P1/P2)",
                "Reports.Read.All (informes de uso de Microsoft 365)")
    aporta = ("evidencias", "derechos")
    opciones = (("planes_extra", "JSON {prefijo de plan de servicio: servicio} que se suma al catálogo"),)

    def leer(self, ctx: ContextoDeLectura) -> ResultadoDeLectura:
        res = ResultadoDeLectura()
        tok = token(ctx)
        g = _graph()

        skus = paginas(ctx, f"{g}/subscribedSkus", tok, res)
        por_id: dict = {}
        extra = ctx.configuracion.get("planes_extra") or {}
        for s in skus:
            parte = s.get("skuPartNumber") or s.get("skuId")
            pre = s.get("prepaidUnits") or {}
            servicios = _servicios_de_planes(s.get("servicePlans"), extra)
            por_id[s.get("skuId")] = (parte, servicios)
            res.derechos.append(Derecho(sku=parte, nombre=parte, comprados=pre.get("enabled"),
                                        consumidos=s.get("consumedUnits"), suspendidos=pre.get("suspended"),
                                        detalle={"sku_id": s.get("skuId"), "aviso": pre.get("warning"),
                                                 "servicios": sorted(servicios)}))

        seleccion = "id,userPrincipalName,mail,accountEnabled,assignedLicenses"
        try:
            usuarios = paginas(ctx, f"{g}/users", tok, res, params={"$select": seleccion + ",signInActivity",
                                                                     "$top": "999"})
            con_inicio = True
        except ErrorDeConector as e:
            if e.codigo not in ("FORBIDDEN", "BAD_REQUEST"):
                raise
            res.avisar("SIGNIN_ACTIVITY_UNAVAILABLE",
                       "Sin permiso para signInActivity (AuditLog.Read.All y Entra ID P1): se lee sin último inicio de sesión")
            usuarios = paginas(ctx, f"{g}/users", tok, res, params={"$select": seleccion, "$top": "999"})
            con_inicio = False

        actividad = self._informes(ctx, tok, res)

        for u in usuarios:
            upn = (u.get("userPrincipalName") or u.get("mail") or "").strip().lower()
            if not upn:
                continue
            inicio = u.get("signInActivity") or {}
            ultimo_inicio = max_fecha(a_fecha_hora(inicio.get("lastSignInDateTime")),
                                      a_fecha_hora(inicio.get("lastNonInteractiveSignInDateTime")),
                                      a_fecha_hora(inicio.get("lastSuccessfulSignInDateTime")))
            de_informe = actividad.get(upn) or {}
            for lic in u.get("assignedLicenses") or []:
                parte, incluidos = por_id.get(lic.get("skuId"), (lic.get("skuId"), set()))
                if not parte:
                    continue
                servicios = {k: v for k, v in de_informe.items() if k in incluidos}
                medido = max_fecha(*servicios.values())
                detalle = {"cuenta_activa": u.get("accountEnabled"), "id_externo": u.get("id")}
                if medido is None and (con_inicio and ultimo_inicio is not None):
                    detalle["base"] = "inicio_de_sesion"
                    detalle["fiabilidad_reducida"] = True
                elif medido is not None:
                    detalle["base"] = "informes_de_uso"
                servicios["inicio_de_sesion"] = ultimo_inicio
                res.evidencias.append(Evidencia(
                    titular_tipo="persona", titular=upn, producto=parte, nombre_producto=parte, sku=lic.get("skuId"),
                    ultimo_uso=medido if medido is not None else ultimo_inicio,
                    servicios=servicios, asignada=True, periodo_dias=ctx.periodo_dias, detalle=detalle))
        return res

    def _informes(self, ctx: ContextoDeLectura, tok: str, res: ResultadoDeLectura) -> dict:
        """{upn: {servicio: datetime}} de los informes de uso; vacío si no hay permiso."""
        g = _graph()
        periodo = periodo_de_informe(ctx.periodo_dias)
        h = {"Authorization": f"Bearer {tok}"}
        salida: dict = {}
        ocultos = 0
        try:
            filas = _csv(ctx.http.obtener_texto(f"{g}/reports/getOffice365ActiveUserDetail(period='{periodo}')",
                                                headers=h))
            for f in filas:
                upn = (f.get("User Principal Name") or "").strip().lower()
                if "@" not in upn:
                    ocultos += 1
                    continue
                d = salida.setdefault(upn, {})
                for col, servicio in COLUMNAS_O365.items():
                    v = a_fecha_hora(f.get(col))
                    if v is not None:
                        d[servicio] = v
            filas = _csv(ctx.http.obtener_texto(f"{g}/reports/getM365AppUserDetail(period='{periodo}')", headers=h))
            for f in filas:
                upn = (f.get("User Principal Name") or "").strip().lower()
                if "@" not in upn:
                    ocultos += 1
                    continue
                escritorio = any((f.get(c) or "").strip().lower() == "yes" for c in ("Windows", "Mac"))
                v = a_fecha_hora(f.get("Last Activity Date"))
                if escritorio and v is not None:
                    salida.setdefault(upn, {})["apps_escritorio"] = v
        except ErrorDeConector as e:
            if e.codigo not in ("FORBIDDEN", "NOT_FOUND", "BAD_REQUEST"):
                raise
            res.avisar("REPORTS_UNAVAILABLE",
                       "Sin informes de uso (Reports.Read.All): el uso se mide por el último inicio de sesión")
        if ocultos:
            res.avisar("REPORTS_CONCEALED", f"{ocultos} filas de los informes tienen el nombre oculto: desactiva "
                                            "«Mostrar nombres ocultos en los informes» en el centro de administración")
        return salida

    def probar(self, ctx: ContextoDeLectura) -> dict:
        tok = token(ctx)
        skus = paginas(ctx, f"{_graph()}/subscribedSkus", tok)
        return {"ok": True, "skus": len(skus)}


class Intune(ProveedorDeUso):
    clave = "intune"
    etiqueta = "Microsoft Intune"
    credencial = "alm_m365"
    obligatorias = ("tenant_id", "client_id", "client_secret")
    fiabilidad = "alta"
    permisos = ("DeviceManagementManagedDevices.Read.All (dispositivos y aplicaciones detectadas)",)
    aporta = ("dispositivos",)

    def leer(self, ctx: ContextoDeLectura) -> ResultadoDeLectura:
        res = ResultadoDeLectura()
        tok = token(ctx)
        g = _graph()
        sel = ("id,deviceName,serialNumber,userPrincipalName,emailAddress,lastSyncDateTime,operatingSystem,"
               "osVersion,manufacturer,model,complianceState,managedDeviceOwnerType")
        crudos = paginas(ctx, f"{g}/deviceManagement/managedDevices", tok, res, params={"$select": sel})
        por_id: dict = {}
        for d in crudos:
            disp = Dispositivo(
                externo_id=str(d.get("id")), nombre=d.get("deviceName"), serie=(d.get("serialNumber") or None),
                sistema=d.get("operatingSystem"), version_sistema=d.get("osVersion"),
                fabricante=d.get("manufacturer"), modelo=d.get("model"),
                usuario=(d.get("userPrincipalName") or d.get("emailAddress") or "").lower() or None,
                ultimo_contacto=a_fecha_hora(d.get("lastSyncDateTime")),
                detalle={"cumplimiento": d.get("complianceState"), "propiedad": d.get("managedDeviceOwnerType")})
            por_id[disp.externo_id] = disp
            res.dispositivos.append(disp)

        apps = paginas(ctx, f"{g}/deviceManagement/detectedApps", tok, res,
                       params={"$select": "id,displayName,version,publisher,deviceCount"})
        apps.sort(key=lambda a: -(a.get("deviceCount") or 0))
        completas = len(apps) <= ctx.max_apps and not any(a["codigo"] == "TRUNCATED" for a in res.avisos)
        if len(apps) > ctx.max_apps:
            res.avisar("APPS_TRUNCATED", f"Hay {len(apps)} aplicaciones detectadas; se leen las {ctx.max_apps} más "
                                         "extendidas (ALM_USAGE_INTUNE_MAX_APPS). No se retira ninguna instalación.")
        for a in apps[:ctx.max_apps]:
            nombre = (a.get("displayName") or "").strip()
            if not nombre:
                continue
            for d in paginas(ctx, f"{g}/deviceManagement/detectedApps/{a.get('id')}/managedDevices", tok, res,
                             params={"$select": "id"}):
                disp = por_id.get(str(d.get("id")))
                if disp is not None:
                    disp.apps.append(AppInstalada(nombre=nombre, version=a.get("version"), editor=a.get("publisher")))
        for disp in res.dispositivos:
            disp.apps_leidas = completas
        return res

    def probar(self, ctx: ContextoDeLectura) -> dict:
        tok = token(ctx)
        cuerpo, _ = ctx.http.obtener_json(f"{_graph()}/deviceManagement/managedDevices",
                                          headers={"Authorization": f"Bearer {tok}"},
                                          params={"$select": "id", "$top": "1"})
        return {"ok": True, "muestra": len(cuerpo.get("value") or [])}
