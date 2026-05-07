"""
Metrics service: Declarative metric registry and handler system.

Each metric is defined as an independent function with standardized signature:
    def metric_handler(db: Session, d_from: date, d_to: date, top_n: int,
                      project_id: Optional[str], user_id: Optional[str],
                      project_ids: Optional[list[str]], **kwargs) -> tuple[list[dict], dict]

Returns:
    (rows: list[dict], meta_patch: dict)
    - rows: List of data points with {"label", "value", ...}
    - meta_patch: Optional metadata overrides (e.g., chart type)

METRICS_REGISTRY maps metric_id -> handler function.
METRICS_OWNERSHIP maps metric_id -> owner module (string) for documentation.
Use get_metrics_owner(metric_name) to look up ownership at runtime.
"""
# ruff: noqa: F401

from typing import Callable

# Type for metric handler function
MetricHandler = Callable[..., tuple[list[dict], dict]]

# Central registry: metric_id -> handler function
# Populated via @register_metric decorator at import time.
METRICS_REGISTRY: dict[str, MetricHandler] = {}


def register_metric(metric_id: str):
    """Decorator to register a metric handler."""
    def decorator(func: MetricHandler) -> MetricHandler:
        METRICS_REGISTRY[metric_id] = func
        return func
    return decorator


def register_metrics_from_module(module):
    """Auto-register all @register_metric decorated functions in a module."""
    for name in dir(module):
        attr = getattr(module, name)
        if callable(attr) and hasattr(attr, "_metric_id"):
            metric_id = attr._metric_id
            METRICS_REGISTRY[metric_id] = attr


# ──────────────────────────────────────────────────────────────────────────────
# Import metric modules to trigger registration (auto-register via @register_metric)
# ──────────────────────────────────────────────────────────────────────────────

from . import hours
from . import costs
from . import projects
from . import capacity
from . import service_desk
from . import rrhh
from . import business
from . import alm
from . import remaining
from . import advanced
from . import okr_nps
from . import training_git
from . import revenue_expenses
from . import sprints_tasks
from . import portfolio_performance
from . import invoices_alerts
from . import automations_cmdb
from . import user_costs


# ──────────────────────────────────────────────────────────────────────────────
# METRICS_OWNERSHIP — documents which module owns each metric.
# Use get_metrics_owner(metric_name) for programmatic lookup.
# ──────────────────────────────────────────────────────────────────────────────

