from datetime import date
from typing import Literal, Optional

from pydantic import BaseModel, Field


class OpportunityIn(BaseModel):
    name: str = Field(..., description="Nombre de la oportunidad")
    client_name: str = Field(..., description="Nombre del cliente potencial")
    stage: str = Field("lead", description="Etapa actual del pipeline")
    probability: float = Field(50, description="Probabilidad estimada de cierre (0-100)")
    expected_revenue: Optional[float] = Field(None, description="Ingresos esperados de la oportunidad")
    expected_margin_pct: Optional[float] = Field(None, description="Margen esperado en porcentaje")
    expected_hours: Optional[float] = Field(None, description="Horas estimadas de ejecución")
    expected_close_date: Optional[date] = Field(None, description="Fecha estimada de cierre")
    expected_start_date: Optional[date] = Field(None, description="Fecha estimada de inicio")
    expected_duration_weeks: Optional[int] = Field(None, description="Duración estimada en semanas")
    description: Optional[str] = Field(None, description="Descripción del alcance de la oportunidad")
    contact_name: Optional[str] = Field(None, description="Nombre del contacto principal")
    contact_email: Optional[str] = Field(None, description="Email del contacto principal")
    owner_id: Optional[str] = Field(None, description="ID del usuario propietario de la oportunidad")
    notes: Optional[str] = Field(None, description="Notas internas sobre la oportunidad")
    # Revisión 2026-11: lo que la conversión lleva al proyecto y al contrato de ingresos.
    client_id: Optional[str] = Field(None, description="Cliente existente (el proyecto convertido queda vinculado)")
    hourly_rate: Optional[float] = Field(None, ge=0, description="Tarifa de facturación por hora")
    contract_type: Optional[Literal["fixed_price", "time_material", "retainer", "hourly_bag"]] = Field(
        None, description="Tipo de contrato (decide el método de reconocimiento de ingresos al convertir)")


class OpportunityUpdate(OpportunityIn):
    name: Optional[str] = Field(None, description="Nuevo nombre de la oportunidad")
    client_name: Optional[str] = Field(None, description="Nuevo nombre del cliente")
    lost_reason: Optional[str] = Field(None, description="Motivo de pérdida si se cierra como perdida")
    project_id: Optional[str] = Field(None, description="ID del proyecto generado al ganar la oportunidad")


class PipelineActivityIn(BaseModel):
    type: str = Field("note", description="Tipo de actividad (note, call, email, meeting)")
    content: str = Field(..., description="Contenido textual de la actividad")


class StageConfigIn(BaseModel):
    stage_key: str = Field(..., description="Clave técnica de la etapa")
    label: str = Field(..., description="Etiqueta visible de la etapa")
    description: Optional[str] = Field(None, description="Descripción detallada de la etapa")
    color: str = Field("#6B7280", description="Color asociado a la etapa en hexadecimal")
    order: int = Field(0, description="Orden de visualización en el pipeline")
    probability_default: float = Field(50, description="Probabilidad por defecto al entrar en la etapa")
    is_terminal: bool = Field(False, description="Indica si es una etapa final del pipeline")
    is_won: bool = Field(False, description="Indica si la etapa representa una victoria")
