"""Bolsa de horas: el exceso imputado sobre el horario se convierte en horas libres.

Rev. 180. Un tipo de ausencia con `saldo = "bolsa"` (p. ej. «Compensación de
horas extra») tiene una bolsa por persona que se alimenta así, día a día:

    exceso = horas imputadas ese día − horas de su horario efectivo ese día
             (turno o jornada, sin festivos ni ausencias: un festivo o un día
             libre tienen 0 horas de horario, así que todo lo imputado es exceso)

y, con las reglas del tipo (`TipoDeAusencia.bolsa`, editables en la pantalla):

- `umbral_minutos`: el exceso solo cuenta a partir de estos minutos (y solo lo
  que pasa de ellos);
- `factor` (día de trabajo), `factor_festivo` (festivo de su sede o de la
  empresa) y `factor_no_laborable` (día libre o fin de semana): cuántas horas
  de bolsa da cada hora de exceso;
- `tope_diario`: como mucho tantas horas de bolsa por día;
- `tope_periodo`: como mucho tantas horas en el año natural;
- `solo_aprobadas`: solo cuentan las imputaciones aprobadas;
- `solo_horas_extra` (18-11-2026): solo genera bolsa el exceso cubierto por
  horas extra APROBADAS con compensación «bolsa» ese día (las autorizadas;
  `app/services/horas_extra/`). Lo trabajado de más sin autorizar no da bolsa.

Cada día deja (o corrige, o borra) UN movimiento `origen = bolsa` con
referencia «tipo:fecha»: recalcular es idempotente. Caduca a los
`caduca_meses` del tipo. Lo consume pedir una ausencia de ese tipo (saldo en
horas, `ausencias/saldos.py`). La pasada diaria recalcula los últimos
`HOUR_BANK_RECALC_DAYS` días (imputaciones tardías o corregidas).
"""
from __future__ import annotations

import uuid
from collections import defaultdict
from datetime import date, timedelta
from typing import Iterable, Optional

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.core import timeutil
from app.models.ausencias import TipoDeAusencia


def _num(v, defecto: Optional[float]) -> Optional[float]:
    return defecto if v in (None, "") else float(v)


def horas_de_bolsa(imputadas: float, horario: float, clase: str, reglas: dict) -> float:
    """Horas de bolsa de un día (puro). `clase`: laborable | festivo | no_laborable."""
    exceso = imputadas - horario
    umbral = (_num(reglas.get("umbral_minutos"), 0.0) or 0.0) / 60
    if exceso <= umbral + 1e-9:
        return 0.0
    factor = {"festivo": _num(reglas.get("factor_festivo"), None),
              "no_laborable": _num(reglas.get("factor_no_laborable"), None)}.get(clase)
    if factor is None:
        factor = _num(reglas.get("factor"), 1.0) or 0.0
    h = (exceso - umbral) * factor
    tope = _num(reglas.get("tope_diario"), None)
    if tope is not None:
        h = min(h, tope)
    return round(max(0.0, h), 4)


def tipos_de_bolsa(db: Session) -> list[TipoDeAusencia]:
    return db.query(TipoDeAusencia).filter(TipoDeAusencia.saldo == "bolsa", TipoDeAusencia.activo.is_(True),
                                           TipoDeAusencia.descuenta_saldo.is_(True)).all()


