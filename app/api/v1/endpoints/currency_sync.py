from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.core.deps import get_db, require_admin
from app.core.responses import APIResponse
from app.models.user import User

router = APIRouter(tags=["Currency"])


@router.post("/currency/sync-ecb", summary="Sync ECB daily exchange rates (admin)")
def sync_ecb_exchange_rates(
    force: bool = Query(default=False, description="Re-sync even if today's rates already exist"),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    from app.services.exchange_rate_service import sync_ecb_rates

    # Segunda auditoria 2026-11 (n.º 20): la descarga del BCE va al worker. Con
    # cola: 202 `{status: "queued"}` (un fallo queda en el log del worker, ya no
    # es un 502). Sin cola, como siempre.
    from app.core.segundo_plano import EN_COLA, encolar, respuesta_en_cola
    result = encolar(sync_ecb_rates, force=force, _sesion=db)
    if result is EN_COLA:
        return respuesta_en_cola()
    if not result.get("ok"):
        raise HTTPException(status_code=502, detail=result.get("error", "ECB fetch failed"))
    return APIResponse.ok(data=result)


@router.post("/currency/sync-openexchangerates", summary="Sync OpenExchangeRates (admin)")
def sync_openexchangerates(
    base: str = Query(default="USD"),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    from app.services.integration_credentials_service import get_credential
    app_id = get_credential(db, "open_exchange_rates", "app_id", org_id=getattr(current_user, "organization_id", None))
    if not app_id:
        raise HTTPException(
            status_code=503,
            detail="OPEN_EXCHANGE_RATES_APP_ID no configurado. Edita en Settings → Sistema → Credenciales → OpenExchangeRates, o defínelo en .env.",
        )

    from app.services.exchange_rate_service import sync_openexchangerates as _sync

    result = _sync(db, app_id=app_id, base=base.upper())
    if not result.get("ok"):
        raise HTTPException(status_code=502, detail=result.get("error", "Sync failed"))
    return APIResponse.ok(data=result)
