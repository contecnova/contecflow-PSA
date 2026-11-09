"""Presupuestos: partidas por meses, real calculado, versiones y aprobación (revisión 2026-11).

Un presupuesto es de un **proyecto**, de un **proyecto previsto** (todavía no
existe: se vincula cuando se crea), de un **departamento** o de un **área**
(varios departamentos). Su plan son sus **partidas** —personal (persona o
perfil × horas × coste/hora), licencias, subcontratación… (`BUDGET_LINE_TYPES`)—
repartidas por meses dentro de su periodo.

El **real se calcula**, no se teclea:
- personal: el coste de las imputaciones del ámbito en el mes (lo que guardó
  la imputación; si no, horas × la tarifa de entonces; si no, la de la persona);
- el resto: los gastos aprobados o reembolsados del ámbito, cada uno en el
  tipo de partida de su categoría (`BUDGET_EXPENSE_TYPE_MAP`); en un proyecto
  cuenta la parte del reparto entre proyectos.

**Versiones**: una reprevisión copia el presupuesto con `version` + 1; al
aprobarse, la versión aprobada anterior queda `sustituido`.

**Aprobación**: enviar abre una solicitud en la bandeja si hay flujo para
`budget`; la decisión se aplica aquí. Sin flujo, aprueban los roles de
`BUDGET_APPROVER_ROLES` desde la propia pantalla.
"""
from __future__ import annotations

import json
from datetime import date, datetime, timezone
from typing import Optional

from fastapi import HTTPException

from app.core import timeutil
from sqlalchemy.orm import Session, joinedload

from app.models.mfa import Budget, BudgetLine
from app.services.audit import audit_log

AMBITOS = ("proyecto", "proyecto_previsto", "departamento", "area")
EDITABLE = ("borrador", "rechazado")


# ── Ajustes ───────────────────────────────────────────────────────────────────

def _aj(db: Session, clave: str, org) -> str:
    from app.services.settings_service import get_runtime_str
    return str(get_runtime_str(db, clave, org) or "")


def _csv(db: Session, clave: str, org) -> list[str]:
    return [x.strip() for x in _aj(db, clave, org).split(",") if x.strip()]


def tipos(db: Session, org) -> list[str]:
    return _csv(db, "BUDGET_LINE_TYPES", org)


def _rol(u) -> str:
    return str(getattr(u.role, "value", u.role))


def puede_gestionar(db: Session, u) -> bool:
    return _rol(u) in _csv(db, "BUDGET_MANAGER_ROLES", u.organization_id)


def puede_aprobar(db: Session, u) -> bool:
    return _rol(u) in _csv(db, "BUDGET_APPROVER_ROLES", u.organization_id)


def _exigir_gestor(db: Session, u) -> None:
    if not puede_gestionar(db, u):
        raise HTTPException(403, "Tu rol no gestiona presupuestos (lo decide BUDGET_MANAGER_ROLES en Admin)")


# ── Meses ─────────────────────────────────────────────────────────────────────

def _primero(d) -> date:
    if isinstance(d, str):
        d = date.fromisoformat(d[:10])
    return date(d.year, d.month, 1)


def meses_del_periodo(desde: date, hasta: date) -> list[str]:
    salida, y, m = [], desde.year, desde.month
    while (y, m) <= (hasta.year, hasta.month):
        salida.append(f"{y}-{m:02d}")
        y, m = (y, m + 1) if m < 12 else (y + 1, 1)
    return salida


def repartir_por_igual(importe: float, meses: list[str]) -> dict[str, float]:
    """Partes iguales en céntimos; el redondeo va al último mes para que sumen exacto."""
    if not meses:
        return {}
    cada = round(importe / len(meses), 2)
    salida = {m: cada for m in meses}
    salida[meses[-1]] = round(importe - cada * (len(meses) - 1), 2)
    return salida


def _mes_actual() -> str:
    hoy = timeutil.today()
    return f"{hoy.year}-{hoy.month:02d}"


# ── Lectura ───────────────────────────────────────────────────────────────────

def _cargar(db: Session, budget_id: str) -> Budget:
    b = db.query(Budget).options(joinedload(Budget.lines)).filter(Budget.id == budget_id).first()
    if b is None:
        raise HTTPException(404, "Presupuesto no encontrado")
    return b


def _linea_dict(l: BudgetLine) -> dict:
    return {"id": l.id, "tipo": l.tipo, "descripcion": l.descripcion, "user_id": l.user_id,
            "user_name": l.user.full_name if l.user else None, "perfil": l.perfil, "horas": l.horas,
            "coste_hora": l.coste_hora, "importe": l.importe, "meses": json.loads(l.meses or "{}")}


