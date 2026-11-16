from typing import Literal, Optional
from pydantic import BaseModel, Field


class PolicyPackUpsert(BaseModel):
    is_enabled: bool = Field(True, description="Indica si el pack de políticas está activo")
    pack_version: str = Field("1.0", max_length=20, description="Versión del pack de políticas")
    config: Optional[dict] = Field(None, description="Configuración específica del pack de políticas")


class EvidenceCreate(BaseModel):
    """Revisión GRC 16-11-2026: longitudes de las columnas, tipo cerrado
    (`marcos_de_cumplimiento.TIPOS_DE_EVIDENCIA`) y hash del artefacto dado por
    quien lo tiene; antes se guardaba el SHA-256 del texto de la URI."""
    framework: str = Field(..., max_length=30, description="Framework de cumplimiento (SOC2, ISO27001)")
    control_id: str = Field(..., min_length=1, max_length=50, description="Identificador del control dentro del framework")
    evidence_type: Literal["policy", "screenshot", "report", "ticket", "audit_log", "other"] = Field(
        ..., description="Tipo de evidencia")
    title: str = Field(..., min_length=1, max_length=255, description="Título descriptivo de la evidencia")
    description: Optional[str] = Field(None, max_length=5000, description="Descripción detallada de la evidencia")
    artifact_uri: Optional[str] = Field(None, max_length=1000, description="URI del artefacto que respalda la evidencia")
    artifact_sha256: Optional[str] = Field(None, pattern=r"^[0-9a-fA-F]{64}$",
                                           description="SHA-256 del artefacto (lo calcula quien tiene el fichero)")
    metadata: Optional[dict] = Field(None, description="Metadatos adicionales asociados a la evidencia")
