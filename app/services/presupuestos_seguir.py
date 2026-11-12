"""Presupuestos: seguir a fondo (revisión 2026-11).

Lo que hace falta para seguir un presupuesto aprobado mes a mes:

- **Comprometido**: lo que ya está pedido y aún no es real. Sale de los
  **pedidos** (`budget_commitments` en estado `comprometido`) y de los
  **contratos y licencias de ALM** del ámbito (por proyecto, o por el centro de
  coste del departamento), que cuentan su coste mensual de aquí al final del
  periodo o a su vencimiento, en el tipo `BUDGET_ALM_LINE_TYPE`. Un pedido
  **facturado** pasa a real en el mes de su factura.
- **Disponible** = plan − real − comprometido, por tipo.
- **Control**: al aprobar un gasto o al dar de alta un pedido se mira el
  disponible de su tipo en los presupuestos aprobados que lo cubren (proyecto,
  departamento de la persona y su área); `BUDGET_CONTROL_POLICY` decide si sólo
  avisa o si bloquea.
- **Cierre mensual**: congela el real del mes por tipo. Antes, cada desviación
  de un tipo que pase `BUDGET_VARIANCE_EXPLAIN_PCT` % y
  `BUDGET_VARIANCE_EXPLAIN_MIN_AMOUNT` necesita su explicación.
- **Reprevisión** por tipo: el plan restante, el ritmo real (media de los meses
  ya pasados) o a mano mes a mes; la previsión al cierre suma lo real hasta hoy
  y lo previsto del resto.
- **Traspasos** entre partidas y **ampliaciones** de un presupuesto aprobado,
  con aprobación (`BUDGET_APPROVER_ROLES`, o el flujo de `budget_transfer`) y
  sin que decida quien lo pide.
- El presupuesto aprobado de un proyecto fija su `budget_amount` (y sus horas):
  es lo que usan EVM, la rentabilidad y la salud del proyecto.
"""
from __future__ import annotations

import csv
import io
import json
from datetime import date, datetime, timezone
from typing import Optional

from sqlalchemy.orm import Session

from app.core import timeutil
from app.models.mfa import Budget, BudgetClose, BudgetCommitment, BudgetLine, BudgetTransfer, BudgetVarianceNote
from app.services.audit import audit_log
from app.core.errores import ErrorDeDominio

METODOS = ("plan", "ritmo", "manual")


def _aj(db: Session, clave: str, org) -> str:
    from app.services.settings_service import get_runtime_str
    return str(get_runtime_str(db, clave, org) or "")


def _num(db: Session, clave: str, org) -> float:
    try:
        return float(_aj(db, clave, org) or 0)
    except ValueError:
        return 0.0


def _mes(d) -> str:
    return f"{d.year}-{d.month:02d}"


def mes_actual() -> str:
    from app.services.budgets_service import _mes_actual
    return _mes_actual()


def _sumar(d: dict, mes: str, tipo: str, v: float) -> None:
    d.setdefault(mes, {})
    d[mes][tipo] = round(d[mes].get(tipo, 0.0) + float(v), 2)


def origen(b: Budget) -> str:
    return b.origen_id or b.id


def tipo_de_gasto(db: Session, org, categoria: str) -> str:
    """El tipo de partida en el que cuenta una categoría de gasto (`BUDGET_EXPENSE_TYPE_MAP`)."""
    from app.services.budgets_service import tipos
    validos = set(tipos(db, org))
    mapa = {}
    for par in _aj(db, "BUDGET_EXPENSE_TYPE_MAP", org).split(","):
        if ":" in par:
            k, v = par.split(":", 1)
            mapa[k.strip()] = v.strip()
    t = mapa.get(categoria)
    return t if t in validos else ("otros" if "otros" in validos else categoria)


# ── Ámbito ────────────────────────────────────────────────────────────────────

def _departamentos_del_ambito(db: Session, b: Budget) -> list[str]:
    from app.models.settings import Department
    if b.ambito == "departamento":
        return [b.department] if b.department else []
    if b.ambito == "area" and b.area_id:
        return [n for (n,) in db.query(Department.name).filter(Department.area_id == b.area_id).all()]
    return []


def _centros_de_coste(db: Session, b: Budget) -> list[str]:
    from app.models.alm import ALMCostCenter
    from app.models.settings import Department
    nombres = _departamentos_del_ambito(db, b)
    if not nombres:
        return []
    deps = [i for (i,) in db.query(Department.id).filter(Department.name.in_(nombres)).all()]
    return [i for (i,) in db.query(ALMCostCenter.id).filter(ALMCostCenter.department_id.in_(deps or [""])).all()]


# ── Comprometido ──────────────────────────────────────────────────────────────

def _meses_restantes(b: Budget, inicio: Optional[date], fin: Optional[date]) -> list[str]:
    from app.services.presupuestos_preparar import meses_de
    desde = max(mes_actual(), _mes(inicio) if inicio else "0000-00")
    hasta = _mes(fin) if fin else "9999-99"
    return [m for m in meses_de(b) if desde <= m <= hasta]


