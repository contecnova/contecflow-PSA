from typing import Optional, List
from pydantic import BaseModel

class MeetingProcessPayload(BaseModel):
    title: Optional[str] = None
    project_id: Optional[str] = None
    platform: str = "upload"
    transcript: str
    participants: Optional[List[str]] = None
    meeting_date: Optional[str] = None
    duration_min: Optional[int] = None

class ContractAnalyzePayload(BaseModel):
    project_id: Optional[str] = None
    client_name: Optional[str] = None
    filename: Optional[str] = None
    contract_text: str

class VoiceCommandPayload(BaseModel):
    transcript: str
    confidence: Optional[float] = None

class SmartScheduleRequest(BaseModel):
    project_id: Optional[str] = None
    max_tasks: int = 20

class OverrunPredictionOut(BaseModel):
    project_id:             str
    project_name:           str
    cost_overrun_prob:      float
    schedule_overrun_prob:  float
    cost_overrun_pct:       float
    schedule_overrun_days:  int
    confidence:             str
    signals:                list
    recommendation:         str
