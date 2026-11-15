"""Lo que el motor de políticas sabe de una ausencia (contexto) y cómo resuelve un cupo.

`contexto(db, ausencia)` da el valor de cada campo del dominio `ausencias`
(`politicas/dominios/ausencias.py`), más:

- `_sujeto`: a quién aplica la política (persona, rol, departamento, equipo,
  país de la oficina de su turno);
- `_fecha`: el primer día (vigencias);
- `_ausencia`: lo que necesita un cupo: persona, equipo, departamento, rol,
  grupos y los días que cuentan con su turno y su oficina.

Sirve igual para una ausencia guardada que para una petición aún sin guardar
(la vista previa): no escribe nada.
"""
from __future__ import annotations

import json
from collections import Counter
from datetime import datetime
from typing import Optional

from sqlalchemy.orm import Session

from app.core import timeutil
from app.services.ausencias import cupos, saldos, turnos


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


def medir(db: Session, a, tipo, dias: list[dict]) -> tuple[float, float]:
    """(días laborables, cantidad en la unidad del tipo).

    Un medio día al empezar o al acabar resta 0,5. En horas: las indicadas o,
    sin ellas, la duración de los turnos de esos días (o la jornada de la
    persona: horas semanales ÷ 5).
    """
    n = float(len(dias))
    if n:
        medios = (0.5 if a.half_day_start else 0) + (0.5 if a.half_day_end else 0)
        if a.start_date == a.end_date:
            medios = 0.5 if (a.half_day_start or a.half_day_end) else 0
        n = max(0.5, n - medios)
    unidad = getattr(tipo, "unidad", None) or "dias"
    if unidad == "medios_dias":
        return n, n * 2
    if unidad == "horas":
        if a.hours:
            return n, float(a.hours)
        todos = {t.id: t for t in turnos.turnos(db, incluir_inactivos=True)}
        con_turno = [todos[d["turno"]] for d in dias if d.get("turno") in todos]
        if con_turno:
            return n, round(sum(turnos.duracion_horas(t) for t in con_turno), 2)
        from app.models.user import User
        semana = db.query(User.weekly_capacity_hours).filter(User.id == a.user_id).scalar() or 0
        return n, round(n * float(semana) / 5, 2)
    return n, n


def _companeros(db: Session, a, u) -> int:
    """El máximo, en un mismo día, de compañeros de equipo ausentes (aprobadas o pendientes)."""
    from app.models.resources import Absence, AbsenceStatus
    from app.models.user import User
    if not getattr(u, "team", None):
        return 0
    filas = db.query(Absence.start_date, Absence.end_date).join(User, User.id == Absence.user_id).filter(
        User.team == u.team, Absence.user_id != a.user_id, Absence.is_active.is_(True),
        Absence.status.in_([AbsenceStatus.approved, AbsenceStatus.pending]),
        Absence.start_date <= a.end_date, Absence.end_date >= a.start_date).all()
    por_dia: Counter = Counter()
    for ini, fin in filas:
        for d in turnos.dias(max(ini, a.start_date), min(fin, a.end_date)):
            por_dia[d] += 1
    return max(por_dia.values()) if por_dia else 0


def _cobertura_restante(db: Session, a, dias: list[dict]) -> Optional[int]:
    """Lo que sobra (o falta, negativo) de cobertura mínima en el peor turno y
    día de la ausencia, contando ya con ella."""
    con_turno = [d for d in dias if d.get("turno")]
    if not con_turno:
        return None
    desde, hasta = min(d["fecha"] for d in con_turno), max(d["fecha"] for d in con_turno)
    if (hasta - desde).days + 1 > turnos.MAX_DIAS_DE_CUADRANTE:
        return None
    c = turnos.cobertura(db, desde, hasta, simular={"user_id": a.user_id, "dias": con_turno})
    mios = {(d["fecha"].isoformat(), d["turno"]) for d in con_turno}
    valores = [x["con_esta"] - x["requeridas"] for x in c["celdas"] if (x["fecha"], x["turno_id"]) in mios]
    return min(valores) if valores else None


