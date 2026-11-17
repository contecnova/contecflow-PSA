"""El horario efectivo de una persona en un día: la ÚNICA fuente de verdad.

Qué horas trabaja cada persona cada día, en este orden:

1. **Cambio del cuadrante** (`asignaciones_de_turno`): el turno (o libre) de
   ese día. Manda sobre todo.
2. **Rotación** (`patrones_de_turnos`): el turno que le toca en su ciclo (o
   libre).
3. **Jornada asignada** (`asignaciones_de_jornada`): la de mayor prioridad que
   le aplique ese día (persona, grupo, equipo, departamento, sede o empresa;
   permanente, con fechas o cada año —verano—).
4. **Empresa**: los días de `PLANNING_WORKDAYS`, desde `DEFAULT_WORKDAY_START`,
   con su jornada semanal (`weekly_capacity_hours`) repartida entre esos días
   (o `DEFAULT_WORKING_HOURS_PER_DAY`).

Sobre ese horario teórico se quitan:

- los **festivos** de la empresa (sin sede ni `applies_to`), de su **sede**
  (`holidays.office_id`) o de su país/ciudad (`applies_to`), salvo en un turno
  que `trabaja_festivos`;
- los días **fuera de contrato** de un externo (`externos.disponibilidad`);
- sus **ausencias** (por defecto las aprobadas): un día entero, medio día (la
  segunda mitad el primer día y la primera el último) o por horas (la franja
  `start_time`–`end_time` dentro de su horario; sin franja, las horas por el
  final).

Un turno que cruza la medianoche cuenta en el día en que empieza.

Lo usan el planificador (CPM, carga, nivelación), las reservas, la capacidad,
la previsión, la rejilla persona×día, las ausencias (días que cuentan, horas
de una petición) y los saldos (conversión días↔horas por persona). Solo lee.
"""
from __future__ import annotations

import json
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date, timedelta
from typing import Iterable, Optional

from sqlalchemy.orm import Session

from app.services.horario import tramos as tr
from app.services.horario.tramos import Tramo

ESPECIFICIDAD = {"persona": 6, "grupo": 5, "equipo": 4, "departamento": 3, "sede": 2, "empresa": 1}
AMBITOS = tuple(ESPECIFICIDAD)
MAX_DIAS = 1100


def _json(v, defecto):
    try:
        return json.loads(v) if v else defecto
    except (TypeError, ValueError):
        return defecto


def dias(desde: date, hasta: date) -> list[date]:
    return [desde + timedelta(days=i) for i in range((hasta - desde).days + 1)]


@dataclass
class AusenciaEnDia:
    id: str
    tipo_id: Optional[str]
    tipo: str
    estado: str
    tramos: tuple[Tramo, ...]
    completa: bool
    modo: str

    def a_dict(self) -> dict:
        return {"id": self.id, "tipo_id": self.tipo_id, "tipo": self.tipo, "estado": self.estado,
                "tramos": tr.a_lista(self.tramos), "horas": tr.total_horas(self.tramos), "completa": self.completa,
                "modo": self.modo}


