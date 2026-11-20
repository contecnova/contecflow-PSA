"""Prevision de factura, estados de cuenta, conciliacion, aprobacion y coste en proyecto.

`prever` calcula todas las lineas de precio vigentes de un contrato en un
periodo (con escalados, minimos y topes por linea), aplica los creditos y
bonus por SLA de sus servicios y, a nivel de contrato, el minimo comprometido
y el tope total. Nada se guarda: `cerrar_periodo` guarda el resultado como
estado de cuenta, que se concilia con la factura del proveedor y se aprueba con
segregacion (no aprueba quien cerro el periodo ni quien registro la factura).

Aprobacion por importe (migracion 191): si la empresa tiene un flujo activo del
tipo `supplier_statement` en el motor comun (`app/services/approval_engine/`,
disenador de flujos con condiciones por importe, niveles, grupos y plazos), el
boton «Aprobar» envia el estado de cuenta a la bandeja (`pending_approval`) y la
decision final la aplica `aplicar_desde_bandeja`. La segregacion se comprueba en
la bandeja antes de anotar la aprobacion (`comprobar_en_bandeja`). Sin flujo,
aprobacion directa con la misma segregacion (como antes).

Lo aprobado que no son horas y tiene proyecto entra en el coste del proyecto
(`partidas`, que llama `costes_de_proyecto.partidas_externas`). Las horas ya
estan en las imputaciones con la tarifa del proveedor: nunca dos veces.
"""
from __future__ import annotations

from datetime import date, datetime, timezone
from typing import Optional

from sqlalchemy.orm import Session

from app.core import timeutil
from app.core.codigos_de_error import error
from app.services.audit import audit_log
from app.services.proveedores import consumo
from app.services.proveedores import serializar as ser
from app.services.proveedores.tipos import MESES_DEL_PERIODO, TIPO_DE_APROBACION

_R = 2


def precio_por_tramos(cantidad: float, tramos: list) -> float:
    """Escalado graduado: cada tramo cobra su parte a su precio."""
    total = 0.0
    for t in sorted(tramos, key=lambda x: float(x.get("from", 0) or 0)):
        desde = float(t.get("from", 0) or 0)
        hasta = t.get("to")
        if cantidad <= desde:
            break
        tope = cantidad if hasta is None else min(cantidad, float(hasta))
        total += (tope - desde) * float(t["price"])
    return total


def importe_por_cantidad(linea, cantidad: float) -> float:
    if linea.tiers:
        return precio_por_tramos(cantidad, linea.tiers)
    return cantidad * float(linea.unit_price or 0)


def _vigente(linea, desde: date, hasta: date) -> bool:
    return (linea.is_active is not False and (linea.valid_from is None or linea.valid_from <= hasta)
            and (linea.valid_until is None or linea.valid_until >= desde))


def _proporcion(periodo: Optional[str], desde: date, hasta: date) -> float:
    if periodo == "one_time":
        return 1.0
    return consumo.meses(desde, hasta) / MESES_DEL_PERIODO.get(periodo or "monthly", 1)


def _linea_base(linea, cantidad, precio, importe, pid, fuente, detalle) -> dict:
    return {"pricing_line_id": linea.id if linea is not None else None,
            "model": linea.model if linea is not None else None, "unit": linea.unit if linea is not None else None,
            "description": (linea.description if linea is not None else None),
            "quantity": round(cantidad, 4) if cantidad is not None else None,
            "unit_price": precio, "amount": round(importe, _R), "project_id": pid, "source": fuente,
            "detail": detalle or {}, "service_id": linea.service_id if linea is not None else None}


def _limites_de_linea(linea, importe: float, desde: date, hasta: date, detalle: dict) -> float:
    p = _proporcion(linea.period or "monthly", desde, hasta)
    if linea.min_amount is not None and importe < linea.min_amount * p:
        detalle["min_applied"] = round(linea.min_amount * p - importe, _R)
        importe = linea.min_amount * p
    if linea.max_amount is not None and importe > linea.max_amount * p:
        detalle["cap_applied"] = round(importe - linea.max_amount * p, _R)
        importe = linea.max_amount * p
    return importe


