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

    # ── BPM: motor de procesos (`app/services/bpmn_engine.py`) ──────────────
    # Pasos automaticos seguidos sin una espera: mas alla, la instancia falla
    # (un bucle en el diagrama sin tarea humana ni temporizador).
    BPMN_MAX_AUTOMATIC_STEPS: int = Field(default=500, env="BPMN_MAX_AUTOMATIC_STEPS")
