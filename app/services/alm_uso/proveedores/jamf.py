"""Jamf Pro: inventario de ordenadores (nº de serie, último contacto, usuario, aplicaciones).

Credenciales: proveedor `alm_jamf` de la empresa (URL de Jamf Pro y un cliente
de API con su secreto). Token: `POST /api/oauth/token` (client credentials).
La URL la escribe el cliente: se valida (https, sin redes internas).

Lee `GET /api/v1/computers-inventory` por páginas con las secciones GENERAL,
HARDWARE, OPERATING_SYSTEM, USER_AND_LOCATION y APPLICATIONS. Cada ordenador
es un `Dispositivo`; su lista de aplicaciones es completa (se pueden retirar
las instalaciones que ya no aparecen).
"""
from __future__ import annotations

from app.services.alm_uso._comun import a_fecha_hora
from app.services.alm_uso.proveedores.base import (
    AppInstalada, ContextoDeLectura, Dispositivo, ErrorDeConector, ProveedorDeUso, ResultadoDeLectura,
)

SECCIONES = ["GENERAL", "HARDWARE", "OPERATING_SYSTEM", "USER_AND_LOCATION", "APPLICATIONS"]


def _base(ctx: ContextoDeLectura) -> str:
    b = (ctx.credenciales.get("base_url") or "").strip().rstrip("/")
    if not b.lower().startswith("https://"):
        raise ErrorDeConector("BAD_CREDENTIALS", "La URL de Jamf Pro debe empezar por https://")
    return b


def token(ctx: ContextoDeLectura) -> str:
    r = ctx.http.enviar_formulario(f"{_base(ctx)}/api/oauth/token", {
        "grant_type": "client_credentials", "client_id": ctx.credenciales["client_id"],
        "client_secret": ctx.credenciales["client_secret"]})
    t = (r or {}).get("access_token")
    if not t:
        raise ErrorDeConector("AUTH_FAILED", "Jamf Pro no devolvió un token")
    return t


class Jamf(ProveedorDeUso):
    clave = "jamf"
    etiqueta = "Jamf Pro"
    credencial = "alm_jamf"
    obligatorias = ("base_url", "client_id", "client_secret")
    fiabilidad = "alta"
    permisos = ("Rol de API con el privilegio «Read Computers» (inventario de ordenadores)",)
    aporta = ("dispositivos",)
    #: Tamaño de página que admite la API de inventario de Jamf Pro.
    TAM_PAGINA = 100

    def leer(self, ctx: ContextoDeLectura) -> ResultadoDeLectura:
        res = ResultadoDeLectura()
        base = _base(ctx)
        h = {"Authorization": f"Bearer {token(ctx)}", "Accept": "application/json"}
        pagina, leidos = 0, 0
        while True:
            if pagina >= ctx.max_paginas:
                res.avisar("TRUNCATED", f"Lectura cortada tras {ctx.max_paginas} páginas")
                break
            cuerpo, _ = ctx.http.obtener_json(f"{base}/api/v1/computers-inventory", headers=h, params={
                "section": SECCIONES, "page": str(pagina), "page-size": str(self.TAM_PAGINA)})
            filas = cuerpo.get("results") or []
            for c in filas:
                g = c.get("general") or {}
                hw = c.get("hardware") or {}
                so = c.get("operatingSystem") or {}
                ul = c.get("userAndLocation") or {}
                res.dispositivos.append(Dispositivo(
                    externo_id=str(c.get("id")), nombre=g.get("name"), serie=hw.get("serialNumber") or None,
                    sistema=so.get("name") or "macOS", version_sistema=so.get("version"),
                    fabricante=hw.get("make"), modelo=hw.get("model"),
                    usuario=(ul.get("email") or "").lower() or None,
                    ultimo_contacto=a_fecha_hora(g.get("lastContactTime")), ip=g.get("lastReportedIp"),
                    apps=[AppInstalada(nombre=a.get("name"), version=a.get("version"))
                          for a in c.get("applications") or [] if a.get("name")],
                    apps_leidas=True, detalle={"gestionado": (g.get("remoteManagement") or {}).get("managed")}))
            leidos += len(filas)
            total = int(cuerpo.get("totalCount") or 0)
            pagina += 1
            if not filas or leidos >= total:
                break
        return res

    def probar(self, ctx: ContextoDeLectura) -> dict:
        base = _base(ctx)
        cuerpo, _ = ctx.http.obtener_json(f"{base}/api/v1/computers-inventory",
                                          headers={"Authorization": f"Bearer {token(ctx)}",
                                                   "Accept": "application/json"},
                                          params={"section": ["GENERAL"], "page": "0", "page-size": "1"})
        return {"ok": True, "total": cuerpo.get("totalCount")}
