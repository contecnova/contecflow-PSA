from typing import Optional, List
from datetime import date, datetime
from pydantic import BaseModel, Field, field_validator
from app.core.config import settings

class PermissionCreate(BaseModel):
    user_id: str = Field(..., description="ID del usuario al que se otorga el permiso")
    level: str = Field("member", description="Nivel de permiso (none, viewer, member, manager, owner)")
    can_see_financials: bool = Field(False, description="Permiso para ver datos financieros")
    can_see_rates: bool = Field(False, description="Permiso para ver tarifas")
    can_export: bool = Field(True, description="Permiso para exportar datos")
    expires_at: Optional[datetime] = Field(None, description="Fecha de expiración del permiso")
    note: Optional[str] = Field(None, description="Nota explicativa del permiso concedido")

class PermissionUpdate(BaseModel):
    level: Optional[str] = Field(None, description="Nuevo nivel de permiso")
    can_see_financials: Optional[bool] = Field(None, description="Actualiza el permiso para ver financieros")
    can_see_rates: Optional[bool] = Field(None, description="Actualiza el permiso para ver tarifas")
    can_export: Optional[bool] = Field(None, description="Actualiza el permiso de exportación")
    expires_at: Optional[datetime] = Field(None, description="Nueva fecha de expiración")
    note: Optional[str] = Field(None, description="Nueva nota explicativa")

class WebhookCreate(BaseModel):
    name: str = Field(..., description="Nombre descriptivo del webhook")
    url: str = Field(..., description="URL HTTPS destino del webhook")
    secret: Optional[str] = Field(None, description="Secreto compartido para firmar las peticiones")
    events: List[str] = Field(..., description="Lista de eventos a los que se suscribe")
    project_id: Optional[str] = Field(None, description="ID del proyecto si el webhook es específico")

class WebhookUpdate(BaseModel):
    name: Optional[str] = Field(None, description="Nuevo nombre del webhook")
    url: Optional[str] = Field(None, description="Nueva URL destino")
    secret: Optional[str] = Field(None, description="Nuevo secreto compartido")
    events: Optional[List[str]] = Field(None, description="Nueva lista de eventos suscritos")
    is_active: Optional[bool] = Field(None, description="Activa o desactiva el webhook")

class SSOCreate(BaseModel):
    provider: str = Field(..., description="Proveedor SSO (saml, oidc, etc.)")
    organization_id: Optional[str] = Field(None, description="ID de la organización a la que se asocia")
    saml_entity_id: Optional[str] = Field(None, description="Entity ID SAML del proveedor")
    saml_sso_url: Optional[str] = Field(None, description="URL HTTPS de Single Sign-On SAML")
    saml_slo_url: Optional[str] = Field(None, description="URL HTTPS de Single Logout SAML")
    saml_certificate: Optional[str] = Field(None, description="Certificado X509 del IdP en PEM")
    saml_attribute_email: str = Field("email", description="Atributo SAML que contiene el email")
    saml_attribute_name: str = Field("displayName", description="Atributo SAML que contiene el nombre")
    saml_attribute_role: Optional[str] = Field(None, description="Atributo SAML que contiene el rol")
    oidc_client_id: Optional[str] = Field(None, description="Client ID OIDC")
    oidc_client_secret: Optional[str] = Field(None, description="Client Secret OIDC")
    oidc_discovery_url: Optional[str] = Field(None, description="URL HTTPS de discovery OIDC")
    oidc_scopes: str = Field("openid email profile", description="Scopes OIDC solicitados")
    role_mapping: Optional[dict] = Field(None, description="Mapping entre roles del IdP y roles internos")
    auto_create_users: bool = Field(True, description="Crea usuarios automáticamente en el primer login")
    default_role: str = Field("employee", description="Rol por defecto asignado a usuarios nuevos")
    allowed_domains: Optional[str] = Field(None, description="Lista separada por comas de dominios permitidos")

    @field_validator("oidc_discovery_url", "saml_sso_url", "saml_slo_url", mode="before")
    @classmethod
    def _require_https(cls, v: Optional[str]) -> Optional[str]:
        if v and not v.startswith("https://"):
            raise ValueError("Solo se permiten URLs HTTPS para configuraciones SSO/OIDC")
        return v

class SSOUpdate(SSOCreate):
    is_active: Optional[bool] = Field(None, description="Activa o desactiva la configuración SSO")
    is_default: Optional[bool] = Field(None, description="Marca esta configuración como la predeterminada")

class SubCreate(BaseModel):
    name: str = Field(..., description="Nombre del subcontratista")
    company: Optional[str] = Field(None, description="Nombre de la empresa del subcontratista")
    email: Optional[str] = Field(None, description="Email de contacto del subcontratista")
    phone: Optional[str] = Field(None, description="Teléfono de contacto")
    country: Optional[str] = Field(None, description="País del subcontratista")
    vat_number: Optional[str] = Field(None, description="Número de IVA o NIF fiscal")
    currency: str = Field(settings.DEFAULT_CURRENCY, description="Moneda por defecto del subcontratista")
    notes: Optional[str] = Field(None, description="Notas internas sobre el subcontratista")