def comprometido_mensual(db: Session, b: Budget) -> dict[str, dict[str, float]]:
    """{mes: {tipo: importe}}: pedidos comprometidos y contratos/licencias de ALM pendientes."""
    from app.models.alm import ALMContract, ALMLicense
    from app.services.budgets_service import tipos
    salida: dict[str, dict[str, float]] = {}
    for c in db.query(BudgetCommitment).filter(BudgetCommitment.origen_id == origen(b),
                                               BudgetCommitment.estado == "comprometido").all():
        _sumar(salida, c.mes, c.tipo, c.importe)
    tipo_alm = _aj(db, "BUDGET_ALM_LINE_TYPE", b.organization_id).strip()
    if tipo_alm not in set(tipos(db, b.organization_id)):
        tipo_alm = "otros"
    proyecto = b.project_id if b.ambito in ("proyecto", "proyecto_previsto") else None
    centros = [] if proyecto else _centros_de_coste(db, b)
    if not proyecto and not centros:
        return salida
    from app.models.alm import ALMContractStatus, LicenseStatus
    contratos = db.query(ALMContract).filter(ALMContract.is_active.isnot(False), ALMContract.status.notin_(
        (ALMContractStatus.cancelled, ALMContractStatus.expired, ALMContractStatus.draft)))
    licencias = db.query(ALMLicense).filter(ALMLicense.is_active.isnot(False), ALMLicense.status.notin_(
        (LicenseStatus.cancelled, LicenseStatus.expired)))
    if proyecto:
        contratos = contratos.filter(ALMContract.project_id == proyecto)
        licencias = licencias.filter(ALMLicense.project_id == proyecto)
    else:
        contratos = contratos.filter(ALMContract.cost_center_id.in_(centros))
        licencias = licencias.filter(ALMLicense.cost_center_id.in_(centros))
    con_importe = set()
    for c in contratos.all():
        if c.annual_value:
            con_importe.add(c.id)
            for m in _meses_restantes(b, c.start_date, c.end_date):
                _sumar(salida, m, tipo_alm, round(float(c.annual_value) / 12, 2))
    for lic in licencias.all():
        if lic.annual_cost and lic.contract_id not in con_importe:   # la de un contrato ya cuenta en él
            for m in _meses_restantes(b, None, lic.expiry_date):
                _sumar(salida, m, tipo_alm, round(float(lic.annual_cost) / 12, 2))
    return salida


def real_de_pedidos(db: Session, b: Budget) -> dict[str, dict[str, float]]:
    salida: dict[str, dict[str, float]] = {}
    for c in db.query(BudgetCommitment).filter(BudgetCommitment.origen_id == origen(b),
                                               BudgetCommitment.estado == "facturado").all():
        if c.fecha_factura:
            _sumar(salida, _mes(c.fecha_factura), c.tipo, c.importe_facturado if c.importe_facturado is not None else c.importe)
    return salida


# ── Cierres, previsión y desviaciones ─────────────────────────────────────────

def cierres(db: Session, b: Budget) -> dict[str, dict[str, float]]:
    return {c.mes: json.loads(c.real or "{}") for c in db.query(BudgetClose).filter(BudgetClose.origen_id == origen(b)).all()}


def prevision(b: Budget) -> dict:
    try:
        return json.loads(b.prevision or "{}") or {}
    except ValueError:
        return {}


def prevision_por_mes(b: Budget, meses: list[str], plan: dict, real: dict, cerrados: set) -> dict[str, dict[str, float]]:
    """{mes: {tipo: importe}}: real en los meses pasados o cerrados; previsto (por su método) en el resto."""
    actual = mes_actual()
    pasados = [m for m in meses if m < actual or m in cerrados]
    tipos = sorted({t for d in list(plan.values()) + list(real.values()) for t in d})
    config = prevision(b)
    salida: dict[str, dict[str, float]] = {}
    for t in tipos:
        metodo = (config.get(t) or {}).get("metodo", "plan")
        manual = (config.get(t) or {}).get("meses") or {}
        ritmo = (round(sum(real.get(m, {}).get(t, 0.0) for m in pasados) / len(pasados), 2) if pasados else 0.0)
        for m in meses:
            if m in pasados:
                v = real.get(m, {}).get(t, 0.0)
            elif m == actual:   # el mes en curso: lo que ya hay, o el plan si es más
                v = max(real.get(m, {}).get(t, 0.0), plan.get(m, {}).get(t, 0.0) if metodo == "plan" else
                        (ritmo if metodo == "ritmo" else float(manual.get(m, 0.0))))
            else:
                v = (plan.get(m, {}).get(t, 0.0) if metodo == "plan" else ritmo if metodo == "ritmo"
                     else float(manual.get(m, 0.0)))
            if v:
                _sumar(salida, m, t, v)
    return salida


def desviaciones_a_explicar(db: Session, b: Budget, mes: str, plan: dict, real: dict) -> list[dict]:
    """Tipos de ese mes cuya desviación pasa los umbrales, con su explicación si la hay."""
    pct = _num(db, "BUDGET_VARIANCE_EXPLAIN_PCT", b.organization_id)
    minimo = _num(db, "BUDGET_VARIANCE_EXPLAIN_MIN_AMOUNT", b.organization_id)
    notas = {n.tipo: n for n in db.query(BudgetVarianceNote).filter(BudgetVarianceNote.origen_id == origen(b),
                                                                     BudgetVarianceNote.mes == mes).all()}
    salida = []
    for t in sorted(set(plan.get(mes, {})) | set(real.get(mes, {}))):
        p, r = plan.get(mes, {}).get(t, 0.0), real.get(mes, {}).get(t, 0.0)
        dif = round(r - p, 2)
        porcentaje = abs(dif) / p * 100 if p else (100.0 if dif else 0.0)
        if abs(dif) >= minimo and porcentaje >= pct and dif:
            n = notas.get(t)
            salida.append({"mes": mes, "tipo": t, "plan": p, "real": r, "desviacion": dif,
                           "desviacion_pct": round(porcentaje, 1) if p else None,
                           "explicacion": n.explicacion if n else None})
    return salida


