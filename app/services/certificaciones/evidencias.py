"""Certificaciones: evidencias (§3.4), siempre bajo control de flujos.

- Una evidencia apunta a un control común (cuenta para todas las normas que lo
  exigen) y, opcionalmente, a un programa y a una fila de la declaración.
  Cuentan para una fila: las suyas, las del programa sin fila para ese control y
  las de la biblioteca de la empresa (sin programa: GRC y medidas del sistema).
- Se apoyan en **Documentos**: versiones, permisos, retención, bloqueo legal y
  flujo de aprobación. Con `exigir_evidencia_aprobada` (por defecto), una
  evidencia documental no cuenta hasta que su documento está aprobado.
- **Caducidad**: `caduca_el` o, si no, `valida_desde` (o el alta) + los días de
  la configuración. Una evidencia caducada deja de contar y avisa (`trabajos`).
- Tipos de origen: `manual`, `plantilla` (documento de la plantilla), `tarea`
  (tarea enlazada al control, cuenta al hacerse), `sistema` (medida automática
  firmada con su huella) y `grc` (las de «Marcos y evidencias», enlazadas).
"""
from __future__ import annotations

from datetime import date, timedelta
from typing import Optional

from sqlalchemy import or_
from sqlalchemy.orm import Session

from app.core.codigos_de_error import error
from app.models.certificaciones import CertAplicabilidad, CertControl, CertEvidencia, CertPrograma
from app.services.certificaciones.comun import (
    auditar, config, fecha, hoy, iso, json_de, org_de, propio,
)

TIPOS = ("documento", "informe_sistema", "tarea", "registro", "enlace")
ORIGENES = ("manual", "sistema", "tarea", "grc", "plantilla")


def caducidad(ev: CertEvidencia, dias: int) -> Optional[date]:
    if ev.caduca_el:
        return ev.caduca_el
    base = ev.valida_desde or (ev.created_at.date() if ev.created_at else None)
    return base + timedelta(days=int(dias or 365)) if base else None


def estado(db: Session, ev: CertEvidencia, cfg, cache: Optional[dict] = None) -> str:
    """valida | caducada | pendiente_aprobacion | pendiente."""
    cache = cache if cache is not None else {}
    if ev.document_id:
        clave = ("doc", ev.document_id)
        if clave not in cache:
            from app.models.documents import Document
            d = db.get(Document, ev.document_id)
            cache[clave] = getattr(getattr(d, "approval_status", None), "value", getattr(d, "approval_status", None)) \
                if d else None
        if cfg.exigir_evidencia_aprobada and cache[clave] != "approved":
            return "pendiente_aprobacion"
    if ev.task_id and ev.origen == "tarea":
        clave = ("task", ev.task_id)
        if clave not in cache:
            from app.models.task import Task
            t = db.get(Task, ev.task_id)
            cache[clave] = getattr(getattr(t, "status", None), "value", getattr(t, "status", None)) if t else None
        if cache[clave] != "done":
            return "pendiente"
    fin = caducidad(ev, cfg.caducidad_evidencia_dias)
    if fin is not None and fin < hoy():
        return "caducada"
    return "valida"


def serializar(db: Session, ev: CertEvidencia, cfg, cache: Optional[dict] = None) -> dict:
    control = db.get(CertControl, ev.control_id)
    return {"id": ev.id, "titulo": ev.titulo, "tipo": ev.tipo, "origen": ev.origen, "programa_id": ev.programa_id,
            "aplicabilidad_id": ev.aplicabilidad_id, "control_id": ev.control_id,
            "control": control.clave_comun if control else None, "control_titulo": control.titulo if control else None,
            "document_id": ev.document_id, "task_id": ev.task_id, "compliance_evidence_id": ev.compliance_evidence_id,
            "uri": ev.uri, "sha256": ev.sha256, "contenido": json_de(ev.contenido, None),
            "valida_desde": iso(ev.valida_desde), "caduca_el": iso(caducidad(ev, cfg.caducidad_evidencia_dias)),
            "estado": estado(db, ev, cfg, cache), "creado_por": ev.creado_por, "created_at": iso(ev.created_at)}


def de_la_fila(db: Session, fila: CertAplicabilidad) -> list[CertEvidencia]:
    """Las evidencias que cuentan para una fila de la declaración."""
    return db.query(CertEvidencia).filter(
        CertEvidencia.organization_id == fila.organization_id, CertEvidencia.control_id == fila.control_id,
        or_(CertEvidencia.aplicabilidad_id == fila.id,
            (CertEvidencia.aplicabilidad_id.is_(None)) & (CertEvidencia.programa_id == fila.programa_id),
            CertEvidencia.programa_id.is_(None))).order_by(CertEvidencia.created_at.desc()).all()


