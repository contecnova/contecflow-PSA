from typing import Optional, List
from pydantic import BaseModel

class WikiSpaceIn(BaseModel):
    name: str
    slug: str
    description: Optional[str] = None
    project_id: Optional[str] = None
    is_public: bool = False

class WikiPageIn(BaseModel):
    title: str
    slug: str
    content: Optional[List] = []
    parent_id: Optional[str] = None
    is_published: bool = True
    sort_order: int = 0
    change_note: Optional[str] = None

class WikiTemplateIn(BaseModel):
    name: str
    description: Optional[str] = None
    icon: Optional[str] = None
    content: Optional[List] = []

class WikiCommentIn(BaseModel):
    content: str
    parent_id: Optional[str] = None

class EpicIn(BaseModel):
    title: str
    description: Optional[str] = None
    color: str = "#7c3aed"
    status: str = "open"
    priority: str = "medium"
    start_date: Optional[str] = None
    end_date: Optional[str] = None
    sort_order: int = 0

class NQLIn(BaseModel):
    entity_type: str
    query: str
    limit: int = 50

class SavedFilterIn(BaseModel):
    name: str
    entity_type: str
    nql_query: str
    is_shared: bool = False

class ThreadedCommentIn(BaseModel):
    content: str
    parent_id: Optional[str] = None
