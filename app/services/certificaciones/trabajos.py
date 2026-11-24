"""Certificaciones: trabajos de fondo (avisos de vencimiento y relojes NIS2), por empresa.

- `revisar_vencimientos(db, org)` (beat diario `cert-vencimientos`):
  · certificados que vencen en `aviso_certificado_dias` (una vez) y auditoría del
    ciclo próxima en `aviso_auditoria_dias` (una vez), como en Licencias;
  · evidencias que caducan en `aviso_evidencia_dias` (una vez por evidencia);
  · acciones correctivas vencidas (una vez);
  · y aporta la evidencia de las tareas enlazadas ya cerradas (`programas.medir`
    sin medir: solo tareas) para que no dependa de que alguien abra la pantalla.
- `relojes_nis2(db, org)` (beat cada 15 min `cert-nis2-relojes`): avisa al
  responsable del incidente 6 h antes de cada plazo y al vencer, una vez cada uno.
"""
from __future__ import annotations

from datetime import timedelta

from sqlalchemy.orm import Session

from app.models.certificaciones import (
    CertAccion, CertAplicabilidad, CertCertificado, CertControlTarea, CertEvidencia, CertHallazgo, CertIncidente,
    CertPrograma,
)
from app.services.certificaciones.comun import ahora, avisar, config, dump, hoy, iso, json_de

_URL = "/certificaciones"


def _responsables(db: Session, org: str, programa_id) -> set:
    p = db.get(CertPrograma, programa_id) if programa_id else None
    return {x for x in ((p.responsable_id, p.patrocinador_id) if p else ()) if x}


def revisar_vencimientos(db: Session, org: str) -> dict:
    from app.services.certificaciones import evidencias as ev_svc
    cfg = config(db, org)
    hoy_ = hoy()
    momento = ahora()
    n = {"cert_certificados_avisados": 0, "cert_auditorias_avisadas": 0, "cert_evidencias_avisadas": 0,
         "cert_acciones_vencidas_avisadas": 0, "cert_evidencias_de_tareas": 0}
    for c in db.query(CertCertificado).filter(CertCertificado.organization_id == org,
                                              CertCertificado.estado == "vigente").all():
        destinatarios = _responsables(db, org, c.programa_id)
        if c.valido_hasta and c.aviso_vencimiento_en is None and \
                c.valido_hasta <= hoy_ + timedelta(days=int(cfg.aviso_certificado_dias or 90)):
            for u in destinatarios:
                avisar(db, u, "certificado_vence", c.numero, c.id, f"{_URL}?tab=certificados", fecha=iso(c.valido_hasta))
            c.aviso_vencimiento_en = momento
            n["cert_certificados_avisados"] += 1
        if c.proxima_auditoria and c.aviso_auditoria_en is None and \
                c.proxima_auditoria <= hoy_ + timedelta(days=int(cfg.aviso_auditoria_dias or 30)):
            for u in destinatarios:
                avisar(db, u, "auditoria_proxima", c.numero, c.id, f"{_URL}?tab=certificados",
                       fecha=iso(c.proxima_auditoria), tipo=c.tipo_proxima or "")
            c.aviso_auditoria_en = momento
            n["cert_auditorias_avisadas"] += 1
    limite = hoy_ + timedelta(days=int(cfg.aviso_evidencia_dias or 30))
    for e in db.query(CertEvidencia).filter(CertEvidencia.organization_id == org,
                                            CertEvidencia.aviso_caducidad_en.is_(None),
                                            CertEvidencia.origen != "sistema").all():
        fin = ev_svc.caducidad(e, cfg.caducidad_evidencia_dias)
        if fin is None or fin > limite:
            continue
        fila = db.get(CertAplicabilidad, e.aplicabilidad_id) if e.aplicabilidad_id else None
        destinatario = (fila.responsable_id if fila else None) or e.creado_por
        avisar(db, destinatario, "evidencia_caduca", e.titulo[:80], e.id, f"{_URL}?tab=evidencias", fecha=iso(fin))
        e.aviso_caducidad_en = momento
        n["cert_evidencias_avisadas"] += 1
    for x in db.query(CertAccion).filter(CertAccion.organization_id == org, CertAccion.aviso_vencida_en.is_(None),
                                         CertAccion.estado.in_(("abierta", "en_curso")),
                                         CertAccion.fecha_limite < hoy_).all():
        h = db.get(CertHallazgo, x.hallazgo_id)
        avisar(db, x.responsable_id, "capa_vencida", h.codigo if h else "CAPA", x.id, f"{_URL}?tab=auditorias",
               fecha=iso(x.fecha_limite))
        x.aviso_vencida_en = momento
        n["cert_acciones_vencidas_avisadas"] += 1
    # Evidencia de las tareas enlazadas que ya se cerraron.
    from app.models.task import Task
    for enlace in db.query(CertControlTarea).filter(CertControlTarea.organization_id == org).all():
        t = db.get(Task, enlace.task_id)
        if t is None or getattr(t.status, "value", t.status) != "done":
            continue
        if db.query(CertEvidencia.id).filter(CertEvidencia.aplicabilidad_id == enlace.aplicabilidad_id,
                                             CertEvidencia.task_id == t.id).first() is not None:
            continue
        f = db.get(CertAplicabilidad, enlace.aplicabilidad_id)
        db.add(CertEvidencia(organization_id=org, programa_id=f.programa_id, aplicabilidad_id=f.id,
                             control_id=f.control_id, titulo=f"Tarea cerrada: {t.code or ''} {t.title}"[:300],
                             tipo="tarea", origen="tarea", task_id=t.id, valida_desde=hoy_))
        n["cert_evidencias_de_tareas"] += 1
    db.commit()
    return n


def relojes_nis2(db: Session, org: str) -> dict:
    from app.services.certificaciones.nis2 import plazos
    cfg = config(db, org)
    momento = ahora()
    enviados = 0
    campos = {"alerta": "alerta_enviada_en", "notificacion": "notificacion_enviada_en",
              "informe_final": "informe_final_enviado_en"}
    for inc in db.query(CertIncidente).filter(CertIncidente.organization_id == org,
                                              CertIncidente.significativo.is_(True),
                                              CertIncidente.estado.notin_(("cerrado", "descartado"))).all():
        avisos = json_de(inc.avisos, {})
        for clave, plazo in plazos(inc, cfg).items():
            if getattr(inc, campos[clave]) is not None:
                continue
            for tipo, cuando in (("proximo", plazo - timedelta(hours=6)), ("vencido", plazo)):
                marca = f"{clave}_{tipo}"
                if momento >= cuando and marca not in avisos:
                    for u in {inc.responsable_id, inc.creado_por} - {None}:
                        avisar(db, u, f"nis2_{tipo}", inc.codigo, inc.id, f"{_URL}?tab=nis2",
                               reloj=clave, plazo=iso(plazo))
                    avisos[marca] = iso(momento)
                    enviados += 1
        inc.avisos = dump(avisos)
    db.commit()
    return {"cert_nis2_avisos": enviados}
