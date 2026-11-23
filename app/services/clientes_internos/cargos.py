"""Cargos internos: showback, chargeback e intercompañía (docs/CLIENTES_INTERNOS.md §4).

Estados: `borrador` -> (`por_aprobar`) -> `emitido` -> `exportado`; `anulado`.

- Showback: informe del coste (no se exporta al ERP).
- Chargeback: nota de cargo interna sin IVA ni serie legal; se exporta como
  asiento (CSV) entre centros de coste.
- Intercompañía: al emitirse crea una factura real con la facturación de
  siempre (`facturas.create_invoice`) con precio de transferencia.

Emitir un cargo que deja el consumo del año por encima del presupuesto lo deja
`por_aprobar`: lo aprueba el responsable de la unidad (o la bandeja, tipo
`internal_charge`, si la empresa tiene flujo), nunca quien lo generó ni quien
lo emitió (segregación de funciones). Todo deja `audit_log`.
"""
from __future__ import annotations
import logging

import csv
from app.core.celdas_seguras import neutralizar_formula
import io
from datetime import date, datetime, timezone
from app.core import timeutil
from typing import Optional

from sqlalchemy.orm import Session

from app.core.codigos_de_error import error
from app.models.clientes_internos import InternalCharge, InternalChargeLine
from app.services.audit import audit_log
from app.services.clientes_internos import costes as C
from app.services.clientes_internos import unidades as U

TIPO_DE_APROBACION = "internal_charge"
PREFIJOS = {"showback": "SB", "chargeback": "NC", "intercompania": "IC"}
VIVOS = ("borrador", "por_aprobar", "emitido", "exportado")


def _ahora():
    return datetime.now(timezone.utc)


def _iso(dt):
    return dt.isoformat() if dt else None


def cargo_dict(db: Session, c: InternalCharge, usuario=None, con_lineas: bool = False) -> dict:
    from app.models.clients import Client
    from app.models.project import Project
    unidad = db.get(Client, c.client_id)
    d = {"id": c.id, "number": c.number, "client_id": c.client_id, "client_name": unidad.name if unidad else None,
         "period": c.period, "mode": c.mode, "status": c.status, "total": round(c.total or 0, 2),
         "currency": c.currency, "invoice_id": c.invoice_id, "erp_reference": c.erp_reference, "notes": c.notes,
         "created_at": _iso(c.created_at), "issued_at": _iso(c.issued_at), "exported_at": _iso(c.exported_at),
         "over_budget": c.status == "por_aprobar",
         "can_approve": bool(usuario is not None and c.status == "por_aprobar" and unidad is not None
                             and puede_aprobar(db, usuario, c, unidad))}
    if con_lineas:
        nombres = {}
        d["lines"] = []
        for li in c.lines:
            if li.project_id and li.project_id not in nombres:
                p = db.get(Project, li.project_id)
                nombres[li.project_id] = p.name if p else None
            d["lines"].append({"id": li.id, "source": li.source, "source_ref": li.source_ref,
                               "description": li.description, "project_id": li.project_id,
                               "project_name": nombres.get(li.project_id), "quantity": li.quantity,
                               "unit_amount": li.unit_amount, "amount": round(li.amount or 0, 2)})
    return d


def cargo_o_404(db: Session, cid: str) -> InternalCharge:
    c = db.get(InternalCharge, cid)
    if c is None:
        raise error(404, "no_encontrado", detail="Cargo interno no encontrado", que="cargo_interno")
    return c


def listar(db: Session, usuario, client_id: Optional[str] = None, period: Optional[str] = None,
           status: Optional[str] = None, solo_emitidos: bool = False) -> list[dict]:
    q = db.query(InternalCharge)
    if client_id:
        q = q.filter(InternalCharge.client_id == client_id)
    if period:
        q = q.filter(InternalCharge.period == period)
    if status:
        q = q.filter(InternalCharge.status == status)
    if solo_emitidos:
        q = q.filter(InternalCharge.status.in_(("emitido", "exportado")))
    return [cargo_dict(db, c, usuario) for c in q.order_by(InternalCharge.period.desc(), InternalCharge.number)]


