from datetime import date
from typing import Optional

from pydantic import BaseModel, Field


class ContractIn(BaseModel):
    name: str = Field(..., description="Nombre del contrato")
    project_id: str = Field(..., description="ID del proyecto asociado al contrato")
    client_name: str = Field(..., description="Nombre del cliente")
    contract_type: str = Field(..., description="Tipo de contrato (fixed, time_material, retainer...)")
    total_amount: Optional[float] = Field(default=None, description="Importe total del contrato en euros")
    hourly_rate: Optional[float] = Field(default=None, description="Tarifa horaria aplicada en el contrato")
    hours_bag: Optional[float] = Field(default=None, description="Bolsa de horas contratadas")
    monthly_retainer: Optional[float] = Field(default=None, description="Cuota mensual del retainer en euros")
    start_date: Optional[date] = Field(default=None, description="Fecha de inicio del contrato")
    end_date: Optional[date] = Field(default=None, description="Fecha de fin del contrato")
    signed_date: Optional[date] = Field(default=None, description="Fecha de firma del contrato")
    client_contact: Optional[str] = Field(default=None, description="Persona de contacto del cliente")
    payment_terms: Optional[str] = Field(default=None, description="Condiciones de pago acordadas")
    notes: Optional[str] = Field(default=None, description="Notas internas sobre el contrato")


class ContractUpdate(BaseModel):
    name: Optional[str] = Field(default=None, description="Nombre del contrato")
    status: Optional[str] = Field(default=None, description="Estado del contrato")
    total_amount: Optional[float] = Field(default=None, description="Importe total del contrato en euros")
    hourly_rate: Optional[float] = Field(default=None, description="Tarifa horaria aplicada en el contrato")
    hours_bag: Optional[float] = Field(default=None, description="Bolsa de horas contratadas")
    monthly_retainer: Optional[float] = Field(default=None, description="Cuota mensual del retainer en euros")
    end_date: Optional[date] = Field(default=None, description="Fecha de fin del contrato")
    signed_date: Optional[date] = Field(default=None, description="Fecha de firma del contrato")
    payment_terms: Optional[str] = Field(default=None, description="Condiciones de pago acordadas")
    notes: Optional[str] = Field(default=None, description="Notas internas sobre el contrato")


class WorkOrderIn(BaseModel):
    name: str = Field(..., description="Nombre de la orden de trabajo")
    amount: Optional[float] = Field(default=None, description="Importe de la orden de trabajo en euros")
    hours: Optional[float] = Field(default=None, description="Horas estimadas de la orden de trabajo")
    start_date: Optional[date] = Field(default=None, description="Fecha de inicio de la orden de trabajo")
    end_date: Optional[date] = Field(default=None, description="Fecha de fin de la orden de trabajo")
    description: Optional[str] = Field(default=None, description="Descripción detallada del trabajo")
