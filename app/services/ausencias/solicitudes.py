"""El ciclo de vida de una ausencia sobre el motor de políticas y el de aprobaciones.

    pedir ─┬─ bloqueo de una política ───────────────────────────▶ 422 (no se guarda)
           ├─ cupo lleno y «bloquear» (al reservar) ─────────────▶ rechazada (409)
           ├─ cupo lleno y «lista de espera» ────────────────────▶ en espera ─┐
           └─ con plaza (o sin cupo) ─▶ pendiente ─▶ flujo de aprobación     │
                                                     │                        │
              cancelar / rechazar ─▶ suelta plazas ─▶ promueve al siguiente ◀┘
                                                     │
              aprobar ─▶ (cupo «al aprobar»: reserva ─▶ aprobada | en espera | rechazada)

- Las reglas son las políticas publicadas del dominio `ausencias`
  (`politicas.evaluar`); cada evaluación se guarda con su explicación.
- La aprobación es SIEMPRE el motor de aprobaciones (`entity_type = leave`): el
  flujo del tipo (o el que elijan sus condiciones), más los niveles y pasos que
  añadan las políticas. Sin flujo ni pasos de política, la decisión es la de un
  responsable en Ausencias (la de siempre), registrada en la línea de tiempo.
- Todo cambio deja un evento en `eventos_de_ausencia` (la línea de tiempo).

Rev. 180 — por horas: una petición es por DÍAS (enteros o medio día) o por
HORAS (franja `start_time`–`end_time` cada día, dentro de su horario efectivo),
según los `modos` del tipo. Se guarda lo que cubre sobre su horario:
`working_days` (días equivalentes), `scheduled_hours` (horas) y `amount` (en la
unidad del tipo). Las políticas pueden redondear las horas (`redondeo`) y
permitir que el saldo quede en negativo hasta un límite (`saldo_negativo`).
"""
from __future__ import annotations

import json
import logging
import uuid
from datetime import date, datetime, time, timedelta, timezone
from typing import Optional

from sqlalchemy.orm import Session

from app.core import timeutil
from app.core.errores import ErrorDeDominio
from app.core.codigos_de_error import error as error_con_codigo
from app.models.ausencias import EventoDeAusencia
from app.models.resources import Absence, AbsenceStatus
from app.services.ausencias import catalogo, cupos, reglas, saldos

logger = logging.getLogger(__name__)
DOMINIO = "ausencias"
ROLES_QUE_GESTIONAN = ("admin", "hr", "pm", "team_lead")


def _rol(u) -> str:
    return str(getattr(getattr(u, "role", None), "value", getattr(u, "role", None)) or "")


def _ahora() -> datetime:
    return datetime.now(timezone.utc)


def evento(db: Session, a: Absence, tipo: str, actor_id: Optional[str] = None, **datos) -> None:
    db.add(EventoDeAusencia(id=str(uuid.uuid4()), organization_id=a.organization_id, absence_id=a.id, tipo=tipo,
                            actor_id=actor_id, datos=json.dumps(datos, ensure_ascii=False, default=str) if datos else None))


def avisar(db: Session, user_ids, titulo: str, cuerpo: str, a: Absence) -> None:
    from app.services.notifications import notify_user
    for uid in sorted({u for u in user_ids if u}):
        try:
            notify_user(db, uid, "system", titulo[:255], cuerpo[:1000], resource="absence", resource_id=a.id,
                        action_url="/absences")
        except Exception:
            logger.warning("no se pudo avisar de la ausencia %s a %s", a.id, uid, exc_info=True)


def _resumen(a: Absence, tipo) -> str:
    unidad = {"dias": "d", "medios_dias": "½d", "horas": "h"}.get(getattr(tipo, "unidad", "dias"), "d")
    return f"{getattr(tipo, 'nombre', a.type)} {a.start_date} → {a.end_date} · {a.amount or a.working_days or 0:g} {unidad}"


# ── Construir y evaluar ──────────────────────────────────────────────────────

def _fecha(v, nombre: str) -> date:
    if isinstance(v, date):
        return v
    try:
        return date.fromisoformat(str(v)[:10])
    except (TypeError, ValueError):
        raise error_con_codigo(422, "fecha_no_valida_en", nombre=nombre)


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