METRICS_OWNERSHIP: dict[str, str] = {
    # === HOURS ===
    "hours_by_project":            "metrics.hours",
    "hours_by_week":               "metrics.hours",
    "hours_by_month":              "metrics.hours",
    "hours_by_department":         "metrics.hours",
    "hours_billable_vs_internal":  "metrics.hours",
    "hours_by_person":             "metrics.hours",
    "hours_heatmap":               "metrics.hours",

    # === COSTS ===
    "cost_by_project":             "metrics.costs",
    "cost_by_person":              "metrics.costs",
    "cost_by_month":               "metrics.costs",
    "budget_consumption":          "metrics.costs",
    "cost_vs_budget":              "metrics.costs",
    "margin_by_project":           "metrics.costs",
    "margin_evolution":            "metrics.costs",
    "revenue_by_client":           "metrics.costs",

    # === PROJECTS & TASKS (projects.py) ===
    "tasks_by_status":             "metrics.projects",
    "tasks_by_project":            "metrics.projects",
    "projects_by_status":          "metrics.projects",
    "projects_by_type":            "metrics.projects",
    "deliverables_status":         "metrics.projects",
    "tasks_lead_time":             "metrics.projects",
    "tasks_blocked_by_project":    "metrics.projects",
    "tasks_overdue":               "metrics.projects",
    "risks_by_level":              "metrics.projects",

    # === CAPACITY ===
    "load_by_week":                "metrics.capacity",
    "productivity_by_person":      "metrics.capacity",

    # === SERVICE DESK ===
    "tickets_by_status":           "metrics.service_desk",
    "tickets_by_type":             "metrics.service_desk",
    "tickets_by_priority":         "metrics.service_desk",
    "tickets_by_agent":            "metrics.service_desk",
    "ticket_resolution_time":      "metrics.service_desk",
    "ticket_sla_compliance":       "metrics.service_desk",
    "ticket_volume_trend":         "metrics.service_desk",
    "ticket_csat":                 "metrics.service_desk",

    # === RRHH ===
    "absences_by_type":            "metrics.rrhh",
    "absences_by_person":          "metrics.rrhh",
    "absences_by_month":           "metrics.rrhh",

    # === BUSINESS / PIPELINE ===
    "pipeline_by_stage":           "metrics.business",
    "pipeline_evolution":          "metrics.business",
    "contracts_by_status":         "metrics.business",
    "win_rate_evolution":          "metrics.business",
    "change_requests_status":      "metrics.business",

    # === ALM ===
    "license_cost_by_vendor":      "metrics.alm",
    "license_utilization":         "metrics.alm",
    "license_expiry_timeline":     "metrics.alm",
    "assets_by_type":              "metrics.alm",

    # === REMAINING (sprints, semantic, load profiles) ===
    "sprint_velocity":             "metrics.remaining",
    "sprint_completion_rate":      "metrics.remaining",
    "semantic_accuracy_trend":     "metrics.remaining",
    "semantic_assignments_by_mode": "metrics.remaining",
    "load_by_person":              "metrics.remaining",

    # === ADVANCED ===
    "forecast_revenue":            "metrics.advanced",
    "burnout_index":               "metrics.advanced",

    # === OKR & NPS ===
    "okr_progress_by_objective":   "metrics.okr_nps",
    "okr_kr_completion_rate":      "metrics.okr_nps",
    "nps_by_client":               "metrics.okr_nps",
    "nps_trend":                   "metrics.okr_nps",
    "nps_distribution":            "metrics.okr_nps",
    "client_health_score":         "metrics.okr_nps",

    # === TRAINING & GIT ===
    "training_completion_rate":    "metrics.training_git",
    "certifications_by_user":      "metrics.training_git",
    "prs_by_author":               "metrics.training_git",
    "prs_by_project":              "metrics.training_git",
    "pr_cycle_time":               "metrics.training_git",
    "deployments_by_env":          "metrics.training_git",
    "deployment_success_rate":     "metrics.training_git",

    # === REVENUE & EXPENSES ===
    "revenue_recognized_by_month": "metrics.revenue_expenses",
    "revenue_by_contract":         "metrics.revenue_expenses",
    "expenses_by_category":        "metrics.revenue_expenses",
    "expenses_by_project":         "metrics.revenue_expenses",
    "expenses_billable_vs_internal": "metrics.revenue_expenses",
    "expenses_trend":              "metrics.revenue_expenses",
    "expenses_pending_approval":   "metrics.revenue_expenses",

    # === SPRINTS & TASKS (sprints_tasks.py — higher-fidelity sprint metrics) ===
    "sprint_velocity_trend":       "metrics.sprints_tasks",
    # sprint_completion_rate also appears in sprints_tasks; last writer wins in
    # the REGISTRY but ownership doc points to the newer module.
    "tasks_by_priority":           "metrics.sprints_tasks",
    "tasks_overdue_by_assignee":   "metrics.sprints_tasks",
    "task_completion_trend":       "metrics.sprints_tasks",
    "tasks_by_assignee":           "metrics.sprints_tasks",
    "epics_by_status":             "metrics.sprints_tasks",
    "milestones_on_time_rate":     "metrics.sprints_tasks",

    # === PORTFOLIO & PERFORMANCE ===
    "portfolio_budget_usage":            "metrics.portfolio_performance",
    "performance_scores_by_person":      "metrics.portfolio_performance",
    "performance_cycle_completion_rate": "metrics.portfolio_performance",
    "timesheets_approval_rate":          "metrics.portfolio_performance",
    "timesheets_billable_hours_trend":   "metrics.portfolio_performance",
    # absences_by_type / absences_by_person also in portfolio_performance
    # (duplicate registration; sprints_tasks wins in REGISTRY for these).

    # === INVOICES, ALERTS & SLA ===
    "invoices_by_status":          "metrics.invoices_alerts",
    "invoice_amount_by_month":     "metrics.invoices_alerts",
    "invoice_amount_by_client":    "metrics.invoices_alerts",
    "invoice_overdue_amount":      "metrics.invoices_alerts",
    "alerts_by_severity":          "metrics.invoices_alerts",
    "alerts_by_type":              "metrics.invoices_alerts",
    "unresolved_alerts_by_project": "metrics.invoices_alerts",
    "sla_breach_trend":            "metrics.invoices_alerts",
    "sla_breach_by_type":          "metrics.invoices_alerts",

    # === AUTOMATIONS & CMDB ===
    "automation_success_rate":     "metrics.automations_cmdb",
    "automation_run_stats":        "metrics.automations_cmdb",
    "cmdb_items_by_status":        "metrics.automations_cmdb",
    "cmdb_items_by_environment":   "metrics.automations_cmdb",
    "cmdb_items_by_type":          "metrics.automations_cmdb",
    "clients_by_industry":         "metrics.automations_cmdb",
    "opportunity_by_owner":        "metrics.automations_cmdb",

    # === USER COSTS ===
    "cost_per_hour_by_person":     "metrics.user_costs",
    "cost_per_hour_by_department": "metrics.user_costs",
    "cost_per_hour_by_country":    "metrics.user_costs",
    "annual_cost_by_person":       "metrics.user_costs",
    "annual_cost_by_country":      "metrics.user_costs",
    "cost_profile_coverage":       "metrics.user_costs",
    "employer_cost_pct_by_country": "metrics.user_costs",
    "cost_per_hour_drift":         "metrics.user_costs",
}


