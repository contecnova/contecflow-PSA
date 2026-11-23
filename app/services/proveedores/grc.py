"""GRC de terceros: documentos, riesgo, accesos, requisitos, avisos y RGPD.

Requisitos para activar un contrato (`requisitos`):

- NDA vigente, siempre.
- Contrato de encargado de tratamiento (RGPD art. 28) vigente si el proveedor
  accede a datos personales (`data_access`).
- Con riesgo alto o critico: ademas una certificacion de seguridad vigente
  (ISO 27001, SOC 2 o ENS) y un seguro vigente (RC o ciber).

Un documento sin caducidad es vigente; caduca el dia siguiente a `expires_at`.
"""
from __future__ import annotations

from datetime import date, timedelta
from typing import Optional

from sqlalchemy.orm import Session

from app.core import timeutil
from app.core.codigos_de_error import error
from app.services.audit import audit_log
from app.services.proveedores import serializar as ser
# Vive en `serializar` (que la usa al pintar un documento) para no cerrar un ciclo
# con un import diferido (23-11-2026); se reexporta aquí con el mismo nombre.
from app.services.proveedores.serializar import estado_de_documento  # noqa: F401
from app.services.proveedores.tipos import (
    CERTIFICACIONES_DE_SEGURIDAD, DOCUMENT_TYPES, RISK_CRITERIA, SEGUROS,
)

#: Grupos de requisitos (se informan como estas claves cuando falta cualquiera del grupo).
GRUPO_SEGURIDAD = "security_certification"
GRUPO_SEGURO = "insurance"


def _dias_aviso(db: Session) -> int:
    from app.services.settings_service import get_runtime_int
    v = get_runtime_int(db, "PROVEEDORES_AVISO_DOCUMENTO_DIAS", db.info.get("organization_id"))
    return int(v if v is not None else 30)


def _meses_revision(db: Session) -> int:
    from app.services.settings_service import get_runtime_int
    v = get_runtime_int(db, "PROVEEDORES_REVISION_RIESGO_MESES", db.info.get("organization_id"))
    return int(v if v is not None else 12)


def _documentos(db: Session, sub_id: str) -> list:
    from app.models.proveedores import SupplierDocument
    return db.query(SupplierDocument).filter(SupplierDocument.subcontractor_id == sub_id,
                                             SupplierDocument.is_active.isnot(False)).order_by(
        SupplierDocument.expires_at.is_(None), SupplierDocument.expires_at).all()


def requisitos(sub) -> list[str]:
    req = ["nda"]
    if sub.data_access:
        req.append("dpa_art28")
    if (sub.risk_level or "") in ("high", "critical"):
        req += [GRUPO_SEGURIDAD, GRUPO_SEGURO]
    return req


def _vigentes(docs: list, hoy: date) -> set:
    return {d.doc_type for d in docs if d.expires_at is None or d.expires_at >= hoy}


def faltan(sub, docs: list, hoy: date) -> list[str]:
    vig = _vigentes(docs, hoy)
    salida = []
    for r in requisitos(sub):
        if r == GRUPO_SEGURIDAD:
            if not vig & set(CERTIFICACIONES_DE_SEGURIDAD):
                salida.append(r)
        elif r == GRUPO_SEGURO:
            if not vig & set(SEGUROS):
                salida.append(r)
        elif r not in vig:
            salida.append(r)
    return salida


def cumplimiento(db: Session, sub) -> dict:
    from app.models.proveedores import SupplierAccessGrant, SupplierRiskAssessment
    hoy = timeutil.today()
    dias = _dias_aviso(db)
    docs = _documentos(db, sub.id)
    falta = faltan(sub, docs, hoy)
    por_caducar = [d for d in docs if estado_de_documento(d, hoy, dias) == "expiring"]
    ultima = db.query(SupplierRiskAssessment).filter(SupplierRiskAssessment.subcontractor_id == sub.id).order_by(
        SupplierRiskAssessment.assessed_at.desc(), SupplierRiskAssessment.created_at.desc()).first()
    n_eval = db.query(SupplierRiskAssessment).filter(SupplierRiskAssessment.subcontractor_id == sub.id).count()
    vencida = bool(sub.next_review_date and sub.next_review_date < hoy) or (ultima is None and bool(sub.data_access))
    accesos = db.query(SupplierAccessGrant).filter(SupplierAccessGrant.subcontractor_id == sub.id).order_by(
        SupplierAccessGrant.revoked_at.isnot(None), SupplierAccessGrant.granted_at.desc()).all()
    estado = "blocked" if falta else ("attention" if por_caducar or vencida else "ok")
    return {
        "status": estado, "required": requisitos(sub), "missing": falta,
        "expiring": [ser.documento(d, hoy) for d in por_caducar],
        "documents": [ser.documento(d, hoy) for d in docs],
        "latest_assessment": ser.evaluacion(ultima) if ultima else None, "assessments_count": n_eval,
        "review_overdue": vencida, "access_grants": [ser.acceso(g) for g in accesos],
    }


