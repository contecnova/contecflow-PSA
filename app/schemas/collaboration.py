"""Pydantic schemas for collaboration domain."""
from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel, Field


# ── Common ───────────────────────────────────────────────────────────────────
class Page(BaseModel):
    items: list = Field(default_factory=list, description="Lista de elementos de la página actual")
    total: int = Field(0, description="Total de elementos disponibles")
    page: int = Field(1, description="Número de página actual")
    page_size: int = Field(50, description="Tamaño de página solicitado")


# ── Workspaces ───────────────────────────────────────────────────────────────
class WorkspaceOut(BaseModel):
    id: str
    organization_id: str
    name: str = Field(..., description="Nombre del workspace")
    icon_url: Optional[str] = Field(None, description="URL del icono del workspace")
    primary_color: Optional[str] = Field(None, description="Color primario en hexadecimal")
    settings: dict = Field({}, description="Configuración personalizada del workspace")
    is_active: bool = Field(True, description="Indica si el workspace está activo")


class WorkspaceUpdate(BaseModel):
    name: Optional[str] = Field(None, description="Nuevo nombre del workspace")
    icon_url: Optional[str] = Field(None, description="Nueva URL del icono")
    primary_color: Optional[str] = Field(None, description="Nuevo color primario en hexadecimal")
    settings: Optional[dict] = Field(None, description="Nueva configuración del workspace")


# ── Teams ────────────────────────────────────────────────────────────────────
class TeamCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=120, description="Nombre del equipo")
    slug: Optional[str] = Field(None, description="Slug URL-friendly del equipo")
    description: Optional[str] = Field(None, description="Descripción del equipo")
    is_private: bool = Field(False, description="Indica si el equipo es privado")
    project_id: Optional[str] = Field(None, description="ID del proyecto asociado al equipo")


class TeamUpdate(BaseModel):
    name: Optional[str] = Field(None, description="Nuevo nombre del equipo")
    description: Optional[str] = Field(None, description="Nueva descripción del equipo")
    is_private: Optional[bool] = Field(None, description="Cambia el estado de privacidad")
    is_archived: Optional[bool] = Field(None, description="Archiva o desarchiva el equipo")


class TeamOut(BaseModel):
    id: str
    name: str = Field(..., description="Nombre del equipo")
    slug: str = Field(..., description="Slug URL-friendly del equipo")
    description: Optional[str] = Field(None, description="Descripción del equipo")
    is_private: bool = Field(..., description="Indica si el equipo es privado")
    project_id: Optional[str] = Field(None, description="ID del proyecto asociado")
    is_archived: bool = Field(..., description="Indica si el equipo está archivado")
    member_count: int = Field(0, description="Número de miembros del equipo")
    channel_count: int = Field(0, description="Número de canales del equipo")
    created_at: Optional[datetime] = None


class TeamMemberOut(BaseModel):
    id: str
    user_id: str = Field(..., description="ID del usuario miembro")
    user_name: Optional[str] = Field(None, description="Nombre del usuario")
    user_email: Optional[str] = Field(None, description="Email del usuario")
    role: str = Field("member", description="Rol del usuario en el equipo")
    joined_at: Optional[datetime] = Field(None, description="Fecha en que se unió al equipo")


class TeamMemberUpsert(BaseModel):
    user_ids: List[str] = Field(..., description="Lista de IDs de usuarios a añadir o actualizar")
    role: str = Field("member", description="Rol a asignar a los usuarios")


# ── Channels ─────────────────────────────────────────────────────────────────
class ChannelCreate(BaseModel):
    team_id: str = Field(..., description="ID del equipo propietario del canal")
    name: str = Field(..., min_length=1, max_length=120, description="Nombre del canal")
    slug: Optional[str] = Field(None, description="Slug URL-friendly del canal")
    topic: Optional[str] = Field(None, description="Tema breve del canal")
    description: Optional[str] = Field(None, description="Descripción extendida del canal")
    channel_type: str = Field("public", description="Tipo de canal (public, private, announcement, project)")
    is_default: bool = Field(False, description="Indica si es canal por defecto del equipo")
    project_id: Optional[str] = Field(None, description="ID del proyecto si es canal de proyecto")
    initial_member_ids: List[str] = Field([], description="IDs de miembros iniciales del canal")


