from typing import Optional, List
from datetime import date
from pydantic import BaseModel

class RACIEntryIn(BaseModel):
    item_type:  str              # deliverable | milestone | phase | custom
    item_label: str
    item_id:    Optional[str] = None
    user_id:    str
    role:       str              # R | A | C | I

class RACIBatchIn(BaseModel):
    entries: List[RACIEntryIn]

class RetroNotesIn(BaseModel):
    manual_notes: Optional[str] = None
    action_items: Optional[List[dict]] = None   # [{text, owner_id}]

class ChangelogEntryIn(BaseModel):
    version_tag: Optional[str] = None
    entry_date:  date
    entry_type:  str = "feature"   # feature | bugfix | improvement | milestone | breaking
    title:       str
    description: Optional[str] = None

class ChangelogEntryPatch(BaseModel):
    version_tag: Optional[str] = None
    entry_date:  Optional[date] = None
    entry_type:  Optional[str] = None
    title:       Optional[str] = None
    description: Optional[str] = None

class UATCaseIn(BaseModel):
    title: str
    description: Optional[str] = None
    expected_result: Optional[str] = None
    actual_result: Optional[str] = None
    status: Optional[str] = "pending"
    priority: Optional[str] = "medium"
    task_id: Optional[str] = None
    assigned_to_id: Optional[str] = None
    notes: Optional[str] = None
