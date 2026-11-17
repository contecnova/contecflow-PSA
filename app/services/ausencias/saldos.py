"""Saldos: de qué descuenta cada tipo, en qué unidad, por periodo, con arrastre y caducidad.

Rev. 180. Un tipo que `descuenta_saldo` descuenta de:

- `vacaciones`: el saldo compartido por todos los tipos con ese saldo. Lo
  gobierna (unidad, periodo, arrastre, caducidad, prorrateo, tabla) el primer
  tipo activo de vacaciones por orden.
- `propio`: su propio cupo por periodo (`cupo_anual`, en la unidad del tipo).
- `bolsa`: una bolsa de horas que se alimenta del exceso imputado según las
  reglas del tipo (`ausencias/bolsa.py`) y de los ajustes de RRHH.

Cada saldo vive en un PERIODO (`periodo_saldo`: anual, semestral, trimestral,
mensual o sin periodo, empezando en `inicio_periodo_mes`) y se mide en DÍAS o
en HORAS (la unidad del tipo que lo gobierna). Lo forman lotes:

- el DERECHO del periodo: la ficha de vacaciones de la persona
  (`user_vacation_balances`), o una tabla de referencia por país/convenio
  (`derecho_tabla_id`: país y ciudad de su sede; categoría = clave del tipo o
  su tipo de contrato), o el cupo del tipo, o `DEFAULT_VACATION_DAYS_PER_YEAR`;
  prorrateado por fecha de alta si `prorratear_alta`; en horas, × su jornada
  media (la conversión días↔horas de ESA persona, de su horario efectivo);
- el ARRASTRE: lo que sobró del periodo anterior, hasta `arrastre_max`, que
  caduca a los `arrastre_caduca_meses` (o al final del periodo);
- los MOVIMIENTOS (`movimientos_de_saldo`): ajustes y horas de bolsa, cada uno
  con su caducidad (`caduca_meses` del tipo).

Las ausencias (aprobadas = «usado»; pendientes o en espera = «pedido»)
consumen los lotes por orden de caducidad (primero lo que antes caduca). Lo que
no cubre ningún lote deja el saldo en negativo (las políticas deciden si se
permite: resultado `saldo_negativo`). Una ausencia descuenta en días sus días
equivalentes (`working_days`: unas horas de un día de 8 h son su parte) y en
horas las horas de su horario que cubre (`scheduled_hours`).

Solo lee: vale para la vista previa, el simulador y la pantalla de saldos.
"""
from __future__ import annotations

import calendar
import json
from dataclasses import dataclass, field
from datetime import date, timedelta
from typing import Iterable, Optional

from sqlalchemy import and_, or_
from sqlalchemy.orm import Session

from app.core import timeutil
from app.models.ausencias import TipoDeAusencia
from app.models.resources import Absence, AbsenceStatus

SALDOS = ("vacaciones", "propio", "bolsa")
PERIODOS = ("anual", "semestral", "trimestral", "mensual", "sin_periodo")
MESES_DE_PERIODO = {"anual": 12, "semestral": 6, "trimestral": 3, "mensual": 1}
PEDIDAS = (AbsenceStatus.pending, AbsenceStatus.waitlisted)
CUENTAN = (AbsenceStatus.approved, AbsenceStatus.pending, AbsenceStatus.waitlisted)
INICIO_SIN_PERIODO = date(2000, 1, 1)


# ── Fechas y periodos ────────────────────────────────────────────────────────

def sumar_meses(d: date, meses: int) -> date:
    m = d.month - 1 + meses
    y, m = d.year + m // 12, m % 12 + 1
    return date(y, m, min(d.day, calendar.monthrange(y, m)[1]))


def periodo(tipo, fecha: date) -> tuple[date, date, str]:
    """(desde, hasta, etiqueta) del periodo de saldo que contiene `fecha`."""
    clase = getattr(tipo, "periodo_saldo", None) or "anual"
    if clase == "sin_periodo":
        return INICIO_SIN_PERIODO, date(9999, 12, 31), "—"
    meses = MESES_DE_PERIODO.get(clase, 12)
    mes0 = int(getattr(tipo, "inicio_periodo_mes", None) or 1)
    ancla = date(fecha.year if fecha.month >= mes0 else fecha.year - 1, mes0, 1)
    while sumar_meses(ancla, meses) <= fecha:
        ancla = sumar_meses(ancla, meses)
    fin = sumar_meses(ancla, meses) - timedelta(days=1)
    if clase == "anual":
        etiqueta = str(ancla.year) if mes0 == 1 else f"{ancla.year}/{fin.year}"
    elif clase == "mensual":
        etiqueta = ancla.strftime("%Y-%m")
    else:
        etiqueta = f"{ancla.isoformat()}…{fin.isoformat()}"
    return ancla, fin, etiqueta


