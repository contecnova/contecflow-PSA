from datetime import datetime
from typing import Optional

from pydantic import BaseModel, EmailStr, Field

from app.schemas.common_enums import UserStatus
from app.core.config import settings


class UserBase(BaseModel):
    username: str = Field(..., description="Nombre de usuario único")
    email: EmailStr = Field(..., description="Correo electrónico del usuario")
    full_name: str = Field(..., description="Nombre completo del usuario")
    first_name: Optional[str] = Field(default=None, description="Nombre del usuario")
    last_name: Optional[str] = Field(default=None, description="Apellidos del usuario")
    department: Optional[str] = Field(default=None, description="Departamento al que pertenece el usuario")
    job_title: Optional[str] = Field(default=None, description="Cargo o puesto del usuario")
    role: str = Field(default="employee", description="Rol del usuario en el sistema")
    status: UserStatus = Field(default=UserStatus.active, description="Estado del usuario")
    weekly_capacity_hours: float = Field(default=settings.DEFAULT_WEEKLY_CAPACITY_HOURS, description="Capacidad semanal en horas")
    organization_id: Optional[str] = Field(default=None, description="ID de la organización principal del usuario")
    organization_ids: Optional[list[str]] = Field(default=None, description="IDs de organizaciones a las que pertenece el usuario")


class UserCreate(UserBase):
    password: Optional[str] = Field(default=None, description="Contraseña del usuario (opcional para usuarios LDAP)")
    # Auditoria 2026-11: el formulario de alta los mandaba y pydantic los descartaba.
    # El alta es solo de administradores (`require_admin` en el endpoint).
    hourly_rate: Optional[float] = Field(default=None, ge=0, description="Tarifa horaria del usuario (solo admin)")
    timezone: Optional[str] = Field(default=None, max_length=50, description="Zona horaria del usuario")
    custom_role_id: Optional[str] = Field(default=None, description="Rol personalizado (restringe modulos)")


class UserUpdate(BaseModel):
    email: Optional[EmailStr] = Field(default=None, description="Correo electrónico del usuario")
    full_name: Optional[str] = Field(default=None, description="Nombre completo del usuario")
    first_name: Optional[str] = Field(default=None, description="Nombre del usuario")
    last_name: Optional[str] = Field(default=None, description="Apellidos del usuario")
    department: Optional[str] = Field(default=None, description="Departamento al que pertenece el usuario")
    job_title: Optional[str] = Field(default=None, description="Cargo o puesto del usuario")
    role: Optional[str] = Field(default=None, description="Rol del usuario en el sistema")
    status: Optional[UserStatus] = Field(default=None, description="Estado del usuario")
    weekly_capacity_hours: Optional[float] = Field(default=None, description="Capacidad semanal en horas")
    hourly_rate: Optional[float] = Field(default=None, description="Tarifa horaria del usuario (solo admin)")
    phone: Optional[str] = Field(default=None, description="Teléfono de contacto del usuario")
    avatar_url: Optional[str] = Field(default=None, description="URL del avatar del usuario")
    manager_id: Optional[str] = Field(default=None, description="ID del manager del usuario")
    timezone: Optional[str] = Field(default=None, description="Zona horaria del usuario")
    organization_id: Optional[str] = Field(default=None, description="ID de la organización principal del usuario")
    organization_ids: Optional[list[str]] = Field(default=None, description="IDs de organizaciones a las que pertenece el usuario")
    custom_role_id: Optional[str] = Field(default=None, description="Rol personalizado (restringe modulos); vacio para quitarlo")


class UserSelfUpdate(BaseModel):
    """Campos que el propio usuario puede editar (sin privilegios)."""

    email: Optional[EmailStr] = Field(default=None, description="Correo electrónico del usuario")
    first_name: Optional[str] = Field(default=None, description="Nombre del usuario")
    last_name: Optional[str] = Field(default=None, description="Apellidos del usuario")
    full_name: Optional[str] = Field(default=None, description="Nombre completo del usuario")
    phone: Optional[str] = Field(default=None, description="Teléfono de contacto del usuario")
    job_title: Optional[str] = Field(default=None, description="Cargo o puesto del usuario")
    avatar_url: Optional[str] = Field(default=None, description="URL del avatar del usuario")
    timezone: Optional[str] = Field(default=None, description="Zona horaria del usuario")


class UserOrganizationOut(BaseModel):
    id: str = Field(..., description="Identificador de la organización")
    name: Optional[str] = Field(default=None, description="Nombre de la organización")
    slug: Optional[str] = Field(default=None, description="Identificador corto único de la organización (slug)")

    class Config:
        from_attributes = True


class UserPublic(UserBase):
    id: str = Field(..., description="Identificador del usuario")
    is_active: bool = Field(default=True, description="Indica si el usuario está activo")
    avatar_url: Optional[str] = Field(default=None, description="URL del avatar del usuario")
    last_login: Optional[datetime] = Field(default=None, description="Fecha y hora del último inicio de sesión")
    created_at: datetime = Field(..., description="Fecha y hora de creación del usuario")
    manager_id: Optional[str] = Field(default=None, description="ID del manager del usuario")
    manager_name: Optional[str] = Field(default=None, description="Nombre del manager del usuario")
    phone: Optional[str] = Field(default=None, description="Teléfono de contacto del usuario")
    organizations: Optional[list[UserOrganizationOut]] = Field(default=None, description="Organizaciones a las que pertenece el usuario")
    custom_role_id: Optional[str] = Field(default=None, description="Rol personalizado asignado")
    # Auditoria 2026-11: la ficha de Ajustes > Usuarios la edita y el listado no la mandaba.
    timezone: Optional[str] = Field(default=None, description="Zona horaria del usuario")
    # Auditoria 2026-11: el panel de perfil lo leia para ocultar el cambio de
    # contrasena a quien entra por SSO, y no venia nunca.
    sso_provider: Optional[str] = Field(default=None, description="Proveedor SSO con el que entra, si lo hay")
    blocked_routes: list[str] = Field(default_factory=list, description="Rutas de pantalla cerradas por el rol (solo en /auth/me y el login)")
    impersonated_by: Optional[str] = Field(default=None, description="Correo del superadmin que ha entrado como este usuario («entrar como»)")

    class Config:
        from_attributes = True


class UserWithRate(UserPublic):
    """Extended view for admin/hr — includes confidential rate."""

    hourly_rate: Optional[float] = Field(default=None, description="Tarifa horaria del usuario (confidencial)")
    ldap_dn: Optional[str] = Field(default=None, description="Distinguished Name (DN) del usuario en LDAP")


class UserLoad(BaseModel):
    user: UserPublic = Field(..., description="Información pública del usuario")
    current_load_pct: float = Field(..., description="Porcentaje de carga actual del usuario")
    hours_this_week: float = Field(..., description="Horas registradas en la semana actual")
    hours_this_month: float = Field(..., description="Horas registradas en el mes actual")
    active_tasks: int = Field(..., description="Número de tareas activas del usuario")
    active_projects: int = Field(..., description="Número de proyectos activos del usuario")
    hourly_rate: Optional[float] = Field(default=None, description="Tarifa horaria del usuario (solo admin/hr)")
