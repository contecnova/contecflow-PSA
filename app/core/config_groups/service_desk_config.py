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

    # ── Correo entrante ──────────────────────────────────────────────────────
    # Direccion de soporte de la organizacion: con ella se sabe de quien es un
    # correo que llega por webhook, y es el Reply-To de los avisos (vacia: el
    # remitente SMTP). El buzon (IMAP o Microsoft 365) se configura
    # en Credenciales > «Service Desk mailbox».
    SD_INBOUND_ADDRESS: str = Field(default="", env="SD_INBOUND_ADDRESS")
    # Respuesta a un ticket resuelto: lo reabre. Uno cerrado abre uno nuevo enlazado.
    SD_REOPEN_ON_REPLY: bool = Field(default=True, env="SD_REOPEN_ON_REPLY")
    SD_CHANNEL_TICKET_TYPE: str = Field(default="incident", env="SD_CHANNEL_TICKET_TYPE")
    SD_MAIL_MAX_PER_RUN: int = Field(default=50, env="SD_MAIL_MAX_PER_RUN")
    SD_MAIL_MAX_ATTACHMENT_MB: int = Field(default=15, env="SD_MAIL_MAX_ATTACHMENT_MB")

    # ── Bandeja de eventos ───────────────────────────────────────────────────
    SD_EVENT_MAX_ATTEMPTS: int = Field(default=5, env="SD_EVENT_MAX_ATTEMPTS")
    SD_EVENT_BATCH_SIZE: int = Field(default=200, env="SD_EVENT_BATCH_SIZE")