# ── Lotes y consumo (puro) ───────────────────────────────────────────────────

@dataclass
class Lote:
    fecha: date
    cantidad: float
    caduca: Optional[date]
    origen: str
    resto: float = field(default=0.0)

    def __post_init__(self):
        self.resto = float(self.cantidad)

    def vale_en(self, d: date) -> bool:
        return self.fecha <= d and (self.caduca is None or self.caduca >= d)


@dataclass
class Consumo:
    fecha: date
    cantidad: float


def repartir(lotes: list[Lote], consumos: Iterable[Consumo]) -> float:
    """Gasta cada consumo (por fecha) de los lotes válidos ese día, primero el
    que antes caduca. Devuelve lo que ningún lote cubrió (el descubierto)."""
    orden = sorted(lotes, key=lambda l: (l.caduca or date.max, l.fecha))
    descubierto = 0.0
    for c in sorted(consumos, key=lambda c: c.fecha):
        falta = float(c.cantidad)
        if falta <= 0:
            continue
        for lote in orden:
            if falta <= 1e-9:
                break
            if lote.resto <= 0 or not lote.vale_en(c.fecha):
                continue
            usa = min(lote.resto, falta)
            lote.resto -= usa
            falta -= usa
        descubierto += max(0.0, falta)
    return descubierto


def restante_en(lotes: list[Lote], descubierto: float, ref: date) -> tuple[float, float]:
    """(lo que queda válido en `ref` menos el descubierto, lo que ya caducó)."""
    vivo = sum(l.resto for l in lotes if l.caduca is None or l.caduca >= ref)
    caducado = sum(l.resto for l in lotes if l.caduca is not None and l.caduca < ref)
    return round(vivo - descubierto, 4), round(caducado, 4)


# ── Configuración del saldo ──────────────────────────────────────────────────

def _json(v, defecto):
    try:
        return json.loads(v) if v else defecto
    except (TypeError, ValueError):
        return defecto


def gobernante(db: Session, tipo: TipoDeAusencia) -> TipoDeAusencia:
    """El tipo cuya configuración manda en el saldo (vacaciones: el primero por orden)."""
    if tipo.saldo != "vacaciones":
        return tipo
    otro = db.query(TipoDeAusencia).filter(TipoDeAusencia.saldo == "vacaciones",
                                           TipoDeAusencia.descuenta_saldo.is_(True),
                                           TipoDeAusencia.activo.is_(True)) \
        .order_by(TipoDeAusencia.orden, TipoDeAusencia.nombre).first()
    return otro or tipo


def clave_de(tipo: TipoDeAusencia) -> str:
    return "vacaciones" if tipo.saldo == "vacaciones" else tipo.id


def unidad_de(cfg: TipoDeAusencia) -> str:
    if cfg.saldo == "bolsa":
        return "horas"
    return "horas" if cfg.unidad == "horas" else "dias"


def consumo_de(a: Absence, unidad: str, media: float) -> float:
    """Lo que una ausencia descuenta del saldo, en su unidad."""
    if unidad == "horas":
        if a.scheduled_hours is not None:
            return float(a.scheduled_hours)
        if a.hours:
            return float(a.hours)
        if (a.unit or "") == "horas" and a.amount:
            return float(a.amount)
        return float(a.working_days or 0) * media
    return float(a.working_days or 0)


def _filtro_del_saldo(tipo: TipoDeAusencia):
    if tipo.saldo == "vacaciones":
        # Las ausencias de antes de la 167 sin tipo enlazado cuentan por su clave.
        return or_(TipoDeAusencia.saldo == "vacaciones",
                   and_(Absence.absence_type_id.is_(None), Absence.type == "vacation"))
    return Absence.absence_type_id == tipo.id


