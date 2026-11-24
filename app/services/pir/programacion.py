"""PIR: programación automática y trabajo de fondo (vencidas y avisos).

Docs: docs/PIR.md §«Programación automática».

- Cambio (`al_cambiar_estado_de_cambio`): al implantarlo (`implemented`) o al
  cerrarlo (`closed_success`/`closed_failed`), según
  `pir_configuracion.momento_cambio`, se crea la PIR con fecha prevista hoy + N
  días (plantilla o configuración). Un cerrado sin PIR previa también la crea,
  aunque el momento sea «implantación» (cierres directos desde `post_review`).
- Proyecto: en la puesta en marcha (`al_completar_hito` de un hito marcado
  `is_go_live`) y/o en el cierre (`al_cerrar_proyecto`, estado `completed` o
  `closed`), según `momento_proyecto`.
- Solo se programan solas las OBLIGATORIAS (por defecto: cambios normales y de
  emergencia; estándar y proyectos según su plantilla o la configuración). Las
  opcionales se programan a mano desde la ficha.
- `revisar_vencidas(db, org)` (beat diario `pir-vencidas`, por organización):
  avisa al responsable N días antes (`aviso_dias_antes`) y una vez al vencer, y
  también al dueño del cambio o al PM del proyecto.

La programación nunca rompe la transición que la dispara: va en un punto de
guardado propio (`begin_nested`) y un fallo queda en el log.
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Optional

from sqlalchemy.orm import Session

from app.models.pir import PirRevision
from app.services.pir.plantillas import config, resolver

logger = logging.getLogger("contecflow.pir")

_IMPLANTADO = "implemented"
_CIERRES = ("closed_success", "closed_failed")


def _valor(x):
    return getattr(x, "value", x)


def _seguro(nombre: str, fn, *args, **kwargs) -> Optional[PirRevision]:
    """Ejecuta `fn` en un punto de guardado: si falla, la transición sigue y queda en el log."""
    db = args[0]
    try:
        with db.begin_nested():
            return fn(*args, **kwargs)
    except Exception:
        logger.exception("PIR: no se pudo programar (%s)", nombre)
        return None


def _obligatoria(db: Session, org, ambito: str, tipo) -> bool:
    return bool(resolver(db, org, ambito, tipo)["obligatorio"])


def al_cambiar_estado_de_cambio(db: Session, change, nuevo: str, usuario=None) -> Optional[PirRevision]:
    """Hook de `change_service._aplicar_estado` (y del despliegue por fases)."""
    nuevo = _valor(nuevo)
    if nuevo not in (_IMPLANTADO,) + _CIERRES:
        return None

    def _programar(db, change, nuevo, usuario):
        from app.services.pir import servicio
        c = config(db, change.organization_id)
        if not _obligatoria(db, change.organization_id, "change", _valor(change.change_type)):
            return None
        hay = db.query(PirRevision.id).filter(PirRevision.change_id == change.id,
                                              PirRevision.estado != "descartado").first() is not None
        if nuevo == _IMPLANTADO and c.momento_cambio != "implantacion":
            return None
        if nuevo in _CIERRES and hay:
            return None
        motivo = "implantacion" if nuevo == _IMPLANTADO else "cierre"
        return servicio.crear(db, None, "change", change.id, motivo=motivo)

    return _seguro(f"cambio {getattr(change, 'number', change.id)}", _programar, db, change, nuevo, usuario)


def al_completar_hito(db: Session, milestone, usuario=None) -> Optional[PirRevision]:
    """Hook de `milestone_service.complete_milestone`: puesta en marcha (go-live) del proyecto."""
    if not getattr(milestone, "is_go_live", False):
        return None

    def _programar(db, milestone, usuario):
        from app.models.project import Project
        from app.services.pir import servicio
        p = db.get(Project, milestone.project_id)
        if p is None:
            return None
        if config(db, p.organization_id).momento_proyecto not in ("go_live", "ambos"):
            return None
        if not _obligatoria(db, p.organization_id, "project", p.project_type):
            return None
        return servicio.crear(db, None, "project", p.id, motivo="go_live", milestone_id=milestone.id)

    return _seguro(f"hito {milestone.id}", _programar, db, milestone, usuario)


def al_cerrar_proyecto(db: Session, project, usuario=None) -> Optional[PirRevision]:
    """Hook de `project_service.update_and_save_project` al pasar a `completed` o `closed`."""
    def _programar(db, project, usuario):
        from app.services.pir import servicio
        if config(db, project.organization_id).momento_proyecto not in ("cierre", "ambos"):
            return None
        if not _obligatoria(db, project.organization_id, "project", project.project_type):
            return None
        return servicio.crear(db, None, "project", project.id, motivo="cierre")

    return _seguro(f"proyecto {getattr(project, 'code', project.id)}", _programar, db, project, usuario)


# ── Trabajo de fondo ─────────────────────────────────────────────────────────

def revisar_vencidas(db: Session, org_id: str) -> dict:
    """Aviso previo y aviso de vencida (una vez cada uno) de las PIR abiertas de la empresa."""
    from app.core import timeutil
    from app.services.pir import servicio
    c = config(db, org_id)
    hoy = timeutil.today()
    ahora = datetime.now(timezone.utc)
    previos = vencidas = 0
    abiertas = db.query(PirRevision).filter(PirRevision.organization_id == org_id,
                                            PirRevision.estado.in_(servicio.ABIERTOS),
                                            PirRevision.fecha_prevista.isnot(None)).all()
    for pir in abiertas:
        if pir.fecha_prevista < hoy and pir.aviso_vencido_en is None:
            destinatarios = {pir.responsable_id} | _gestor_del_origen(db, pir)
            for u in destinatarios:
                servicio._avisar(db, u, "vencida", pir, fecha=pir.fecha_prevista.isoformat())
            pir.aviso_vencido_en = ahora
            vencidas += 1
        elif (pir.fecha_prevista >= hoy and pir.aviso_previo_en is None
              and pir.fecha_prevista - timedelta(days=int(c.aviso_dias_antes or 0)) <= hoy):
            servicio._avisar(db, pir.responsable_id, "proxima", pir, fecha=pir.fecha_prevista.isoformat())
            pir.aviso_previo_en = ahora
            previos += 1
    return {"pir_avisos_previos": previos, "pir_vencidas_avisadas": vencidas,
            "pir_vencidas": sum(1 for p in abiertas if p.fecha_prevista < hoy)}


def _gestor_del_origen(db: Session, pir: PirRevision) -> set:
    from app.services.pir.servicio import _origen
    o = _origen(db, pir)
    if o is None:
        return set()
    return {o.owner_id} - {None} if pir.origen_tipo == "change" else {o.pm_id} - {None}
