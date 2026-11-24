"""Certificaciones: panel y paquete del auditor (§3.9).

- Panel: avance por norma, carencias, hallazgos abiertos, acciones vencidas,
  certificados por vencer, cobertura de evidencias e incidentes NIS2 abiertos.
- Paquete del auditor: declaración de aplicabilidad, matriz, evidencias (metadatos
  y huellas), pruebas, auditorías, hallazgos y acciones, firmado con la misma clave
  Ed25519 que el informe de cumplimiento y la cadena de auditoría
  (`informe_de_cumplimiento.firmar`). Queda traza en `cert_paquetes` (quién,
  cuándo, huella) y en el registro de auditoría. El auditor con acceso temporal
  puede descargarlo (queda en su registro).
"""
from __future__ import annotations

import hashlib
import json
from datetime import timedelta
from typing import Optional

from sqlalchemy.orm import Session

from app.models.certificaciones import (
    CertAplicabilidad, CertCertificado, CertEvidencia, CertIncidente, CertPaquete, CertPrograma, CertPrueba,
)
from app.services.certificaciones import auditorias as aud
from app.services.certificaciones import catalogo, certificados, evidencias, programas
from app.services.certificaciones.comun import (
    ahora, auditar, config, dump, hoy, iso, json_de, org_de, propio,
)


def panel(db: Session, usuario, programa_id: Optional[str] = None) -> dict:
    org = org_de(usuario)
    catalogo.asegurar_sembrado(db, org)
    cfg = config(db, org)
    progs = db.query(CertPrograma).filter(CertPrograma.organization_id == org)
    if programa_id:
        progs = progs.filter(CertPrograma.id == programa_id)
    por_norma: dict[str, dict] = {}
    carencias = []
    cobertura = {"filas": 0, "con_evidencia_valida": 0}
    for p in progs.all():
        for f in programas.aplicabilidad(db, usuario, p.id):
            if f["sede"]:
                continue
            if f["aplica"]:
                cobertura["filas"] += 1
                cobertura["con_evidencia_valida"] += int(f["evidencias_validas"] > 0)
            for m in {x["marco"] for x in f["marcos"]}:
                d = por_norma.setdefault(m, {e: 0 for e in programas.ESTADOS_MATRIZ})
                d[f["estado_matriz"]] += 1
            if f["estado_matriz"] in ("no_cumple", "caducado") and len(carencias) < 50:
                carencias.append({"programa": p.codigo, "fila_id": f["id"], "control": f["control"],
                                  "titulo": f["titulo"], "estado": f["estado_matriz"]})
    for m, d in por_norma.items():
        aplicables = sum(v for k, v in d.items() if k != "no_aplica")
        d["avance"] = round(100 * d["cumple"] / aplicables, 1) if aplicables else None
    limite = hoy() + timedelta(days=int(cfg.aviso_certificado_dias or 90))
    por_vencer = [certificados.serializar(db, c) for c in db.query(CertCertificado).filter(
        CertCertificado.organization_id == org, CertCertificado.estado == "vigente",
        CertCertificado.valido_hasta.isnot(None), CertCertificado.valido_hasta <= limite).all()]
    hallazgos = aud.hallazgos(db, usuario, programa_id=programa_id, solo_abiertos=True)
    vencidas = aud.acciones(db, usuario, programa_id=programa_id, solo_vencidas=True)
    from app.services.certificaciones import nis2
    incidentes = [i for i in nis2.listar(db, usuario, solo_abiertos=True)
                  if not programa_id or i["programa_id"] in (None, programa_id)]
    return {"por_norma": por_norma, "carencias": carencias,
            "cobertura_evidencias": {**cobertura, "porcentaje": round(100 * cobertura["con_evidencia_valida"]
                                                                       / cobertura["filas"], 1)
                                     if cobertura["filas"] else None},
            "hallazgos_abiertos": len(hallazgos),
            "hallazgos_por_tipo": {t: sum(1 for h in hallazgos if h["tipo"] == t) for t in aud.TIPOS_HALLAZGO},
            "acciones_vencidas": vencidas, "certificados_por_vencer": por_vencer,
            "incidentes_nis2_abiertos": incidentes}


