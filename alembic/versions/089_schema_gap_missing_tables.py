"""Cierra el hueco de esquema: 19 tablas que ninguna revisión creaba.

Auditoría 2026-08 (hallazgo 11). El esquema se construía por dos caminos
distintos y sólo uno estaba completo:

  · BD nueva      → `Base.metadata.create_all()` + `alembic stamp head`
  · BD existente  → `alembic upgrade head`

`stamp head` marca las 88 revisiones como aplicadas SIN EJECUTARLAS, así que la
cadena de Alembic nunca se ejercitó de principio a fin. Al probarla sobre una
base vacía resultó que produce 374 tablas mientras los modelos definen 392:
faltan estas 19, que existían únicamente porque `create_all` las creaba.

Consecuencia real: un despliegue que hubiese pasado por la vía de Alembic se
queda sin ellas y la aplicación falla en gastos, plantillas de correo,
automatizaciones, reconocimiento de ingresos, GDPR, webhooks y CAB. Nadie lo
detectó porque en la práctica siempre se usaba `create_all`.

── Por qué esta revisión usa `Base.metadata` en lugar de `op.create_table` ────
Transcribir a mano 19 definiciones de tabla (con sus columnas, tipos, índices y
claves ajenas) es duplicar información que ya está en los modelos, y esa copia
se desincroniza en el primer cambio. Aquí los modelos SON la fuente de verdad y
se crean exactamente las 19 tablas nombradas.

La lista de nombres es explícita y fija a propósito: una migración debe hacer
siempre lo mismo, así que no se deriva de "lo que falte hoy" — si mañana se añade
un modelo nuevo, le corresponde su propia revisión, no que ésta cambie de
comportamiento retroactivamente.

`checkfirst=True` la hace idempotente: en una base que venga de `create_all`
estas tablas ya existen y la revisión no toca nada, así que se puede aplicar sin
riesgo sobre instalaciones actuales.
"""
from typing import Union

from alembic import op

revision: str = "089_schema_gap_missing_tables"
down_revision: Union[str, None] = "088_portal_translations"
branch_labels = None
depends_on = None


# Las 19 tablas que la cadena de revisiones no creaba, medidas comparando
# `alembic upgrade head` sobre una base vacía contra `Base.metadata`.
MISSING_TABLES = (
    "automation_executions",
    "automation_rules",
    "cab_votes",
    "calendar_events",
    "change_request_windows",
    "commit_links",
    "dashboard_widgets",
    "email_logs",
    "email_templates",
    "expenses",
    "gdpr_requests",
    "integration_configs",
    "maintenance_windows",
    "onboarding_states",
    "project_risk_scores",
    "revenue_recognition_entries",
    "revenue_recognition_rules",
    "webhook_trigger_logs",
    "webhook_triggers",
)


def _tables_to_handle():
    """Objetos Table de los modelos para los nombres de MISSING_TABLES.

    Importa `app.models` para que todos los modelos queden registrados en
    `Base.metadata`; sin ese import el metadata está vacío y no se crearía nada.
    """
    from app.db.base import Base
    import app.models  # noqa: F401 — import con efecto: registra los modelos

    # Auditoria 2026-11: las dos tablas de `revenue_recognition_*` se retiraron
    # del dominio (revision 156, un solo motor de ingresos, que ya contempla que
    # no existan). Esta revision no puede depender de modelos que ya no estan:
    # se crean las que siguen siendo modelo y se omiten las retiradas.
    return [Base.metadata.tables[n] for n in MISSING_TABLES if n in Base.metadata.tables]


def upgrade() -> None:
    from app.db.base import Base

    bind = op.get_bind()
    # checkfirst=True → idempotente sobre instalaciones que vengan de create_all.
    Base.metadata.create_all(bind=bind, tables=_tables_to_handle(), checkfirst=True)


def downgrade() -> None:
    from app.db.base import Base

    bind = op.get_bind()
    # Se descartan en orden inverso para respetar las dependencias de claves
    # ajenas entre ellas (p. ej. automation_executions → automation_rules).
    Base.metadata.drop_all(bind=bind, tables=list(reversed(_tables_to_handle())), checkfirst=True)
