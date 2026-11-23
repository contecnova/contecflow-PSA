"""Coste de licencias y hardware por titular y día (licencias y hardware, fase 3 — 16-11-2026).

Cada licencia y cada activo tienen un coste diario; ese coste se reparte entre
quien los tiene cada día (`ALMAsignacion`) y se imputa a un proyecto, un
centro de coste y un cliente. Lo que nadie tiene es **coste ocioso** (asientos
comprados sin asignar, equipos en el almacén): se imputa al proyecto o centro
de la propia licencia o activo, y se ve aparte.

**Coste diario de una licencia** (un año = 365 días):

- cuota: ``annual_cost / 365`` entre su inicio (compra, o inicio del contrato)
  y su vencimiento (o el fin del contrato);
- si no tiene cuota propia y su contrato tiene ``annual_value``, el contrato se
  reparte entre sus licencias sin cuota, por asientos; lo que el contrato
  cueste por encima de la suma de cuotas de sus licencias es una línea del
  propio contrato (``kind = contract``). Así nunca cuentan dos veces la
  licencia y el contrato;
- una perpetua con precio de compra se amortiza en ``amortization_months``
  (o `ALM_PERPETUAL_AMORTIZATION_MONTHS`) desde la compra.

**Reparto.** Con un total de asientos (nominal, dispositivo, volumen), cada
asiento cuesta ``coste / total``; una asignación paga ``quantity`` asientos y
el resto es ocioso. Sin total (sitio) o concurrente, el coste se reparte entre
lo asignado. Una bolsa paga sus asientos y los reparte con sus hijas; lo no
repartido queda en el titular de la bolsa.

**Activos**: (precio − residual) / (años de amortización × 365) desde la
compra, hasta la baja; o la cuota de renting (``lease_monthly_cost × 12 /
365``) hasta ``lease_expiry``.

**Imputación** de una línea (`cargo_de`): lo explícito de la asignación
(``charge_*``), si no el titular (proyecto, cliente) o la bolsa de la que
cuelga; el centro de coste del recurso o, si no, el del departamento del
titular. El cliente de un proyecto es el del proyecto. ``rebillable``: el de
la asignación, o el del recurso.

Consumidores: `costes_de_proyecto.costes_externos` (rentabilidad y EVM),
`presupuestos_seguir.comprometido_mensual` y `GET /alm/costs`.
"""
from __future__ import annotations

import calendar
from collections import defaultdict
from dataclasses import asdict, dataclass, field
from datetime import date, timedelta
from typing import Iterable, Optional

from sqlalchemy import or_
from sqlalchemy.orm import Session

from app.core import timeutil
from sqlalchemy.orm import object_session
from app.services.settings_service import por_empresa as _pe
from app.models.alm import ALMAsignacion, ALMAsset, ALMContract, ALMLicense, LicenseMetric

DIAS_DEL_ANO = 365.0
UN_DIA = timedelta(days=1)
ORIGEN = date(2000, 1, 1)


@dataclass
class Linea:
    kind: str                       # license | asset | contract | idle
    resource_type: str              # license | asset | contract
    resource_id: str
    resource_name: str
    amount: float
    days: int
    currency: str
    assignment_id: Optional[str] = None
    holder_type: Optional[str] = None
    holder_id: Optional[str] = None
    project_id: Optional[str] = None
    cost_center_id: Optional[str] = None
    client_id: Optional[str] = None
    rebillable: bool = False
    license_id: Optional[str] = None
    contract_id: Optional[str] = None
    extra: dict = field(default_factory=dict)


# ── Cargo ─────────────────────────────────────────────────────────────────────

