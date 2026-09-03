"""Las 12 métricas de tickets, con valores calculados a mano.

Auditoría 2026-08 (P3-18). `_serie_tickets_open` era complejidad **18**: doce
ramas sobre `metric_key` **dentro** del bucle de filas, así que reevaluaba la
cadena entera por cada ticket de la consulta.

Lo que estos tests fijan y el test de catálogo no puede ver, porque sobre base
vacía las doce valen 0.0:

  · que «abierto» y «resuelto» usan listas de estados **distintas** — un ticket
    cancelado no está abierto pero tampoco cuenta como resuelto. Estaba escrito
    como dos literales separados en dos ramas, y uniformarlos por descuido en un
    refactor cambiaría las dos métricas a la vez sin que nada fallara;
  · que las tres medias (primera respuesta, resolución, CSAT) promedian sobre
    las filas que **tienen** el dato, no sobre todos los tickets del mes —
    dividir entre todos hundiría el CSAT de cualquier mes con tickets sin
    encuestar;
  · que un mes sin filas que apliquen da 0.0 y no divide por cero;
  · que las métricas de incumplimiento de SLA cuentan por el flag y no por el
    estado.

Todos los tickets se crean en el mismo mes salvo donde se dice, para que las
cuentas se puedan hacer a mano sin ambigüedad. La rejilla es el año en curso.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone

import pytest

from app.models.service_desk import Ticket
from app.services.bi_smart_alerts.metrics import _fetch_metric_series

ANIO = 2026
MES = 4                      # todos los tickets base en abril
OTRO_MES = 5


def _ticket(db, *, mes=MES, estado="new", prioridad="p3_medium",
            resp=None, resol=None, csat=None,
            sla_resp=False, sla_resol=False, auto=False, dedicado=None):
    db.add(Ticket(
        id=str(uuid.uuid4()),
        organization_id="1",
        number=f"TK-{uuid.uuid4().hex[:8]}",
        title="Ticket de prueba",
        description="—",
        ticket_type="incident",
        status=estado,
        priority=prioridad,
        created_at=datetime(ANIO, mes, 10, 12, 0, tzinfo=timezone.utc),
        first_response_minutes=resp,
        resolution_minutes=resol,
        csat_score=csat,
        sla_response_breached=sla_resp,
        sla_resolution_breached=sla_resol,
        auto_resolved=auto,
        time_spent_minutes=dedicado,
    ))


def _por_mes(db, clave: str) -> dict[str, float]:
    from app.services.bi_smart_alerts.metrics import _construir_contexto
    ctx = _construir_contexto(db, clave, "1")
    serie = _fetch_metric_series(db, clave, "1")
    assert serie is not None and len(serie) == len(ctx.series), clave
    return {m["month"]: v for m, v in zip(ctx.series, serie, strict=True)}


def _mes(v: dict[str, float], mes=MES) -> float:
    return v[f"{ANIO}-{mes:02d}"]


# ── Abierto y resuelto usan listas de estados distintas ───────────────────────

@pytest.fixture
def por_estado(db):
    """Un ticket de cada estado, los ocho.

    Abiertos: new, assigned, in_progress, pending_client, pending_third → 5
    Resueltos: resolved, closed → 2
    Cancelado: ni abierto ni resuelto → 1
    """
    for estado in ("new", "assigned", "in_progress", "pending_client",
                   "pending_third", "resolved", "closed", "cancelled"):
        _ticket(db, estado=estado)
    db.commit()


def test_los_abiertos_excluyen_cerrados_resueltos_y_cancelados(db, por_estado):
    assert _mes(_por_mes(db, "tickets_open")) == 5.0


def test_los_resueltos_solo_cuentan_resolved_y_closed(db, por_estado):
    """El cancelado NO cuenta como resuelto, aunque tampoco esté abierto."""
    assert _mes(_por_mes(db, "tickets_resolved")) == 2.0


def test_un_cancelado_no_esta_ni_abierto_ni_resuelto(db):
    """La asimetría, aislada. Si las dos listas de estados se uniformaran, una de
    las dos métricas cambiaría sin que nada fallara."""
    _ticket(db, estado="cancelled")
    db.commit()
    assert _mes(_por_mes(db, "tickets_open")) == 0.0
    assert _mes(_por_mes(db, "tickets_resolved")) == 0.0
    assert _mes(_por_mes(db, "tickets_created")) == 1.0


def test_los_creados_cuentan_todos_los_estados(db, por_estado):
    assert _mes(_por_mes(db, "tickets_created")) == 8.0


def test_los_creados_van_al_mes_de_creacion(db):
    _ticket(db, mes=MES)
    _ticket(db, mes=OTRO_MES)
    _ticket(db, mes=OTRO_MES)
    db.commit()
    v = _por_mes(db, "tickets_created")
    assert _mes(v, MES) == 1.0
    assert _mes(v, OTRO_MES) == 2.0


# ── Prioridades ───────────────────────────────────────────────────────────────

def test_las_prioridades_p1_y_p2_se_cuentan_por_separado(db):
    _ticket(db, prioridad="p1_critical")
    _ticket(db, prioridad="p1_critical")
    _ticket(db, prioridad="p2_high")
    _ticket(db, prioridad="p3_medium")
    _ticket(db, prioridad="p4_low")
    db.commit()
    assert _mes(_por_mes(db, "tickets_p1_count")) == 2.0
    assert _mes(_por_mes(db, "tickets_p2_count")) == 1.0


def test_la_prioridad_se_cuenta_sea_cual_sea_el_estado(db):
    """No lleva filtro de estado: un P1 ya cerrado sigue habiendo sido un P1."""
    _ticket(db, prioridad="p1_critical", estado="closed")
    db.commit()
    assert _mes(_por_mes(db, "tickets_p1_count")) == 1.0


# ── Las tres medias ───────────────────────────────────────────────────────────

def test_la_primera_respuesta_promedia_solo_los_que_la_tienen(db):
    """Tres tickets, dos con dato: (10 + 30) / 2 = 20. El tercero no baja la
    media a 13,33 — promediar sobre todos los tickets del mes es justo el error
    que este test descarta."""
    _ticket(db, resp=10)
    _ticket(db, resp=30)
    _ticket(db, resp=None)
    db.commit()
    assert _mes(_por_mes(db, "first_response_time_avg")) == pytest.approx(20.0)


def test_el_tiempo_de_resolucion_promedia_igual(db):
    _ticket(db, resol=100)
    _ticket(db, resol=200)
    _ticket(db, resol=None)
    db.commit()
    assert _mes(_por_mes(db, "resolution_time_avg")) == pytest.approx(150.0)


def test_el_csat_promedia_solo_los_encuestados(db):
    """Cuatro tickets, dos encuestados: (5 + 4) / 2 = 4,5. Si dividiera entre los
    cuatro saldría 2,25 y el panel mostraría una satisfacción falsa."""
    _ticket(db, csat=5)
    _ticket(db, csat=4)
    _ticket(db, csat=None)
    _ticket(db, csat=None)
    db.commit()
    assert _mes(_por_mes(db, "csat_avg")) == pytest.approx(4.5)


def test_un_csat_de_cero_si_cuenta(db):
    """`csat is not None` y no `if csat`: un cero es una valoración legítima —
    la peor— y descartarla subiría la media artificialmente."""
    _ticket(db, csat=0)
    _ticket(db, csat=4)
    db.commit()
    assert _mes(_por_mes(db, "csat_avg")) == pytest.approx(2.0)


def test_un_mes_sin_datos_da_cero_y_no_divide_por_cero(db):
    _ticket(db, resp=10)
    db.commit()
    v = _por_mes(db, "first_response_time_avg")
    assert _mes(v, MES) == pytest.approx(10.0)
    assert _mes(v, OTRO_MES) == 0.0


def test_las_medias_se_redondean_a_dos_decimales(db):
    """(10 + 11 + 11) / 3 = 10,666… → 10,67."""
    _ticket(db, resp=10)
    _ticket(db, resp=11)
    _ticket(db, resp=11)
    db.commit()
    assert _mes(_por_mes(db, "first_response_time_avg")) == pytest.approx(10.67)


# ── Incumplimientos de SLA y auto-resolución ──────────────────────────────────

def test_los_incumplimientos_de_sla_se_cuentan_por_el_flag(db):
    """Por el flag y no por el estado: un ticket ya cerrado puede haber
    incumplido el SLA, y es precisamente el que hay que contar."""
    _ticket(db, sla_resp=True, estado="closed")
    _ticket(db, sla_resp=True, estado="new")
    _ticket(db, sla_resp=False)
    db.commit()
    assert _mes(_por_mes(db, "sla_response_breached")) == 2.0


def test_los_dos_incumplimientos_de_sla_son_independientes(db):
    """Responder a tiempo y resolver a tiempo son dos compromisos distintos."""
    _ticket(db, sla_resp=True, sla_resol=False)
    _ticket(db, sla_resp=False, sla_resol=True)
    db.commit()
    assert _mes(_por_mes(db, "sla_response_breached")) == 1.0
    assert _mes(_por_mes(db, "sla_resolution_breached")) == 1.0


def test_los_auto_resueltos_se_cuentan_por_su_flag(db):
    _ticket(db, auto=True)
    _ticket(db, auto=True)
    _ticket(db, auto=False)
    db.commit()
    assert _mes(_por_mes(db, "auto_resolved_count")) == 2.0


# ── Tiempo dedicado: suma, no media ───────────────────────────────────────────

def test_el_tiempo_dedicado_se_suma(db):
    """Ésta acumula minutos y no promedia. Si se colara en el grupo de las
    medias, un mes con tres tickets de 60 minutos mostraría 60 en vez de 180."""
    _ticket(db, dedicado=60)
    _ticket(db, dedicado=60)
    _ticket(db, dedicado=60)
    db.commit()
    assert _mes(_por_mes(db, "ticket_time_spent_total")) == 180.0


def test_un_ticket_sin_tiempo_dedicado_no_aporta(db):
    _ticket(db, dedicado=None)
    _ticket(db, dedicado=0)
    _ticket(db, dedicado=45)
    db.commit()
    assert _mes(_por_mes(db, "ticket_time_spent_total")) == 45.0


# ── Que el fichero y la tabla no se separen ───────────────────────────────────

def test_las_12_claves_de_ticket_estan_cubiertas():
    from app.services.bi_smart_alerts.metrics import CLAVES_DE_TICKET

    probadas = {
        "tickets_open", "tickets_created", "tickets_resolved",
        "tickets_p1_count", "tickets_p2_count",
        "first_response_time_avg", "resolution_time_avg", "csat_avg",
        "sla_response_breached", "sla_resolution_breached",
        "auto_resolved_count", "ticket_time_spent_total",
    }
    assert probadas == set(CLAVES_DE_TICKET), (
        f"sin probar: {set(CLAVES_DE_TICKET) - probadas}; "
        f"sobran: {probadas - set(CLAVES_DE_TICKET)}"
    )


def test_las_claves_cableadas_y_las_atendidas_coinciden():
    """`_serie_tickets_open` devuelve `None` para una clave que no atiende, y el
    despachador lo lee como «no me toca». Una clave cableada pero fuera de la
    tabla se quedaría sin serie en silencio."""
    from app.services.bi_smart_alerts.metrics import (
        CLAVES_DE_TICKET, _RESOLUTORES, _serie_tickets_open,
    )

    cableadas = {k for k, v in _RESOLUTORES.items() if v is _serie_tickets_open}
    assert cableadas == set(CLAVES_DE_TICKET), (
        f"cableadas sin atender: {cableadas - set(CLAVES_DE_TICKET)}; "
        f"atendidas sin cablear: {set(CLAVES_DE_TICKET) - cableadas}"
    )