def _informe_base(db: Session, b: Budget) -> tuple[list[str], dict, dict, set]:
    from app.services.budgets_service import _plan_mensual, _real_mensual
    from app.services.presupuestos_preparar import meses_de
    plan, real = _plan_mensual(b), _real_mensual(db, b)   # ya trae pedidos facturados y meses cerrados
    return meses_de(b), plan, real, {c for (c,) in db.query(BudgetClose.mes).filter(BudgetClose.origen_id == origen(b)).all()}


def _exigir_gestor(db: Session, u) -> None:
    from app.services.budgets_service import _exigir_gestor as exigir
    exigir(db, u)


def _cargar(db: Session, budget_id: str) -> Budget:
    from app.services.budgets_service import _cargar as cargar
    return cargar(db, budget_id)


def cerrar_mes(db: Session, u, budget_id: str, mes: str) -> None:
    _exigir_gestor(db, u)
    b = _cargar(db, budget_id)
    if b.estado != "aprobado":
        raise ErrorDeDominio(409, "Se cierran los meses de un presupuesto aprobado")
    if mes >= mes_actual():
        raise ErrorDeDominio(400, "Sólo se cierra un mes ya terminado")
    meses, plan, real, cerrados = _informe_base(db, b)
    if mes not in meses:
        raise ErrorDeDominio(400, "El mes no es del periodo del presupuesto")
    if mes in cerrados:
        raise ErrorDeDominio(409, "Ese mes ya está cerrado")
    faltan = [d for d in desviaciones_a_explicar(db, b, mes, plan, real) if not d["explicacion"]]
    if faltan:
        raise ErrorDeDominio(409, "Explica antes las desviaciones de: " + ", ".join(
            f"{d['tipo']} ({d['desviacion']:+g})" for d in faltan))
    db.add(BudgetClose(organization_id=b.organization_id, origen_id=origen(b), mes=mes,
                       real=json.dumps(real.get(mes, {})), cerrado_por=u.id))
    audit_log(db, u, "CLOSE", "budgets", b.id, b.name, new_values={"mes": mes, "real": real.get(mes, {})})
    db.commit()


def reabrir_mes(db: Session, u, budget_id: str, mes: str) -> None:
    from app.services.budgets_service import puede_aprobar
    if not puede_aprobar(db, u):
        raise ErrorDeDominio(403, "Reabrir un mes cerrado es de los roles de BUDGET_APPROVER_ROLES")
    b = _cargar(db, budget_id)
    c = db.query(BudgetClose).filter(BudgetClose.origen_id == origen(b), BudgetClose.mes == mes).first()
    if c is None:
        raise ErrorDeDominio(404, "Ese mes no está cerrado")
    db.delete(c)
    audit_log(db, u, "REOPEN", "budgets", b.id, b.name, new_values={"mes": mes})
    db.commit()


def explicar(db: Session, u, budget_id: str, mes: str, tipo: str, texto: str) -> None:
    _exigir_gestor(db, u)
    b = _cargar(db, budget_id)
    if not (texto or "").strip():
        raise ErrorDeDominio(400, "Escribe la explicación")
    n = db.query(BudgetVarianceNote).filter(BudgetVarianceNote.origen_id == origen(b), BudgetVarianceNote.mes == mes,
                                            BudgetVarianceNote.tipo == tipo).first()
    if n is None:
        n = BudgetVarianceNote(organization_id=b.organization_id, origen_id=origen(b), mes=mes, tipo=tipo, explicacion="")
        db.add(n)
    n.explicacion, n.autor_id = texto.strip(), u.id
    db.commit()


def guardar_prevision(db: Session, u, budget_id: str, tipo: str, metodo: str, meses: Optional[dict]) -> None:
    """Reprevisión de un tipo. Vale también en un presupuesto aprobado: no toca el plan."""
    _exigir_gestor(db, u)
    b = _cargar(db, budget_id)
    if metodo not in METODOS:
        raise ErrorDeDominio(400, f"Método de previsión no válido: {metodo}")
    config = prevision(b)
    config[tipo] = {"metodo": metodo, **({"meses": {k: round(float(v), 2) for k, v in (meses or {}).items()}}
                                         if metodo == "manual" else {})}
    b.prevision = json.dumps(config)
    audit_log(db, u, "UPDATE", "budgets", b.id, b.name, new_values={"prevision": {tipo: config[tipo]}})
    db.commit()


# ── Informe de seguimiento ────────────────────────────────────────────────────

