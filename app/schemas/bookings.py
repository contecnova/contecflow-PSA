from datetime import date, datetime
from typing import List, Optional

from pydantic import BaseModel, Field

from app.core.config import settings


class DependencyCreate(BaseModel):
    predecessor_id: str = Field(..., description="ID de la tarea predecesora")
    successor_id: str = Field(..., description="ID de la tarea sucesora")
    dependency_type: str = Field("FS", description="Tipo de dependencia (FS, SS, FF, SF)")
    lag_days: int = Field(0, description="Días de desfase entre predecesora y sucesora")


class BookingCreate(BaseModel):
    user_id: str = Field(..., description="ID del usuario reservado")
    project_id: Optional[str] = Field(None, description="ID del proyecto al que se asigna la reserva")
    task_id: Optional[str] = Field(None, description="ID de la tarea concreta de la reserva")
    booking_type: str = Field("hard", description="Tipo de reserva (hard, soft, tentative)")
    start_date: date = Field(..., description="Fecha de inicio de la reserva")
    end_date: date = Field(..., description="Fecha de fin de la reserva")
    hours_per_day: float = Field(settings.DEFAULT_WORKING_HOURS_PER_DAY, description="Horas reservadas por día")
    note: Optional[str] = Field(None, description="Nota explicativa sobre la reserva")


class BookingUpdate(BaseModel):
    start_date: Optional[date] = Field(None, description="Nueva fecha de inicio")
    end_date: Optional[date] = Field(None, description="Nueva fecha de fin")
    hours_per_day: Optional[float] = Field(None, description="Nuevas horas diarias reservadas")
    project_id: Optional[str] = Field(None, description="Nuevo proyecto asociado")
    task_id: Optional[str] = Field(None, description="Nueva tarea asociada")
    booking_type: Optional[str] = Field(None, description="Nuevo tipo de reserva")
    note: Optional[str] = Field(None, description="Nueva nota de la reserva")


class SLAScheduleCreate(BaseModel):
    name: str = Field(..., description="Nombre del calendario SLA")
    timezone: str = Field(settings.DEFAULT_TIMEZONE, description="Zona horaria del calendario")
    is_default: bool = Field(False, description="Indica si es el calendario por defecto de la organización")
    work_days: List[int] = Field([1, 2, 3, 4, 5], description="Días laborables (1=lunes, 7=domingo)")
    work_start: Optional[str] = Field("09:00", description="Hora de inicio de la jornada (HH:MM)")
    work_end: Optional[str] = Field("17:00", description="Hora de fin de la jornada (HH:MM)")


class ApiKeyCreate(BaseModel):
    name: str = Field(..., description="Nombre descriptivo de la API key")
    scopes: List[str] = Field(["read"], description="Lista de scopes/permisos concedidos a la clave")
    rate_limit_per_hour: int = Field(1000, description="Límite máximo de peticiones por hora")
    rate_limit_per_day: int = Field(10000, description="Límite máximo de peticiones por día")
    expires_at: Optional[datetime] = Field(None, description="Fecha de expiración de la clave")


class RecurringCreate(BaseModel):
    name: str = Field(..., description="Nombre de la facturación recurrente")
    project_id: Optional[str] = Field(None, description="ID del proyecto asociado")
    contract_id: Optional[str] = Field(None, description="ID del contrato asociado")
    frequency: str = Field("monthly", description="Frecuencia (weekly, monthly, quarterly, yearly)")
    next_date: date = Field(..., description="Próxima fecha de emisión")
    end_date: Optional[date] = Field(None, description="Fecha de fin de la recurrencia")
    client_name: Optional[str] = Field(None, description="Nombre del cliente facturado")
    client_email: Optional[str] = Field(None, description="Email del cliente para envío")
    client_vat: Optional[str] = Field(None, description="NIF/VAT del cliente")
    amount: float = Field(..., description="Importe a facturar antes de impuestos")
    tax_rate: float = Field(settings.DEFAULT_TAX_RATE, description="Tipo impositivo aplicado")
    currency: str = Field(settings.DEFAULT_CURRENCY, description="Moneda en formato ISO 4217")
    description: Optional[str] = Field(None, description="Descripción del concepto facturado")
    payment_terms_days: int = Field(30, description="Plazo de pago en días")
