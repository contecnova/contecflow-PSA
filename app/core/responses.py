"""Canonical API response wrapper — audit #67.

Para nuevos endpoints (y migración incremental de los viejos), envolver
las respuestas en APIResponse o APIListResponse:

    @router.get("/items")
    def list_items() -> APIListResponse[Item]:
        items = svc.list_items(...)
        return APIListResponse.ok(items=items, total=len(items))
"""
from typing import Generic, List, Optional, TypeVar
from pydantic import BaseModel, Field

T = TypeVar("T")


class ResponseMeta(BaseModel):
    total: Optional[int] = Field(None, description="Total de items (si está paginado)")
    page: Optional[int] = Field(None, description="Página actual")
    page_size: Optional[int] = Field(None, description="Tamaño de página")
    has_more: Optional[bool] = Field(None, description="Hay más páginas")


class APIResponse(BaseModel, Generic[T]):
    """Wrapper para respuestas single-object."""
    data: T
    meta: Optional[ResponseMeta] = None

    @classmethod
    def ok(cls, data: T, meta: Optional[ResponseMeta] = None) -> "APIResponse[T]":
        return cls(data=data, meta=meta)


class APIListResponse(BaseModel, Generic[T]):
    """Wrapper para respuestas de lista (paginada o no)."""
    items: List[T]
    meta: ResponseMeta

    @classmethod
    def ok(
        cls,
        items: List[T],
        total: Optional[int] = None,
        page: Optional[int] = None,
        page_size: Optional[int] = None,
    ) -> "APIListResponse[T]":
        return cls(
            items=items,
            meta=ResponseMeta(
                total=total if total is not None else len(items),
                page=page,
                page_size=page_size,
            ),
        )