class _Cache:
    def __init__(self, db: Session):
        self.db = db
        self.proyectos: dict = {}
        self.centros_por_dep: Optional[dict] = None
        self.dep_por_nombre: Optional[dict] = None
        self.usuarios: dict = {}

    def cliente_de_proyecto(self, pid):
        if not pid:
            return None
        if pid not in self.proyectos:
            from app.models.project import Project
            fila = self.db.query(Project.client_id).filter(Project.id == pid).first()
            self.proyectos[pid] = fila[0] if fila else None
        return self.proyectos[pid]

    def centro_de_departamento(self, dep_id):
        if self.centros_por_dep is None:
            from app.models.alm import ALMCostCenter
            self.centros_por_dep = {d: c for c, d in self.db.query(ALMCostCenter.id, ALMCostCenter.department_id)
                                    .filter(ALMCostCenter.department_id.isnot(None), ALMCostCenter.is_active.isnot(False))}
        return self.centros_por_dep.get(dep_id)

    def departamento_de_usuario(self, uid):
        if uid not in self.usuarios:
            from app.models.settings import Department
            from app.models.user import User
            if self.dep_por_nombre is None:
                self.dep_por_nombre = {n: i for i, n in self.db.query(Department.id, Department.name)}
            fila = self.db.query(User.department).filter(User.id == uid).first()
            self.usuarios[uid] = self.dep_por_nombre.get(fila[0]) if fila and fila[0] else None
        return self.usuarios[uid]


def cargo_de(cache: _Cache, a: ALMAsignacion, recurso) -> dict:
    padre = a.parent
    proyecto = (a.charge_project_id or a.holder_project_id
                or (padre.charge_project_id or padre.holder_project_id if padre is not None else None))
    cliente = (a.charge_client_id or a.holder_client_id
               or (padre.charge_client_id or padre.holder_client_id if padre is not None else None)
               or cache.cliente_de_proyecto(proyecto))
    departamento = a.holder_department_id or (padre.holder_department_id if padre is not None else None)
    if departamento is None and a.holder_user_id:
        departamento = cache.departamento_de_usuario(a.holder_user_id)
    centro = (a.charge_cost_center_id or (padre.charge_cost_center_id if padre is not None else None)
              or getattr(recurso, "cost_center_id", None) or cache.centro_de_departamento(departamento))
    refact = a.rebillable if a.rebillable is not None else (
        padre.rebillable if padre is not None and padre.rebillable is not None else bool(getattr(recurso, "rebillable", False)))
    return {"project_id": proyecto, "client_id": cliente, "cost_center_id": centro, "rebillable": bool(refact and cliente)}


# ── Tramos ────────────────────────────────────────────────────────────────────

def _tramos(desde: date, hasta: date, puntos: Iterable[Optional[date]]):
    """Intervalos [a, b) en los que nada cambia, dentro de [desde, hasta]."""
    cortes = {desde, hasta + UN_DIA}
    for p in puntos:
        if p is not None and desde < p <= hasta:
            cortes.add(p)
    orden = sorted(cortes)
    return list(zip(orden, orden[1:]))


def _fin_real(a: ALMAsignacion) -> Optional[date]:
    """Último día que cuenta (None: abierta)."""
    return a.ended_on if a.status == "ended" else None


def _cuenta(a: ALMAsignacion) -> bool:
    return a.status in ("active", "ended") and not (a.status == "ended" and a.ended_on is None)


def _vigente(a: ALMAsignacion, dia: date) -> bool:
    if not _cuenta(a) or dia < a.valid_from:
        return False
    fin = _fin_real(a)
    return fin is None or dia <= fin


# ── Licencias ─────────────────────────────────────────────────────────────────

def _moneda(lic: ALMLicense) -> str:
    # 18-11-2026: sin contrato con moneda, la de la empresa de la licencia (no la global).
    if lic.contract is not None and lic.contract.currency:
        return lic.contract.currency
    return _pe.moneda_de_empresa(object_session(lic), registro=lic)


def _ventana_licencia(lic: ALMLicense) -> tuple[date, Optional[date]]:
    inicio = lic.purchase_date or (lic.contract.start_date if lic.contract is not None else None)
    if inicio is None and lic.created_at is not None:
        inicio = lic.created_at.date()
    fin = lic.expiry_date or (lic.contract.end_date if lic.contract is not None else None)
    return inicio or ORIGEN, fin


def _cuota_anual(db: Session, lic: ALMLicense, reparto_contrato: dict) -> float:
    if lic.annual_cost:
        return float(lic.annual_cost)
    return reparto_contrato.get(lic.id, 0.0)


