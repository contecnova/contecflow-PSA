from datetime import datetime
from typing import List, Optional
from pydantic import BaseModel

class CalendarEventCreate(BaseModel):
    subject:       str
    start_dt:      datetime
    end_dt:        datetime
    body:          Optional[str] = None
    location:      Optional[str] = None
    attendees:     List[str] = []
    user_upn:      str

class TeamsNotification(BaseModel):
    title:       str
    text:        str
    color:       str = "0078D4"
    webhook_url: Optional[str] = None

class MilestoneSyncRequest(BaseModel):
    user_upn:  str
    days_ahead: int = 30
