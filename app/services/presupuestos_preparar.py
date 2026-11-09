"""Presupuestos: preparar a fondo (revisión 2026-11).

El presupuesto es la base de las áreas y de los proyectos. Aquí vive lo que
hace falta para prepararlo bien; `budgets_service` lo usa al guardar partidas,
enviar y enseñar la ficha.

**Cómo se calcula una partida** (por meses dentro de su periodo, y si tiene
`mes_desde`/`mes_hasta`, sólo entre ellos), según los campos que traiga:

1. **Conductor**: `unidades × precio_unitario` con su `recurrencia`
   (única: el primer mes; mensual; trimestral: cada tres meses desde el primero;
   anual: cada doce).
2. **Persona por coste cargado**: `user_id` + `dedicacion_pct` (sin horas):
   cada mes, el coste anual de la estructura de costes **vigente ese mes**
   (`user_cost_profiles`, así las subidas con fecha entran solas) / 12 × % de
   dedicación.
3. **Vacante**: `salario_anual` (+ `pais` y `fecha_alta`): desde el mes de alta,
   salario × (1 + cargas del país en `country_employer_costs`) / 12 × % de
   dedicación (100 % si no se da).
4. **Horas × coste/hora** (persona o perfil), repartido por igual.
5. **Importe**, repartido por igual o como se teclee mes a mes.

La **inflación** de los supuestos (`supuestos.inflacion_pct`) sube cada año del
periodo después del primero los modos 1, 3, 4 y 5 repartido por igual; el modo
2 no, porque la estructura de costes ya trae sus subidas.

**Ingresos**: una partida con `sentido = "ingreso"` y tipo de
`BUDGET_REVENUE_TYPES` se calcula igual (horas facturables × tarifa como
conductor, o importe) y da el margen previsto.

**CAPEX**: `naturaleza = "capex"` con `vida_meses`; el plan guarda el pago (el
mes en que se compra) y la ficha enseña además la amortización mensual.

**Jerarquía**: área > departamento > proyecto. `padre_id` es el origen del
presupuesto que consume; un área o un departamento puede tener `techo`, y la
suma de sus hijos no debe pasarlo (`BUDGET_CEILING_POLICY`: avisar o bloquear).
"""
from __future__ import annotations

import json
from datetime import date
from typing import Optional

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.core import timeutil
from app.models.mfa import Budget, BudgetCampaign, BudgetLine, BudgetTemplate

NIVEL = {"area": 0, "departamento": 1, "proyecto": 2, "proyecto_previsto": 2}
RECURRENCIAS = ("unica", "mensual", "trimestral", "anual")
ACTIVOS = ("borrador", "enviado", "aprobado")   # versiones que cuentan contra el techo del padre


def _aj(db: Session, clave: str, org) -> str:
    from app.services.settings_service import get_runtime_str
    return str(get_runtime_str(db, clave, org) or "")


def _csv(db: Session, clave: str, org) -> list[str]:
    return [x.strip() for x in _aj(db, clave, org).split(",") if x.strip()]


def tipos_de_ingreso(db: Session, org) -> list[str]:
    return _csv(db, "BUDGET_REVENUE_TYPES", org)


def supuestos(b: Budget) -> dict:
    try:
        return json.loads(b.supuestos or "{}") or {}
    except ValueError:
        return {}


# ── Meses ─────────────────────────────────────────────────────────────────────

def meses_de(b: Budget) -> list[str]:
    from app.services.budgets_service import meses_del_periodo
    return meses_del_periodo(b.periodo_desde, b.periodo_hasta) if b.periodo_desde and b.periodo_hasta else []


def rango_de_la_partida(b: Budget, l: BudgetLine) -> list[str]:
    meses = meses_de(b)
    if l.mes_desde:
        meses = [m for m in meses if m >= l.mes_desde]
    if l.mes_hasta:
        meses = [m for m in meses if m <= l.mes_hasta]
    return meses


def _factor_inflacion(b: Budget, mes: str) -> float:
    pct = float(supuestos(b).get("inflacion_pct") or 0)
    anios = int(mes[:4]) - b.periodo_desde.year
    return (1 + pct / 100) ** max(anios, 0)


