"""
Alert service — business logic for alert generation.
Called by both the API endpoint and the Celery worker.
"""
from sqlalchemy.orm import Session
from app.api.v1.endpoints.alerts import AlertEngine


def run_alert_engine(db: Session) -> dict:
    engine = AlertEngine(db)
    count = engine.run_all()
    return {"alerts_generated": count}
