"""
Automatizaciones: cuando y cuanto corren las reglas SI-ENTONCES.

Referenced by:
  - app/services/automation_events (bandeja de eventos y su proceso)
  - app/services/automations_service (barrido periodico y acciones)

NOTE: This is a *mixin* — see `app.core.config_groups` package docstring.
"""
from pydantic import Field


class AutomationsSettingsMixin:
    # Interruptor por organizacion: con False las reglas solo se simulan.
    AUTOMATIONS_ENABLED: bool = Field(default=True, env="AUTOMATIONS_ENABLED")
    # Canal de Slack si la configuracion de la empresa no fija uno (ronda 2
    # auditoria 2026-11-22: antes «#general» y «#contecflow-alerts» fijos).
    SLACK_CANAL_POR_DEFECTO: str = Field(default="#contecflow-alerts", env="SLACK_CANAL_POR_DEFECTO")
    # Entregas de webhooks salientes por webhook y minuto (antes 120 fijo).
    WEBHOOK_OUTBOUND_PER_MIN: int = Field(default=120, env="WEBHOOK_OUTBOUND_PER_MIN")
    # Version de la API REST de Salesforce (antes `v57.0` fijo en la URL).
    SALESFORCE_API_VERSION: str = Field(default="v57.0", env="SALESFORCE_API_VERSION")
    # Una accion de una regla puede disparar otra regla; mas alla de esta
    # profundidad la cadena se corta (evita bucles entre reglas).
    AUTOMATIONS_MAX_CHAIN_DEPTH: int = Field(default=3, env="AUTOMATIONS_MAX_CHAIN_DEPTH")
    AUTOMATIONS_EVENT_BATCH_SIZE: int = Field(default=200, env="AUTOMATIONS_EVENT_BATCH_SIZE")
    AUTOMATIONS_EVENT_MAX_ATTEMPTS: int = Field(default=3, env="AUTOMATIONS_EVENT_MAX_ATTEMPTS")
    # Barrido periodico (tareas vencidas, presupuesto, partes sin enviar).
    # Cada cuantos minutos corre: se lee al arrancar el beat / el scheduler.
    AUTOMATIONS_SCAN_MINUTES: int = Field(default=15, env="AUTOMATIONS_SCAN_MINUTES")
    # «Vence pronto»: dias antes de la fecha limite de una tarea.
    AUTOMATIONS_DEADLINE_DAYS: int = Field(default=2, env="AUTOMATIONS_DEADLINE_DAYS")
    # Dia (ISO, 1=lunes … 7=domingo) desde el que se avisa del parte sin enviar.
    AUTOMATIONS_TIMESHEET_WEEKDAY: int = Field(default=5, env="AUTOMATIONS_TIMESHEET_WEEKDAY")
    AUTOMATIONS_WEBHOOK_TIMEOUT_SECONDS: int = Field(default=10, env="AUTOMATIONS_WEBHOOK_TIMEOUT_SECONDS")
    # Resumen diario de avisos (revisión 2026-11): hora local (0-23) desde la
    # que se manda a quien lo tenga activado, y cuántos avisos lista como mucho.
    NOTIFICATIONS_DIGEST_HOUR: int = Field(default=8, env="NOTIFICATIONS_DIGEST_HOUR")
    NOTIFICATIONS_DIGEST_MAX_ITEMS: int = Field(default=20, env="NOTIFICATIONS_DIGEST_MAX_ITEMS")
    # Avisos a la hora de cada empresa (19-11-2026): hora local (HH:MM, en su
    # DEFAULT_TIMEZONE) del motor de alertas, del recordatorio de la campaña de
    # presupuestos y del de imputaciones (este avisa solo a quien ese día
    # trabaja según su horario efectivo). Se redondea al cuarto de hora. Los valores
    # son los de antes, cuando eran horas fijas del worker.
    NOTIFICATIONS_ALERTS_TIME: str = Field(default="08:00", env="NOTIFICATIONS_ALERTS_TIME")
    NOTIFICATIONS_BUDGET_CAMPAIGN_TIME: str = Field(default="08:30", env="NOTIFICATIONS_BUDGET_CAMPAIGN_TIME")
    NOTIFICATIONS_MISSING_IMPUTATIONS_TIME: str = Field(default="18:00", env="NOTIFICATIONS_MISSING_IMPUTATIONS_TIME")
    # 19-11-2026: también los recordatorios de evaluaciones de desempeño (antes 09:00 fijas).
    NOTIFICATIONS_PERF_REMINDERS_TIME: str = Field(default="09:00", env="NOTIFICATIONS_PERF_REMINDERS_TIME")

    # ── BPM: motor de procesos (`app/services/bpmn_engine.py`) ──────────────
    # Pasos automaticos seguidos sin una espera: mas alla, la instancia falla
    # (un bucle en el diagrama sin tarea humana ni temporizador).
    BPMN_MAX_AUTOMATIC_STEPS: int = Field(default=500, env="BPMN_MAX_AUTOMATIC_STEPS")
    # Revision BPM 2026-11-16: tamano maximo del XML de un diagrama y de las
    # variables (JSON) de una instancia. Sin tope, una sola peticion guardaba
    # megas en una fila y el motor los parseaba en cada paso.
    BPMN_MAX_XML_BYTES: int = Field(default=2_000_000, env="BPMN_MAX_XML_BYTES")
    BPMN_MAX_VARIABLES_BYTES: int = Field(default=65_536, env="BPMN_MAX_VARIABLES_BYTES")
