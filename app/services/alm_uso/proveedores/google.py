"""Google Workspace por Admin SDK (Directory, Reports) y Enterprise License Manager.

Credenciales: proveedor `alm_google` de la empresa — la clave JSON de una
cuenta de servicio con delegación de todo el dominio, el administrador al que
suplanta (`admin_email`) y el cliente (`customer_id`, `my_customer` por defecto).
Token: aserción JWT (RS256) firmada con la clave de la cuenta de servicio contra
su `token_uri`.

Lee:
  1. Directory `users.list` → cuentas, suspendidas y `lastLoginTime`.
  2. Licensing `listForProduct` de cada producto de la opción `productos`
     (por defecto `Google-Apps`, Workspace) → quién tiene cada SKU. La API pide
     el dominio principal o el id de cliente: con `my_customer` hace falta la
     opción `dominio`; si falta, aviso y la evidencia es por producto.
  3. Reports `usage/users` del día `hoy - retraso_informes_dias` (Google publica
     el uso con hasta 3 días de retraso) → último uso de cada servicio (gmail,
     drive, calendar, meet, docs…).
  4. Reports `activity` de la aplicación `token` → aplicaciones de terceros a
     las que la gente dio acceso con su cuenta (software no controlado).
"""
from __future__ import annotations

import json
import time
from datetime import timedelta
from typing import Optional

from app.core.config import settings
from app.services.alm_uso._comun import a_fecha_hora, ahora, max_fecha
from app.services.alm_uso.proveedores.base import (
    Aplicacion, ContextoDeLectura, ErrorDeConector, Evidencia, ProveedorDeUso, ResultadoDeLectura,
)

ALCANCES = (
    "https://www.googleapis.com/auth/admin.directory.user.readonly",
    "https://www.googleapis.com/auth/admin.reports.usage.readonly",
    "https://www.googleapis.com/auth/admin.reports.audit.readonly",
    "https://www.googleapis.com/auth/apps.licensing",
)
#: Días que Google tarda en publicar el informe de uso (documentado por Google);
#: se puede cambiar con la opción `retraso_informes_dias` de la conexión.
RETRASO_DE_INFORMES = 3


def token(ctx: ContextoDeLectura) -> str:
    import jwt
    try:
        cuenta = json.loads(ctx.credenciales["service_account_json"])
    except (TypeError, ValueError) as exc:
        raise ErrorDeConector("BAD_CREDENTIALS", "La clave de la cuenta de servicio no es un JSON válido") from exc
    if not cuenta.get("client_email") or not cuenta.get("private_key"):
        raise ErrorDeConector("BAD_CREDENTIALS", "A la clave de la cuenta de servicio le falta client_email o private_key")
    uri = cuenta.get("token_uri") or settings.GOOGLE_TOKEN_URL
    ahora = int(time.time())
    try:
        asercion = jwt.encode({"iss": cuenta["client_email"], "sub": ctx.credenciales["admin_email"],
                               "scope": " ".join(ALCANCES), "aud": uri, "iat": ahora, "exp": ahora + 3600},
                              cuenta["private_key"], algorithm="RS256")
    except Exception as exc:  # clave privada ilegible
        raise ErrorDeConector("BAD_CREDENTIALS", "No se pudo firmar con la clave de la cuenta de servicio") from exc
    r = ctx.http.enviar_formulario(uri, {"grant_type": "urn:ietf:params:oauth:grant-type:jwt-bearer",
                                         "assertion": asercion})
    t = (r or {}).get("access_token")
    if not t:
        raise ErrorDeConector("AUTH_FAILED", "Google no devolvió un token")
    return t


def _paginas(ctx: ContextoDeLectura, url: str, tok: str, clave: str, params: dict,
             res: Optional[ResultadoDeLectura] = None) -> list:
    salida, n, pagina = [], 0, None
    h = {"Authorization": f"Bearer {tok}"}
    while True:
        if n >= ctx.max_paginas:
            if res is not None:
                res.avisar("TRUNCATED", f"Lectura cortada tras {ctx.max_paginas} páginas ({url})")
            break
        p = dict(params)
        if pagina:
            p["pageToken"] = pagina
        cuerpo, _ = ctx.http.obtener_json(url, headers=h, params=p)
        salida.extend(cuerpo.get(clave) or [])
        pagina = cuerpo.get("nextPageToken")
        n += 1
        if not pagina:
            break
    return salida


