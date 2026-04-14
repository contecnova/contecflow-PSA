from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.deps import get_db, require_admin
from app.models.user import User

router = APIRouter(tags=["Currency"])


@router.post("/currency/sync-ecb", summary="Sync ECB daily exchange rates (admin)")
def sync_ecb_exchange_rates(
    force: bool = Query(default=False, description="Re-sync even if today's rates already exist"),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    from app.services.exchange_rate_service import sync_ecb_rates

    result = sync_ecb_rates(db, force=force)
    if not result.get("ok"):
        raise HTTPException(status_code=502, detail=result.get("error", "ECB fetch failed"))
    return result


@router.post("/currency/sync-openexchangerates", summary="Sync OpenExchangeRates (admin)")
def sync_openexchangerates(
    base: str = Query(default="USD"),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    app_id = settings.OPEN_EXCHANGE_RATES_APP_ID
    if not app_id:
        raise HTTPException(
            status_code=503,
            detail="OPEN_EXCHANGE_RATES_APP_ID not configured. Set it in your .env file.",
        )

    from app.services.exchange_rate_service import sync_openexchangerates as _sync

    result = _sync(db, app_id=app_id, base=base.upper())
    if not result.get("ok"):
        raise HTTPException(status_code=502, detail=result.get("error", "Sync failed"))
    return result