def seguimiento(db: Session, b: Budget) -> dict:
    """Plan, real (congelado en los meses cerrados), comprometido, disponible y previsión."""
    meses, plan, real, cerrados = _informe_base(db, b)
    comp = comprometido_mensual(db, b)
    prev = prevision_por_mes(b, meses, plan, real, cerrados)
    tipos = sorted({t for d in list(plan.values()) + list(real.values()) + list(comp.values()) for t in d})
    por_tipo = []
    for t in tipos:
        p = round(sum(plan.get(m, {}).get(t, 0) for m in meses), 2)
        r = round(sum(real.get(m, {}).get(t, 0) for m in meses), 2)
        c = round(sum(comp.get(m, {}).get(t, 0) for m in meses), 2)
        f = round(sum(prev.get(m, {}).get(t, 0) for m in meses), 2)
        por_tipo.append({"tipo": t, "plan": p, "real": r, "comprometido": c, "disponible": round(p - r - c, 2),
                         "prevision": f, "metodo": (prevision(b).get(t) or {}).get("metodo", "plan"),
                         "consumo_pct": round((r + c) / p * 100, 1) if p else None})
    actual = mes_actual()
    pendientes = []
    for m in meses:
        if m < actual and m not in cerrados:
            pendientes += [d for d in desviaciones_a_explicar(db, b, m, plan, real) if not d["explicacion"]]
    total = lambda campo: round(sum(x[campo] for x in por_tipo), 2)  # noqa: E731
    return {"por_tipo": por_tipo, "plan": total("plan"), "real": total("real"), "comprometido": total("comprometido"),
            "disponible": total("disponible"), "prevision": total("prevision"),
            "meses_cerrados": sorted(cerrados),
            "meses_por_cerrar": [m for m in meses if m < actual and m not in cerrados],
            "comprometido_por_mes": {m: round(sum(v.values()), 2) for m, v in comp.items()},
            "prevision_por_mes": {m: round(sum(v.values()), 2) for m, v in prev.items()},
            "desviaciones_sin_explicar": pendientes,
            "traspasos_pendientes": db.query(BudgetTransfer).filter(BudgetTransfer.budget_id == b.id,
                                                                    BudgetTransfer.estado == "pendiente").count()}


def detalle_del_real(db: Session, b: Budget, mes: str, tipo: Optional[str] = None) -> list[dict]:
    """Lo que compone el real de un mes (y tipo): imputaciones, gastos, pedidos facturados."""
    from app.models.expenses import Expense
    from app.models.imputation import Imputation
    from app.models.user import User
    from app.services.budgets_service import _usuarios_del_ambito
    from app.services.gastos_avanzados import COSTE, importe_por_proyecto
    y, m = int(mes[:4]), int(mes[5:7])
    desde, hasta = date(y, m, 1), date(y + (m == 12), 1 if m == 12 else m + 1, 1)
    proyecto = b.project_id if b.ambito in ("proyecto", "proyecto_previsto") else None
    usuarios = _usuarios_del_ambito(db, b)
    nombres = dict(db.query(User.id, User.full_name).all())
    tarifas = dict(db.query(User.id, User.hourly_rate).all())
    salida: list[dict] = []
    if tipo in (None, "personal"):
        q = db.query(Imputation).filter(Imputation.date >= desde, Imputation.date < hasta)
        q = q.filter(Imputation.project_id == proyecto) if proyecto else q.filter(Imputation.user_id.in_(usuarios or [""]))
        for i in q.order_by(Imputation.date).all():
            coste = (float(i.cost_amount) if i.cost_amount is not None
                     else float(i.hours or 0) * float(i.hourly_rate_snapshot or tarifas.get(i.user_id) or 0))
            salida.append({"origen": "imputacion", "id": i.id, "fecha": i.date.isoformat(), "tipo": "personal",
                           "quien": nombres.get(i.user_id), "concepto": i.description or "", "horas": i.hours,
                           "importe": round(coste, 2), "project_id": i.project_id})
    gq = db.query(Expense).filter(Expense.status.in_(COSTE), Expense.expense_date >= desde, Expense.expense_date < hasta)
    if proyecto:
        from sqlalchemy import or_

        from app.models.expenses import ExpenseAllocation
        reparto = db.query(ExpenseAllocation.expense_id).filter(ExpenseAllocation.project_id == proyecto)
        gastos = importe_por_proyecto(db, gq.filter(or_(Expense.project_id == proyecto, Expense.id.in_(reparto))).all(), proyecto)
    else:
        gastos = [(g, float(g.amount)) for g in gq.filter(Expense.user_id.in_(usuarios or [""])).all()]
    for g, importe in gastos:
        t = tipo_de_gasto(db, b.organization_id, str(getattr(g.category, "value", g.category)))
        if tipo in (None, t):
            salida.append({"origen": "gasto", "id": g.id, "fecha": g.expense_date.isoformat(), "tipo": t,
                           "quien": nombres.get(g.user_id), "concepto": g.description or "", "importe": round(importe, 2)})
    if proyecto:
        from app.models.enterprise import Subcontractor, SubcontractorTimeLog
        tipo_sub = tipo_de_gasto(db, b.organization_id, "subcontract")
        if tipo in (None, tipo_sub):
            for log, nombre in db.query(SubcontractorTimeLog, Subcontractor.name).join(
                    Subcontractor, Subcontractor.id == SubcontractorTimeLog.subcontractor_id).filter(
                    SubcontractorTimeLog.project_id == proyecto, SubcontractorTimeLog.is_active.isnot(False),
                    SubcontractorTimeLog.cost_amount.isnot(None),
                    SubcontractorTimeLog.log_date >= desde, SubcontractorTimeLog.log_date < hasta).all():
                salida.append({"origen": "subcontrata", "id": log.id, "fecha": log.log_date.isoformat(), "tipo": tipo_sub,
                               "quien": nombre, "concepto": log.description or "", "horas": log.hours,
                               "importe": round(float(log.cost_amount), 2)})
    for c in db.query(BudgetCommitment).filter(BudgetCommitment.origen_id == origen(b), BudgetCommitment.estado == "facturado",
                                               BudgetCommitment.fecha_factura >= desde, BudgetCommitment.fecha_factura < hasta).all():
        if tipo in (None, c.tipo):
            salida.append({"origen": "pedido", "id": c.id, "fecha": c.fecha_factura.isoformat(), "tipo": c.tipo,
                           "quien": c.proveedor, "concepto": f"{c.referencia or ''} {c.descripcion}".strip(),
                           "importe": float(c.importe_facturado if c.importe_facturado is not None else c.importe)})
    return salida


