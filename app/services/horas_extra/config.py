"""Configuración de horas extra por empresa y presupuestos de horas (18-11-2026).

Sin fila de configuración el módulo está DESACTIVADO: nadie puede pedir y la
imputación se comporta exactamente como antes (tope semanal incluido). Todo
cambio se audita (`audit_log`, recurso `overtime_config` / `overtime_budget`)
con los valores de antes y de después.
"""
from __future__ import annotations

import json
import uuid
from typing import Optional

from sqlalchemy.orm import Session

from app.core.codigos_de_error import error as error_con_codigo
from app.models.horas_extra import ConfigDeHorasExtra, PresupuestoDeHorasExtra

CONTROLES = ("ninguno", "avisar", "regularizar", "bloquear")
COMPENSACIONES = ("pago", "bolsa", "ninguna")
TIPOS = ("laborable", "fuera_de_franja", "festivo", "no_laborable", "guardia")
ESTADOS = ("pendiente", "aprobada", "rechazada", "cancelada")
ORIGENES = ("previa", "posterior")
AMBITOS = ("empresa", "departamento", "equipo", "proyecto")
PERIODOS = ("mes", "anio")

# 18-11-2026: activado por defecto (decisión del usuario): toda empresa tiene
# horas extra desde el principio, con control «avisar» al imputar (no bloquea).
DEFECTO = {"activo": True, "control_imputacion": "avisar", "tolerancia_minutos": 15,
           "compensaciones": list(COMPENSACIONES), "compensacion_por_defecto": "bolsa", "workflow_id": None,
           "tipo_bolsa_id": None, "pedir_en_nombre": True, "exigir_motivo": True}


def _org(db: Session, usuario=None) -> Optional[str]:
    return getattr(usuario, "organization_id", None) or (db.info or {}).get("organization_id")


def fila(db: Session) -> Optional[ConfigDeHorasExtra]:
    return db.query(ConfigDeHorasExtra).order_by(ConfigDeHorasExtra.created_at).first()


def actual(db: Session) -> dict:
    """La configuración en vigor (la de por defecto si no hay fila)."""
    f = fila(db)
    if f is None:
        return dict(DEFECTO)
    try:
        comp = json.loads(f.compensaciones) if f.compensaciones else list(COMPENSACIONES)
    except ValueError:
        comp = list(COMPENSACIONES)
    return {"activo": bool(f.activo), "control_imputacion": f.control_imputacion,
            "tolerancia_minutos": int(f.tolerancia_minutos or 0), "compensaciones": comp,
            "compensacion_por_defecto": f.compensacion_por_defecto, "workflow_id": f.workflow_id,
            "tipo_bolsa_id": f.tipo_bolsa_id, "pedir_en_nombre": bool(f.pedir_en_nombre),
            "exigir_motivo": bool(f.exigir_motivo)}


def para_pantalla(db: Session, usuario) -> dict:
    from app.models.billing_reports import ApprovalWorkflow
    from app.services.ausencias import bolsa
    f = fila(db)
    rol = str(getattr(usuario.role, "value", usuario.role))
    return {**actual(db), "updated_at": f.updated_at.isoformat() if f is not None and f.updated_at else None,
            "updated_by": f.updated_by if f is not None else None,
            "puede_editar": rol in ("admin", "hr") or bool(getattr(usuario, "is_superadmin", False)),
            "flujos": [{"id": w.id, "name": w.name} for w in db.query(ApprovalWorkflow).filter(
                ApprovalWorkflow.entity_type == "overtime", ApprovalWorkflow.is_active.is_(True)).all()],
            "tipos_de_bolsa": [{"id": t.id, "nombre": t.nombre} for t in bolsa.tipos_de_bolsa(db)]}


def guardar(db: Session, usuario, datos: dict) -> dict:
    """Valida y guarda (crea la fila la primera vez). Audita antes/después."""
    from app.services.audit import audit_log
    v = {**actual(db), **{k: datos[k] for k in DEFECTO if k in datos}}
    errores = []
    if v["control_imputacion"] not in CONTROLES:
        errores.append(f"control_imputacion: {v['control_imputacion']}")
    comp = [c for c in (v["compensaciones"] or []) if c]
    if not comp or any(c not in COMPENSACIONES for c in comp):
        errores.append("compensaciones")
    if v["compensacion_por_defecto"] not in comp:
        errores.append("compensacion_por_defecto")
    try:
        v["tolerancia_minutos"] = int(v["tolerancia_minutos"] or 0)
        if not 0 <= v["tolerancia_minutos"] <= 240:
            errores.append("tolerancia_minutos (0-240)")
    except (TypeError, ValueError):
        errores.append("tolerancia_minutos")
    if v["workflow_id"]:
        from app.models.billing_reports import ApprovalWorkflow
        wf = db.query(ApprovalWorkflow).filter(ApprovalWorkflow.id == v["workflow_id"]).first()
        if wf is None or wf.entity_type != "overtime":
            errores.append("workflow_id (flujo de tipo overtime)")
    if v["tipo_bolsa_id"]:
        from app.models.ausencias import TipoDeAusencia
        t = db.query(TipoDeAusencia).filter(TipoDeAusencia.id == v["tipo_bolsa_id"]).first()
        if t is None or t.saldo != "bolsa":
            errores.append("tipo_bolsa_id (tipo de ausencia con saldo de bolsa)")
    if errores:
        raise error_con_codigo(422, "horas_extra_config_no_valida", detalle=", ".join(errores))
    antes = actual(db)
    f = fila(db)
    if f is None:
        f = ConfigDeHorasExtra(id=str(uuid.uuid4()), organization_id=_org(db, usuario))
        db.add(f)
    f.activo, f.control_imputacion, f.tolerancia_minutos = bool(v["activo"]), v["control_imputacion"], \
        v["tolerancia_minutos"]
    f.compensaciones, f.compensacion_por_defecto = json.dumps(comp), v["compensacion_por_defecto"]
    f.workflow_id, f.tipo_bolsa_id = v["workflow_id"] or None, v["tipo_bolsa_id"] or None
    f.pedir_en_nombre, f.exigir_motivo = bool(v["pedir_en_nombre"]), bool(v["exigir_motivo"])
    f.updated_by = usuario.id
    db.flush()
    audit_log(db, usuario, "UPDATE", "overtime_config", f.id, "Horas extra", old_values=antes, new_values=actual(db))
    db.commit()
    return para_pantalla(db, usuario)


