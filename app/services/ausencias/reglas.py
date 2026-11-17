"""Lo que el motor de políticas sabe de una ausencia (contexto) y cómo resuelve un cupo.

`contexto(db, ausencia)` da el valor de cada campo del dominio `ausencias`
(`politicas/dominios/ausencias.py`), más:

- `_sujeto`: a quién aplica la política (persona, rol, departamento, equipo,
  grupos, país y ciudad de su sede —o de la oficina de su turno—);
- `_fecha`: el primer día (vigencias);
- `_ausencia`: lo que necesita un cupo: persona, equipo, departamento, rol,
  grupos y los días que cuentan con su turno, su sede y los minutos de su
  horario que ocupa (cupos por franja horaria).

Rev. 180: todo se mide sobre el HORARIO EFECTIVO de la persona
(`app/services/horario`): un día de vacaciones son las horas de su turno o
jornada ese día (no 8 fijas); una petición por horas ocupa su franja dentro de
ese horario y cuenta como la parte de día que es (2 h de un día de 8 h = 0,25
días). Sirve igual para una ausencia guardada que para una petición aún sin
guardar (vista previa, simulador): no escribe nada.
"""
from __future__ import annotations

import json
from collections import Counter, defaultdict
from datetime import date, datetime, time, timedelta, timezone
from types import SimpleNamespace
from typing import Optional

from sqlalchemy.orm import Session

from app.core import timeutil
from app.services.ausencias import cupos, saldos, turnos
from app.services.horario import tramos as tr


def _tipo(db: Session, a):
    from app.services.ausencias import catalogo
    t = getattr(a, "absence_type", None)
    if t is None and a.absence_type_id:
        t = catalogo.tipo(db, a.absence_type_id)
    if t is None and a.type:
        t = catalogo.tipo_por_clave(db, a.type)
    return t


def grupos_de(db: Session, user_id: str) -> list[str]:
    from app.models.billing_reports import ApprovalGroup
    salida = []
    for g in db.query(ApprovalGroup).all():
        try:
            if user_id in json.loads(g.member_ids or "[]"):
                salida.append(g.id)
        except ValueError:
            continue
    return salida


# ── Medir una petición sobre el horario ──────────────────────────────────────

def tramos_por_dia(a, dias: list[dict]) -> dict[date, tuple]:
    """Los tramos del horario que la ausencia ocupa cada día que cuenta."""
    from app.services.horario.efectivo import tramos_de_ausencia
    plan = {d["fecha"]: SimpleNamespace(tramos=tuple(d.get("tramos") or ())) for d in dias}
    return tramos_de_ausencia(a, plan)


def medir(db: Session, a, tipo, dias: list[dict]) -> tuple[float, float]:
    """(días equivalentes, cantidad en la unidad del tipo). Ver `medida`."""
    m = medida(db, a, tipo, dias)
    return m["dias"], m["cantidad"]


def medida(db: Session, a, tipo, dias: list[dict]) -> dict:
    """Cuánto es una petición sobre el horario de la persona.

    - `dias`: días equivalentes (cada día, la parte de su horario que ocupa:
      un día entero 1, medio día 0,5, dos horas de un turno de 8 h 0,25);
    - `horas`: horas de su horario que cubre (descontada la pausa en proporción);
    - `cantidad`: en la unidad del tipo (días, medios días u horas);
    - `por_dia`: {fecha: {horas, fraccion, tramos}}; `horas_max_dia`;
      `horas_fuera`: horas de la franja pedida que caen fuera de su horario.
    """
    ocupados = tramos_por_dia(a, dias)
    por_dia: dict = {}
    total_h = total_d = maximo = fuera = 0.0
    for d in dias:
        f = d["fecha"]
        bruto = tr.total_horas(d.get("tramos") or ())
        neto_dia = float(d.get("horas") if d.get("horas") is not None else bruto)
        quita = tr.total_horas(ocupados.get(f, ()))
        horas = round(quita * (neto_dia / bruto), 4) if bruto else 0.0
        fraccion = round(horas / neto_dia, 4) if neto_dia else 0.0
        por_dia[f] = {"horas": horas, "fraccion": fraccion, "tramos": ocupados.get(f, ())}
        total_h += horas
        total_d += fraccion
        maximo = max(maximo, horas)
        if a.start_time is not None and a.end_time is not None:
            pedida = tr.total_horas([tr.desde_texto(a.start_time, a.end_time)])
            fuera = max(fuera, round(pedida - quita, 4))
    unidad = getattr(tipo, "unidad", None) or "dias"
    if unidad == "horas" and a.hours and a.start_time is None and not dias:
        total_h = float(a.hours)
    cantidad = total_h if unidad == "horas" else (total_d * 2 if unidad == "medios_dias" else total_d)
    return {"dias": round(total_d, 4), "horas": round(total_h, 4), "cantidad": round(cantidad, 4),
            "por_dia": por_dia, "horas_max_dia": round(maximo, 4), "horas_fuera": round(fuera, 4)}