def construir(db: Session, usuario, datos: dict, a: Optional[Absence] = None) -> Absence:
    """Una ausencia (nueva y SIN guardar, o la existente con los cambios) desde
    los datos de la pantalla o del API antiguo (`type`, `start_date`, `end_date`, `reason`)."""
    from app.models.user import User
    tipo = catalogo.resolver_tipo(db, tipo_id=datos.get("absence_type_id") or datos.get("tipo_id"),
                                  clave=datos.get("type"))
    inicio, fin = _fecha(datos.get("start_date"), "inicio"), _fecha(datos.get("end_date"), "fin")
    if fin < inicio:
        raise ErrorDeDominio(400, "La fecha de fin no puede ser anterior a la de inicio")
    sustituto = datos.get("substitute_id") or None
    if sustituto:
        if sustituto == (a.user_id if a else usuario.id):
            raise ErrorDeDominio(422, "No puedes ser tu propio sustituto")
        if db.query(User.id).filter(User.id == sustituto, User.is_active.is_(True)).first() is None:
            raise ErrorDeDominio(422, "El sustituto no existe en tu empresa o no está activo")
    turno = datos.get("shift_id") or None
    if turno:
        from app.services.ausencias import turnos
        turnos.turno(db, turno)
    horas = datos.get("hours")
    if horas not in (None, "") and float(horas) <= 0:
        raise ErrorDeDominio(422, "Las horas tienen que ser más de 0")
    h_ini, h_fin = _hora(datos.get("start_time"), "hora de inicio"), _hora(datos.get("end_time"), "hora de fin")
    if (h_ini is None) != (h_fin is None):
        raise error_con_codigo(422, "indica_hora_inicio_y_fin")
    if h_ini is not None and h_ini == h_fin:
        raise error_con_codigo(422, "franja_misma_hora")
    permitidos = catalogo.modos_de(tipo)
    solo_horas = "dias" not in permitidos and "medio_dia" not in permitidos
    modo = datos.get("modo") or ("horas" if (h_ini is not None or horas not in (None, "") or solo_horas) else "dias")
    if modo not in ("dias", "horas"):
        raise error_con_codigo(422, "modo_de_peticion_no_valido")
    medio = bool(datos.get("half_day_start")) or bool(datos.get("half_day_end"))
    if modo == "horas" and "horas" not in permitidos:
        raise error_con_codigo(422, "tipo_no_se_pide_por_horas", tipo=tipo.nombre)
    if modo == "dias" and "dias" not in permitidos and not (medio and "medio_dia" in permitidos):
        raise error_con_codigo(422, "tipo_se_pide_por_horas", tipo=tipo.nombre)
    if modo == "dias" and medio and "medio_dia" not in permitidos:
        raise error_con_codigo(422, "tipo_no_se_pide_por_medio_dia", tipo=tipo.nombre)
    if modo == "horas" and h_ini is None and horas in (None, ""):
        raise error_con_codigo(422, "por_horas_indica_franja")
    if a is None:
        a = Absence(id=None, user_id=usuario.id, organization_id=getattr(usuario, "organization_id", None),
                    status=AbsenceStatus.pending, is_active=True)
    a.absence_type, a.absence_type_id, a.type = tipo, tipo.id, tipo.clave
    a.start_date, a.end_date = inicio, fin
    a.reason = datos.get("reason")
    a.shift_id, a.substitute_id = turno, sustituto
    a.modo = modo
    a.start_time, a.end_time = (h_ini, h_fin) if modo == "horas" else (None, None)
    a.half_day_start = bool(datos.get("half_day_start")) and modo == "dias"
    a.half_day_end = bool(datos.get("half_day_end")) and modo == "dias"
    a.hours = float(horas) if horas not in (None, "") and modo == "horas" and h_ini is None else None
    a.unit = tipo.unidad
    return a


def medidas_finales(ev: dict) -> dict:
    """Lo que la petición descuenta tras las políticas: el `redondeo` de las
    horas (si alguna lo pide, gana el de mayor prioridad) y el negativo que se
    permite en el saldo (`saldo_negativo`: el mayor)."""
    ctx = ev.get("contexto") or {}
    propios = (ev.get("resultado") or {}).get("propios") or []
    horas, dias, cantidad = float(ctx.get("horas") or 0), float(ctx.get("dias_laborables") or 0), \
        float(ctx.get("cantidad") or 0)
    redondeo = next((p for p in propios if p.get("tipo") == "redondeo"), None)
    detalle = None
    if redondeo is not None and horas > 0:
        nuevas = reglas.redondear(horas, int(redondeo.get("minutos") or 0), redondeo.get("modo") or "arriba")
        factor = nuevas / horas
        detalle = {"antes": horas, "despues": nuevas, "minutos": int(redondeo.get("minutos") or 0),
                   "modo": redondeo.get("modo"), "politica": redondeo.get("politica")}
        horas, dias = nuevas, round(dias * factor, 4)
        cantidad = round(cantidad * factor, 4)
    negativo = max([float(p.get("hasta") or 0) for p in propios if p.get("tipo") == "saldo_negativo"] or [0.0])
    restante = ctx.get("saldo_restante")
    if restante is not None and detalle is not None:
        unidad_h = ctx.get("_saldo_unidad") == "horas"
        delta = (detalle["despues"] - detalle["antes"]) if unidad_h else dias - float(ctx.get("dias_laborables") or 0)
        restante = round(restante - delta, 2)
    return {"horas": round(horas, 4), "dias": round(dias, 4), "cantidad": round(cantidad, 4), "redondeo": detalle,
            "negativo_permitido": negativo, "saldo_restante": restante}


def _guardar_medidas(a: Absence, m: dict) -> None:
    a.working_days, a.amount, a.scheduled_hours = m["dias"], m["cantidad"], m["horas"]


def evaluar(db: Session, a: Absence) -> dict:
    from app.services import politicas
    return politicas.evaluar(db, DOMINIO, a, organization_id=a.organization_id)


def _cupos_en(ev: dict, momento: str) -> list[dict]:
    return [c for c in (ev.get("resultado") or {}).get("propios") or []
            if c.get("tipo") == cupos.TIPO and (c.get("momento") or "solicitud") == momento and c.get("clave")]


