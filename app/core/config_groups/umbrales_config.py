"""
Umbrales de semáforo por métrica (19-11-2026).

Una definición por MÉTRICA, no por pantalla: antes cada pantalla y servicio
decidía sus cortes para el mismo número (presupuesto consumido a 70/90, 75/90,
85/100, >80 o >90 según dónde se mirase). Los valores por defecto son los más
usados al medirlo (ver DOCS.md, «Umbrales de semáforo»). Las funciones que los
aplican viven en `app.core.umbrales`; cada valor es un ajuste en vivo por
empresa (Configuración › Configuración dinámica › `semaforos`).

Las métricas que ya tenían ajuste lo conservan (no se duplican): riesgo
(`RISK_LEVEL_*`), salud de proyecto (`PROJECT_HEALTH_TRAFFIC_*`), índices EVM
(`EVM_INDEX_*`) e infrautilización (`RESOURCE_UNDERUSE_PCT`).

NOTE: This is a *mixin* — see `app.core.config_groups` package docstring.
"""
from pydantic import Field


class UmbralesSettingsMixin:
    # Presupuesto consumido (% gastado del presupuesto). Más es peor.
    UMBRAL_PRESUPUESTO_AVISO_PCT: float = Field(default=70.0, description="Budget used — warning above this %.")
    UMBRAL_PRESUPUESTO_CRITICO_PCT: float = Field(default=90.0, description="Budget used — critical above this %.")
    # Carga de una persona (% de su capacidad). Más es peor.
    UMBRAL_CARGA_AVISO_PCT: float = Field(default=85.0, description="Resource load — high above this % of capacity.")
    UMBRAL_CARGA_CRITICO_PCT: float = Field(default=100.0, description="Resource load — overloaded above this % of capacity.")
    UMBRAL_SOBRECARGA_HORAS_SEMANA: float = Field(
        default=42.0, description="Burnout — a week with more hours than this counts as an overloaded week.")
    # Cumplimiento de SLA (% de tickets dentro de plazo). Menos es peor.
    UMBRAL_SLA_AVISO_PCT: float = Field(default=90.0, description="SLA compliance — warning below this %.")
    UMBRAL_SLA_CRITICO_PCT: float = Field(default=75.0, description="SLA compliance — critical below this %.")
    # Progreso de un OKR (%). Menos es peor.
    UMBRAL_OKR_AVISO_PCT: float = Field(default=60.0, description="OKR progress — warning below this %.")
    UMBRAL_OKR_CRITICO_PCT: float = Field(default=30.0, description="OKR progress — critical below this %.")
    # NPS (-100..100). Menos es peor.
    UMBRAL_NPS_AVISO: float = Field(default=50.0, description="NPS — warning below this value (-100..100).")
    UMBRAL_NPS_CRITICO: float = Field(default=0.0, description="NPS — critical below this value (-100..100).")
    # Margen (%). Menos es peor.
    UMBRAL_MARGEN_AVISO_PCT: float = Field(default=50.0, description="Margin — warning below this %.")
    UMBRAL_MARGEN_CRITICO_PCT: float = Field(default=30.0, description="Margin — critical below this %.")
    # Sprint: completitud y ratio de velocidad (% del plan). Menos es peor.
    UMBRAL_SPRINT_COMPLETITUD_AVISO_PCT: float = Field(default=80.0, description="Sprint completion — warning below this %.")
    UMBRAL_SPRINT_COMPLETITUD_CRITICO_PCT: float = Field(default=50.0, description="Sprint completion — critical below this %.")
    UMBRAL_SPRINT_VELOCIDAD_AVISO_PCT: float = Field(default=85.0, description="Sprint velocity ratio — warning below this %.")
    UMBRAL_SPRINT_VELOCIDAD_CRITICO_PCT: float = Field(default=50.0, description="Sprint velocity ratio — critical below this %.")
    # Aprobaciones: riesgo de SLA del paso, tasa de rechazo, pendientes, horas por decisión. Más es peor (≥).
    UMBRAL_APROBACION_RIESGO_SLA_AVISO_PCT: float = Field(default=50.0, description="Approvals — step SLA risk warning from this %.")
    UMBRAL_APROBACION_RIESGO_SLA_CRITICO_PCT: float = Field(default=80.0, description="Approvals — step SLA risk critical from this %.")
    UMBRAL_APROBACION_RECHAZO_AVISO_PCT: float = Field(default=10.0, description="Approvals — rejection rate warning from this %.")
    UMBRAL_APROBACION_RECHAZO_CRITICO_PCT: float = Field(default=25.0, description="Approvals — rejection rate critical from this %.")
    UMBRAL_APROBACION_PENDIENTES_CRITICO: float = Field(default=3.0, description="Approvals — a step with this many pending requests is critical.")
    UMBRAL_APROBACION_DECISION_HORAS: float = Field(default=24.0, description="Approvals — a step deciding in this many hours or more is slow.")
    # Vencimientos (días que faltan: contratos, licencias). Menos es peor.
    UMBRAL_VENCIMIENTO_HORIZONTE_DIAS: int = Field(default=90, description="Expiries — show what expires within these days.")
    UMBRAL_VENCIMIENTO_AVISO_DIAS: int = Field(default=30, description="Expiries — warning when this many days or fewer are left.")
    UMBRAL_VENCIMIENTO_CRITICO_DIAS: int = Field(default=14, description="Expiries — critical when this many days or fewer are left.")
    # Hitos del portal: horizonte de próximos hitos y «inminente».
    UMBRAL_HITOS_HORIZONTE_DIAS: int = Field(default=60, description="Client portal — upcoming milestones within these days.")
    UMBRAL_HITOS_INMINENTE_DIAS: int = Field(default=7, description="Client portal — a milestone fewer than this many days away is imminent.")