def get_metrics_owner(metric_name: str) -> str:
    """
    Return the owner module string for a given metric_id.

    Example:
        get_metrics_owner("hours_by_project")  # -> "metrics.hours"

    Returns "metrics.unknown" if the metric is not in METRICS_OWNERSHIP.
    """
    return METRICS_OWNERSHIP.get(metric_name, "metrics.unknown")


# ──────────────────────────────────────────────────────────────────────────────
# __all__ — exhaustive list of all public names exported by this package.
# Any `from app.services.metrics import X` must find X here.
# ──────────────────────────────────────────────────────────────────────────────

__all__ = [
    # Registry infrastructure
    "METRICS_REGISTRY",
    "METRICS_OWNERSHIP",
    "register_metric",
    "register_metrics_from_module",
    "get_metrics_owner",

    # === HOURS ===
    "metric_hours_by_project",
    "metric_hours_by_week",
    "metric_hours_by_month",
    "metric_hours_by_department",
    "metric_hours_billable_vs_internal",
    "metric_hours_by_person",
    "metric_hours_heatmap",

    # === COSTS ===
    "metric_cost_by_project",
    "metric_cost_by_person",
    "metric_cost_by_month",
    "metric_budget_consumption",
    "metric_cost_vs_budget",
    "metric_margin_by_project",
    "metric_margin_evolution",
    "metric_revenue_by_client",

    # === PROJECTS & TASKS (projects.py) ===
    "metric_tasks_by_status",
    "metric_tasks_by_project",
    "metric_projects_by_status",
    "metric_projects_by_type",
    "metric_deliverables_status",
    "metric_tasks_lead_time",
    "metric_tasks_blocked_by_project",
    "metric_tasks_overdue",
    "metric_risks_by_level",

    # === CAPACITY ===
    "metric_load_by_week",
    "metric_productivity_by_person",

    # === SERVICE DESK ===
    "metric_tickets_by_status",
    "metric_tickets_by_type",
    "metric_tickets_by_priority",
    "metric_tickets_by_agent",
    "metric_ticket_resolution_time",
    "metric_ticket_sla_compliance",
    "metric_ticket_volume_trend",
    "metric_ticket_csat",

    # === RRHH ===
    "metric_absences_by_type",
    "metric_absences_by_person",
    "metric_absences_by_month",

    # === BUSINESS ===
    "metric_pipeline_by_stage",
    "metric_pipeline_evolution",
    "metric_contracts_by_status",
    "metric_win_rate_evolution",
    "metric_change_requests_status",

    # === ALM ===
    "metric_license_cost_by_vendor",
    "metric_license_utilization",
    "metric_license_expiry_timeline",
    "metric_assets_by_type",

    # === REMAINING ===
    "metric_sprint_velocity",
    "metric_sprint_completion_rate",
    "metric_semantic_accuracy_trend",
    "metric_semantic_assignments_by_mode",
    "metric_load_by_person",

    # === ADVANCED ===
    "metric_forecast_revenue",
    "metric_burnout_index",

    # === OKR & NPS ===
    "metric_okr_progress_by_objective",
    "metric_okr_kr_completion_rate",
    "metric_nps_by_client",
    "metric_nps_trend",
    "metric_nps_distribution",
    "metric_client_health_score",

    # === TRAINING & GIT ===
    "metric_training_completion_rate",
    "metric_certifications_by_user",
    "metric_prs_by_author",
    "metric_prs_by_project",
    "metric_pr_cycle_time",
    "metric_deployments_by_env",
    "metric_deployment_success_rate",

    # === REVENUE & EXPENSES ===
    "metric_revenue_recognized_by_month",
    "metric_revenue_by_contract",
    "metric_expenses_by_category",
    "metric_expenses_by_project",
    "metric_expenses_billable_vs_internal",
    "metric_expenses_trend",
    "metric_expenses_pending_approval",

    # === SPRINTS & TASKS (sprints_tasks.py) ===
    "metric_sprint_velocity_trend",
    "metric_tasks_by_priority",
    "metric_tasks_overdue_by_assignee",
    "metric_task_completion_trend",
    "metric_tasks_by_assignee",
    "metric_epics_by_status",
    "metric_milestones_on_time_rate",

    # === PORTFOLIO & PERFORMANCE ===
    "metric_portfolio_budget_usage",
    "metric_performance_scores_by_person",
    "metric_performance_cycle_completion_rate",
    "metric_timesheets_approval_rate",
    "metric_timesheets_billable_hours_trend",

    # === INVOICES, ALERTS & SLA ===
    "metric_invoices_by_status",
    "metric_invoice_amount_by_month",
    "metric_invoice_amount_by_client",
    "metric_invoice_overdue_amount",
    "metric_alerts_by_severity",
    "metric_alerts_by_type",
    "metric_unresolved_alerts_by_project",
    "metric_sla_breach_trend",
    "metric_sla_breach_by_type",

    # === AUTOMATIONS & CMDB ===
    "metric_automation_success_rate",
    "metric_automation_run_stats",
    "metric_cmdb_items_by_status",
    "metric_cmdb_items_by_environment",
    "metric_cmdb_items_by_type",
    "metric_clients_by_industry",
    "metric_opportunity_by_owner",

    # === USER COSTS ===
    "metric_cost_per_hour_by_person",
    "metric_cost_per_hour_by_department",
    "metric_cost_per_hour_by_country",
    "metric_annual_cost_by_person",
    "metric_annual_cost_by_country",
    "metric_cost_profile_coverage",
    "metric_employer_cost_pct_by_country",
    "metric_cost_per_hour_drift",
]