class GoogleWorkspace(ProveedorDeUso):
    clave = "google"
    etiqueta = "Google Workspace"
    credencial = "alm_google"
    obligatorias = ("service_account_json", "admin_email")
    fiabilidad = "alta"
    permisos = tuple(f"Delegación de dominio con el alcance {a}" for a in ALCANCES) + (
        "El administrador suplantado necesita los privilegios de Usuarios (lectura), Informes y Licencias",)
    aporta = ("evidencias", "aplicaciones")
    opciones = (("productos", "Lista de productos de Licensing (por defecto [\"Google-Apps\"])"),
                ("dominio", "Dominio principal, para Licensing cuando el cliente es my_customer"),
                ("retraso_informes_dias", "Días de retraso del informe de uso (por defecto 3)"))

    def leer(self, ctx: ContextoDeLectura) -> ResultadoDeLectura:
        res = ResultadoDeLectura()
        tok = token(ctx)
        admin = settings.GOOGLE_ADMIN_API_BASE
        cliente = ctx.credenciales.get("customer_id") or "my_customer"
        usuarios = _paginas(ctx, f"{admin}/admin/directory/v1/users", tok, "users",
                            {"customer": cliente, "maxResults": "500", "projection": "basic"}, res)
        cuentas = {}
        for u in usuarios:
            correo = (u.get("primaryEmail") or "").lower()
            if correo:
                cuentas[correo] = {"login": a_fecha_hora(u.get("lastLoginTime")), "suspendida": bool(u.get("suspended")),
                                   "id": u.get("id")}

        uso = self._uso(ctx, tok, res)
        licencias = self._licencias(ctx, tok, cliente, res)
        if licencias is None:
            licencias = [{"userId": c, "productId": "Google-Apps", "skuId": "Google-Apps", "skuName": "Google Workspace"}
                         for c, d in cuentas.items() if not d["suspendida"]]
            asignada = None
        else:
            asignada = True
        for item in licencias:
            correo = (item.get("userId") or "").lower()
            if not correo:
                continue
            cuenta = cuentas.get(correo) or {}
            servicios = dict(uso.get(correo) or {})
            servicios["inicio_de_sesion"] = cuenta.get("login")
            medido = max_fecha(*[v for k, v in servicios.items() if k != "inicio_de_sesion"])
            detalle = {"cuenta_activa": not cuenta.get("suspendida", False), "id_externo": cuenta.get("id"),
                       "producto_id": item.get("productId"),
                       "base": "informes_de_uso" if medido is not None else "inicio_de_sesion"}
            if medido is None:
                detalle["fiabilidad_reducida"] = True
            res.evidencias.append(Evidencia(
                titular_tipo="persona", titular=correo, producto=item.get("skuId") or item.get("productId"),
                nombre_producto=item.get("skuName") or item.get("skuId"), sku=item.get("skuId"),
                ultimo_uso=max_fecha(medido, cuenta.get("login")), servicios=servicios, asignada=asignada,
                periodo_dias=ctx.periodo_dias, detalle=detalle))

        res.aplicaciones.extend(self._aplicaciones(ctx, tok, res))
        return res

    def _licencias(self, ctx, tok, cliente, res) -> Optional[list]:
        dominio = ctx.configuracion.get("dominio") or (cliente if cliente != "my_customer" else None)
        if not dominio:
            res.avisar("LICENSING_NEEDS_DOMAIN", "Licensing necesita el dominio principal (opción «dominio») o el id "
                                                 "de cliente: se mide por producto, sin SKU")
            return None
        salida: list = []
        try:
            for producto in ctx.configuracion.get("productos") or ["Google-Apps"]:
                salida += _paginas(ctx, f"{settings.GOOGLE_LICENSING_API_BASE}/apps/licensing/v1/product/"
                                        f"{producto}/users", tok, "items",
                                   {"customerId": dominio, "maxResults": "1000"}, res)
        except ErrorDeConector as e:
            if e.codigo not in ("FORBIDDEN", "NOT_FOUND", "BAD_REQUEST"):
                raise
            res.avisar("LICENSING_UNAVAILABLE", f"Licensing no disponible ({e.mensaje}): se mide por producto")
            return None
        return salida

    def _uso(self, ctx, tok, res) -> dict:
        retraso = int(ctx.configuracion.get("retraso_informes_dias") or RETRASO_DE_INFORMES)
        dia = ((ctx.ahora or ahora()) - timedelta(days=retraso)).date().isoformat()
        try:
            filas = _paginas(ctx, f"{settings.GOOGLE_ADMIN_API_BASE}/admin/reports/v1/usage/users/all/dates/{dia}",
                             tok, "usageReports", {"maxResults": "1000"}, res)
        except ErrorDeConector as e:
            if e.codigo not in ("FORBIDDEN", "BAD_REQUEST", "NOT_FOUND"):
                raise
            res.avisar("REPORTS_UNAVAILABLE", f"Informe de uso no disponible ({e.mensaje}): se usa el último acceso")
            return {}
        salida: dict = {}
        for f in filas:
            correo = ((f.get("entity") or {}).get("userEmail") or "").lower()
            if not correo:
                continue
            d = salida.setdefault(correo, {})
            for p in f.get("parameters") or []:
                nombre = str(p.get("name") or "")
                if "last" not in nombre or ":" not in nombre:
                    continue
                v = a_fecha_hora(p.get("datetimeValue"))
                servicio = nombre.split(":", 1)[0]
                if servicio == "accounts" or v is None:
                    continue
                d[servicio] = max_fecha(d.get(servicio), v)
        return salida

    def _aplicaciones(self, ctx, tok, res) -> list:
        desde = ((ctx.ahora or ahora()) - timedelta(days=ctx.periodo_dias))
        try:
            items = _paginas(ctx, f"{settings.GOOGLE_ADMIN_API_BASE}/admin/reports/v1/activity/users/all/"
                                  "applications/token", tok, "items",
                             {"startTime": desde.strftime("%Y-%m-%dT%H:%M:%SZ"), "maxResults": "1000"}, res)
        except ErrorDeConector as e:
            if e.codigo not in ("FORBIDDEN", "BAD_REQUEST", "NOT_FOUND"):
                raise
            res.avisar("TOKEN_AUDIT_UNAVAILABLE", "No se pudieron leer las aplicaciones autorizadas con la cuenta")
            return []
        apps: dict = {}
        for it in items:
            quien = ((it.get("actor") or {}).get("email") or "").lower()
            cuando = a_fecha_hora((it.get("id") or {}).get("time"))
            for ev in it.get("events") or []:
                nombre = next((p.get("value") for p in ev.get("parameters") or [] if p.get("name") == "app_name"), None)
                if not nombre:
                    continue
                a = apps.setdefault(nombre, {"usuarios": set(), "ultimo": None})
                a["usuarios"].add(quien)
                a["ultimo"] = max_fecha(a["ultimo"], cuando)
        return [Aplicacion(nombre=n, usuarios=len(d["usuarios"]), ultimo_uso=d["ultimo"], origen="google_oauth")
                for n, d in apps.items()]

    def probar(self, ctx: ContextoDeLectura) -> dict:
        tok = token(ctx)
        cuerpo, _ = ctx.http.obtener_json(f"{settings.GOOGLE_ADMIN_API_BASE}/admin/directory/v1/users",
                                          headers={"Authorization": f"Bearer {tok}"},
                                          params={"customer": ctx.credenciales.get("customer_id") or "my_customer",
                                                  "maxResults": "1"})
        return {"ok": True, "muestra": len(cuerpo.get("users") or [])}