def _numero(db: Session, org_id, modo: str, periodo: str) -> str:
    """Auditoría 22-11-2026 (M62): secuencia bloqueada por empresa, modo y periodo
    (antes `count()+1`: dos generaciones a la vez repetían número)."""
    from app.services.numbering import maximo_numerico, siguiente_codigo
    base = f"{PREFIJOS[modo]}-{periodo.replace('-', '')}-"
    return siguiente_codigo(db, f"internal_charge:{modo}:{periodo}"[:50], prefijo=base, relleno=3, org_id=org_id,
                            maximo_existente=lambda: maximo_numerico(
                                n for (n,) in db.query(InternalCharge.number).filter(
                                    InternalCharge.organization_id == org_id,
                                    InternalCharge.number.like(base + "%"))))


def generar(db: Session, actor, client_id: str, periodo: str) -> dict:
    """Borrador del mes con las líneas de coste congeladas."""
    unidad = U.unidad_o_404(db, client_id, actor)
    desde, hasta = C.periodo(periodo)
    vivo = db.query(InternalCharge).filter(InternalCharge.client_id == unidad.id, InternalCharge.period == periodo,
                                           InternalCharge.status.in_(VIVOS)).first()
    if vivo is not None:
        raise error(409, "interno_cargo_ya_existe", numero=vivo.number)
    modo = unidad.finance_mode or "showback"
    calculo = C.coste(db, unidad, desde, hasta)
    factor = 1.0
    if modo == "intercompania" and unidad.transfer_markup_pct:
        factor = 1 + float(unidad.transfer_markup_pct) / 100.0
    c = InternalCharge(organization_id=unidad.organization_id, client_id=unidad.id, period=periodo, mode=modo,
                       status="borrador", currency=calculo["currency"], created_by=actor.id,
                       number=_numero(db, unidad.organization_id, modo, periodo))
    db.add(c)
    db.flush()
    total = 0.0
    for li in calculo["lines"]:
        importe = round(li["amount"] * factor, 2)
        total += importe
        db.add(InternalChargeLine(organization_id=unidad.organization_id, charge_id=c.id, source=li["source"],
                                  source_ref=li["source_ref"], project_id=li["project_id"],
                                  description=li["description"], quantity=li["quantity"],
                                  unit_amount=li["unit_amount"], amount=importe))
    c.total = round(total, 2)
    audit_log(db, actor, "CREATE", "internal_charge", c.id, c.number,
              new_values={"client_id": unidad.id, "period": periodo, "mode": modo, "total": c.total})
    db.commit()
    db.refresh(c)
    return cargo_dict(db, c, actor, con_lineas=True)


def _supera_presupuesto(db: Session, unidad, c: InternalCharge) -> bool:
    from app.services.clientes_internos.presupuesto import estado
    _, hasta = C.periodo(c.period)
    e = estado(db, unidad, int(c.period[:4]), hasta=hasta)
    return bool(e["budget"]) and e["consumed"] > e["budget"]


def emitir(db: Session, actor, cid: str) -> dict:
    c = cargo_o_404(db, cid)
    if c.status != "borrador":
        raise error(409, "interno_cargo_estado", estado=c.status)
    unidad = U.unidad_o_404(db, c.client_id, actor)
    c.issued_by = actor.id
    if c.mode != "showback" and _supera_presupuesto(db, unidad, c):
        c.status = "por_aprobar"
        audit_log(db, actor, "SUBMIT", "internal_charge", c.id, c.number,
                  new_values={"status": "por_aprobar", "reason": "over_budget"})
        db.commit()
        from app.services.approval_engine import fuentes
        fuentes.abrir(db, TIPO_DE_APROBACION, c.id, f"{c.number} · {unidad.name} · {c.total} {c.currency or ''}",
                      actor.id, contexto={"amount": c.total, "client_id": unidad.id, "period": c.period,
                                          "category": "internal_charge"})
        db.refresh(c)
        return cargo_dict(db, c, actor, con_lineas=True)
    _emitir(db, actor, c, unidad)
    db.commit()
    db.refresh(c)
    return cargo_dict(db, c, actor, con_lineas=True)


def _emitir(db: Session, actor, c: InternalCharge, unidad) -> None:
    c.status = "emitido"
    c.issued_at = _ahora()
    if c.mode == "intercompania" and not c.invoice_id:
        c.invoice_id = _factura_intercompania(db, actor, c, unidad)
    audit_log(db, actor, "APPROVE" if c.issued_by != actor.id else "UPDATE", "internal_charge", c.id, c.number,
              new_values={"status": "emitido", "invoice_id": c.invoice_id, "total": c.total})