def _reparto_de_contratos(contratos: Iterable[ALMContract]) -> tuple[dict, dict]:
    """({license_id: cuota del contrato que le toca}, {contract_id: cuota que no absorbe ninguna licencia})."""
    por_licencia: dict = {}
    sobrante: dict = {}
    for c in contratos:
        if not c.annual_value:
            continue
        lics = [lic for lic in (c.licenses or []) if lic.is_active]
        propias = sum(float(lic.annual_cost or 0) for lic in lics)
        sin_cuota = [lic for lic in lics if not lic.annual_cost]
        resto = max(0.0, float(c.annual_value) - propias)
        if sin_cuota and resto > 0:
            pesos = [max(1, lic.total_seats or 1) for lic in sin_cuota]
            total = float(sum(pesos))
            for lic, peso in zip(sin_cuota, pesos):
                por_licencia[lic.id] = resto * peso / total
        elif resto > 0:
            sobrante[c.id] = resto
    return por_licencia, sobrante


def _lineas_de_licencia(db: Session, cache: _Cache, lic: ALMLicense, desde: date, hasta: date,
                        cuota_anual: float, salida: list, sin_amortizacion: bool = False) -> None:
    inicio, fin = _ventana_licencia(lic)
    meses = lic.amortization_months
    if not meses:
        from app.services.alm_ajustes import ajuste_int
        meses = ajuste_int(db, "ALM_PERPETUAL_AMORTIZATION_MONTHS", lic.organization_id) or 36
    amort_fin = None
    amort_diaria = 0.0
    tipo = getattr(lic.type, "value", lic.type)
    if lic.purchase_price and lic.purchase_date and tipo in ("perpetual", "oem", "volume") and not sin_amortizacion:
        dias_amort = max(1, round(meses * DIAS_DEL_ANO / 12))
        amort_diaria = float(lic.purchase_price) / dias_amort
        amort_fin = lic.purchase_date + timedelta(days=dias_amort - 1)
    if not cuota_anual and not amort_diaria:
        return
    a0 = max(desde, inicio)
    a1 = min(hasta, fin) if fin else hasta
    if a1 < a0:
        return
    asignaciones = [a for a in (lic.assignments or []) if _cuenta(a)]
    puntos = [inicio, (fin + UN_DIA) if fin else None, (amort_fin + UN_DIA) if amort_fin else None]
    for a in asignaciones:
        puntos += [a.valid_from, (_fin_real(a) + UN_DIA) if _fin_real(a) else None]
    metrica = lic.metric or LicenseMetric.named_user.value
    con_total = lic.total_seats and metrica not in (LicenseMetric.concurrent.value, LicenseMetric.site.value)
    moneda = _moneda(lic)
    acumulado: dict = defaultdict(lambda: [0.0, 0])
    for t0, t1 in _tramos(a0, a1, puntos):
        dias = (t1 - t0).days
        diaria = cuota_anual / DIAS_DEL_ANO + (amort_diaria if amort_fin and t0 <= amort_fin else 0.0)
        if diaria <= 0:
            continue
        coste = diaria * dias
        primeras = [a for a in asignaciones if a.parent_id is None and _vigente(a, t0)]
        usados = sum(a.quantity or 0 for a in primeras)
        asientos = float(lic.total_seats) if con_total else float(max(usados, 1))
        for a in primeras:
            parte = coste * (a.quantity or 0) / asientos
            if a.mode == "pool":
                hijas = [h for h in asignaciones if h.parent_id == a.id and _vigente(h, t0)]
                usados_bolsa = 0
                for h in hijas:
                    q = min(h.quantity or 0, max(0, (a.quantity or 0) - usados_bolsa))
                    usados_bolsa += q
                    if q and a.quantity:
                        celda = acumulado[("a", h.id)]
                        celda[0] += parte * q / a.quantity
                        celda[1] += dias
                parte = parte * max(0, (a.quantity or 0) - usados_bolsa) / (a.quantity or 1)
            celda = acumulado[("a", a.id)]
            celda[0] += parte
            celda[1] += dias
        if con_total and usados < asientos:
            celda = acumulado[("idle", lic.id)]
            celda[0] += coste * (asientos - usados) / asientos
            celda[1] += dias
        elif not con_total and not primeras:
            # Revisión 16-11-2026: sin asientos contados y sin nadie asignado, la cuota
            # se paga igual: va entera como «sin usar» a la licencia (su proyecto o centro
            # de coste). Antes desaparecía: `asientos` era 1 pero no había a quién repartir.
            celda = acumulado[("idle", lic.id)]
            celda[0] += coste
            celda[1] += dias
    por_id = {a.id: a for a in asignaciones}
    for (clase, ident), (importe, dias) in acumulado.items():
        if importe <= 0:
            continue
        if clase == "idle":
            salida.append(Linea(kind="idle", resource_type="license", resource_id=lic.id, resource_name=lic.name,
                                amount=importe, days=dias, currency=moneda, project_id=lic.project_id,
                                cost_center_id=lic.cost_center_id, client_id=cache.cliente_de_proyecto(lic.project_id),
                                license_id=lic.id, contract_id=lic.contract_id))
            continue
        a = por_id[ident]
        salida.append(Linea(kind="license", resource_type="license", resource_id=lic.id, resource_name=lic.name,
                            amount=importe, days=dias, currency=moneda, assignment_id=a.id,
                            holder_type=a.holder_type, holder_id=a.holder_id, license_id=lic.id,
                            contract_id=lic.contract_id, **cargo_de(cache, a, lic)))