class ChannelUpdate(BaseModel):
    name: Optional[str] = Field(None, description="Nuevo nombre del canal")
    topic: Optional[str] = Field(None, description="Nuevo tema del canal")
    description: Optional[str] = Field(None, description="Nueva descripción del canal")
    channel_type: Optional[str] = Field(None, description="Nuevo tipo de canal")
    is_archived: Optional[bool] = Field(None, description="Archiva o desarchiva el canal")


class ChannelOut(BaseModel):
    id: str
    conversation_id: str = Field(..., description="ID de la conversación subyacente")
    team_id: str = Field(..., description="ID del equipo propietario")
    name: str = Field(..., description="Nombre del canal")
    slug: str = Field(..., description="Slug del canal")
    topic: Optional[str] = Field(None, description="Tema del canal")
    description: Optional[str] = Field(None, description="Descripción del canal")
    channel_type: str = Field(..., description="Tipo de canal")
    is_default: bool = Field(..., description="Indica si es canal por defecto")
    is_archived: bool = Field(..., description="Indica si está archivado")
    project_id: Optional[str] = Field(None, description="ID del proyecto asociado")
    member_count: int = Field(0, description="Número de miembros del canal")
    unread_count: int = Field(0, description="Mensajes sin leer del usuario actual")
    last_activity_at: Optional[datetime] = Field(None, description="Marca temporal de la última actividad")


class ChannelMemberOut(BaseModel):
    id: str
    user_id: str = Field(..., description="ID del usuario miembro")
    user_name: Optional[str] = Field(None, description="Nombre del usuario")
    role: str = Field("member", description="Rol del usuario en el canal")
    notify_level: str = Field("all", description="Nivel de notificaciones (all, mentions, none)")
    is_starred: bool = Field(False, description="Indica si el canal está destacado por el usuario")
    is_muted: bool = Field(False, description="Indica si el canal está silenciado")
    last_read_at: Optional[datetime] = Field(None, description="Marca temporal de la última lectura")


# ── Direct + Group Conversations ─────────────────────────────────────────────
class DirectOpenIn(BaseModel):
    user_id: Optional[str] = Field(None, description="ID del usuario destinatario interno")
    client_user_id: Optional[str] = Field(None, description="ID del usuario cliente externo")


class GroupCreate(BaseModel):
    title: Optional[str] = Field(None, description="Título del chat de grupo")
    user_ids: List[str] = Field([], description="IDs de usuarios internos miembros")
    client_user_ids: List[str] = Field([], description="IDs de usuarios cliente miembros")


class GroupUpdate(BaseModel):
    title: Optional[str] = Field(None, description="Nuevo título del grupo")
    icon_url: Optional[str] = Field(None, description="Nueva URL del icono del grupo")


class ConversationOut(BaseModel):
    id: str
    kind: str = Field(..., description="Tipo de conversación (channel, direct, group)")
    workspace_id: str = Field(..., description="ID del workspace al que pertenece")
    last_activity_at: Optional[datetime] = Field(None, description="Marca temporal de la última actividad")
    last_message_id: Optional[str] = Field(None, description="ID del último mensaje enviado")
    is_archived: bool = Field(..., description="Indica si la conversación está archivada")
    title: Optional[str] = Field(None, description="Título de la conversación")
    icon_url: Optional[str] = Field(None, description="URL del icono de la conversación")
    members: List[dict] = Field([], description="Resumen de miembros de la conversación")
    unread_count: int = Field(0, description="Mensajes sin leer para el usuario actual")
    extra: dict = Field({}, description="Metadatos extra de la conversación")


