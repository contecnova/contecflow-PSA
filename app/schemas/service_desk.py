"""
Service Desk – Pydantic input schemas.

All request-body models are defined here so they can be tested independently
of the FastAPI router and reused across endpoints.
"""
from typing import Optional
from datetime import datetime
from pydantic import BaseModel, Field, field_validator

from app.core.config import settings


# ── Ticket ────────────────────────────────────────────────────────────────────

class TicketCreateIn(BaseModel):
    title: str = Field(..., description="Título del ticket")
    description: str = Field(..., description="Descripción detallada del ticket")
    ticket_type: str = Field("incident", description="Tipo de ticket (incident, request, problem, change)")
    urgency: str = Field("medium", description="Urgencia del ticket (low, medium, high, critical)")
    impact: str = Field("user", description="Impacto del ticket (user, department, organization)")
    priority: Optional[str] = Field(None, description="Prioridad del ticket (auto-calculada si no se proporciona)")
    service_item_id: Optional[str] = Field(None, description="ID del ítem de catálogo de servicios")
    project_id: Optional[str] = Field(None, description="ID del proyecto asociado")
    contract_id: Optional[str] = Field(None, description="ID del contrato asociado")
    client_id: Optional[str] = Field(None, description="ID del cliente solicitante")
    ci_id: Optional[str] = Field(None, description="ID del configuration item afectado")
    tags: Optional[str] = Field(None, description="Etiquetas separadas por comas")
    assigned_to_user_id: Optional[str] = Field(None, description="ID del usuario asignado al ticket")
    assigned_group_id: Optional[str] = Field(None, description="ID del grupo asignado al ticket")
    requester_name: Optional[str] = Field(None, description="Nombre del solicitante externo")
    requester_email: Optional[str] = Field(None, description="Email del solicitante externo")
    source: str = Field("portal", description="Canal de origen del ticket (portal, email, phone, chat)")
    dynamic_fields: Optional[dict] = Field(None, description="Campos dinámicos personalizados del ticket")

    @field_validator('service_item_id', 'project_id', 'contract_id', 'client_id', 'ci_id',
                     'assigned_to_user_id', 'assigned_group_id', mode='before')
    @classmethod
    def empty_str_to_none(cls, v):
        return None if v == '' else v


class TicketUpdateIn(BaseModel):
    title: Optional[str] = Field(None, description="Nuevo título del ticket")
    description: Optional[str] = Field(None, description="Nueva descripción del ticket")
    status: Optional[str] = Field(None, description="Nuevo estado del ticket")
    priority: Optional[str] = Field(None, description="Nueva prioridad del ticket")
    urgency: Optional[str] = Field(None, description="Nueva urgencia del ticket")
    impact: Optional[str] = Field(None, description="Nuevo impacto del ticket")
    support_level: Optional[str] = Field(None, description="Nivel de soporte asignado (l1, l2, l3)")
    assigned_to_user_id: Optional[str] = Field(None, description="Nuevo usuario asignado")
    assigned_group_id: Optional[str] = Field(None, description="Nuevo grupo asignado")
    ci_id: Optional[str] = Field(None, description="Nuevo configuration item asociado")
    project_id: Optional[str] = Field(None, description="Nuevo proyecto asociado")
    tags: Optional[str] = Field(None, description="Nuevas etiquetas")
    resolution: Optional[str] = Field(None, description="Texto de resolución del ticket")
    resolution_code: Optional[str] = Field(None, description="Código de resolución estandarizado")
    problem_id: Optional[str] = Field(None, description="ID del problema vinculado")
    dynamic_fields: Optional[dict] = Field(None, description="Nuevos valores de campos dinámicos")

    @field_validator('assigned_to_user_id', 'assigned_group_id', 'ci_id',
                     'project_id', 'problem_id', mode='before')
    @classmethod
    def empty_str_to_none(cls, v):
        return None if v == '' else v


class CommentIn(BaseModel):
    body: str = Field(..., description="Cuerpo del comentario en el ticket")
    is_public: bool = Field(True, description="Indica si el comentario es visible para el cliente")


