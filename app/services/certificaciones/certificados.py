"""Certificaciones: certificados y etiquetas (§3.7), con ciclo de vida igual que una licencia.

Emisión, alcance, entidad certificadora y número; auditorías de seguimiento (año
1 y 2) y renovación (año 3). TISAX: etiqueta de 3 años con el identificador del
portal ENX y el del alcance de la evaluación. Si no se da `proxima_auditoria`,
se calcula: seguimiento a los 12 y 24 meses de la emisión y renovación antes del
vencimiento. Los avisos de vencimiento y de auditoría próxima los da
`trabajos.revisar_vencimientos` (como los de Licencias).
"""
from __future__ import annotations

from datetime import date
from typing import Optional

from sqlalchemy.orm import Session

from app.core.codigos_de_error import error
from app.models.certificaciones import CertCertificado, CertEntidad, CertMarco, CertPrograma
from app.services.certificaciones.comun import auditar, elegir, fecha, hoy, iso, org_de, propio

ESTADOS = ("vigente", "suspendido", "retirado", "caducado")
TIPOS_PROXIMA = ("seguimiento_1", "seguimiento_2", "renovacion")


def _anios(d: date, n: int) -> date:
    try:
        return d.replace(year=d.year + n)
    except ValueError:  # 29 de febrero
        return d.replace(year=d.year + n, day=28)


def siguiente_auditoria(c: CertCertificado, referencia: Optional[date] = None) -> tuple[Optional[date], Optional[str]]:
    """(fecha, tipo) de la próxima auditoría del ciclo de 3 años."""
    if not c.emitido_el:
        return None, None
    ref = referencia or hoy()
    for n, tipo in ((1, "seguimiento_1"), (2, "seguimiento_2")):
        f = _anios(c.emitido_el, n)
        if f >= ref:
            return f, tipo
    if c.valido_hasta:
        return c.valido_hasta, "renovacion"
    return _anios(c.emitido_el, 3), "renovacion"


def serializar(db: Session, c: CertCertificado) -> dict:
    marco = db.get(CertMarco, c.marco_id) if c.marco_id else None
    entidad = db.get(CertEntidad, c.entidad_id) if c.entidad_id else None
    dias = (c.valido_hasta - hoy()).days if c.valido_hasta else None
    return {"id": c.id, "numero": c.numero, "programa_id": c.programa_id, "marco_id": c.marco_id,
            "marco": marco.clave if marco else None, "entidad_id": c.entidad_id,
            "entidad": entidad.nombre if entidad else None, "alcance": c.alcance, "nivel": c.nivel,
            "emitido_el": iso(c.emitido_el), "valido_hasta": iso(c.valido_hasta), "dias_para_vencer": dias,
            "estado": "caducado" if c.estado == "vigente" and dias is not None and dias < 0 else c.estado,
            "enx_id": c.enx_id, "enx_ambito": c.enx_ambito, "proxima_auditoria": iso(c.proxima_auditoria),
            "tipo_proxima": c.tipo_proxima, "document_id": c.document_id}


def listar(db: Session, usuario, programa_id: Optional[str] = None) -> list[dict]:
    org = org_de(usuario)
    q = db.query(CertCertificado).filter(CertCertificado.organization_id == org)
    if programa_id:
        q = q.filter(CertCertificado.programa_id == programa_id)
    return [serializar(db, c) for c in q.order_by(CertCertificado.valido_hasta.asc().nullslast()).all()]


def guardar(db: Session, usuario, datos: dict, certificado_id: Optional[str] = None) -> dict:
    org = org_de(usuario)
    c = propio(db, CertCertificado, certificado_id, usuario, "certificado") if certificado_id \
        else CertCertificado(organization_id=org, creado_por=usuario.id, estado="vigente")
    if "numero" in datos or not certificado_id:
        numero = (datos.get("numero") or "").strip()
        if not numero:
            raise error(422, "cert_campo_no_valido", campo="numero")
        if db.query(CertCertificado.id).filter(CertCertificado.organization_id == org,
                                               CertCertificado.numero == numero,
                                               CertCertificado.id != (c.id or "")).first():
            raise error(409, "cert_certificado_repetido")
        c.numero = numero[:120]
    if "marco" in datos:
        m = db.query(CertMarco).filter(CertMarco.organization_id == org, CertMarco.clave == datos["marco"]).first() \
            if datos["marco"] else None
        if datos["marco"] and m is None:
            raise error(422, "cert_campo_no_valido", campo="marco")
        c.marco_id = m.id if m else None
    if "programa_id" in datos:
        c.programa_id = propio(db, CertPrograma, datos["programa_id"], usuario,
                               "programa_de_certificacion").id if datos["programa_id"] else None
    if "entidad_id" in datos:
        c.entidad_id = propio(db, CertEntidad, datos["entidad_id"], usuario, "entidad").id if datos["entidad_id"] \
            else None
    for k in ("emitido_el", "valido_hasta", "proxima_auditoria"):
        if k in datos:
            setattr(c, k, fecha(datos[k], k))
    if "estado" in datos and datos["estado"]:
        c.estado = elegir(datos["estado"], ESTADOS, "estado")
    if "tipo_proxima" in datos and datos["tipo_proxima"]:
        c.tipo_proxima = elegir(datos["tipo_proxima"], TIPOS_PROXIMA, "tipo_proxima")
    for k in ("alcance", "nivel", "enx_id", "enx_ambito", "document_id"):
        if k in datos:
            setattr(c, k, datos[k])
    marco = db.get(CertMarco, c.marco_id) if c.marco_id else None
    if c.emitido_el and not c.valido_hasta:
        c.valido_hasta = _anios(c.emitido_el, 3)
    if marco is not None and marco.clave == "tisax" and c.emitido_el and c.valido_hasta \
            and c.valido_hasta > _anios(c.emitido_el, 3):
        raise error(422, "cert_tisax_mas_de_tres_anios")
    if c.valido_hasta and c.emitido_el and c.valido_hasta < c.emitido_el:
        raise error(422, "cert_campo_no_valido", campo="valido_hasta")
    if "proxima_auditoria" not in datos or not datos.get("proxima_auditoria"):
        c.proxima_auditoria, tipo = siguiente_auditoria(c)
        c.tipo_proxima = c.tipo_proxima if datos.get("tipo_proxima") else tipo
    # Cambia la fecha: los avisos vuelven a darse.
    c.aviso_vencimiento_en = c.aviso_auditoria_en = None
    if not certificado_id:
        db.add(c)
    db.flush()
    auditar(db, usuario, "UPDATE" if certificado_id else "CREATE", "certificado", c.id, c.numero,
            despues=serializar(db, c))
    db.commit()
    return serializar(db, c)
