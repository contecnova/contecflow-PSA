"""Historial del temporizador filtrado en el servidor (auditoría 04b, B4; 23-11-2026).

Antes `/timer` pedía la primera página de imputaciones y se quedaba en el
cliente con las del temporizador: con muchas imputaciones a mano el historial
salía corto o vacío. Ahora `GET /imputations?only_timer=true` filtra en la base.
"""
from datetime import date
import uuid

from app.models.imputation import Imputation
from app.models.project import Project, ProjectStatus, ProjectType
from app.models.user import User


def _auth(token):
    return {"Authorization": f"Bearer {token}"}


def test_only_timer_devuelve_solo_las_del_temporizador(client, db, dev_token):
    dev = db.query(User).filter(User.id == "dev-test-id").one()
    proyecto = Project(code=f"TMRH-{uuid.uuid4().hex[:6]}", name="Historial del temporizador",
                       project_type=ProjectType.development, status=ProjectStatus.active,
                       organization_id=dev.organization_id, pm_id="pm-test-id")
    db.add(proyecto)
    db.flush()
    sesion = str(uuid.uuid4())
    db.add(Imputation(user_id=dev.id, project_id=proyecto.id, date=date.today(), hours=1.5, timer_session_id=sesion))
    for _ in range(3):
        db.add(Imputation(user_id=dev.id, project_id=proyecto.id, date=date.today(), hours=1.0))
    db.commit()

    r = client.get("/api/v1/imputations", params={"only_timer": "true", "project_id": proyecto.id},
                   headers=_auth(dev_token))
    assert r.status_code == 200, r.text
    filas = r.json()["items"]
    assert [f.get("timer_session_id") for f in filas] == [sesion]

    todas = client.get("/api/v1/imputations", params={"project_id": proyecto.id}, headers=_auth(dev_token))
    assert todas.status_code == 200
    assert len(todas.json()["items"]) == 4