def _ausencias(db: Session, user_id: str, tipo: TipoDeAusencia, desde: date, hasta: date,
               excluir: Optional[str]) -> list[Absence]:
    q = db.query(Absence).outerjoin(TipoDeAusencia, TipoDeAusencia.id == Absence.absence_type_id).filter(
        Absence.user_id == user_id, Absence.is_active.is_(True), Absence.status.in_(CUENTAN),
        Absence.start_date >= desde, Absence.start_date <= hasta, _filtro_del_saldo(tipo))
    if excluir:
        q = q.filter(Absence.id != excluir)
    return q.all()


# ── Derecho ──────────────────────────────────────────────────────────────────

def _de_tabla(db: Session, tabla_id: str, usuario, categorias: list[str], fecha: date) -> Optional[float]:
    """El valor de una tabla de referencia para la sede (país, ciudad) y la
    categoría más concreta de la persona, vigente en `fecha`."""
    from app.models.advanced_config import Office
    from app.services.politicas.condiciones import cargar_tablas
    tablas = cargar_tablas(db, [tabla_id])
    if tabla_id not in tablas:
        return None
    _tipo, filas = tablas[tabla_id]
    sede = db.query(Office).filter(Office.id == usuario.office_id).first() if getattr(usuario, "office_id", None) else None
    pais = ((sede.country or "") if sede else "").strip().upper()[:2]
    ciudad = ((sede.city or "") if sede else "").strip().lower()
    cats = [c for c in categorias if c]
    mejor, puntos_mejor = None, -1
    for f in filas:
        if f["pais"] and f["pais"].upper() != pais:
            continue
        if f["ciudad"] and (not f["pais"] or f["ciudad"].strip().lower() != ciudad):
            continue
        if f["categoria"] and f["categoria"] not in cats:
            continue
        if (f["vigente_desde"] and f["vigente_desde"] > fecha) or (f["vigente_hasta"] and f["vigente_hasta"] < fecha):
            continue
        puntos = (4 if f["pais"] else 0) + (2 if f["ciudad"] else 0) + (1 if f["categoria"] else 0)
        if puntos > puntos_mejor:
            mejor, puntos_mejor = f, puntos
    return float(mejor["valor"]) if mejor is not None and mejor["valor"] is not None else None


def derecho(db: Session, usuario, cfg: TipoDeAusencia, desde: date, hasta: date, unidad: str,
            media: float) -> tuple[float, str, Optional[float]]:
    """(derecho del periodo en la unidad del saldo, de dónde sale, arrastre fijado a mano o None)."""
    from app.services.settings_service import get_runtime_int
    clase = cfg.periodo_saldo or "anual"
    fraccion = MESES_DE_PERIODO.get(clase, 12) / 12
    valor, origen, en_dias, arrastre_fijo = 0.0, "ninguno", True, None
    ficha = None
    if cfg.saldo == "vacaciones" and clase == "anual":
        from app.models.advanced_config import UserVacationBalance
        ficha = db.query(UserVacationBalance).filter(UserVacationBalance.user_id == usuario.id,
                                                     UserVacationBalance.year == desde.year).first()
    if ficha is not None:
        valor, origen = float(ficha.days_entitled or 0), "ficha"
        arrastre_fijo = float(ficha.days_carried_over) if ficha.days_carried_over else None
    elif cfg.derecho_tabla_id and (v := _de_tabla(db, cfg.derecho_tabla_id, usuario,
                                                    [cfg.clave, getattr(usuario, "employment_type", None)],
                                                    desde)) is not None:
        valor, origen, en_dias = v * fraccion if clase != "sin_periodo" else v, "tabla", unidad == "dias"
    elif cfg.saldo == "propio" and cfg.cupo_anual:
        valor, origen = float(cfg.cupo_anual), "tipo"
        en_dias = unidad == "dias"
        if cfg.unidad == "medios_dias":
            valor = valor / 2
    elif cfg.saldo == "vacaciones":
        valor = float(get_runtime_int(db, "DEFAULT_VACATION_DAYS_PER_YEAR", usuario.organization_id) or 0) * fraccion
        origen = "empresa"
    if en_dias and unidad == "horas":
        valor = valor * media
    alta = getattr(usuario, "hire_date", None)
    if cfg.prorratear_alta and alta and desde < alta <= hasta and clase != "sin_periodo":
        valor = valor * ((hasta - alta).days + 1) / ((hasta - desde).days + 1)
        origen += "+prorrateo"
    return round(valor, 4), origen, arrastre_fijo