@dataclass
class DiaEfectivo:
    fecha: date
    tramos: tuple[Tramo, ...] = ()
    pausa_minutos: int = 0
    origen: str = "empresa"                 # cambio | rotacion | jornada | empresa
    turno_id: Optional[str] = None
    jornada_id: Optional[str] = None
    festivo: Optional[str] = None
    trabaja_festivo: bool = False
    fuera_de_contrato: bool = False
    ausencias: list[AusenciaEnDia] = field(default_factory=list)

    # ── Horas ────────────────────────────────────────────────────────────────
    def _neto(self, tramos: Iterable[Tramo]) -> float:
        """Horas de unos tramos del día descontando la parte proporcional de la pausa."""
        bruto = tr.total_horas(self.tramos)
        parte = tr.total_horas(tramos)
        if bruto <= 0:
            return 0.0
        return round(max(0.0, parte - (self.pausa_minutos / 60) * (parte / bruto)), 4)

    @property
    def horas_teoricas(self) -> float:
        """Las del turno o la jornada, antes de festivos, contrato y ausencias."""
        return self._neto(self.tramos)

    @property
    def es_festivo_no_trabajado(self) -> bool:
        return bool(self.festivo) and not self.trabaja_festivo

    @property
    def libres(self) -> tuple[Tramo, ...]:
        """Los tramos en que de verdad trabaja (sin festivo, contrato ni ausencias)."""
        if self.fuera_de_contrato or self.es_festivo_no_trabajado:
            return ()
        quitar: list[Tramo] = []
        for a in self.ausencias:
            quitar.extend(a.tramos)
        return tr.restar(self.tramos, quitar)

    @property
    def horas(self) -> float:
        return self._neto(self.libres)

    def horas_sin(self, estados: tuple = ("pending", "waitlisted")) -> float:
        """Horas disponibles sin contar las ausencias en esos estados (las pendientes aún no quitan nada)."""
        if self.fuera_de_contrato or self.es_festivo_no_trabajado:
            return 0.0
        quitar = [t for a in self.ausencias if a.estado not in estados for t in a.tramos]
        return self._neto(tr.restar(self.tramos, quitar))

    @property
    def laborable(self) -> bool:
        """Le toca trabajar ese día (horario y no festivo ni fuera de contrato), aunque esté ausente."""
        return self.horas_teoricas > 0 and not self.fuera_de_contrato and not self.es_festivo_no_trabajado

    @property
    def disponible(self) -> bool:
        return self.horas > 0

    def desglose(self) -> dict:
        """Horas teóricas, de festivo, fuera de contrato, de ausencia y disponibles (suman)."""
        teo = self.horas_teoricas
        fuera = teo if self.fuera_de_contrato else 0.0
        fest = teo if (not self.fuera_de_contrato and self.es_festivo_no_trabajado) else 0.0
        aus = 0.0 if (fuera or fest) else round(teo - self.horas, 4)
        return {"teoricas": teo, "festivo": fest, "fuera_de_contrato": fuera, "ausencia": aus, "disponibles": self.horas}

    def a_dict(self) -> dict:
        return {"fecha": self.fecha.isoformat(), "origen": self.origen, "turno_id": self.turno_id,
                "jornada_id": self.jornada_id, "tramos": tr.a_lista(self.tramos), "pausa_minutos": self.pausa_minutos,
                "festivo": self.festivo, "trabaja_festivo": self.trabaja_festivo,
                "fuera_de_contrato": self.fuera_de_contrato, "laborable": self.laborable,
                "horas_teoricas": round(self.horas_teoricas, 2), "horas": round(self.horas, 2),
                "libres": tr.a_lista(self.libres), "ausencias": [a.a_dict() for a in self.ausencias]}


# ── Datos de la empresa (una vez por cálculo) ────────────────────────────────

@dataclass
class _Empresa:
    org: Optional[str]
    dias_laborables: frozenset
    horas_por_dia: float
    inicio: int
    turnos: dict
    jornadas: dict
    asignaciones: list
    oficinas: dict
    grupos: dict            # user_id -> [grupo_id]


