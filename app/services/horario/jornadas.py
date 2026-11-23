"""Jornadas laborales, a quién se aplican, ficha laboral de una persona y rejilla persona×día.

Rev. 180. Lo escribe la pantalla de Ausencias › Jornadas (administración y
RRHH); todo cambio queda en la auditoría. La rejilla (horario efectivo de cada
persona y día, con su turno o jornada, festivos y ausencias) la ve quien puede
ver a esas personas: un externo, solo a sí mismo y a quien comparte proyecto
con él; un tipo de ausencia privado se enseña como «Ausencia».
"""
from __future__ import annotations

import json
import uuid
from datetime import date
from typing import Optional

from sqlalchemy.orm import Session

from app.core.errores import ErrorDeDominio
from app.core.codigos_de_error import error as error_con_codigo
from app.models.horario import AsignacionDeJornada, JornadaLaboral
from app.services.horario import tramos as tr
from app.services.horario.efectivo import AMBITOS

IDIOMAS = ("es", "en", "zh")
MAX_DIAS_REJILLA = 93


def _org(db: Session, usuario=None) -> Optional[str]:
    return getattr(usuario, "organization_id", None) or (db.info or {}).get("organization_id")


def _json(v, defecto):
    try:
        return json.loads(v) if v else defecto
    except (TypeError, ValueError):
        return defecto


def _fecha(v, nombre: str) -> Optional[date]:
    if v in (None, ""):
        return None
    if isinstance(v, date):
        return v
    try:
        return date.fromisoformat(str(v)[:10])
    except ValueError:
        raise error_con_codigo(422, "fecha_no_valida_en", nombre=nombre)


def _auditar(db: Session, usuario, accion: str, recurso: str, rid: str, nombre: Optional[str] = None, **valores):
    from app.services.audit import audit_log
    audit_log(db, usuario, accion, recurso, rid, nombre, new_values=valores or None)


# ── Jornadas ─────────────────────────────────────────────────────────────────

def horas_de_semana(semana: dict, pausa: int) -> dict:
    salida = {}
    for d in range(1, 8):
        try:
            t = tr.de_lista(semana.get(str(d)) or [])
        except ValueError:
            t = ()
        salida[str(d)] = round(max(0.0, tr.total_horas(t) - (pausa / 60 if t else 0)), 2)
    return salida


def jornada_dict(j: JornadaLaboral) -> dict:
    semana = _json(j.semana, {}) or {}
    horas = horas_de_semana(semana, int(j.pausa_minutos or 0))
    return {"id": j.id, "nombre": j.nombre, "nombres": _json(j.nombres, {}), "color": j.color,
            "semana": {str(d): semana.get(str(d)) or [] for d in range(1, 8)}, "pausa_minutos": int(j.pausa_minutos or 0),
            "horas_por_dia": horas, "horas_semana": round(sum(horas.values()), 2), "activo": bool(j.activo),
            "orden": j.orden, "asignaciones": [asignacion_dict(a) for a in j.asignaciones or []]}


def jornadas(db: Session, *, incluir_inactivas: bool = False) -> list[JornadaLaboral]:
    q = db.query(JornadaLaboral)
    if not incluir_inactivas:
        q = q.filter(JornadaLaboral.activo.is_(True))
    return q.order_by(JornadaLaboral.orden, JornadaLaboral.nombre).all()


def jornada(db: Session, jornada_id: str) -> JornadaLaboral:
    j = db.query(JornadaLaboral).filter(JornadaLaboral.id == jornada_id).first()
    if j is None:
        raise error_con_codigo(404, "jornada_no_encontrada")
    return j