def _repartir(importe: float, meses: list[str]) -> dict[str, float]:
    from app.services.budgets_service import repartir_por_igual
    return repartir_por_igual(importe, meses)


# ── Coste de personas ─────────────────────────────────────────────────────────

def coste_mensual_de_persona(db: Session, user_id: str, mes: str) -> Optional[float]:
    """Coste anual cargado / 12 del perfil de costes vigente el primer día del mes."""
    from sqlalchemy import or_

    from app.models.user_cost import UserCostProfile
    dia = date(int(mes[:4]), int(mes[5:7]), 1)
    p = (db.query(UserCostProfile)
         .filter(UserCostProfile.user_id == user_id, UserCostProfile.is_active.isnot(False),
                 UserCostProfile.valid_from <= dia,
                 or_(UserCostProfile.valid_to.is_(None), UserCostProfile.valid_to >= dia))
         .order_by(UserCostProfile.valid_from.desc()).first())
    return round(float(p.total_annual_cost) / 12, 2) if p else None


def cargas_del_pais(db: Session, org, pais: Optional[str]) -> float:
    from sqlalchemy import or_

    from app.models.user_cost import CountryEmployerCost
    if not pais:
        raise HTTPException(400, "Una vacante necesita el país (para sus cargas sociales)")
    fila = (db.query(CountryEmployerCost)
            .filter(CountryEmployerCost.country_code == pais.upper(), CountryEmployerCost.is_active.isnot(False),
                    or_(CountryEmployerCost.organization_id == org, CountryEmployerCost.organization_id.is_(None)))
            .order_by(CountryEmployerCost.organization_id.is_(None)).first())
    if fila is None:
        raise HTTPException(400, f"No hay cargas sociales para {pais.upper()}: dalas de alta en Estructura de costes")
    return float(fila.employer_cost_pct)


# ── Cálculo de una partida ────────────────────────────────────────────────────

def calcular(db: Session, b: Budget, l: BudgetLine, meses_tecleados: Optional[dict] = None) -> None:
    """Rellena `l.meses` e `l.importe` según el modo de la partida (ver cabecera)."""
    rango = rango_de_la_partida(b, l)
    if not rango:
        raise HTTPException(400, "La partida no tiene ningún mes dentro del periodo")
    if l.recurrencia and l.recurrencia not in RECURRENCIAS:
        raise HTTPException(400, f"Recurrencia no válida: {l.recurrencia}")
    ded = (float(l.dedicacion_pct) / 100) if l.dedicacion_pct is not None else 1.0
    if l.dedicacion_pct is not None and not 0 < float(l.dedicacion_pct) <= 100:
        raise HTTPException(400, "La dedicación va de 1 a 100 %")
    meses: dict[str, float] = {}

    if l.unidades is not None and l.precio_unitario is not None:
        paso = {"unica": None, "mensual": 1, "trimestral": 3, "anual": 12}[l.recurrencia or "unica"]
        cuando = [rango[0]] if paso is None else rango[::paso]
        for m in cuando:
            meses[m] = round(float(l.unidades) * float(l.precio_unitario) * _factor_inflacion(b, m), 2)
    elif l.user_id and l.dedicacion_pct is not None and l.horas is None:
        for m in rango:
            coste = coste_mensual_de_persona(db, l.user_id, m)
            if coste is None:
                raise HTTPException(400, f"La persona no tiene estructura de coste vigente en {m}")
            meses[m] = round(coste * ded, 2)
    elif l.salario_anual is not None:
        cargas = cargas_del_pais(db, b.organization_id, l.pais)
        alta = f"{l.fecha_alta.year}-{l.fecha_alta.month:02d}" if l.fecha_alta else rango[0]
        mensual = float(l.salario_anual) * (1 + cargas) / 12 * ded
        for m in rango:
            if m >= alta:
                meses[m] = round(mensual * _factor_inflacion(b, m), 2)
    elif l.horas is not None:
        if l.coste_hora is None:
            raise HTTPException(400, "Con horas hace falta el coste o la tarifa por hora (o una persona con su coste)")
        base = _repartir(round(float(l.horas) * float(l.coste_hora), 2), rango)
        meses = {m: round(v * _factor_inflacion(b, m), 2) for m, v in base.items()}
    elif meses_tecleados:
        fuera = set(meses_tecleados) - set(rango)
        if fuera:
            raise HTTPException(400, f"Meses fuera del periodo de la partida: {', '.join(sorted(fuera))}")
        meses = {k: round(float(v), 2) for k, v in meses_tecleados.items() if float(v)}
    else:
        if l.importe is None or float(l.importe) < 0:
            raise HTTPException(400, "El importe tiene que ser cero o positivo")
        base = _repartir(float(l.importe), rango)
        meses = {m: round(v * _factor_inflacion(b, m), 2) for m, v in base.items()}

    l.meses = json.dumps({k: v for k, v in meses.items() if v})
    l.importe = round(sum(meses.values()), 2)


