"""El día de una persona frente a sus horas extra (18-11-2026).

Todo sale del horario efectivo (`app/services/horario/efectivo.py`, la única
fuente de verdad: cuadrante > rotación > jornada > empresa, menos festivos de
empresa y sede, fuera de contrato y ausencias aprobadas). Aquí no se inventa
ningún horario.

- Clase de día: `festivo` (festivo no trabajado de su empresa/sede),
  `no_laborable` (sin horario: fin de semana, día libre del cuadrante, fuera de
  contrato) o `laborable`.
- Exceso imputado de un día = imputado − horas de su horario ese día (las
  disponibles: un festivo o una ausencia aprobada dan 0). Las horas «sin
  autorizar» son el exceso menos lo autorizado (peticiones APROBADAS de ese
  día); si no pasan de la tolerancia de la empresa, cuentan como 0.
- Acumulados: horas de peticiones vivas (pendientes y aprobadas; de una
  aprobada, las autorizadas) en el día, la semana (lunes a domingo), el mes y
  el año naturales, y en el año solo las que se pagan (el máximo legal español
  de 80 h/año no cuenta las compensadas con descanso).
- Descanso: horas entre el final del trabajo del día anterior y el inicio del
  de este, y entre el final de este (con las horas extra) y el inicio del
  siguiente. Sin franja, las horas extra se suponen al final de su horario.
- Días seguidos: días contiguos con trabajo (horario, imputación o horas extra
  vivas) alrededor de la fecha, contando la fecha.
- Presupuesto restante: el menor, entre los presupuestos activos que le
  aplican (empresa, su departamento, su equipo, el proyecto), de horas menos
  lo consumido (peticiones vivas del periodo) menos esta petición.
"""
from __future__ import annotations

from collections import defaultdict
from datetime import date, timedelta
from typing import Iterable, Optional

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models.horas_extra import PeticionDeHorasExtra
from app.services.horario import tramos as tr

VIVOS = ("pendiente", "aprobada")
EPS = 1e-6


def horas_vivas(p: PeticionDeHorasExtra) -> float:
    """Lo que cuenta de una petición: las autorizadas si está aprobada, si no las pedidas."""
    if p.estado == "aprobada" and p.horas_autorizadas is not None:
        return float(p.horas_autorizadas)
    return float(p.horas or 0)


def horas_ponderadas(p) -> float:
    return round(horas_vivas(p) * float(p.factor or 1.0), 2)


def clase_de(dia) -> str:
    if dia is not None and dia.es_festivo_no_trabajado:
        return "festivo"
    if dia is None or dia.fuera_de_contrato or dia.horas_teoricas <= 0:
        return "no_laborable"
    return "laborable"


def dia(db: Session, user_id: str, fecha: date):
    from app.services.horario import efectivo as hor
    return hor.dia(db, user_id, fecha)


def franja_de(p) -> Optional[tr.Tramo]:
    if p.hora_inicio is None or p.hora_fin is None:
        return None
    return tr.desde_texto(p.hora_inicio, p.hora_fin)


def medir(db: Session, p) -> dict:
    """Clase de día, horario de ese día y cuánto de la franja cae fuera de él."""
    d = dia(db, p.user_id, p.fecha)
    libres = d.libres if d is not None else ()
    f = franja_de(p)
    dentro = fuera = 0.0
    if f is not None:
        dentro = tr.total_horas(tr.interseccion([f], libres))
        fuera = round(f.horas - dentro, 4)
    return {"dia": d, "clase": clase_de(d), "horario_horas": round(d.horas, 4) if d is not None else 0.0,
            "tramos": tr.a_lista(libres), "festivo": d.festivo if d is not None else None,
            "franja_horas": round(f.horas, 4) if f is not None else None, "horas_dentro": round(dentro, 4),
            "horas_fuera": fuera if f is not None else None}


# ── Imputado frente a horario ────────────────────────────────────────────────

