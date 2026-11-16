"""Qué licencia de ALM es cada producto/SKU que leen las fuentes.

La conciliación mapea sola lo inequívoco (SKU igual o un único nombre igual);
el resto aparece aquí con una sugerencia (la licencia cuyo nombre comparte más
palabras con el producto) para que una persona lo confirme, lo cambie o lo
marque como «no se controla». Guardar un mapeo pone al día al momento las
evidencias y los derechos ya leídos de ese producto.
"""
from __future__ import annotations

from typing import Optional

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.core.errores import ErrorDeDominio
from app.models.alm import ALMLicense
from app.models.alm import ALMLicenseAssignment as Asignacion
from app.models.alm_uso import ALMUsoDerecho, ALMUsoEvidencia, ALMUsoMapeo
from app.services.alm_uso._comun import TITULAR_DISPOSITIVO, TITULAR_PERSONA, exigir_org, normalizar
from app.services.alm_uso.conciliacion import PRODUCTO_EQUIPO


def _sugerencia(nombre: str, licencias: list) -> Optional[dict]:
    palabras = set(normalizar(nombre).split())
    if not palabras:
        return None
    mejor, puntos = None, 0.0
    for lic in licencias:
        otras = set(normalizar(f"{lic.name} {lic.product_name or ''} {lic.edition or ''} {lic.sku or ''}").split())
        if not otras:
            continue
        p = len(palabras & otras) / len(palabras | otras)
        if p > puntos:
            mejor, puntos = lic, p
    return {"license_id": mejor.id, "nombre": mejor.name, "parecido": round(puntos, 2)} if mejor and puntos > 0 else None


def productos(db: Session, org: str, solo_sin_licencia: bool = False) -> list[dict]:
    exigir_org(org)
    licencias = db.query(ALMLicense).filter(ALMLicense.organization_id == org, ALMLicense.is_active.is_(True)).all()
    nombres = {l.id: l.name for l in licencias}
    mapeos = {(m.fuente, m.producto): m for m in db.query(ALMUsoMapeo).filter(ALMUsoMapeo.organization_id == org)}
    filas = db.query(ALMUsoEvidencia.fuente, ALMUsoEvidencia.producto, func.max(ALMUsoEvidencia.nombre_producto),
                     func.max(ALMUsoEvidencia.license_id), func.count(ALMUsoEvidencia.id)).filter(
        ALMUsoEvidencia.organization_id == org, ALMUsoEvidencia.producto != PRODUCTO_EQUIPO,
        ALMUsoEvidencia.vista_en_ultima_lectura.is_(True)).group_by(
        ALMUsoEvidencia.fuente, ALMUsoEvidencia.producto).all()
    salida = []
    for fuente, producto, nombre, lic_id, n in filas:
        m = mapeos.get((fuente, producto))
        if solo_sin_licencia and (lic_id or (m and m.ignorar)):
            continue
        salida.append({"fuente": fuente, "producto": producto, "nombre": nombre or producto, "titulares": n,
                       "license_id": lic_id, "licencia": nombres.get(lic_id),
                       "mapeo": "manual" if m and not m.ignorar else ("ignorado" if m and m.ignorar else
                                                                      ("automatico" if lic_id else None)),
                       "sugerencia": None if lic_id else _sugerencia(nombre or producto, licencias)})
    salida.sort(key=lambda x: (x["license_id"] is not None, -x["titulares"], x["nombre"].lower()))
    return salida


def guardar(db: Session, usuario, fuente: str, producto: str, license_id: Optional[str], ignorar: bool) -> dict:
    from app.services.audit import audit_log
    org = exigir_org(getattr(usuario, "organization_id", None))
    if license_id and db.query(ALMLicense.id).filter(ALMLicense.id == license_id,
                                                     ALMLicense.organization_id == org).first() is None:
        raise ErrorDeDominio(404, {"code": "ALM_USAGE_LICENSE_NOT_FOUND", "message": "Licencia no encontrada"})
    m = db.query(ALMUsoMapeo).filter(ALMUsoMapeo.organization_id == org, ALMUsoMapeo.fuente == fuente,
                                     ALMUsoMapeo.producto == producto).first()
    anterior = (m.license_id, m.ignorar) if m else None
    if not license_id and not ignorar:
        if m is not None:
            db.delete(m)       # vuelve a mapearse sola (SKU / nombre)
    else:
        if m is None:
            m = ALMUsoMapeo(organization_id=org, fuente=fuente, producto=producto[:255], created_by=usuario.id)
            db.add(m)
        m.license_id, m.ignorar = (None, True) if ignorar else (license_id, False)
    nuevo = None if ignorar else license_id
    evs = db.query(ALMUsoEvidencia).filter(ALMUsoEvidencia.organization_id == org, ALMUsoEvidencia.fuente == fuente,
                                           ALMUsoEvidencia.producto == producto).all()
    for e in evs:
        e.license_id = nuevo
        e.assignment_id = None
        if nuevo:
            q = db.query(Asignacion.id).filter(Asignacion.organization_id == org, Asignacion.license_id == nuevo,
                                               Asignacion.status == "active")
            if e.titular_tipo == TITULAR_PERSONA and e.user_id:
                fila = q.filter(Asignacion.holder_user_id == e.user_id).first()
            elif e.titular_tipo == TITULAR_DISPOSITIVO and e.asset_id:
                fila = q.filter(Asignacion.holder_asset_id == e.asset_id).first()
            else:
                fila = None
            e.assignment_id = fila[0] if fila else None
    db.query(ALMUsoDerecho).filter(ALMUsoDerecho.organization_id == org, ALMUsoDerecho.fuente == fuente,
                                   ALMUsoDerecho.sku == producto).update({"license_id": nuevo},
                                                                         synchronize_session=False)
    audit_log(db, usuario, "UPDATE", "alm_uso_mapeo", None, f"{fuente}:{producto}",
              old_values={"license_id": anterior[0], "ignorar": anterior[1]} if anterior else None,
              new_values={"license_id": nuevo, "ignorar": bool(ignorar)})
    db.commit()
    return {"fuente": fuente, "producto": producto, "license_id": nuevo, "ignorar": bool(ignorar),
            "evidencias": len(evs)}
