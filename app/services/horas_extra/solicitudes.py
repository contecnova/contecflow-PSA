"""El ciclo de vida de una petición de horas extra (18-11-2026, rev. 184).

    pedir (previa) ─┬─ datos incoherentes con su horario ──────────────▶ 422 (no se guarda)
                    ├─ bloqueo de una política ─────────────────────────▶ 422 (no se guarda)
                    ├─ requisitos sin cumplir (motivo…) ────────────────▶ 422
                    └─ pendiente ─▶ flujo `overtime` (o su responsable) ─▶ aprobada | rechazada
    imputar de más (posterior, `control.py`, modo «regularizar»)
                    └─ pendiente ─▶ el mismo flujo; un bloqueo de política NO impide registrar lo
                                    trabajado: queda como incidencia (`incumple`) y avisa
    pendiente ─▶ editar (se vuelve a evaluar y a pedir) | cancelar
    aprobada  ─▶ compensación: bolsa (`ausencias/bolsa.py`) o pago (liquidar con referencia)

- Las reglas son las políticas publicadas del dominio `horas_extra`; cada
  evaluación se guarda con su explicación (momento solicitud, declaracion,
  edicion, recalculo).
- La aprobación es SIEMPRE el motor de aprobaciones (`entity_type = overtime`):
  el flujo de la configuración (o el que elijan sus condiciones), más los
  niveles y pasos que añadan las políticas. Sin flujo ni pasos de política,
  decide su responsable directo (o RRHH/administración), registrado aquí.
- Segregación: nadie decide sobre sus propias horas extra ni sobre las que
  pidió para otra persona (403 y la infracción SoD queda registrada).
- Todo cambio deja un evento (`eventos_de_horas_extra`) y un `audit_log`.
"""
from __future__ import annotations

import json
import logging
import uuid
from datetime import date, datetime, time, timezone
from typing import Optional

from sqlalchemy.orm import Session

from app.core import timeutil
from app.core.codigos_de_error import error as error_con_codigo
from app.models.horas_extra import EventoDeHorasExtra, PeticionDeHorasExtra
from app.services.horas_extra import calculo, config, reglas

logger = logging.getLogger(__name__)
DOMINIO = "horas_extra"
TIPO_DE_APROBACION = "overtime"


def _rol(u) -> str:
    return str(getattr(getattr(u, "role", None), "value", getattr(u, "role", None)) or "")


def _ahora() -> datetime:
    return datetime.now(timezone.utc)


def es_gestion(u) -> bool:
    return bool(getattr(u, "is_superadmin", False)) or _rol(u) in ("admin", "hr")


def es_responsable_de(db: Session, usuario, user_id: str, niveles: int = 10) -> bool:
    from app.services.approval_engine._base import responsable_de_nivel
    return any(responsable_de_nivel(db, user_id, n) == usuario.id for n in range(1, niveles + 1))


def evento(db: Session, p: PeticionDeHorasExtra, tipo: str, actor_id: Optional[str] = None, **datos) -> None:
    db.add(EventoDeHorasExtra(id=str(uuid.uuid4()), organization_id=p.organization_id, peticion_id=p.id, tipo=tipo,
                              actor_id=actor_id, created_at=_ahora(),   # con microsegundos: orden estable
                              datos=json.dumps(datos, ensure_ascii=False, default=str) if datos else None))


def _auditar(db: Session, actor, accion: str, p: PeticionDeHorasExtra, antes: Optional[dict] = None, **extra) -> None:
    from app.services.audit import audit_log
    audit_log(db, actor, accion, "overtime_request", p.id, resumen(p), old_values=antes,
              new_values={"estado": p.estado, "horas": p.horas, "horas_autorizadas": p.horas_autorizadas,
                          "compensacion": p.compensacion, "factor": p.factor, "user_id": p.user_id, **extra})


def avisar(db: Session, user_ids, titulo: str, cuerpo: str, p: PeticionDeHorasExtra) -> None:
    from app.services.notifications import notify_user
    for uid in sorted({u for u in user_ids if u}):
        try:
            notify_user(db, uid, "system", titulo[:255], cuerpo[:1000], resource="overtime", resource_id=p.id,
                        action_url="/overtime")
        except Exception:
            logger.warning("no se pudo avisar de las horas extra %s a %s", p.id, uid, exc_info=True)