# ──────────────────────────────────────────────────────────────────────────────
# Re-export all metric handler functions into this namespace so that
# `from app.services.metrics import metric_hours_by_project` works.
# ──────────────────────────────────────────────────────────────────────────────

# === HOURS ===
from .hours import (
    metric_hours_by_project,
    metric_hours_by_week,
    metric_hours_by_month,
    metric_hours_by_department,
    metric_hours_billable_vs_internal,
    metric_hours_by_person,
    metric_hours_heatmap,
)

# === COSTS ===
from .costs import (
    metric_cost_by_project,
    metric_cost_by_person,
    metric_cost_by_month,
    metric_budget_consumption,
    metric_cost_vs_budget,
    metric_margin_by_project,
    metric_margin_evolution,
    metric_revenue_by_client,
)

# === PROJECTS & TASKS ===
from .projects import (
    metric_tasks_by_status,
    metric_tasks_by_project,
    metric_projects_by_status,
    metric_projects_by_type,
    metric_deliverables_status,
    metric_tasks_lead_time,
    metric_tasks_blocked_by_project,
    metric_tasks_overdue,
    metric_risks_by_level,
)

# === CAPACITY ===
from .capacity import (
    metric_load_by_week,
    metric_productivity_by_person,
)

# === SERVICE DESK ===
from .service_desk import (
    metric_tickets_by_status,
    metric_tickets_by_type,
    metric_tickets_by_priority,
    metric_tickets_by_agent,
    metric_ticket_resolution_time,
    metric_ticket_sla_compliance,
    metric_ticket_volume_trend,
    metric_ticket_csat,
)

