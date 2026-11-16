"""Okta: usuarios, asignaciones de aplicaciones y accesos SSO del System Log.

Credenciales: proveedor `alm_okta` de la empresa (URL de la organización y un
token de API de un administrador de solo lectura, cabecera `SSWS`). La URL la
escribe el cliente: se valida (https, sin redes internas) en cada llamada.

Lee:
  1. `GET /api/v1/users` → cuentas, estado y `lastLogin`: una evidencia del
     producto `okta` (la licencia de Okta por usuario).
  2. `GET /api/v1/apps?filter=status eq "ACTIVE"` y `GET /api/v1/apps/{id}/users`
     → quién tiene asignada cada aplicación (asignada = sí).
  3. `GET /api/v1/logs` con `eventType eq "user.authentication.sso"` del
     periodo → último acceso SSO y días distintos con acceso (frecuencia) de
     cada persona a cada aplicación.

Cada aplicación es un producto `app:<id>` con su nombre visible; se concilia
con ALM por el mapeo o por el nombre. Las aplicaciones con gente asignada que
no estén en ALM son candidatas a software no controlado.
"""
from __future__ import annotations

from datetime import timedelta

from app.services.alm_uso._comun import a_fecha_hora, ahora, max_fecha
from app.services.alm_uso.proveedores.base import (
    Aplicacion, ContextoDeLectura, ErrorDeConector, Evidencia, ProveedorDeUso, ResultadoDeLectura,
)
from app.services.alm_uso.proveedores.http import siguiente_de_link


def _base(ctx: ContextoDeLectura) -> str:
    b = (ctx.credenciales.get("base_url") or "").strip().rstrip("/")
    if not b.lower().startswith("https://"):
        raise ErrorDeConector("BAD_CREDENTIALS", "La URL de Okta debe empezar por https://")
    return b


def _paginas(ctx: ContextoDeLectura, url: str, params: dict, res: ResultadoDeLectura | None = None) -> list:
    h = {"Authorization": f"SSWS {ctx.credenciales['api_token']}", "Accept": "application/json"}
    salida, siguiente, n = [], url, 0
    while siguiente:
        if n >= ctx.max_paginas:
            if res is not None:
                res.avisar("TRUNCATED", f"Lectura cortada tras {ctx.max_paginas} páginas ({url})")
            break
        cuerpo, cab = ctx.http.obtener_json(siguiente, headers=h, params=params if n == 0 else None)
        if isinstance(cuerpo, list):
            salida.extend(cuerpo)
        siguiente = siguiente_de_link(cab)
        n += 1
    return salida


