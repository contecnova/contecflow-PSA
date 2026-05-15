from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


class AutomationRuleCreate(BaseModel):
    name: str = Field(..., description="Nombre identificativo de la regla de automatización")
    description: Optional[str] = Field(None, description="Descripción detallada de la regla")
    project_id: Optional[str] = Field(None, description="ID del proyecto al que aplica la regla (None si es global)")
    is_global: bool = Field(False, description="Indica si la regla aplica a toda la organización")
    trigger_type: str = Field(..., description="Tipo de evento que dispara la regla")
    trigger_conditions: Optional[Dict[str, Any]] = Field(None, description="Condiciones adicionales a cumplir para activar la regla")
    actions: List[Dict[str, Any]] = Field(..., description="Lista ordenada de acciones a ejecutar cuando se dispara la regla")


class AutomationRuleUpdate(BaseModel):
    name: Optional[str] = Field(None, description="Nuevo nombre de la regla")
    description: Optional[str] = Field(None, description="Nueva descripción de la regla")
    is_active: Optional[bool] = Field(None, description="Activa o desactiva la regla")
    trigger_type: Optional[str] = Field(None, description="Nuevo tipo de trigger")
    trigger_conditions: Optional[Dict[str, Any]] = Field(None, description="Nuevas condiciones del trigger")
    actions: Optional[List[Dict[str, Any]]] = Field(None, description="Nueva lista de acciones")
