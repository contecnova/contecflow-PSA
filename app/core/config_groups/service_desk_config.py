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
    # Numeros de Twilio de la organizacion (E.164, separados por comas). Una
    # llamada o un SMS a uno de ellos es de esta organizacion; la voz rechaza
    # los numeros que no declara nadie (segunda auditoria 2026-11, #19). Se lee
    # por organizacion en la fila del ajuste; el valor del entorno no enruta.
    TWILIO_PHONE_NUMBERS: str = Field(default="", env="TWILIO_PHONE_NUMBERS")
    # Respuesta a un ticket resuelto: lo reabre. Uno cerrado abre uno nuevo enlazado.
    SD_REOPEN_ON_REPLY: bool = Field(default=True, env="SD_REOPEN_ON_REPLY")
    SD_CHANNEL_TICKET_TYPE: str = Field(default="incident", env="SD_CHANNEL_TICKET_TYPE")
    SD_MAIL_MAX_PER_RUN: int = Field(default=50, env="SD_MAIL_MAX_PER_RUN")
    SD_MAIL_MAX_ATTACHMENT_MB: int = Field(default=15, env="SD_MAIL_MAX_ATTACHMENT_MB")
    # Auditoria 2026-11-22 (A-SD6): el `From` de un correo solo actua como su
    # persona (comenta como ella, cambia el estado) con SPF/DKIM/DMARC en
    # `Authentication-Results`. Apagarlo solo si la pasarela no anota esos
    # resultados. `SD_INBOUND_AUTHSERV_ID`: el servidor cuya cabecera vale.
    SD_INBOUND_REQUIRE_SENDER_AUTH: bool = Field(default=True, env="SD_INBOUND_REQUIRE_SENDER_AUTH")
    SD_INBOUND_AUTHSERV_ID: str = Field(default="", env="SD_INBOUND_AUTHSERV_ID")

    # ── Agente autonomo ──────────────────────────────────────────────────────
    # Barrido cada 5 min de los tickets nuevos: comenta y, con un playbook que
    # lo permita, resuelve. Apagado por defecto: escribe al solicitante.
    SD_AUTONOMOUS_AGENT_ENABLED: bool = Field(default=False, env="SD_AUTONOMOUS_AGENT_ENABLED")
    SD_AUTONOMY_RESOLVE_THRESHOLD: float = Field(default=0.80, env="SD_AUTONOMY_RESOLVE_THRESHOLD")
    SD_AUTONOMY_SUGGEST_THRESHOLD: float = Field(default=0.50, env="SD_AUTONOMY_SUGGEST_THRESHOLD")
    # Mejoras de mercado 16-11-2026. Modo: suggest (deja la propuesta para un
    # agente) o execute. Playbooks de serie apagados en la empresa (CSV de ids).
    SD_AUTONOMOUS_AGENT_MODE: str = Field(default="suggest", env="SD_AUTONOMOUS_AGENT_MODE")
    SD_AUTONOMOUS_DISABLED_PLAYBOOKS: str = Field(default="", env="SD_AUTONOMOUS_DISABLED_PLAYBOOKS")
    # Cola por riesgo: peso del riesgo de SLA frente al valor de negocio (0-1).
    SD_QUEUE_SLA_RISK_WEIGHT: float = Field(default=0.65, env="SD_QUEUE_SLA_RISK_WEIGHT")
    # Candidatos a duplicado: dias hacia atras, parecido minimo (0-1) y cuantos.
    SD_DUPLICATE_WINDOW_DAYS: int = Field(default=14, env="SD_DUPLICATE_WINDOW_DAYS")
    SD_DUPLICATE_MIN_SIMILARITY: float = Field(default=0.35, env="SD_DUPLICATE_MIN_SIMILARITY")
    SD_DUPLICATE_MAX_CANDIDATES: int = Field(default=5, env="SD_DUPLICATE_MAX_CANDIDATES")
    # Aviso de colision: segundos sin latido tras los que una presencia caduca.
    SD_PRESENCE_TTL_SECONDS: int = Field(default=45, env="SD_PRESENCE_TTL_SECONDS")
    # Asistente del portal: caducidad de una propuesta, parecido minimo para
    # proponer un servicio y el servicio que restablece contrasenas (vacio: no hay).
    SD_PORTAL_ASSISTANT_ACTION_TTL_MINUTES: int = Field(default=15, env="SD_PORTAL_ASSISTANT_ACTION_TTL_MINUTES")
    SD_PORTAL_ASSISTANT_MIN_MATCH: float = Field(default=0.2, env="SD_PORTAL_ASSISTANT_MIN_MATCH")
    SD_PASSWORD_RESET_SERVICE_ID: str = Field(default="", env="SD_PASSWORD_RESET_SERVICE_ID")
    # Canales en tiempo real (17-11-2026): el asistente del portal entiende con
    # la IA (si no hay IA, reconocimiento por palabras) y su tope de tokens.
    SD_PORTAL_ASSISTANT_AI: bool = Field(default=True, env="SD_PORTAL_ASSISTANT_AI")
    SD_PORTAL_ASSISTANT_MAX_TOKENS: int = Field(default=700, env="SD_PORTAL_ASSISTANT_MAX_TOKENS")
    # Slack: canal donde se publica la tarjeta de cada ticket nuevo (su hilo
    # queda atado) y canales de entrada (cada mensaje raiz abre un ticket), por
    # id de canal. Adjuntos de los canales: tope en MB.
    SD_SLACK_TICKET_CHANNEL: str = Field(default="", env="SD_SLACK_TICKET_CHANNEL")
    SD_SLACK_INTAKE_CHANNELS: str = Field(default="", env="SD_SLACK_INTAKE_CHANNELS")
    SD_CHANNEL_MAX_ATTACHMENT_MB: int = Field(default=16, env="SD_CHANNEL_MAX_ATTACHMENT_MB")

    # ── Cambios ──────────────────────────────────────────────────────────────
    # Cola (AgentGroup) que hace de comite de cambios; en emergencias votan
    # solo sus responsables. Regla: majority, all o any.
    SD_CAB_GROUP_ID: str = Field(default="", env="SD_CAB_GROUP_ID")
    SD_CAB_APPROVAL_RULE: str = Field(default="majority", env="SD_CAB_APPROVAL_RULE")
    # Un cambio estandar con riesgo calculado hasta aqui se aprueba solo.
    SD_CHANGE_AUTO_APPROVE_MAX_RISK: int = Field(default=30, env="SD_CHANGE_AUTO_APPROVE_MAX_RISK")
    # Catalogo de cambios estandar (23-11-2026, A-SD19): un modelo se suspende
    # (vuelve al CAB) si su tasa de fallo supera este % con al menos N cierres;
    # su aprobacion caduca a los N dias (revision periodica).
    SD_STANDARD_CHANGE_MAX_FAILURE_PCT: int = Field(default=20, env="SD_STANDARD_CHANGE_MAX_FAILURE_PCT")
    SD_STANDARD_CHANGE_MIN_CLOSURES: int = Field(default=5, env="SD_STANDARD_CHANGE_MIN_CLOSURES")
    SD_STANDARD_CHANGE_REVIEW_DAYS: int = Field(default=365, env="SD_STANDARD_CHANGE_REVIEW_DAYS")

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

    # ── Autorresolucion con IA (valores por defecto) ─────────────────────────
    # Cada empresa los cambia en su configuracion de autorresolucion
    # (`sd.auto_resolution.config::<empresa>`); esto es solo el punto de partida.
    SD_AUTO_CLOSE_HOURS_AFTER_RESOLUTION: int = Field(default=72, ge=1, le=720, env="SD_AUTO_CLOSE_HOURS_AFTER_RESOLUTION")
    SD_VALIDATION_WINDOW_HOURS: int = Field(default=48, ge=1, le=720, env="SD_VALIDATION_WINDOW_HOURS")

    # ── Errores conocidos (KEDB) ─────────────────────────────────────────────
    # Dias hasta la revision de un error conocido al publicarlo o revisarlo
    # (si la peticion no trae otro valor). Ajuste en vivo por empresa.
    KEDB_DEFAULT_REVIEW_DAYS: int = Field(default=90, ge=7, le=365, env="KEDB_DEFAULT_REVIEW_DAYS")

    # ── Bandeja de eventos ───────────────────────────────────────────────────
    SD_EVENT_MAX_ATTEMPTS: int = Field(default=5, env="SD_EVENT_MAX_ATTEMPTS")
    SD_EVENT_BATCH_SIZE: int = Field(default=200, env="SD_EVENT_BATCH_SIZE")
