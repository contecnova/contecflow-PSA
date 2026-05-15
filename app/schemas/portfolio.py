from datetime import date
from typing import Optional

from pydantic import BaseModel, Field


class PortfolioIn(BaseModel):
    name: str = Field(..., description="Nombre del portfolio")
    description: Optional[str] = Field(None, description="Descripción del portfolio")
    status: Optional[str] = Field("active", description="Estado del portfolio (active, archived, etc.)")
    budget_total: Optional[float] = Field(None, description="Presupuesto total agregado del portfolio")
    start_date: Optional[date] = Field(None, description="Fecha de inicio del portfolio")
    end_date: Optional[date] = Field(None, description="Fecha de fin del portfolio")


class PortfolioProjectIn(BaseModel):
    project_id: str = Field(..., description="ID del proyecto incluido en el portfolio")
    rag_override: Optional[str] = Field(None, description="Override manual del estado RAG del proyecto")
    display_order: Optional[float] = Field(0.0, description="Orden de visualización dentro del portfolio")