def _peticiones(ev: dict, momento: str) -> list[dict]:
    aus = (ev.get("contexto") or {}).get("_ausencia") or {}
    return [{"cupo": c, "huecos": cupos.huecos_de(c, aus)} for c in _cupos_en(ev, momento)]


def _mensaje_de_bloqueo(cupo: Optional[dict]) -> str:
    for r in (cupo or {}).get("si_lleno") or []:
        if r.get("tipo") == "block" and (r.get("mensaje") or "").strip():
            return r["mensaje"]
    return "No queda plaza en el cupo para esas fechas"


def _exigencias(db: Session, a: Absence, tipo, ctx: dict, m: Optional[dict] = None) -> None:
    """Lo que no depende de una política: sustituto si el tipo lo exige, que
    caiga en su horario y el saldo (con el negativo que permitan las políticas)."""
    if tipo.requiere_sustituto and not a.substitute_id:
        raise error_con_codigo(422, "tipo_necesita_sustituto", tipo=tipo.nombre)
    if not ctx.get("dias_laborables"):
        if a.start_time is not None:
            raise error_con_codigo(422, "franja_fuera_de_horario")
        raise error_con_codigo(422, "sin_dia_de_trabajo")
    restante = (m or {}).get("saldo_restante", ctx.get("saldo_restante"))
    permitido = float((m or {}).get("negativo_permitido") or 0)
    if tipo.descuenta_saldo and restante is not None and restante < -permitido - 1e-9:
        disponible = ctx.get("saldo_disponible")
        cantidad = f"{(m or ctx).get('cantidad', ctx.get('cantidad')):g}"
        codigo = "saldo_insuficiente" if disponible is not None else "saldo_agotado"
        params = {"cantidad": cantidad}
        if disponible is not None:
            params["disponible"] = f"{disponible:g}"
        if permitido:
            codigo += "_con_limite"
            params["permitido"] = f"{permitido:g}"
        raise error_con_codigo(400, codigo, **params)


def _solapada(db: Session, a: Absence) -> None:
    """Otra ausencia viva de la persona que pisa esta. Dos por horas el mismo día
    con franjas distintas no se pisan (rev. 180)."""
    from app.services.horario import tramos as tr
    q = db.query(Absence).filter(
        Absence.user_id == a.user_id, Absence.is_active.is_(True),
        Absence.status.in_([AbsenceStatus.pending, AbsenceStatus.approved, AbsenceStatus.waitlisted]),
        Absence.start_date <= a.end_date, Absence.end_date >= a.start_date)
    if a.id:
        q = q.filter(Absence.id != a.id)
    for otra in q.all():
        if a.start_time is not None and otra.start_time is not None:
            if not tr.interseccion([tr.desde_texto(a.start_time, a.end_time)],
                                   [tr.desde_texto(otra.start_time, otra.end_time)]):
                continue
        raise ErrorDeDominio(400, f"Ya tienes una ausencia solapada del {otra.start_date} al {otra.end_date}")


# ── Vista previa ─────────────────────────────────────────────────────────────

def _aprobaciones_previstas(db: Session, a: Absence, tipo, ev: dict) -> list[dict]:
    """Los pasos que tendrá la aprobación: los del flujo del tipo (o el que se
    elegiría) y los que añaden las políticas."""
    from app.models.billing_reports import ApprovalWorkflow
    from app.services.approval_engine._base import elegir_flujo
    wf = None
    if tipo.workflow_id:
        wf = db.query(ApprovalWorkflow).filter(ApprovalWorkflow.id == tipo.workflow_id,
                                               ApprovalWorkflow.is_active.is_(True)).first()
    if wf is None:
        wf = elegir_flujo(db, "leave", {"type": tipo.clave})
    salida = []
    if wf is not None:
        for s in sorted(wf.steps or [], key=lambda s: (s.step_order, str(s.id))):
            salida.append({"orden": s.step_order, "nombre": s.name, "tipo": getattr(s, "kind", None) or "approve",
                           "aprobador": s.approver_type, "rol": s.approver_role, "origen": "flujo"})
    r = ev.get("resultado") or {}
    for i in range(int(r.get("niveles") or 0)):
        salida.append({"orden": None, "nombre": f"+{i + 1}", "tipo": "approve", "aprobador": "manager_level",
                       "rol": None, "origen": "politica"})
    for p in r.get("pasos") or []:
        salida.append({"orden": None, "nombre": p.get("nombre"), "tipo": "approve", "aprobador": p.get("approver_type"),
                       "rol": p.get("approver_role"), "origen": "politica"})
    return salida


def _documentos_previstos(db: Session, tipo, ev: dict) -> list[dict]:
    from app.services.ausencias import documentos
    salida = [{"tipo_id": r.tipo_de_documento_id, "nombre": r.tipo_de_documento.nombre, "plazo_dias": r.plazo_dias,
               "plazo_desde": r.plazo_desde, "repetir_cada_dias": r.repetir_cada_dias, "obligatorio": bool(r.obligatorio),
               "origen": "tipo"} for r in tipo.requisitos or []]
    for t in documentos.tipos_de_politica(db, ev):
        if t.id not in {x["tipo_id"] for x in salida}:
            salida.append({"tipo_id": t.id, "nombre": t.nombre, "plazo_dias": 0, "plazo_desde": "solicitud",
                           "repetir_cada_dias": None, "obligatorio": True, "origen": "politica"})
    return salida