def _plan_mensual(b: Budget) -> dict[str, dict[str, float]]:
    plan: dict[str, dict[str, float]] = {}
    for l in b.lines:
        for mes, imp in json.loads(l.meses or "{}").items():
            plan.setdefault(mes, {})
            plan[mes][l.tipo] = round(plan[mes].get(l.tipo, 0.0) + float(imp), 2)
    return plan


def _usuarios_del_ambito(db: Session, b: Budget) -> Optional[list[str]]:
    from app.models.user import User
    if b.ambito == "departamento":
        departamentos = [b.department] if b.department else []
    elif b.ambito == "area":
        departamentos = [d.strip() for d in (b.area or "").split(",") if d.strip()]
    else:
        return None
    if not departamentos:
        return []
    return [uid for (uid,) in db.query(User.id).filter(User.department.in_(departamentos)).all()]


def _real_mensual(db: Session, b: Budget) -> dict[str, dict[str, float]]:
    """{mes: {tipo: importe}} calculado de imputaciones y gastos del ámbito."""
    from app.models.expenses import Expense
    from app.models.imputation import Imputation
    from app.models.user import User
    from app.services.gastos_avanzados import COSTE, importe_por_proyecto
    if not (b.periodo_desde and b.periodo_hasta):
        return {}
    proyecto = b.project_id if b.ambito in ("proyecto", "proyecto_previsto") else None
    usuarios = _usuarios_del_ambito(db, b)
    if b.ambito in ("proyecto", "proyecto_previsto") and not proyecto:
        return {}       # un proyecto previsto sin vincular no tiene real todavía
    desde = b.periodo_desde
    hasta_y, hasta_m = b.periodo_hasta.year, b.periodo_hasta.month
    hasta = date(hasta_y + (hasta_m == 12), 1 if hasta_m == 12 else hasta_m + 1, 1)
    real: dict[str, dict[str, float]] = {}

    def sumar(fecha, tipo, importe):
        mes = f"{fecha.year}-{fecha.month:02d}"
        real.setdefault(mes, {})
        real[mes][tipo] = round(real[mes].get(tipo, 0.0) + float(importe), 2)

    # Personal: imputaciones.
    q = db.query(Imputation).filter(Imputation.date >= desde, Imputation.date < hasta)
    q = q.filter(Imputation.project_id == proyecto) if proyecto else q.filter(Imputation.user_id.in_(usuarios or [""]))
    tarifas = dict(db.query(User.id, User.hourly_rate).all())
    tipos_validos = set(tipos(db, b.organization_id))
    tipo_personal = "personal" if "personal" in tipos_validos else None
    if tipo_personal:
        for i in q.all():
            coste = (float(i.cost_amount) if i.cost_amount is not None
                     else float(i.hours or 0) * float(i.hourly_rate_snapshot or tarifas.get(i.user_id) or 0))
            sumar(i.date, tipo_personal, coste)
    # El resto: gastos por su categoría.
    mapa = {}
    for par in _csv(db, "BUDGET_EXPENSE_TYPE_MAP", b.organization_id):
        if ":" in par:
            k, v = par.split(":", 1)
            mapa[k.strip()] = v.strip()
    gq = db.query(Expense).filter(Expense.status.in_(COSTE), Expense.expense_date >= desde, Expense.expense_date < hasta)
    if proyecto:
        from sqlalchemy import or_

        from app.models.expenses import ExpenseAllocation
        por_reparto = db.query(ExpenseAllocation.expense_id).filter(ExpenseAllocation.project_id == proyecto)
        gastos = importe_por_proyecto(db, gq.filter(or_(Expense.project_id == proyecto,
                                                        Expense.id.in_(por_reparto))).all(), proyecto)
    else:
        gastos = [(g, float(g.amount)) for g in gq.filter(Expense.user_id.in_(usuarios or [""])).all()]
    for g, importe in gastos:
        cat = str(getattr(g.category, "value", g.category))
        tipo = mapa.get(cat) if mapa.get(cat) in tipos_validos else ("otros" if "otros" in tipos_validos else cat)
        sumar(g.expense_date, tipo, importe)
    return real


