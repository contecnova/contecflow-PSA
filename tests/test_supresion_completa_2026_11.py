"""Derecho de supresión: borra las copias, las credenciales y el almacén (revisión 2026-11).

Medido antes: dos borrados distintos y ninguno tocaba las copias del nombre o del
correo en otras tablas ni las credenciales; el de Enterprise guardaba el correo
original en la propia solicitud.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from app.models.mfa import MFAConfig
from app.models.pipeline import Opportunity
from app.models.sessions import UserSession
from app.models.user import User, UserRole
from app.services.bi_gdpr_service import execute_erasure


def test_EL_HALLAZGO_la_supresion_llega_a_las_copias_y_las_credenciales(db, monkeypatch):
    enviado = []

    class Conexion:      # el almacén de verdad no se toca en una prueba
        def execute(self, sql, params=None):
            enviado.append((sql, params))

        def close(self):
            pass
    monkeypatch.setattr("app.services.olap.etl.get_duckdb_conn", lambda: Conexion())
    db.add(User(id="u-sup", username="laura_g", email="laura@cliente.es", full_name="Laura Gómez",
                role=UserRole.employee, organization_id="1", hashed_password="x", phone="600000000"))
    db.add(Opportunity(code="OPP-S1", name="Renovación", client_name="Cliente", contact_name="Laura Gómez",
                       contact_email="laura@cliente.es", organization_id="1"))
    db.add(Opportunity(code="OPP-S2", name="Otra", client_name="Cliente", contact_name="Laura Gómez Pérez",
                       organization_id="1"))
    ahora = datetime.now(timezone.utc)
    db.add(UserSession(user_id="u-sup", refresh_token_jti="jti-1", last_seen_at=ahora, expires_at=ahora + timedelta(days=1)))
    db.add(MFAConfig(user_id="u-sup", totp_secret="s"))
    db.commit()
    r = execute_erasure(db, subject_id="laura@cliente.es", org_id="1")
    db.expire_all()
    u = db.get(User, "u-sup")
    assert (u.full_name, u.phone, u.is_active, u.hashed_password) == ("[ERASED]", None, False, None)
    assert u.email.endswith("@erased.invalid") and "laura" not in u.email + u.username
    o1 = db.query(Opportunity).filter(Opportunity.code == "OPP-S1").one()
    assert (o1.contact_name, o1.contact_email) == ("[ERASED]", u.email)
    assert db.query(Opportunity).filter(Opportunity.code == "OPP-S2").one().contact_name == "Laura Gómez Pérez"  # sólo exactas
    assert db.query(UserSession).filter(UserSession.user_id == "u-sup").count() == 0
    assert db.query(MFAConfig).filter(MFAConfig.user_id == "u-sup").count() == 0
    assert enviado == [("DELETE FROM dim_user WHERE user_id = ?", ["u-sup"])]
    assert {"table": "duckdb", "action": "dim_user: borrada"} in r["operations"]