# ── Compañeros, cobertura, acumulados ────────────────────────────────────────

def _solapadas(db: Session, a, estados=None) -> list:
    """Ausencias de OTRAS personas que solapan con la petición."""
    from app.models.resources import Absence, AbsenceStatus
    estados = estados or [AbsenceStatus.approved, AbsenceStatus.pending]
    return db.query(Absence).filter(Absence.user_id != a.user_id, Absence.is_active.is_(True),
                                    Absence.status.in_(estados), Absence.start_date <= a.end_date,
                                    Absence.end_date >= a.start_date).all()


def _maximo_por_dia(a, otras: list, mismos: callable) -> int:
    """El máximo, en un mismo día de la petición, de personas ausentes que cumplen `mismos(ausencia, dia)`."""
    por_dia: Counter = Counter()
    vistos = set()
    for o in otras:
        for d in turnos.dias(max(o.start_date, a.start_date), min(o.end_date, a.end_date)):
            if (o.user_id, d) in vistos or not mismos(o, d):
                continue
            vistos.add((o.user_id, d))
            por_dia[d] += 1
    return max(por_dia.values()) if por_dia else 0


def _solapes(db: Session, a, u, mis_turnos: dict) -> dict:
    """Compañeros ausentes (aprobadas o pendientes) el peor día, por equipo, turno, rol, sede y departamento."""
    from app.models.user import User
    otras = _solapadas(db, a)
    if not otras or u is None:
        return {"companeros_ausentes": 0, "ausentes_mismo_turno": 0, "ausentes_mismo_rol": 0,
                "ausentes_misma_sede": 0, "ausentes_mismo_departamento": 0}
    ids = {o.user_id for o in otras}
    gente = {x.id: x for x in db.query(User).filter(User.id.in_(ids)).all()}
    plan = turnos.plan_crudo(db, a.start_date, a.end_date, ids) if any(mis_turnos.values()) else {}

    def igual(attr):
        mio = getattr(u, attr, None)
        return lambda o, d: bool(mio) and getattr(gente.get(o.user_id), attr, None) == mio

    def mismo_turno(o, d):
        mio = mis_turnos.get(d)
        return bool(mio) and plan.get((o.user_id, d), (None,))[0] == mio

    return {"companeros_ausentes": _maximo_por_dia(a, otras, igual("team")),
            "ausentes_mismo_turno": _maximo_por_dia(a, otras, mismo_turno),
            "ausentes_mismo_rol": _maximo_por_dia(a, otras, igual("role")),
            "ausentes_misma_sede": _maximo_por_dia(a, otras, igual("office_id")),
            "ausentes_mismo_departamento": _maximo_por_dia(a, otras, igual("department"))}


def _cobertura_restante(db: Session, a, dias: list[dict], m: dict) -> Optional[int]:
    """Lo que sobra (o falta, negativo) de cobertura mínima en el peor turno y
    día de la ausencia, contando ya con ella (por horas no quita a la persona del turno)."""
    con_turno = [d for d in dias if d.get("turno")]
    if not con_turno:
        return None
    desde, hasta = min(d["fecha"] for d in con_turno), max(d["fecha"] for d in con_turno)
    if (hasta - desde).days + 1 > turnos.MAX_DIAS_DE_CUADRANTE:
        return None
    simulados = [{"fecha": d["fecha"], "turno": d["turno"],
                  "parcial": (m["por_dia"].get(d["fecha"], {}).get("fraccion", 1) or 0) < 1 - 1e-9}
                 for d in con_turno]
    c = turnos.cobertura(db, desde, hasta, simular={"user_id": a.user_id, "dias": simulados})
    mios = {(d["fecha"].isoformat(), d["turno"]) for d in con_turno}
    valores = [x["con_esta"] - x["requeridas"] for x in c["celdas"] if (x["fecha"], x["turno_id"]) in mios]
    return min(valores) if valores else None