def amortizacion(b: Budget) -> dict[str, float]:
    """Cuota mensual de las partidas CAPEX dentro del periodo: cada pago, entre su vida."""
    salida: dict[str, float] = {}
    periodo = meses_de(b)
    for l in b.lines:
        if l.naturaleza != "capex" or l.sentido != "gasto" or not l.vida_meses:
            continue
        for mes_pago, importe in json.loads(l.meses or "{}").items():
            cuota = float(importe) / int(l.vida_meses)
            i = periodo.index(mes_pago) if mes_pago in periodo else None
            if i is None:
                continue
            for m in periodo[i:i + int(l.vida_meses)]:
                salida[m] = round(salida.get(m, 0.0) + cuota, 2)
    return salida


# ── Jerarquía y techo ─────────────────────────────────────────────────────────

def _ultima(db: Session, origen: str) -> Optional[Budget]:
    return (db.query(Budget).filter((Budget.origen_id == origen) | (Budget.id == origen))
            .order_by(Budget.version.desc()).first())


def total_de_gasto(b: Budget) -> float:
    return round(sum(l.importe for l in b.lines if l.sentido != "ingreso"), 2)


def total_de_ingreso(b: Budget) -> float:
    return round(sum(l.importe for l in b.lines if l.sentido == "ingreso"), 2)


def hijos(db: Session, b: Budget) -> list[Budget]:
    """La última versión de cada presupuesto que consume de éste (activos)."""
    origen = b.origen_id or b.id
    salida = {}
    for h in db.query(Budget).filter(Budget.padre_id == origen).all():
        clave = h.origen_id or h.id
        if clave not in salida or h.version > salida[clave].version:
            salida[clave] = h
    return [h for h in salida.values() if h.estado in ACTIVOS]


def estado_del_techo(db: Session, b: Budget) -> Optional[dict]:
    if b.techo is None:
        return None
    consumido = round(sum(total_de_gasto(h) for h in hijos(db, b)), 2)
    return {"techo": b.techo, "consumido_por_hijos": consumido, "disponible": round(b.techo - consumido, 2),
            "excedido": consumido > b.techo + 0.005}


def consolidado(db: Session, b: Budget, _visto: Optional[set] = None) -> float:
    """Plan de gasto propio más el de todos sus hijos (y los hijos de éstos)."""
    visto = _visto if _visto is not None else set()
    if b.id in visto:
        return 0.0
    visto.add(b.id)
    return round(total_de_gasto(b) + sum(consolidado(db, h, visto) for h in hijos(db, b)), 2)


def padre_por_defecto(db: Session, d: dict) -> Optional[str]:
    """Departamento → el de su área; proyecto → el de su departamento (o el de su área)."""
    from app.models.project import Project
    from app.models.settings import Department
    year = d["periodo_desde"].year

    def vigente(ambito, **filtro):
        q = db.query(Budget).filter(Budget.ambito == ambito, Budget.year == year, Budget.escenario == "base",
                                    Budget.estado.in_(ACTIVOS))
        for k, v in filtro.items():
            q = q.filter(getattr(Budget, k) == v)
        b = q.order_by(Budget.version.desc()).first()
        return (b.origen_id or b.id) if b else None

    if d["ambito"] == "departamento" and d.get("department"):
        dep = db.query(Department).filter(Department.name == d["department"]).first()
        return vigente("area", area_id=dep.area_id) if dep and dep.area_id else None
    if d["ambito"] in ("proyecto", "proyecto_previsto"):
        nombre_dep = d.get("department")
        if not nombre_dep and d.get("project_id"):
            nombre_dep = db.query(Project.department).filter(Project.id == d["project_id"]).scalar()
        if not nombre_dep:
            return None
        padre = vigente("departamento", department=nombre_dep)
        if padre:
            return padre
        dep = db.query(Department).filter(Department.name == nombre_dep).first()
        return vigente("area", area_id=dep.area_id) if dep and dep.area_id else None
    return None