class TimeLogIn(BaseModel):
    minutes: int = Field(..., description="Minutos invertidos en el ticket")
    unit: str = Field("minutes", description="Unidad de la cantidad reportada (minutes, hours)")
    description: Optional[str] = Field(None, description="Descripción del trabajo realizado")
    billable: bool = Field(False, description="Indica si el tiempo es facturable")


class CSATIn(BaseModel):
    score: int = Field(..., description="Puntuación de satisfacción del cliente (1-5)")
    comment: Optional[str] = Field(None, description="Comentario libre del cliente")


class MergeIn(BaseModel):
    merged_ticket_id: str = Field(..., description="ID del ticket que se fusiona con el actual")
    reason: Optional[str] = Field(None, description="Motivo de la fusión")


class SplitTicketIn(BaseModel):
    title: Optional[str] = Field(None, description="Título del nuevo ticket resultante del split")
    description: Optional[str] = Field(None, description="Descripción del nuevo ticket")
    ticket_type: Optional[str] = Field(None, description="Tipo del nuevo ticket")
    priority: Optional[str] = Field(None, description="Prioridad del nuevo ticket")
    urgency: Optional[str] = Field(None, description="Urgencia del nuevo ticket")
    impact: Optional[str] = Field(None, description="Impacto del nuevo ticket")
    support_level: Optional[str] = Field(None, description="Nivel de soporte del nuevo ticket")
    tags: Optional[str] = Field(None, description="Etiquetas del nuevo ticket")
    copy_latest_comments: int = Field(0, description="Número de comentarios recientes a copiar al nuevo ticket")


# ── Problem ───────────────────────────────────────────────────────────────────

class ProblemIn(BaseModel):
    title: str = Field(..., description="Título del problema raíz")
    description: str = Field(..., description="Descripción detallada del problema")
    priority: str = Field("p2_high", description="Prioridad del problema (p1_critical..p4_low)")
    ci_id: Optional[str] = Field(None, description="ID del configuration item afectado")
    project_id: Optional[str] = Field(None, description="ID del proyecto asociado")
    owner_user_id: Optional[str] = Field(None, description="ID del propietario del problema")


class ProblemUpdateIn(BaseModel):
    status: Optional[str] = Field(None, description="Nuevo estado del problema")
    root_cause: Optional[str] = Field(None, description="Causa raíz identificada")
    workaround: Optional[str] = Field(None, description="Solución temporal disponible")
    fix_description: Optional[str] = Field(None, description="Descripción de la solución definitiva")
    owner_user_id: Optional[str] = Field(None, description="Nuevo propietario del problema")


# ── Knowledge Base ────────────────────────────────────────────────────────────

class KBArticleIn(BaseModel):
    title: str = Field(..., description="Título del artículo de la KB")
    body: str = Field(..., description="Contenido del artículo en formato markdown/HTML")
    summary: Optional[str] = Field(None, description="Resumen breve del artículo")
    category_id: Optional[str] = Field(None, description="ID de la categoría a la que pertenece")
    tags: Optional[str] = Field(None, description="Etiquetas separadas por comas")
    is_public: bool = Field(True, description="Indica si el artículo es visible para clientes")
    status: str = Field("draft", description="Estado del artículo (draft, published, archived)")
    created_from_ticket_id: Optional[str] = Field(None, description="ID del ticket origen del artículo")


class KBArticleUpdate(BaseModel):
    title: Optional[str] = Field(None, description="Nuevo título del artículo")
    body: Optional[str] = Field(None, description="Nuevo contenido del artículo")
    summary: Optional[str] = Field(None, description="Nuevo resumen breve")
    tags: Optional[str] = Field(None, description="Nuevas etiquetas")
    is_public: Optional[bool] = Field(None, description="Actualiza la visibilidad pública")
    status: Optional[str] = Field(None, description="Nuevo estado del artículo")