def vista_previa(db: Session, usuario, datos: dict) -> dict:
    """Lo que pasaría si se pidiera ahora: días, saldo, cupos (plazas libres y
    puesto en la lista de espera), aprobaciones, documentos, avisos y bloqueos.
    No guarda nada."""
    actual = None
    if datos.get("id"):
        actual = db.query(Absence).filter(Absence.id == datos["id"], Absence.user_id == usuario.id).first()
    a = construir(db, usuario, datos)
    if actual is not None:
        a.id = actual.id
    if not a.requested_at:
        a.requested_at = _ahora()
    ev = evaluar(db, a)
    ctx = ev["contexto"]
    tipo = a.absence_type
    r = ev["resultado"]
    m = medidas_finales(ev)
    errores = []
    try:
        _exigencias(db, a, tipo, ctx, m)
        _solapada(db, a)
    except ErrorDeDominio as e:
        errores.append(e.detail if isinstance(e.detail, str) else str(e.detail))
    cupos_detalle = [p for pol in ev["explicacion"] for regla in pol.get("reglas") or [] for p in regla.get("propios") or []
                     if p.get("tipo", "cupo") == "cupo" and "huecos" in p]
    saldo = saldos.de_tipo(db, a.user_id, a.start_date, tipo, excluir=a.id)
    aplican = [{"politica": p.get("politica"), "reglas": [x.get("regla") for x in p.get("reglas") or [] if x.get("cumple")]}
               for p in ev["explicacion"] if p.get("aplica")]
    return {
        "decision": ev["decision"], "dias": ctx["_ausencia"]["dias"], "dias_laborables": m["dias"],
        "cantidad": m["cantidad"], "unidad": ctx["unidad"], "modo": ctx.get("modo"), "horas": m["horas"],
        "horas_max_dia": ctx.get("horas_max_dia"), "horas_fuera_de_horario": ctx.get("horas_fuera_de_horario"),
        "redondeo": m["redondeo"], "negativo_permitido": m["negativo_permitido"], "politicas_que_aplican": aplican,
        "saldo": saldo, "saldo_restante": m["saldo_restante"], "saldo_restante_horas": ctx.get("saldo_restante_horas"),
        "cupos": cupos_detalle, "aprobaciones": _aprobaciones_previstas(db, a, tipo, ev),
        "documentos": _documentos_previstos(db, tipo, ev),
        "avisos": [x.get("mensaje") for x in r.get("avisos") or []],
        "bloqueos": [x.get("mensaje") for x in r.get("bloqueos") or []] + errores,
        "lista_de_espera": bool(r.get("lista_de_espera")) or any(c.get("lleno") and c.get("momento") == "solicitud"
                                                                  for c in cupos_detalle),
        "requisitos": [x.get("tipo") for x in r.get("requisitos") or []],
        "cobertura_restante": ctx.get("cobertura_restante"), "companeros_ausentes": ctx.get("companeros_ausentes"),
        "explicacion": ev["explicacion"],
    }


# ── Pedir ────────────────────────────────────────────────────────────────────

def solicitar(db: Session, usuario, datos: dict) -> Absence:
    from app.services import politicas
    from app.services.ausencias import documentos
    a = construir(db, usuario, datos)
    a.id = str(uuid.uuid4())
    a.requested_at = _ahora()
    ev = evaluar(db, a)
    ctx = ev["contexto"]
    tipo = a.absence_type
    m = medidas_finales(ev)
    _exigencias(db, a, tipo, ctx, m)
    _solapada(db, a)
    if ev["decision"] == "block":
        raise ErrorDeDominio(422, {"message": "; ".join(b.get("mensaje") or "" for b in ev["resultado"]["bloqueos"])
                                   or "Lo impide una política", "bloqueos": ev["resultado"]["bloqueos"]})
    _guardar_medidas(a, m)
    db.add(a)
    db.flush()
    evento(db, a, "pedida", usuario.id, dias=a.working_days, cantidad=a.amount, unidad=a.unit, horas=a.scheduled_hours,
           modo=a.modo, franja=f"{a.start_time:%H:%M}–{a.end_time:%H:%M}" if a.start_time else None,
           redondeo=m["redondeo"])
    politicas.registrar_evaluacion(db, DOMINIO, a.id, ev, momento="solicitud", usuario_id=usuario.id,
                                   organization_id=a.organization_id)
    documentos.crear_requisitos(db, a, tipo, ev)
    db.commit()
    _tras_pedir(db, a, ev, usuario)
    return a


