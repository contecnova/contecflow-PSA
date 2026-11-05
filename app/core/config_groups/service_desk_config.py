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

    # ── Agente autonomo ──────────────────────────────────────────────────────
    # Barrido cada 5 min de los tickets nuevos: comenta y, con un playbook que
    # lo permita, resuelve. Apagado por defecto: escribe al solicitante.
    SD_AUTONOMOUS_AGENT_ENABLED: bool = Field(default=False, env="SD_AUTONOMOUS_AGENT_ENABLED")
    SD_AUTONOMY_RESOLVE_THRESHOLD: float = Field(default=0.80, env="SD_AUTONOMY_RESOLVE_THRESHOLD")
    SD_AUTONOMY_SUGGEST_THRESHOLD: float = Field(default=0.50, env="SD_AUTONOMY_SUGGEST_THRESHOLD")

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
    # Calidad de la base de conocimiento (revisión 2026-11).
    # Relevancia mínima para citar un artículo: por vectores (coseno) o, sin
    # modelo de frases, fracción de palabras de la pregunta que aparecen.
    SD_KB_RAG_MIN_SCORE_VECTOR: float = Field(default=0.35, env="SD_KB_RAG_MIN_SCORE_VECTOR")
    SD_KB_RAG_MIN_SCORE_WORDS: float = Field(default=0.5, env="SD_KB_RAG_MIN_SCORE_WORDS")
    SD_KB_RAG_MAX_SOURCES: int = Field(default=3, env="SD_KB_RAG_MAX_SOURCES")
    # Parecido mínimo entre preguntas para aplicar la corrección de un experto.
    SD_KB_CORRECTION_MATCH: float = Field(default=0.8, env="SD_KB_CORRECTION_MATCH")
    # Días sin tocar un artículo publicado para avisar de que hay que revisarlo (0: no).
    SD_KB_STALE_DAYS: int = Field(default=180, env="SD_KB_STALE_DAYS")
    # Contradicciones: parecido mínimo para comparar dos artículos con IA, y
    # pares como mucho por pasada (0: no se buscan).
    SD_KB_CONTRADICTION_SIMILARITY: float = Field(default=0.75, env="SD_KB_CONTRADICTION_SIMILARITY")
    SD_KB_CONTRADICTION_MAX_PAIRS: int = Field(default=10, env="SD_KB_CONTRADICTION_MAX_PAIRS")

    # ── Tiempo ───────────────────────────────────────────────────────────────
    # El tiempo de un ticket con proyecto pasa a los partes del agente (y de
    # ahi a la factura si es facturable), con las reglas de imputacion.
    SD_TIME_TO_TIMESHEET: bool = Field(default=True, env="SD_TIME_TO_TIMESHEET")

    # ── Activos ──────────────────────────────────────────────────────────────
    # Dias antes de que venza la garantia, el fin de vida, el leasing o el
    # mantenimiento de un activo en que el escaneo diario abre su ticket de
    # renovacion. 0 lo apaga.
    SD_ASSET_REFRESH_DAYS: int = Field(default=7, ge=0, env="SD_ASSET_REFRESH_DAYS")

    # ── Bandeja de eventos ───────────────────────────────────────────────────
    SD_EVENT_MAX_ATTEMPTS: int = Field(default=5, env="SD_EVENT_MAX_ATTEMPTS")
    SD_EVENT_BATCH_SIZE: int = Field(default=200, env="SD_EVENT_BATCH_SIZE")