# ── Documentos ───────────────────────────────────────────────────────────────

def exigir_documento(db: Session, doc_id: str):
    from app.models.proveedores import SupplierDocument
    d = db.query(SupplierDocument).filter(SupplierDocument.id == doc_id, SupplierDocument.is_active.isnot(False)).first()
    if d is None:
        raise error(404, "no_encontrado", detail="Documento no encontrado", que="documento")
    return d


def _aplicar_documento(d, datos: dict, actor) -> None:
    from datetime import datetime, timezone
    verificado = datos.pop("verified", None)
    for k, v in datos.items():
        setattr(d, k, v)
    if d.doc_type not in DOCUMENT_TYPES:
        raise error(422, "proveedor_documento_no_valido", tipo=d.doc_type)
    if d.issued_at and d.expires_at and d.expires_at < d.issued_at:
        raise error(422, "proveedor_fechas_no_validas")
    if verificado:
        d.verified_by = actor.id
        d.verified_at = datetime.now(timezone.utc)
    if "expires_at" in datos:
        d.expiry_notified_at = None


def crear_documento(db: Session, sub, datos: dict, actor) -> dict:
    from app.models.proveedores import SupplierDocument
    datos = {k: v for k, v in datos.items() if v is not None}
    if not datos.get("doc_type"):
        raise error(422, "campo_obligatorio", campo="doc_type")
    d = SupplierDocument(subcontractor_id=sub.id)
    _aplicar_documento(d, datos, actor)
    db.add(d)
    db.flush()
    audit_log(db, actor, "CREATE", "supplier_documents", d.id, sub.name,
              new_values={"doc_type": d.doc_type, "expires_at": str(d.expires_at) if d.expires_at else None})
    db.commit()
    db.refresh(d)
    return ser.documento(d)


def actualizar_documento(db: Session, d, datos: dict, actor) -> dict:
    antes = ser.documento(d)
    _aplicar_documento(d, dict(datos), actor)
    audit_log(db, actor, "UPDATE", "supplier_documents", d.id, d.doc_type,
              old_values={k: antes.get(k) for k in datos if k != "verified"},
              new_values={k: (str(v) if hasattr(v, "isoformat") else v) for k, v in datos.items()})
    db.commit()
    db.refresh(d)
    return ser.documento(d)


def borrar_documento(db: Session, d, actor) -> dict:
    """Baja logica: la evidencia se conserva (retencion y bloqueo legal)."""
    d.is_active = False
    audit_log(db, actor, "DELETE", "supplier_documents", d.id, d.doc_type)
    db.commit()
    return {"ok": True}


# ── Evaluacion de riesgo ─────────────────────────────────────────────────────

def puntuar(criterios: dict) -> tuple[float, str]:
    """Puntuacion 0-100 y nivel. Un 5 en acceso a datos o seguridad sube al menos a alto."""
    valores = []
    for c in RISK_CRITERIA:
        v = criterios.get(c)
        if v is None:
            continue
        v = int(v)
        if v < 1 or v > 5:
            raise error(422, "proveedor_criterio_no_valido", criterio=c)
        valores.append(v)
    desconocidos = set(criterios) - set(RISK_CRITERIA)
    if desconocidos or not valores:
        raise error(422, "proveedor_criterio_no_valido", criterio=", ".join(sorted(desconocidos)) or "-")
    score = round((sum(valores) / len(valores) - 1) / 4 * 100, 1)
    nivel = "low" if score < 30 else "medium" if score < 55 else "high" if score < 75 else "critical"
    if nivel in ("low", "medium") and (criterios.get("data_access") == 5 or criterios.get("security") == 5):
        nivel = "high"
    return score, nivel