def _empresa(db: Session, org: Optional[str]) -> _Empresa:
    from app.models.advanced_config import Office
    from app.models.billing_reports import ApprovalGroup
    from app.models.horario import AsignacionDeJornada, JornadaLaboral
    from app.services.ausencias import turnos as turnos_srv
    from app.services.planificador.calendario import interpretar_dias_laborables
    from app.services.settings_service import get_runtime_float, get_runtime_str
    try:
        laborables = interpretar_dias_laborables(get_runtime_str(db, "PLANNING_WORKDAYS", org))
    except ValueError:
        laborables = frozenset({1, 2, 3, 4, 5})
    horas = float(get_runtime_float(db, "DEFAULT_WORKING_HOURS_PER_DAY", org) or 8.0)
    try:
        inicio = tr.minutos(get_runtime_str(db, "DEFAULT_WORKDAY_START", org) or "09:00")
    except (ValueError, TypeError):
        inicio = 9 * 60
    jornadas = {j.id: j for j in db.query(JornadaLaboral).filter(JornadaLaboral.activo.is_(True)).all()}
    asignaciones = [a for a in db.query(AsignacionDeJornada).all() if a.jornada_id in jornadas]
    grupos: dict = defaultdict(list)
    for g in db.query(ApprovalGroup).all():
        for uid in _json(getattr(g, "member_ids", None), []) or []:
            grupos[uid].append(g.id)
    return _Empresa(org=org, dias_laborables=laborables, horas_por_dia=horas, inicio=inicio,
                    turnos={t.id: t for t in turnos_srv.turnos(db, incluir_inactivos=True)},
                    jornadas=jornadas, asignaciones=asignaciones,
                    oficinas={o.id: o for o in db.query(Office).all()}, grupos=dict(grupos))


def _vigente(a, d: date) -> bool:
    if a.recurrente_anual and a.desde and a.hasta:
        md, ini, fin = (d.month, d.day), (a.desde.month, a.desde.day), (a.hasta.month, a.hasta.day)
        return ini <= md <= fin if ini <= fin else (md >= ini or md <= fin)
    return not ((a.desde and d < a.desde) or (a.hasta and d > a.hasta))


def _aplica(a, u, grupos: list) -> bool:
    v = (a.valor or "").strip()
    if a.ambito == "empresa":
        return True
    if a.ambito == "persona":
        return v == u.id
    if a.ambito == "sede":
        return bool(u.office_id) and v == u.office_id
    if a.ambito == "grupo":
        return v in grupos
    if a.ambito == "departamento":
        return bool(u.department) and v.lower() == (u.department or "").lower()
    if a.ambito == "equipo":
        return bool(u.team) and v.lower() == (u.team or "").lower()
    return False


def jornada_que_aplica(asignaciones: list, u, grupos: list, d: date):
    """La asignación que manda ese día: prioridad, concreción, temporal, más reciente."""
    candidatas = [a for a in asignaciones if _aplica(a, u, grupos) and _vigente(a, d)]
    if not candidatas:
        return None
    return max(candidatas, key=lambda a: (a.prioridad or 0, ESPECIFICIDAD.get(a.ambito, 0),
                                          1 if (a.desde or a.hasta) else 0, a.desde or date.min, str(a.id)))


def tramos_de_jornada(j, d: date) -> tuple[Tramo, ...]:
    semana = _json(j.semana, {}) or {}
    try:
        return tr.de_lista(semana.get(str(d.isoweekday())) or [])
    except ValueError:
        return ()


def _festivo(festivos_del_dia: list, oficina) -> Optional[str]:
    """El nombre del festivo que le toca (empresa, su sede o su país/ciudad), o None."""
    for h in festivos_del_dia:
        if getattr(h, "office_id", None):
            if oficina is not None and h.office_id == oficina.id:
                return h.name
            continue
        destino = (h.applies_to or "").strip().lower()
        if not destino:
            return h.name
        if oficina is not None and destino in {(oficina.country or "").strip().lower(), (oficina.name or "").strip().lower(),
                                               (oficina.city or "").strip().lower(), oficina.id.lower()}:
            return h.name
    return None


def _org_de(db: Session, usuarios: list) -> Optional[str]:
    org = (db.info or {}).get("organization_id")
    if org:
        return org
    return next((u.organization_id for u in usuarios if getattr(u, "organization_id", None)), None)


# ── El cálculo ───────────────────────────────────────────────────────────────