def imputado(db: Session, user_id: str, fecha: date, excluir_imputacion: Optional[str] = None) -> float:
    from app.models.imputation import Imputation
    q = db.query(func.sum(Imputation.hours)).filter(Imputation.user_id == user_id, Imputation.date == fecha,
                                                    Imputation.is_active.is_(True))
    if excluir_imputacion:
        q = q.filter(Imputation.id != excluir_imputacion)
    return float(q.scalar() or 0.0)


def autorizadas(db: Session, user_id: str, fecha: date, estados: tuple = ("aprobada",),
                origen: Optional[str] = None) -> float:
    q = db.query(PeticionDeHorasExtra).filter(PeticionDeHorasExtra.user_id == user_id,
                                              PeticionDeHorasExtra.fecha == fecha,
                                              PeticionDeHorasExtra.estado.in_(estados))
    if origen:
        q = q.filter(PeticionDeHorasExtra.origen == origen)
    return round(sum(horas_vivas(p) for p in q.all()), 4)


def sin_autorizar(imputadas: float, horario: float, aprobadas: float, tolerancia_min: int) -> float:
    """Horas imputadas fuera de horario sin autorización (puro)."""
    resto = imputadas - horario - aprobadas
    if resto <= (tolerancia_min or 0) / 60 + EPS:
        return 0.0
    return round(resto, 4)


def estado_del_dia(db: Session, user_id: str, fecha: date, tolerancia_min: int, imputadas: Optional[float] = None,
                   d=None) -> dict:
    d = d if d is not None else dia(db, user_id, fecha)
    horario = d.horas if d is not None else 0.0
    imp = imputado(db, user_id, fecha) if imputadas is None else imputadas
    aprob = autorizadas(db, user_id, fecha)
    pend = autorizadas(db, user_id, fecha, estados=("pendiente",))
    return {"horario": round(horario, 2), "imputado": round(imp, 2), "autorizadas": round(aprob, 2),
            "pendientes": round(pend, 2), "exceso_real": round(max(0.0, imp - horario), 2),
            "sin_autorizar": round(sin_autorizar(imp, horario, aprob, tolerancia_min), 2)}


# ── Acumulados, descanso, días seguidos ──────────────────────────────────────

def _periodos(fecha: date) -> dict:
    lunes = fecha - timedelta(days=fecha.weekday())
    mes0 = fecha.replace(day=1)
    mes1 = (mes0 + timedelta(days=32)).replace(day=1) - timedelta(days=1)
    return {"dia": (fecha, fecha), "semana": (lunes, lunes + timedelta(days=6)), "mes": (mes0, mes1),
            "anio": (date(fecha.year, 1, 1), date(fecha.year, 12, 31))}


def acumulados(db: Session, user_id: str, fecha: date, horas_esta: float, compensacion: str,
               excluir_id: Optional[str] = None) -> dict:
    per = _periodos(fecha)
    q = db.query(PeticionDeHorasExtra).filter(PeticionDeHorasExtra.user_id == user_id,
                                              PeticionDeHorasExtra.estado.in_(VIVOS),
                                              PeticionDeHorasExtra.fecha >= per["anio"][0],
                                              PeticionDeHorasExtra.fecha <= per["anio"][1])
    if excluir_id:
        q = q.filter(PeticionDeHorasExtra.id != excluir_id)
    otras = q.all()
    salida = {}
    for k, (a, b) in per.items():
        salida[k] = round(sum(horas_vivas(p) for p in otras if a <= p.fecha <= b) + horas_esta, 2)
    salida["anio_pago"] = round(sum(horas_vivas(p) for p in otras if p.compensacion == "pago")
                                + (horas_esta if compensacion == "pago" else 0.0), 2)
    return salida


def _fin_y_inicio(d) -> tuple[Optional[int], Optional[int]]:
    if d is None or not d.libres:
        return None, None
    return min(t.inicio for t in d.libres), max(t.fin for t in d.libres)


