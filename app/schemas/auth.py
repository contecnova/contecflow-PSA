from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel, Field

from app.schemas.users import UserPublic


class LoginRequest(BaseModel):
    username: str = Field(..., description="Nombre de usuario o correo electrónico para iniciar sesión")
    password: str = Field(..., description="Contraseña del usuario")


class TokenResponse(BaseModel):
    access_token: Optional[str] = Field(default=None, description="Token JWT de acceso")
    refresh_token: Optional[str] = Field(default=None, description="Token JWT de refresco")
    token_type: str = Field(default="bearer", description="Tipo de token de autenticación")
    user: UserPublic = Field(..., description="Información pública del usuario autenticado")
    mfa_required: bool = Field(default=False, description="Indica si se requiere autenticación multifactor")
    mfa_challenge_token: Optional[str] = Field(default=None, description="Token de desafío para completar el flujo MFA")
    mfa_methods: Optional[list[str]] = Field(default=None, description="Métodos MFA disponibles para el usuario")


class RefreshRequest(BaseModel):
    refresh_token: str = Field(..., description="Token JWT de refresco a utilizar para obtener un nuevo access token")


class PasswordForgotRequest(BaseModel):
    email_or_username: str = Field(..., description="Correo electrónico o nombre de usuario para recuperar la contraseña")


class PasswordResetRequest(BaseModel):
    token: str = Field(..., description="Token de restablecimiento de contraseña recibido")
    new_password: str = Field(..., description="Nueva contraseña a establecer")


class ActiveSessionOut(BaseModel):
    id: str = Field(..., description="Identificador de la sesión activa")
    ip_address: Optional[str] = Field(default=None, description="Dirección IP desde la que se inició la sesión")
    ip_asn: Optional[str] = Field(default=None, description="ASN asociado a la dirección IP")
    ip_org: Optional[str] = Field(default=None, description="Organización asociada a la dirección IP")
    country_code: Optional[str] = Field(default=None, description="Código del país de origen de la sesión")
    region: Optional[str] = Field(default=None, description="Región geográfica de origen de la sesión")
    city: Optional[str] = Field(default=None, description="Ciudad de origen de la sesión")
    user_agent: Optional[str] = Field(default=None, description="User-Agent del cliente que inició la sesión")
    device_name: Optional[str] = Field(default=None, description="Nombre del dispositivo asociado a la sesión")
    risk_score: int = Field(default=0, description="Puntuación de riesgo calculada para la sesión")
    risk_level: str = Field(default="low", description="Nivel de riesgo categorizado de la sesión")
    risk_reasons: List[str] = Field(default_factory=list, description="Motivos asociados al riesgo de la sesión")
    auth_method: Optional[str] = Field(default=None, description="Método de autenticación utilizado")
    last_seen_at: Optional[datetime] = Field(default=None, description="Última actividad detectada en la sesión")
    expires_at: datetime = Field(..., description="Fecha y hora de expiración de la sesión")
    created_at: Optional[datetime] = Field(default=None, description="Fecha y hora de creación de la sesión")
    is_current: bool = Field(default=False, description="Indica si es la sesión actual del usuario")
