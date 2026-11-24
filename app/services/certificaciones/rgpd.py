"""Certificaciones: RGPD (§3.10).

Datos personales del módulo:
- **auditores y consultores externos** (`cert_auditores`: nombre, correo,
  cualificaciones, conflictos de interés, NDA) y lo que consultaron con su acceso
  temporal (`cert_accesos_registro`: IP y momento);
- **personas internas** como responsables, implantadores, evaluadores, quienes
  prueban, corrigen o cierran (claves ajenas a `users`, que tras la supresión
  apuntan a la ficha ya seudonimizada: no se tocan aquí).

- `copia_auditor` / `suprimir_auditor`: por ficha o por correo (desde una
  solicitud RGPD de `cab_service/gdpr.py`). Suprimir seudonimiza la ficha
  (`[ERASED]`), borra correo, cualificaciones y conflictos, revoca sus accesos y
  quita la IP de su registro de consultas. La traza de QUÉ auditó se conserva
  (obligación legal de las auditorías), salvo que no haya bloqueo legal y se pida
  expresamente lo contrario fuera del módulo. Bajo bloqueo legal
  (`cert_auditores`), no se toca (409).
- `copia_de_usuario`: lo que el módulo guarda de una persona interna (art. 15/20).
"""
from __future__ import annotations

from typing import Optional

from sqlalchemy import or_
from sqlalchemy.orm import Session

from app.core.codigos_de_error import error
from app.models.certificaciones import (
    CertAcceso, CertAccesoRegistro, CertAccion, CertAplicabilidad, CertAuditor, CertHallazgo, CertPrograma,
    CertPrueba,
)
from app.services.certificaciones.comun import ahora, auditar, iso, json_de, org_de, propio

BORRADO = "[ERASED]"


def auditores_por_email(db: Session, email: Optional[str], org: str) -> list[CertAuditor]:
    if not email:
        return []
    return db.query(CertAuditor).filter(CertAuditor.organization_id == org,
                                        CertAuditor.email.ilike(email.strip())).all()


def _copia(db: Session, a: CertAuditor) -> dict:
    accesos = db.query(CertAcceso).filter(CertAcceso.auditor_id == a.id).all()
    return {"nombre": a.nombre, "email": a.email, "cualificaciones": json_de(a.cualificaciones, []),
            "independencia_declarada": a.independencia_declarada, "conflictos_interes": a.conflictos_interes,
            "nda_firmado_el": iso(a.nda_firmado_el), "desde": iso(a.desde), "hasta": iso(a.hasta),
            "accesos": [{"programa_id": x.programa_id, "desde": iso(x.desde), "hasta": iso(x.hasta),
                         "revocado_en": iso(x.revocado_en),
                         "consultas": [{"recurso": r.recurso, "detalle": r.detalle, "ip": r.ip, "en": iso(r.en)}
                                       for r in db.query(CertAccesoRegistro).filter(
                                           CertAccesoRegistro.acceso_id == x.id).all()]}
                        for x in accesos]}


def copia_auditor(db: Session, usuario, auditor_id: str) -> dict:
    a = propio(db, CertAuditor, auditor_id, usuario, "auditor")
    auditar(db, usuario, "GDPR_EXPORT", "auditor", a.id)
    db.commit()
    return {"certification_auditor": _copia(db, a)}


def copia_por_email(db: Session, email: str, org: str) -> dict:
    return {"certification_auditors": [_copia(db, a) for a in auditores_por_email(db, email, org)]}


def exigir_sin_bloqueo_legal(db: Session, auditores: list[CertAuditor]) -> None:
    from app.db.bloqueo_legal import _bloqueo_de, bloqueos_activos
    if not auditores:
        return
    bloqueos = bloqueos_activos(db, auditores[0].organization_id)
    for a in auditores:
        if _bloqueo_de("cert_auditores", a, bloqueos) is not None:
            raise error(409, "cert_auditor_bajo_bloqueo_legal")


def _suprimir(db: Session, a: CertAuditor) -> None:
    a.nombre = BORRADO
    a.email = None
    a.cualificaciones = None
    a.conflictos_interes = None
    a.activo = False
    a.suprimido_en = ahora()
    for x in db.query(CertAcceso).filter(CertAcceso.auditor_id == a.id).all():
        if x.revocado_en is None:
            x.revocado_en = ahora()
        for r in db.query(CertAccesoRegistro).filter(CertAccesoRegistro.acceso_id == x.id).all():
            r.ip = None


def suprimir_auditor(db: Session, usuario, auditor_id: str) -> dict:
    a = propio(db, CertAuditor, auditor_id, usuario, "auditor")
    exigir_sin_bloqueo_legal(db, [a])
    _suprimir(db, a)
    auditar(db, usuario, "GDPR_ERASE", "auditor", a.id)
    db.commit()
    return {"ok": True, "suprimido": a.id}


def suprimir_por_email(db: Session, email: str, org: str) -> Optional[dict]:
    """Desde una solicitud RGPD (no confirma; la solicitud va en una transacción)."""
    auditores = auditores_por_email(db, email, org)
    if not auditores:
        return None
    exigir_sin_bloqueo_legal(db, auditores)
    for a in auditores:
        _suprimir(db, a)
    db.flush()
    return {"certification_auditors_erased": len(auditores)}


def copia_de_usuario(db: Session, user_id: str, org: Optional[str] = None) -> dict:
    """Papeles de una persona interna en el módulo (responsable, implanta, evalúa, prueba, corrige, cierra)."""
    from app.db.session import sin_filtro_de_tenant
    with sin_filtro_de_tenant(db):
        def _q(modelo, *conds):
            q = db.query(modelo).filter(or_(*conds))
            return q.filter(modelo.organization_id == org).all() if org else q.all()
        programas = _q(CertPrograma, CertPrograma.responsable_id == user_id, CertPrograma.patrocinador_id == user_id)
        filas = _q(CertAplicabilidad, CertAplicabilidad.responsable_id == user_id,
                   CertAplicabilidad.implantado_por == user_id, CertAplicabilidad.eficacia_por == user_id)
        pruebas = _q(CertPrueba, CertPrueba.probado_por == user_id)
        hallazgos = _q(CertHallazgo, CertHallazgo.corregido_por == user_id, CertHallazgo.cerrado_por == user_id)
        acciones = _q(CertAccion, CertAccion.responsable_id == user_id, CertAccion.hecho_por == user_id,
                      CertAccion.verificado_por == user_id)
        return {"certification_programs": [{"codigo": p.codigo, "nombre": p.nombre,
                                            "papel": "responsable" if p.responsable_id == user_id else "patrocinador"}
                                           for p in programas],
                "certification_controls": [{"fila": f.id, "responsable": f.responsable_id == user_id,
                                            "implanto": f.implantado_por == user_id,
                                            "evaluo": f.eficacia_por == user_id} for f in filas],
                "certification_tests": [{"id": x.id, "tipo": x.tipo, "resultado": x.resultado,
                                         "probado_en": iso(x.probado_en)} for x in pruebas],
                "certification_findings": [{"codigo": h.codigo, "corrigio": h.corregido_por == user_id,
                                            "cerro": h.cerrado_por == user_id} for h in hallazgos],
                "certification_actions": [{"id": x.id, "estado": x.estado} for x in acciones]}


def _org(usuario) -> str:
    return org_de(usuario)