def informe(db: Session, b: Budget) -> dict:
    """Plan contra real por mes y por tipo, desviación y previsión al cierre."""
    plan, real = _plan_mensual(b), _real_mensual(db, b)
    meses = meses_del_periodo(b.periodo_desde, b.periodo_hasta) if b.periodo_desde and b.periodo_hasta else []
    actual = _mes_actual()
    filas, prevision = [], 0.0
    for m in meses:
        p, r = round(sum(plan.get(m, {}).values()), 2), round(sum(real.get(m, {}).values()), 2)
        cerrado = m < actual
        prevision += r if m <= actual else p
        filas.append({"mes": m, "plan": p, "real": r, "desviacion": round(r - p, 2), "cerrado": cerrado,
                      "en_curso": m == actual})
    todos_tipos = sorted({t for d in list(plan.values()) + list(real.values()) for t in d})
    por_tipo = []
    for t in todos_tipos:
        p = round(sum(d.get(t, 0) for d in plan.values()), 2)
        r = round(sum(d.get(t, 0) for d in real.values()), 2)
        por_tipo.append({"tipo": t, "plan": p, "real": r, "desviacion": round(r - p, 2),
                         "desviacion_pct": round((r - p) / p * 100, 1) if p else None})
    total_plan = round(sum(f["plan"] for f in filas), 2)
    total_real = round(sum(f["real"] for f in filas), 2)
    plan_a_hoy = round(sum(f["plan"] for f in filas if f["mes"] <= actual), 2)
    return {"meses": filas, "por_tipo": por_tipo, "total_plan": total_plan, "total_real": total_real,
            "plan_hasta_hoy": plan_a_hoy, "desviacion_hasta_hoy": round(total_real - plan_a_hoy, 2),
            "prevision_cierre": round(prevision, 2),
            "sin_real": b.ambito == "proyecto_previsto" and not b.project_id}


def _cabecera(b: Budget) -> dict:
    return {"id": b.id, "name": b.name, "year": b.year, "ambito": b.ambito, "department": b.department,
            "area": b.area, "project_id": b.project_id, "project_name": b.project.name if b.project else None,
            "cliente_id": b.cliente_id, "tipo_proyecto": b.tipo_proyecto,
            "periodo_desde": b.periodo_desde.isoformat() if b.periodo_desde else None,
            "periodo_hasta": b.periodo_hasta.isoformat() if b.periodo_hasta else None,
            "currency": b.currency, "notes": b.notes, "version": b.version, "origen_id": b.origen_id or b.id,
            "estado": b.estado, "motivo_rechazo": b.motivo_rechazo,
            "approved_at": b.approved_at.isoformat() if b.approved_at else None,
            "total_plan": round(sum(l.importe for l in b.lines), 2)}


def detalle(db: Session, u, budget_id: str) -> dict:
    from app.services.approval_engine import fuentes
    b = _cargar(db, budget_id)
    versiones = (db.query(Budget).filter(Budget.origen_id == (b.origen_id or b.id))
                 .order_by(Budget.version).all())
    return {**_cabecera(b), "lineas": [_linea_dict(l) for l in b.lines], "informe": informe(db, b),
            "versiones": [{"id": v.id, "version": v.version, "estado": v.estado,
                           "total_plan": round(sum(l.importe for l in v.lines), 2)} for v in versiones],
            "aprobacion_en_bandeja": fuentes.estado(db, "budget", b.id),
            "puedo_editar": puede_gestionar(db, u) and b.estado in EDITABLE,
            "puedo_aprobar": puede_aprobar(db, u) and b.estado == "enviado",
            "tipos": tipos(db, b.organization_id)}


def _vigentes(db: Session, year=None, ambito=None, *, aprobada_primero: bool = False) -> list[Budget]:
    """Una versión por presupuesto: la última, o —para los totales— la aprobada si la hay."""
    q = db.query(Budget).options(joinedload(Budget.lines))
    if year:
        q = q.filter(Budget.year == year)
    if ambito:
        q = q.filter(Budget.ambito == ambito)
    elegidos: dict[str, Budget] = {}
    for b in q.all():
        clave = b.origen_id or b.id
        actual = elegidos.get(clave)
        if actual is None:
            elegidos[clave] = b
        elif aprobada_primero and (b.estado == "aprobado") != (actual.estado == "aprobado"):
            if b.estado == "aprobado":
                elegidos[clave] = b
        elif b.version > actual.version:
            elegidos[clave] = b
    return list(elegidos.values())