# ── Service Catalog ───────────────────────────────────────────────────────────

class ServiceCategoryIn(BaseModel):
    name: str = Field(..., description="Nombre de la categoría del catálogo")
    description: Optional[str] = Field(None, description="Descripción de la categoría")
    icon: str = Field("🔧", description="Icono asociado a la categoría")
    color: str = Field("#00d4ff", description="Color en hexadecimal de la categoría")
    sort_order: int = Field(0, description="Orden de visualización de la categoría")


class ServiceItemIn(BaseModel):
    category_id: str = Field(..., description="ID de la categoría a la que pertenece el ítem")
    name: str = Field(..., description="Nombre del servicio del catálogo")
    description: Optional[str] = Field(None, description="Descripción del servicio")
    ticket_type: str = Field("service_request", description="Tipo de ticket que genera el servicio")
    default_priority: str = Field("p3_medium", description="Prioridad por defecto del servicio")
    default_support_level: str = Field("l1", description="Nivel de soporte por defecto")
    sla_response_hours: float = Field(8, description="Horas máximas para primera respuesta")
    sla_resolution_hours: float = Field(24, description="Horas máximas para resolución")
    requires_approval: bool = Field(False, description="Indica si requiere aprobación previa")
    is_visible_to_clients: bool = Field(True, description="Indica si es visible en el portal de clientes")
    sort_order: int = Field(0, description="Orden de visualización del servicio")


class ServiceItemUpdate(BaseModel):
    category_id: Optional[str] = Field(None, description="Nueva categoría a la que pertenece")
    name: Optional[str] = Field(None, description="Nuevo nombre del servicio")
    description: Optional[str] = Field(None, description="Nueva descripción del servicio")
    ticket_type: Optional[str] = Field(None, description="Nuevo tipo de ticket")
    default_priority: Optional[str] = Field(None, description="Nueva prioridad por defecto")
    default_support_level: Optional[str] = Field(None, description="Nuevo nivel de soporte por defecto")
    sla_response_hours: Optional[float] = Field(None, description="Nuevas horas SLA de respuesta")
    sla_resolution_hours: Optional[float] = Field(None, description="Nuevas horas SLA de resolución")
    requires_approval: Optional[bool] = Field(None, description="Actualiza si requiere aprobación")
    is_visible_to_clients: Optional[bool] = Field(None, description="Actualiza la visibilidad para clientes")
    sort_order: Optional[int] = Field(None, description="Nuevo orden de visualización")


# ── SLA ───────────────────────────────────────────────────────────────────────

class SLAPolicyIn(BaseModel):
    name: str = Field(..., description="Nombre de la política de SLA")
    is_default: bool = Field(False, description="Indica si es la política por defecto")
    p1_response_hours: float = Field(1, description="Horas de respuesta para P1 crítico")
    p1_resolution_hours: float = Field(4, description="Horas de resolución para P1 crítico")
    p2_response_hours: float = Field(4, description="Horas de respuesta para P2 alto")
    p2_resolution_hours: float = Field(8, description="Horas de resolución para P2 alto")
    p3_response_hours: float = Field(8, description="Horas de respuesta para P3 medio")
    p3_resolution_hours: float = Field(24, description="Horas de resolución para P3 medio")
    p4_response_hours: float = Field(24, description="Horas de respuesta para P4 bajo")
    p4_resolution_hours: float = Field(72, description="Horas de resolución para P4 bajo")
    business_hours_only: bool = Field(True, description="Cuenta solo horas de la jornada laboral")


class HolidayIn(BaseModel):
    name: str = Field(..., description="Nombre del festivo")
    holiday_date: str = Field(..., description="Fecha del festivo en formato YYYY-MM-DD")
    country: Optional[str] = Field(None, description="Código de país al que aplica el festivo")
    sla_policy_id: Optional[str] = Field(None, description="ID de la política SLA a la que aplica")


# ── Configuration Items ───────────────────────────────────────────────────────