# ── El saldo ─────────────────────────────────────────────────────────────────

def _media(db: Session, user_id: str, desde: date, hasta: date, cache: dict) -> float:
    clave = (user_id, desde, hasta)
    if clave not in cache:
        from app.services.horario import efectivo as hor
        d0 = max(desde, timeutil.today() - timedelta(days=366)) if desde == INICIO_SIN_PERIODO else desde
        d1 = min(hasta, d0 + timedelta(days=365))
        cache[clave] = hor.media_diaria_de(db, user_id, d0, d1)
    return cache[clave]


def saldo(db: Session, user_id: str, tipo: TipoDeAusencia, fecha: Optional[date] = None,
          excluir: Optional[str] = None, *, _profundidad: int = 0, _cache: Optional[dict] = None) -> Optional[dict]:
    """El saldo del que descuenta `tipo` para la persona en el periodo de
    `fecha` (hoy por defecto), medido en `fecha`. None si el tipo no descuenta."""
    from app.models.horario import MovimientoDeSaldo
    from app.models.user import User
    from app.services.settings_service import get_runtime_int
    if not tipo.descuenta_saldo or tipo.saldo not in SALDOS:
        return None
    cache = _cache if _cache is not None else {}
    ref = fecha or timeutil.today()
    cfg = gobernante(db, tipo)
    clave, unidad = clave_de(tipo), unidad_de(cfg)
    desde, hasta, etiqueta = periodo(cfg, ref)
    usuario = db.query(User).filter(User.id == user_id).first()
    if usuario is None:
        return None
    media = _media(db, user_id, desde, hasta, cache)
    valor, origen, arrastre_fijo = derecho(db, usuario, cfg, desde, hasta, unidad, media) \
        if cfg.saldo != "bolsa" else (0.0, "bolsa", None)
    lotes: list[Lote] = []
    if valor:
        lotes.append(Lote(desde, valor, hasta if cfg.periodo_saldo != "sin_periodo" else None, "derecho"))

    # Arrastre del periodo anterior.
    arrastre, arrastre_caduca = 0.0, None
    tope_periodos = int(get_runtime_int(db, "ABSENCE_BALANCE_CARRY_PERIODS", usuario.organization_id) or 0)
    if cfg.periodo_saldo != "sin_periodo":
        if arrastre_fijo is not None:
            arrastre = arrastre_fijo * (media if unidad == "horas" else 1)
        elif cfg.arrastre_max is not None and cfg.arrastre_max > 0 and _profundidad < tope_periodos:
            previo = saldo(db, user_id, tipo, desde - timedelta(days=1), excluir, _profundidad=_profundidad + 1,
                           _cache=cache)
            sobra = max(0.0, (previo or {}).get("restante_al_cierre", 0.0))
            arrastre = min(sobra, float(cfg.arrastre_max))
        if arrastre > 0:
            arrastre_caduca = (sumar_meses(desde, int(cfg.arrastre_caduca_meses)) - timedelta(days=1)
                               if cfg.arrastre_caduca_meses else hasta)
            lotes.append(Lote(desde, round(arrastre, 4), arrastre_caduca, "arrastre"))

    # Movimientos (ajustes, bolsa).
    movs = db.query(MovimientoDeSaldo).filter(MovimientoDeSaldo.user_id == user_id,
                                              MovimientoDeSaldo.saldo_clave == clave,
                                              MovimientoDeSaldo.fecha >= desde, MovimientoDeSaldo.fecha <= hasta).all()
    consumos: list[Consumo] = []
    neto_movs = 0.0
    for m in movs:
        cant = float(m.cantidad or 0)
        if (m.unidad or unidad) != unidad:
            cant = cant * media if unidad == "horas" else (cant / media if media else 0.0)
        neto_movs += cant
        if cant >= 0:
            lotes.append(Lote(m.fecha, cant, m.caduca, m.origen or "manual"))
        else:
            consumos.append(Consumo(m.fecha, -cant))

    usado = pedido = 0.0
    for a in _ausencias(db, user_id, tipo, desde, hasta, excluir):
        c = consumo_de(a, unidad, media)
        consumos.append(Consumo(a.start_date, c))
        if a.status == AbsenceStatus.approved:
            usado += c
        else:
            pedido += c
    descubierto = repartir(lotes, consumos)
    restante, caducado = restante_en(lotes, descubierto, ref)
    al_cierre, _ = restante_en(lotes, descubierto, hasta) if cfg.periodo_saldo != "sin_periodo" else (restante, 0)
    proximas = sorted(({"fecha": l.caduca.isoformat(), "cantidad": round(l.resto, 2), "origen": l.origen}
                       for l in lotes if l.caduca and l.resto > 1e-9 and l.caduca >= ref and l.caduca < date(9999, 1, 1)),
                      key=lambda x: x["fecha"])[:5]
    disponible = sum(l.cantidad for l in lotes)
    equivalente = round(restante / media, 2) if unidad == "horas" and media else round(restante * media, 2)
    return {
        "saldo": tipo.saldo, "clave": clave, "tipo_id": tipo.id if tipo.saldo != "vacaciones" else None,
        "gobierna": cfg.id, "unidad": unidad, "year": desde.year,
        "periodo": {"clase": cfg.periodo_saldo or "anual", "desde": desde.isoformat(), "hasta": hasta.isoformat(),
                    "etiqueta": etiqueta},
        "derecho": round(valor, 2), "derecho_origen": origen,
        "arrastre": round(arrastre, 2), "arrastre_caduca": arrastre_caduca.isoformat() if arrastre_caduca else None,
        "movimientos": round(neto_movs, 2), "disponible": round(disponible, 2),
        "usado": round(usado, 2), "pedido": round(pedido, 2), "caducado": round(caducado, 2),
        "restante": round(restante, 2), "restante_al_cierre": round(al_cierre, 4),
        "media_diaria_horas": round(media, 2),
        "equivalente": {"unidad": "dias" if unidad == "horas" else "horas", "restante": equivalente},
        "proximas_caducidades": proximas, "retribuido": bool(getattr(cfg, "retribuido", True)),
    }