def _factura_intercompania(db: Session, actor, c: InternalCharge, unidad) -> Optional[str]:
    from app.models.billing_reports import Invoice
    from app.schemas.billing_reports import InvoiceCreate
    from app.services.billing_reports_service.facturas import create_invoice
    # M12 (auditoría 22-11-2026): `create_invoice` confirma por su cuenta; si
    # algo fallaba después, el reintento creaba OTRA factura. Ahora es
    # idempotente: si ya hay una factura intercompañía de este cargo, se reutiliza.
    previa = db.query(Invoice.id).filter(Invoice.notes == f"Intercompañía {c.number}",
                                         Invoice.client_name == unidad.name).first()
    if previa is not None:
        return previa[0]
    desde, hasta = C.periodo(c.period)
    lineas = [{"description": li.description, "quantity": 1, "unit": "ud", "unit_price": round(li.amount or 0, 2),
               "source_type": "internal_charge", "source_ids": [li.id]} for li in c.lines if li.amount]
    payload = InvoiceCreate(client_name=unidad.name, client_address=unidad.billing_address or unidad.address,
                            client_vat=unidad.tax_id, client_email=unidad.email, issue_date=timeutil.today(),
                            currency=c.currency, notes=f"Intercompañía {c.number}", period_from=desde,
                            period_to=hasta, lines=lineas)
    factura = create_invoice(payload, actor, db)
    fid = factura.get("id") if isinstance(factura, dict) else getattr(factura, "id", None)
    if fid:
        from app.models.billing_reports import Invoice
        inv = db.get(Invoice, fid)
        if inv is not None:
            inv.client_id = unidad.id
    return fid


def puede_aprobar(db: Session, usuario, c: InternalCharge, unidad) -> bool:
    if usuario.id in (c.created_by, c.issued_by):
        return False
    return U.papel(db, usuario, unidad) == "responsable" or getattr(usuario, "is_superadmin", False)


def _segregacion(db: Session, actor, c: InternalCharge) -> None:
    # M12: sin el `try/except: pass` inútil (llamaba a una comprobación y
    # tragaba su resultado para lanzar después este mismo error).
    if actor.id in (c.created_by, c.issued_by):
        raise error(403, "interno_sod_cargo")


def decidir(db: Session, actor, cid: str, aprobado: bool, nota: Optional[str] = None,
            desde_bandeja: bool = False) -> dict:
    c = cargo_o_404(db, cid)
    if c.status != "por_aprobar":
        raise error(409, "interno_cargo_estado", estado=c.status)
    unidad = U.unidad_o_404(db, c.client_id)
    _segregacion(db, actor, c)
    if not desde_bandeja and U.papel(db, actor, unidad) != "responsable" and not getattr(actor, "is_superadmin", False):
        raise error(403, "interno_solo_responsable")
    if aprobado:
        _emitir(db, actor, c, unidad)
    else:
        c.status = "borrador"
        c.issued_by = None
        audit_log(db, actor, "REJECT", "internal_charge", c.id, c.number, new_values={"note": nota})
    if not desde_bandeja:
        from app.services.approval_engine import fuentes
        fuentes.cerrar(db, TIPO_DE_APROBACION, c.id, "approved" if aprobado else "rejected",
                       nota or f"Decidido en Clientes internos por {actor.full_name}")
    db.commit()
    db.refresh(c)
    return cargo_dict(db, c, actor, con_lineas=True)


def comprobar_en_bandeja(req, actor, db: Session, decision: str = "approved") -> None:
    """Antes de anotar la decisión en la bandeja: la segregación del cargo."""
    c = db.get(InternalCharge, req.entity_id)
    if c is not None and actor is not None:
        _segregacion(db, actor, c)


def aplicar_desde_bandeja(db: Session, cid: str, aprobado: bool, actor, nota: Optional[str] = None) -> None:
    c = db.get(InternalCharge, cid)
    if c is None or c.status != "por_aprobar":
        return
    decidir(db, actor, cid, aprobado, nota, desde_bandeja=True)