# ── Messages ─────────────────────────────────────────────────────────────────
class MessageCreate(BaseModel):
    conversation_id: Optional[str] = Field(None, description="ID de la conversación destino")
    channel_id: Optional[str] = Field(None, description="ID del canal destino (alternativo a conversation_id)")
    direct_id: Optional[str] = Field(None, description="ID del chat directo destino")
    group_id: Optional[str] = Field(None, description="ID del chat de grupo destino")
    parent_message_id: Optional[str] = Field(None, description="ID del mensaje al que se responde en hilo")
    body: str = Field(..., min_length=1, max_length=20000, description="Contenido textual del mensaje")
    type: str = Field("text", description="Tipo de mensaje (text, system, bot, etc.)")
    metadata_json: dict = Field({}, description="Metadatos adicionales del mensaje")
    mention_user_ids: List[str] = Field([], description="IDs de usuarios mencionados")
    mention_client_ids: List[str] = Field([], description="IDs de usuarios cliente mencionados")
    is_everyone: bool = Field(False, description="Indica si menciona a @everyone")
    scheduled_for: Optional[datetime] = Field(None, description="Marca temporal para envío programado")
    linked_task_id: Optional[str] = Field(None, description="ID de tarea vinculada al mensaje")
    linked_ticket_id: Optional[str] = Field(None, description="ID de ticket vinculado al mensaje")
    linked_deliverable_id: Optional[str] = Field(None, description="ID de entregable vinculado al mensaje")
    linked_risk_id: Optional[str] = Field(None, description="ID de riesgo vinculado al mensaje")


class MessageUpdate(BaseModel):
    body: Optional[str] = Field(None, description="Nuevo contenido del mensaje")
    metadata_json: Optional[dict] = Field(None, description="Nuevos metadatos del mensaje")


class MessageOut(BaseModel):
    id: str
    conversation_id: str = Field(..., description="ID de la conversación a la que pertenece")
    thread_id: Optional[str] = Field(None, description="ID del hilo asociado")
    parent_message_id: Optional[str] = Field(None, description="ID del mensaje padre en el hilo")
    user_id: Optional[str] = Field(None, description="ID del usuario interno autor")
    client_user_id: Optional[str] = Field(None, description="ID del usuario cliente autor")
    bot_id: Optional[str] = Field(None, description="ID del bot autor si aplica")
    author_name: Optional[str] = Field(None, description="Nombre visible del autor")
    author_avatar: Optional[str] = Field(None, description="URL del avatar del autor")
    type: str = Field(..., description="Tipo de mensaje")
    status: str = Field(..., description="Estado del mensaje (sent, edited, deleted, etc.)")
    body: Optional[str] = Field(None, description="Contenido textual del mensaje")
    body_html: Optional[str] = Field(None, description="Contenido renderizado en HTML")
    metadata_json: dict = Field({}, description="Metadatos adicionales")
    has_attachments: bool = Field(False, description="Indica si tiene adjuntos")
    attachments: List[dict] = Field([], description="Lista de adjuntos del mensaje")
    reactions: List[dict] = Field([], description="Reacciones agregadas al mensaje")
    is_pinned: bool = Field(False, description="Indica si está fijado en la conversación")
    is_redacted: bool = Field(False, description="Indica si ha sido redactado por compliance")
    linked_task_id: Optional[str] = Field(None, description="ID de tarea vinculada")
    linked_ticket_id: Optional[str] = Field(None, description="ID de ticket vinculado")
    linked_deliverable_id: Optional[str] = Field(None, description="ID de entregable vinculado")
    linked_risk_id: Optional[str] = Field(None, description="ID de riesgo vinculado")
    edited_at: Optional[datetime] = Field(None, description="Marca temporal de la última edición")
    deleted_at: Optional[datetime] = None
    sent_at: datetime = Field(..., description="Marca temporal de envío")


class MessageVersionOut(BaseModel):
    id: str
    body: Optional[str] = Field(None, description="Contenido del mensaje en esa versión")
    edited_by_user_id: Optional[str] = Field(None, description="Usuario que realizó la edición")
    edited_at: datetime = Field(..., description="Marca temporal de la edición")


# ── Reactions / Mentions / Reads ─────────────────────────────────────────────
class ReactionToggle(BaseModel):
    emoji: str = Field(..., min_length=1, max_length=60, description="Emoji aplicado como reacción")


class ReadUpdate(BaseModel):
    last_message_id: str = Field(..., description="ID del último mensaje leído por el usuario")


# ── Pinned + Saved ───────────────────────────────────────────────────────────
class PinIn(BaseModel):
    message_id: str = Field(..., description="ID del mensaje a fijar")


