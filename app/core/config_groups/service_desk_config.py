"""
Service Desk: avisos del ciclo de vida del ticket y su bandeja de salida.

Referenced by:
  - app/services/service_desk/ticket_event_processor (quien recibe que)
  - app/services/service_desk/inbound_mail (buzon de entrada)

NOTE: This is a *mixin* — see `app.core.config_groups` package docstring.
"""
from pydantic import Field


class ServiceDeskSettingsMixin:
    # ── A quien se avisa ─────────────────────────────────────────────────────
    SD_NOTIFY_REQUESTER_ON_CREATE: bool = Field(default=True, env="SD_NOTIFY_REQUESTER_ON_CREATE")
    SD_NOTIFY_REQUESTER_ON_REPLY: bool = Field(default=True, env="SD_NOTIFY_REQUESTER_ON_REPLY")
    SD_NOTIFY_REQUESTER_ON_RESOLVE: bool = Field(default=True, env="SD_NOTIFY_REQUESTER_ON_RESOLVE")
    # Los agentes siempre reciben la campana; esto añade el correo.
    SD_NOTIFY_AGENTS_BY_EMAIL: bool = Field(default=True, env="SD_NOTIFY_AGENTS_BY_EMAIL")
    # Buzon al que contesta el cliente (Reply-To). Vacio: el remitente SMTP.
    SD_REPLY_TO_ADDRESS: str = Field(default="", env="SD_REPLY_TO_ADDRESS")

    # ── Bandeja de eventos ───────────────────────────────────────────────────
    SD_EVENT_MAX_ATTEMPTS: int = Field(default=5, env="SD_EVENT_MAX_ATTEMPTS")
    SD_EVENT_BATCH_SIZE: int = Field(default=200, env="SD_EVENT_BATCH_SIZE")