def validar_padre(db: Session, ambito: str, padre_id: Optional[str]) -> None:
    if not padre_id:
        return
    padre = _ultima(db, padre_id)
    if padre is None:
        raise HTTPException(400, "El presupuesto padre no existe")
    if NIVEL[padre.ambito] >= NIVEL[ambito]:
        raise HTTPException(400, "El padre tiene que ser de un nivel superior (área > departamento > proyecto)")


def comprobar_techo_del_padre(db: Session, b: Budget) -> Optional[str]:
    """Aviso (o 409 con BUDGET_CEILING_POLICY = bloquear) si el padre se pasa de su techo."""
    if not b.padre_id:
        return None
    padre = _ultima(db, b.padre_id)
    estado = estado_del_techo(db, padre) if padre else None
    if not estado or not estado["excedido"]:
        return None
    texto = (f"Con este presupuesto, los de «{padre.name}» suman {estado['consumido_por_hijos']} "
             f"y su techo es {estado['techo']}")
    if _aj(db, "BUDGET_CEILING_POLICY", b.organization_id).strip().lower() == "bloquear":
        raise HTTPException(409, texto)
    return texto


# ── Justificación ─────────────────────────────────────────────────────────────

def exigir_justificaciones(db: Session, b: Budget) -> None:
    minimo = float(_aj(db, "BUDGET_JUSTIFICATION_MIN_AMOUNT", b.organization_id) or 0)
    if minimo <= 0:
        return
    faltan = [l.descripcion for l in b.lines if l.importe >= minimo and not (l.justificacion or "").strip()]
    if faltan:
        raise HTTPException(400, f"Las partidas de {minimo:g} o más necesitan justificación: {', '.join(faltan[:5])}")


# ── Copiar, plantillas y escenarios ───────────────────────────────────────────

_CAMPOS_DE_PARTIDA = ("tipo", "descripcion", "sentido", "naturaleza", "vida_meses", "user_id", "perfil", "horas",
                      "coste_hora", "unidades", "precio_unitario", "recurrencia", "dedicacion_pct", "pais",
                      "salario_anual", "justificacion")


def partida_como_dict(l: BudgetLine) -> dict:
    d = {k: getattr(l, k) for k in _CAMPOS_DE_PARTIDA}
    d["importe"] = l.importe
    d["fecha_alta"] = l.fecha_alta.isoformat() if l.fecha_alta else None
    return d


def nueva_partida(db: Session, b: Budget, datos: dict, meses: Optional[dict] = None) -> BudgetLine:
    l = BudgetLine(organization_id=b.organization_id, budget_id=b.id, tipo=datos.get("tipo"),
                   descripcion=datos.get("descripcion") or "", importe=datos.get("importe") or 0)
    for k in _CAMPOS_DE_PARTIDA:
        if k in datos and datos[k] not in ("", None):
            setattr(l, k, datos[k])
    if datos.get("fecha_alta"):
        l.fecha_alta = date.fromisoformat(str(datos["fecha_alta"])[:10])
    b.lines.append(l)
    calcular(db, b, l, meses)
    return l