class SaveIn(BaseModel):
    message_id: str = Field(..., description="ID del mensaje guardado")
    note: Optional[str] = Field(None, description="Nota personal asociada al guardado")


# ── Drafts ───────────────────────────────────────────────────────────────────
class DraftIn(BaseModel):
    body: str = Field("", description="Contenido del borrador")
    metadata_json: dict = Field({}, description="Metadatos asociados al borrador")
    parent_message_id: Optional[str] = Field(None, description="Mensaje padre si es respuesta en hilo")


# ── Presence ─────────────────────────────────────────────────────────────────
class PresenceIn(BaseModel):
    status: str = Field("online", description="Estado de presencia (online, away, busy, offline)")
    custom_message: Optional[str] = Field(None, description="Mensaje personalizado de estado")


class PresenceOut(BaseModel):
    user_id: Optional[str] = Field(None, description="ID del usuario interno")
    client_user_id: Optional[str] = Field(None, description="ID del usuario cliente")
    status: str = Field(..., description="Estado de presencia")
    custom_message: Optional[str] = Field(None, description="Mensaje personalizado de estado")
    is_in_call: bool = Field(False, description="Indica si el usuario está en llamada")
    last_seen_at: Optional[datetime] = Field(None, description="Marca temporal de la última conexión")


# ── Notification rules ───────────────────────────────────────────────────────
class NotificationRuleIn(BaseModel):
    scope: str = Field("global", description="Ámbito de la regla (global, workspace, channel)")
    target_id: Optional[str] = Field(None, description="ID del objetivo al que aplica la regla")
    notify_messages: str = Field("all", description="Nivel de notificación de mensajes (all, mentions, none)")
    desktop_push: bool = Field(True, description="Indica si se envían notificaciones push de escritorio")
    email_digest: str = Field("weekly", description="Frecuencia del resumen por email")
    do_not_disturb_from: Optional[str] = Field(None, description="Hora de inicio de no molestar (HH:MM)")
    do_not_disturb_to: Optional[str] = Field(None, description="Hora de fin de no molestar (HH:MM)")


# ── Attachments ──────────────────────────────────────────────────────────────
class AttachmentInitIn(BaseModel):
    conversation_id: str = Field(..., description="ID de la conversación que recibirá el adjunto")
    name: str = Field(..., description="Nombre del archivo a subir")
    mime_type: Optional[str] = Field(None, description="MIME type del archivo")
    size_bytes: int = Field(0, description="Tamaño del archivo en bytes")


class AttachmentInitOut(BaseModel):
    attachment_id: str = Field(..., description="ID asignado al adjunto")
    upload_url: str = Field(..., description="URL pre-firmada para subir el archivo")
    storage_provider: str = Field(..., description="Proveedor de almacenamiento destino")
    expires_in: int = Field(3600, description="Segundos hasta que expira la URL de subida")


class AttachmentOut(BaseModel):
    id: str
    name: str = Field(..., description="Nombre del archivo")
    mime_type: Optional[str] = Field(None, description="MIME type del archivo")
    size_bytes: int = Field(..., description="Tamaño del archivo en bytes")
    storage_provider: str = Field(..., description="Proveedor de almacenamiento")
    av_status: str = Field(..., description="Estado del análisis antivirus")
    dlp_status: str = Field(..., description="Estado del análisis DLP")
    is_quarantined: bool = Field(..., description="Indica si el archivo está en cuarentena")
    download_url: Optional[str] = Field(None, description="URL pre-firmada de descarga")
    preview_url: Optional[str] = Field(None, description="URL pre-firmada de previsualización")
    created_at: datetime


# ── Calls ────────────────────────────────────────────────────────────────────
class CallStartIn(BaseModel):
    conversation_id: str = Field(..., description="ID de la conversación donde se inicia la llamada")
    kind: str = Field("video", description="Tipo de llamada (audio, video, screen_share)")
    invite_user_ids: List[str] = Field([], description="IDs de usuarios invitados a la llamada")


