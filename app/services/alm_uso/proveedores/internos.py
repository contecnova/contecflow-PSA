"""Fuentes internas: el acceso a contecflow, los accesos SSO propios y el agente de inventario.

- `contecflow`: último acceso de cada persona de la empresa a contecflow (lo más
  reciente de `users.last_login` y `user_sessions.last_seen_at`) y los días
  distintos con sesión en el periodo. Producto `contecflow`: sirve para la
  licencia de la propia plataforma y como señal de actividad de la persona.
- `contecflow_sso`: quien entra por SSO (`user_sessions.auth_method = sso`)
  usa su cuenta del proveedor de identidad (`users.sso_provider`: azure_ad,
  okta, google…). Producto `sso:<proveedor>`. También aporta el proveedor de
  identidad como aplicación vista (si no está en ALM, es candidato).
- `agente_cmdb`: no se consulta; el agente de inventario on-premise ENVÍA su
  inventario en cada check-in (`inventario.procesar_checkin`). La conexión
  existe para activarlo, fijar su fiabilidad y ver su último envío.

Solo leen filas de la empresa de la conexión (filtro explícito además del de
tenant).
"""
from __future__ import annotations

from datetime import timedelta

from sqlalchemy import func

from app.services.alm_uso._comun import aware, max_fecha, ahora
from app.services.alm_uso.proveedores.base import (
    Aplicacion, ContextoDeLectura, Evidencia, ProveedorDeUso, ResultadoDeLectura,
)


def _usuarios(ctx: ContextoDeLectura):
    from app.db.session import _miembros_de
    from app.models.user import User
    return ctx.db.query(User).filter(_miembros_de(User, ctx.organization_id)).all()


def _sesiones(ctx: ContextoDeLectura, solo_sso: bool = False) -> dict:
    """{user_id: (último visto, días distintos con sesión en el periodo)} de las sesiones de la empresa."""
    from app.models.sessions import UserSession
    desde = (ctx.ahora or ahora()) - timedelta(days=ctx.periodo_dias)
    q = ctx.db.query(UserSession.user_id, UserSession.last_seen_at, UserSession.created_at).filter(
        UserSession.organization_id == ctx.organization_id)
    if solo_sso:
        q = q.filter(UserSession.auth_method == "sso")
    salida: dict = {}
    for uid, visto, creada in q.all():
        ultimo, dias = salida.get(uid, (None, set()))
        ultimo = max_fecha(ultimo, visto, creada)
        for v in (visto, creada):
            if v is not None and aware(v) >= desde:
                dias.add(aware(v).date())
        salida[uid] = (ultimo, dias)
    return salida


class AccesoContecflow(ProveedorDeUso):
    clave = "contecflow"
    etiqueta = "Accesos a contecflow"
    fiabilidad = "alta"
    tipo = "interno"
    permisos = ()
    aporta = ("evidencias",)

    def leer(self, ctx: ContextoDeLectura) -> ResultadoDeLectura:
        res = ResultadoDeLectura()
        sesiones = _sesiones(ctx)
        for u in _usuarios(ctx):
            if not u.email:
                continue
            visto, dias = sesiones.get(u.id, (None, set()))
            ultimo = max_fecha(u.last_login, visto)
            res.evidencias.append(Evidencia(
                titular_tipo="persona", titular=u.email.lower(), producto="contecflow", nombre_producto="contecflow",
                ultimo_uso=ultimo, frecuencia=len(dias), periodo_dias=ctx.periodo_dias, asignada=bool(u.is_active),
                servicios={"inicio_de_sesion": ultimo}, detalle={"cuenta_activa": bool(u.is_active)}))
        return res


class SsoContecflow(ProveedorDeUso):
    clave = "contecflow_sso"
    etiqueta = "Accesos SSO a contecflow"
    fiabilidad = "media"
    tipo = "interno"
    permisos = ()
    aporta = ("evidencias", "aplicaciones")

    def leer(self, ctx: ContextoDeLectura) -> ResultadoDeLectura:
        res = ResultadoDeLectura()
        sesiones = _sesiones(ctx, solo_sso=True)
        por_proveedor: dict = {}
        for u in _usuarios(ctx):
            if not u.sso_provider or not u.email:
                continue
            visto, dias = sesiones.get(u.id, (None, set()))
            proveedor = u.sso_provider.lower()
            res.evidencias.append(Evidencia(
                titular_tipo="persona", titular=u.email.lower(), producto=f"sso:{proveedor}",
                nombre_producto=proveedor, ultimo_uso=visto, frecuencia=len(dias), periodo_dias=ctx.periodo_dias,
                asignada=bool(u.is_active), servicios={"sso": visto}, detalle={"proveedor": proveedor}))
            p = por_proveedor.setdefault(proveedor, {"n": 0, "ultimo": None})
            p["n"] += 1
            p["ultimo"] = max_fecha(p["ultimo"], visto)
        for proveedor, d in por_proveedor.items():
            res.aplicaciones.append(Aplicacion(nombre=proveedor, usuarios=d["n"], ultimo_uso=d["ultimo"],
                                               origen="contecflow_sso"))
        return res


class AgenteInventario(ProveedorDeUso):
    clave = "agente_cmdb"
    etiqueta = "Agente de inventario (CMDB)"
    fiabilidad = "alta"
    tipo = "agente"
    permisos = ("Token del agente on-premise (CMDB → Agentes); el agente envía software instalado y nº de serie",)
    aporta = ("dispositivos",)

    def leer(self, ctx: ContextoDeLectura) -> ResultadoDeLectura:
        res = ResultadoDeLectura()
        res.avisar("PUSH_SOURCE", "El agente envía su inventario en cada check-in; no hay nada que leer")
        return res

    def probar(self, ctx: ContextoDeLectura) -> dict:
        from app.models.cmdb import CMDBAgentRegistration
        n, ultimo = ctx.db.query(func.count(CMDBAgentRegistration.id), func.max(CMDBAgentRegistration.last_checkin_at)) \
            .filter(CMDBAgentRegistration.organization_id == ctx.organization_id,
                    CMDBAgentRegistration.is_active.is_(True)).one()
        return {"ok": True, "agentes": int(n or 0), "ultimo_checkin": ultimo.isoformat() if ultimo else None}
