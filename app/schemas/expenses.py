from datetime import date
from typing import Optional

from pydantic import BaseModel, Field, field_validator

from app.core.config import settings


def _vacio_es_ninguno(v):
    """Un selector «Sin proyecto» envía "": es «ninguno», no un id (si no, la clave ajena da 500)."""
    return None if isinstance(v, str) and not v.strip() else v


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
    receipt_url: Optional[str] = Field(None, description="URL del justificante adjunto")
    status: Optional[str] = Field(None, description="Estado del gasto (draft, submitted, approved, rejected)")
    is_billable: Optional[bool] = Field(None, description="Indica si el gasto es facturable al cliente")

    _sin_vacios = field_validator("project_id", "contract_id", mode="before", check_fields=False)(_vacio_es_ninguno)


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

    _sin_vacios = field_validator("project_id", "contract_id", mode="before", check_fields=False)(_vacio_es_ninguno)


class ExpenseUpdate(BaseModel):
    category: Optional[str] = Field(None, description="Nueva categoría del gasto")
    description: Optional[str] = Field(None, description="Nueva descripción del gasto")
    amount: Optional[float] = Field(None, description="Nuevo importe del gasto")
    expense_date: Optional[date] = Field(None, description="Nueva fecha del gasto")
    is_billable: Optional[bool] = Field(None, description="Actualiza si es facturable al cliente")
    notes: Optional[str] = Field(None, description="Nuevas notas internas")
    km: Optional[float] = Field(None, gt=0, description="Kilómetros: con ellos el importe lo calcula el servidor")


class ExpenseReviewPayload(BaseModel):
    approved: bool = Field(..., description="Indica si el gasto se aprueba")
    rejection_reason: Optional[str] = Field(None, description="Motivo de rechazo en caso de no aprobar")