def _acumulados(db: Session, a, tipo, m: dict) -> dict:
    """Lo pedido del mismo tipo en el mes y el año del primer día, CONTANDO esta petición."""
    from app.models.resources import Absence, AbsenceStatus
    anio0 = date(a.start_date.year, 1, 1)
    q = db.query(Absence).filter(Absence.user_id == a.user_id, Absence.is_active.is_(True),
                                 Absence.status.in_([AbsenceStatus.approved, AbsenceStatus.pending,
                                                     AbsenceStatus.waitlisted]),
                                 Absence.start_date >= anio0, Absence.start_date < date(anio0.year + 1, 1, 1))
    if tipo is not None and getattr(tipo, "id", None):
        q = q.filter(Absence.absence_type_id == tipo.id)
    else:
        q = q.filter(Absence.type == a.type)
    if a.id:
        q = q.filter(Absence.id != a.id)
    h_mes = d_mes = h_anio = d_anio = 0.0
    n_mes = n_anio = 0
    for o in q.all():
        h = float(o.scheduled_hours if o.scheduled_hours is not None else (o.hours or 0))
        d = float(o.working_days or 0)
        h_anio, d_anio, n_anio = h_anio + h, d_anio + d, n_anio + 1
        if o.start_date.month == a.start_date.month:
            h_mes, d_mes, n_mes = h_mes + h, d_mes + d, n_mes + 1
    return {"horas_en_mes": round(h_mes + m["horas"], 2), "dias_en_mes": round(d_mes + m["dias"], 2),
            "horas_en_anio": round(h_anio + m["horas"], 2), "dias_en_anio": round(d_anio + m["dias"], 2),
            "peticiones_en_mes": n_mes + 1, "peticiones_en_anio": n_anio + 1}


def _tipos_alrededor(db: Session, a) -> dict:
    """Tipos (claves) de las OTRAS ausencias de la persona: que solapan, que van
    pegadas (el día laborable anterior o siguiente) y las del año."""
    from app.models.resources import Absence, AbsenceStatus
    from app.services.horario import efectivo as hor
    vivas = [AbsenceStatus.approved, AbsenceStatus.pending, AbsenceStatus.waitlisted]
    q = db.query(Absence).filter(Absence.user_id == a.user_id, Absence.is_active.is_(True),
                                 Absence.status.in_(vivas),
                                 Absence.start_date <= date(a.start_date.year, 12, 31),
                                 Absence.end_date >= date(a.start_date.year, 1, 1) - timedelta(days=15))
    if a.id:
        q = q.filter(Absence.id != a.id)
    otras = q.all()
    plan = hor.horario(db, a.user_id, a.start_date - timedelta(days=15), a.end_date + timedelta(days=15),
                       estados_ausencia=None)
    antes = next((d for d in sorted(plan, reverse=True) if d < a.start_date and plan[d].laborable),
                 a.start_date - timedelta(days=1))
    despues = next((d for d in sorted(plan) if d > a.end_date and plan[d].laborable), a.end_date + timedelta(days=1))
    sol, cont, anio = set(), set(), set()
    for o in otras:
        if o.start_date.year == a.start_date.year or o.end_date.year == a.start_date.year:
            anio.add(o.type)
        if o.start_date <= a.end_date and o.end_date >= a.start_date:
            sol.add(o.type)
        elif antes <= o.end_date < a.start_date or a.end_date < o.start_date <= despues:
            cont.add(o.type)
    return {"tipos_solapados": sorted(sol), "tipos_contiguos": sorted(cont), "tipos_en_el_anio": sorted(anio)}


def _inicio_dt(a, dias: list[dict], m: dict) -> datetime:
    """Momento en que empieza la ausencia (para el preaviso en horas)."""
    primero = dias[0]["fecha"] if dias else a.start_date
    tramos = m["por_dia"].get(primero, {}).get("tramos") or ()
    minutos = tramos[0].inicio if tramos else (tr.minutos(a.start_time) if a.start_time else 0)
    return datetime.combine(primero, time(0, 0), tzinfo=timezone.utc) + timedelta(minutes=minutos)