def resumen(p: PeticionDeHorasExtra) -> str:
    franja = f" {p.hora_inicio:%H:%M}–{p.hora_fin:%H:%M}" if p.hora_inicio and p.hora_fin else ""
    return f"Horas extra {p.fecha}{franja} · {float(p.horas or 0):g} h"


def instantanea(p: PeticionDeHorasExtra) -> dict:
    return {"estado": p.estado, "fecha": str(p.fecha), "tipo": p.tipo, "horas": p.horas,
            "horas_autorizadas": p.horas_autorizadas, "compensacion": p.compensacion, "factor": p.factor,
            "hora_inicio": p.hora_inicio.strftime("%H:%M") if p.hora_inicio else None,
            "hora_fin": p.hora_fin.strftime("%H:%M") if p.hora_fin else None, "motivo": p.motivo,
            "project_id": p.project_id}


# ── Construir y validar ──────────────────────────────────────────────────────

def exigir_activo(db: Session) -> dict:
    cfg = config.actual(db)
    if not cfg["activo"]:
        raise error_con_codigo(409, "horas_extra_desactivadas")
    return cfg


def _fecha(v) -> date:
    if isinstance(v, date):
        return v
    try:
        return date.fromisoformat(str(v)[:10])
    except (TypeError, ValueError):
        raise error_con_codigo(422, "fecha_no_valida_en", nombre="fecha")


def _hora(v, nombre: str) -> Optional[time]:
    if v in (None, ""):
        return None
    if isinstance(v, time):
        return v
    try:
        h, m = str(v).split(":")[:2]
        return time(int(h), int(m))
    except (TypeError, ValueError):
        raise error_con_codigo(422, "hora_no_valida_en", nombre=nombre)


def puede_pedir_para(db: Session, usuario, user_id: str, cfg: dict) -> bool:
    if user_id == usuario.id:
        return True
    if not cfg.get("pedir_en_nombre"):
        return False
    return es_gestion(usuario) or es_responsable_de(db, usuario, user_id)


def construir(db: Session, usuario, datos: dict, cfg: dict, p: Optional[PeticionDeHorasExtra] = None
              ) -> PeticionDeHorasExtra:
    """Una petición (nueva SIN guardar, o la existente con los cambios) desde los datos de la pantalla."""
    from app.models.user import User
    user_id = (p.user_id if p is not None else None) or datos.get("user_id") or usuario.id
    if p is None:
        if not puede_pedir_para(db, usuario, user_id, cfg):
            raise error_con_codigo(403, "horas_extra_no_puedes_pedir_para_otro")
        persona = db.query(User).filter(User.id == user_id, User.is_active.is_(True)).first()
        if persona is None:
            raise error_con_codigo(404, "persona_no_existe_en_empresa")
        p = PeticionDeHorasExtra(id=None, user_id=user_id, solicitante_id=usuario.id,
                                 organization_id=getattr(persona, "organization_id", None), origen="previa",
                                 estado="pendiente", factor=1.0)
    tipo = datos.get("tipo") or "laborable"
    if tipo not in config.TIPOS:
        raise error_con_codigo(422, "horas_extra_tipo_no_valido", tipo=tipo)
    fecha = _fecha(datos.get("fecha"))
    h_ini, h_fin = _hora(datos.get("hora_inicio"), "hora de inicio"), _hora(datos.get("hora_fin"), "hora de fin")
    if (h_ini is None) != (h_fin is None):
        raise error_con_codigo(422, "indica_hora_inicio_y_fin")
    if h_ini is not None and h_ini == h_fin:
        raise error_con_codigo(422, "franja_misma_hora")
    horas = datos.get("horas")
    franja_h = None
    if h_ini is not None:
        from app.services.horario import tramos as tr
        franja_h = round(tr.desde_texto(h_ini, h_fin).horas, 4)
    if horas in (None, ""):
        if franja_h is None:
            raise error_con_codigo(422, "horas_extra_sin_franja_ni_horas")
        horas = franja_h
    try:
        horas = round(float(horas), 4)
    except (TypeError, ValueError):
        raise error_con_codigo(422, "horas_extra_horas_no_validas")
    if not 0 < horas <= 24:
        raise error_con_codigo(422, "horas_extra_horas_no_validas")
    if franja_h is not None and horas > franja_h + 1e-6:
        raise error_con_codigo(422, "horas_extra_horas_mayor_que_franja", horas=f"{horas:g}", franja=f"{franja_h:g}")
    compensacion = datos.get("compensacion") or p.compensacion or cfg["compensacion_por_defecto"]
    if compensacion not in cfg["compensaciones"]:
        raise error_con_codigo(422, "horas_extra_compensacion_no_permitida", compensacion=compensacion)
    proyecto = datos.get("project_id") or None
    if proyecto:
        from app.models.project import Project
        if db.query(Project.id).filter(Project.id == proyecto).first() is None:
            raise error_con_codigo(404, "proyecto_no_encontrado")
    sustituto = datos.get("sustituto_id") or None
    if sustituto:
        if sustituto == user_id:
            raise error_con_codigo(422, "horas_extra_no_puedes_pedir_para_otro")
        if db.query(User.id).filter(User.id == sustituto, User.is_active.is_(True)).first() is None:
            raise error_con_codigo(404, "persona_no_existe_en_empresa")
    p.tipo, p.fecha, p.hora_inicio, p.hora_fin, p.horas = tipo, fecha, h_ini, h_fin, horas
    p.motivo = (datos.get("motivo") or "").strip() or None
    p.project_id, p.ticket_id, p.sustituto_id = proyecto, (datos.get("ticket_id") or None), sustituto
    p.compensacion = compensacion
    p.factor = 1.0
    return p