# ── Presupuestos ─────────────────────────────────────────────────────────────

def presupuesto_dict(p: PresupuestoDeHorasExtra, consumidas: Optional[float] = None,
                     etiqueta: Optional[str] = None) -> dict:
    return {"id": p.id, "ambito": p.ambito, "valor": p.valor, "etiqueta": etiqueta or p.valor or p.ambito,
            "periodo": p.periodo, "anio": p.anio, "horas": p.horas, "nota": p.nota, "activo": bool(p.activo),
            "consumidas": round(consumidas or 0.0, 2),
            "restantes": round(p.horas - (consumidas or 0.0), 2)}


def presupuestos(db: Session, solo_activos: bool = False) -> list[PresupuestoDeHorasExtra]:
    q = db.query(PresupuestoDeHorasExtra)
    if solo_activos:
        q = q.filter(PresupuestoDeHorasExtra.activo.is_(True))
    return q.order_by(PresupuestoDeHorasExtra.ambito, PresupuestoDeHorasExtra.valor).all()


def _validar_presupuesto(db: Session, datos: dict) -> dict:
    errores = []
    ambito, periodo = datos.get("ambito"), datos.get("periodo") or "anio"
    if ambito not in AMBITOS:
        errores.append("ambito")
    if periodo not in PERIODOS:
        errores.append("periodo")
    valor = (datos.get("valor") or None) if ambito != "empresa" else None
    if ambito in ("departamento", "equipo", "proyecto") and not valor:
        errores.append("valor")
    if ambito == "proyecto" and valor:
        from app.models.project import Project
        if db.query(Project.id).filter(Project.id == valor).first() is None:
            errores.append("proyecto")
    try:
        horas = float(datos.get("horas"))
        if horas < 0:
            errores.append("horas")
    except (TypeError, ValueError):
        horas = 0.0
        errores.append("horas")
    anio = datos.get("anio")
    if anio not in (None, ""):
        try:
            anio = int(anio)
        except (TypeError, ValueError):
            errores.append("anio")
    else:
        anio = None
    if errores:
        raise error_con_codigo(422, "horas_extra_presupuesto_no_valido", detalle=", ".join(errores))
    return {"ambito": ambito, "valor": valor, "periodo": periodo, "anio": anio, "horas": horas,
            "nota": (datos.get("nota") or None), "activo": bool(datos.get("activo", True))}


def guardar_presupuesto(db: Session, usuario, datos: dict, presupuesto_id: Optional[str] = None) -> PresupuestoDeHorasExtra:
    from app.services.audit import audit_log
    v = _validar_presupuesto(db, datos)
    antes = None
    if presupuesto_id:
        p = db.query(PresupuestoDeHorasExtra).filter(PresupuestoDeHorasExtra.id == presupuesto_id).first()
        if p is None:
            raise error_con_codigo(404, "horas_extra_presupuesto_no_encontrado")
        antes = presupuesto_dict(p)
    else:
        p = PresupuestoDeHorasExtra(id=str(uuid.uuid4()), organization_id=_org(db, usuario), created_by=usuario.id)
        db.add(p)
    for k, x in v.items():
        setattr(p, k, x)
    db.flush()
    audit_log(db, usuario, "UPDATE" if antes else "CREATE", "overtime_budget", p.id, p.valor or p.ambito,
              old_values=antes, new_values=presupuesto_dict(p))
    db.commit()
    return p


def borrar_presupuesto(db: Session, usuario, presupuesto_id: str) -> None:
    from app.services.audit import audit_log
    p = db.query(PresupuestoDeHorasExtra).filter(PresupuestoDeHorasExtra.id == presupuesto_id).first()
    if p is None:
        raise error_con_codigo(404, "horas_extra_presupuesto_no_encontrado")
    audit_log(db, usuario, "DELETE", "overtime_budget", p.id, p.valor or p.ambito, old_values=presupuesto_dict(p))
    db.delete(p)
    db.commit()