def _lineas_de(db: Session, contrato, linea, desde: date, hasta: date, avisos: list) -> list[dict]:
    from app.models.proveedores import SupplierWorkPackage
    modelo = linea.model
    if modelo in ("per_resource", "per_unit"):
        m = consumo.medir(db, contrato, linea, desde, hasta)
        if m.get("warning"):
            avisos.append({"code": m["warning"], "params": {"line": linea.description or linea.unit or linea.id}})
        det = dict(m["detail"])
        importe = _limites_de_linea(linea, importe_por_cantidad(linea, m["quantity"]), desde, hasta, det)
        return [_linea_base(linea, m["quantity"], linea.unit_price, importe, m["project_id"] or contrato.project_id,
                            m["source"], det)]
    if modelo == "fixed_price":
        q = db.query(SupplierWorkPackage).filter(SupplierWorkPackage.status == "accepted",
                                                 SupplierWorkPackage.accepted_at >= desde,
                                                 SupplierWorkPackage.accepted_at <= hasta)
        if linea.work_package_id:
            q = q.filter(SupplierWorkPackage.id == linea.work_package_id)
        else:
            q = q.filter(SupplierWorkPackage.contract_id == contrato.id)
        salida = []
        for wp in q.all():
            precio = float(linea.unit_price if linea.unit_price is not None else (wp.price or 0))
            salida.append(_linea_base(linea, 1.0, precio, precio, wp.project_id, "accepted_packages",
                                      {"work_package_id": wp.id, "title": wp.title, "accepted_at": str(wp.accepted_at)}))
        return salida
    if modelo == "subscription":
        p = _proporcion(linea.period, desde, hasta)
        cuota = float(linea.unit_price or 0) * p
        det = {"months_factor": round(p, 4)}
        importe = cuota
        cantidad = None
        if linea.included_units is not None and linea.overage_price is not None and linea.unit:
            m = consumo.medir(db, contrato, linea, desde, hasta)
            cantidad = m["quantity"]
            incluidas = float(linea.included_units) * p
            exceso = max(0.0, cantidad - incluidas)
            det.update({"included": round(incluidas, 4), "overage_units": round(exceso, 4)})
            importe += exceso * float(linea.overage_price)
        importe = _limites_de_linea(linea, importe, desde, hasta, det)
        return [_linea_base(linea, cantidad, linea.unit_price, importe, contrato.project_id, "subscription", det)]
    if modelo == "expense":
        regs = consumo._registros(db, contrato, linea, desde, hasta, "expense")
        importe = sum(float(r.amount if r.amount is not None else r.quantity or 0) for r in regs)
        det = {"records": len(regs)}
        if contrato.expenses_cap is not None and importe > contrato.expenses_cap:
            det["cap_applied"] = round(importe - contrato.expenses_cap, _R)
            importe = float(contrato.expenses_cap)
            avisos.append({"code": "tope_de_gastos", "params": {"cap": contrato.expenses_cap}})
        pid = next((r.project_id for r in regs if r.project_id), contrato.project_id)
        return [_linea_base(linea, None, None, importe, pid, "usage", det)]
    if modelo == "bonus":
        return []  # se resuelve con las reglas del servicio (`_creditos_y_bonus`)
    return []


def _creditos_y_bonus(db: Session, contrato, lineas: list, desde: date, hasta: date) -> list[dict]:
    """Por cada servicio del contrato con reglas: credito (negativo) o bonus segun su SLA del periodo."""
    from app.models.proveedores import SupplierPricingLine, SupplierService
    from app.services.proveedores import servicios as srv
    salida = []
    servicios = db.query(SupplierService).filter(SupplierService.contract_id == contrato.id).all()
    for s in servicios:
        if not (s.credit_rules or s.bonus_rules):
            continue
        m = srv.sla(db, s, desde, hasta)
        pct = m["compliance_pct"]
        if pct is None:
            continue
        propias = [x for x in lineas if x.get("service_id") == s.id]
        base = sum(x["amount"] for x in (propias or ([x for x in lineas if x["model"] != "per_resource"]
                                                     if len(servicios) == 1 else [])))
        credito = max((float(r["credit_pct"]) for r in (s.credit_rules or []) if pct < float(r["below_pct"])), default=0.0)
        if credito and base:
            salida.append({"pricing_line_id": None, "model": "credit", "unit": None, "service_id": s.id,
                           "description": s.name, "quantity": None, "unit_price": None,
                           "amount": round(-base * credito / 100, _R), "project_id": contrato.project_id,
                           "source": "rule", "detail": {"sla_pct": pct, "credit_pct": credito, "base": round(base, _R)}})
        bonus = max((float(r["bonus_pct"]) for r in (s.bonus_rules or []) if pct >= float(r["above_pct"])), default=0.0)
        fijos = db.query(SupplierPricingLine).filter(SupplierPricingLine.contract_id == contrato.id,
                                                     SupplierPricingLine.model == "bonus",
                                                     SupplierPricingLine.service_id == s.id,
                                                     SupplierPricingLine.is_active.isnot(False)).all()
        if bonus and base:
            salida.append({"pricing_line_id": None, "model": "bonus", "unit": None, "service_id": s.id,
                           "description": s.name, "quantity": None, "unit_price": None,
                           "amount": round(base * bonus / 100, _R), "project_id": contrato.project_id,
                           "source": "rule", "detail": {"sla_pct": pct, "bonus_pct": bonus, "base": round(base, _R)}})
        objetivo_cumplido = m["met"] if m["met"] is not None else bool(bonus)
        for f in fijos:
            if objetivo_cumplido and _vigente(f, desde, hasta):
                importe = float(f.unit_price or 0) * _proporcion(f.period, desde, hasta)
                salida.append(_linea_base(f, None, f.unit_price, importe, contrato.project_id, "rule",
                                          {"sla_pct": pct}))
    return salida