def coherencia(db: Session, p: PeticionDeHorasExtra) -> dict:
    """Registro de jornada coherente: el tipo cuadra con el día y la franja no cae en su horario."""
    m = reglas.medir_cache(db, p)
    p.clase_dia = m["clase"]
    esperado = {"festivo": ("festivo",), "no_laborable": ("no_laborable",),
                "laborable": ("laborable",), "fuera_de_franja": ("laborable",)}.get(p.tipo)
    if esperado and m["clase"] not in esperado:
        raise error_con_codigo(422, "horas_extra_tipo_no_coincide", tipo=p.tipo, fecha=str(p.fecha), clase=m["clase"])
    if p.origen == "previa" and m["franja_horas"] is not None and m["horas_dentro"] > 1e-6:
        raise error_con_codigo(422, "horas_extra_franja_dentro_de_horario", horas=f"{m['horas_dentro']:g}")
    return m


def solapada(db: Session, p: PeticionDeHorasExtra) -> None:
    from app.services.horario import tramos as tr
    f = calculo.franja_de(p)
    if f is None:
        return
    q = db.query(PeticionDeHorasExtra).filter(PeticionDeHorasExtra.user_id == p.user_id,
                                              PeticionDeHorasExtra.fecha == p.fecha,
                                              PeticionDeHorasExtra.estado.in_(calculo.VIVOS))
    if p.id:
        q = q.filter(PeticionDeHorasExtra.id != p.id)
    for otra in q.all():
        g = calculo.franja_de(otra)
        if g is not None and tr.interseccion([f], [g]):
            raise error_con_codigo(422, "horas_extra_solapada", fecha=str(p.fecha))


def evaluar(db: Session, p: PeticionDeHorasExtra) -> dict:
    from app.services import politicas
    return politicas.evaluar(db, DOMINIO, p, organization_id=p.organization_id)


def _mensajes(ev: dict) -> dict:
    r = ev.get("resultado") or {}
    return {"avisos": [a.get("mensaje") for a in r.get("avisos") or [] if a.get("mensaje")],
            "bloqueos": [b.get("mensaje") for b in r.get("bloqueos") or [] if b.get("mensaje")]}


def _aplicar_y_exigir(db: Session, p: PeticionDeHorasExtra, ev: dict, cfg: dict, estricto: bool = True) -> list:
    """`set_field` de las políticas (compensación, factor) y requisitos. Devuelve los pendientes."""
    from app.services import politicas
    politicas.aplicar_campos(db, DOMINIO, p, ev["resultado"])
    pendientes = [r.get("mensaje") or r.get("tipo") for r in
                  politicas.requisitos_pendientes(db, DOMINIO, p, ev["resultado"])]
    if cfg.get("exigir_motivo") and not p.motivo and p.origen == "previa":
        pendientes.insert(0, "motivo")
    if estricto:
        if pendientes == ["motivo"]:
            raise error_con_codigo(422, "horas_extra_motivo_obligatorio")
        if pendientes:
            raise error_con_codigo(422, "horas_extra_requisitos", requisitos="; ".join(pendientes))
    return pendientes