def recalcular(db: Session, desde: date, hasta: date, user_ids: Optional[Iterable[str]] = None,
               actor_id: Optional[str] = None) -> dict:
    """Rehace los movimientos de bolsa de [desde, hasta]. Confirma (commit)."""
    from app.models.horario import MovimientoDeSaldo
    from app.models.imputation import Imputation
    from app.services.ausencias import catalogo, saldos
    from app.services.horario import efectivo as hor
    tipos = tipos_de_bolsa(db)
    if not tipos or hasta < desde:
        return {"tipos": 0, "personas": 0, "creados": 0, "cambiados": 0, "borrados": 0}
    filtro_ids = set(user_ids) if user_ids is not None else None
    hechos = {"tipos": len(tipos), "personas": 0, "creados": 0, "cambiados": 0, "borrados": 0}
    for tipo in tipos:
        reglas = catalogo.bolsa_de(tipo)
        q = db.query(Imputation.user_id, Imputation.date, func.sum(Imputation.hours)).filter(
            Imputation.date >= desde, Imputation.date <= hasta, Imputation.is_active.is_(True))
        if reglas.get("solo_aprobadas"):
            q = q.filter(Imputation.is_approved.is_(True))
        if filtro_ids is not None:
            q = q.filter(Imputation.user_id.in_(filtro_ids))
        imputado: dict = defaultdict(dict)
        for uid, d, h in q.group_by(Imputation.user_id, Imputation.date).all():
            imputado[uid][d] = float(h or 0)
        existentes: dict = {}
        mq = db.query(MovimientoDeSaldo).filter(MovimientoDeSaldo.saldo_clave == tipo.id,
                                                MovimientoDeSaldo.origen == "bolsa",
                                                MovimientoDeSaldo.fecha >= desde, MovimientoDeSaldo.fecha <= hasta)
        if filtro_ids is not None:
            mq = mq.filter(MovimientoDeSaldo.user_id.in_(filtro_ids))
        for m in mq.all():
            existentes[(m.user_id, m.fecha)] = m
        personas = set(imputado) | {u for u, _ in existentes}
        hechos["personas"] = max(hechos["personas"], len(personas))
        planes = hor.horarios(db, personas, desde, hasta) if personas else {}
        tope_anual = _num(reglas.get("tope_periodo"), None)
        autorizado = _autorizado_en_bolsa(db, personas, desde, hasta) if reglas.get("solo_horas_extra") else None
        for uid in sorted(personas):
            acumulado: dict = defaultdict(float)
            if tope_anual is not None:
                for anio in {d.year for d in hor.dias(desde, hasta)}:
                    previo = db.query(func.sum(MovimientoDeSaldo.cantidad)).filter(
                        MovimientoDeSaldo.user_id == uid, MovimientoDeSaldo.saldo_clave == tipo.id,
                        MovimientoDeSaldo.origen == "bolsa", MovimientoDeSaldo.fecha >= date(anio, 1, 1),
                        MovimientoDeSaldo.fecha < desde).scalar()
                    acumulado[anio] = float(previo or 0)
            for d in hor.dias(desde, hasta):
                x = (planes.get(uid) or {}).get(d)
                horario = x.horas if x is not None else 0.0
                clase = "laborable"
                if x is not None and x.es_festivo_no_trabajado:
                    clase = "festivo"
                elif x is None or x.horas_teoricas <= 0:
                    clase = "no_laborable"
                imp = imputado.get(uid, {}).get(d, 0.0)
                if autorizado is not None:
                    # Solo el exceso que cubren horas extra aprobadas en bolsa.
                    imp = min(imp, horario + autorizado.get((uid, d), 0.0))
                h = horas_de_bolsa(imp, horario, clase, reglas)
                if tope_anual is not None:
                    h = round(max(0.0, min(h, tope_anual - acumulado[d.year])), 4)
                    acumulado[d.year] += h
                fila = existentes.get((uid, d))
                if h <= 0:
                    if fila is not None:
                        db.delete(fila)
                        hechos["borrados"] += 1
                    continue
                caduca = (saldos.sumar_meses(d, int(tipo.caduca_meses)) if tipo.caduca_meses else None)
                if fila is None:
                    db.add(MovimientoDeSaldo(
                        id=str(uuid.uuid4()), organization_id=tipo.organization_id, user_id=uid, saldo_clave=tipo.id,
                        fecha=d, cantidad=h, unidad="horas", origen="bolsa", referencia=f"{tipo.id}:{d.isoformat()}",
                        caduca=caduca, nota=f"Exceso imputado {imputado.get(uid, {}).get(d, 0.0):g} h − horario {horario:g} h",
                        created_by=actor_id))
                    hechos["creados"] += 1
                elif abs(fila.cantidad - h) > 1e-6 or fila.caduca != caduca:
                    fila.cantidad, fila.caduca = h, caduca
                    hechos["cambiados"] += 1
    db.commit()
    return hechos


def _autorizado_en_bolsa(db: Session, personas, desde: date, hasta: date) -> dict:
    """{(user_id, fecha): horas} de horas extra aprobadas que se compensan con bolsa."""
    from app.models.horas_extra import PeticionDeHorasExtra
    from app.services.horas_extra.calculo import horas_vivas
    salida: dict = defaultdict(float)
    if not personas:
        return salida
    for p in db.query(PeticionDeHorasExtra).filter(PeticionDeHorasExtra.user_id.in_(list(personas)),
                                                   PeticionDeHorasExtra.estado == "aprobada",
                                                   PeticionDeHorasExtra.compensacion == "bolsa",
                                                   PeticionDeHorasExtra.fecha >= desde,
                                                   PeticionDeHorasExtra.fecha <= hasta).all():
        salida[(p.user_id, p.fecha)] += horas_vivas(p)
    return salida


def recalcular_y_auditar(db: Session, actor, desde: date, hasta: date,
                         user_ids: Optional[Iterable[str]] = None) -> dict:
    """`recalcular` pedido a mano: deja rastro en la auditoria y confirma."""
    from app.services.audit import audit_log
    r = recalcular(db, desde, hasta, user_ids, actor.id)
    audit_log(db, actor, "RECALCULATE", "hour_bank", None, None,
              new_values={**r, "desde": str(desde), "hasta": str(hasta)})
    db.commit()
    return r


def pasada(db: Session) -> dict:
    """La pasada diaria: recalcula los últimos HOUR_BANK_RECALC_DAYS días."""
    from app.services.settings_service import get_runtime_int
    dias = int(get_runtime_int(db, "HOUR_BANK_RECALC_DAYS", (db.info or {}).get("organization_id")) or 0)
    if dias <= 0:
        return {"omitida": True}
    hoy = timeutil.today()
    return recalcular(db, hoy - timedelta(days=dias), hoy - timedelta(days=1))
