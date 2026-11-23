"""Imputar fuera de horario sin autorización (18-11-2026, rev. 184).

Lo llama el alta y la edición de imputaciones (`imputation_service`). Con el
módulo desactivado (sin configuración) no hace nada y todo sigue como antes.
Con el módulo activo, según `control_imputacion` de la empresa:

- `bloquear`: si el día queda con horas fuera de horario sin una petición
  APROBADA que las cubra (más allá de la tolerancia), la imputación no se
  guarda (422 `horas_extra_sin_autorizar`). El tope semanal de capacidad se
  amplía con las horas extra aprobadas de esa semana.
- `regularizar`: la imputación se guarda y el exceso sin autorizar queda como
  declaración POSTERIOR pendiente de aprobación (una por persona y día; se
  recalcula si cambia lo imputado y se anula si el exceso desaparece). El tope
  semanal no se aplica: el control es el de horas extra, día a día.
- `avisar`: se guarda, se avisa a la persona y a su responsable y queda en el
  registro de auditoría (`OVERTIME_UNAUTHORIZED`); la lista «Sin autorizar» y
  el informe de cumplimiento lo enseñan. Sin tope semanal, como `regularizar`.
- `ninguno`: no se controla la imputación (las peticiones siguen funcionando);
  el tope semanal se amplía con lo aprobado.

Los fallos después de guardar una imputación se registran y no la deshacen.
"""
from __future__ import annotations

import logging
from datetime import date, timedelta
from typing import Optional

from sqlalchemy.orm import Session

from app.core.codigos_de_error import error as error_con_codigo
from app.models.horas_extra import PeticionDeHorasExtra
from app.services.horas_extra import calculo, config

logger = logging.getLogger(__name__)


def _cfg(db: Session) -> Optional[dict]:
    """La configuración activa o None si la empresa la desactivó.

    M22 (auditoría 22-11-2026): antes un error al leerla devolvía None, es decir
    «módulo desactivado», y una empresa con «bloquear» dejaba pasar todo
    (fail-open). Ahora el error se propaga: la imputación falla y se ve.
    """
    cfg = config.actual(db)
    return cfg if cfg["activo"] else None


def _tope_legal_anual(db: Session, user_id: str) -> float:
    """A49: tope legal de horas extra al año (`OVERTIME_LEGAL_ANNUAL_CAP_HOURS`,
    por empresa; 80 por defecto, art. 35.2 del Estatuto de los Trabajadores;
    0 = sin tope, para empresas de otros países con otra regla)."""
    from app.models.user import User
    from app.services.settings_service import get_runtime_float
    org = db.query(User.organization_id).filter(User.id == user_id).scalar()
    return float(get_runtime_float(db, "OVERTIME_LEGAL_ANNUAL_CAP_HOURS", org) or 0.0)


def horas_extra_del_anio(db: Session, user_id: str, fecha: date) -> float:
    """Horas extra aprobadas o pendientes de la persona en el año natural de `fecha`."""
    filas = db.query(PeticionDeHorasExtra).filter(
        PeticionDeHorasExtra.user_id == user_id,
        PeticionDeHorasExtra.estado.in_(("aprobada", "pendiente")),
        PeticionDeHorasExtra.fecha >= date(fecha.year, 1, 1),
        PeticionDeHorasExtra.fecha <= date(fecha.year, 12, 31)).all()
    return sum(calculo.horas_vivas(p) for p in filas)


def capacidad_semanal_extra(db: Session, user_id: str, fecha: date) -> float:
    """Horas que se suman al tope semanal de capacidad (0 = como antes; inf = sin tope)."""
    cfg = _cfg(db)
    if cfg is None:
        return 0.0
    if cfg["control_imputacion"] in ("avisar", "regularizar"):
        return float("inf")
    lunes = fecha - timedelta(days=fecha.weekday())
    filas = db.query(PeticionDeHorasExtra).filter(PeticionDeHorasExtra.user_id == user_id,
                                                  PeticionDeHorasExtra.estado == "aprobada",
                                                  PeticionDeHorasExtra.fecha >= lunes,
                                                  PeticionDeHorasExtra.fecha <= lunes + timedelta(days=6)).all()
    return sum(calculo.horas_vivas(p) for p in filas)