def _lineas_de_contrato(cache: _Cache, c: ALMContract, cuota: float, desde: date, hasta: date, salida: list) -> None:
    inicio = c.start_date or ORIGEN
    fin = c.end_date
    # Revisión 16-11-2026: un contrato cancelado no es coste (antes de la fase 3 el
    # comprometido ya lo excluía). Sin esto, uno cancelado sin fecha de fin sumaba
    # su cuota todos los días desde el origen (medido: 9.999 al año en un presupuesto).
    if getattr(c.status, "value", c.status) in ("draft", "pending", "cancelled"):
        return
    a0, a1 = max(desde, inicio), (min(hasta, fin) if fin else hasta)
    if a1 < a0:
        return
    dias = (a1 - a0).days + 1
    salida.append(Linea(kind="contract", resource_type="contract", resource_id=c.id, resource_name=c.title,
                        amount=cuota / DIAS_DEL_ANO * dias, days=dias,
                        currency=c.currency or _pe.moneda_de_empresa(cache.db, registro=c), project_id=c.project_id,
                        cost_center_id=c.cost_center_id, client_id=cache.cliente_de_proyecto(c.project_id),
                        contract_id=c.id))


# ── Activos ───────────────────────────────────────────────────────────────────

def _lineas_de_activo(cache: _Cache, activo: ALMAsset, desde: date, hasta: date, salida: list,
                      sin_amortizacion: bool = False) -> None:
    tasas = []   # (inicio, fin, diaria)
    if activo.purchase_price and activo.purchase_date and activo.depreciation_years and not sin_amortizacion:
        dias_amort = max(1, round(activo.depreciation_years * DIAS_DEL_ANO))
        base = max(0.0, float(activo.purchase_price) - float(activo.residual_value or 0))
        fin = activo.purchase_date + timedelta(days=dias_amort - 1)
        if activo.disposal_date and activo.disposal_date < fin:
            fin = activo.disposal_date
        tasas.append((activo.purchase_date, fin, base / dias_amort))
    if activo.lease_monthly_cost:
        inicio = activo.purchase_date or (activo.created_at.date() if activo.created_at else ORIGEN)
        tasas.append((inicio, activo.lease_expiry, float(activo.lease_monthly_cost) * 12 / DIAS_DEL_ANO))
    if not tasas:
        return
    asignaciones = [a for a in (activo.assignments or []) if _cuenta(a)]
    puntos = []
    for i, f, _ in tasas:
        puntos += [i, (f + UN_DIA) if f else None]
    for a in asignaciones:
        puntos += [a.valid_from, (_fin_real(a) + UN_DIA) if _fin_real(a) else None]
    acumulado: dict = defaultdict(lambda: [0.0, 0])
    for t0, t1 in _tramos(desde, hasta, puntos):
        diaria = sum(d for i, f, d in tasas if i <= t0 and (f is None or t0 <= f))
        if diaria <= 0:
            continue
        dias = (t1 - t0).days
        titular = next((a for a in asignaciones if _vigente(a, t0)), None)
        celda = acumulado[titular.id if titular else None]
        celda[0] += diaria * dias
        celda[1] += dias
    por_id = {a.id: a for a in asignaciones}
    moneda = activo.currency or _pe.moneda_de_empresa(cache.db, registro=activo)
    for ident, (importe, dias) in acumulado.items():
        if importe <= 0:
            continue
        if ident is None:
            salida.append(Linea(kind="idle", resource_type="asset", resource_id=activo.id, resource_name=activo.name,
                                amount=importe, days=dias, currency=moneda, project_id=None,
                                cost_center_id=activo.cost_center_id, client_id=None))
            continue
        a = por_id[ident]
        salida.append(Linea(kind="asset", resource_type="asset", resource_id=activo.id, resource_name=activo.name,
                            amount=importe, days=dias, currency=moneda, assignment_id=a.id,
                            holder_type=a.holder_type, holder_id=a.holder_id, **cargo_de(cache, a, activo)))