def por_control(db: Session, org: str, programa_id: str) -> dict[str, list[CertEvidencia]]:
    """Evidencias del programa y de la biblioteca agrupadas por control (para la matriz)."""
    salida: dict[str, list] = {}
    for ev in db.query(CertEvidencia).filter(
            CertEvidencia.organization_id == org,
            or_(CertEvidencia.programa_id == programa_id, CertEvidencia.programa_id.is_(None))).all():
        salida.setdefault(ev.control_id, []).append(ev)
    return salida


def listar(db: Session, usuario, *, programa_id: Optional[str] = None, control_id: Optional[str] = None,
           estado_filtro: Optional[str] = None) -> list[dict]:
    org = org_de(usuario)
    cfg = config(db, org)
    q = db.query(CertEvidencia).filter(CertEvidencia.organization_id == org)
    if programa_id:
        propio(db, CertPrograma, programa_id, usuario, "programa_de_certificacion")
        q = q.filter(or_(CertEvidencia.programa_id == programa_id, CertEvidencia.programa_id.is_(None)))
    if control_id:
        q = q.filter(CertEvidencia.control_id == control_id)
    cache: dict = {}
    filas = [serializar(db, ev, cfg, cache) for ev in q.order_by(CertEvidencia.created_at.desc()).limit(2000).all()]
    if estado_filtro:
        filas = [f for f in filas if f["estado"] == estado_filtro]
    return filas


def crear(db: Session, usuario, datos: dict, *, origen: str = "manual", confirmar: bool = True) -> CertEvidencia:
    org = org_de(usuario)
    fila = None
    if datos.get("aplicabilidad_id"):
        fila = propio(db, CertAplicabilidad, datos["aplicabilidad_id"], usuario, "fila_de_aplicabilidad")
    control_id = fila.control_id if fila else datos.get("control_id")
    if not control_id:
        raise error(422, "cert_campo_no_valido", campo="control_id")
    propio(db, CertControl, control_id, usuario, "control")
    programa_id = fila.programa_id if fila else datos.get("programa_id")
    if programa_id:
        propio(db, CertPrograma, programa_id, usuario, "programa_de_certificacion")
    tipo = datos.get("tipo") or ("documento" if datos.get("document_id") else "registro")
    if tipo not in TIPOS:
        raise error(422, "cert_campo_no_valido", campo="tipo")
    if datos.get("document_id"):
        from app.models.documents import Document
        d = db.get(Document, datos["document_id"])
        if d is None or d.organization_id != org:
            raise error(422, "cert_campo_no_valido", campo="document_id")
    sha = (datos.get("sha256") or "").lower() or None
    if sha and (len(sha) != 64 or any(c not in "0123456789abcdef" for c in sha)):
        raise error(422, "cert_campo_no_valido", campo="sha256")
    if tipo != "documento" and not (datos.get("uri") or datos.get("contenido") or datos.get("task_id")):
        raise error(422, "cert_evidencia_sin_soporte")
    ev = CertEvidencia(organization_id=org, programa_id=programa_id, aplicabilidad_id=fila.id if fila else None,
                       control_id=control_id, titulo=(datos.get("titulo") or "").strip()[:300] or "—", tipo=tipo,
                       origen=origen, document_id=datos.get("document_id"), task_id=datos.get("task_id"),
                       uri=datos.get("uri"), sha256=sha, contenido=datos.get("contenido"),
                       valida_desde=fecha(datos.get("valida_desde"), "valida_desde") or hoy(),
                       caduca_el=fecha(datos.get("caduca_el"), "caduca_el"), creado_por=getattr(usuario, "id", None))
    db.add(ev)
    db.flush()
    auditar(db, usuario, "CREATE", "evidencia", ev.id, ev.titulo,
            despues={"control_id": control_id, "programa_id": programa_id, "tipo": tipo, "origen": origen,
                     "sha256": sha, "document_id": ev.document_id})
    if confirmar:
        db.commit()
    return ev


def borrar(db: Session, usuario, evidencia_id: str) -> None:
    """Borrar una evidencia (admin): el bloqueo legal (`cert_evidencias`) lo impide al confirmar."""
    ev = propio(db, CertEvidencia, evidencia_id, usuario, "evidencia")
    auditar(db, usuario, "DELETE", "evidencia", ev.id, ev.titulo,
            antes={"control_id": ev.control_id, "sha256": ev.sha256, "origen": ev.origen})
    db.delete(ev)
    db.commit()
