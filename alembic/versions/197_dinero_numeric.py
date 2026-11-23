"""Dinero en Numeric en vez de Float (23-11-2026, auditoría 2026-11-22).

79 columnas de importes, precios y tarifas que seguían en `Float` (IEEE-754:
sumas y redondeos inexactos en facturación, ingresos, proveedores, gastos,
presupuestos, ALM y costes de personas) pasan a los tipos del proyecto
(`app/models/money.py`):

- `Money` = Numeric(18, 2): importes;
- `Rate`  = Numeric(18, 6): tarifas por hora, tipos de cambio, precios
  unitarios y costes por llamada de IA (necesitan más de dos decimales).

Python sigue viendo `float` (`asdecimal=False`, como el resto de columnas
`Money` ya existentes: facturas, gastos, presupuestos...): la mejora es el
almacenamiento y las sumas exactas en la base, sin `TypeError` float*Decimal
ni cambios en las respuestas del API.

Descartadas del plan (no son dinero): `absences.amount` (días u horas),
`alerts.value` (métrica: % o €), `client_health_snapshots.budget_component`
(ratio), `ml_prediction_logs.cost_overrun_prob` (probabilidad),
`okr_checkins.value`, `okr_key_results.target_value/current_value` (métrica
del OKR), `project_risk_scores.budget_risk` (puntuación),
`security_metric_snapshots.auth_failure_rate` (ratio) y
`tabla_de_referencia_filas.valor` (importe O número, según la tabla).

PostgreSQL: `ALTER COLUMN ... TYPE NUMERIC(18,N) USING round(col::numeric, N)`.
SQLite: se redondea con `round()` y se cambia el tipo con
`batch_alter_table` (recrea la tabla). Deshacer: vuelve a `Float`
(`double precision`); el redondeo hecho no se deshace.

Revision ID: 197_dinero_numeric
Revises: 196_auditoria_2026_11_22
"""
import sqlalchemy as sa
from alembic import op

revision = "197_dinero_numeric"
down_revision = "196_auditoria_2026_11_22"
branch_labels = None
depends_on = None

M, R = 2, 6   # decimales de Money y de Rate

#: (tabla, columna, decimales, admite NULL)
COLUMNAS = (
    ("ai_contract_clauses", "impact_amount", M, True),
    ("ai_contracts", "total_value", M, True),
    ("ai_providers", "total_cost_usd", R, True),
    ("ai_usage_logs", "cost_usd", R, True),
    ("alm_assets", "purchase_price", M, True),
    ("alm_assets", "residual_value", M, True),
    ("alm_assets", "lease_monthly_cost", M, True),
    ("alm_assets", "disposal_value", M, True),
    ("alm_contracts", "total_value", M, True),
    ("alm_contracts", "annual_value", M, True),
    ("alm_cost_centers", "budget_annual", M, True),
    ("alm_facturas_proveedor", "amount", M, False),
    ("alm_facturas_proveedor", "tax_amount", M, True),
    ("alm_facturas_proveedor", "expected_amount", M, True),
    ("alm_licenses", "purchase_price", M, True),
    ("alm_licenses", "annual_cost", M, True),
    ("alm_renovaciones", "new_annual_cost", M, True),
    ("alm_software_no_controlado", "importe", M, True),
    ("alm_uso_recuperaciones", "coste_anual", M, True),
    ("budget_commitments", "importe", M, False),
    ("budget_commitments", "importe_facturado", M, True),
    ("budget_lines", "coste_hora", R, True),
    ("budget_lines", "importe", M, False),
    ("budget_lines", "precio_unitario", R, True),
    ("budget_transfers", "importe", M, False),
    ("budgets", "total_amount", M, False),
    ("change_requests", "cost_impact", M, True),
    ("currency_conversion_logs", "original_amount", M, False),
    ("currency_conversion_logs", "converted_amount", M, False),
    ("currency_conversion_logs", "rate_used", R, False),
    ("feature_requests", "estimated_cost", M, True),
    ("gantt_baseline_tasks", "planned_cost", M, True),
    ("gantt_baselines", "budget_at_freeze", M, True),
    ("internal_charge_lines", "unit_amount", R, True),
    ("internal_charge_lines", "amount", M, False),
    ("internal_charges", "total", M, False),
    ("internal_shared_costs", "monthly_amount", M, False),
    ("portfolio_proposals", "estimated_budget", M, True),
    ("portfolios", "budget_total", M, True),
    ("portfolios", "budget_spent", M, True),
    ("projects", "billing_rate", R, True),
    ("projects", "contract_amount", M, True),
    ("projects", "retainer_amount", M, True),
    ("projects", "budget_amount", M, True),
    ("rev_contracts", "contract_value", M, False),
    ("rev_entries", "amount", M, False),
    ("rev_obligations", "allocated_amount", M, False),
    ("revenue_forecasts", "revenue_planned", M, True),
    ("revenue_forecasts", "revenue_actual", M, True),
    ("revenue_forecasts", "revenue_forecast", M, True),
    ("revenue_forecasts", "cost_planned", M, True),
    ("revenue_forecasts", "cost_actual", M, True),
    ("sd_service_items", "internal_price", M, True),
    ("subcontractor_assignments", "po_amount", M, True),
    ("subcontractor_invoices", "amount", M, False),
    ("subcontractor_invoices", "total", M, False),
    ("subcontractor_rates", "cost_rate", R, False),
    ("subcontractor_rates", "sell_rate", R, True),
    ("subcontractor_timelogs", "cost_amount", M, True),
    ("subcontractor_workers", "cost_rate", R, True),
    ("subcontractor_workers", "sell_rate", R, True),
    ("supplier_contracts", "total_cap", M, True),
    ("supplier_contracts", "po_amount", M, True),
    ("supplier_documents", "coverage_amount", M, True),
    ("supplier_pricing_lines", "unit_price", R, True),
    ("supplier_pricing_lines", "overage_price", R, True),
    ("supplier_pricing_lines", "min_amount", M, True),
    ("supplier_pricing_lines", "max_amount", M, True),
    ("supplier_statements", "subtotal", M, False),
    ("supplier_statements", "expected_amount", M, False),
    ("supplier_statements", "invoice_amount", M, True),
    ("supplier_usage_records", "amount", M, True),
    ("supplier_work_packages", "price", M, True),
    ("training_courses", "cost", M, True),
    ("user_cost_profiles", "gross_annual_salary", M, False),
    ("user_cost_profiles", "extra_annual_costs", M, False),
    ("user_cost_profiles", "total_annual_cost", M, False),
    ("user_cost_profiles", "cost_per_hour", R, False),
    ("users", "hourly_rate", R, True),
)