def _tras_pedir(db: Session, a: Absence, ev: dict, actor) -> None:
    """Cupos al pedir (reserva o espera) y, con plaza, el flujo de aprobación."""
    peticiones = _peticiones(ev, "solicitud")
    r = cupos.reservar(db, a.id, a.requested_at, peticiones, a.organization_id) if peticiones else {"resultado": "sin_cupo"}
    if r["resultado"] == "lleno":
        a.status, a.rejection_reason = AbsenceStatus.rejected, _mensaje_de_bloqueo(r.get("cupo"))[:255]
        evento(db, a, "rechazada", None, motivo=a.rejection_reason, cupo_lleno=r.get("llenos"))
        db.commit()
        raise ErrorDeDominio(409, a.rejection_reason)
    if r["resultado"] == "espera" or (r["resultado"] == "sin_cupo" and ev["decision"] == "waitlist"):
        a.status = AbsenceStatus.waitlisted
        posicion = cupos.posicion(db, a.id)
        evento(db, a, "en_espera", None, momento="solicitud", posicion=posicion, llenos=r.get("llenos"))
        avisar(db, [a.user_id], "Ausencia en lista de espera",
               f"{_resumen(a, a.absence_type)}: no queda plaza; vas la {posicion or '—'}ª en la lista", a)
        db.commit()
        return
    if r["resultado"] == "ocupa":
        evento(db, a, "plaza", None, reservas=cupos.reservas_de(db, a.id))
        db.commit()
    _abrir_flujo(db, a, ev)


def _abrir_flujo(db: Session, a: Absence, ev: dict) -> None:
    from app.services.approval_engine import fuentes
    from app.services.politicas import ejecutar_avisos
    tipo = a.absence_type
    if not tipo.requiere_aprobacion and ev["decision"] in ("allow", "auto_approve"):
        aplicar_decision(db, a, True, None, "No necesita aprobación")
        return
    fuentes.abrir(db, "leave", a.id, _resumen(a, tipo), a.user_id,
                  {"days": a.working_days, "type": tipo.clave}, evaluacion=ev, workflow_id=tipo.workflow_id)
    db.refresh(a)
    estado = fuentes.estado(db, "leave", a.id)
    if estado is None:
        # Sin flujo ni pasos de política: decide un responsable en Ausencias.
        ejecutar_avisos(db, ev["resultado"], a.user_id, "absence", a.id, _resumen(a, tipo), a.organization_id)
        if ev["decision"] == "auto_approve":
            aplicar_decision(db, a, True, None, "Aprobada por política")
            return
        from app.services.approval_engine._base import responsable_de_nivel
        jefe = responsable_de_nivel(db, a.user_id, 1)
        evento(db, a, "en_revision", None, sin_flujo=True)
        avisar(db, [jefe], "Ausencia por revisar", _resumen(a, tipo), a)
        db.commit()
    else:
        evento(db, a, "en_aprobacion", None, solicitud=estado)
        db.commit()


# ── Decidir ──────────────────────────────────────────────────────────────────

def aplicar_decision(db: Session, a: Absence, aprobado: bool, actor, nota: Optional[str]) -> Absence:
    """La decisión final (de la bandeja, de un responsable o de una política).

    Al aprobar, los cupos «al aprobar» reservan plaza: sin plaza, la ausencia
    queda en espera (ya aprobada) o se rechaza, según la política.
    """
    from app.services.approval_engine import fuentes
    if a.status not in (AbsenceStatus.pending, AbsenceStatus.waitlisted):
        return a
    actor_id = getattr(actor, "id", None)
    ampliacion = _ampliacion_pendiente(db, a)
    if not aprobado and ampliacion is not None:
        return _rechazar_ampliacion(db, a, actor_id, nota, ampliacion)
    if aprobado:
        ev = evaluar(db, a)
        peticiones = _peticiones(ev, "aprobacion")
        if peticiones:
            r = cupos.reservar(db, a.id, a.requested_at or _ahora(), peticiones, a.organization_id)
            if r["resultado"] == "lleno":
                return _rechazar(db, a, actor_id, _mensaje_de_bloqueo(r.get("cupo")))
            if r["resultado"] == "espera":
                a.status = AbsenceStatus.waitlisted
                posicion = cupos.posicion(db, a.id)
                evento(db, a, "en_espera", actor_id, momento="aprobacion", posicion=posicion, llenos=r.get("llenos"))
                avisar(db, [a.user_id], "Ausencia aprobada en lista de espera",
                       f"{_resumen(a, a.absence_type)}: aprobada, pero el cupo está lleno; vas la {posicion or '—'}ª", a)
                db.commit()
                return a
        a.status = AbsenceStatus.approved
        a.approved_by, a.approved_at, a.rejection_reason = actor_id, _ahora(), None
        fuentes.cerrar(db, "leave", a.id, "approved", nota or "Aprobada")
        evento(db, a, "aprobada", actor_id, nota=nota)
        if actor_id is None or actor_id != a.user_id:
            avisar(db, [a.user_id], "Ausencia aprobada", _resumen(a, a.absence_type), a)
        db.commit()
        return a
    return _rechazar(db, a, actor_id, nota)