def horarios(db: Session, user_ids: Iterable[str], desde: date, hasta: date, *,
             estados_ausencia: Optional[tuple] = ("approved",), excluir_ausencia: Optional[str] = None,
             org: Optional[str] = None) -> dict[str, dict[date, DiaEfectivo]]:
    """{user_id: {fecha: DiaEfectivo}} de [desde, hasta]. `estados_ausencia=None`: sin ausencias."""
    from app.models.settings import Holiday
    from app.models.user import User
    from app.services.ausencias import turnos as turnos_srv
    from app.services.externos.disponibilidad import ventanas

    ids = sorted({u for u in user_ids if u})
    if not ids or hasta < desde:
        return {}
    if (hasta - desde).days + 1 > MAX_DIAS:
        hasta = desde + timedelta(days=MAX_DIAS - 1)
    usuarios = {u.id: u for u in db.query(User).filter(User.id.in_(ids)).all()}
    emp = _empresa(db, org or _org_de(db, list(usuarios.values())))
    plan = turnos_srv.plan_crudo(db, desde, hasta, ids)
    fest_q = db.query(Holiday).filter(Holiday.date >= desde, Holiday.date <= hasta)
    if emp.org:
        fest_q = fest_q.filter(Holiday.organization_id == emp.org)
    festivos: dict = defaultdict(list)
    for h in fest_q.all():
        festivos[h.date].append(h)
    contratos = ventanas(db, ids)
    salida: dict[str, dict[date, DiaEfectivo]] = {}
    for uid in ids:
        u = usuarios.get(uid)
        if u is None:
            continue
        grupos = emp.grupos.get(uid, [])
        n_lab = len(emp.dias_laborables) or 5
        semana_h = float(u.weekly_capacity_hours) if u.weekly_capacity_hours else None
        horas_dia = (semana_h / n_lab) if semana_h else emp.horas_por_dia
        sede = emp.oficinas.get(u.office_id) if u.office_id else None
        v = contratos.get(uid)
        por_dia: dict[date, DiaEfectivo] = {}
        for d in dias(desde, hasta):
            dia = DiaEfectivo(fecha=d)
            tid, origen = plan.get((uid, d), (None, None))
            oficina = sede
            if origen:
                dia.origen = origen
                t = emp.turnos.get(tid) if tid else None
                if t is not None:
                    dia.turno_id = t.id
                    dia.tramos = turnos_srv.tramos_de_turno(t)
                    dia.pausa_minutos = int(t.pausa_minutos or 0)
                    dia.trabaja_festivo = bool(t.trabaja_festivos)
                    if oficina is None and t.office_id:
                        oficina = emp.oficinas.get(t.office_id)
            else:
                a = jornada_que_aplica(emp.asignaciones, u, grupos, d)
                if a is not None:
                    j = emp.jornadas[a.jornada_id]
                    dia.origen, dia.jornada_id = "jornada", j.id
                    dia.tramos = tramos_de_jornada(j, d)
                    dia.pausa_minutos = int(j.pausa_minutos or 0) if dia.tramos else 0
                elif d.isoweekday() in emp.dias_laborables and horas_dia > 0:
                    fin = min(emp.inicio + int(round(horas_dia * 60)), emp.inicio + tr.DIA)
                    dia.tramos = (Tramo(emp.inicio, fin),) if fin > emp.inicio else ()
            dia.festivo = _festivo(festivos.get(d, []), oficina)
            dia.fuera_de_contrato = v is not None and not v.contiene(d)
            por_dia[d] = dia
        salida[uid] = por_dia
    if estados_ausencia:
        _aplicar_ausencias(db, salida, ids, desde, hasta, estados_ausencia, excluir_ausencia)
    return salida


def _aplicar_ausencias(db: Session, salida: dict, ids: list, desde: date, hasta: date, estados: tuple,
                       excluir: Optional[str]) -> None:
    from app.models.resources import Absence
    q = db.query(Absence).filter(Absence.user_id.in_(ids), Absence.is_active.is_(True),
                                 Absence.start_date <= hasta, Absence.end_date >= desde)
    q = q.filter(Absence.status.in_(list(estados)))
    if excluir:
        q = q.filter(Absence.id != excluir)
    for a in q.all():
        dias_persona = salida.get(a.user_id) or {}
        for d, tramos in tramos_de_ausencia(a, dias_persona).items():
            dia = dias_persona.get(d)
            if dia is None:
                continue
            dia.ausencias.append(AusenciaEnDia(
                id=a.id, tipo_id=a.absence_type_id, tipo=a.type, estado=str(getattr(a.status, "value", a.status)),
                tramos=tramos, completa=tr.total_horas(tramos) >= tr.total_horas(dia.tramos) - 1e-9,
                modo=a.modo or ("horas" if a.start_time else "dias")))