def exportar_csv(db: Session, b: Budget) -> str:
    """Una fila por mes y tipo: plan, real, comprometido, previsión."""
    meses, plan, real, cerrados = _informe_base(db, b)
    comp = comprometido_mensual(db, b)
    prev = prevision_por_mes(b, meses, plan, real, cerrados)
    tipos = sorted({t for d in list(plan.values()) + list(real.values()) + list(comp.values()) for t in d})
    buf = io.StringIO()
    w = csv.writer(buf, quoting=csv.QUOTE_ALL)
    w.writerow(["mes", "tipo", "plan", "real", "comprometido", "prevision", "cerrado"])
    for m in meses:
        for t in tipos:
            w.writerow([m, t, *(f"{d.get(m, {}).get(t, 0):.2f}" for d in (plan, real, comp, prev)),
                        "si" if m in cerrados else "no"])
    return buf.getvalue()


# ── Pedidos y control presupuestario ──────────────────────────────────────────

def presupuestos_que_cubren(db: Session, *, fecha: date, project_id: Optional[str] = None,
                            user_id: Optional[str] = None) -> list[Budget]:
    """Los presupuestos aprobados (escenario base) cuyo periodo cubre la fecha y cuyo ámbito incluye el gasto."""
    from app.models.settings import Department
    from app.models.user import User
    mes = date(fecha.year, fecha.month, 1)
    q = db.query(Budget).filter(Budget.estado == "aprobado", Budget.escenario == "base",
                                Budget.periodo_desde <= mes, Budget.periodo_hasta >= mes)
    salida = []
    if project_id:
        salida += q.filter(Budget.project_id == project_id).all()
    dep = db.query(User.department).filter(User.id == user_id).scalar() if user_id else None
    if dep:
        salida += q.filter(Budget.ambito == "departamento", Budget.department == dep).all()
        area = db.query(Department.area_id).filter(Department.name == dep).scalar()
        if area:
            salida += q.filter(Budget.ambito == "area", Budget.area_id == area).all()
    return salida


def comprobar_disponible(db: Session, org, *, tipo_por_presupuesto, importe: float, fecha: date,
                         project_id: Optional[str] = None, user_id: Optional[str] = None,
                         excluir_pedido: Optional[str] = None) -> list[str]:
    """Avisos de los presupuestos que se pasarían; 409 si `BUDGET_CONTROL_POLICY = bloquear`."""
    politica = _aj(db, "BUDGET_CONTROL_POLICY", org).strip().lower()
    if politica in ("", "ninguno", "no"):
        return []
    avisos = []
    for b in presupuestos_que_cubren(db, fecha=fecha, project_id=project_id, user_id=user_id):
        tipo = tipo_por_presupuesto(b)
        fila = next((x for x in seguimiento(db, b)["por_tipo"] if x["tipo"] == tipo), None)
        disponible = fila["disponible"] if fila else 0.0
        if importe > disponible + 0.005:
            avisos.append(f"«{b.name}»: en {tipo} quedan {disponible:g} y esto suma {importe:g}")
    if avisos and politica == "bloquear":
        raise ErrorDeDominio(409, "Sin presupuesto disponible: " + "; ".join(avisos))
    return avisos


def crear_pedido(db: Session, u, budget_id: str, datos: dict) -> dict:
    from app.services.budgets_service import tipos
    _exigir_gestor(db, u)
    b = _cargar(db, budget_id)
    if b.estado != "aprobado":
        raise ErrorDeDominio(409, "Los pedidos se comprometen contra un presupuesto aprobado")
    tipo = datos.get("tipo")
    if tipo not in tipos(db, b.organization_id):
        raise ErrorDeDominio(400, f"Tipo no válido: {tipo}")
    importe = float(datos.get("importe") or 0)
    mes = (datos.get("mes") or "")[:7]
    if importe <= 0 or not mes or not (datos.get("descripcion") or "").strip():
        raise ErrorDeDominio(400, "El pedido necesita descripción, importe y mes")
    avisos = comprobar_disponible(db, b.organization_id, tipo_por_presupuesto=lambda _x: tipo, importe=importe,
                                  fecha=date(int(mes[:4]), int(mes[5:7]), 1), project_id=b.project_id) \
        if b.project_id else _aviso_propio(db, b, tipo, importe)
    c = BudgetCommitment(organization_id=b.organization_id, origen_id=origen(b), tipo=tipo, descripcion=datos["descripcion"],
                         proveedor=datos.get("proveedor"), referencia=datos.get("referencia"), importe=importe, mes=mes,
                         created_by=u.id)
    db.add(c)
    audit_log(db, u, "CREATE", "budget_commitments", None, datos["descripcion"], new_values={"importe": importe, "mes": mes})
    db.commit()
    return {"id": c.id, "avisos": avisos}


