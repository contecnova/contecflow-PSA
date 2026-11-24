"""Certificaciones: evaluación de proveedores críticos de la cadena de suministro (NIS2 art. 21.2.d, §3.8).

Enlaza con **Proveedores** (`subcontractors`): la ficha, contratos, documentos y
la evaluación de riesgo de Proveedores siguen allí; aquí queda la evaluación
para el programa (criticidad, resultado, próxima revisión) y su evidencia.
"""
from __future__ import annotations

from typing import Optional

from sqlalchemy.orm import Session

from app.core.codigos_de_error import error
from app.models.certificaciones import CertPrograma, CertProveedor
from app.services.certificaciones.comun import auditar, elegir, fecha, hoy, iso, nombre_de, org_de, propio

CRITICIDADES = ("alta", "media", "baja")
RESULTADOS = ("pendiente", "aceptable", "con_condiciones", "no_aceptable")


def serializar(db: Session, x: CertProveedor) -> dict:
    vencida = x.proxima_evaluacion is not None and x.proxima_evaluacion < hoy()
    return {"id": x.id, "programa_id": x.programa_id, "subcontractor_id": x.subcontractor_id, "nombre": x.nombre,
            "criticidad": x.criticidad, "servicios": x.servicios, "resultado": x.resultado, "riesgo": x.riesgo,
            "evaluado_por": nombre_de(db, x.evaluado_por), "evaluado_en": iso(x.evaluado_en),
            "proxima_evaluacion": iso(x.proxima_evaluacion), "vencida": vencida, "notas": x.notas}


def listar(db: Session, usuario, programa_id: Optional[str] = None) -> list[dict]:
    org = org_de(usuario)
    q = db.query(CertProveedor).filter(CertProveedor.organization_id == org)
    if programa_id:
        q = q.filter(CertProveedor.programa_id == programa_id)
    return [serializar(db, x) for x in q.order_by(CertProveedor.nombre).all()]


def guardar(db: Session, usuario, datos: dict, proveedor_id: Optional[str] = None) -> dict:
    org = org_de(usuario)
    x = propio(db, CertProveedor, proveedor_id, usuario, "proveedor_critico") if proveedor_id \
        else CertProveedor(organization_id=org)
    if datos.get("subcontractor_id"):
        from app.models.enterprise import Subcontractor
        s = db.get(Subcontractor, datos["subcontractor_id"])
        if s is None or s.organization_id != org:
            raise error(422, "cert_campo_no_valido", campo="subcontractor_id")
        x.subcontractor_id = s.id
        x.nombre = x.nombre or s.name
    if "nombre" in datos and datos["nombre"]:
        x.nombre = datos["nombre"].strip()[:200]
    if not x.nombre:
        raise error(422, "cert_campo_no_valido", campo="nombre")
    if "programa_id" in datos:
        x.programa_id = propio(db, CertPrograma, datos["programa_id"], usuario, "programa_de_certificacion").id \
            if datos["programa_id"] else None
    if "criticidad" in datos and datos["criticidad"]:
        x.criticidad = elegir(datos["criticidad"], CRITICIDADES, "criticidad")
    if "resultado" in datos and datos["resultado"]:
        x.resultado = elegir(datos["resultado"], RESULTADOS, "resultado")
        if x.resultado != "pendiente":
            x.evaluado_por = usuario.id
            x.evaluado_en = hoy()
    if "proxima_evaluacion" in datos:
        x.proxima_evaluacion = fecha(datos["proxima_evaluacion"], "proxima_evaluacion")
    for k in ("servicios", "riesgo", "notas"):
        if k in datos:
            setattr(x, k, datos[k])
    if not proveedor_id:
        db.add(x)
    db.flush()
    auditar(db, usuario, "UPDATE" if proveedor_id else "CREATE", "proveedor_critico", x.id, x.nombre,
            despues={"criticidad": x.criticidad, "resultado": x.resultado})
    db.commit()
    return serializar(db, x)