class CIIn(BaseModel):
    name: str = Field(..., description="Nombre del configuration item")
    ci_type: str = Field(..., description="Tipo de CI (server, application, network, etc.)")
    status: str = Field("operational", description="Estado operativo del CI")
    description: Optional[str] = Field(None, description="Descripción detallada del CI")
    project_id: Optional[str] = Field(None, description="ID del proyecto al que pertenece")
    owner_user_id: Optional[str] = Field(None, description="ID del responsable del CI")
    environment: Optional[str] = Field(None, description="Entorno (production, staging, dev)")
    version: Optional[str] = Field(None, description="Versión del CI")
    location: Optional[str] = Field(None, description="Ubicación física o lógica del CI")
    vendor: Optional[str] = Field(None, description="Proveedor o fabricante del CI")
    criticality: str = Field("medium", description="Criticidad del CI (low, medium, high, critical)")
    sla_policy_id: Optional[str] = Field(None, description="Política SLA aplicada al CI")


# ── Agent Groups ──────────────────────────────────────────────────────────────

class AgentGroupIn(BaseModel):
    name: str = Field(..., description="Nombre del grupo de agentes")
    description: Optional[str] = Field(None, description="Descripción del grupo")
    support_level: str = Field("l1", description="Nivel de soporte del grupo (l1, l2, l3)")


# ── Announcements ─────────────────────────────────────────────────────────────

class AnnouncementIn(BaseModel):
    title: str = Field(..., description="Título del anuncio")
    body: str = Field(..., description="Contenido del anuncio")
    type: str = Field("info", description="Tipo del anuncio (info, warning, critical)")
    show_to_clients: bool = Field(True, description="Indica si es visible para clientes")
    ci_id: Optional[str] = Field(None, description="ID del CI afectado por el anuncio")
    starts_at: Optional[datetime] = Field(None, description="Inicio de la vigencia del anuncio")
    ends_at: Optional[datetime] = Field(None, description="Fin de la vigencia del anuncio")


# ── Escalation Rules ──────────────────────────────────────────────────────────

class EscalationRuleIn(BaseModel):
    name: str = Field(..., description="Nombre de la regla de escalado")
    trigger: str = Field(..., description="Evento o condición que dispara el escalado")
    action: str = Field(..., description="Acción a ejecutar al activarse la regla")
    applies_to_priority: Optional[str] = Field(None, description="Prioridades a las que aplica (JSON list o vacío para todas)")
    idle_hours_threshold: Optional[float] = Field(None, description="Horas de inactividad antes de escalar")
    group_id: Optional[str] = Field(None, description="ID del grupo origen al que aplica la regla")
    target_group_id: Optional[str] = Field(None, description="ID del grupo destino del escalado")
    notify_user_ids: Optional[str] = Field(None, description="JSON list de IDs de usuarios a notificar")
    target_priority: Optional[str] = Field(None, description="Nueva prioridad asignada al escalar")
    sort_order: int = Field(100, description="Orden de evaluación de la regla")
    is_active: bool = Field(True, description="Indica si la regla está activa")


# ── Assets ────────────────────────────────────────────────────────────────────

