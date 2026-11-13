"""Service Desk — estado del correo entrante: ultimos mensajes, prueba y lectura."""
from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.core.deps import require_admin
from app.core.responses import APIListResponse, APIResponse
from app.db.session import get_db
from app.models.user import User
from app.services.service_desk import buzones
from app.core.constantes import MAX_TAMANO_DE_PAGINA

router = APIRouter(prefix="/inbound", tags=["Service Desk - Correo entrante"])


@router.get("/messages", summary="Últimos correos recibidos y qué se hizo con cada uno")
def ultimos(limit: int = Query(30, ge=1, le=MAX_TAMANO_DE_PAGINA), db: Session = Depends(get_db),
            _: User = Depends(require_admin)):
    return APIListResponse.ok(items=buzones.ultimos_mensajes(db, limit))


@router.post("/test", summary="Probar la conexión con el buzón (no procesa nada)")
def probar(db: Session = Depends(get_db), user: User = Depends(require_admin)):
    return APIResponse.ok(data=buzones.probar_buzon(db, user.organization_id))


@router.post("/run", summary="Leer ahora el buzón de la organización")
def leer_ahora(db: Session = Depends(get_db), user: User = Depends(require_admin)):
    return APIResponse.ok(data=buzones.leer_buzon(db, user.organization_id))