def _por_tabla():
    tablas = {}
    for tabla, columna, escala, nula in COLUMNAS:
        tablas.setdefault(tabla, []).append((columna, escala, nula))
    return sorted(tablas.items())


def _tipos_actuales(insp, tabla):
    return {c["name"]: c["type"] for c in insp.get_columns(tabla)} if insp.has_table(tabla) else {}


def _es_numeric(tipo, escala):
    return isinstance(tipo, sa.Numeric) and not isinstance(tipo, sa.Float) and getattr(tipo, "scale", None) == escala


def upgrade() -> None:
    bind = op.get_bind()
    pg = bind.dialect.name == "postgresql"
    insp = sa.inspect(bind)
    for tabla, cols in _por_tabla():
        actuales = _tipos_actuales(insp, tabla)
        pendientes = [(c, e, n) for c, e, n in cols if c in actuales and not _es_numeric(actuales[c], e)]
        if not pendientes:
            continue
        if pg:
            for c, e, _ in pendientes:
                op.execute(f'ALTER TABLE "{tabla}" ALTER COLUMN "{c}" TYPE NUMERIC(18, {e}) '
                           f'USING round("{c}"::numeric, {e})')
            continue
        for c, e, _ in pendientes:
            op.execute(f'UPDATE "{tabla}" SET "{c}" = round("{c}", {e}) WHERE "{c}" IS NOT NULL')
        with op.batch_alter_table(tabla) as lote:
            for c, e, n in pendientes:
                lote.alter_column(c, type_=sa.Numeric(18, e), existing_type=sa.Float(), existing_nullable=n)


def downgrade() -> None:
    bind = op.get_bind()
    pg = bind.dialect.name == "postgresql"
    insp = sa.inspect(bind)
    for tabla, cols in _por_tabla():
        actuales = _tipos_actuales(insp, tabla)
        pendientes = [(c, e, n) for c, e, n in cols if c in actuales and _es_numeric(actuales[c], e)]
        if not pendientes:
            continue
        if pg:
            for c, _, _ in pendientes:
                op.execute(f'ALTER TABLE "{tabla}" ALTER COLUMN "{c}" TYPE DOUBLE PRECISION '
                           f'USING "{c}"::double precision')
            continue
        with op.batch_alter_table(tabla) as lote:
            for c, e, n in pendientes:
                lote.alter_column(c, type_=sa.Float(), existing_type=sa.Numeric(18, e), existing_nullable=n)