def _rechazar(db: Session, a: Absence, actor_id: Optional[str], nota: Optional[str]) -> Absence:
    from app.services.approval_engine import fuentes
    a.status = AbsenceStatus.rejected
    a.approved_by, a.approved_at, a.rejection_reason = actor_id, _ahora(), (nota or None) and nota[:255]
    fuentes.cerrar(db, "leave", a.id, "rejected", nota or "Rechazada")
    evento(db, a, "rechazada", actor_id, motivo=nota)
    avisar(db, [a.user_id], "Ausencia rechazada", f"{_resumen(a, a.absence_type)}{' — ' + nota if nota else ''}", a)
    db.commit()
    libres = cupos.liberar(db, a.id)
    promover(db, libres)
    return a


def revisar(db: Session, usuario, a: Absence, aprobado: bool, nota: Optional[str]) -> Absence:
    """`POST /absences/{id}/review`: con solicitud en la bandeja, es un voto en
    ESA solicitud (paso actual, varios niveles, en paralelo, delegación); sin
    ella, la decisión directa de un responsable."""
    from app.models.billing_reports import ApprovalRequest
    from app.services.approval_engine._base import exigir_que_no_sea_suyo
    from app.services.approval_engine.requests import decide_approval_request
    if a.status != AbsenceStatus.pending:
        raise ErrorDeDominio(400, "Solo se pueden revisar ausencias pendientes")
    exigir_que_no_sea_suyo(db, a.user_id, usuario, "absence", a.id)
    req = db.query(ApprovalRequest).filter(ApprovalRequest.entity_type == "leave", ApprovalRequest.entity_id == a.id,
                                           ApprovalRequest.status == "pending").first()
    if req is not None:
        decide_approval_request(req.id, "approved" if aprobado else "rejected", nota, None, db, usuario)
        db.refresh(a)
        if a.status == AbsenceStatus.pending:
            evento(db, a, "voto", usuario.id, decision="approved" if aprobado else "rejected", nota=nota)
            db.commit()
        return a
    return aplicar_decision(db, a, aprobado, usuario, nota)


# ── Cancelar, editar, ampliar ────────────────────────────────────────────────

def cancelar(db: Session, usuario, a: Absence) -> None:
    from app.services.approval_engine import fuentes
    if a.status == AbsenceStatus.approved and a.start_date <= timeutil.today():
        raise ErrorDeDominio(400, "No puedes cancelar una ausencia ya iniciada")
    a.status = AbsenceStatus.cancelled
    a.is_active = False
    fuentes.cerrar(db, "leave", a.id, "cancelled", "Cancelada por quien la pidió")
    evento(db, a, "cancelada", usuario.id)
    db.commit()
    libres = cupos.liberar(db, a.id)
    promover(db, libres)


def editar(db: Session, usuario, a: Absence, datos: dict) -> Absence:
    """Solo pendiente o en espera: se vuelve a evaluar y a reservar desde cero
    (la petición conserva su momento de llegada si no cambian las fechas)."""
    from app.services.approval_engine import fuentes
    from app.services.ausencias import documentos
    if a.status not in (AbsenceStatus.pending, AbsenceStatus.waitlisted):
        raise ErrorDeDominio(400, f"Solo se pueden editar ausencias pendientes. Esta está '{getattr(a.status, 'value', a.status)}'")
    fechas = (a.start_date, a.end_date)
    a = construir(db, usuario, datos, a)
    if (a.start_date, a.end_date) != fechas:
        a.requested_at = _ahora()
    ev = evaluar(db, a)
    ctx = ev["contexto"]
    m = medidas_finales(ev)
    _exigencias(db, a, a.absence_type, ctx, m)
    _solapada(db, a)
    if ev["decision"] == "block":
        db.rollback()
        raise ErrorDeDominio(422, "; ".join(b.get("mensaje") or "" for b in ev["resultado"]["bloqueos"]) or "Lo impide una política")
    _guardar_medidas(a, m)
    a.status = AbsenceStatus.pending
    fuentes.cerrar(db, "leave", a.id, "cancelled", "Editada: se vuelve a pedir")
    evento(db, a, "editada", usuario.id, dias=a.working_days)
    from app.services import politicas
    politicas.registrar_evaluacion(db, DOMINIO, a.id, ev, momento="edicion", usuario_id=usuario.id,
                                   organization_id=a.organization_id)
    documentos.crear_requisitos(db, a, a.absence_type, ev)
    db.commit()
    libres = cupos.liberar(db, a.id)
    _tras_pedir(db, a, ev, usuario)
    promover(db, libres)
    return a


def _ampliacion_pendiente(db: Session, a: Absence) -> Optional[dict]:
    """Los datos de una ampliación aún sin decidir (la última `ampliada` pendiente
    sin una `aprobada`, `ampliacion_rechazada` o `cancelada` después), o None."""
    eventos = db.query(EventoDeAusencia).filter(EventoDeAusencia.absence_id == a.id) \
        .order_by(EventoDeAusencia.created_at.desc(), EventoDeAusencia.id.desc()).all()
    for e in eventos:
        if e.tipo in ("aprobada", "ampliacion_rechazada", "cancelada"):
            return None
        if e.tipo == "ampliada":
            d = json.loads(e.datos or "{}")
            return d if d.get("pendiente") else None
    return None


