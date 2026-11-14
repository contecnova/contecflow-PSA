from typing import Optional, List
from pydantic import BaseModel, Field

class WikiSpaceIn(BaseModel):
    name: str = Field(..., description="Nombre del espacio wiki")
    slug: str = Field(..., description="Identificador corto único del espacio (slug)")
    description: Optional[str] = Field(default=None, description="Descripción del espacio wiki")
    project_id: Optional[str] = Field(default=None, description="ID del proyecto asociado al espacio")
    is_public: bool = Field(default=False, description="Indica si el espacio es público")

class WikiPageIn(BaseModel):
    title: str = Field(..., description="Título de la página wiki")
    slug: str = Field(..., description="Identificador corto único de la página (slug)")
    content: Optional[List] = Field(default=[], description="Contenido estructurado de la página")
    parent_id: Optional[str] = Field(default=None, description="ID de la página padre (jerarquía)")
    is_published: bool = Field(default=True, description="Indica si la página está publicada")
    sort_order: int = Field(default=0, description="Orden de la página dentro del listado")
    change_note: Optional[str] = Field(default=None, description="Nota describiendo el cambio realizado")

class WikiPageVisibilityIn(BaseModel):
    visibility: str = Field(..., pattern="^(team|portal|public)$",
                            description="Quien ve la pagina: team | portal | public")

class WikiTemplateIn(BaseModel):
    name: str = Field(..., description="Nombre de la plantilla wiki")
    description: Optional[str] = Field(default=None, description="Descripción de la plantilla")
    icon: Optional[str] = Field(default=None, description="Icono asociado a la plantilla")
    content: Optional[List] = Field(default=[], description="Contenido estructurado de la plantilla")

class WikiCommentIn(BaseModel):
    content: str = Field(..., description="Contenido del comentario")
    parent_id: Optional[str] = Field(default=None, description="ID del comentario padre (para respuestas)")

class EpicIn(BaseModel):
    title: str = Field(..., description="Título de la épica")
    description: Optional[str] = Field(default=None, description="Descripción de la épica")
    color: str = Field(default="#7c3aed", description="Color asociado a la épica (hex)")
    status: str = Field(default="open", description="Estado actual de la épica")
    priority: str = Field(default="medium", description="Prioridad de la épica")
    start_date: Optional[str] = Field(default=None, description="Fecha de inicio de la épica")
    end_date: Optional[str] = Field(default=None, description="Fecha de fin de la épica")
    sort_order: int = Field(default=0, description="Orden de la épica dentro del listado")

class NQLIn(BaseModel):
    entity_type: str = Field(..., description="Tipo de entidad sobre la que ejecutar la consulta NQL")
    query: str = Field(..., description="Consulta NQL a ejecutar")
    limit: int = Field(default=50, description="Número máximo de resultados a devolver")

class SavedFilterIn(BaseModel):
    name: str = Field(..., description="Nombre del filtro guardado")
    entity_type: str = Field(..., description="Tipo de entidad al que aplica el filtro")
    nql_query: str = Field(..., description="Consulta NQL asociada al filtro")
    is_shared: bool = Field(default=False, description="Indica si el filtro es compartido con otros usuarios")

class ThreadedCommentIn(BaseModel):
    content: str = Field(..., description="Contenido del comentario")
    parent_id: Optional[str] = Field(default=None, description="ID del comentario padre (para respuestas)")