def anular(db: Session, actor, cid: str, nota: Optional[str] = None) -> dict:
    c = cargo_o_404(db, cid)
    if c.status in ("anulado", "exportado"):
        raise error(409, "interno_cargo_estado", estado=c.status)
    if c.status == "por_aprobar":
        from app.services.approval_engine import fuentes
        fuentes.cerrar(db, TIPO_DE_APROBACION, c.id, "cancelled", nota or "anulado")
    antes = c.status
    c.status = "anulado"
    c.cancelled_at = _ahora()
    c.notes = ((c.notes or "") + ("\n" if c.notes else "") + (nota or "")).strip() or None
    audit_log(db, actor, "CANCEL", "internal_charge", c.id, c.number,
              old_values={"status": antes}, new_values={"status": "anulado", "note": nota})
    db.commit()
    db.refresh(c)
    return cargo_dict(db, c, actor, con_lineas=True)


def cuenta_de_ti(db: Session, org_id) -> str:
    """La cuenta de TI del asiento (ajuste por empresa `INTERNAL_IT_ERP_ACCOUNT`), o vacío."""
    from app.services.settings_service.por_empresa import ajuste_de_empresa
    return str(ajuste_de_empresa(db, "INTERNAL_IT_ERP_ACCOUNT", org_id) or "").strip()


def exportar(db: Session, actor, periodo: str, reexportar: bool = False) -> str:
    """CSV de asientos de los chargebacks emitidos del mes; los marca como exportados.

    M12 (auditoría 22-11-2026): con `reexportar`, también los ya exportados del
    mes con su MISMO asiento (`erp_reference`), sin volver a marcarlos: si la
    descarga se perdía, no había forma de volver a obtener el fichero.

    Dos apuntes por cargo: debe en la cuenta/centro de la unidad (`erp_account`,
    o el código de su centro de coste) y haber en la cuenta de TI de la empresa
    (ajuste `INTERNAL_IT_ERP_ACCOUNT`; sin él, 409 `interno_sin_cuenta_ti`). Sin IVA.
    """
    from app.models.alm import ALMCostCenter
    from app.models.clients import Client
    C.periodo(periodo)
    cuenta_ti = cuenta_de_ti(db, getattr(actor, "organization_id", None))
    if not cuenta_ti:
        raise error(409, "interno_sin_cuenta_ti")
    estados = ("emitido", "exportado") if reexportar else ("emitido",)
    filas = db.query(InternalCharge).filter(InternalCharge.period == periodo, InternalCharge.status.in_(estados),
                                            InternalCharge.mode == "chargeback").order_by(InternalCharge.number).all()
    usados = {c.erp_reference for c in filas if c.erp_reference}
    salida = io.StringIO()
    w = csv.writer(salida, delimiter=";")
    w.writerow(["entry", "date", "document", "unit", "cost_center", "account", "debit", "credit", "currency",
                "description"])
    hoy = timeutil.today().isoformat()
    n = 0
    for c in filas:
        unidad = db.get(Client, c.client_id)
        centro = db.get(ALMCostCenter, unidad.cost_center_id) if unidad and unidad.cost_center_id else None
        cuenta = (unidad.erp_account if unidad else None) or (centro.code if centro else "")
        if c.status == "exportado" and c.erp_reference:
            asiento = c.erp_reference
        else:
            n += 1
            asiento = f"{periodo.replace('-', '')}-{n:04d}"
            while asiento in usados:
                n += 1
                asiento = f"{periodo.replace('-', '')}-{n:04d}"
            usados.add(asiento)
        texto = f"Cargo interno {c.number} {periodo}"
        w.writerow([asiento, hoy, c.number, neutralizar_formula(unidad.name if unidad else ""),
                    neutralizar_formula(centro.code if centro else ""), neutralizar_formula(cuenta),
                    f"{c.total:.2f}", "0.00", neutralizar_formula(c.currency or ""), texto])
        w.writerow([asiento, hoy, c.number, "", "", neutralizar_formula(cuenta_ti), "0.00", f"{c.total:.2f}",
                    neutralizar_formula(c.currency or ""), texto])
        if c.status != "exportado":
            c.status = "exportado"
            c.exported_at = _ahora()
            c.erp_reference = asiento
    audit_log(db, actor, "EXPORT", "internal_charge", None, f"asientos {periodo}",
              metadata={"period": periodo, "charges": [c.number for c in filas], "reexport": reexportar})
    db.commit()
    return salida.getvalue()
