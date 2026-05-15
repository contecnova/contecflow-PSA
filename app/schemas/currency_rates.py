from datetime import date
from typing import Optional

from pydantic import BaseModel, Field


class ExchangeRateCreate(BaseModel):
    from_currency: str = Field(..., description="Código ISO 4217 de la moneda origen")
    to_currency: str = Field(..., description="Código ISO 4217 de la moneda destino")
    rate: float = Field(..., description="Tipo de cambio aplicado de origen a destino")
    effective_date: Optional[date] = Field(None, description="Fecha en la que entra en vigor el tipo")
    source: Optional[str] = Field("manual", description="Origen del tipo de cambio (manual, api, ecb, etc.)")
