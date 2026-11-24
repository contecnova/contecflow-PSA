"""Certificaciones: auditores y empresas colaboradoras (§3.6) y acceso temporal del auditor.

- Empresas: entidades certificadoras, proveedores de auditoría de ENX,
  consultoras, auditores SOX, laboratorios 62443… Pueden enlazarse a su ficha de
  **Proveedores** (`subcontractor_id`) para reutilizar contratos, NDA y GRC.
- Personas: cualificación, independencia, conflictos de interés, NDA y periodo
  de actuación (dato personal: `rgpd.py`).
- Acceso temporal de solo lectura (decisión 2 de la propuesta): un enlace del
  portal (`/auditor/<token>`) limitado a UN programa y a un periodo (como mucho
  `acceso_auditor_max_dias`). Solo se guarda la huella SHA-256 del token; se
  revoca en cualquier momento; cada consulta queda en `cert_accesos_registro` y
  en el registro de auditoría. Exige NDA firmado, independencia declarada y que
  el periodo caiga dentro del periodo de actuación de la persona.
"""
from __future__ import annotations

import hashlib
import secrets
from datetime import timedelta
from typing import Optional

from sqlalchemy.orm import Session

from app.core.codigos_de_error import error
from app.models.certificaciones import (
    CertAcceso, CertAccesoRegistro, CertAuditor, CertEntidad, CertPrograma,
)
from app.services.certificaciones.comun import (
    ahora, auditar, aware, config, dump, elegir, fecha, hoy, iso, json_de, nombre_de, org_de, propio,
)

TIPOS_DE_ENTIDAD = ("certificadora", "proveedor_enx", "consultora", "auditor_sox", "laboratorio_62443",
                    "autoridad", "otra")


def huella_de_token(token: str) -> str:
    return hashlib.sha256((token or "").encode()).hexdigest()


# ── Empresas colaboradoras ───────────────────────────────────────────────────

def serializar_entidad(e: CertEntidad) -> dict:
    return {"id": e.id, "nombre": e.nombre, "tipo": e.tipo, "acreditaciones": json_de(e.acreditaciones, []),
            "subcontractor_id": e.subcontractor_id, "contacto_email": e.contacto_email, "web": e.web,
            "notas": e.notas, "activo": e.activo}


def entidades(db: Session, usuario) -> list[dict]:
    org = org_de(usuario)
    return [serializar_entidad(e) for e in db.query(CertEntidad).filter(CertEntidad.organization_id == org)
            .order_by(CertEntidad.nombre).all()]


def guardar_entidad(db: Session, usuario, datos: dict, entidad_id: Optional[str] = None) -> dict:
    org = org_de(usuario)
    e = propio(db, CertEntidad, entidad_id, usuario, "entidad") if entidad_id else CertEntidad(organization_id=org)
    if "nombre" in datos or not entidad_id:
        nombre = (datos.get("nombre") or "").strip()
        if not nombre:
            raise error(422, "cert_campo_no_valido", campo="nombre")
        repetida = db.query(CertEntidad.id).filter(CertEntidad.organization_id == org, CertEntidad.nombre == nombre,
                                                   CertEntidad.id != (e.id or "")).first()
        if repetida:
            raise error(409, "cert_entidad_repetida")
        e.nombre = nombre[:200]
    if "tipo" in datos or not entidad_id:
        e.tipo = elegir(datos.get("tipo") or "otra", TIPOS_DE_ENTIDAD, "tipo")
    if "acreditaciones" in datos and datos["acreditaciones"] is not None:
        e.acreditaciones = dump([str(x) for x in datos["acreditaciones"]])
    if "subcontractor_id" in datos:
        if datos["subcontractor_id"]:
            from app.models.enterprise import Subcontractor
            s = db.get(Subcontractor, datos["subcontractor_id"])
            if s is None or s.organization_id != org:
                raise error(422, "cert_campo_no_valido", campo="subcontractor_id")
        e.subcontractor_id = datos["subcontractor_id"] or None
    for k in ("contacto_email", "web", "notas", "activo"):
        if k in datos and datos[k] is not None:
            setattr(e, k, datos[k])
    if not entidad_id:
        db.add(e)
    db.flush()
    auditar(db, usuario, "UPDATE" if entidad_id else "CREATE", "entidad", e.id, e.nombre,
            despues=serializar_entidad(e))
    db.commit()
    return serializar_entidad(e)


# ── Auditores (personas) ─────────────────────────────────────────────────────