def comprobar(db: Session, user_id: str, fecha: date, horas_nuevas: float,
              excluir_imputacion: Optional[str] = None) -> dict:
    """Lo que pasaría al dejar el día con estas horas (sin efectos). Para Imputar y para el alta."""
    cfg = _cfg(db)
    if cfg is None:
        return {"activo": False, "control": None, "horario": None, "imputado": None, "autorizadas": None,
                "sin_autorizar": 0.0, "accion": "nada"}
    total = calculo.imputado(db, user_id, fecha, excluir_imputacion) + float(horas_nuevas or 0)
    e = calculo.estado_del_dia(db, user_id, fecha, cfg["tolerancia_minutos"], imputadas=total)
    accion = "nada"
    if e["sin_autorizar"] > 0 and cfg["control_imputacion"] != "ninguno":
        accion = cfg["control_imputacion"]
    return {"activo": True, "control": cfg["control_imputacion"], "horario": e["horario"], "imputado": e["imputado"],
            "autorizadas": e["autorizadas"], "pendientes": e["pendientes"], "sin_autorizar": e["sin_autorizar"],
            "accion": accion}


def antes_de_imputar(db: Session, user_id: str, fecha: date, horas_nuevas: float,
                     excluir_imputacion: Optional[str] = None) -> None:
    """Con `bloquear`, 422 si el día queda con horas sin autorizar."""
    c = comprobar(db, user_id, fecha, horas_nuevas, excluir_imputacion)
    if c["accion"] == "bloquear":
        raise error_con_codigo(422, "horas_extra_sin_autorizar", fecha=str(fecha), sin_autorizar=f"{c['sin_autorizar']:g}")
    # A49 (auditoría 22-11-2026): el tope LEGAL anual se aplica siempre que el
    # módulo esté activo, sea cual sea el control (avisar o regularizar dejaban
    # la capacidad semanal en infinito y nada paraba el exceso). Decisión de
    # estándar: un límite legal no es un aviso; la empresa puede cambiar la
    # cifra o ponerla a 0 si su legislación es otra.
    if c.get("activo") and (c.get("sin_autorizar") or 0) > 0:
        tope = _tope_legal_anual(db, user_id)
        if tope > 0:
            pendiente_hoy = _pendiente_posterior(db, user_id, fecha)
            ya = horas_extra_del_anio(db, user_id, fecha) - (calculo.horas_vivas(pendiente_hoy) if pendiente_hoy else 0.0)
            if ya + float(c["sin_autorizar"]) > tope + 1e-9:
                raise error_con_codigo(422, "horas_extra_tope_legal", tope=f"{tope:g}", acumuladas=f"{ya:g}")


def despues_de_imputar(db: Session, user_id: str, fecha: date, actor_id: Optional[str]) -> Optional[dict]:
    """Tras guardar (alta, edición o borrado): regularizar o avisar. Nunca deshace la imputación."""
    try:
        cfg = _cfg(db)
        if cfg is None or cfg["control_imputacion"] in ("ninguno", "bloquear"):
            if cfg is not None and cfg["control_imputacion"] == "bloquear":
                return regularizar_dia(db, user_id, fecha, actor_id, cfg, solo_anular=True)
            return None
        if cfg["control_imputacion"] == "regularizar":
            return regularizar_dia(db, user_id, fecha, actor_id, cfg)
        return _avisar_sin_autorizar(db, user_id, fecha, actor_id, cfg)
    except Exception:
        db.rollback()
        logger.exception("control de horas extra tras imputar (%s, %s)", user_id, fecha)
        return None


def _pendiente_posterior(db: Session, user_id: str, fecha: date) -> Optional[PeticionDeHorasExtra]:
    return db.query(PeticionDeHorasExtra).filter(PeticionDeHorasExtra.user_id == user_id,
                                                 PeticionDeHorasExtra.fecha == fecha,
                                                 PeticionDeHorasExtra.origen == "posterior",
                                                 PeticionDeHorasExtra.estado == "pendiente").first()


def regularizar_dia(db: Session, user_id: str, fecha: date, actor_id: Optional[str], cfg: dict,
                    solo_anular: bool = False) -> dict:
    """Una declaración posterior pendiente por persona y día con el exceso sin autorizar."""
    from app.services.horas_extra import solicitudes
    e = calculo.estado_del_dia(db, user_id, fecha, cfg["tolerancia_minutos"])
    p = _pendiente_posterior(db, user_id, fecha)
    if e["sin_autorizar"] <= 0:
        if p is not None:
            solicitudes.cancelar(db, None, p, "Lo imputado ya no supera el horario", motivo_evento="anulada")
            return {"accion": "anulada", "peticion_id": p.id}
        return {"accion": "nada"}
    if solo_anular:
        return {"accion": "nada"}
    if p is None:
        p = solicitudes.declarar(db, user_id, fecha, e["sin_autorizar"], actor_id, cfg)
        return {"accion": "creada", "peticion_id": p.id}
    if abs(p.horas - e["sin_autorizar"]) > 1e-6:
        solicitudes.recalcular_posterior(db, p, e["sin_autorizar"], actor_id, cfg)
        return {"accion": "actualizada", "peticion_id": p.id}
    return {"accion": "nada", "peticion_id": p.id}