def tramos_de_ausencia(a, dias_persona: dict) -> dict[date, tuple[Tramo, ...]]:
    """Los tramos que una ausencia quita cada día de su horario (los días del
    rango que estén en `dias_persona`). Sirve igual para una ausencia guardada
    que para una petición sin guardar."""
    salida: dict[date, tuple[Tramo, ...]] = {}
    rango = [d for d in dias(a.start_date, a.end_date) if d in dias_persona]
    if a.start_time is not None and a.end_time is not None:
        for d in rango:
            salida[d] = tr.franja_en_dia(a.start_time, a.end_time, dias_persona[d].tramos)
        return salida
    if (a.modo == "horas" or (getattr(a, "unit", None) == "horas" and not a.half_day_start and not a.half_day_end)) \
            and a.hours:
        con_horario = [d for d in rango if dias_persona[d].tramos]
        if not con_horario:
            return {d: () for d in rango}
        por_dia = float(a.hours) / len(con_horario)
        for d in rango:
            t = dias_persona[d].tramos
            salida[d] = tr.restar(t, tr.recortar_horas(t, por_dia)) if t else ()
        return salida
    for d in rango:
        t = dias_persona[d].tramos
        if a.start_date == a.end_date and (a.half_day_start or a.half_day_end):
            salida[d] = tr.mitad(t, "segunda" if a.half_day_start else "primera")
        elif d == a.start_date and a.half_day_start:
            salida[d] = tr.mitad(t, "segunda")
        elif d == a.end_date and a.half_day_end:
            salida[d] = tr.mitad(t, "primera")
        else:
            salida[d] = tuple(t)
    return salida


# ── Atajos ───────────────────────────────────────────────────────────────────

def horario(db: Session, user_id: str, desde: date, hasta: date, **kw) -> dict[date, DiaEfectivo]:
    return horarios(db, [user_id], desde, hasta, **kw).get(user_id, {})


def dia(db: Session, user_id: str, fecha: date, **kw) -> Optional[DiaEfectivo]:
    return horario(db, user_id, fecha, fecha, **kw).get(fecha)


def media_diaria(dias_persona: dict, defecto: float = 8.0) -> float:
    """Horas medias de un día de trabajo (teóricas, sin festivos ni fuera de
    contrato): la conversión días↔horas de esa persona."""
    valores = [x.horas_teoricas for x in dias_persona.values()
               if x.horas_teoricas > 0 and not x.es_festivo_no_trabajado and not x.fuera_de_contrato]
    return round(sum(valores) / len(valores), 4) if valores else defecto


def media_diaria_de(db: Session, user_id: str, desde: date, hasta: date) -> float:
    from app.services.settings_service import get_runtime_float
    defecto = float(get_runtime_float(db, "DEFAULT_WORKING_HOURS_PER_DAY", (db.info or {}).get("organization_id"))
                    or 8.0)
    return media_diaria(horario(db, user_id, desde, hasta, estados_ausencia=None), defecto)


def semana(db: Session, user_id: str, lunes: date) -> dict:
    """Desglose de horas de una semana (lunes a domingo) con las ausencias aprobadas."""
    total = {"teoricas": 0.0, "festivo": 0.0, "fuera_de_contrato": 0.0, "ausencia": 0.0, "disponibles": 0.0}
    dias_lab: list[date] = []
    for d, x in sorted(horario(db, user_id, lunes, lunes + timedelta(days=6)).items()):
        for k, v in x.desglose().items():
            total[k] += v
        if x.disponible:
            dias_lab.append(d)
    return {**{k: round(v, 2) for k, v in total.items()}, "dias_disponibles": dias_lab}
