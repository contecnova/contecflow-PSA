from typing import Optional
from pydantic import BaseModel, Field

class PolicyPackUpsert(BaseModel):
    is_enabled: bool = Field(True, description="Indica si el pack de políticas está activo")
    pack_version: str = Field("1.0", description="Versión del pack de políticas")
    config: Optional[dict] = Field(None, description="Configuración específica del pack de políticas")

class EvidenceCreate(BaseModel):
    framework: str = Field(..., description="Framework de cumplimiento al que pertenece (ISO27001, SOC2, etc.)")
    control_id: str = Field(..., description="Identificador del control dentro del framework")
    evidence_type: str = Field(..., description="Tipo de evidencia (documento, log, captura, etc.)")
    title: str = Field(..., description="Título descriptivo de la evidencia")
    description: Optional[str] = Field(None, description="Descripción detallada de la evidencia")
    artifact_uri: Optional[str] = Field(None, description="URI del artefacto que respalda la evidencia")
    metadata: Optional[dict] = Field(None, description="Metadatos adicionales asociados a la evidencia")