# ── Entrada ───────────────────────────────────────────────────────────────────

def lineas(db: Session, desde: date, hasta: date, *, project_id: Optional[str] = None,
           incluir_ociosos: bool = True, sin_amortizacion: bool = False,
           project_ids: Optional[Iterable[str]] = None) -> list[Linea]:
    """Todas las líneas de coste del periodo [desde, hasta], ambos incluidos.

    Con ``project_id`` solo se cargan los recursos que pueden imputarle algo
    (y se devuelven solo sus líneas). ``sin_amortizacion``: solo cuotas
    (suscripciones, contratos, renting), lo que se paga; para presupuestos."""
    if hasta < desde:
        return []
    cache = _Cache(db)
    salida: list[Linea] = []
    lics = db.query(ALMLicense).filter(ALMLicense.is_active.is_(True))
    activos = db.query(ALMAsset)
    contratos = db.query(ALMContract).filter(ALMContract.is_active.isnot(False))
    # Auditoría 22-11-2026 (§7.2): `project_ids` = la misma poda para una lista
    # de proyectos (el margen en bloque), sin una pasada por proyecto.
    ids = ({project_id} if project_id else set()) | set(project_ids or ())
    if ids:
        ids_asig = db.query(ALMAsignacion.id).filter(or_(
            ALMAsignacion.holder_project_id.in_(ids), ALMAsignacion.charge_project_id.in_(ids)))
        de_proyecto = or_(ALMAsignacion.id.in_(ids_asig), ALMAsignacion.parent_id.in_(ids_asig))
        lics = lics.filter(or_(ALMLicense.project_id.in_(ids), ALMLicense.id.in_(
            db.query(ALMAsignacion.license_id).filter(de_proyecto))))
        activos = activos.filter(or_(ALMAsset.project_id.in_(ids), ALMAsset.id.in_(
            db.query(ALMAsignacion.asset_id).filter(de_proyecto))))
        contratos = contratos.filter(or_(ALMContract.project_id.in_(ids), ALMContract.id.in_(
            db.query(ALMLicense.contract_id).filter(ALMLicense.id.in_(lics.with_entities(ALMLicense.id))))))
    contratos = contratos.all()
    reparto, sobrante = _reparto_de_contratos(contratos)
    for lic in lics.all():
        _lineas_de_licencia(db, cache, lic, desde, hasta, _cuota_anual(db, lic, reparto), salida, sin_amortizacion)
    for a in activos.all():
        _lineas_de_activo(cache, a, desde, hasta, salida, sin_amortizacion)
    for c in contratos:
        if c.id in sobrante:
            _lineas_de_contrato(cache, c, sobrante[c.id], desde, hasta, salida)
    if ids:
        salida = [li for li in salida if li.project_id in ids]
    if not incluir_ociosos:
        salida = [li for li in salida if li.kind != "idle"]
    return salida