class CallTokenOut(BaseModel):
    call_id: str = Field(..., description="ID de la llamada generada")
    livekit_url: str = Field(..., description="URL del servidor LiveKit")
    livekit_room: str = Field(..., description="Nombre de la sala LiveKit")
    livekit_token: str = Field(..., description="Token JWT para conectarse a LiveKit")
    kind: str = Field(..., description="Tipo de llamada")
    role: str = Field("participant", description="Rol del usuario en la llamada (host, participant)")


class CallSummaryOut(BaseModel):
    id: str
    conversation_id: str = Field(..., description="ID de la conversación de la llamada")
    kind: str = Field(..., description="Tipo de llamada")
    status: str = Field(..., description="Estado de la llamada")
    started_at: Optional[datetime] = Field(None, description="Marca temporal de inicio")
    ended_at: Optional[datetime] = Field(None, description="Marca temporal de fin")
    duration_seconds: int = Field(..., description="Duración total en segundos")
    is_recorded: bool = Field(..., description="Indica si la llamada fue grabada")
    has_transcript: bool = Field(..., description="Indica si hay transcripción disponible")
    has_summary: bool = Field(..., description="Indica si hay resumen IA disponible")
    summary_text: Optional[str] = Field(None, description="Resumen generado por IA")
    actions: List[dict] = Field([], description="Acciones derivadas de la llamada")
    participants: List[dict] = Field([], description="Lista de participantes de la llamada")


# ── Bots ─────────────────────────────────────────────────────────────────────
class BotOut(BaseModel):
    id: str
    kind: str = Field(..., description="Tipo de bot")
    handle: str = Field(..., description="Identificador único tipo @handle")
    display_name: str = Field(..., description="Nombre visible del bot")
    description: Optional[str] = Field(None, description="Descripción del bot")
    avatar_url: Optional[str] = Field(None, description="URL del avatar del bot")
    is_enabled: bool = Field(..., description="Indica si el bot está habilitado")


class BotMessageIn(BaseModel):
    bot_handle: str = Field(..., description="Handle del bot al que se invoca")
    conversation_id: str = Field(..., description="ID de la conversación donde se invoca")
    args: str = Field("", description="Argumentos pasados al bot")


# ── Slash command ────────────────────────────────────────────────────────────
class SlashCommandIn(BaseModel):
    conversation_id: str = Field(..., description="ID de la conversación donde se ejecuta el comando")
    command: str = Field(..., description="Nombre del comando slash (sin la barra)")
    args: str = Field("", description="Argumentos pasados al comando")


class SlashCommandOut(BaseModel):
    command: str = Field(..., description="Comando ejecutado")
    success: bool = Field(..., description="Indica si la ejecución fue exitosa")
    response: dict = Field({}, description="Respuesta estructurada del comando")


# ── Integrations / Webhooks ──────────────────────────────────────────────────
class IntegrationCreate(BaseModel):
    kind: str = Field(..., description="Tipo de integración (slack, teams, jira, etc.)")
    name: str = Field(..., description="Nombre descriptivo de la integración")
    config: dict = Field({}, description="Configuración específica de la integración")


class IntegrationOut(BaseModel):
    id: str
    kind: str = Field(..., description="Tipo de integración")
    name: str = Field(..., description="Nombre descriptivo")
    is_enabled: bool = Field(..., description="Indica si la integración está habilitada")
    config: dict = Field(..., description="Configuración asociada")
    created_at: datetime


class WebhookCreate(BaseModel):
    direction: str = Field("incoming", description="Dirección del webhook (incoming, outgoing)")
    name: str = Field(..., description="Nombre descriptivo del webhook")
    url: Optional[str] = Field(None, description="URL destino para webhooks salientes")
    target_channel_id: Optional[str] = Field(None, description="ID del canal destino para webhooks entrantes")
    events: List[str] = Field([], description="Eventos a los que se suscribe el webhook")


class WebhookOut(BaseModel):
    id: str
    direction: str = Field(..., description="Dirección del webhook")
    name: str = Field(..., description="Nombre descriptivo")
    url: Optional[str] = Field(None, description="URL destino del webhook")
    secret_token: str = Field(..., description="Token secreto para firmar las peticiones")
    target_channel_id: Optional[str] = Field(None, description="Canal destino para webhooks entrantes")
    events: List[str] = Field([], description="Eventos a los que se suscribe")
    is_active: bool = Field(..., description="Indica si el webhook está activo")
    last_called_at: Optional[datetime] = Field(None, description="Marca temporal de la última invocación")
    failure_count: int = Field(0, description="Número de fallos consecutivos")