def guardar_jornada(db: Session, usuario, datos: dict, jornada_id: Optional[str] = None) -> dict:
    j = jornada(db, jornada_id) if jornada_id else JornadaLaboral(id=str(uuid.uuid4()), organization_id=_org(db, usuario))
    nombres = {k: str(v).strip()[:120] for k, v in (datos.get("nombres") or {}).items() if k in IDIOMAS and str(v or "").strip()}
    nombre = (datos.get("nombre") or "").strip() or nombres.get("es") or next(iter(nombres.values()), "")
    if not nombre:
        raise error_con_codigo(422, "jornada_sin_nombre")
    from app.services.texto_para_usuario import texto_para
    _t = lambda clave, **p: texto_para(db, getattr(usuario, "id", None), clave, org_id=_org(db, usuario), **p)  # noqa: E731
    errores = []
    semana = {}
    for d in range(1, 8):
        lista = [x for x in ((datos.get("semana") or {}).get(str(d)) or []) if x and (x[0] or x[1])]
        try:
            t = tr.de_lista(lista)
        except (ValueError, TypeError, IndexError) as exc:
            errores.append(_t("jornada.error_dia", dia=d, detalle=exc))
            continue
        if t and t[-1].fin - t[0].inicio > tr.DIA:
            errores.append(_t("jornada.error_tramos_24h", dia=d))
        semana[str(d)] = tr.a_lista(t)
    # Baja (auditoría 22-11-2026): la pausa se valida (antes `int()` daba 500
    # con texto y no tenía tope): entero entre 0 y la jornada más larga.
    mas_larga = max((sum(t.minutos for t in tr.de_lista(v)) for v in semana.values() if v), default=tr.DIA)
    try:
        pausa = int(datos.get("pausa_minutos") or 0)
    except (TypeError, ValueError):
        pausa = -1
    if pausa < 0:
        errores.append(_t("jornada.error_pausa_negativa") if str(datos.get("pausa_minutos") or "0").lstrip("-").isdigit()
                       else _t("jornada.error_pausa_no_valida", maximo=mas_larga))
        pausa = 0
    elif pausa > mas_larga:
        errores.append(_t("jornada.error_pausa_no_valida", maximo=mas_larga))
    if not any(semana.values()):
        errores.append(_t("jornada.error_sin_horario"))
    if errores:
        raise ErrorDeDominio(422, {"message": _t("jornada.errores"), "errors": errores})
    j.nombre, j.nombres = nombre[:120], json.dumps(nombres, ensure_ascii=False) if nombres else None
    j.color = datos.get("color") or j.color or "#4f8cff"
    j.semana, j.pausa_minutos = json.dumps(semana), pausa
    j.activo = bool(datos.get("activo", True))
    j.orden = int(datos.get("orden") if datos.get("orden") is not None else (j.orden or 100))
    if jornada_id is None:
        db.add(j)
    _auditar(db, usuario, "UPDATE" if jornada_id else "CREATE", "work_schedule", j.id, j.nombre, semana=semana,
             pausa_minutos=pausa)
    db.commit()
    return jornada_dict(j)


def borrar_jornada(db: Session, usuario, jornada_id: str) -> dict:
    """Con asignaciones, se desactiva (deja de aplicar); sin ellas, se borra."""
    j = jornada(db, jornada_id)
    if j.asignaciones:
        j.activo = False
        salida = {"desactivado": True}
    else:
        db.delete(j)
        salida = {"eliminado": True}
    _auditar(db, usuario, "DELETE", "work_schedule", jornada_id, j.nombre, **salida)
    db.commit()
    return salida


# ── Asignaciones ─────────────────────────────────────────────────────────────

def asignacion_dict(a: AsignacionDeJornada) -> dict:
    return {"id": a.id, "jornada_id": a.jornada_id, "ambito": a.ambito, "valor": a.valor,
            "desde": a.desde.isoformat() if a.desde else None, "hasta": a.hasta.isoformat() if a.hasta else None,
            "recurrente_anual": bool(a.recurrente_anual), "prioridad": a.prioridad or 0, "nota": a.nota}