def listar(db: Session, u, *, year: Optional[int] = None, ambito: Optional[str] = None,
           estado: Optional[str] = None, aprobada_primero: bool = False) -> list[dict]:
    """La última versión de cada presupuesto, con su plan, su real y la desviación."""
    ultimos = {b.id: b for b in _vigentes(db, year, ambito, aprobada_primero=aprobada_primero)}
    salida = []
    for b in sorted(ultimos.values(), key=lambda x: (-(x.year or 0), x.name)):
        if estado and b.estado != estado:
            continue
        inf = informe(db, b)
        salida.append({**_cabecera(b), "total_real": inf["total_real"], "plan_hasta_hoy": inf["plan_hasta_hoy"],
                       "desviacion_hasta_hoy": inf["desviacion_hasta_hoy"], "prevision_cierre": inf["prevision_cierre"]})
    return salida


def resumen(db: Session, u, year: Optional[int] = None) -> dict:
    """Totales del ejercicio sobre la última versión aprobada (o la vigente si ninguna lo está)."""
    yr = year or timeutil.today().year
    lista = listar(db, u, year=yr, aprobada_primero=True)
    por_mes: dict[str, dict] = {}
    for item in lista:
        for f in informe(db, _cargar(db, item["id"]))["meses"]:
            if not f["mes"].startswith(str(yr)):
                continue
            d = por_mes.setdefault(f["mes"], {"mes": f["mes"], "plan": 0.0, "real": 0.0})
            d["plan"] = round(d["plan"] + f["plan"], 2)
            d["real"] = round(d["real"] + f["real"], 2)
    return {"year": yr, "presupuestos": len(lista),
            "aprobados": sum(1 for x in lista if x["estado"] == "aprobado"),
            "total_plan": round(sum(x["total_plan"] for x in lista), 2),
            "total_real": round(sum(x["total_real"] for x in lista), 2),
            "plan_hasta_hoy": round(sum(x["plan_hasta_hoy"] for x in lista), 2),
            "prevision_cierre": round(sum(x["prevision_cierre"] for x in lista), 2),
            "por_mes": [por_mes[m] for m in sorted(por_mes)]}


# ── Alta y cabecera ───────────────────────────────────────────────────────────

_CABECERA = ("name", "ambito", "department", "area", "project_id", "cliente_id", "tipo_proyecto",
             "periodo_desde", "periodo_hasta", "currency", "notes")


def _validar_cabecera(db: Session, u, d: dict) -> None:
    from app.services.project_service import get_project_scoped_or_404
    if d.get("ambito") not in AMBITOS:
        raise HTTPException(400, f"Ámbito no válido: {d.get('ambito')}")
    if d["ambito"] == "proyecto":
        if not d.get("project_id"):
            raise HTTPException(400, "Elige el proyecto")
        get_project_scoped_or_404(db, d["project_id"], u)
    if d["ambito"] == "departamento" and not d.get("department"):
        raise HTTPException(400, "Elige el departamento")
    if d["ambito"] == "area" and not (d.get("area") or "").strip():
        raise HTTPException(400, "Indica los departamentos del área")
    if not (d.get("periodo_desde") and d.get("periodo_hasta")):
        raise HTTPException(400, "Indica el periodo")
    if _primero(d["periodo_hasta"]) < _primero(d["periodo_desde"]):
        raise HTTPException(400, "El periodo acaba antes de empezar")


def crear(db: Session, u, datos: dict) -> dict:
    _exigir_gestor(db, u)
    d = {k: datos.get(k) for k in _CABECERA if datos.get(k) not in (None, "")}
    _validar_cabecera(db, u, d)
    d["periodo_desde"], d["periodo_hasta"] = _primero(d["periodo_desde"]), _primero(d["periodo_hasta"])
    if not d.get("name"):
        raise HTTPException(400, "Ponle un nombre")
    b = Budget(organization_id=u.organization_id, created_by=u.id, year=d["periodo_desde"].year, total_amount=0,
               estado="borrador", version=1, **d)
    db.add(b)
    db.flush()
    b.origen_id = b.id
    audit_log(db, u, "CREATE", "budgets", b.id, b.name, new_values={"ambito": b.ambito})
    db.commit()
    return detalle(db, u, b.id)


def _editable(db: Session, u, b: Budget) -> None:
    _exigir_gestor(db, u)
    if b.estado not in EDITABLE:
        raise HTTPException(409, "Sólo se cambia un presupuesto en borrador o rechazado: haz una versión nueva")