def contexto(db: Session, a) -> dict:
    from app.models.advanced_config import Office
    from app.models.user import User
    u = db.query(User).filter(User.id == a.user_id).first()
    tipo = _tipo(db, a)
    dias = turnos.dias_que_cuentan(db, a.user_id, a.start_date, a.end_date, a.shift_id)
    laborables, cantidad = medir(db, a, tipo, dias)
    rol = str(getattr(getattr(u, "role", None), "value", getattr(u, "role", None)) or "") or None
    turno = a.shift_id or (Counter(d["turno"] for d in dias if d.get("turno")).most_common(1) or [(None, 0)])[0][0]
    oficina = next((d["office_id"] for d in dias if d.get("office_id")), None)
    o = db.query(Office).filter(Office.id == oficina).first() if oficina else None
    pais = ((o.country or "").upper()[:2] or None) if o is not None else None
    pedido = a.requested_at.date() if isinstance(a.requested_at, datetime) else timeutil.today()
    saldo = saldos.de_tipo(db, a.user_id, a.start_date.year, tipo, excluir=a.id) if tipo is not None else None
    restante = None if saldo is None else round(saldo["restante"] - (laborables if tipo.saldo == "vacaciones" else cantidad), 2)
    documentos = 0
    if a.id:
        from app.models.ausencias import DocumentoDeAusencia
        documentos = db.query(DocumentoDeAusencia.id).filter(DocumentoDeAusencia.absence_id == a.id,
                                                            DocumentoDeAusencia.estado == "vigente").count()
    grupos = grupos_de(db, a.user_id)
    return {
        "tipo": getattr(tipo, "clave", a.type), "unidad": getattr(tipo, "unidad", "dias"),
        "cantidad": cantidad, "dias_laborables": laborables, "dias_consecutivos": (a.end_date - a.start_date).days + 1,
        "fecha_inicio": a.start_date, "fecha_fin": a.end_date,
        "periodo": {"desde": a.start_date, "hasta": a.end_date},
        "turno": turno, "ubicacion": oficina, "equipo": getattr(u, "team", None),
        "departamento": getattr(u, "department", None), "rol": rol, "persona": a.user_id,
        "sustituto": a.substitute_id, "saldo_restante": restante,
        "antelacion_dias": (a.start_date - pedido).days, "companeros_ausentes": _companeros(db, a, u) if u else 0,
        "cobertura_restante": _cobertura_restante(db, a, dias),
        "datos_especiales": bool(getattr(tipo, "datos_especiales", False)), "motivo": a.reason,
        "documentos": documentos,
        "_sujeto": {"usuario_id": a.user_id, "rol": rol, "departamento": getattr(u, "department", None),
                    "equipo": getattr(u, "team", None), "pais": pais, "ciudad": None},
        "_fecha": a.start_date,
        "_ausencia": {"id": a.id, "usuario_id": a.user_id, "equipo": getattr(u, "team", None),
                      "departamento": getattr(u, "department", None), "rol": rol, "grupos": grupos,
                      "dias": [{"fecha": d["fecha"], "turno": d.get("turno"), "office_id": d.get("office_id")}
                               for d in dias]},
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
               "agrupar_por": cupo.get("agrupar_por") or "empresa", "huecos": estado, "lleno": bool(llenos),
               "posicion_estimada": (max(h["espera"] for h in llenos) + 1) if llenos else None,
               "aplica": bool(huecos)}
    if not llenos:
        return [], detalle
    if (cupo.get("momento") or "solicitud") == "aprobacion":
        return [{"tipo": "warn", "mensaje": f"Cupo lleno ahora ({len(llenos)} día/turno): se decide al aprobar"}], detalle
    return list(cupo.get("si_lleno") or []), detalle