def _meses_entre(a: date, b: date) -> int:
    return (b.year - a.year) * 12 + (b.month - a.month) - (1 if b.day < a.day else 0)


def contexto(db: Session, a) -> dict:
    from app.models.advanced_config import Office
    from app.models.user import User
    u = db.query(User).filter(User.id == a.user_id).first()
    tipo = _tipo(db, a)
    dias = turnos.dias_que_cuentan(db, a.user_id, a.start_date, a.end_date, a.shift_id)
    m = medida(db, a, tipo, dias)
    rol = str(getattr(getattr(u, "role", None), "value", getattr(u, "role", None)) or "") or None
    turno = a.shift_id or (Counter(d["turno"] for d in dias if d.get("turno")).most_common(1) or [(None, 0)])[0][0]
    oficina = next((d["office_id"] for d in dias if d.get("office_id")), None) or getattr(u, "office_id", None)
    o = db.query(Office).filter(Office.id == oficina).first() if oficina else None
    pais = ((o.country or "").upper()[:2] or None) if o is not None else None
    ciudad = (o.city or None) if o is not None else None
    pedido_dt = a.requested_at if isinstance(a.requested_at, datetime) else datetime.now(timezone.utc)
    if pedido_dt.tzinfo is None:
        pedido_dt = pedido_dt.replace(tzinfo=timezone.utc)
    pedido = a.requested_at.date() if isinstance(a.requested_at, datetime) else timeutil.today()

    saldo = saldos.de_tipo(db, a.user_id, a.start_date, tipo, excluir=a.id) if tipo is not None else None
    restante = restante_h = disponible = None
    if saldo is not None:
        consumo = m["horas"] if saldo["unidad"] == "horas" else m["dias"]
        restante = round(saldo["restante"] - consumo, 2)
        media = saldo.get("media_diaria_horas") or 0
        restante_h = restante if saldo["unidad"] == "horas" else round(restante * media, 2)
        disponible = saldo["restante"]
    documentos = 0
    if a.id:
        from app.models.ausencias import DocumentoDeAusencia
        documentos = db.query(DocumentoDeAusencia.id).filter(DocumentoDeAusencia.absence_id == a.id,
                                                            DocumentoDeAusencia.estado == "vigente").count()
    grupos = grupos_de(db, a.user_id)
    mis_turnos = {d["fecha"]: d.get("turno") for d in dias}
    solapes = _solapes(db, a, u, mis_turnos)
    alta = getattr(u, "hire_date", None)
    franjas_min = defaultdict(list)
    for f, x in m["por_dia"].items():
        franjas_min[f] = [[t.inicio, t.fin] for t in x["tramos"]]
    por_horas = a.start_time is not None or (a.modo == "horas")
    return {
        "tipo": getattr(tipo, "clave", a.type), "unidad": getattr(tipo, "unidad", "dias"),
        "modo": "horas" if por_horas else "dias",
        "cantidad": m["cantidad"], "dias_laborables": m["dias"], "horas": m["horas"],
        "horas_max_dia": m["horas_max_dia"], "horas_fuera_de_horario": m["horas_fuera"],
        "hora_inicio": a.start_time.strftime("%H:%M") if a.start_time else None,
        "hora_fin": a.end_time.strftime("%H:%M") if a.end_time else None,
        "dia_completo": all(x["fraccion"] >= 1 - 1e-9 for x in m["por_dia"].values()) if m["por_dia"] else False,
        "dias_consecutivos": (a.end_date - a.start_date).days + 1,
        "fecha_inicio": a.start_date, "fecha_fin": a.end_date,
        "periodo": {"desde": a.start_date, "hasta": a.end_date},
        "turno": turno, "ubicacion": oficina, "sede": getattr(u, "office_id", None),
        "equipo": getattr(u, "team", None), "departamento": getattr(u, "department", None), "rol": rol,
        "persona": a.user_id, "grupos": grupos, "tipo_de_contrato": getattr(u, "employment_type", None),
        "antiguedad_meses": _meses_entre(alta, a.start_date) if alta else None,
        "sustituto": a.substitute_id, "saldo_restante": restante, "saldo_restante_horas": restante_h,
        "saldo_disponible": disponible, "retribuido": bool(getattr(tipo, "retribuido", True)),
        "_saldo_unidad": (saldo or {}).get("unidad"),
        "antelacion_dias": (a.start_date - pedido).days,
        "antelacion_horas": round((_inicio_dt(a, dias, m) - pedido_dt).total_seconds() / 3600, 2),
        **solapes,
        "cobertura_restante": _cobertura_restante(db, a, dias, m),
        **_acumulados(db, a, tipo, m),
        **_tipos_alrededor(db, a),
        "datos_especiales": bool(getattr(tipo, "datos_especiales", False)), "motivo": a.reason,
        "documentos": documentos,
        "_sujeto": {"usuario_id": a.user_id, "rol": rol, "departamento": getattr(u, "department", None),
                    "equipo": getattr(u, "team", None), "pais": pais, "ciudad": ciudad, "grupos": grupos},
        "_fecha": a.start_date,
        "_ausencia": {"id": a.id, "usuario_id": a.user_id, "equipo": getattr(u, "team", None),
                      "departamento": getattr(u, "department", None), "rol": rol, "grupos": grupos,
                      "dias": [{"fecha": d["fecha"], "turno": d.get("turno"), "office_id": d.get("office_id"),
                                "horas": m["por_dia"].get(d["fecha"], {}).get("horas", 0.0),
                                "minutos": franjas_min.get(d["fecha"], [])}
                               for d in dias if m["por_dia"].get(d["fecha"], {}).get("horas", 0) > 0]},
    }


