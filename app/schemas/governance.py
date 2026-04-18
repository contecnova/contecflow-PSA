from typing import Optional
from pydantic import BaseModel

class PolicyPackUpsert(BaseModel):
    is_enabled: bool = True
    pack_version: str = "1.0"
    config: Optional[dict] = None

class EvidenceCreate(BaseModel):
    framework: str
    control_id: str
    evidence_type: str
    title: str
    description: Optional[str] = None
    artifact_uri: Optional[str] = None
    metadata: Optional[dict] = None