def _bloquear_si_politica(ev: dict) -> None:
    if ev["decision"] == "block":
        bloqueos = (ev.get("resultado") or {}).get("bloqueos") or []
        mensaje = "; ".join(b.get("mensaje") or "" for b in bloqueos) or "Lo impide una política"
        raise error_con_codigo(422, "horas_extra_bloqueada", mensaje=mensaje)


# ── Vista previa ─────────────────────────────────────────────────────────────

def _aprobaciones_previstas(db: Session, p: PeticionDeHorasExtra, ev: dict, cfg: dict) -> list[dict]:
    from app.models.billing_reports import ApprovalWorkflow
    from app.services.approval_engine._base import elegir_flujo
    wf = None
    if cfg.get("workflow_id"):
        wf = db.query(ApprovalWorkflow).filter(ApprovalWorkflow.id == cfg["workflow_id"],
                                               ApprovalWorkflow.is_active.is_(True)).first()
    if wf is None:
        wf = elegir_flujo(db, TIPO_DE_APROBACION, {"type": p.tipo, "amount": p.horas})
    salida = []
    if wf is not None:
        for s in sorted(wf.steps or [], key=lambda s: (s.step_order, str(s.id))):
            salida.append({"orden": s.step_order, "nombre": s.name, "tipo": getattr(s, "kind", None) or "approve",
                           "aprobador": s.approver_type, "rol": s.approver_role, "origen": "flujo"})
    r = ev.get("resultado") or {}
    for i in range(int(r.get("niveles") or 0)):
        salida.append({"orden": None, "nombre": f"+{i + 1}", "tipo": "approve", "aprobador": "manager_level",
                       "rol": None, "origen": "politica"})
    for x in r.get("pasos") or []:
        salida.append({"orden": None, "nombre": x.get("nombre"), "tipo": "approve",
                       "aprobador": x.get("approver_type"), "rol": x.get("approver_role"), "origen": "politica"})
    if not salida and ev["decision"] not in ("auto_approve",):
        salida.append({"orden": 1, "nombre": "Responsable", "tipo": "approve", "aprobador": "manager", "rol": None,
                       "origen": "responsable"})
    return salida


def vista_previa(db: Session, usuario, datos: dict) -> dict:
    """Lo que pasaría si se pidiera ahora. No guarda nada."""
    cfg = exigir_activo(db)
    actual = None
    if datos.get("id"):
        actual = db.query(PeticionDeHorasExtra).filter(PeticionDeHorasExtra.id == datos["id"]).first()
    p = construir(db, usuario, datos, cfg)
    if actual is not None:
        p.id = actual.id
    p.created_at = _ahora()
    errores = []
    try:
        coherencia(db, p)
        solapada(db, p)
    except Exception as e:  # noqa: BLE001 — se enseñan, no se lanzan
        errores.append(getattr(e, "detail", None) or str(e))
    if p.clase_dia is None:
        p.clase_dia = reglas.medir_cache(db, p)["clase"]
    ev = evaluar(db, p)
    pendientes = _aplicar_y_exigir(db, p, ev, cfg, estricto=False)
    ctx = ev["contexto"]
    extra = ctx.get("_peticion") or {}
    msj = _mensajes(ev)
    return {"decision": ev["decision"], "horas": p.horas, "clase_dia": p.clase_dia,
            "horario": extra.get("horario"), "horas_fuera_de_horario": ctx.get("horas_fuera_de_horario"),
            "acumulados": extra.get("acumulados"), "presupuesto_restante": ctx.get("presupuesto_restante"),
            "presupuestos": extra.get("presupuestos"), "descanso_horas": ctx.get("descanso_horas"),
            "dias_seguidos": ctx.get("dias_seguidos"), "antelacion_horas": ctx.get("antelacion_horas"),
            "compensacion": p.compensacion, "factor": p.factor, "horas_ponderadas": calculo.horas_ponderadas(p),
            "aprobaciones": _aprobaciones_previstas(db, p, ev, cfg), "avisos": msj["avisos"],
            "bloqueos": msj["bloqueos"], "requisitos": pendientes, "errores": errores,
            "explicacion": ev["explicacion"]}


