"""Avisos configurables de riesgo (campana y correo; §11.10 del diseño).

`risk_settings.alerts`:

- ``kev_new``: hallazgo vivo con CVE explotado (KEV o con intentos) que nos
  afecta, la primera vez que se ve explotado;
- ``index_above``: índice de la empresa o de un cliente por encima del umbral
  (una vez por ámbito y día);
- ``sla_due_days``: hallazgos cuyo SLA vence en los próximos N días (un aviso
  agrupado por día).

Destinatarios: los usuarios activos de la empresa con los roles indicados y
los usuarios indicados. Campana: `notify_user` (tipo ``system``: el tipo de la
tabla es un enumerado que no se migra); correo, si ``email``, por
`notification_service.enviar_correo` respetando la preferencia del usuario.
No se repite el mismo aviso (`sw_risk_alert_log`).
"""
from __future__ import annotations

import logging
from datetime import timedelta
from typing import Optional

from sqlalchemy.orm import Session

from app.services.cmdb_software.riesgo import calculo as calc

logger = logging.getLogger(__name__)


def _ya(db, org, tipo: str, clave: str) -> bool:
    from app.models.cmdb_riesgo import RiskAlertLog
    return calc._q(db, RiskAlertLog, org).filter(RiskAlertLog.kind == tipo,
                                                 RiskAlertLog.alert_key == clave[:200]).first() is not None


def _destinatarios(db: Session, org, alertas: dict) -> list:
    from app.models.user import User
    if not org:
        return []
    q = db.query(User).filter(User.organization_id == org, User.is_active.is_(True))
    usuarios = {u.id: u for u in q.filter(User.role.in_(alertas.get("roles") or ["__ninguno__"]))}
    for u in q.filter(User.id.in_(alertas.get("user_ids") or [""])):
        usuarios[u.id] = u
    return list(usuarios.values())


def _mandar(db: Session, org, alertas: dict, tipo: str, clave: str, aviso: dict, url: str) -> bool:
    """True si es un aviso nuevo (queda en `sw_risk_alert_log` aunque no haya destinatarios)."""
    from app.models.cmdb_riesgo import RiskAlertLog
    from app.services.notifications import notify_user, texto_de_aviso
    if _ya(db, org, tipo, clave):
        return False
    usuarios = _destinatarios(db, org, alertas)
    for u in usuarios:
        titulo, cuerpo = texto_de_aviso(db, u.id, aviso, aviso["titulo"], None)
        notify_user(db, u.id, "system", titulo, cuerpo, resource="cmdb_software", resource_id=clave[:36],
                    action_url=url, aviso=aviso)
        if alertas.get("email") and u.email:
            try:
                from app.services.notification_service import enviar_correo
                from app.services.preferencias_de_aviso import quiere
                if quiere(db, u.id, "system", "email"):
                    enviar_correo(u.email, titulo, f"<p>{cuerpo or ''}</p>")
            except Exception:  # noqa: BLE001 - el correo es secundario: la campana ya está
                logger.warning("aviso de riesgo: correo no enviado", exc_info=True)
    db.add(RiskAlertLog(organization_id=org, kind=tipo, alert_key=clave[:200], recipients=len(usuarios),
                        summary=str(aviso.get("params"))[:2000]))
    db.flush()
    return True


def revisar(db: Session, org, ctx: Optional[calc.Contexto] = None) -> dict:
    """Manda los avisos que tocan. No confirma. Devuelve cuántos avisos (no destinatarios)."""
    ctx = ctx or calc.contexto(db, org)
    al = ctx.conf["alerts"]
    resumen = {"kev_new": 0, "index_above": 0, "sla_due_days": 0}
    url = "/cmdb?tab=risk"
    if al.get("kev_new"):
        for h in ctx.hallazgos:
            if h.aceptado or not (h.kev or h.intentos > 0):
                continue
            nombre = ctx.prods[h.f.product_id].name if h.f.product_id in ctx.prods else "?"
            maquinas = ", ".join(sorted(ctx.cis[c].name for c in h.cis if c in ctx.cis)) or "-"
            aviso = {"titulo": "aviso.swr_kev.titulo", "cuerpo": "aviso.swr_kev.cuerpo",
                     "params": {"cve": h.v.vuln_id if h.v else "?", "producto": nombre, "maquinas": maquinas,
                                "riesgo": round(h.r)}}
            if _mandar(db, org, al, "kev_new", f"f:{h.f.id}", aviso, url):
                resumen["kev_new"] += 1
    umbral = al.get("index_above")
    if umbral is not None:
        hoy = calc.ahora().date().isoformat()
        for tipo in ("org", "client"):
            for id_ in calc.entidades(db, org, ctx, tipo):
                r = calc.indice(calc.filtrar(ctx, tipo, id_), ctx.conf)
                if r["score"] <= umbral:
                    continue
                nombre = calc._nombre(db, org, tipo, id_) or tipo
                aviso = {"titulo": "aviso.swr_indice.titulo", "cuerpo": "aviso.swr_indice.cuerpo",
                         "params": {"ambito": nombre, "indice": round(r["score"], 1), "umbral": umbral}}
                if _mandar(db, org, al, "index_above", f"{tipo}:{id_}:{hoy}", aviso, url):
                    resumen["index_above"] += 1
    dias = al.get("sla_due_days")
    if dias is not None:
        limite = calc.ahora() + timedelta(days=int(dias))
        proximos = [h for h in ctx.hallazgos if not h.aceptado and h.f.sla_due_at is not None
                    and calc.ahora() <= calc._utc(h.f.sla_due_at) <= limite]
        if proximos:
            hoy = calc.ahora().date().isoformat()
            aviso = {"titulo": "aviso.swr_sla.titulo", "cuerpo": "aviso.swr_sla.cuerpo",
                     "params": {"n": len(proximos), "dias": int(dias)}}
            if _mandar(db, org, al, "sla_due_days", f"sla:{hoy}", aviso, url):
                resumen["sla_due_days"] += 1
    return resumen