def contenido_del_paquete(db: Session, programa: CertPrograma, usuario_o_none=None) -> dict:
    """Todo lo que entrega el paquete (sin ficheros: metadatos y huellas)."""
    org = programa.organization_id

    class _Ctx:  # usuario mínimo para reutilizar las consultas acotadas por empresa
        organization_id = org
        id = getattr(usuario_o_none, "id", None)

    u = usuario_o_none or _Ctx()
    cfg = config(db, org)
    filas = programas.aplicabilidad(db, u, programa.id)
    ids = [f["id"] for f in filas]
    pruebas = [programas.serializar_prueba(db, x) for x in db.query(CertPrueba).filter(
        CertPrueba.aplicabilidad_id.in_(ids)).all()] if ids else []
    evs = [evidencias.serializar(db, e, cfg) for e in db.query(CertEvidencia).filter(
        CertEvidencia.organization_id == org,
        (CertEvidencia.programa_id == programa.id) | CertEvidencia.programa_id.is_(None)).all()]
    controles_del_programa = {f["control_id"] for f in filas}
    evs = [e for e in evs if e["control_id"] in controles_del_programa]
    for e in evs:
        e.pop("contenido", None)
    return {
        "type": "contecflow.certification_auditor_package", "version": 1,
        "organization_id": org, "programa": programas.serializar(db, programa),
        "generated_at": iso(ahora()),
        "catalogo_huella": catalogo.cargar().get("huella"),
        "declaracion_de_aplicabilidad": filas, "matriz": programas.matriz(db, u, programa.id),
        "pruebas": pruebas, "evidencias": evs, "auditorias": aud.listar(db, u, programa.id),
        "hallazgos": aud.hallazgos(db, u, programa_id=programa.id),
        "acciones": aud.acciones(db, u, programa_id=programa.id),
        "certificados": certificados.listar(db, u, programa.id),
    }


def generar_paquete(db: Session, usuario, programa_id: str, *, acceso=None) -> dict:
    """Paquete firmado y su traza. `usuario` None + `acceso` = lo descarga el auditor externo."""
    from app.services.informe_de_cumplimiento import firmar
    if acceso is not None:
        programa = db.get(CertPrograma, acceso.programa_id)
    else:
        programa = propio(db, CertPrograma, programa_id, usuario, "programa_de_certificacion")
    doc = firmar(contenido_del_paquete(db, programa, usuario))
    huella = hashlib.sha256(json.dumps(doc, sort_keys=True, ensure_ascii=False, default=str).encode()).hexdigest()
    resumen = {"filas": len(doc["declaracion_de_aplicabilidad"]), "evidencias": len(doc["evidencias"]),
               "hallazgos": len(doc["hallazgos"]), "acciones": len(doc["acciones"])}
    db.add(CertPaquete(organization_id=programa.organization_id, programa_id=programa.id,
                       generado_por=getattr(usuario, "id", None), acceso_id=getattr(acceso, "id", None),
                       sha256=huella, resumen=dump(resumen)))
    if usuario is not None:
        auditar(db, usuario, "EXPORT", "paquete_auditor", programa.id, programa.codigo,
                meta={"sha256": huella, **resumen})
    db.commit()
    return {**doc, "package_sha256": huella}


def paquetes(db: Session, usuario, programa_id: str) -> list[dict]:
    p = propio(db, CertPrograma, programa_id, usuario, "programa_de_certificacion")
    from app.services.certificaciones.comun import nombre_de
    return [{"id": x.id, "sha256": x.sha256, "resumen": json_de(x.resumen, {}), "generado_en": iso(x.generado_en),
             "generado_por": nombre_de(db, x.generado_por), "por_auditor": x.acceso_id is not None}
            for x in db.query(CertPaquete).filter(CertPaquete.programa_id == p.id)
            .order_by(CertPaquete.generado_en.desc()).all()]


def vista_del_auditor(db: Session, acceso) -> dict:
    """Lo que ve el auditor con su enlace: solo su programa y solo lectura."""
    programa = db.get(CertPrograma, acceso.programa_id)
    datos = contenido_del_paquete(db, programa)
    from app.models.certificaciones import CertAuditor
    a = db.get(CertAuditor, acceso.auditor_id)
    return {**datos, "acceso": {"auditor": a.nombre if a else None, "hasta": iso(acceso.hasta)},
            "incidentes_nis2": [], "solo_lectura": True,
            "filas_total": db.query(CertAplicabilidad).filter(CertAplicabilidad.programa_id == programa.id).count(),
            "incidentes_abiertos": db.query(CertIncidente).filter(
                CertIncidente.organization_id == programa.organization_id,
                CertIncidente.programa_id == programa.id, CertIncidente.estado.notin_(("cerrado", "descartado"))
            ).count()}