def de_tipo(db: Session, user_id: str, ref, tipo: Optional[TipoDeAusencia], excluir: Optional[str] = None) -> Optional[dict]:
    """El saldo de un tipo; `ref` es una fecha (o un año, compatibilidad: su 1 de enero o hoy)."""
    if tipo is None or not tipo.descuenta_saldo:
        return None
    if isinstance(ref, int):
        hoy = timeutil.today()
        ref = hoy if hoy.year == ref else date(ref, 1, 1)
    return saldo(db, user_id, tipo, ref, excluir)


def vacaciones(db: Session, user_id: str, year: int, excluir: Optional[str] = None) -> dict:
    """El saldo de vacaciones de un año (formato de siempre más lo nuevo)."""
    from app.services.ausencias import catalogo
    tipo = next((t for t in catalogo.tipos(db) if t.descuenta_saldo and t.saldo == "vacaciones"), None)
    if tipo is None:
        return {"saldo": "vacaciones", "unidad": "dias", "year": year, "disponible": 0.0, "derecho": 0.0,
                "arrastre": 0.0, "usado": 0.0, "pedido": 0.0, "restante": 0.0}
    return de_tipo(db, user_id, year, tipo, excluir)


def todos(db: Session, user_id: str, ref=None) -> list[dict]:
    """Todos los saldos de una persona: el de vacaciones y uno por tipo con saldo propio o bolsa."""
    from app.services.ausencias import catalogo
    fecha = ref if isinstance(ref, date) else (date(ref, 1, 1) if isinstance(ref, int) and ref != timeutil.today().year
                                               else timeutil.today())
    tipos = catalogo.tipos(db)
    salida = []
    cache: dict = {}
    vac = [t for t in tipos if t.descuenta_saldo and t.saldo == "vacaciones"]
    if vac:
        v = saldo(db, user_id, vac[0], fecha, _cache=cache)
        if v is not None:
            v["tipos"] = [t.id for t in vac]
            salida.append(v)
    for t in tipos:
        if t.descuenta_saldo and t.saldo in ("propio", "bolsa"):
            p = saldo(db, user_id, t, fecha, _cache=cache)
            if p is not None:
                p["tipos"] = [t.id]
                salida.append(p)
    return salida