def _convertir(db: Session, importe: float, de: str, a: str, fecha: date, cache: dict) -> float:
    if (de or a).upper() == a.upper():
        return importe
    from app.services.profitability_service import get_fx_rate
    return importe * get_fx_rate(db, de.upper(), a.upper(), fecha, _cache=cache)


def coste_de_proyecto(db: Session, project_id: str, moneda: str, desde=None, hasta=None) -> float:
    """Coste de licencias y equipos imputado al proyecto en el periodo (para la rentabilidad)."""
    hasta = hasta or timeutil.today()
    desde = desde or ORIGEN
    fx: dict = {}
    return round(sum(_convertir(db, li.amount, li.currency, moneda, hasta, fx)
                     for li in lineas(db, desde, hasta, project_id=project_id)), 2)


AGRUPACIONES = ("holder", "project", "cost_center", "client", "resource", "kind")


def resumen(db: Session, desde: date, hasta: date, agrupar: str = "holder", moneda: Optional[str] = None,
            project_id: Optional[str] = None) -> dict:
    """Totales del periodo agrupados (``holder``, ``project``, ``cost_center``, ``client``,
    ``resource`` o ``kind``) y las líneas, en ``moneda``."""
    from app.services.alm_asignaciones import nombre_de_titular
    if agrupar not in AGRUPACIONES:
        agrupar = "holder"
    moneda = (moneda or _pe.moneda_de_empresa(db)).upper()
    fx: dict = {}
    filas = lineas(db, desde, hasta, project_id=project_id)
    grupos: dict = {}
    nombres = _Nombres(db)
    total = ocioso = refacturable = 0.0
    detalle = []
    for li in filas:
        importe = _convertir(db, li.amount, li.currency, moneda, hasta, fx)
        total += importe
        if li.kind == "idle":
            ocioso += importe
        if li.rebillable:
            refacturable += importe
        clave, nombre = nombres.grupo(agrupar, li)
        g = grupos.setdefault(clave, {"key": clave, "name": nombre, "amount": 0.0, "idle": 0.0, "lines": 0})
        g["amount"] += importe
        g["idle"] += importe if li.kind == "idle" else 0.0
        g["lines"] += 1
        d = asdict(li)
        d.pop("extra", None)
        d["amount"] = round(importe, 2)
        d["currency"] = moneda
        d["holder_name"] = nombre_de_titular(db, li.holder_type, li.holder_id)
        d["project_name"] = nombres.proyecto(li.project_id)
        d["client_name"] = nombres.cliente(li.client_id)
        d["cost_center_name"] = nombres.centro(li.cost_center_id)
        detalle.append(d)
    for g in grupos.values():
        g["amount"] = round(g["amount"], 2)
        g["idle"] = round(g["idle"], 2)
    return {"from": desde.isoformat(), "to": hasta.isoformat(), "currency": moneda, "group_by": agrupar,
            "total": round(total, 2), "idle": round(ocioso, 2), "rebillable": round(refacturable, 2),
            "groups": sorted(grupos.values(), key=lambda g: -g["amount"]),
            "lines": sorted(detalle, key=lambda d: -d["amount"])}


class _Nombres:
    def __init__(self, db: Session):
        self.db = db
        self._c: dict = {}

    def _uno(self, modelo, ident, campo="name"):
        if not ident:
            return None
        k = (modelo.__name__, ident)
        if k not in self._c:
            obj = self.db.get(modelo, ident)
            self._c[k] = getattr(obj, campo, None) if obj is not None else None
        return self._c[k]

    def proyecto(self, i):
        from app.models.project import Project
        return self._uno(Project, i)

    def cliente(self, i):
        from app.models.clients import Client
        return self._uno(Client, i)

    def centro(self, i):
        from app.models.alm import ALMCostCenter
        return self._uno(ALMCostCenter, i)

    def grupo(self, agrupar: str, li: Linea) -> tuple[str, Optional[str]]:
        from app.services.alm_asignaciones import nombre_de_titular
        if agrupar == "holder":
            if li.kind == "idle":
                return ("idle", None)
            return (f"{li.holder_type}:{li.holder_id}", nombre_de_titular(self.db, li.holder_type, li.holder_id))
        if agrupar == "project":
            return (li.project_id or "none", self.proyecto(li.project_id))
        if agrupar == "cost_center":
            return (li.cost_center_id or "none", self.centro(li.cost_center_id))
        if agrupar == "client":
            return (li.client_id or "none", self.cliente(li.client_id))
        if agrupar == "kind":
            return (li.kind, None)
        return (f"{li.resource_type}:{li.resource_id}", li.resource_name)