# === RRHH ===
from .rrhh import (
    metric_absences_by_type,
    metric_absences_by_person,
    metric_absences_by_month,
)

# === BUSINESS ===
from .business import (
    metric_pipeline_by_stage,
    metric_pipeline_evolution,
    metric_contracts_by_status,
    metric_win_rate_evolution,
    metric_change_requests_status,
)

# === ALM ===
from .alm import (
    metric_license_cost_by_vendor,
    metric_license_utilization,
    metric_license_expiry_timeline,
    metric_assets_by_type,
)

# === REMAINING ===
from .remaining import (
    metric_sprint_velocity,
    metric_sprint_completion_rate,
    metric_semantic_accuracy_trend,
    metric_semantic_assignments_by_mode,
    metric_load_by_person,
)

# === ADVANCED ===
from .advanced import (
    metric_forecast_revenue,
    metric_burnout_index,
)

# === OKR & NPS ===
from .okr_nps import (
    metric_okr_progress_by_objective,
    metric_okr_kr_completion_rate,
    metric_nps_by_client,
    metric_nps_trend,
    metric_nps_distribution,
    metric_client_health_score,
)

# === TRAINING & GIT ===
from .training_git import (
    metric_training_completion_rate,
    metric_certifications_by_user,
    metric_prs_by_author,
    metric_prs_by_project,
    metric_pr_cycle_time,
    metric_deployments_by_env,
    metric_deployment_success_rate,
)

# === REVENUE & EXPENSES ===
from .revenue_expenses import (
    metric_revenue_recognized_by_month,
    metric_revenue_by_contract,
    metric_expenses_by_category,
    metric_expenses_by_project,
    metric_expenses_billable_vs_internal,
    metric_expenses_trend,
    metric_expenses_pending_approval,
)

# === SPRINTS & TASKS (sprints_tasks.py) ===
from .sprints_tasks import (
    metric_sprint_velocity_trend,
    metric_sprint_completion_rate as metric_sprint_completion_rate_v2,  # noqa: F811
    metric_tasks_by_status as metric_tasks_by_status_v2,  # noqa: F811
    metric_tasks_by_priority,
    metric_tasks_overdue_by_assignee,
    metric_task_completion_trend,
    metric_tasks_by_assignee,
    metric_epics_by_status,
    metric_milestones_on_time_rate,
)

# === PORTFOLIO & PERFORMANCE ===
from .portfolio_performance import (
    metric_portfolio_budget_usage,
    metric_performance_scores_by_person,
    metric_performance_cycle_completion_rate,
    metric_timesheets_approval_rate,
    metric_timesheets_billable_hours_trend,
)

# === INVOICES, ALERTS & SLA ===
from .invoices_alerts import (
    metric_invoices_by_status,
    metric_invoice_amount_by_month,
    metric_invoice_amount_by_client,
    metric_invoice_overdue_amount,
    metric_alerts_by_severity,
    metric_alerts_by_type,
    metric_unresolved_alerts_by_project,
    metric_sla_breach_trend,
    metric_sla_breach_by_type,
)

# === AUTOMATIONS & CMDB ===
from .automations_cmdb import (
    metric_automation_success_rate,
    metric_automation_run_stats,
    metric_cmdb_items_by_status,
    metric_cmdb_items_by_environment,
    metric_cmdb_items_by_type,
    metric_clients_by_industry,
    metric_opportunity_by_owner,
)

# === USER COSTS ===
from .user_costs import (
    metric_cost_per_hour_by_person,
    metric_cost_per_hour_by_department,
    metric_cost_per_hour_by_country,
    metric_annual_cost_by_person,
    metric_annual_cost_by_country,
    metric_cost_profile_coverage,
    metric_employer_cost_pct_by_country,
    metric_cost_per_hour_drift,
)
