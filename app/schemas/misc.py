from datetime import date
from typing import List, Optional

from pydantic import BaseModel, Field


class ExportRequest(BaseModel):
    project_ids: Optional[List[str]] = Field(None, description="Lista de IDs de proyectos a exportar")
    user_ids: Optional[List[str]] = Field(None, description="Lista de IDs de usuarios a exportar")
    date_from: Optional[date] = Field(None, description="Fecha desde la que filtrar los datos")
    date_to: Optional[date] = Field(None, description="Fecha hasta la que filtrar los datos")
    include_costs: bool = Field(False, description="Indica si se incluyen costes en la exportación")
    format: str = Field("xlsx", description="Formato de la exportación (xlsx, csv, json)")


class PaginatedResponse(BaseModel):
    items: list = Field(..., description="Lista de elementos de la página actual")
    total: int = Field(..., description="Total de elementos disponibles")
    page: int = Field(..., description="Número de página actual")
    page_size: int = Field(..., description="Tamaño de página solicitado")
    pages: int = Field(..., description="Número total de páginas")
