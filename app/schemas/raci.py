from typing import Optional, List, Literal
from datetime import date
from pydantic import BaseModel, Field

class RACIEntryIn(BaseModel):
    item_type: str = Field(..., description="Tipo de elemento RACI (task, milestone, deliverable, etc.)")
    item_label: str = Field(..., description="Etiqueta visible del elemento RACI")
    item_id: Optional[str] = Field(None, description="ID del elemento vinculado si existe")
    user_id: str = Field(..., description="ID del usuario asignado al rol")
    role: Literal["R", "A", "C", "I"] = Field(..., description="Rol RACI: R (Responsible), A (Accountable), C (Consulted), I (Informed)")

class RACIBatchIn(BaseModel):
    entries: List[RACIEntryIn] = Field(..., description="Lista de entradas RACI a crear o actualizar en lote")

class RetroNotesIn(BaseModel):
    manual_notes: Optional[str] = Field(None, description="Notas manuales de la retrospectiva")
    action_items: Optional[List[dict]] = Field(None, description="Acciones derivadas con texto y responsable")

class ChangelogEntryIn(BaseModel):
    version_tag: Optional[str] = Field(None, description="Etiqueta de versión asociada a la entrada")
    entry_date: date = Field(..., description="Fecha de la entrada en el changelog")
    entry_type: str = Field("feature", description="Tipo de entrada (feature, bugfix, improvement, milestone, breaking)")
    title: str = Field(..., description="Título de la entrada del changelog")
    description: Optional[str] = Field(None, description="Descripción detallada del cambio")

class ChangelogEntryPatch(BaseModel):
    version_tag: Optional[str] = Field(None, description="Nueva etiqueta de versión")
    entry_date: Optional[date] = Field(None, description="Nueva fecha de la entrada")
    entry_type: Optional[str] = Field(None, description="Nuevo tipo de entrada")
    title: Optional[str] = Field(None, description="Nuevo título de la entrada")
    description: Optional[str] = Field(None, description="Nueva descripción del cambio")

class UATCaseIn(BaseModel):
    title: str = Field(..., description="Título del caso de prueba UAT")
    description: Optional[str] = Field(None, description="Descripción del caso de prueba")
    expected_result: Optional[str] = Field(None, description="Resultado esperado del caso")
    actual_result: Optional[str] = Field(None, description="Resultado obtenido al ejecutar el caso")
    status: Optional[str] = Field("pending", description="Estado del caso (pending, passed, failed, blocked)")
    priority: Optional[str] = Field("medium", description="Prioridad del caso (low, medium, high, critical)")
    task_id: Optional[str] = Field(None, description="ID de la tarea relacionada")
    assigned_to_id: Optional[str] = Field(None, description="ID del usuario asignado al caso")
    notes: Optional[str] = Field(None, description="Notas adicionales del caso")