class Okta(ProveedorDeUso):
    clave = "okta"
    etiqueta = "Okta"
    credencial = "alm_okta"
    obligatorias = ("base_url", "api_token")
    fiabilidad = "media"
    permisos = ("Token de API de un administrador de solo lectura (Read-only Administrator): okta.users.read, "
                "okta.apps.read, okta.logs.read",)
    aporta = ("evidencias", "aplicaciones")

    def leer(self, ctx: ContextoDeLectura) -> ResultadoDeLectura:
        res = ResultadoDeLectura()
        base = _base(ctx)
        cuentas: dict = {}
        for u in _paginas(ctx, f"{base}/api/v1/users", {"limit": "200"}, res):
            perfil = u.get("profile") or {}
            login = (perfil.get("login") or perfil.get("email") or "").lower()
            if not login:
                continue
            cuentas[u.get("id")] = login
            activa = u.get("status") in ("ACTIVE", "PASSWORD_EXPIRED", "LOCKED_OUT", "RECOVERY")
            res.evidencias.append(Evidencia(
                titular_tipo="persona", titular=login, producto="okta", nombre_producto="Okta",
                ultimo_uso=a_fecha_hora(u.get("lastLogin")), asignada=activa,
                servicios={"inicio_de_sesion": a_fecha_hora(u.get("lastLogin"))},
                detalle={"cuenta_activa": activa, "estado": u.get("status"), "id_externo": u.get("id")}))

        apps = _paginas(ctx, f"{base}/api/v1/apps", {"limit": "200", "filter": 'status eq "ACTIVE"'}, res)
        asignados: dict = {}
        for a in apps:
            gente = set()
            for au in _paginas(ctx, f"{base}/api/v1/apps/{a.get('id')}/users", {"limit": "500"}, res):
                login = cuentas.get(au.get("id")) or ((au.get("credentials") or {}).get("userName") or "").lower()
                if login:
                    gente.add(login)
            asignados[a.get("id")] = (a.get("label") or a.get("name") or a.get("id"), gente)

        accesos: dict = {}
        desde = (ctx.ahora or ahora()) - timedelta(days=ctx.periodo_dias)
        try:
            eventos = _paginas(ctx, f"{base}/api/v1/logs", {
                "since": desde.strftime("%Y-%m-%dT%H:%M:%SZ"),
                "until": (ctx.ahora or ahora()).strftime("%Y-%m-%dT%H:%M:%SZ"),
                "filter": 'eventType eq "user.authentication.sso"', "limit": "1000"}, res)
        except ErrorDeConector as e:
            if e.codigo not in ("FORBIDDEN",):
                raise
            res.avisar("SYSTEM_LOG_UNAVAILABLE", "Sin permiso para el System Log: solo asignaciones y último acceso")
            eventos = []
        for ev in eventos:
            login = ((ev.get("actor") or {}).get("alternateId") or "").lower()
            cuando = a_fecha_hora(ev.get("published"))
            for t in ev.get("target") or []:
                if t.get("type") != "AppInstance" or not login or cuando is None:
                    continue
                d = accesos.setdefault((login, t.get("id")), {"ultimo": None, "dias": set(), "nombre": t.get("displayName")})
                d["ultimo"] = max_fecha(d["ultimo"], cuando)
                d["dias"].add(cuando.date())

        vistos = set()
        for app_id, (nombre, gente) in asignados.items():
            usuarios = set(gente)
            for (login, aid), d in accesos.items():
                if aid == app_id:
                    usuarios.add(login)
            ultimo_app = None
            for login in usuarios:
                d = accesos.get((login, app_id)) or {}
                ultimo_app = max_fecha(ultimo_app, d.get("ultimo"))
                vistos.add((login, app_id))
                res.evidencias.append(Evidencia(
                    titular_tipo="persona", titular=login, producto=f"app:{app_id}", nombre_producto=nombre,
                    ultimo_uso=d.get("ultimo"), frecuencia=len(d.get("dias") or ()) if eventos else None,
                    periodo_dias=ctx.periodo_dias, asignada=login in gente,
                    servicios={"sso": d.get("ultimo")}, detalle={"aplicacion_id": app_id}))
            res.aplicaciones.append(Aplicacion(nombre=nombre, usuarios=len(usuarios), ultimo_uso=ultimo_app,
                                               origen="okta"))
        # Accesos a aplicaciones que ya no están activas (o no se listaron).
        for (login, aid), d in accesos.items():
            if (login, aid) in vistos:
                continue
            res.evidencias.append(Evidencia(
                titular_tipo="persona", titular=login, producto=f"app:{aid}", nombre_producto=d.get("nombre"),
                ultimo_uso=d["ultimo"], frecuencia=len(d["dias"]), periodo_dias=ctx.periodo_dias, asignada=False,
                servicios={"sso": d["ultimo"]}, detalle={"aplicacion_id": aid}))
        return res

    def probar(self, ctx: ContextoDeLectura) -> dict:
        base = _base(ctx)
        cuerpo, _ = ctx.http.obtener_json(f"{base}/api/v1/users", params={"limit": "1"},
                                          headers={"Authorization": f"SSWS {ctx.credenciales['api_token']}",
                                                   "Accept": "application/json"})
        return {"ok": True, "muestra": len(cuerpo) if isinstance(cuerpo, list) else 0}
