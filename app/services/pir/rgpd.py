"""RGPD de las PIR: copia (art. 15/20) y supresión (art. 17) de una persona (docs/PIR.md §5).

Datos personales de una PIR: el responsable y los autores (claves ajenas a
`users`, que se quedan apuntando a la ficha ya seudonimizada), la lista JSON de
`participantes` (ids, sin clave ajena) y los nombres libres de interesados en
`satisfaccion`.

- `copia`: las PIR donde la persona es responsable, participante, autora,
  aprobadora o cierra, con su papel; y sus acciones de mejora.
- `suprimir`: quita su id de `participantes` y tacha («[ERASED]») las entradas
  de `satisfaccion` cuyo interesado es su nombre, usuario o correo. El
  responsable se queda: apunta a la ficha seudonimizada, que ya no identifica.
  Las PIR bajo bloqueo legal (tipo `pir_reviews`) no se tocan. Se llama desde
  `supresion_service.suprimir_persona` ANTES de seudonimizar la ficha.
"""
from __future__ import annotations

import json
from typing import Optional

from sqlalchemy import or_
from sqlalchemy.orm import Session

from app.models.pir import PirAccion, PirRevision

BORRADO = "[ERASED]"


def _json(raw, defecto):
    try:
        v = json.loads(raw) if raw else defecto
    except (TypeError, ValueError):
        return defecto
    return v if v is not None else defecto


def _suyas(db: Session, user_id: str, org: Optional[str] = None):
    from app.db.session import sin_filtro_de_tenant
    with sin_filtro_de_tenant(db):
        q = db.query(PirRevision).filter(or_(
            PirRevision.responsable_id == user_id, PirRevision.participantes.like(f'%"{user_id}"%'),
            PirRevision.creado_por == user_id, PirRevision.enviado_por == user_id,
            PirRevision.aprobado_por == user_id, PirRevision.cerrado_por == user_id))
        if org:
            q = q.filter(PirRevision.organization_id == org)
        return q.order_by(PirRevision.created_at).all()


def copia(db: Session, user_id: str, org: Optional[str] = None) -> dict:
    """Las PIR donde participa (con su papel) y sus acciones de mejora."""
    from app.db.session import sin_filtro_de_tenant
    revisiones = []
    for p in _suyas(db, user_id, org):
        papeles = [n for n, v in (("responsable", p.responsable_id), ("autor", p.creado_por),
                                  ("envio", p.enviado_por), ("aprobador", p.aprobado_por),
                                  ("cierre", p.cerrado_por)) if v == user_id]
        if user_id in _json(p.participantes, []):
            papeles.append("participante")
        revisiones.append({"codigo": p.codigo, "titulo": p.titulo, "origen": p.origen_tipo,
                           "estado": p.estado, "resultado": p.resultado, "papeles": papeles,
                           "fecha_prevista": str(p.fecha_prevista) if p.fecha_prevista else None,
                           "fecha_real": str(p.fecha_real) if p.fecha_real else None,
                           "resumen": p.resumen})
    with sin_filtro_de_tenant(db):
        q = db.query(PirAccion).filter(PirAccion.responsable_id == user_id)
        if org:
            q = q.filter(PirAccion.organization_id == org)
        acciones = [{"pir_id": a.pir_id, "descripcion": a.descripcion, "estado": a.estado,
                     "fecha_limite": str(a.fecha_limite) if a.fecha_limite else None} for a in q.all()]
    return {"pir_reviews": revisiones, "pir_actions": acciones}


def suprimir(db: Session, user) -> dict:
    """Quita a la persona de participantes y satisfacción de sus PIR. No hace commit."""
    from app.db.bloqueo_legal import _bloqueo_de, bloqueos_activos
    from app.db.session import sin_filtro_de_tenant
    nombres = {str(v).strip().lower() for v in (user.full_name, user.username, user.email)
               if v and len(str(v).strip()) >= 3}
    informe = {"participantes": 0, "satisfaccion": 0, "held": 0}
    bloqueos: dict = {}
    with sin_filtro_de_tenant(db):
        candidatas = db.query(PirRevision).filter(or_(
            PirRevision.participantes.like(f'%"{user.id}"%'), PirRevision.satisfaccion.isnot(None))).all()
        for p in candidatas:
            org = p.organization_id
            if org not in bloqueos:
                bloqueos[org] = bloqueos_activos(db, org)
            participantes = _json(p.participantes, [])
            satisfaccion = _json(p.satisfaccion, [])
            toca_part = user.id in participantes
            toca_sat = any(isinstance(s, dict) and str(s.get("interesado") or "").strip().lower() in nombres
                           for s in satisfaccion)
            if not (toca_part or toca_sat):
                continue
            if _bloqueo_de("pir_reviews", p, bloqueos[org]) is not None:
                informe["held"] += 1
                continue
            if toca_part:
                p.participantes = json.dumps([u for u in participantes if u != user.id], ensure_ascii=False)
                informe["participantes"] += 1
            if toca_sat:
                for s in satisfaccion:
                    if isinstance(s, dict) and str(s.get("interesado") or "").strip().lower() in nombres:
                        s["interesado"] = BORRADO
                        s["comentario"] = None
                p.satisfaccion = json.dumps(satisfaccion, ensure_ascii=False, default=str)
                informe["satisfaccion"] += 1
    db.flush()
    return informe
