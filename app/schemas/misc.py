from datetime import date
from typing import List, Optional

from pydantic import BaseModel


class ExportRequest(BaseModel):
    project_ids: Optional[List[str]] = None
    user_ids: Optional[List[str]] = None
    date_from: Optional[date] = None
    date_to: Optional[date] = None
    include_costs: bool = False
    format: str = "xlsx"


class PaginatedResponse(BaseModel):
    items: list
    total: int
    page: int
    page_size: int
    pages: int
