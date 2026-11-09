"""Fuera ajustes y umbrales de alerta que no leía nadie.

Revisión 2026-11.
- Ajustes generales `company_logo_url`, `work_days_per_week`,
  `budget_alert_threshold` y `overload_threshold`: ningún código los leía (los
  dos últimos duplicaban los umbrales de Ajustes → Alertas).
- `alert_configs` con tipos `budget_alert`, `overload_alert` y `deadline_alert`:
  la siembra de demostración usaba nombres que el motor no conoce.
- `deadline_risk` con umbral 0 pasa a 7 días: el motor ya avisaba a 7 días y
  ahora lee el umbral de la tabla.

Revision ID: 150_ajustes_y_alertas_sin_lector
Revises: 149_modulos_de_ia_con_un_nombre
"""
import sqlalchemy as sa
from alembic import op

revision = "150_ajustes_y_alertas_sin_lector"
down_revision = "149_modulos_de_ia_con_un_nombre"
branch_labels = None
depends_on = None


def upgrade() -> None:
    con = op.get_bind()
    tablas = set(sa.inspect(con).get_table_names())
    if "app_settings" in tablas:
        con.execute(sa.text("DELETE FROM app_settings WHERE key IN "
                            "('company_logo_url','work_days_per_week','budget_alert_threshold','overload_threshold')"))
    if "alert_configs" in tablas:
        con.execute(sa.text("DELETE FROM alert_configs WHERE alert_type IN ('budget_alert','overload_alert','deadline_alert')"))
        con.execute(sa.text("UPDATE alert_configs SET threshold_value = 7, "
                            "description = 'Proyecto activo que vence en N días o menos' "
                            "WHERE alert_type = 'deadline_risk' AND (threshold_value IS NULL OR threshold_value = 0)"))


def downgrade() -> None:
    # Eran valores que nadie leía; no hay estado que devolver.
    pass