# ── Compliance ───────────────────────────────────────────────────────────────
class RetentionPolicyIn(BaseModel):
    name: str = Field(..., description="Nombre de la política de retención")
    scope: str = Field("workspace", description="Ámbito de aplicación (workspace, team, channel)")
    target_id: Optional[str] = Field(None, description="ID del objetivo al que aplica la política")
    retention_months: int = Field(24, description="Meses de retención antes de purgar")
    apply_to: str = Field("all", description="Tipo de contenido afectado (all, messages, files)")


class RetentionPolicyOut(RetentionPolicyIn):
    id: str
    is_active: bool = Field(..., description="Indica si la política está activa")


class LegalHoldIn(BaseModel):
    case_reference: str = Field(..., description="Referencia del caso legal")
    description: Optional[str] = Field(None, description="Descripción del legal hold")
    custodian_user_ids: List[str] = Field([], description="Usuarios internos custodios")
    custodian_client_ids: List[str] = Field([], description="Usuarios cliente custodios")
    channel_ids: List[str] = Field([], description="Canales afectados por el legal hold")


class LegalHoldOut(LegalHoldIn):
    id: str
    started_at: datetime = Field(..., description="Marca temporal de inicio del hold")
    ended_at: Optional[datetime] = Field(None, description="Marca temporal de fin del hold")
    is_active: bool = Field(..., description="Indica si el legal hold está activo")


class EDiscoveryRequest(BaseModel):
    case_reference: Optional[str] = Field(None, description="Referencia del caso de eDiscovery")
    user_ids: List[str] = Field([], description="Usuarios a incluir en la búsqueda")
    keywords: List[str] = Field([], description="Palabras clave de búsqueda")
    date_from: Optional[datetime] = Field(None, description="Fecha desde la que buscar")
    date_to: Optional[datetime] = Field(None, description="Fecha hasta la que buscar")
    include_attachments: bool = Field(True, description="Indica si se incluyen archivos adjuntos")


# ── Search ───────────────────────────────────────────────────────────────────
class SearchHit(BaseModel):
    kind: str = Field(..., description="Tipo de resultado (message, file, channel, user)")
    id: str = Field(..., description="ID del resultado encontrado")
    title: Optional[str] = Field(None, description="Título o nombre del resultado")
    snippet: Optional[str] = Field(None, description="Fragmento con la coincidencia destacada")
    conversation_id: Optional[str] = Field(None, description="ID de la conversación si aplica")
    sent_at: Optional[datetime] = Field(None, description="Marca temporal del recurso")
    score: float = Field(0.0, description="Puntuación de relevancia del resultado")
    extra: dict = Field({}, description="Metadatos extra del resultado")


class SearchResponse(BaseModel):
    hits: List[SearchHit] = Field(..., description="Lista de coincidencias encontradas")
    total: int = Field(..., description="Total de coincidencias")


# ── WebSocket events ─────────────────────────────────────────────────────────
class WsEvent(BaseModel):
    type: str = Field(..., description="Tipo de evento WebSocket")
    payload: dict = Field({}, description="Carga útil del evento")
    conversation_id: Optional[str] = Field(None, description="ID de conversación si aplica")
    message_id: Optional[str] = Field(None, description="ID del mensaje si aplica")
    timestamp: datetime = Field(default_factory=datetime.utcnow, description="Marca temporal del evento")


# ── Audit ────────────────────────────────────────────────────────────────────
class AuditEventOut(BaseModel):
    id: str
    actor_user_id: Optional[str] = Field(None, description="ID del usuario que realizó la acción")
    action: str = Field(..., description="Acción auditada")
    entity_type: str = Field(..., description="Tipo de entidad afectada")
    entity_id: Optional[str] = Field(None, description="ID de la entidad afectada")
    payload: dict = Field({}, description="Información detallada de la acción")
    created_at: datetime