def _requiere_aprobacion(db: Session, tipo, ev: dict) -> bool:
    """La ampliación vuelve a aprobación si las políticas lo piden (revisión,
    lista de espera) o si el tipo pide aprobación y hay flujo para él."""
    from app.services.approval_engine._base import elegir_flujo
    if ev["decision"] in ("review", "waitlist"):
        return True
    if not tipo.requiere_aprobacion or ev["decision"] == "auto_approve":
        return False
    return bool(tipo.workflow_id) or elegir_flujo(db, "leave", {"type": tipo.clave}) is not None


def ampliar(db: Session, usuario, a: Absence, nuevo_fin: date, nota: Optional[str] = None) -> Absence:
    """Alargar una ausencia aprobada (una baja que se prolonga). RRHH, admin o el
    responsable. El tramo nuevo pasa por las políticas como una petición: si una
    lo bloquea, no se amplía; toma (o espera) sus plazas de cupo; y vuelve a
    aprobación si las políticas o el flujo del tipo lo piden. Si se rechaza, la
    ausencia vuelve a su fin anterior (sigue aprobada). Todo queda en la línea de tiempo."""
    from app.services import politicas
    from app.services.approval_engine import fuentes
    from app.services.ausencias import documentos
    if a.status != AbsenceStatus.approved:
        raise ErrorDeDominio(400, "Solo se amplía una ausencia aprobada")
    if nuevo_fin <= a.end_date:
        raise ErrorDeDominio(422, "La nueva fecha de fin tiene que ser posterior a la actual")
    anterior = a.end_date
    tramo = Absence(id=a.id, user_id=a.user_id, organization_id=a.organization_id, type=a.type,
                    absence_type_id=a.absence_type_id, start_date=anterior + timedelta(days=1), end_date=nuevo_fin,
                    shift_id=a.shift_id, substitute_id=a.substitute_id, reason=a.reason, unit=a.unit,
                    half_day_start=False, half_day_end=False, requested_at=_ahora(), status=AbsenceStatus.pending,
                    modo=a.modo, start_time=a.start_time, end_time=a.end_time)
    tramo.absence_type = a.absence_type
    ev = evaluar(db, tramo)
    if tramo in db:
        db.expunge(tramo)
    if ev["decision"] == "block":
        raise ErrorDeDominio(422, "; ".join(b.get("mensaje") or "" for b in ev["resultado"]["bloqueos"])
                             or "Lo impide una política")
    otra = db.query(Absence).filter(Absence.user_id == a.user_id, Absence.id != a.id, Absence.is_active.is_(True),
                                    Absence.status.in_([AbsenceStatus.pending, AbsenceStatus.approved,
                                                        AbsenceStatus.waitlisted]),
                                    Absence.start_date <= nuevo_fin, Absence.end_date > anterior).first()
    if otra is not None:
        raise ErrorDeDominio(400, f"Se solapa con otra ausencia del {otra.start_date} al {otra.end_date}")
    # Plazas del tramo nuevo (cualquier momento: la parte ya aprobada conserva las suyas).
    aus = (ev.get("contexto") or {}).get("_ausencia") or {}
    peticiones = [{"cupo": c, "huecos": cupos.huecos_de(c, aus)} for c in (ev["resultado"].get("propios") or [])
                  if c.get("tipo") == cupos.TIPO and c.get("clave")]
    r = cupos.reservar(db, a.id, _ahora(), peticiones, a.organization_id) if peticiones else {"resultado": "sin_cupo"}
    if r["resultado"] == "lleno":
        raise ErrorDeDominio(409, _mensaje_de_bloqueo(r.get("cupo")))
    a.end_date = nuevo_fin
    _guardar_medidas(a, medidas_finales(evaluar(db, a)))
    espera = r["resultado"] == "espera" or (r["resultado"] == "sin_cupo" and ev["decision"] == "waitlist")
    pendiente = espera or _requiere_aprobacion(db, a.absence_type, ev)
    evento(db, a, "ampliada", usuario.id, desde=anterior, hasta=nuevo_fin, nota=nota, pendiente=pendiente,
           decision=ev["decision"])
    politicas.registrar_evaluacion(db, DOMINIO, a.id, ev, momento="ampliacion", usuario_id=usuario.id,
                                   organization_id=a.organization_id)
    documentos.crear_requisitos(db, a, a.absence_type, ev)
    avisar(db, [a.user_id], "Ausencia ampliada", _resumen(a, a.absence_type), a)
    if espera:
        a.status = AbsenceStatus.waitlisted
        evento(db, a, "en_espera", None, momento="solicitud", posicion=cupos.posicion(db, a.id), ampliacion=True)
        db.commit()
        return a
    if not pendiente:
        db.commit()
        return a
    a.status = AbsenceStatus.pending
    db.commit()
    fuentes.abrir(db, "leave", a.id, f"Ampliación: {_resumen(a, a.absence_type)}", a.user_id,
                  {"days": a.working_days, "type": a.type, "ampliacion": True}, evaluacion=ev,
                  workflow_id=a.absence_type.workflow_id)
    db.refresh(a)
    if a.status == AbsenceStatus.pending:
        evento(db, a, "en_aprobacion" if fuentes.estado(db, "leave", a.id) == "pending" else "en_revision", None,
               ampliacion=True)
        db.commit()
    return a


