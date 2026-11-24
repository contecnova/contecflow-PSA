"""Salud del cliente y NPS: el cálculo único (revisión 24-11-2026).

Fija lo medido roto: componentes con campos inexistentes (entrega y presupuesto
siempre el valor por defecto, tickets 0), la foto de «calcular salud» con 60 %
inventado y sin componentes, el ranking con duplicados y clientes inactivos, y
las CSAT 1-5 mezcladas en el NPS. Ver README §27.4 y el docstring de
customer_health_service.
"""
from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from types import SimpleNamespace

import pytest

from app.services import customer_health_service as chs

HOY = date(2026, 11, 24)
DESDE = HOY - timedelta(days=90)


def _hito(**kw):
    base = dict(is_active=True, due_date=HOY - timedelta(days=10), is_completed=False, completed_date=None)
    base.update(kw)
    return SimpleNamespace(**base)


# ── Funciones puras ───────────────────────────────────────────────────────────

class TestNps:
    def test_sin_respuestas(self):
        assert chs.nps_de_puntuaciones([]) is None

    def test_mezcla(self):
        # 2 promotores, 1 pasivo, 1 detractor → (2-1)/4 = 25
        assert chs.nps_de_puntuaciones([10, 9, 7, 4]) == pytest.approx(25.0)

    def test_extremos(self):
        assert chs.nps_de_puntuaciones([10, 10]) == pytest.approx(100.0)
        assert chs.nps_de_puntuaciones([0, 6]) == pytest.approx(-100.0)


class TestHitos:
    def test_completado_a_tiempo(self):
        h = _hito(is_completed=True, completed_date=HOY - timedelta(days=12))
        assert chs.hito_evaluable(h, DESDE, HOY) is True

    def test_completado_tarde(self):
        h = _hito(is_completed=True, completed_date=HOY - timedelta(days=2))
        assert chs.hito_evaluable(h, DESDE, HOY) is False

    def test_vencido_sin_completar(self):
        assert chs.hito_evaluable(_hito(), DESDE, HOY) is False

    def test_futuro_sin_completar_no_cuenta(self):
        assert chs.hito_evaluable(_hito(due_date=HOY + timedelta(days=5)), DESDE, HOY) is None

    def test_completado_antes_de_tiempo_cuenta(self):
        h = _hito(due_date=HOY + timedelta(days=30), is_completed=True, completed_date=HOY - timedelta(days=1))
        assert chs.hito_evaluable(h, DESDE, HOY) is True

    def test_fuera_de_ventana_no_cuenta(self):
        h = _hito(due_date=HOY - timedelta(days=200), is_completed=True, completed_date=HOY - timedelta(days=199))
        assert chs.hito_evaluable(h, DESDE, HOY) is None

    def test_completado_sin_fecha_no_medible(self):
        assert chs.hito_evaluable(_hito(is_completed=True, completed_date=None), DESDE, HOY) is None

    def test_inactivo_o_sin_vencimiento(self):
        assert chs.hito_evaluable(_hito(is_active=False), DESDE, HOY) is None
        assert chs.hito_evaluable(_hito(due_date=None), DESDE, HOY) is None


PESOS = {"nps": 0.4, "delivery": 0.2, "budget": 0.15, "ticket_resolution": 0.15, "portal_activity": 0.1}


class TestComponer:
    def test_todos_con_datos_es_la_media_ponderada(self):
        valores = {"nps": 100, "delivery": 50, "budget": 100, "ticket_resolution": 0, "portal_activity": 100}
        puntuacion, efectivos, cobertura = chs.componer(valores, PESOS, 70)
        assert puntuacion == pytest.approx(40 + 10 + 15 + 0 + 10)
        assert cobertura == pytest.approx(1.0)
        assert sum(efectivos.values()) == pytest.approx(1.0)

    def test_sin_datos_reparte_el_peso(self):
        valores = {"nps": 80, "delivery": None, "budget": None, "ticket_resolution": 40, "portal_activity": None}
        puntuacion, efectivos, cobertura = chs.componer(valores, PESOS, 70)
        # 80·0.4/0.55 + 40·0.15/0.55
        assert puntuacion == pytest.approx(round((80 * 0.4 + 40 * 0.15) / 0.55, 1))
        assert efectivos["delivery"] == 0.0
        assert efectivos["nps"] == pytest.approx(0.4 / 0.55)
        assert cobertura == pytest.approx(0.55)

    def test_ningun_dato_usa_el_defecto(self):
        puntuacion, _, cobertura = chs.componer(dict.fromkeys(PESOS), PESOS, 70)
        assert puntuacion == 70.0
        assert cobertura == 0.0

    def test_pesos_que_no_suman_uno_se_normalizan(self):
        pesos = {k: v * 10 for k, v in PESOS.items()}
        valores = {"nps": 60, "delivery": 60, "budget": 60, "ticket_resolution": 60, "portal_activity": 60}
        assert chs.componer(valores, pesos, 70)[0] == pytest.approx(60.0)

    def test_peso_negativo_cuenta_como_cero(self):
        valores = {"nps": 100, "delivery": 0}
        assert chs.componer(valores, {"nps": 1.0, "delivery": -5.0}, 70)[0] == pytest.approx(100.0)