def descanso(db: Session, user_id: str, fecha: date, franja: Optional[tr.Tramo], horas: float) -> Optional[float]:
    """Menor descanso (horas) alrededor del día con las horas extra; None si no se puede medir."""
    from app.services.horario import efectivo as hor
    dias = (hor.horarios(db, [user_id], fecha - timedelta(days=1), fecha + timedelta(days=1)) or {}).get(user_id, {})
    ini, fin = _fin_y_inicio(dias.get(fecha))
    if franja is not None:
        ini = franja.inicio if ini is None else min(ini, franja.inicio)
        fin = franja.fin if fin is None else max(fin, franja.fin)
    elif fin is not None:
        fin = fin + int(round(horas * 60))
    if ini is None or fin is None:
        return None
    candidatos = []
    _, fin_prev = _fin_y_inicio(dias.get(fecha - timedelta(days=1)))
    ini_sig, _ = _fin_y_inicio(dias.get(fecha + timedelta(days=1)))
    # M24 (auditoría 22-11-2026): el descanso se mide contra lo que de verdad se
    # trabaja: las horas extra aprobadas o pendientes del día anterior y del
    # siguiente amplían su jornada (antes solo el horario teórico, y una tarde
    # larga de ayer no recortaba el descanso de hoy).
    for p in db.query(PeticionDeHorasExtra).filter(
            PeticionDeHorasExtra.user_id == user_id, PeticionDeHorasExtra.estado.in_(VIVOS),
            PeticionDeHorasExtra.fecha.in_((fecha - timedelta(days=1), fecha + timedelta(days=1)))).all():
        f = franja_de(p)
        if f is None:
            continue
        if p.fecha < fecha:
            fin_prev = f.fin if fin_prev is None else max(fin_prev, f.fin)
        else:
            ini_sig = f.inicio if ini_sig is None else min(ini_sig, f.inicio)
    if fin_prev is not None:
        candidatos.append(ini - (fin_prev - tr.DIA))
    if ini_sig is not None:
        candidatos.append(ini_sig + tr.DIA - fin)
    return round(min(candidatos) / 60, 2) if candidatos else None


def dias_seguidos(db: Session, user_id: str, fecha: date, ventana: int = 21) -> int:
    from app.models.imputation import Imputation
    from app.services.horario import efectivo as hor
    desde, hasta = fecha - timedelta(days=ventana), fecha + timedelta(days=ventana)
    plan = (hor.horarios(db, [user_id], desde, hasta) or {}).get(user_id, {})
    trabaja = {d for d, x in plan.items() if x.horas > 0}
    trabaja |= {d for (d,) in db.query(Imputation.date).filter(
        Imputation.user_id == user_id, Imputation.date >= desde, Imputation.date <= hasta,
        Imputation.is_active.is_(True), Imputation.hours > 0).distinct()}
    trabaja |= {d for (d,) in db.query(PeticionDeHorasExtra.fecha).filter(
        PeticionDeHorasExtra.user_id == user_id, PeticionDeHorasExtra.estado.in_(VIVOS),
        PeticionDeHorasExtra.fecha >= desde, PeticionDeHorasExtra.fecha <= hasta).distinct()}
    trabaja.add(fecha)
    n, d = 1, fecha - timedelta(days=1)
    while d in trabaja and d >= desde:
        n, d = n + 1, d - timedelta(days=1)
    d = fecha + timedelta(days=1)
    while d in trabaja and d <= hasta:
        n, d = n + 1, d + timedelta(days=1)
    return n


# ── Presupuestos ─────────────────────────────────────────────────────────────

def _rango_de(p, fecha: date) -> tuple[date, date]:
    per = _periodos(fecha)
    return per["mes"] if p.periodo == "mes" else per["anio"]


def aplica(p, usuario, project_id: Optional[str]) -> bool:
    if p.ambito == "empresa":
        return True
    if p.ambito == "departamento":
        return bool(usuario is not None and getattr(usuario, "department", None) == p.valor)
    if p.ambito == "equipo":
        return bool(usuario is not None and getattr(usuario, "team", None) == p.valor)
    return bool(project_id and project_id == p.valor)