def refacturable(db: Session, desde: date, hasta: date, moneda: Optional[str] = None) -> dict:
    """Coste refacturable por cliente, con el margen `ALM_REBILL_MARKUP_PCT`."""
    from app.services.alm_ajustes import ajuste_float
    org = (getattr(db, "info", None) or {}).get("organization_id")
    margen = ajuste_float(db, "ALM_REBILL_MARKUP_PCT", org)
    r = resumen(db, desde, hasta, agrupar="client", moneda=moneda)
    lineas_ = [li for li in r["lines"] if li["rebillable"]]
    por_cliente: dict = {}
    for li in lineas_:
        g = por_cliente.setdefault(li["client_id"], {"client_id": li["client_id"], "client_name": li["client_name"],
                                                     "cost": 0.0, "lines": []})
        g["cost"] += li["amount"]
        g["lines"].append(li)
    for g in por_cliente.values():
        g["cost"] = round(g["cost"], 2)
        g["amount_to_bill"] = round(g["cost"] * (1 + margen / 100.0), 2)
    return {"from": r["from"], "to": r["to"], "currency": r["currency"], "markup_pct": margen,
            "clients": sorted(por_cliente.values(), key=lambda g: -g["cost"]),
            "total_cost": round(sum(g["cost"] for g in por_cliente.values()), 2),
            "total_to_bill": round(sum(g["amount_to_bill"] for g in por_cliente.values()), 2)}


# ── Presupuestos ──────────────────────────────────────────────────────────────

def _limites_de_mes(mes: str) -> tuple[date, date]:
    y, m = int(mes[:4]), int(mes[5:7])
    return date(y, m, 1), date(y, m, calendar.monthrange(y, m)[1])


def meses_facturados(db: Session) -> dict:
    """{(contract_id|license_id): {mes}} cubiertos por una factura de proveedor ya pagada con un gasto.

    Ese mes ya es real (el gasto) y no puede contar también como comprometido."""
    from app.models.alm import ALMFacturaProveedor
    salida: dict = defaultdict(set)
    for f in db.query(ALMFacturaProveedor).filter(ALMFacturaProveedor.is_active.isnot(False),
                                                  ALMFacturaProveedor.expense_id.isnot(None)):
        desde = f.period_from or f.issue_date
        hasta = f.period_to or f.issue_date
        d = date(desde.year, desde.month, 1)
        while d <= hasta:
            for k in (f.contract_id, f.license_id):
                if k:
                    salida[k].add(f"{d.year:04d}-{d.month:02d}")
            d = date(d.year + (d.month // 12), d.month % 12 + 1, 1)
    return salida


def comprometido_por_mes(db: Session, meses: list[str], *, project_id: Optional[str] = None,
                         cost_center_ids: Optional[list[str]] = None, moneda: Optional[str] = None) -> dict[str, float]:
    """{mes: importe} que se pagará por licencias, contratos y renting imputados al ámbito
    (sin amortizaciones: lo comprado ya no es compromiso), sin los meses ya facturados."""
    if not meses or (not project_id and not cost_center_ids):
        return {}
    moneda = (moneda or _pe.moneda_de_empresa(db)).upper()
    facturados = meses_facturados(db)
    fx: dict = {}
    salida: dict[str, float] = {}
    for mes in meses:
        d0, d1 = _limites_de_mes(mes)
        total = 0.0
        for li in lineas(db, d0, d1, project_id=project_id, sin_amortizacion=True):
            if not project_id and li.cost_center_id not in (cost_center_ids or []):
                continue
            if mes in facturados.get(li.contract_id or "", set()) or mes in facturados.get(li.license_id or "", set()):
                continue
            total += _convertir(db, li.amount, li.currency, moneda, d0, fx)
        if total:
            salida[mes] = round(total, 2)
    return salida
