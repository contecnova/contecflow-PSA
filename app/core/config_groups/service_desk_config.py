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

    # ── Cambios ──────────────────────────────────────────────────────────────
    # Cola (AgentGroup) que hace de comite de cambios; en emergencias votan
    # solo sus responsables. Regla: majority, all o any.
    SD_CAB_GROUP_ID: str = Field(default="", env="SD_CAB_GROUP_ID")
    SD_CAB_APPROVAL_RULE: str = Field(default="majority", env="SD_CAB_APPROVAL_RULE")
    # Un cambio estandar con riesgo calculado hasta aqui se aprueba solo.
    SD_CHANGE_AUTO_APPROVE_MAX_RISK: int = Field(default=30, env="SD_CHANGE_AUTO_APPROVE_MAX_RISK")

    # ── Monitorizacion y guardias ────────────────────────────────────────────
    # Gravedad de la alerta -> prioridad del ticket (JSON). Lo que no este, P3.
    SD_EVENT_SEVERITY_MAP: str = Field(
        default='{"critical": "p1_critical", "high": "p2_high", "error": "p2_high", '
                '"warning": "p3_medium", "info": "p4_low"}',
        env="SD_EVENT_SEVERITY_MAP")
    # Al recuperarse la alerta, resolver su incidencia si nadie la ha tocado.
    SD_EVENT_AUTO_RESOLVE: bool = Field(default=True, env="SD_EVENT_AUTO_RESOLVE")
    # Prioridades que avisan a quien esta de guardia en la cola del ticket.
    SD_ONCALL_PRIORITIES: str = Field(default="p1_critical,p2_high", env="SD_ONCALL_PRIORITIES")
    SD_ONCALL_SMS: bool = Field(default=True, env="SD_ONCALL_SMS")

    # ── Base de conocimiento ─────────────────────────────────────────────────
    # Con revision, el autor envia y publica un revisor (la cola indicada, o un
    # administrador).
    SD_KB_REQUIRE_REVIEW: bool = Field(default=False, env="SD_KB_REQUIRE_REVIEW")
    SD_KB_REVIEWER_GROUP_ID: str = Field(default="", env="SD_KB_REVIEWER_GROUP_ID")

    # ── Tiempo ───────────────────────────────────────────────────────────────
    # El tiempo de un ticket con proyecto pasa a los partes del agente (y de
    # ahi a la factura si es facturable), con las reglas de imputacion.
    SD_TIME_TO_TIMESHEET: bool = Field(default=True, env="SD_TIME_TO_TIMESHEET")

    # ── Bandeja de eventos ───────────────────────────────────────────────────
    SD_EVENT_MAX_ATTEMPTS: int = Field(default=5, env="SD_EVENT_MAX_ATTEMPTS")
    SD_EVENT_BATCH_SIZE: int = Field(default=200, env="SD_EVENT_BATCH_SIZE")