class SubUpdate(SubCreate):
    is_active: Optional[bool] = Field(None, description="Activa o desactiva el subcontratista")
    name: Optional[str] = Field(None, description="Nuevo nombre del subcontratista")

class RateCreate(BaseModel):
    description: str = Field(..., description="Descripción de la tarifa")
    cost_rate: float = Field(..., description="Coste por hora del recurso")
    sell_rate: Optional[float] = Field(None, description="Tarifa de venta por hora")
    currency: str = Field(settings.DEFAULT_CURRENCY, description="Moneda de las tarifas")
    valid_from: Optional[date] = Field(None, description="Fecha desde la que aplica la tarifa")
    valid_until: Optional[date] = Field(None, description="Fecha hasta la que aplica la tarifa")

class AssignmentCreate(BaseModel):
    project_id: str = Field(..., description="ID del proyecto al que se asigna")
    worker_id: Optional[str] = Field(None, description="ID del recurso asignado")
    rate_id: Optional[str] = Field(None, description="ID de la tarifa aplicada")
    po_number: Optional[str] = Field(None, description="Número de orden de compra asociada")
    po_amount: Optional[float] = Field(None, description="Importe de la orden de compra")
    hours_contracted: Optional[float] = Field(None, description="Horas contratadas en la asignación")
    start_date: Optional[date] = Field(None, description="Fecha de inicio de la asignación")
    end_date: Optional[date] = Field(None, description="Fecha de fin de la asignación")
    notes: Optional[str] = Field(None, description="Notas internas de la asignación")

class WorkerCreate(BaseModel):
    name: str = Field(..., description="Nombre del recurso externo")
    role: Optional[str] = Field(None, description="Rol o cargo del recurso")
    email: Optional[str] = Field(None, description="Email de contacto del recurso")
    phone: Optional[str] = Field(None, description="Teléfono de contacto")
    cost_rate: Optional[float] = Field(None, description="Coste por hora del recurso")
    sell_rate: Optional[float] = Field(None, description="Tarifa de venta por hora")
    currency: str = Field(settings.DEFAULT_CURRENCY, description="Moneda de las tarifas")
    available_from: Optional[date] = Field(None, description="Fecha desde la que está disponible")
    available_until: Optional[date] = Field(None, description="Fecha hasta la que está disponible")
    weekly_capacity_hours: Optional[float] = Field(None, description="Horas semanales de capacidad")
    notes: Optional[str] = Field(None, description="Notas internas sobre el recurso")

class WorkerUpdate(BaseModel):
    name: Optional[str] = Field(None, description="Nuevo nombre del recurso")
    role: Optional[str] = Field(None, description="Nuevo rol o cargo")
    email: Optional[str] = Field(None, description="Nuevo email de contacto")
    phone: Optional[str] = Field(None, description="Nuevo teléfono")
    cost_rate: Optional[float] = Field(None, description="Nuevo coste por hora")
    sell_rate: Optional[float] = Field(None, description="Nueva tarifa de venta por hora")
    currency: Optional[str] = Field(None, description="Nueva moneda")
    available_from: Optional[date] = Field(None, description="Nueva fecha de inicio de disponibilidad")
    available_until: Optional[date] = Field(None, description="Nueva fecha de fin de disponibilidad")
    weekly_capacity_hours: Optional[float] = Field(None, description="Nueva capacidad semanal en horas")
    is_active: Optional[bool] = Field(None, description="Activa o desactiva el recurso")
    notes: Optional[str] = Field(None, description="Nuevas notas internas")

class WorkerSkillCreate(BaseModel):
    skill_id: str = Field(..., description="ID de la skill asignada al recurso")
    level: str = Field("intermediate", description="Nivel de dominio (beginner, intermediate, advanced, expert)")
    years_experience: Optional[float] = Field(None, description="Años de experiencia con la skill")
    certified: bool = Field(False, description="Indica si el recurso está certificado")
    cert_name: Optional[str] = Field(None, description="Nombre de la certificación")
    notes: Optional[str] = Field(None, description="Notas sobre la skill")

class ForecastUpdate(BaseModel):
    revenue_planned: Optional[float] = Field(None, description="Ingresos planificados del periodo")
    revenue_actual: Optional[float] = Field(None, description="Ingresos reales del periodo")
    revenue_forecast: Optional[float] = Field(None, description="Ingresos previstos del periodo")
    cost_planned: Optional[float] = Field(None, description="Costes planificados del periodo")
    cost_actual: Optional[float] = Field(None, description="Costes reales del periodo")
    hours_planned: Optional[float] = Field(None, description="Horas planificadas del periodo")
    hours_actual: Optional[float] = Field(None, description="Horas reales imputadas del periodo")
    notes: Optional[str] = Field(None, description="Notas sobre la actualización del forecast")