def _gastado_antes(db: Session, contrato, excluir: Optional[str] = None) -> float:
    from sqlalchemy import func

    from app.models.proveedores import SupplierStatement
    q = db.query(func.coalesce(func.sum(SupplierStatement.expected_amount), 0.0)).filter(
        SupplierStatement.contract_id == contrato.id)
    if excluir:
        q = q.filter(SupplierStatement.id != excluir)
    return float(q.scalar() or 0)


def prever(db: Session, contrato, desde: date, hasta: date) -> dict:
    if hasta < desde:
        raise error(422, "proveedor_fechas_no_validas")
    avisos: list = []
    lineas: list = []
    for x in contrato.lines or []:
        if _vigente(x, desde, hasta):
            lineas.extend(_lineas_de(db, contrato, x, desde, hasta, avisos))
    reglas = _creditos_y_bonus(db, contrato, lineas, desde, hasta)
    subtotal = round(sum(x["amount"] for x in lineas), _R)
    creditos = round(sum(-x["amount"] for x in reglas if x["model"] == "credit"), _R)
    bonus = round(sum(x["amount"] for x in reglas if x["model"] == "bonus"), _R)
    total = subtotal - creditos + bonus
    ajustes = 0.0
    if contrato.committed_minimum:
        minimo = float(contrato.committed_minimum) * _proporcion(contrato.minimum_period, desde, hasta)
        if total < minimo:
            ajustes += minimo - total
            avisos.append({"code": "minimo_comprometido", "params": {"minimum": round(minimo, _R)}})
            reglas.append({"pricing_line_id": None, "model": "adjustment", "unit": None, "service_id": None,
                           "description": "committed_minimum", "quantity": None, "unit_price": None,
                           "amount": round(minimo - total, _R), "project_id": contrato.project_id,
                           "source": "contract", "detail": {"minimum": round(minimo, _R)}})
            total = minimo
    gastado = _gastado_antes(db, contrato)
    if contrato.total_cap is not None and gastado + total > contrato.total_cap:
        exceso = gastado + total - float(contrato.total_cap)
        recorte = min(exceso, total)
        ajustes -= recorte
        avisos.append({"code": "tope_alcanzado", "params": {"cap": contrato.total_cap, "spent": round(gastado, _R)}})
        reglas.append({"pricing_line_id": None, "model": "adjustment", "unit": None, "service_id": None,
                       "description": "total_cap", "quantity": None, "unit_price": None,
                       "amount": round(-recorte, _R), "project_id": contrato.project_id, "source": "contract",
                       "detail": {"cap": contrato.total_cap, "spent": round(gastado, _R)}})
        total -= recorte
    if contrato.po_amount is not None and gastado + total > contrato.po_amount:
        avisos.append({"code": "pedido_superado", "params": {"po_number": contrato.po_number or "",
                                                             "po_amount": contrato.po_amount}})
    return {"contract_id": contrato.id, "period_start": str(desde), "period_end": str(hasta),
            "currency": contrato.currency, "lines": lineas + reglas, "subtotal": subtotal, "credits": creditos,
            "bonus": bonus, "adjustments": round(ajustes, _R), "expected_amount": round(total, _R),
            "warnings": avisos}


# ── Estados de cuenta ────────────────────────────────────────────────────────

def exigir_estado(db: Session, estado_id: str):
    from app.models.proveedores import SupplierStatement
    s = db.query(SupplierStatement).filter(SupplierStatement.id == estado_id).first()
    if s is None:
        raise error(404, "no_encontrado", detail="Estado de cuenta no encontrado", que="estado_de_cuenta")
    return s