# ── Pedir y declarar ─────────────────────────────────────────────────────────

def solicitar(db: Session, usuario, datos: dict) -> PeticionDeHorasExtra:
    from app.services import politicas
    cfg = exigir_activo(db)
    p = construir(db, usuario, datos, cfg)
    p.id = str(uuid.uuid4())
    p.created_at = _ahora()
    coherencia(db, p)
    solapada(db, p)
    ev = evaluar(db, p)
    _bloquear_si_politica(ev)
    _aplicar_y_exigir(db, p, ev, cfg)
    p.avisos = json.dumps(_mensajes(ev), ensure_ascii=False)
    db.add(p)
    db.flush()
    evento(db, p, "creada", usuario.id, horas=p.horas, tipo_horas=p.tipo, clase=p.clase_dia, compensacion=p.compensacion,
           factor=p.factor, para=p.user_id if p.user_id != usuario.id else None)
    politicas.registrar_evaluacion(db, DOMINIO, p.id, ev, momento="solicitud", usuario_id=usuario.id,
                                   organization_id=p.organization_id)
    _auditar(db, usuario, "CREATE", p)
    db.commit()
    abrir_flujo(db, p, ev, cfg)
    return p


def declarar(db: Session, user_id: str, fecha: date, horas: float, actor_id: Optional[str], cfg: dict
             ) -> PeticionDeHorasExtra:
    """Declaración POSTERIOR: el exceso imputado sin autorizar, pendiente de regularizar.

    Lo que se trabajó no se puede «bloquear»: un bloqueo de política se guarda
    como incidencia (`incumple`), se avisa al responsable y sigue el flujo.
    """
    from app.models.user import User
    from app.services import politicas
    u = db.query(User).filter(User.id == user_id).first()
    p = PeticionDeHorasExtra(id=str(uuid.uuid4()), user_id=user_id, solicitante_id=None,
                             organization_id=getattr(u, "organization_id", None), origen="posterior",
                             estado="pendiente", factor=1.0, fecha=fecha, horas=round(horas, 4),
                             compensacion=cfg["compensacion_por_defecto"], created_at=_ahora())
    p.clase_dia = reglas.medir_cache(db, p)["clase"]
    p.tipo = p.clase_dia if p.clase_dia in ("festivo", "no_laborable") else "laborable"
    ev = evaluar(db, p)
    _aplicar_y_exigir(db, p, ev, cfg, estricto=False)
    p.avisos = json.dumps(_mensajes(ev), ensure_ascii=False)
    db.add(p)
    db.flush()
    evento(db, p, "declarada", actor_id, horas=p.horas, clase=p.clase_dia)
    politicas.registrar_evaluacion(db, DOMINIO, p.id, ev, momento="declaracion", usuario_id=actor_id,
                                   organization_id=p.organization_id)
    if ev["decision"] == "block":
        _incumple(db, p, ev)
    _auditar(db, None, "CREATE", p, origen="posterior")
    db.commit()
    # Lo trabajado sin autorización siempre lo revisa una persona: ni se bloquea ni se aprueba solo.
    d = "review" if ev["decision"] in ("block", "auto_approve", "allow") else ev["decision"]
    abrir_flujo(db, p, {**ev, "decision": d, "resultado": {**(ev.get("resultado") or {}), "decision": d,
                                                           "auto_aprobar": False}}, cfg)
    return p


def _incumple(db: Session, p: PeticionDeHorasExtra, ev: dict) -> None:
    from app.services.approval_engine._base import responsable_de_nivel
    bloqueos = _mensajes(ev)["bloqueos"]
    evento(db, p, "incumple", None, bloqueos=bloqueos)
    avisar(db, [p.user_id, responsable_de_nivel(db, p.user_id, 1)], "Horas extra que incumplen una regla",
           f"{resumen(p)}: {'; '.join(bloqueos)}", p)


