from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from app.db.session import get_db
from app.core.deps import get_current_user
from app.models.user import User

router = APIRouter()

@router.get("/pipeline", summary="Resource demand from pipeline")
def get_resource_demand_pipeline(db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    # Dummy response for test contract
    return {"demand": 0, "projects": []}