def listar(db: Session, sub_id: str) -> list:
    from app.models.proveedores import SupplierStatement
    return [ser.estado_de_cuenta(s) for s in db.query(SupplierStatement).filter(
        SupplierStatement.subcontractor_id == sub_id).order_by(SupplierStatement.period_end.desc()).all()]


def cerrar_periodo(db: Session, contrato, desde: date, hasta: date, actor) -> dict:
    from app.models.proveedores import SupplierStatement, SupplierUsageRecord
    if contrato.status not in ("active", "suspended", "terminated", "expired"):
        raise error(409, "proveedor_contrato_no_activo")
    solapa = db.query(SupplierStatement.id).filter(SupplierStatement.contract_id == contrato.id,
                                                   SupplierStatement.period_start <= hasta,
                                                   SupplierStatement.period_end >= desde).first()
    if solapa:
        raise error(409, "proveedor_periodo_ya_cerrado")
    p = prever(db, contrato, desde, hasta)
    st = SupplierStatement(subcontractor_id=contrato.subcontractor_id, contract_id=contrato.id, period_start=desde,
                           period_end=hasta, currency=contrato.currency, lines=p["lines"], subtotal=p["subtotal"],
                           credits=p["credits"], bonus=p["bonus"], adjustments=p["adjustments"],
                           expected_amount=p["expected_amount"], status="closed", closed_by=actor.id)
    db.add(st)
    db.flush()
    db.query(SupplierUsageRecord).filter(SupplierUsageRecord.contract_id == contrato.id,
                                         SupplierUsageRecord.statement_id.is_(None),
                                         SupplierUsageRecord.period_start >= desde,
                                         SupplierUsageRecord.period_end <= hasta).update(
        {"statement_id": st.id}, synchronize_session=False)
    audit_log(db, actor, "CREATE", "supplier_statements", st.id, contrato.title,
              new_values={"period": f"{desde}/{hasta}", "expected_amount": st.expected_amount})
    db.commit()
    db.refresh(st)
    return ser.estado_de_cuenta(st)


def _tolerancia(db: Session) -> float:
    from app.services.settings_service import get_runtime_float
    v = get_runtime_float(db, "PROVEEDORES_TOLERANCIA_CONCILIACION_PCT", db.info.get("organization_id"))
    return float(v if v is not None else 2.0)


def conciliar(db: Session, st, factura_id: str, actor) -> dict:
    from app.models.enterprise import SubcontractorInvoice
    from app.services.profitability_service import get_fx_rate
    if st.status == "approved":
        raise error(409, "proveedor_estado_aprobado")
    if st.status == "pending_approval":
        raise error(409, "proveedor_aprobacion_en_bandeja")
    f = db.query(SubcontractorInvoice).filter(SubcontractorInvoice.id == factura_id,
                                              SubcontractorInvoice.subcontractor_id == st.subcontractor_id).first()
    if f is None:
        raise error(404, "no_encontrado", detail="Factura no encontrada", que="factura")
    importe = float(f.amount or 0)
    if f.currency and st.currency and f.currency.upper() != st.currency.upper():
        importe *= get_fx_rate(db, f.currency.upper(), st.currency.upper(), f.issue_date)
    dif = round(importe - float(st.expected_amount or 0), _R)
    pct = round(dif / st.expected_amount * 100, 2) if st.expected_amount else None
    st.invoice_id = f.id
    st.invoice_amount = round(importe, _R)
    st.difference = dif
    st.difference_pct = pct
    dentro = abs(dif) < 0.01 or (pct is not None and abs(pct) <= _tolerancia(db))
    st.status = "reconciled" if dentro else "disputed"
    st.dispute_reason = None if dentro else "difference_out_of_tolerance"
    f.contract_id = st.contract_id
    audit_log(db, actor, "UPDATE", "supplier_statements", st.id, "conciliado",
              new_values={"invoice_id": f.id, "difference": dif, "difference_pct": pct, "status": st.status})
    db.commit()
    db.refresh(st)
    return ser.estado_de_cuenta(st)


def _factura(db: Session, st):
    from app.models.enterprise import SubcontractorInvoice
    return db.get(SubcontractorInvoice, st.invoice_id) if st.invoice_id else None