def serializar_auditor(db: Session, a: CertAuditor) -> dict:
    entidad = db.get(CertEntidad, a.entidad_id) if a.entidad_id else None
    return {"id": a.id, "entidad_id": a.entidad_id, "entidad": entidad.nombre if entidad else None,
            "nombre": a.nombre, "email": a.email, "cualificaciones": json_de(a.cualificaciones, []),
            "independencia_declarada": a.independencia_declarada, "conflictos_interes": a.conflictos_interes,
            "nda_firmado_el": iso(a.nda_firmado_el), "nda_document_id": a.nda_document_id,
            "desde": iso(a.desde), "hasta": iso(a.hasta), "activo": a.activo, "suprimido": a.suprimido_en is not None}


def auditores(db: Session, usuario) -> list[dict]:
    org = org_de(usuario)
    return [serializar_auditor(db, a) for a in db.query(CertAuditor).filter(CertAuditor.organization_id == org)
            .order_by(CertAuditor.nombre).all()]


def guardar_auditor(db: Session, usuario, datos: dict, auditor_id: Optional[str] = None) -> dict:
    org = org_de(usuario)
    a = propio(db, CertAuditor, auditor_id, usuario, "auditor") if auditor_id else CertAuditor(organization_id=org)
    if a.suprimido_en is not None:
        raise error(409, "cert_auditor_suprimido")
    if "nombre" in datos or not auditor_id:
        nombre = (datos.get("nombre") or "").strip()
        if not nombre:
            raise error(422, "cert_campo_no_valido", campo="nombre")
        a.nombre = nombre[:200]
    if "entidad_id" in datos:
        a.entidad_id = propio(db, CertEntidad, datos["entidad_id"], usuario, "entidad").id if datos["entidad_id"] \
            else None
    if "cualificaciones" in datos and datos["cualificaciones"] is not None:
        a.cualificaciones = dump([str(x) for x in datos["cualificaciones"]])
    for k in ("nda_firmado_el", "desde", "hasta"):
        if k in datos:
            setattr(a, k, fecha(datos[k], k))
    if "nda_document_id" in datos:
        if datos["nda_document_id"]:
            from app.models.documents import Document
            d = db.get(Document, datos["nda_document_id"])
            if d is None or d.organization_id != org:
                raise error(422, "cert_campo_no_valido", campo="nda_document_id")
        a.nda_document_id = datos["nda_document_id"] or None
    for k in ("email", "independencia_declarada", "conflictos_interes", "activo"):
        if k in datos and datos[k] is not None:
            setattr(a, k, datos[k])
    if a.desde and a.hasta and a.hasta < a.desde:
        raise error(422, "cert_campo_no_valido", campo="hasta")
    if not auditor_id:
        db.add(a)
    db.flush()
    # Sin el correo ni los conflictos en claro en el registro (dato personal): solo qué cambió.
    auditar(db, usuario, "UPDATE" if auditor_id else "CREATE", "auditor", a.id, a.id,
            despues={"campos": sorted(k for k in datos if datos[k] is not None)})
    db.commit()
    return serializar_auditor(db, a)


# ── Acceso temporal de solo lectura ──────────────────────────────────────────

def serializar_acceso(db: Session, x: CertAcceso) -> dict:
    a = db.get(CertAuditor, x.auditor_id)
    p = db.get(CertPrograma, x.programa_id)
    momento = ahora()
    vigente = x.revocado_en is None and aware(x.desde) <= momento <= aware(x.hasta)
    return {"id": x.id, "auditor_id": x.auditor_id, "auditor": a.nombre if a else None,
            "programa_id": x.programa_id, "programa": p.codigo if p else None, "desde": iso(x.desde),
            "hasta": iso(x.hasta), "revocado_en": iso(x.revocado_en), "revocado_por": nombre_de(db, x.revocado_por),
            "creado_por": nombre_de(db, x.creado_por), "ultimo_uso_en": iso(x.ultimo_uso_en), "usos": x.usos,
            "vigente": vigente}


def accesos(db: Session, usuario, programa_id: Optional[str] = None) -> list[dict]:
    org = org_de(usuario)
    q = db.query(CertAcceso).filter(CertAcceso.organization_id == org)
    if programa_id:
        q = q.filter(CertAcceso.programa_id == programa_id)
    return [serializar_acceso(db, x) for x in q.order_by(CertAcceso.created_at.desc()).all()]