def test_categoria():
    s = SimpleNamespace(HEALTH_THRESHOLD_EXCELLENT=80, HEALTH_THRESHOLD_GOOD=60, HEALTH_THRESHOLD_AT_RISK=40)
    assert chs.categoria(85, s) == "excellent"
    assert chs.categoria(60, s) == "good"
    assert chs.categoria(45, s) == "at_risk"
    assert chs.categoria(10, s) == "critical"
    assert chs.categoria(70, s, con_datos=False) == "no_data"


def _componentes(tickets, portal):
    return {
        "ticket_resolution": {"value": tickets, "weight": 0.15, "has_data": tickets is not None},
        "portal_activity": {"value": portal, "weight": 0.10, "has_data": portal is not None},
    }


def test_actividad_combinada():
    assert chs.actividad_combinada(_componentes(100, 50)) == pytest.approx(80.0)
    assert chs.actividad_combinada(_componentes(None, 50)) == pytest.approx(50.0)
    assert chs.actividad_combinada(_componentes(None, None)) is None


def test_nota_de_foto():
    r = {"data_coverage": 0.25, "components": {
        "nps": {"value": 90, "has_data": True}, "delivery": {"value": None, "has_data": False},
        "budget": {"value": None, "has_data": False},
        **_componentes(100, None)}}
    nota = chs.nota_de_foto(r)
    assert "tickets=100" in nota and "portal=-" in nota
    assert "no_data=delivery,budget,portal_activity" in nota


# ── Con base de datos ─────────────────────────────────────────────────────────

def _cliente(db, nombre, **kw):
    from app.models.clients import Client
    c = Client(name=nombre, industry="technology", **kw)
    db.add(c)
    db.flush()
    return c


def test_csat_no_entra_en_el_nps(db):
    from app.models.nps import ClientNPS, NPSCategory
    from app.services import nps_service
    c = _cliente(db, "Cliente CSAT")
    nps_service.create_nps_entry(db, c.id, 10, None, None, "manual")
    # Una CSAT 5 (la mejor) se guardaba en la misma tabla y contaba en el NPS.
    db.add(ClientNPS(client_id=c.id, score=5, category=NPSCategory.passive, survey_type="csat"))
    db.commit()
    filas = nps_service.list_nps_responses(db, c.id, 50)
    assert [r.score for r in filas] == [10]
    r = chs.compute_composite_health(c.id, db)
    assert r["components"]["nps"]["responses"] == 1
    assert r["components"]["nps"]["value"] == pytest.approx(100.0)


def test_calcular_salud_guarda_los_componentes(db):
    from app.services import nps_service
    c = _cliente(db, "Cliente Foto")
    for _ in range(2):
        nps_service.create_nps_entry(db, c.id, 10, None, None, "manual")
    snap = nps_service.compute_and_save_health(db, c.id)
    assert snap.nps_component == pytest.approx(100.0)
    assert snap.delivery_component is None and snap.budget_component is None
    # Solo NPS medido: todo su peso → 100 (antes 40·1 + 70·0.6 = 82 inventado).
    assert snap.health_score == pytest.approx(100.0)
    assert snap.note.startswith("auto;")


def test_ranking_sin_duplicados_y_solo_clientes_activos(db):
    from app.models.clients import ClientStatus
    from app.models.nps import ClientHealthSnapshot
    from app.services import nps_service
    activo = _cliente(db, "Activo Ranking")
    perdido = _cliente(db, "Perdido Ranking", status=ClientStatus.churned)
    baja = _cliente(db, "Baja Ranking", is_active=False)
    t = datetime(2026, 11, 20, 10, 0, tzinfo=timezone.utc)
    for c in (activo, perdido, baja):
        db.add(ClientHealthSnapshot(client_id=c.id, health_score=50, snapshot_at=t))
    db.add(ClientHealthSnapshot(client_id=activo.id, health_score=60, snapshot_at=t))  # misma fecha
    db.commit()
    filas = [(s.client_id, s.health_score) for s, _ in nps_service.get_health_leaderboard(db)
             if s.client_id in (activo.id, perdido.id, baja.id)]
    assert filas == [(activo.id, 60)]