def editar(db: Session, u, budget_id: str, datos: dict) -> dict:
    b = _cargar(db, budget_id)
    _editable(db, u, b)
    d = {**{k: getattr(b, k) for k in _CABECERA}, **{k: v for k, v in datos.items() if k in _CABECERA}}
    _validar_cabecera(db, u, d)
    antes = {k: str(getattr(b, k)) for k in _CABECERA}
    for k in _CABECERA:
        if k in datos:
            v = datos[k]
            setattr(b, k, _primero(v) if k.startswith("periodo_") and v else (v if v != "" else None))
    b.year = b.periodo_desde.year
    validos = set(meses_del_periodo(b.periodo_desde, b.periodo_hasta))
    for l in b.lines:      # un mes que queda fuera del periodo no puede seguir planificado
        meses = json.loads(l.meses or "{}")
        if set(meses) - validos:
            l.meses = json.dumps(repartir_por_igual(l.importe, sorted(validos)))
    audit_log(db, u, "UPDATE", "budgets", b.id, b.name, old_values=antes,
              new_values={k: str(getattr(b, k)) for k in _CABECERA})
    db.commit()
    return detalle(db, u, b.id)


# ── Partidas ──────────────────────────────────────────────────────────────────

def _preparar_linea(db: Session, b: Budget, l: BudgetLine, datos: dict) -> None:
    from app.models.user import User
    for k in ("tipo", "descripcion", "user_id", "perfil", "horas", "coste_hora", "importe"):
        if k in datos:
            setattr(l, k, datos[k] if datos[k] != "" else None)
    if l.tipo not in tipos(db, b.organization_id):
        raise HTTPException(400, f"Tipo de partida no válido: {l.tipo} (los de BUDGET_LINE_TYPES)")
    if not (l.descripcion or "").strip():
        raise HTTPException(400, "Describe la partida")
    if l.horas is not None:
        if l.coste_hora is None and l.user_id:
            l.coste_hora = db.query(User.hourly_rate).filter(User.id == l.user_id).scalar()
        if l.coste_hora is None:
            raise HTTPException(400, "Con horas hace falta el coste por hora (o una persona con su coste)")
        l.importe = round(float(l.horas) * float(l.coste_hora), 2)
    if l.importe is None or float(l.importe) < 0:
        raise HTTPException(400, "El importe tiene que ser cero o positivo")
    validos = meses_del_periodo(b.periodo_desde, b.periodo_hasta)
    meses = datos.get("meses")
    if meses:
        fuera = set(meses) - set(validos)
        if fuera:
            raise HTTPException(400, f"Meses fuera del periodo: {', '.join(sorted(fuera))}")
        suma = round(sum(float(v) for v in meses.values()), 2)
        if abs(suma - float(l.importe)) > 0.01:
            raise HTTPException(400, f"El reparto por meses suma {suma} y la partida es {l.importe}")
        l.meses = json.dumps({k: round(float(v), 2) for k, v in meses.items() if float(v)})
    else:
        l.meses = json.dumps(repartir_por_igual(float(l.importe), validos))


def crear_linea(db: Session, u, budget_id: str, datos: dict) -> dict:
    b = _cargar(db, budget_id)
    _editable(db, u, b)
    l = BudgetLine(organization_id=b.organization_id, budget_id=b.id, tipo=datos.get("tipo"),
                   descripcion=datos.get("descripcion") or "", importe=datos.get("importe") or 0)
    _preparar_linea(db, b, l, datos)
    db.add(l)
    db.commit()
    return detalle(db, u, b.id)


def editar_linea(db: Session, u, budget_id: str, linea_id: str, datos: dict) -> dict:
    b = _cargar(db, budget_id)
    _editable(db, u, b)
    l = next((x for x in b.lines if x.id == linea_id), None)
    if l is None:
        raise HTTPException(404, "Partida no encontrada")
    _preparar_linea(db, b, l, datos)
    db.commit()
    return detalle(db, u, b.id)


def borrar_linea(db: Session, u, budget_id: str, linea_id: str) -> dict:
    b = _cargar(db, budget_id)
    _editable(db, u, b)
    l = next((x for x in b.lines if x.id == linea_id), None)
    if l is None:
        raise HTTPException(404, "Partida no encontrada")
    db.delete(l)
    db.commit()
    return detalle(db, u, b.id)


# ── Versiones, aprobación y vínculo ───────────────────────────────────────────