class AssetIn(BaseModel):
    name: str = Field(..., description="Nombre del activo")
    asset_type: str = Field(..., description="Tipo de activo (hardware, software, license, etc.)")
    serial_number: Optional[str] = Field(None, description="Número de serie del activo")
    model: Optional[str] = Field(None, description="Modelo del activo")
    manufacturer: Optional[str] = Field(None, description="Fabricante del activo")
    part_number: Optional[str] = Field(None, description="Número de pieza")
    license_key: Optional[str] = Field(None, description="Clave de licencia si aplica")
    license_seats: Optional[int] = Field(None, description="Número de asientos de licencia")
    purchase_date: Optional[str] = Field(None, description="Fecha de compra en formato YYYY-MM-DD")
    warranty_expiry: Optional[str] = Field(None, description="Fecha de expiración de la garantía")
    eol_date: Optional[str] = Field(None, description="Fecha de fin de vida del activo")
    lease_expiry: Optional[str] = Field(None, description="Fecha de expiración del leasing")
    purchase_price: Optional[float] = Field(None, description="Precio de compra del activo")
    current_value: Optional[float] = Field(None, description="Valor actual contable del activo")
    currency: str = Field(settings.DEFAULT_CURRENCY, description="Moneda en formato ISO 4217")
    po_number: Optional[str] = Field(None, description="Número de orden de compra")
    vendor: Optional[str] = Field(None, description="Proveedor del activo")
    vendor_contract: Optional[str] = Field(None, description="Contrato con el proveedor")
    location: Optional[str] = Field(None, description="Ubicación física del activo")
    assigned_user_id: Optional[str] = Field(None, description="ID del usuario que lo tiene asignado")
    department: Optional[str] = Field(None, description="Departamento al que pertenece")
    ci_id: Optional[str] = Field(None, description="ID del CI vinculado")
    tags: Optional[str] = Field(None, description="Etiquetas separadas por comas")
    notes: Optional[str] = Field(None, description="Notas internas sobre el activo")
    managed_by_user_id: Optional[str] = Field(None, description="Usuario responsable de su gestión")


class AssetUpdate(AssetIn):
    name: Optional[str] = Field(None, description="Nuevo nombre del activo")
    asset_type: Optional[str] = Field(None, description="Nuevo tipo de activo")
    status: Optional[str] = Field(None, description="Nuevo estado del activo")


# ── Status Page ───────────────────────────────────────────────────────────────

class StatusComponentIn(BaseModel):
    name: str = Field(..., description="Nombre del componente del status page")
    description: Optional[str] = Field(None, description="Descripción del componente")
    group_name: Optional[str] = Field(None, description="Grupo de agrupación del componente")
    sort_order: int = Field(0, description="Orden de visualización del componente")
    status: str = Field("operational", description="Estado actual del componente")
    is_public: bool = Field(True, description="Indica si es público en el status page")
    ci_id: Optional[str] = Field(None, description="ID del CI vinculado")


class StatusIncidentIn(BaseModel):
    title: str = Field(..., description="Título del incidente del status page")
    status: str = Field("investigating", description="Estado inicial del incidente")
    impact: str = Field("partial_outage", description="Impacto del incidente")
    update_message: Optional[str] = Field(None, description="Mensaje inicial del incidente")
    ticket_id: Optional[str] = Field(None, description="ID del ticket interno asociado")


class StatusIncidentUpdateIn(BaseModel):
    status: str = Field(..., description="Nuevo estado del incidente")
    message: str = Field(..., description="Mensaje de actualización para el público")


# ── Canned Responses ──────────────────────────────────────────────────────────

class CannedResponseIn(BaseModel):
    title: str = Field(..., description="Título de la respuesta predefinida")
    body: str = Field(..., description="Contenido de la respuesta predefinida")
    category: Optional[str] = Field(None, description="Categoría para agrupar las respuestas")
    shortcut: Optional[str] = Field(None, description="Atajo de teclado/slash para insertar la respuesta")
    is_active: bool = Field(True, description="Indica si la respuesta está disponible")


# ── On-Call Schedules ────────────────────────────────────────────────────────

class OnCallScheduleIn(BaseModel):
    name: str = Field(..., description="Nombre del calendario on-call")
    group_id: str = Field(..., description="ID del grupo de agentes al que aplica")
    rotation: str = Field("weekly", description="Periodicidad de la rotación (daily, weekly, monthly)")
    timezone: str = Field(settings.DEFAULT_TIMEZONE, description="Zona horaria del calendario")
    description: Optional[str] = Field(None, description="Descripción del calendario")


class OnCallEntryIn(BaseModel):
    user_id: str = Field(..., description="ID del usuario de guardia")
    start_dt: datetime = Field(..., description="Inicio del turno de guardia")
    end_dt: datetime = Field(..., description="Fin del turno de guardia")
    notes: Optional[str] = Field(None, description="Notas internas del turno")