def _aviso_propio(db: Session, b: Budget, tipo: str, importe: float) -> list[str]:
    politica = _aj(db, "BUDGET_CONTROL_POLICY", b.organization_id).strip().lower()
    if politica in ("", "ninguno", "no"):
        return []
    fila = next((x for x in seguimiento(db, b)["por_tipo"] if x["tipo"] == tipo), None)
    disponible = fila["disponible"] if fila else 0.0
    if importe <= disponible + 0.005:
        return []
    texto = f"«{b.name}»: en {tipo} quedan {disponible:g} y esto suma {importe:g}"
    if politica == "bloquear":
        raise ErrorDeDominio(409, "Sin presupuesto disponible: " + texto)
    return [texto]


def actualizar_pedido(db: Session, u, pedido_id: str, datos: dict) -> dict:
    _exigir_gestor(db, u)
    c = db.query(BudgetCommitment).filter(BudgetCommitment.id == pedido_id).first()
    if c is None:
        raise ErrorDeDominio(404, "Pedido no encontrado")
    estado = datos.get("estado")
    if estado == "facturado":
        c.estado = "facturado"
        c.fecha_factura = date.fromisoformat(str(datos.get("fecha_factura") or timeutil.today().isoformat())[:10])
        c.importe_facturado = float(datos["importe_facturado"]) if datos.get("importe_facturado") is not None else c.importe
    elif estado == "anulado":
        c.estado = "anulado"
    elif estado:
        raise ErrorDeDominio(400, "Un pedido pasa a facturado o anulado")
    audit_log(db, u, "UPDATE", "budget_commitments", c.id, c.descripcion, new_values={"estado": c.estado})
    db.commit()
    return pedido_dict(c)


def pedido_dict(c: BudgetCommitment) -> dict:
    return {"id": c.id, "tipo": c.tipo, "descripcion": c.descripcion, "proveedor": c.proveedor, "referencia": c.referencia,
            "importe": c.importe, "mes": c.mes, "estado": c.estado,
            "fecha_factura": c.fecha_factura.isoformat() if c.fecha_factura else None,
            "importe_facturado": c.importe_facturado}


def listar_pedidos(db: Session, b: Budget) -> list[dict]:
    return [pedido_dict(c) for c in db.query(BudgetCommitment).filter(BudgetCommitment.origen_id == origen(b))
            .order_by(BudgetCommitment.mes, BudgetCommitment.created_at).all()]


def control_de_gasto(db: Session, gasto) -> list[str]:
    """Al aprobar un gasto: el disponible de su tipo en los presupuestos que lo cubren."""
    tipo = tipo_de_gasto(db, getattr(gasto, "organization_id", None), str(getattr(gasto.category, "value", gasto.category)))
    return comprobar_disponible(db, getattr(gasto, "organization_id", None), tipo_por_presupuesto=lambda _b: tipo,
                                importe=float(gasto.amount or 0), fecha=gasto.expense_date,
                                project_id=gasto.project_id, user_id=gasto.user_id)


# ── Traspasos y ampliaciones ──────────────────────────────────────────────────

def traspaso_dict(t: BudgetTransfer) -> dict:
    return {"id": t.id, "budget_id": t.budget_id, "desde_linea_id": t.desde_linea_id, "hacia_linea_id": t.hacia_linea_id,
            "hacia_tipo": t.hacia_tipo, "hacia_descripcion": t.hacia_descripcion, "importe": t.importe, "motivo": t.motivo,
            "estado": t.estado, "solicitante_id": t.solicitante_id, "motivo_rechazo": t.motivo_rechazo,
            "created_at": t.created_at.isoformat() if t.created_at else None}


def solicitar_traspaso(db: Session, u, budget_id: str, datos: dict) -> dict:
    from app.services.approval_engine import fuentes
    _exigir_gestor(db, u)
    b = _cargar(db, budget_id)
    if b.estado != "aprobado":
        raise ErrorDeDominio(409, "Los traspasos son de un presupuesto aprobado (si no, edítalo)")
    importe = float(datos.get("importe") or 0)
    if importe <= 0 or not (datos.get("motivo") or "").strip():
        raise ErrorDeDominio(400, "El traspaso necesita importe y motivo")
    ids = {l.id for l in b.lines}
    if datos.get("desde_linea_id") and datos["desde_linea_id"] not in ids:
        raise ErrorDeDominio(400, "La partida de origen no es de este presupuesto")
    if datos.get("hacia_linea_id") and datos["hacia_linea_id"] not in ids:
        raise ErrorDeDominio(400, "La partida de destino no es de este presupuesto")
    if not datos.get("hacia_linea_id") and not datos.get("hacia_tipo"):
        raise ErrorDeDominio(400, "Elige la partida de destino o el tipo de una nueva")
    if datos.get("desde_linea_id"):
        origen_l = next(l for l in b.lines if l.id == datos["desde_linea_id"])
        quedan = sum(v for m, v in json.loads(origen_l.meses or "{}").items() if m >= mes_actual())
        if importe > quedan + 0.005:
            raise ErrorDeDominio(400, f"A la partida de origen le quedan {quedan:g} de aquí al final")
    t = BudgetTransfer(organization_id=b.organization_id, budget_id=b.id, desde_linea_id=datos.get("desde_linea_id"),
                       hacia_linea_id=datos.get("hacia_linea_id"), hacia_tipo=datos.get("hacia_tipo"),
                       hacia_descripcion=datos.get("hacia_descripcion"), importe=importe, motivo=datos["motivo"],
                       solicitante_id=u.id)
    db.add(t)
    db.commit()
    fuentes.abrir(db, "budget_transfer", t.id,
                  f"{'Ampliación' if not t.desde_linea_id else 'Traspaso'} en {b.name} · {importe:g} {b.currency}", u.id,
                  {"amount": importe, "category": b.ambito, "project_id": b.project_id})
    return traspaso_dict(t)