def enviar(db: Session, u, budget_id: str) -> dict:
    from app.services.approval_engine import fuentes
    b = _cargar(db, budget_id)
    _editable(db, u, b)
    if not b.lines:
        raise HTTPException(400, "Un presupuesto sin partidas no se envía")
    b.estado, b.motivo_rechazo = "enviado", None
    audit_log(db, u, "SUBMIT", "budgets", b.id, b.name)
    db.commit()
    total = round(sum(l.importe for l in b.lines), 2)
    fuentes.abrir(db, "budget", b.id, f"Presupuesto {b.name} v{b.version} · {total} {b.currency}", u.id,
                  {"amount": total, "category": b.ambito, "project_id": b.project_id})
    return detalle(db, u, b.id)


def decidir(db: Session, u, budget_id: str, aprobado: bool, motivo: Optional[str] = None,
            desde_bandeja: bool = False) -> dict:
    from app.services.approval_engine import fuentes
    b = _cargar(db, budget_id)
    if not desde_bandeja and not puede_aprobar(db, u):
        raise HTTPException(403, "Aprobar presupuestos es de los roles de BUDGET_APPROVER_ROLES")
    if b.estado != "enviado":
        raise HTTPException(409, "Sólo se decide un presupuesto enviado")
    if aprobado:
        for previa in db.query(Budget).filter(Budget.origen_id == (b.origen_id or b.id), Budget.id != b.id,
                                              Budget.estado == "aprobado").all():
            previa.estado = "sustituido"
        b.estado, b.is_approved = "aprobado", True
        b.approved_by, b.approved_at = u.id, datetime.now(timezone.utc)
    else:
        if not (motivo or "").strip():
            raise HTTPException(400, "Indica el motivo del rechazo")
        b.estado, b.motivo_rechazo = "rechazado", motivo
    if not desde_bandeja:
        fuentes.cerrar(db, "budget", b.id, "approved" if aprobado else "rejected", f"Decidido en Presupuestos por {u.full_name}")
    audit_log(db, u, "APPROVE" if aprobado else "REJECT", "budgets", b.id, b.name,
              new_values={"estado": b.estado, "motivo": motivo})
    db.commit()
    return detalle(db, u, b.id)


def nueva_version(db: Session, u, budget_id: str) -> dict:
    _exigir_gestor(db, u)
    b = _cargar(db, budget_id)
    origen = b.origen_id or b.id
    ultima = max(v for (v,) in db.query(Budget.version).filter(Budget.origen_id == origen).all())
    if db.query(Budget).filter(Budget.origen_id == origen, Budget.estado.in_(("borrador", "enviado"))).first():
        raise HTTPException(409, "Ya hay una versión en curso de este presupuesto")
    n = Budget(organization_id=b.organization_id, created_by=u.id, total_amount=0, estado="borrador",
               version=ultima + 1, origen_id=origen, year=b.year, name=b.name, ambito=b.ambito,
               department=b.department, area=b.area, project_id=b.project_id, cliente_id=b.cliente_id,
               tipo_proyecto=b.tipo_proyecto, periodo_desde=b.periodo_desde, periodo_hasta=b.periodo_hasta,
               currency=b.currency, notes=b.notes)
    db.add(n)
    db.flush()
    for l in b.lines:
        db.add(BudgetLine(organization_id=l.organization_id, budget_id=n.id, tipo=l.tipo, descripcion=l.descripcion,
                          user_id=l.user_id, perfil=l.perfil, horas=l.horas, coste_hora=l.coste_hora,
                          importe=l.importe, meses=l.meses))
    audit_log(db, u, "CREATE", "budgets", n.id, n.name, new_values={"version": n.version, "desde": b.id})
    db.commit()
    return detalle(db, u, n.id)


def vincular_proyecto(db: Session, u, budget_id: str, project_id: str) -> dict:
    """Un proyecto previsto ya existe: el presupuesto (todas sus versiones) pasa a ser suyo."""
    from app.services.project_service import get_project_scoped_or_404
    _exigir_gestor(db, u)
    b = _cargar(db, budget_id)
    if b.ambito != "proyecto_previsto":
        raise HTTPException(409, "Sólo se vincula el presupuesto de un proyecto previsto")
    get_project_scoped_or_404(db, project_id, u)
    for v in db.query(Budget).filter(Budget.origen_id == (b.origen_id or b.id)).all():
        v.project_id = project_id
    audit_log(db, u, "UPDATE", "budgets", b.id, b.name, new_values={"vinculado_a": project_id})
    db.commit()
    return detalle(db, u, b.id)


def aplicar_desde_bandeja(db: Session, actor, budget_id: str, aprobado: bool, nota: Optional[str]) -> None:
    decidir(db, actor, budget_id, aprobado, nota or "Rechazado en la bandeja de aprobaciones", desde_bandeja=True)