def consumo_de(db: Session, p, fecha: date, excluir_id: Optional[str] = None) -> float:
    from app.models.user import User
    a, b = _rango_de(p, fecha)
    q = db.query(PeticionDeHorasExtra).filter(PeticionDeHorasExtra.estado.in_(VIVOS),
                                              PeticionDeHorasExtra.fecha >= a, PeticionDeHorasExtra.fecha <= b)
    if excluir_id:
        q = q.filter(PeticionDeHorasExtra.id != excluir_id)
    if p.ambito == "proyecto":
        q = q.filter(PeticionDeHorasExtra.project_id == p.valor)
    elif p.ambito in ("departamento", "equipo"):
        col = User.department if p.ambito == "departamento" else User.team
        q = q.join(User, User.id == PeticionDeHorasExtra.user_id).filter(col == p.valor)
    return round(sum(horas_vivas(x) for x in q.all()), 4)


def presupuesto_restante(db: Session, usuario, fecha: date, project_id: Optional[str], horas_esta: float,
                         excluir_id: Optional[str] = None) -> tuple[Optional[float], list]:
    from app.services.horas_extra import config
    detalle = []
    for p in config.presupuestos(db, solo_activos=True):
        if p.anio is not None and p.anio != fecha.year:
            continue
        if not aplica(p, usuario, project_id):
            continue
        consumido = consumo_de(db, p, fecha, excluir_id)
        detalle.append({"id": p.id, "ambito": p.ambito, "valor": p.valor, "horas": p.horas,
                        "consumidas": round(consumido, 2), "restantes": round(p.horas - consumido - horas_esta, 2)})
    if not detalle:
        return None, []
    return min(d["restantes"] for d in detalle), detalle


# ── Varios días a la vez (listados, resumen, control) ─────────────────────────

def excesos(db: Session, desde: date, hasta: date, user_ids: Optional[Iterable[str]] = None,
            tolerancia_min: int = 0) -> list[dict]:
    """Días con imputación por encima del horario en [desde, hasta]."""
    from app.models.imputation import Imputation
    from app.services.horario import efectivo as hor
    q = db.query(Imputation.user_id, Imputation.date, func.sum(Imputation.hours)).filter(
        Imputation.date >= desde, Imputation.date <= hasta, Imputation.is_active.is_(True))
    ids = set(user_ids) if user_ids is not None else None
    if ids is not None:
        if not ids:
            return []
        q = q.filter(Imputation.user_id.in_(ids))
    imput: dict = defaultdict(dict)
    for uid, d, h in q.group_by(Imputation.user_id, Imputation.date).all():
        imput[uid][d] = float(h or 0)
    if not imput:
        return []
    planes = hor.horarios(db, list(imput), desde, hasta)
    pets: dict = defaultdict(list)
    for p in db.query(PeticionDeHorasExtra).filter(PeticionDeHorasExtra.user_id.in_(list(imput)),
                                                   PeticionDeHorasExtra.fecha >= desde,
                                                   PeticionDeHorasExtra.fecha <= hasta,
                                                   PeticionDeHorasExtra.estado.in_(VIVOS)).all():
        pets[(p.user_id, p.fecha)].append(p)
    salida = []
    for uid, por_dia in imput.items():
        for d, h in por_dia.items():
            x = (planes.get(uid) or {}).get(d)
            horario = x.horas if x is not None else 0.0
            if h <= horario + EPS:
                continue
            lista = pets.get((uid, d), [])
            aprob = sum(horas_vivas(p) for p in lista if p.estado == "aprobada")
            pend = sum(horas_vivas(p) for p in lista if p.estado == "pendiente")
            posterior = next((p.id for p in lista if p.origen == "posterior" and p.estado == "pendiente"), None)
            salida.append({"user_id": uid, "fecha": d, "horario": round(horario, 2), "imputado": round(h, 2),
                           "clase": clase_de(x), "autorizadas": round(aprob, 2), "pendientes": round(pend, 2),
                           "exceso_real": round(h - horario, 2),
                           "sin_autorizar": round(sin_autorizar(h, horario, aprob, tolerancia_min), 2),
                           "peticion_id": posterior or (lista[0].id if lista else None)})
    return sorted(salida, key=lambda r: (r["fecha"], r["user_id"]))