def guardar_asignacion(db: Session, usuario, datos: dict, asignacion_id: Optional[str] = None) -> dict:
    from app.models.advanced_config import Office
    from app.models.billing_reports import ApprovalGroup
    from app.models.user import User
    a = db.query(AsignacionDeJornada).filter(AsignacionDeJornada.id == asignacion_id).first() if asignacion_id else None
    if asignacion_id and a is None:
        raise error_con_codigo(404, "asignacion_no_encontrada")
    j = jornada(db, datos.get("jornada_id") or (a.jornada_id if a else ""))
    ambito = datos.get("ambito") or "empresa"
    if ambito not in AMBITOS:
        raise error_con_codigo(422, "ambito_desconocido", ambito=str(ambito))
    valor = (datos.get("valor") or "").strip() or None
    if ambito != "empresa" and not valor:
        raise error_con_codigo(422, "asignacion_sin_destino")
    existe = {"sede": lambda v: db.query(Office.id).filter(Office.id == v).first(),
              "persona": lambda v: db.query(User.id).filter(User.id == v).first(),
              "grupo": lambda v: db.query(ApprovalGroup.id).filter(ApprovalGroup.id == v).first()}.get(ambito)
    if existe is not None and existe(valor) is None:
        raise error_con_codigo(422, "destino_no_existe_en_empresa")
    desde, hasta = _fecha(datos.get("desde"), "desde"), _fecha(datos.get("hasta"), "hasta")
    recurrente = bool(datos.get("recurrente_anual"))
    if recurrente and not (desde and hasta):
        raise error_con_codigo(422, "jornada_anual_sin_fechas")
    if desde and hasta and hasta < desde and not recurrente:
        raise error_con_codigo(422, "fecha_final_anterior")
    if a is None:
        a = AsignacionDeJornada(id=str(uuid.uuid4()), organization_id=_org(db, usuario), created_by=usuario.id)
        db.add(a)
    a.jornada_id, a.ambito, a.valor = j.id, ambito, (None if ambito == "empresa" else valor)
    a.desde, a.hasta, a.recurrente_anual = desde, hasta, recurrente
    a.prioridad = int(datos.get("prioridad") or 0)
    a.nota = (datos.get("nota") or None) and str(datos["nota"])[:255]
    _auditar(db, usuario, "UPDATE" if asignacion_id else "CREATE", "work_schedule_assignment", a.id, j.nombre,
             **{k: (v.isoformat() if isinstance(v, date) else v) for k, v in asignacion_dict(a).items()})
    db.commit()
    return asignacion_dict(a)


def borrar_asignacion(db: Session, usuario, asignacion_id: str) -> None:
    a = db.query(AsignacionDeJornada).filter(AsignacionDeJornada.id == asignacion_id).first()
    if a is None:
        raise error_con_codigo(404, "asignacion_no_encontrada")
    _auditar(db, usuario, "DELETE", "work_schedule_assignment", a.id, None)
    db.delete(a)
    db.commit()


# ── Ficha laboral ────────────────────────────────────────────────────────────

def ficha_dict(u) -> dict:
    return {"user_id": u.id, "nombre": u.full_name, "office_id": u.office_id,
            "hire_date": u.hire_date.isoformat() if u.hire_date else None, "employment_type": u.employment_type,
            "weekly_capacity_hours": u.weekly_capacity_hours, "equipo": u.team, "departamento": u.department}


def fichas(db: Session) -> list[dict]:
    from app.models.user import User
    return [ficha_dict(u) for u in db.query(User).filter(User.is_active.is_(True)).order_by(User.full_name).all()]


def guardar_ficha(db: Session, usuario, user_id: str, datos: dict) -> dict:
    from app.models.advanced_config import Office
    from app.models.user import User
    u = db.query(User).filter(User.id == user_id).first()
    if u is None:
        raise error_con_codigo(404, "persona_no_encontrada")
    antes = ficha_dict(u)
    if "office_id" in datos:
        oid = datos.get("office_id") or None
        if oid and db.query(Office.id).filter(Office.id == oid).first() is None:
            raise error_con_codigo(422, "sede_no_existe")
        u.office_id = oid
    if "hire_date" in datos:
        u.hire_date = _fecha(datos.get("hire_date"), "fecha de alta")
    if "employment_type" in datos:
        u.employment_type = (str(datos.get("employment_type") or "").strip() or None) and str(datos["employment_type"]).strip()[:40]
    from app.services.audit import audit_log
    audit_log(db, usuario, "UPDATE", "user_work_profile", u.id, u.full_name, old_values=antes, new_values=ficha_dict(u))
    db.commit()
    return ficha_dict(u)


# ── Rejilla persona × día ────────────────────────────────────────────────────

