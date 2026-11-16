"""Periodo libre en informes (16-11-2026): límites que aplica la API.

El selector de periodo del frontend los lee para desactivar lo que la API
rechazaría (rango demasiado largo, demasiados puntos para una granularidad) y
para resolver ``auto`` igual que el servidor. Ver ``app/core/periodo.py``.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, get_db
from app.core.periodo import GRANULARIDADES, limites_de_periodo
from app.core.responses import APIResponse
from app.models.user import User

router = APIRouter()


@router.get("/limites", summary="Límites del periodo libre de los informes")
def limites(db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    org_id = str(current_user.organization_id) if current_user.organization_id else None
    datos = limites_de_periodo(db, org_id).a_dict()
    datos["granularidades"] = list(GRANULARIDADES)
    return APIResponse.ok(data=datos)