def decidir_traspaso(db: Session, u, transfer_id: str, aprobado: bool, motivo: Optional[str] = None,
                     desde_bandeja: bool = False) -> dict:
    from app.services.approval_engine import fuentes
    from app.services.approval_engine._base import exigir_que_no_sea_suyo
    from app.services.budgets_service import puede_aprobar
    t = db.query(BudgetTransfer).filter(BudgetTransfer.id == transfer_id).first()
    if t is None:
        raise ErrorDeDominio(404, "Traspaso no encontrado")
    if t.estado != "pendiente":
        raise ErrorDeDominio(409, "Ese traspaso ya está decidido")
    if not desde_bandeja:
        if not puede_aprobar(db, u):
            raise ErrorDeDominio(403, "Decidir traspasos es de los roles de BUDGET_APPROVER_ROLES")
        exigir_que_no_sea_suyo(db, t.solicitante_id, u, "budget", t.id)
    b = _cargar(db, t.budget_id)
    if aprobado:
        _aplicar_traspaso(db, b, t)
        t.estado = "aprobado"
    else:
        if not (motivo or "").strip():
            raise ErrorDeDominio(400, "Indica el motivo del rechazo")
        t.estado, t.motivo_rechazo = "rechazado", motivo
    t.decisor_id, t.decidido_at = u.id, datetime.now(timezone.utc)
    if not desde_bandeja:
        fuentes.cerrar(db, "budget_transfer", t.id, "approved" if aprobado else "rejected", f"Decidido por {u.full_name}")
    audit_log(db, u, "APPROVE" if aprobado else "REJECT", "budget_transfers", t.id, b.name,
              new_values={"importe": t.importe, "estado": t.estado})
    db.commit()
    if aprobado:
        sincronizar_proyecto(db, b)
    return traspaso_dict(t)


def _congelar(l: BudgetLine) -> None:
    """Tras un traspaso la partida queda por meses tecleados (ya no se recalcula)."""
    for campo in ("unidades", "precio_unitario", "recurrencia", "dedicacion_pct", "salario_anual", "horas", "coste_hora"):
        setattr(l, campo, None)


def _aplicar_traspaso(db: Session, b: Budget, t: BudgetTransfer) -> None:
    from app.services.presupuestos_preparar import meses_de
    restantes = [m for m in meses_de(b) if m >= mes_actual()] or meses_de(b)[-1:]
    if t.desde_linea_id:
        l = next(x for x in b.lines if x.id == t.desde_linea_id)
        meses = json.loads(l.meses or "{}")
        base = {m: v for m, v in meses.items() if m in restantes}
        total = sum(base.values())
        if t.importe > total + 0.005:
            raise ErrorDeDominio(409, f"A la partida de origen sólo le quedan {total:g}")
        for m, v in base.items():
            meses[m] = round(v - t.importe * v / total, 2)
        l.meses = json.dumps({k: v for k, v in meses.items() if abs(v) > 0.004})
        l.importe = round(sum(json.loads(l.meses).values()), 2)
        _congelar(l)
    if t.hacia_linea_id:
        d = next(x for x in b.lines if x.id == t.hacia_linea_id)
    else:
        d = BudgetLine(organization_id=b.organization_id, budget_id=b.id, tipo=t.hacia_tipo,
                       descripcion=t.hacia_descripcion or f"Traspaso: {t.motivo[:80]}", importe=0, meses="{}",
                       sentido="gasto", naturaleza="opex", justificacion=t.motivo)
        b.lines.append(d)
    meses = json.loads(d.meses or "{}")
    cada = round(t.importe / len(restantes), 2)
    for i, m in enumerate(restantes):
        extra = cada if i < len(restantes) - 1 else round(t.importe - cada * (len(restantes) - 1), 2)
        meses[m] = round(meses.get(m, 0.0) + extra, 2)
    d.meses = json.dumps(meses)
    d.importe = round(sum(meses.values()), 2)
    _congelar(d)


def listar_traspasos(db: Session, b: Budget) -> list[dict]:
    return [traspaso_dict(t) for t in db.query(BudgetTransfer).filter(BudgetTransfer.budget_id == b.id)
            .order_by(BudgetTransfer.created_at.desc()).all()]


def aplicar_desde_bandeja(db: Session, actor, transfer_id: str, aprobado: bool, nota: Optional[str]) -> None:
    decidir_traspaso(db, actor, transfer_id, aprobado, nota or "Rechazado en la bandeja de aprobaciones", desde_bandeja=True)