def conceder(db: Session, usuario, datos: dict) -> dict:
    """Crea el acceso y devuelve el token UNA vez (solo se guarda su huella)."""
    org = org_de(usuario)
    a = propio(db, CertAuditor, datos.get("auditor_id"), usuario, "auditor")
    p = propio(db, CertPrograma, datos.get("programa_id"), usuario, "programa_de_certificacion")
    if not a.activo or a.suprimido_en is not None:
        raise error(409, "cert_auditor_inactivo")
    if not a.nda_firmado_el:
        raise error(409, "cert_auditor_sin_nda")
    if not a.independencia_declarada:
        raise error(409, "cert_auditor_sin_independencia")
    maximo = int(config(db, org).acceso_auditor_max_dias or 30)
    dias = int(datos.get("dias") or min(7, maximo))
    if dias < 1 or dias > maximo:
        raise error(422, "cert_acceso_demasiado_largo", maximo=maximo)
    desde = ahora()
    hasta = desde + timedelta(days=dias)
    if (a.hasta and hasta.date() > a.hasta) or (a.desde and desde.date() < a.desde):
        raise error(409, "cert_acceso_fuera_de_periodo")
    token = secrets.token_urlsafe(32)
    x = CertAcceso(organization_id=org, auditor_id=a.id, programa_id=p.id, token_hash=huella_de_token(token),
                   desde=desde, hasta=hasta, creado_por=usuario.id, usos=0)
    db.add(x)
    db.flush()
    auditar(db, usuario, "GRANT", "acceso", x.id, p.codigo, despues={"auditor_id": a.id, "dias": dias,
                                                                      "hasta": iso(hasta)})
    db.commit()
    return {**serializar_acceso(db, x), "token": token, "url": f"/auditor/{token}"}


def revocar(db: Session, usuario, acceso_id: str) -> dict:
    x = propio(db, CertAcceso, acceso_id, usuario, "acceso")
    if x.revocado_en is None:
        x.revocado_en = ahora()
        x.revocado_por = usuario.id
        auditar(db, usuario, "REVOKE", "acceso", x.id)
        db.commit()
    return serializar_acceso(db, x)


def registro(db: Session, usuario, acceso_id: str) -> list[dict]:
    x = propio(db, CertAcceso, acceso_id, usuario, "acceso")
    return [{"recurso": r.recurso, "detalle": r.detalle, "ip": r.ip, "en": iso(r.en)}
            for r in db.query(CertAccesoRegistro).filter(CertAccesoRegistro.acceso_id == x.id)
            .order_by(CertAccesoRegistro.en.desc()).limit(1000).all()]


def resolver_token(db: Session, token: str) -> CertAcceso:
    """El acceso vigente del token (la sesión viene en contexto de sistema; publica la empresa al resolverlo)."""
    if not token or len(token) < 20:
        raise error(401, "cert_acceso_no_valido")
    x = db.query(CertAcceso).filter(CertAcceso.token_hash == huella_de_token(token)).first()
    momento = ahora()
    if x is None or x.revocado_en is not None or not (aware(x.desde) <= momento <= aware(x.hasta)):
        raise error(401, "cert_acceso_no_valido")
    a = db.get(CertAuditor, x.auditor_id)
    if a is None or not a.activo or a.suprimido_en is not None:
        raise error(401, "cert_acceso_no_valido")
    from app.db.session import publicar_empresa
    publicar_empresa(db, x.organization_id)
    return x


def apuntar(db: Session, x: CertAcceso, recurso: str, detalle: Optional[str], ip: Optional[str]) -> None:
    """Lo que consulta el auditor: en su registro y en el de auditoría (sin usuario: el actor es el acceso)."""
    x.usos = (x.usos or 0) + 1
    x.ultimo_uso_en = ahora()
    db.add(CertAccesoRegistro(organization_id=x.organization_id, acceso_id=x.id, recurso=recurso,
                              detalle=(detalle or "")[:300] or None, ip=(ip or "")[:64] or None))
    from app.services.audit import audit_log
    audit_log(db, None, "AUDITOR_READ", "certificaciones", x.id, f"acceso:{recurso}"[:255],
              metadata={"entidad": "acceso", "auditor_id": x.auditor_id, "programa_id": x.programa_id,
                        "organization_id": x.organization_id, "recurso": recurso}, ip_address=ip)
    db.commit()


def dentro_de_plazo(fecha_fin) -> bool:
    return fecha_fin is None or fecha_fin >= hoy()