def resolver_cupo(db: Session, ctx: dict, cupo: dict) -> tuple[list, dict]:
    """Qué resultados del motor salen de un cupo AHORA, sin reservar nada.

    Momento «solicitud»: si alguna plaza está llena, los de `si_lleno` (lista
    de espera, bloqueo, aviso…). Momento «aprobación»: la plaza se decide al
    aprobar; si ahora está llena se avisa a quien aprueba. El detalle (plazas,
    ocupadas, en espera, puesto estimado) va a la explicación.
    """
    aus = ctx.get("_ausencia") or {}
    huecos = cupos.huecos_de(cupo, aus)
    maximo = int(cupo.get("maximo") or 0)
    estado = cupos.ocupacion(db, cupo.get("clave") or "", huecos, excluir=aus.get("id")) if cupo.get("clave") else []
    for h in estado:
        h["libres"] = max(0, maximo - h["ocupadas"])
    llenos = [h for h in estado if h["libres"] <= 0]
    detalle = {"clave": cupo.get("clave"), "maximo": maximo, "momento": cupo.get("momento") or "solicitud",
               "agrupar_por": cupo.get("agrupar_por") or "empresa", "franja_minutos": int(cupo.get("franja_minutos") or 0),
               "huecos": estado, "lleno": bool(llenos),
               "posicion_estimada": (max(h["espera"] for h in llenos) + 1) if llenos else None,
               "aplica": bool(huecos)}
    if not llenos:
        return [], detalle
    if (cupo.get("momento") or "solicitud") == "aprobacion":
        return [{"tipo": "warn", "mensaje": f"Cupo lleno ahora ({len(llenos)} día/turno): se decide al aprobar"}], detalle
    return list(cupo.get("si_lleno") or []), detalle


def resolver_saldo_negativo(ctx: dict, r: dict) -> dict:
    """Detalle de un `saldo_negativo` para la explicación (lo aplica `solicitudes`)."""
    hasta = float(r.get("hasta") or 0)
    restante = ctx.get("saldo_restante")
    return {"permite_hasta": -hasta, "saldo_restante": restante,
            "cubre": restante is None or restante >= -hasta - 1e-9}


def redondear(horas: float, minutos: int, modo: str) -> float:
    """Redondea unas horas a múltiplos de `minutos` (arriba, abajo o al más cercano)."""
    import math
    if minutos <= 0:
        return horas
    pasos = horas * 60 / minutos
    n = math.ceil(pasos - 1e-9) if modo == "arriba" else (math.floor(pasos + 1e-9) if modo == "abajo" else round(pasos))
    return round(n * minutos / 60, 4)