def abrir_flujo(db: Session, p: PeticionDeHorasExtra, ev: dict, cfg: dict) -> None:
    from app.services.approval_engine import fuentes
    from app.services.politicas import ejecutar_avisos
    fuentes.abrir(db, TIPO_DE_APROBACION, p.id, resumen(p), p.user_id,
                  {"type": p.tipo, "amount": p.horas, "hours": p.horas, "origin": p.origen},
                  evaluacion=ev, workflow_id=cfg.get("workflow_id"))
    db.refresh(p)
    if p.estado != "pendiente":
        return       # el flujo la aprobó solo (auto_approve) y ya se aplicó
    estado = fuentes.estado(db, TIPO_DE_APROBACION, p.id)
    if estado is None:
        ejecutar_avisos(db, ev["resultado"], p.user_id, "overtime", p.id, resumen(p), p.organization_id)
        if ev["decision"] == "auto_approve":
            aplicar_decision(db, p, True, None, "Aprobada por política")
            return
        from app.services.approval_engine._base import responsable_de_nivel
        jefe = responsable_de_nivel(db, p.user_id, 1)
        evento(db, p, "en_revision", None, sin_flujo=True, responsable=jefe)
        avisar(db, [jefe], "Horas extra por revisar", resumen(p), p)
        db.commit()
    else:
        evento(db, p, "en_aprobacion", None, solicitud=estado)
        db.commit()


# ── Decidir ──────────────────────────────────────────────────────────────────

def exigir_segregacion(db: Session, p: PeticionDeHorasExtra, usuario) -> None:
    """Nadie decide sobre lo suyo ni sobre lo que pidió para otra persona (403 + infracción SoD)."""
    from app.services.approval_engine._base import exigir_que_no_sea_suyo
    exigir_que_no_sea_suyo(db, p.user_id, usuario, TIPO_DE_APROBACION, p.id)
    if p.solicitante_id and p.solicitante_id != p.user_id:
        exigir_que_no_sea_suyo(db, p.solicitante_id, usuario, TIPO_DE_APROBACION, p.id)


def aplicar_decision(db: Session, p: PeticionDeHorasExtra, aprobado: bool, actor, nota: Optional[str],
                     horas_autorizadas: Optional[float] = None) -> PeticionDeHorasExtra:
    from app.services.approval_engine import fuentes
    if p.estado != "pendiente":
        return p
    actor_id = getattr(actor, "id", None)
    antes = instantanea(p)
    p.decidido_por, p.decidido_en = actor_id, _ahora()
    if aprobado:
        p.estado = "aprobada"
        p.horas_autorizadas = round(float(horas_autorizadas if horas_autorizadas is not None else p.horas), 4)
        fuentes.cerrar(db, TIPO_DE_APROBACION, p.id, "approved", nota or "Aprobada")
        evento(db, p, "aprobada", actor_id, nota=nota, horas_autorizadas=p.horas_autorizadas,
               automatica=actor_id is None or None)
        _auditar(db, actor, "APPROVE", p, antes)
        if actor_id != p.user_id:
            avisar(db, [p.user_id, p.solicitante_id if p.solicitante_id != actor_id else None], "Horas extra aprobadas",
                   f"{resumen(p)} · autorizadas {p.horas_autorizadas:g} h", p)
        db.commit()
        compensar(db, p, actor_id)
        return p
    p.estado = "rechazada"
    p.motivo_rechazo = (nota or None) and nota[:500]
    fuentes.cerrar(db, TIPO_DE_APROBACION, p.id, "rejected", nota or "Rechazada")
    evento(db, p, "rechazada", actor_id, motivo=nota)
    _auditar(db, actor, "REJECT", p, antes)
    avisar(db, [p.user_id, p.solicitante_id], "Horas extra rechazadas", f"{resumen(p)}{' — ' + nota if nota else ''}", p)
    db.commit()
    return p