def _segregacion(db: Session, st, actor) -> None:
    """No aprueba quien cerro el periodo ni quien registro la factura del proveedor."""
    f = _factura(db, st)
    if actor is not None and actor.id in {st.closed_by, getattr(f, "created_by", None)} - {None}:
        raise error(409, "proveedor_segregacion_aprobacion")


def contexto_de_aprobacion(db: Session, st) -> dict:
    """Lo que ven las condiciones del flujo: importe en la moneda de la empresa, proyecto y proveedor."""
    from app.services.profitability_service import get_fx_rate
    from app.services.settings_service.por_empresa import moneda_de_empresa
    propio = float(st.invoice_amount if st.invoice_amount is not None else st.expected_amount or 0)
    importe = propio
    moneda = moneda_de_empresa(db)
    if st.currency and moneda and st.currency.upper() != moneda.upper():
        importe *= get_fx_rate(db, st.currency.upper(), moneda.upper(), st.period_end)
    contrato = st.contract
    return {"amount": round(importe, _R), "currency": moneda, "statement_currency": st.currency,
            "amount_in_statement_currency": round(propio, _R),
            "project_id": getattr(contrato, "project_id", None), "subcontractor_id": st.subcontractor_id,
            "contract_id": st.contract_id}


def hay_flujo(db: Session, actor, contexto: dict) -> bool:
    """¿Tiene la empresa un flujo activo de `supplier_statement` que encaje con este importe?"""
    from app.services.approval_engine._base import elegir_flujo
    return elegir_flujo(db, TIPO_DE_APROBACION,
                        {**contexto, "department": getattr(actor, "department", None)}) is not None


def _aplicar_aprobacion(db: Session, st, actor, via: str = "direct") -> None:
    f = _factura(db, st)
    st.status = "approved"
    st.approved_by = actor.id if actor else None
    st.approved_at = datetime.now(timezone.utc)
    if f is not None and f.status == "received":
        f.status = "approved"
    audit_log(db, actor, "APPROVE", "supplier_statements", st.id, "aprobado",
              new_values={"expected_amount": st.expected_amount, "invoice_id": st.invoice_id, "via": via,
                          "approval_request_id": st.approval_request_id})


def aprobar(db: Session, st, actor) -> dict:
    """Aprobar: con flujo del motor, a la bandeja; sin flujo, directo con segregacion."""
    if st.status == "pending_approval":
        raise error(409, "proveedor_aprobacion_en_bandeja")
    if st.status != "reconciled":
        raise error(409, "proveedor_estado_no_conciliado")
    contexto = contexto_de_aprobacion(db, st)
    if hay_flujo(db, actor, contexto):
        return enviar_a_aprobacion(db, st, actor, contexto)
    _segregacion(db, st, actor)
    _aplicar_aprobacion(db, st, actor)
    db.commit()
    db.refresh(st)
    return ser.estado_de_cuenta(st)


def enviar_a_aprobacion(db: Session, st, actor, contexto: Optional[dict] = None) -> dict:
    """Abre la solicitud del motor comun (tipo `supplier_statement`) y deja el estado en la bandeja.

    El flujo lo elige el motor por sus condiciones (importe, proyecto). Si el
    motor la aprueba solo (politica de aprobacion automatica), el estado queda
    aprobado aqui mismo por `aplicar_desde_bandeja`.
    """
    from app.models.billing_reports import ApprovalRequest
    from app.services.approval_engine import fuentes
    contexto = contexto or contexto_de_aprobacion(db, st)
    sub = st.contract.subcontractor if st.contract is not None else None
    importe = st.invoice_amount if st.invoice_amount is not None else st.expected_amount
    partes = [getattr(sub, "name", None), st.contract.title if st.contract is not None else None,
              f"{st.period_start}/{st.period_end}", f"{importe} {st.currency or ''}".strip()]
    resumen = " · ".join(p for p in partes if p)
    st_id = st.id
    fuentes.abrir(db, TIPO_DE_APROBACION, st_id, resumen, actor.id, contexto=contexto)
    st = exigir_estado(db, st_id)
    db.refresh(st)
    if st.status == "approved":           # aprobada sola por politica
        return ser.estado_de_cuenta(st)
    req = db.query(ApprovalRequest).filter(ApprovalRequest.entity_type == TIPO_DE_APROBACION,
                                           ApprovalRequest.entity_id == st_id,
                                           ApprovalRequest.status == "pending").order_by(
        ApprovalRequest.created_at.desc()).first()
    if req is None:
        raise error(409, "proveedor_aprobacion_no_abierta")
    st.status = "pending_approval"
    st.approval_request_id = req.id
    audit_log(db, actor, "SUBMIT", "supplier_statements", st.id, "a la bandeja de aprobaciones",
              new_values={"approval_request_id": req.id, "amount": contexto.get("amount"),
                          "currency": contexto.get("currency")})
    db.commit()
    db.refresh(st)
    return ser.estado_de_cuenta(st)