# ── El presupuesto aprobado, base del proyecto ────────────────────────────────

def sincronizar_proyecto(db: Session, b: Budget) -> None:
    """El presupuesto aprobado (escenario base) de un proyecto fija su `budget_amount` y sus horas."""
    from app.models.project import Project
    from app.services.presupuestos_preparar import total_de_gasto
    if b.estado != "aprobado" or b.escenario != "base" or not b.project_id:
        return
    p = db.query(Project).filter(Project.id == b.project_id).first()
    if p is None:
        return
    p.budget_amount = total_de_gasto(b)
    horas = sum(float(l.horas or 0) for l in b.lines if l.tipo == "personal" and l.sentido != "ingreso")
    if horas:
        p.budget_hours = round(horas, 1)
    db.commit()


# ── Alertas ───────────────────────────────────────────────────────────────────

def revisar_alertas(engine) -> int:
    """Consumo (real + comprometido) y previsión al cierre de cada presupuesto aprobado.

    Usa los umbrales de Ajustes → Alertas: `budget_exceeded` y `budget_critical`
    (consumo en % del plan) y `budget_forecast_overrun` (previsión al cierre en %
    del plan). Un aviso abierto por presupuesto y tipo de alerta.
    """
    from app.models.alert import Alert, AlertType
    db = engine.db
    creadas = 0
    ultimas: dict[str, Budget] = {}
    for b in db.query(Budget).filter(Budget.estado == "aprobado", Budget.escenario == "base").all():
        ultimas[origen(b)] = b
    for b in ultimas.values():
        s = seguimiento(db, b)
        if not s["plan"]:
            continue
        consumo = (s["real"] + s["comprometido"]) / s["plan"] * 100
        candidatas = []
        critica, umbral_c, sev_c = engine._config(AlertType.budget_critical, b.organization_id)
        aviso, umbral_a, sev_a = engine._config(AlertType.budget_exceeded, b.organization_id)
        if critica and consumo >= umbral_c:
            candidatas.append((AlertType.budget_critical, sev_c, umbral_c, f"Presupuesto consumido al {consumo:.0f} %: {b.name}"))
        elif aviso and consumo >= umbral_a:
            candidatas.append((AlertType.budget_exceeded, sev_a, umbral_a, f"Presupuesto al {consumo:.0f} %: {b.name}"))
        prevista, umbral_p, sev_p = engine._config(AlertType.budget_forecast_overrun, b.organization_id)
        prevision_pct = s["prevision"] / s["plan"] * 100
        if prevista and prevision_pct > umbral_p:
            candidatas.append((AlertType.budget_forecast_overrun, sev_p, umbral_p,
                               f"La previsión al cierre llega al {prevision_pct:.0f} % del plan: {b.name}"))
        for tipo, sev, umbral, titulo in candidatas:
            clave = f"budget:{origen(b)}:{tipo.value}"[:200]
            if db.query(Alert).filter(Alert.dedup_key == clave, Alert.is_resolved.isnot(True)).first():
                continue
            db.add(Alert(alert_type=tipo, severity=sev, title=titulo, organization_id=b.organization_id,
                         project_id=b.project_id, value=round(prevision_pct if tipo == AlertType.budget_forecast_overrun else consumo, 2),
                         threshold=umbral, dedup_key=clave,
                         description=(f"Plan {s['plan']:g}, real {s['real']:g}, comprometido {s['comprometido']:g}, "
                                      f"previsión {s['prevision']:g}")))
            creadas += 1
    db.commit()
    return creadas


# ── Cuadro de control ─────────────────────────────────────────────────────────

def cuadro(db: Session, u, year: Optional[int] = None) -> list[dict]:
    """Un renglón por presupuesto vigente (el aprobado si lo hay) con su semáforo."""
    from app.services.budgets_service import _vigentes
    yr = year or timeutil.today().year
    salida = []
    for b in _vigentes(db, yr, aprobada_primero=True):
        s = seguimiento(db, b)
        consumo = (s["real"] + s["comprometido"]) / s["plan"] * 100 if s["plan"] else None
        rojo = (consumo is not None and consumo >= 100) or s["prevision"] > s["plan"] + 0.005
        ambar = (not rojo) and ((consumo or 0) >= 85 or bool(s["desviaciones_sin_explicar"]) or bool(s["meses_por_cerrar"]))
        salida.append({"id": b.id, "name": b.name, "ambito": b.ambito, "estado": b.estado, "version": b.version,
                       "escenario": b.escenario, "currency": b.currency, "plan": s["plan"], "real": s["real"], "comprometido": s["comprometido"],
                       "disponible": s["disponible"], "prevision": s["prevision"],
                       "consumo_pct": round(consumo, 1) if consumo is not None else None,
                       "meses_por_cerrar": len(s["meses_por_cerrar"]),
                       "desviaciones_sin_explicar": len(s["desviaciones_sin_explicar"]),
                       "traspasos_pendientes": s["traspasos_pendientes"],
                       "semaforo": "rojo" if rojo else "ambar" if ambar else "verde"})
    orden = {"rojo": 0, "ambar": 1, "verde": 2}
    return sorted(salida, key=lambda x: (orden[x["semaforo"]], -(x["consumo_pct"] or 0)))