def copiar_de_otro(db: Session, destino: Budget, origen: Budget, base: str, ajuste_pct: float) -> None:
    """Partidas a partir de otro presupuesto (p. ej. el del año anterior).

    `base = "plan"`: sus partidas, con el mismo modo de cálculo, ajustado un %.
    `base = "real"`: una partida por tipo con lo gastado de verdad, mes a mes
    (el mismo mes del año siguiente), ajustado un %.
    """
    from app.services.budgets_service import _real_mensual
    factor = 1 + float(ajuste_pct or 0) / 100
    periodo = set(meses_de(destino))
    if base == "plan":
        for l in origen.lines:
            d = partida_como_dict(l)
            for k in ("importe", "precio_unitario", "salario_anual", "coste_hora"):
                if d.get(k) is not None:
                    d[k] = round(float(d[k]) * factor, 2)
            if l.unidades is None and l.salario_anual is None and l.horas is None and not (l.user_id and l.dedicacion_pct):
                desplaza = destino.periodo_desde.year - origen.periodo_desde.year
                meses = {f"{int(m[:4]) + desplaza}-{m[5:]}": round(float(v) * factor, 2)
                         for m, v in json.loads(l.meses or "{}").items()}
                meses = {m: v for m, v in meses.items() if m in periodo}
                if meses:
                    d["importe"] = round(sum(meses.values()), 2)
                    nueva_partida(db, destino, d, meses)
                continue
            nueva_partida(db, destino, d)
    elif base == "real":
        desplaza = destino.periodo_desde.year - origen.periodo_desde.year
        por_tipo: dict[str, dict[str, float]] = {}
        for mes, tipos in _real_mensual(db, origen).items():
            nuevo = f"{int(mes[:4]) + desplaza}-{mes[5:]}"
            if nuevo not in periodo:
                continue
            for t, v in tipos.items():
                por_tipo.setdefault(t, {})[nuevo] = round(float(v) * factor, 2)
        for t, meses in por_tipo.items():
            if sum(meses.values()):
                nueva_partida(db, destino, {"tipo": t, "descripcion": f"{t} (real de {origen.year})",
                                            "importe": round(sum(meses.values()), 2)}, meses)
    else:
        raise HTTPException(400, "base es «plan» o «real»")


def aplicar_plantilla(db: Session, b: Budget, plantilla: BudgetTemplate) -> None:
    for d in json.loads(plantilla.partidas or "[]"):
        nueva_partida(db, b, d)


def comparar(db: Session, ids: list[str]) -> dict:
    """Plan de gasto, ingreso y margen de varios presupuestos (versiones o escenarios), por tipo y mes."""
    salida = []
    for bid in ids:
        b = db.query(Budget).filter(Budget.id == bid).first()
        if b is None:
            raise HTTPException(404, f"Presupuesto {bid} no encontrado")
        por_tipo: dict[str, float] = {}
        por_mes: dict[str, float] = {}
        for l in b.lines:
            if l.sentido == "ingreso":
                continue
            por_tipo[l.tipo] = round(por_tipo.get(l.tipo, 0) + l.importe, 2)
            for m, v in json.loads(l.meses or "{}").items():
                por_mes[m] = round(por_mes.get(m, 0) + float(v), 2)
        gasto, ingreso = total_de_gasto(b), total_de_ingreso(b)
        salida.append({"id": b.id, "name": b.name, "version": b.version, "escenario": b.escenario, "estado": b.estado,
                       "gasto": gasto, "ingreso": ingreso, "margen": round(ingreso - gasto, 2),
                       "por_tipo": por_tipo, "por_mes": por_mes, "supuestos": supuestos(b)})
    return {"presupuestos": salida}


# ── Campaña ───────────────────────────────────────────────────────────────────

def recordar_campana(db: Session) -> int:
    """Avisa a los responsables de presupuestos sin enviar cuando la fecha límite se acerca."""
    from app.services.notifications import notify_user
    hoy = timeutil.today()
    avisos = 0
    for c in db.query(BudgetCampaign).filter(BudgetCampaign.abierta.is_(True)).all():
        dias = (c.fecha_limite - hoy).days
        margen = int(_aj(db, "BUDGET_CAMPAIGN_REMINDER_DAYS", c.organization_id) or 0)
        if dias < 0 or dias > margen:
            continue
        ultimas: dict[str, Budget] = {}
        for b in db.query(Budget).filter(Budget.campana_id == c.id).all():
            clave = b.origen_id or b.id
            if clave not in ultimas or b.version > ultimas[clave].version:
                ultimas[clave] = b
        for b in ultimas.values():
            if b.estado not in ("borrador", "rechazado"):
                continue
            quien = b.responsable_id or b.created_by
            if quien and notify_user(db, quien, "budget_warning", f"Presupuesto «{b.name}» sin enviar",
                                     f"La campaña «{c.nombre}» cierra el {c.fecha_limite.isoformat()} "
                                     f"({dias} días).", "budgets", b.id, f"/budgets?id={b.id}"):
                avisos += 1
    db.commit()
    return avisos