def comprobar_en_bandeja(req, actor, db: Session, decision: str = "approved") -> None:
    """Antes de anotar una aprobacion en la bandeja: la segregacion del estado de cuenta."""
    from app.models.proveedores import SupplierStatement
    if decision != "approved":
        return
    st = db.query(SupplierStatement).filter(SupplierStatement.id == req.entity_id).first()
    if st is not None:
        _segregacion(db, st, actor)


def aplicar_desde_bandeja(db: Session, estado_id: str, aprobado: bool, actor, nota: Optional[str] = None) -> None:
    """Decision final de la bandeja: aprobado -> `approved`; rechazado -> `disputed` con la nota."""
    from app.models.proveedores import SupplierStatement
    st = db.query(SupplierStatement).filter(SupplierStatement.id == estado_id).first()
    if st is None or st.status not in ("pending_approval", "reconciled"):
        return
    if aprobado:
        _aplicar_aprobacion(db, st, actor, via="approval_engine")
    else:
        st.status = "disputed"
        st.dispute_reason = (nota or "").strip() or "rejected_in_approval"
        audit_log(db, actor, "REJECT", "supplier_statements", st.id, "rechazado en la bandeja",
                  new_values={"reason": st.dispute_reason, "approval_request_id": st.approval_request_id})
    db.commit()


def disputar(db: Session, st, motivo: Optional[str], actor) -> dict:
    if st.status == "approved":
        raise error(409, "proveedor_estado_aprobado")
    if not (motivo or "").strip():
        raise error(422, "campo_obligatorio", campo="reason")
    if st.status == "pending_approval":
        # Disputarlo lo saca de la bandeja: su solicitud pendiente se cancela.
        from app.services.approval_engine import fuentes
        fuentes.cerrar(db, TIPO_DE_APROBACION, st.id, "cancelled", motivo)
    st.status = "disputed"
    st.dispute_reason = motivo
    audit_log(db, actor, "REJECT", "supplier_statements", st.id, "disputado", new_values={"reason": motivo})
    db.commit()
    db.refresh(st)
    return ser.estado_de_cuenta(st)


# ── Coste en el proyecto y cifras globales ───────────────────────────────────

def partidas(db: Session, project_ids: list, moneda: str, desde=None, hasta=None, convertir=None) -> list[tuple]:
    """[(project_id, fecha, "subcontrata", importe)] de las lineas aprobadas que no son horas."""
    from app.models.proveedores import SupplierStatement
    if not project_ids:
        return []
    q = db.query(SupplierStatement).filter(SupplierStatement.status == "approved")
    if desde:
        q = q.filter(SupplierStatement.period_end >= desde)
    if hasta:
        q = q.filter(SupplierStatement.period_end <= hasta)
    ids = set(project_ids)
    salida = []
    for st in q.all():
        for x in st.lines or []:
            if x.get("model") == "per_resource" or x.get("project_id") not in ids:
                continue
            importe = float(x.get("amount") or 0)
            if convertir is not None:
                importe = convertir(importe, st.currency, st.period_end)
            salida.append((x["project_id"], st.period_end, "subcontrata", importe))
    return salida


def prevision_del_mes(db: Session) -> float:
    """Suma de la prevision del mes en curso de los contratos activos, en la moneda de la empresa."""
    from app.models.proveedores import SupplierContract
    from app.services.profitability_service import get_fx_rate
    from app.services.settings_service.por_empresa import moneda_de_empresa
    hoy = timeutil.today()
    desde = hoy.replace(day=1)
    import calendar
    hasta = hoy.replace(day=calendar.monthrange(hoy.year, hoy.month)[1])
    moneda = moneda_de_empresa(db)
    total = 0.0
    for c in db.query(SupplierContract).filter(SupplierContract.status == "active",
                                               SupplierContract.is_template == False).all():  # noqa: E712
        try:
            importe = prever(db, c, desde, hasta)["expected_amount"]
        except Exception:  # una prevision rota no tumba el cuadro global
            continue
        if c.currency and c.currency.upper() != moneda:
            importe *= get_fx_rate(db, c.currency.upper(), moneda, hoy)
        total += importe
    return round(total, _R)
