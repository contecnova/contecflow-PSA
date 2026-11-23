from datetime import date
from typing import Optional

from pydantic import BaseModel, Field, field_validator

from app.core.config import settings
from app.schemas._enlaces import EnlaceSeguro  # auditoría 22-11-2026: solo http(s)


def _vacio_es_ninguno(v):
    """Un selector «Sin proyecto» envía "": es «ninguno», no un id (si no, la clave ajena da 500)."""
    return None if isinstance(v, str) and not v.strip() else v


def _pais_en_mayusculas(v):
    return v.upper() if isinstance(v, str) else v


class ExpenseIn(BaseModel):
    user_id: Optional[str] = Field(None, description="ID del usuario propietario del gasto")
    project_id: Optional[str] = Field(None, description="ID del proyecto al que se imputa el gasto")
    category: Optional[str] = Field(None, description="Categoría del gasto")
    amount: Optional[float] = Field(None, description="Importe del gasto")
    currency: Optional[str] = Field(None, description="Moneda en formato ISO 4217")
    expense_date: Optional[date] = Field(None, description="Fecha en la que se produjo el gasto")
    description: Optional[str] = Field(None, description="Descripción breve del gasto")
    notes: Optional[str] = Field(None, description="Notas internas adicionales")
    km: Optional[float] = Field(None, gt=0, description="Kilómetros: con ellos el importe lo calcula el servidor")
    country: Optional[str] = Field(None, min_length=2, max_length=2, pattern="^[A-Za-z]{2}$",
                                   description="País donde se hizo el gasto (ISO 3166-1 alfa-2)")
    city: Optional[str] = Field(None, max_length=120, description="Ciudad donde se hizo el gasto")
    attendees: Optional[int] = Field(None, ge=1, le=1000, description="Asistentes (comidas; incluye a quien paga)")
    trip: Optional[str] = Field(None, max_length=120, description="Viaje al que pertenece el gasto")
    receipt_url: EnlaceSeguro = Field(None, description="URL del justificante adjunto")
    status: Optional[str] = Field(None, description="Estado del gasto (draft, submitted, approved, rejected)")
    is_billable: Optional[bool] = Field(None, description="Indica si el gasto es facturable al cliente")

    _sin_vacios = field_validator("project_id", "contract_id", "country", "city", "trip", mode="before",
                                  check_fields=False)(_vacio_es_ninguno)
    _pais = field_validator("country", check_fields=False)(_pais_en_mayusculas)


class ExpenseCreate(BaseModel):
    project_id: Optional[str] = Field(None, description="ID del proyecto asociado al gasto")
    contract_id: Optional[str] = Field(None, description="ID del contrato asociado al gasto")
    category: str = Field(..., description="Categoría del gasto")
    description: str = Field(..., description="Descripción breve del gasto")
    amount: float = Field(..., description="Importe del gasto")
    currency: str = Field(settings.DEFAULT_CURRENCY, description="Moneda en formato ISO 4217")
    expense_date: date = Field(..., description="Fecha en la que se produjo el gasto")
    is_billable: bool = Field(True, description="Indica si el gasto es facturable al cliente")
    receipt_name: Optional[str] = Field(None, description="Nombre del archivo de justificante")
    notes: Optional[str] = Field(None, description="Notas internas adicionales")
    km: Optional[float] = Field(None, gt=0, description="Kilómetros: con ellos el importe lo calcula el servidor")
    country: Optional[str] = Field(None, min_length=2, max_length=2, pattern="^[A-Za-z]{2}$",
                                   description="País donde se hizo el gasto (ISO 3166-1 alfa-2)")
    city: Optional[str] = Field(None, max_length=120, description="Ciudad donde se hizo el gasto")
    attendees: Optional[int] = Field(None, ge=1, le=1000, description="Asistentes (comidas; incluye a quien paga)")
    trip: Optional[str] = Field(None, max_length=120, description="Viaje al que pertenece el gasto")

    _sin_vacios = field_validator("project_id", "contract_id", "country", "city", "trip", mode="before",
                                  check_fields=False)(_vacio_es_ninguno)
    _pais = field_validator("country", check_fields=False)(_pais_en_mayusculas)


class ExpenseUpdate(BaseModel):
    category: Optional[str] = Field(None, description="Nueva categoría del gasto")
    description: Optional[str] = Field(None, description="Nueva descripción del gasto")
    amount: Optional[float] = Field(None, description="Nuevo importe del gasto")
    expense_date: Optional[date] = Field(None, description="Nueva fecha del gasto")
    is_billable: Optional[bool] = Field(None, description="Actualiza si es facturable al cliente")
    notes: Optional[str] = Field(None, description="Nuevas notas internas")
    km: Optional[float] = Field(None, gt=0, description="Kilómetros: con ellos el importe lo calcula el servidor")
    country: Optional[str] = Field(None, min_length=2, max_length=2, pattern="^[A-Za-z]{2}$",
                                   description="País donde se hizo el gasto (ISO 3166-1 alfa-2)")
    city: Optional[str] = Field(None, max_length=120, description="Ciudad donde se hizo el gasto")
    attendees: Optional[int] = Field(None, ge=1, le=1000, description="Asistentes (comidas; incluye a quien paga)")
    trip: Optional[str] = Field(None, max_length=120, description="Viaje al que pertenece el gasto")

    _sin_vacios = field_validator("country", "city", "trip", mode="before")(_vacio_es_ninguno)
    _pais = field_validator("country")(_pais_en_mayusculas)


class ExpenseReviewPayload(BaseModel):
    approved: bool = Field(..., description="Indica si el gasto se aprueba")
    rejection_reason: Optional[str] = Field(None, description="Motivo de rechazo en caso de no aprobar")
