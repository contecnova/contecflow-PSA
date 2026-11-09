"""El motor de alertas lee los umbrales de Ajustes → Alertas (revisión 2026-11).

Medido antes: `alert_configs` sólo la tocaba su pantalla; el motor usaba 100 %,
85 %, 7 días y 2 días fijos.
"""
from __future__ import annotations

from datetime import timedelta

from app.core import timeutil
from app.models.advanced_config import AlertConfig
from app.models.alert import Alert, AlertType
from app.models.project import Project
from app.services.alert_service import AlertEngine


def _proyecto(db, code, dias):
    p = Project(code=code, name=code, status="active", organization_id="1", project_type="consulting",
                end_date_planned=timeutil.today() + timedelta(days=dias))
    db.add(p)
    db.commit()
    return p


def _umbral(db, tipo, valor, activa=True):
    db.add(AlertConfig(organization_id="1", alert_type=tipo, label=tipo, threshold_value=valor, is_enabled=activa))
    db.commit()


def _hay(db, p):
    return db.query(Alert).filter(Alert.project_id == p.id, Alert.alert_type == AlertType.deadline_risk).count()


def test_EL_HALLAZGO_el_plazo_de_aviso_sale_de_ajustes(db):
    _umbral(db, "deadline_risk", 20)
    lejos = _proyecto(db, "ALR1", 15)
    AlertEngine(db)._check_deadline()
    assert _hay(db, lejos) == 1  # con 7 días fijos no avisaba


def test_una_alerta_apagada_no_salta(db):
    _umbral(db, "deadline_risk", 30, activa=False)
    p = _proyecto(db, "ALR2", 2)
    AlertEngine(db)._check_deadline()
    assert _hay(db, p) == 0


def test_sin_fila_usa_el_valor_del_catalogo(db):
    p = _proyecto(db, "ALR3", 5)
    assert AlertEngine(db)._config(AlertType.deadline_risk, "1")[1] == 7
    AlertEngine(db)._check_deadline()
    assert _hay(db, p) == 1