def revisar(db: Session, usuario, p: PeticionDeHorasExtra, aprobado: bool, nota: Optional[str],
            horas_autorizadas: Optional[float] = None) -> PeticionDeHorasExtra:
    """Con solicitud en la bandeja, es un voto en ESA solicitud; sin ella, la decisión de su
    responsable (cualquiera de su cadena), RRHH o administración."""
    from app.models.billing_reports import ApprovalRequest
    from app.services.approval_engine.requests import decide_approval_request
    if p.estado != "pendiente":
        raise error_con_codigo(409, "horas_extra_no_pendiente")
    exigir_segregacion(db, p, usuario)
    if horas_autorizadas is not None and not 0 <= float(horas_autorizadas) <= float(p.horas) + 1e-6:
        raise error_con_codigo(422, "horas_extra_autorizadas_no_validas", horas=f"{p.horas:g}")
    req = db.query(ApprovalRequest).filter(ApprovalRequest.entity_type == TIPO_DE_APROBACION,
                                           ApprovalRequest.entity_id == p.id,
                                           ApprovalRequest.status == "pending").first()
    if req is not None:
        if horas_autorizadas is not None and aprobado:
            # Lo que el último paso apruebe queda limitado a lo que decide este aprobador.
            evento(db, p, "horas_ajustadas", usuario.id, horas_autorizadas=float(horas_autorizadas))
            p.horas_autorizadas = round(float(horas_autorizadas), 4)
            db.commit()
        decide_approval_request(req.id, "approved" if aprobado else "rejected", nota, None, db, usuario)
        db.refresh(p)
        if p.estado == "pendiente":
            evento(db, p, "voto", usuario.id, decision="approved" if aprobado else "rejected", nota=nota)
            db.commit()
        return p
    if not (es_gestion(usuario) or es_responsable_de(db, usuario, p.user_id)):
        from app.core.errores import ErrorDeDominio
        raise ErrorDeDominio(403, "Solo su responsable, RRHH o administración")
    return aplicar_decision(db, p, aprobado, usuario, nota, horas_autorizadas)


def aplicar_desde_bandeja(req, decision: str, actor, db: Session) -> None:
    """La decisión final de la bandeja de aprobaciones (`fuentes.aplicar`)."""
    p = db.query(PeticionDeHorasExtra).filter(PeticionDeHorasExtra.id == req.entity_id).first()
    if p is None or p.estado != "pendiente":
        return
    aplicar_decision(db, p, decision == "approved", actor, req.final_note,
                     p.horas_autorizadas if p.horas_autorizadas is not None else None)


def comprobar_en_bandeja(req, actor, db: Session) -> None:
    """Antes de un voto en la bandeja: la segregación también vale para quien la pidió por otro."""
    if actor is None:
        return
    p = db.query(PeticionDeHorasExtra).filter(PeticionDeHorasExtra.id == req.entity_id).first()
    if p is not None:
        exigir_segregacion(db, p, actor)


# ── Cancelar, editar, compensar, liquidar ────────────────────────────────────

def cancelar(db: Session, usuario, p: PeticionDeHorasExtra, nota: Optional[str] = None,
             motivo_evento: str = "cancelada") -> PeticionDeHorasExtra:
    from app.services.approval_engine import fuentes
    puede = p.estado == "pendiente" or (p.estado == "aprobada" and p.fecha > timeutil.today()
                                        and p.liquidada_en is None)
    if not puede:
        raise error_con_codigo(409, "horas_extra_no_cancelable")
    antes = instantanea(p)
    estaba_aprobada = p.estado == "aprobada"
    p.estado = "cancelada"
    fuentes.cerrar(db, TIPO_DE_APROBACION, p.id, "cancelled", nota or "Cancelada")
    evento(db, p, motivo_evento, getattr(usuario, "id", None), nota=nota)
    _auditar(db, usuario, "CANCEL", p, antes)
    db.commit()
    if estaba_aprobada:
        compensar(db, p, getattr(usuario, "id", None))
    return p


