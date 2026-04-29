"""045 – ITSM-P08: seed built-in RCA system templates into sd_problem_rca_templates

Seeds the three standard templates that were previously hard-coded in
rca_wizard_service._TEMPLATES so they are now DB-backed and can be read,
extended, or used as canonical references.  Each row has is_system=True
(non-deletable via public API) and a stable UUID so dependent references
are predictable.

Revision ID: 045_rca_templates_seed
Revises: 044_known_error_ticket_links
Create Date: 2026-04-28
"""
from __future__ import annotations

import json

import sqlalchemy as sa
from alembic import op

revision = "045_rca_templates_seed"
down_revision = "044_known_error_ticket_links"
branch_labels = None
depends_on = None

# Stable UUIDs for the three built-in templates
FIVE_WHYS_ID = "00000001-0000-0000-0000-000000000001"
FISHBONE_ID  = "00000001-0000-0000-0000-000000000002"
ITIL_STD_ID  = "00000001-0000-0000-0000-000000000003"

_FIVE_WHYS_STEPS = [
    {"step": 1, "label": "Why #1", "prompt": "¿Por qué ocurrió el problema? Describe el síntoma observable inicial."},
    {"step": 2, "label": "Why #2", "prompt": "¿Por qué ocurrió lo que describiste en el paso anterior? Profundiza un nivel más."},
    {"step": 3, "label": "Why #3", "prompt": "¿Por qué se produjo esa causa? Continúa explorando hacia atrás en la cadena causal."},
    {"step": 4, "label": "Why #4", "prompt": "¿Por qué existía esa condición? Busca el factor sistémico o de proceso subyacente."},
    {"step": 5, "label": "Why #5 — Causa Raíz", "prompt": "¿Por qué existía ese factor? Esta respuesta debería apuntar directamente a la causa raíz. Resume la causa raíz final aquí."},
]

_FISHBONE_STEPS = [
    {"step": 1, "label": "Personas", "prompt": "¿Qué factores humanos o de equipo pudieron contribuir al problema? (falta de formación, errores humanos, comunicación deficiente, etc.)"},
    {"step": 2, "label": "Proceso", "prompt": "¿Qué fallos en procesos o procedimientos contribuyeron? (procedimientos ausentes, obsoletos, no seguidos, etc.)"},
    {"step": 3, "label": "Tecnología", "prompt": "¿Qué factores tecnológicos o de infraestructura influyeron? (bugs de software, fallos de hardware, configuración incorrecta, etc.)"},
    {"step": 4, "label": "Entorno", "prompt": "¿Qué factores del entorno o externos afectaron? (condiciones de red, proveedores externos, cambios de carga, etc.)"},
    {"step": 5, "label": "Materiales / Datos", "prompt": "¿Problemas con datos, configuraciones, dependencias o insumos del sistema? (datos corruptos, configuraciones incorrectas, librerías desactualizadas, etc.)"},
    {"step": 6, "label": "Métricas / Monitorización", "prompt": "¿Existían alertas, umbrales o métricas que fallaron en detectar o prevenir el problema? (falta de alertas, umbrales mal calibrados, ausencia de observabilidad, etc.)"},
]

_ITIL_STEPS = [
    {"step": 1, "label": "Cronología", "prompt": "Describe la cronología del incidente: ¿cuándo comenzó, qué eventos sucedieron, cuándo fue detectado y resuelto? Incluye timestamps aproximados."},
    {"step": 2, "label": "Factores Contribuyentes", "prompt": "Lista todos los factores que contribuyeron al problema. Considera: cambios recientes, carga inusual, deuda técnica, dependencias externas y cualquier condición preexistente."},
    {"step": 3, "label": "Enunciado de Causa Raíz", "prompt": "Formula un enunciado claro y conciso de la causa raíz. Debe responder a: ¿qué falló exactamente y por qué ocurrió? Evita síntomas — apunta al origen."},
    {"step": 4, "label": "Acciones de Prevención", "prompt": "¿Qué acciones concretas evitarán la recurrencia? Incluye: cambios de configuración, mejoras de proceso, actualizaciones de monitorización y responsables."},
]

_SEED_ROWS = [
    {
        "id": FIVE_WHYS_ID,
        "name": "5 Whys (Toyota)",
        "template_type": "five_whys",
        "steps_json": json.dumps(_FIVE_WHYS_STEPS, ensure_ascii=False),
        "description": "Técnica iterativa de 5 preguntas '¿Por qué?' para llegar a la causa raíz. Ideal para problemas simples con cadena causal lineal.",
        "is_system": True,
        "is_active": True,
        "created_by": None,
    },
    {
        "id": FISHBONE_ID,
        "name": "Diagrama de Ishikawa (Fishbone)",
        "template_type": "fishbone",
        "steps_json": json.dumps(_FISHBONE_STEPS, ensure_ascii=False),
        "description": "Analiza 6 categorías de causas: Personas, Proceso, Tecnología, Entorno, Materiales/Datos, Métricas. Ideal para problemas multifactoriales.",
        "is_system": True,
        "is_active": True,
        "created_by": None,
    },
    {
        "id": ITIL_STD_ID,
        "name": "Análisis ITIL Estándar",
        "template_type": "itil_standard",
        "steps_json": json.dumps(_ITIL_STEPS, ensure_ascii=False),
        "description": "Proceso ITIL de 4 pasos: Cronología → Factores contribuyentes → Enunciado de causa raíz → Acciones de prevención.",
        "is_system": True,
        "is_active": True,
        "created_by": None,
    },
]


def upgrade() -> None:
    bind = op.get_bind()

    for row in _SEED_ROWS:
        # Idempotent: skip if already present
        result = bind.execute(
            sa.text("SELECT id FROM sd_problem_rca_templates WHERE id = :id"),
            {"id": row["id"]},
        ).fetchone()
        if result:
            continue

        bind.execute(
            sa.text(
                """
                INSERT INTO sd_problem_rca_templates
                    (id, name, template_type, steps_json, description, is_system, is_active, created_by, created_at)
                VALUES
                    (:id, :name, :template_type, :steps_json, :description, :is_system, :is_active, :created_by, CURRENT_TIMESTAMP)
                """
            ),
            row,
        )


def downgrade() -> None:
    bind = op.get_bind()
    for row in _SEED_ROWS:
        bind.execute(
            sa.text("DELETE FROM sd_problem_rca_templates WHERE id = :id AND is_system = true"),
            {"id": row["id"]},
        )