def personas_que_ve(db: Session, viewer: User, user_ids: Optional[list[str]]) -> Optional[list[str]]:
    """Un empleado (ni responsable ni RRHH) ve su equipo (o a sí mismo); el resto, lo que diga la visibilidad."""
    rol = str(getattr(viewer.role, "value", viewer.role))
    if rol in ("admin", "hr", "pm", "team_lead", "subcontractor") or getattr(viewer, "is_superadmin", False):
        return user_ids
    from app.models.user import User
    q = db.query(User.id).filter(User.is_active.is_(True))
    q = q.filter(User.team == viewer.team) if viewer.team else q.filter(User.id == viewer.id)
    propios = {u for (u,) in q.all()}
    return [u for u in (user_ids or propios) if u in propios] or [viewer.id]


def rejilla(db: Session, viewer, desde: date, hasta: date, *, equipo: Optional[str] = None,
            departamento: Optional[str] = None, user_ids: Optional[list[str]] = None,
            con_pendientes: bool = True) -> dict:
    """El horario efectivo de cada persona y día, para la rejilla común.

    Cada celda: origen (turno / jornada / empresa), turno o jornada con su
    nombre y color, tramos, horas teóricas y disponibles, festivo, fuera de
    contrato y ausencias (aprobadas y, si se pide, pendientes) con sus horas.
    """
    from app.models.resources import Absence
    from app.models.user import User
    from app.services.absence_service import puede_ver_tipo
    from app.services.ausencias import turnos as turnos_srv
    from app.services.horario import efectivo as hor
    from app.services.politica_de_visibilidad import ids_de_personas_visibles
    if hasta < desde:
        raise error_con_codigo(422, "fecha_final_anterior")
    if (hasta - desde).days + 1 > MAX_DIAS_REJILLA:
        raise error_con_codigo(422, "maximo_de_dias", max=MAX_DIAS_REJILLA)
    q = db.query(User).filter(User.is_active.is_(True))
    if equipo:
        q = q.filter(User.team == equipo)
    if departamento:
        q = q.filter(User.department == departamento)
    if user_ids:
        q = q.filter(User.id.in_(user_ids))
    visibles = ids_de_personas_visibles(db, viewer)
    if visibles is not None:
        q = q.filter(User.id.in_(visibles))
    personas = q.order_by(User.full_name).all()
    estados = ("approved", "pending", "waitlisted") if con_pendientes else ("approved",)
    plan = hor.horarios(db, [u.id for u in personas], desde, hasta, estados_ausencia=estados)
    turnos = {t.id: t for t in turnos_srv.turnos(db, incluir_inactivos=True)}
    js = {j.id: j for j in jornadas(db, incluir_inactivas=True)}
    ausencias = {a.id: a for a in db.query(Absence).filter(
        Absence.user_id.in_([u.id for u in personas]), Absence.start_date <= hasta, Absence.end_date >= desde).all()} \
        if personas else {}
    filas = []
    for u in personas:
        celdas = {}
        for d, x in sorted((plan.get(u.id) or {}).items()):
            c = x.a_dict()
            c["horas"] = round(x.horas_sin(), 2)
            t = turnos.get(x.turno_id) if x.turno_id else None
            j = js.get(x.jornada_id) if x.jornada_id else None
            c["etiqueta"] = t.nombre if t else (j.nombre if j else None)
            c["color"] = t.color if t else (j.color if j else None)
            for aus in c["ausencias"]:
                a = ausencias.get(aus["id"])
                visible = a is not None and puede_ver_tipo(db, viewer, a)
                tipo = getattr(a, "absence_type", None) if visible else None
                aus["tipo"] = aus["tipo"] if visible else "private"
                aus["tipo_id"] = aus["tipo_id"] if visible else None
                aus["nombre"] = tipo.nombre if tipo is not None else None
                aus["color"] = tipo.color if tipo is not None else None
            celdas[d.isoformat()] = c
        filas.append({"id": u.id, "nombre": u.full_name, "equipo": u.team, "departamento": u.department,
                      "sede": u.office_id, "celdas": celdas,
                      "horas_teoricas": round(sum(x.horas_teoricas for x in (plan.get(u.id) or {}).values()), 2),
                      "horas": round(sum(x.horas_sin() for x in (plan.get(u.id) or {}).values()), 2)})
    return {"desde": desde.isoformat(), "hasta": hasta.isoformat(), "personas": filas,
            "turnos": [turnos_srv.turno_dict(t) for t in turnos.values() if t.activo],
            "jornadas": [{"id": j.id, "nombre": j.nombre, "color": j.color} for j in js.values()]}
