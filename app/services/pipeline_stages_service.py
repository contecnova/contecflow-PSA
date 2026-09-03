"""Configuracion de etapas del embudo comercial.

Auditoria 2026-08 (hallazgo 22). Este codigo vivia en `v238_service.py`, un
fichero de 784 lineas nombrado por NUMERO DE VERSION y con SEIS dominios sin
relacion dentro: etapas del embudo, planificacion de capacidad, analitica
ad-hoc, pagos, instantaneas de colaboracion y SCIM.

Agrupar por version en lugar de por dominio tiene un coste concreto: nadie sabe
donde buscar, y un fichero con seis dominios no tiene revisor natural — quien
entra a tocar los pagos no revisa la analitica que hay 300 lineas mas abajo. Fue
esa misma mala ubicacion la que oculto el P0 numero 1 de la auditoria, escondido
en un fichero llamado `mfa_service`.

El reparto se pudo hacer mecanicamente porque los seis dominios nunca estuvieron
acoplados, solo apilados: se comprobo por AST que no habia ni una llamada entre
grupos ni un solo ciclo. Los cuerpos se movieron verbatim.
"""

from typing import Optional
from sqlalchemy.orm import Session
from fastapi import HTTPException
from app.models.pipeline import PipelineStageConfig

_DEFAULT_STAGE_CONFIGS = [
    {"stage_key": "lead", "label": "Lead", "color": "#6B7280", "order": 0, "probability_default": 10, "is_terminal": False, "is_won": False},
    {"stage_key": "qualification", "label": "Calificación", "color": "#3B82F6", "order": 1, "probability_default": 25, "is_terminal": False, "is_won": False},
    {"stage_key": "proposal", "label": "Propuesta", "color": "#8B5CF6", "order": 2, "probability_default": 50, "is_terminal": False, "is_won": False},
    {"stage_key": "negotiation", "label": "Negociación", "color": "#F59E0B", "order": 3, "probability_default": 75, "is_terminal": False, "is_won": False},
    {"stage_key": "won", "label": "Ganada", "color": "#10B981", "order": 4, "probability_default": 100, "is_terminal": True, "is_won": True},
    {"stage_key": "lost", "label": "Perdida", "color": "#EF4444", "order": 5, "probability_default": 0, "is_terminal": True, "is_won": False},
]


def get_stage_configs(db: Session) -> dict:
    configs = db.query(PipelineStageConfig).filter(
        PipelineStageConfig.is_active == True
    ).order_by(PipelineStageConfig.order).all()
    if not configs:
        return {"configs": _DEFAULT_STAGE_CONFIGS, "source": "defaults"}
    return {
        "configs": [
            {
                "id": c.id, "stage_key": c.stage_key, "label": c.label,
                "description": c.description, "color": c.color, "order": c.order,
                "probability_default": c.probability_default,
                "is_terminal": c.is_terminal, "is_won": c.is_won,
            }
            for c in configs
        ],
        "source": "custom",
    }


def create_stage_config_record(
    stage_key: str,
    label: str,
    description: Optional[str],
    color: Optional[str],
    order: Optional[int],
    probability_default: Optional[float],
    is_terminal: Optional[bool],
    is_won: Optional[bool],
    db: Session,
) -> dict:
    existing = db.query(PipelineStageConfig).filter(
        PipelineStageConfig.stage_key == stage_key
    ).first()
    if existing:
        raise HTTPException(status_code=409, detail=f"Stage key '{stage_key}' already exists")
    config = PipelineStageConfig(
        stage_key=stage_key,
        label=label,
        description=description,
        color=color or "#6B7280",
        order=order or 0,
        probability_default=probability_default or 50,
        is_terminal=is_terminal or False,
        is_won=is_won or False,
    )
    db.add(config)
    db.commit()
    db.refresh(config)
    return {"id": config.id, "stage_key": config.stage_key, "label": config.label, "created": True}


def delete_stage_config_record(stage_key: str, db: Session) -> None:
    config = db.query(PipelineStageConfig).filter(PipelineStageConfig.stage_key == stage_key).first()
    if not config:
        raise HTTPException(status_code=404, detail="Stage config not found")
    config.is_active = False
    db.commit()