def _rechazar_ampliacion(db: Session, a: Absence, actor_id: Optional[str], nota: Optional[str], d: dict) -> Absence:
    """Rechazada una ampliación: vuelve al fin anterior, sigue aprobada y suelta las plazas del tramo."""
    from app.models.ausencias import HuecoDeCupo, ReservaDeCupo
    from app.services.approval_engine import fuentes
    anterior = date.fromisoformat(str(d["desde"])[:10])
    a.end_date, a.status = anterior, AbsenceStatus.approved
    _guardar_medidas(a, medidas_finales(evaluar(db, a)))
    fuentes.cerrar(db, "leave", a.id, "rejected", nota or "Ampliación rechazada")
    evento(db, a, "ampliacion_rechazada", actor_id, motivo=nota, vuelve_a=anterior)
    texto = _resumen(a, a.absence_type) + (f" — {nota}" if nota else "")
    avisar(db, [a.user_id], "Ampliación rechazada", texto, a)
    libres = set()
    with cupos.seccion(db):
        filas = db.query(ReservaDeCupo, HuecoDeCupo).join(HuecoDeCupo, HuecoDeCupo.id == ReservaDeCupo.hueco_id) \
            .filter(ReservaDeCupo.absence_id == a.id, ReservaDeCupo.estado.in_(("ocupa", "espera")),
                    HuecoDeCupo.fecha > anterior).all()
        for res, h in filas:
            if res.estado == "ocupa":
                libres.add(h.id)
                h.ocupadas = max(0, (h.ocupadas or 0) - 1)
            res.estado = "liberada"
        db.commit()
    promover(db, libres)
    return a


# ── Lista de espera ──────────────────────────────────────────────────────────

def promover(db: Session, hueco_ids: Optional[set] = None, actor=None) -> list[str]:
    """Da la plaza liberada a quien espera, por orden de llegada: la primera
    petición que ya cabe ENTERA. Abre su flujo (o la aprueba si ya estaba
    aprobada) y avisa a quien diga el cupo."""
    if hueco_ids is not None and not hueco_ids:
        return []
    promovidas = []
    for absence_id in cupos.en_espera_en(db, hueco_ids):
        if not cupos.intentar_promover(db, absence_id):
            continue
        a = db.query(Absence).filter(Absence.id == absence_id).first()
        if a is None or a.status != AbsenceStatus.waitlisted:
            continue
        promovidas.append(a.id)
        _tras_promover(db, a, actor)
    return promovidas


def _tras_promover(db: Session, a: Absence, actor) -> None:
    from app.services.politicas import ejecutar_avisos
    ultimo = db.query(EventoDeAusencia).filter(EventoDeAusencia.absence_id == a.id, EventoDeAusencia.tipo == "en_espera") \
        .order_by(EventoDeAusencia.created_at.desc()).first()
    momento = (json.loads(ultimo.datos or "{}") if ultimo else {}).get("momento") or "solicitud"
    ev = evaluar(db, a)
    evento(db, a, "promovida", getattr(actor, "id", None), momento=momento)
    avisos = [{"destinatarios": c.get("avisar_al_promover") or [{"tipo": "solicitante"}],
               "canales": c.get("canales") or ["app"], "mensaje": "Ha quedado una plaza libre y es tuya",
               "politica": "Cupo"} for c in _cupos_en(ev, momento)]
    if avisos:
        ejecutar_avisos(db, {"avisar": avisos}, a.user_id, "absence", a.id, _resumen(a, a.absence_type),
                        a.organization_id)
    else:
        avisar(db, [a.user_id], "Tienes plaza", _resumen(a, a.absence_type), a)
    if momento == "aprobacion":
        a.status = AbsenceStatus.approved
        a.approved_at = _ahora()
        evento(db, a, "aprobada", None, nota="Plaza libre tras la aprobación")
        db.commit()
        return
    a.status = AbsenceStatus.pending
    db.commit()
    _abrir_flujo(db, a, ev)


def dar_plaza(db: Session, usuario, a: Absence) -> Absence:
    """Un responsable promueve a mano a quien espera (aunque el cupo esté lleno:
    queda marcado «por encima»)."""
    from app.models.ausencias import ReservaDeCupo
    if a.status != AbsenceStatus.waitlisted:
        raise ErrorDeDominio(400, "Esa ausencia no está en lista de espera")
    if not cupos.intentar_promover(db, a.id):
        with cupos.seccion(db):
            for r in db.query(ReservaDeCupo).filter(ReservaDeCupo.absence_id == a.id, ReservaDeCupo.estado == "espera"):
                r.estado, r.por_encima = "ocupa", True
            db.commit()
    evento(db, a, "plaza_manual", usuario.id)
    db.commit()
    _tras_promover(db, a, usuario)
    return a


def promover_pendientes(db: Session) -> list[str]:
    """La pasada diaria: por si una política subió el máximo de un cupo."""
    return promover(db, None)


def pasada_diaria(db: Session, org: Optional[str] = None) -> dict:
    """Lo que corre el worker cada día en cada empresa (`app.worker.ausencias_pasada_diaria`)."""
    from app.services.ausencias import bolsa, documentos
    return {"documentos": documentos.pasada(db), "promovidas": len(promover_pendientes(db)), "bolsa": bolsa.pasada(db)}