def _avisar_sin_autorizar(db: Session, user_id: str, fecha: date, actor_id: Optional[str], cfg: dict) -> dict:
    from app.models.user import User
    from app.services.approval_engine._base import responsable_de_nivel
    from app.services.audit import audit_log
    from app.services.notifications import notify_user
    e = calculo.estado_del_dia(db, user_id, fecha, cfg["tolerancia_minutos"])
    if e["sin_autorizar"] <= 0:
        return {"accion": "nada"}
    # M27 (auditoría 22-11-2026): un aviso por persona, día y cifra. Antes cada
    # edición del día volvía a registrar y a notificar lo mismo. Además el id
    # del recurso era «usuario:fecha» (47 caracteres en una columna de 36).
    import json as _json
    from app.models.enterprise import AuditLog
    ultimo = db.query(AuditLog.new_values).filter(
        AuditLog.action == "OVERTIME_UNAUTHORIZED", AuditLog.resource == "overtime_day",
        AuditLog.resource_id == user_id, AuditLog.resource_name == str(fecha),
    ).order_by(AuditLog.created_at.desc()).first()
    if ultimo is not None:
        try:
            previo = float((_json.loads(ultimo[0] or "{}") or {}).get("sin_autorizar") or 0)
        except (TypeError, ValueError):
            previo = None
        if previo is not None and abs(previo - float(e["sin_autorizar"])) < 1e-6:
            return {"accion": "ya_avisada", **e}
    actor = db.query(User).filter(User.id == actor_id).first() if actor_id else None
    audit_log(db, actor, "OVERTIME_UNAUTHORIZED", "overtime_day", user_id, str(fecha),
              new_values={"user_id": user_id, "fecha": str(fecha), **e})
    from app.services.texto_para_usuario import texto_para
    for uid in {user_id, responsable_de_nivel(db, user_id, 1)} - {None}:
        try:
            cuerpo = texto_para(db, uid, "horas_extra.sin_autorizar.mensaje", fecha=fecha,
                                horas=f"{e['sin_autorizar']:g}")
            notify_user(db, uid, "system", texto_para(db, uid, "horas_extra.sin_autorizar.titulo"), cuerpo, resource="overtime",
                        action_url="/overtime")
        except Exception:
            logger.warning("no se pudo avisar de horas sin autorizar a %s", uid, exc_info=True)
    db.commit()
    return {"accion": "avisada", **e}


def regularizar_periodo(db: Session, usuario, desde: date, hasta: date) -> dict:
    """Pasa `regularizar_dia` por todos los días con exceso del periodo (al activar el control)."""
    from app.services.audit import audit_log
    from app.services.horas_extra import solicitudes
    cfg = solicitudes.exigir_activo(db)
    if hasta < desde or (hasta - desde).days > 400:
        raise error_con_codigo(422, "rango_de_1_a_400_dias")
    hechos = {"creadas": 0, "actualizadas": 0, "anuladas": 0}
    dias = {(r["user_id"], r["fecha"]) for r in calculo.excesos(db, desde, hasta, tolerancia_min=cfg["tolerancia_minutos"])}
    dias |= {(p.user_id, p.fecha) for p in db.query(PeticionDeHorasExtra).filter(
        PeticionDeHorasExtra.origen == "posterior", PeticionDeHorasExtra.estado == "pendiente",
        PeticionDeHorasExtra.fecha >= desde, PeticionDeHorasExtra.fecha <= hasta).all()}
    for uid, d in sorted(dias):
        r = regularizar_dia(db, uid, d, usuario.id, cfg)
        clave = {"creada": "creadas", "actualizada": "actualizadas", "anulada": "anuladas"}.get(r["accion"])
        if clave:
            hechos[clave] += 1
    audit_log(db, usuario, "REGULARIZE", "overtime_request", None, None,
              new_values={**hechos, "desde": str(desde), "hasta": str(hasta)})
    db.commit()
    return hechos