def _sumar_meses(d: date, meses: int) -> date:
    import calendar
    m = d.month - 1 + meses
    anio, mes = d.year + m // 12, m % 12 + 1
    return date(anio, mes, min(d.day, calendar.monthrange(anio, mes)[1]))


def listar_evaluaciones(db: Session, sub_id: str) -> list:
    from app.models.proveedores import SupplierRiskAssessment
    return [ser.evaluacion(a) for a in db.query(SupplierRiskAssessment).filter(
        SupplierRiskAssessment.subcontractor_id == sub_id).order_by(SupplierRiskAssessment.assessed_at.desc()).all()]


def evaluar(db: Session, sub, datos: dict, actor) -> dict:
    from app.models.proveedores import SupplierRiskAssessment
    score, nivel = puntuar(datos["criteria"])
    cuando = datos.get("assessed_at") or timeutil.today()
    meses = _meses_revision(db)
    if nivel in ("high", "critical"):
        meses = max(1, meses // 2)
    a = SupplierRiskAssessment(subcontractor_id=sub.id, assessed_at=cuando, assessed_by=actor.id,
                               criteria=datos["criteria"], score=score, level=nivel,
                               next_review_date=_sumar_meses(cuando, meses),
                               due_diligence_done=bool(datos.get("due_diligence_done")), notes=datos.get("notes"))
    db.add(a)
    sub.risk_score = score
    sub.risk_level = nivel
    sub.next_review_date = a.next_review_date
    db.flush()
    audit_log(db, actor, "CREATE", "supplier_risk_assessments", a.id, sub.name,
              new_values={"score": score, "level": nivel, "next_review_date": str(a.next_review_date)})
    db.commit()
    db.refresh(a)
    return ser.evaluacion(a)


# ── Registro de accesos ──────────────────────────────────────────────────────

def conceder_acceso(db: Session, sub, datos: dict, actor) -> dict:
    from app.models.enterprise import SubcontractorWorker
    from app.models.proveedores import SupplierAccessGrant
    from app.services.proveedores import ficha
    ficha.exigir_activo(sub)
    if datos.get("worker_id") and not db.query(SubcontractorWorker.id).filter(
            SubcontractorWorker.id == datos["worker_id"], SubcontractorWorker.subcontractor_id == sub.id).first():
        raise error(422, "externo_persona_no_valida")
    if datos.get("personal_data") and not sub.data_access:
        raise error(409, "proveedor_sin_acceso_a_datos")
    datos = {k: v for k, v in datos.items() if v is not None}
    datos["granted_at"] = datos.get("granted_at") or timeutil.today()
    g = SupplierAccessGrant(subcontractor_id=sub.id, granted_by=actor.id, **datos)
    db.add(g)
    db.flush()
    audit_log(db, actor, "CREATE", "supplier_access_grants", g.id, f"{sub.name}: {g.system}",
              new_values={"system": g.system, "access_level": g.access_level, "personal_data": g.personal_data,
                          "expires_at": str(g.expires_at) if g.expires_at else None})
    db.commit()
    db.refresh(g)
    return ser.acceso(g)


def revocar_acceso(db: Session, acceso_id: str, motivo: Optional[str], actor) -> dict:
    from app.models.proveedores import SupplierAccessGrant
    g = db.query(SupplierAccessGrant).filter(SupplierAccessGrant.id == acceso_id).first()
    if g is None:
        raise error(404, "no_encontrado", detail="Acceso no encontrado", que="acceso")
    if g.revoked_at is not None:
        raise error(409, "proveedor_acceso_ya_revocado")
    g.revoked_at = timeutil.today()
    g.revoked_by = actor.id if actor else None
    g.revoke_reason = (motivo or "")[:255] or None
    audit_log(db, actor, "UPDATE", "supplier_access_grants", g.id, f"{g.system}: revocado",
              new_values={"revoked_at": str(g.revoked_at), "reason": motivo})
    db.commit()
    db.refresh(g)
    return ser.acceso(g)


# ── Cifras, avisos diarios y controles ──────────────────────────────────────

def resumen(db: Session) -> dict:
    from app.models.enterprise import Subcontractor
    from app.models.proveedores import SupplierDocument
    hoy = timeutil.today()
    dias = _dias_aviso(db)
    activos = [s.id for s in db.query(Subcontractor.id).filter(
        Subcontractor.lifecycle_status.in_(("onboarding", "active", "suspended"))).all()]
    docs = db.query(SupplierDocument).filter(SupplierDocument.subcontractor_id.in_(activos),
                                             SupplierDocument.is_active.isnot(False),
                                             SupplierDocument.expires_at.isnot(None)).all() if activos else []
    return {
        "expiring": sum(1 for d in docs if estado_de_documento(d, hoy, dias) == "expiring"),
        "expired": sum(1 for d in docs if estado_de_documento(d, hoy, dias) == "expired"),
        "reviews_overdue": db.query(Subcontractor).filter(Subcontractor.lifecycle_status.in_(("onboarding", "active")),
                                                          Subcontractor.next_review_date.isnot(None),
                                                          Subcontractor.next_review_date < hoy).count(),
    }


def avisos_diarios(db: Session, org_id: Optional[str] = None, hoy: Optional[date] = None) -> dict:
    """Trabajo diario (con `externos-caducidad`): documentos por caducar, revisiones
    vencidas al responsable interno, y accesos caducados se revocan solos."""
    from app.models.enterprise import Subcontractor
    from app.models.proveedores import SupplierAccessGrant, SupplierDocument
    from app.services.notifications import notify_user
    hoy = hoy or timeutil.today()
    dias = _dias_aviso(db)
    avisados = revocados = revisiones = 0
    for d in db.query(SupplierDocument).filter(SupplierDocument.is_active.isnot(False),
                                               SupplierDocument.expires_at.isnot(None),
                                               SupplierDocument.expiry_notified_at.is_(None),
                                               SupplierDocument.expires_at <= hoy + timedelta(days=dias)).all():
        sub = db.get(Subcontractor, d.subcontractor_id)
        if sub is None or sub.lifecycle_status == "offboarded":
            continue
        if sub.internal_owner_id:
            notify_user(db, sub.internal_owner_id, "system", f"{sub.name}: documento {d.doc_type} caduca el {d.expires_at}",
                        "Pide al proveedor el documento renovado y súbelo en su ficha (Cumplimiento).",
                        resource="subcontractors", resource_id=sub.id, action_url="/subcontractors")
        d.expiry_notified_at = hoy
        avisados += 1
    for g in db.query(SupplierAccessGrant).filter(SupplierAccessGrant.revoked_at.is_(None),
                                                  SupplierAccessGrant.expires_at.isnot(None),
                                                  SupplierAccessGrant.expires_at < hoy).all():
        g.revoked_at = hoy
        g.revoke_reason = "expired"
        audit_log(db, None, "UPDATE", "supplier_access_grants", g.id, f"{g.system}: caducado")
        revocados += 1
    for sub in db.query(Subcontractor).filter(Subcontractor.lifecycle_status.in_(("onboarding", "active")),
                                              Subcontractor.next_review_date == hoy).all():
        if sub.internal_owner_id:
            notify_user(db, sub.internal_owner_id, "system", f"{sub.name}: toca revisar su riesgo",
                        "Haz la evaluación periódica en su ficha (Cumplimiento).",
                        resource="subcontractors", resource_id=sub.id, action_url="/subcontractors")
            revisiones += 1
    return {"documentos_avisados": avisados, "accesos_revocados": revocados, "revisiones_avisadas": revisiones}


def controles(db: Session, org: str) -> list[tuple]:
    """Controles de terceros para `informe_de_cumplimiento`: [(id, estado, medido, fuente, marcos)]."""
    from app.models.enterprise import Subcontractor
    from app.models.proveedores import SupplierAccessGrant, SupplierDocument
    hoy = timeutil.today()
    vivos = db.query(Subcontractor).filter(Subcontractor.organization_id == org,
                                           Subcontractor.lifecycle_status.in_(("onboarding", "active", "suspended"))).all()
    sin_dpa = [s for s in vivos if s.data_access and "dpa_art28" not in _vigentes(_documentos(db, s.id), hoy)]
    ids = [s.id for s in vivos]
    caducados = db.query(SupplierDocument).filter(SupplierDocument.subcontractor_id.in_(ids),
                                                  SupplierDocument.is_active.isnot(False),
                                                  SupplierDocument.expires_at < hoy).count() if ids else 0
    revision = sum(1 for s in vivos if s.next_review_date and s.next_review_date < hoy)
    sin_eval = sum(1 for s in vivos if s.data_access and not s.risk_level)
    bajas = [s.id for s in db.query(Subcontractor.id).filter(Subcontractor.organization_id == org,
                                                             Subcontractor.lifecycle_status == "offboarded").all()]
    abiertos_de_baja = db.query(SupplierAccessGrant).filter(SupplierAccessGrant.subcontractor_id.in_(bajas),
                                                           SupplierAccessGrant.revoked_at.is_(None)).count() if bajas else 0
    sin_caducidad = db.query(SupplierAccessGrant).filter(SupplierAccessGrant.organization_id == org,
                                                        SupplierAccessGrant.revoked_at.is_(None),
                                                        SupplierAccessGrant.expires_at.is_(None)).count()
    return [
        ("third_party_dpa", "pass" if not sin_dpa else "attention",
         {"suppliers_with_data_access": sum(1 for s in vivos if s.data_access), "without_valid_dpa": len(sin_dpa)},
         "subcontractors con data_access frente a supplier_documents dpa_art28 vigentes",
         ("RGPD art. 28", "ISO27001 A.5.20")),
        ("third_party_documents", "pass" if caducados == 0 else "attention", {"expired_documents": caducados},
         "supplier_documents caducados de proveedores no dados de baja", ("ISO27001 A.5.19", "SOC2 CC9.2")),
        ("third_party_reviews", "pass" if revision == 0 and sin_eval == 0 else "attention",
         {"reviews_overdue": revision, "data_access_without_assessment": sin_eval},
         "subcontractors.next_review_date y supplier_risk_assessments", ("ISO27001 A.5.22", "NIS2 art. 21.2.d")),
        ("third_party_access", "pass" if abiertos_de_baja == 0 else "attention",
         {"open_grants_of_offboarded": abiertos_de_baja, "open_grants_without_expiry": sin_caducidad},
         "supplier_access_grants sin revocar", ("ISO27001 A.5.18", "ISO27001 A.5.20")),
    ]


# ── RGPD del freelance (persona fisica) ──────────────────────────────────────

def datos_personales(db: Session, user) -> Optional[dict]:
    """Su ficha de proveedor y accesos (copia de datos, art. 15/20). None si no es externo."""
    from app.models.enterprise import Subcontractor, SubcontractorWorker
    from app.models.proveedores import SupplierAccessGrant
    w = db.query(SubcontractorWorker).filter(SubcontractorWorker.user_id == user.id).first()
    if w is None:
        return None
    sub = db.get(Subcontractor, w.subcontractor_id)
    salida = {
        "worker": {"name": w.name, "email": w.email, "phone": w.phone, "role": w.role,
                   "available_from": str(w.available_from) if w.available_from else None,
                   "available_until": str(w.available_until) if w.available_until else None,
                   "cost_rate": w.cost_rate, "currency": w.currency},
        "supplier": {"name": sub.name, "kind": sub.kind, "code": sub.code} if sub else None,
        "access_grants": [ser.acceso(g) for g in db.query(SupplierAccessGrant).filter(
            SupplierAccessGrant.worker_id == w.id).all()],
    }
    if sub is not None and sub.kind == "freelance":
        salida["supplier"].update({"email": sub.email, "phone": sub.phone, "vat_number": sub.vat_number,
                                   "address": sub.address, "country": sub.country})
    return salida


def suprimir(db: Session, user) -> dict:
    """Supresion (art. 17): limpia su ficha de persona externa y, si es freelance, la del proveedor.
    Los importes, contratos y facturas se conservan (obligacion legal, art. 17.3.b)."""
    from app.models.enterprise import Subcontractor, SubcontractorWorker
    tocado = {"workers": 0, "freelance_supplier": 0}
    for w in db.query(SubcontractorWorker).filter(SubcontractorWorker.user_id == user.id).all():
        w.phone = None
        w.notes = None
        w.email = None
        tocado["workers"] += 1
        sub = db.get(Subcontractor, w.subcontractor_id)
        if sub is not None and sub.kind == "freelance":
            sub.phone = None
            sub.email = None
            sub.address = None
            sub.notes = None
            tocado["freelance_supplier"] += 1
    return tocado