def editar(db: Session, usuario, p: PeticionDeHorasExtra, datos: dict) -> PeticionDeHorasExtra:
    """Solo pendientes: se vuelve a evaluar y la aprobación empieza de nuevo."""
    from app.services import politicas
    from app.services.approval_engine import fuentes
    if p.estado != "pendiente":
        raise error_con_codigo(409, "horas_extra_no_pendiente")
    cfg = exigir_activo(db)
    antes = instantanea(p)
    construir(db, usuario, datos, cfg, p)
    p.horas_autorizadas = None
    coherencia(db, p)
    solapada(db, p)
    ev = evaluar(db, p)
    if p.origen == "previa":
        try:
            _bloquear_si_politica(ev)
            _aplicar_y_exigir(db, p, ev, cfg)
        except Exception:
            db.rollback()
            raise
    else:
        _aplicar_y_exigir(db, p, ev, cfg, estricto=False)
    p.avisos = json.dumps(_mensajes(ev), ensure_ascii=False)
    fuentes.cerrar(db, TIPO_DE_APROBACION, p.id, "cancelled", "Editada: se vuelve a pedir")
    evento(db, p, "editada", usuario.id, antes=antes)
    politicas.registrar_evaluacion(db, DOMINIO, p.id, ev, momento="edicion", usuario_id=usuario.id,
                                   organization_id=p.organization_id)
    _auditar(db, usuario, "UPDATE", p, antes)
    db.commit()
    abrir_flujo(db, p, ev, cfg)
    return p


def recalcular_posterior(db: Session, p: PeticionDeHorasExtra, horas: float, actor_id: Optional[str], cfg: dict
                         ) -> None:
    """La declaración pendiente de un día cambia porque cambió lo imputado."""
    from app.services import politicas
    antes = instantanea(p)
    p.horas = round(horas, 4)
    ev = evaluar(db, p)
    _aplicar_y_exigir(db, p, ev, cfg, estricto=False)
    p.avisos = json.dumps(_mensajes(ev), ensure_ascii=False)
    evento(db, p, "recalculada", actor_id, antes=antes["horas"], ahora=p.horas)
    politicas.registrar_evaluacion(db, DOMINIO, p.id, ev, momento="recalculo", usuario_id=actor_id,
                                   organization_id=p.organization_id)
    if ev["decision"] == "block":
        _incumple(db, p, ev)
    _auditar(db, None, "UPDATE", p, antes, motivo="imputacion")
    db.commit()


def compensar(db: Session, p: PeticionDeHorasExtra, actor_id: Optional[str]) -> None:
    """Bolsa: si el tipo de bolsa exige horas extra aprobadas (`solo_horas_extra`), se recalcula
    la bolsa de ese día (al aprobar o al cancelar). El pago se liquida aparte (`liquidar`)."""
    if p.compensacion != "bolsa":
        return
    cfg = config.actual(db)
    from app.services.ausencias import bolsa, catalogo
    tipo = next((t for t in bolsa.tipos_de_bolsa(db) if t.id == cfg.get("tipo_bolsa_id")), None)
    if tipo is None or not catalogo.bolsa_de(tipo).get("solo_horas_extra"):
        return
    try:
        bolsa.recalcular(db, p.fecha, p.fecha, [p.user_id], actor_id)
        from app.models.horario import MovimientoDeSaldo
        m = db.query(MovimientoDeSaldo).filter(MovimientoDeSaldo.user_id == p.user_id,
                                               MovimientoDeSaldo.saldo_clave == tipo.id,
                                               MovimientoDeSaldo.origen == "bolsa",
                                               MovimientoDeSaldo.fecha == p.fecha).first()
        if p.estado == "aprobada":
            evento(db, p, "compensada_bolsa", actor_id, cantidad=m.cantidad if m else 0.0, tipo=tipo.nombre,
                   pendiente_de_imputar=m is None)
            db.commit()
    except Exception:
        db.rollback()
        logger.exception("no se pudo recalcular la bolsa de las horas extra %s", p.id)


def liquidar(db: Session, usuario, p: PeticionDeHorasExtra, referencia: str) -> PeticionDeHorasExtra:
    if p.estado != "aprobada" or p.compensacion != "pago":
        raise error_con_codigo(409, "horas_extra_no_liquidable")
    if p.liquidada_en is not None:
        raise error_con_codigo(409, "horas_extra_ya_liquidada")
    referencia = (referencia or "").strip()
    if not referencia:
        raise error_con_codigo(422, "horas_extra_referencia_obligatoria")
    exigir_segregacion(db, p, usuario)
    antes = instantanea(p)
    p.liquidada_en, p.liquidada_por, p.referencia_pago = _ahora(), usuario.id, referencia[:120]
    evento(db, p, "liquidada", usuario.id, referencia=p.referencia_pago, horas_ponderadas=calculo.horas_ponderadas(p))
    _auditar(db, usuario, "SETTLE", p, antes, referencia=p.referencia_pago)
    db.commit()
    return p
