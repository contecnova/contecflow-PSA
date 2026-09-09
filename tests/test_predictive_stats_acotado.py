"""`/predictive/stats` gastaba 12 consultas por ticket abierto, sin tope.

Auditoría 2026-08 (P3-22). El endpoint cargaba **todos** los tickets abiertos
como objetos del ORM y, para cada uno, llamaba a `predict_ticket` y a
`predict_sla_breach`. Medido con la sesión real, no estimado:

     1 ticket abierto  ->    12 consultas
     5 tickets         ->    60 consultas
    20 tickets         ->   240 consultas

Exactamente **12 consultas por ticket**, y lineal. Con 500 tickets abiertos
—una cifra normal en un service desk con tráfico— son **6.000 consultas en una
sola petición**, más 500 objetos del ORM en memoria.

El tope no arregla el N+1; lo acota, que es lo que se puede hacer sin rediseñar
los dos predictores. Y la respuesta dice cuántos analizó de cuántos hay, para
que un número truncado no se lea como completo.

## Y el `except Exception` que se tragaba la mitad

El bucle tenía `except Exception: logger.debug(...)`, así que si los predictores
fallaban para la mitad de los tickets la respuesta salía igual, con la mitad de
los datos y sin decirlo. Sigue siendo *best-effort* —es lo correcto para una
predicción— pero ahora se cuenta en `failed_tickets`.
"""
from __future__ import annotations

import pytest
from sqlalchemy import event as sa_event

ORG = "org-pred-mia"
OTRA = "org-pred-ajena"


class _Usuario:
    def __init__(self, organization_id, superadmin=False):
        self.id = "u-pred"
        self.organization_id = organization_id
        self.is_superadmin = superadmin


def _tickets(db, org, cuantos, desde=0):
    from app.models.service_desk import Ticket

    for i in range(desde, desde + cuantos):
        db.add(Ticket(
            id=f"tp-{org}-{i}", number=f"SD-P{org[-3:]}{i}",
            ticket_type="incident", title=f"Ticket {i}", description="x",
            # `status` es un Enum: «open» no es un valor válido, los abiertos
            # son todos los que no están en `resolved`/`closed`.
            status="new", organization_id=org))
    db.commit()


def _contar_consultas(db, funcion):
    """Cuántas sentencias emite `funcion()`."""
    enlace = db.get_bind()
    cuenta = {"n": 0}

    def contar(conn, cursor, statement, parameters, context, executemany):
        cuenta["n"] += 1

    sa_event.listen(enlace, "before_cursor_execute", contar)
    try:
        resultado = funcion()
    finally:
        sa_event.remove(enlace, "before_cursor_execute", contar)
    return resultado, cuenta["n"]


# -- El ámbito ---------------------------------------------------------------

def test_EL_HALLAZGO_no_se_analizan_los_tickets_de_otro_cliente(db):
    from app.services.service_desk import predictive_analytics_service as svc

    _tickets(db, ORG, 3)
    _tickets(db, OTRA, 7)

    datos = svc.estadisticas_predictivas(db, _Usuario(ORG))
    assert datos["open_tickets"] == 3, (
        f"se están contando tickets de otras organizaciones: "
        f"{datos['open_tickets']}")
    assert datos["analyzed_tickets"] == 3


def test_EL_ESCENARIO_la_consulta_de_antes_alcanzaba_las_dos(db):
    """Que el escenario es real, medido y no contado."""
    from app.models.service_desk import Ticket

    _tickets(db, ORG, 3)
    _tickets(db, OTRA, 7)

    filas = db.query(Ticket).filter(
        Ticket.status.notin_(["resolved", "closed"])).all()
    assert len(filas) == 10, (
        "la consulta sin ámbito ya no alcanza las dos organizaciones; "
        "revisar si estos tests siguen midiendo lo que dicen")


def test_un_superadmin_si_ve_los_de_todos(db):
    from app.services.service_desk import predictive_analytics_service as svc

    _tickets(db, ORG, 3)
    _tickets(db, OTRA, 7)

    datos = svc.estadisticas_predictivas(db, _Usuario(None, superadmin=True))
    assert datos["open_tickets"] == 10


def test_un_sujeto_sin_organizacion_no_analiza_los_de_todos(db):
    from app.services.service_desk import predictive_analytics_service as svc

    _tickets(db, ORG, 3)
    datos = svc.estadisticas_predictivas(db, _Usuario(None))
    assert datos["open_tickets"] == 0


# -- El tope y el coste ------------------------------------------------------

def test_EL_HALLAZGO_el_coste_por_ticket_es_lineal_y_alto(db):
    """Deja medido el N+1, que el tope acota pero no elimina.

    Si alguien rediseña los predictores para que hagan una sola consulta, este
    test se pondrá en rojo — y entonces habrá que subir el tope, que es
    exactamente la conversación que hay que tener.
    """
    from app.services.service_desk import predictive_analytics_service as svc

    _tickets(db, ORG, 1)
    _, con_uno = _contar_consultas(
        db, lambda: svc.estadisticas_predictivas(db, _Usuario(ORG)))

    _tickets(db, ORG, 4, desde=1)
    _, con_cinco = _contar_consultas(
        db, lambda: svc.estadisticas_predictivas(db, _Usuario(ORG)))

    # Dos consultas fijas (el `count` y el `SELECT` acotado) más las de cada
    # ticket. La pendiente es lo que importa.
    por_ticket = (con_cinco - con_uno) / 4
    assert por_ticket > 5, (
        f"el coste por ticket ha bajado a {por_ticket:.1f} consultas: si los "
        "predictores ya no hacen N+1, el tope de tickets analizados se puede "
        "subir")


def test_el_tope_acota_lo_que_se_analiza_y_lo_dice(db, monkeypatch):
    from app.services.service_desk import predictive_analytics_service as svc

    _tickets(db, ORG, 5)
    monkeypatch.setattr(svc, "TOPE_DE_TICKETS_ANALIZADOS", 2)

    datos = svc.estadisticas_predictivas(db, _Usuario(ORG))
    assert datos["open_tickets"] == 5, "el total de abiertos debe seguir siendo 5"
    assert datos["analyzed_tickets"] == 2
    assert datos["truncated"] is True


def test_sin_truncamiento_no_se_marca(db):
    from app.services.service_desk import predictive_analytics_service as svc

    _tickets(db, ORG, 3)
    datos = svc.estadisticas_predictivas(db, _Usuario(ORG))
    assert datos["truncated"] is False
    assert datos["analyzed_tickets"] == datos["open_tickets"] == 3


def test_el_tope_se_configura_por_entorno_y_no_esta_en_duro():
    """La perilla tiene que existir en la configuración, no sólo en el código."""
    from app.services.service_desk import predictive_analytics_service as svc

    assert isinstance(svc.TOPE_DE_TICKETS_ANALIZADOS, int)
    assert svc.TOPE_DE_TICKETS_ANALIZADOS > 0

    entorno = open(".env.example", encoding="utf-8").read()
    assert "PREDICTIVE_STATS_MAX_TICKETS" in entorno, (
        "la perilla no está declarada en .env.example: el código la lee y la "
        "configuración no la ofrece")


# -- La forma de la respuesta ------------------------------------------------

def test_los_campos_de_siempre_siguen_estando(db):
    """No se cambia el contrato: sólo se añaden campos."""
    from app.services.service_desk import predictive_analytics_service as svc

    _tickets(db, ORG, 2)
    datos = svc.estadisticas_predictivas(db, _Usuario(ORG))

    for campo in ("open_tickets", "severity_distribution", "sla_at_risk_count",
                  "sla_at_risk_pct"):
        assert campo in datos, f"falta el campo {campo}, que ya devolvía antes"
    assert set(datos["severity_distribution"]) >= {
        "critical", "high", "medium", "low"}


def test_sin_tickets_el_porcentaje_es_cero_y_no_revienta(db):
    """La división por cero estaba resuelta en el original; se conserva."""
    from app.services.service_desk import predictive_analytics_service as svc

    datos = svc.estadisticas_predictivas(db, _Usuario(ORG))
    assert datos["open_tickets"] == 0
    assert datos["sla_at_risk_pct"] == 0


def test_los_fallos_de_prediccion_se_cuentan(db, monkeypatch):
    """El `except Exception` seguía siendo silencioso: ahora se ve."""
    from app.services.service_desk import predictive_analytics_service as svc

    _tickets(db, ORG, 3)

    def revienta(*_args, **_kwargs):
        raise RuntimeError("el predictor falla")

    monkeypatch.setattr(svc, "predict_ticket", revienta)

    datos = svc.estadisticas_predictivas(db, _Usuario(ORG))
    assert datos["failed_tickets"] == 3, (
        "los fallos de predicción no se están contando, así que una respuesta "
        "sin datos se lee como una respuesta con cero riesgo")
    assert datos["open_tickets"] == 3
    assert datos["sla_at_risk_count"] == 0


@pytest.mark.parametrize("umbral", [0.55])
def test_el_umbral_de_riesgo_esta_declarado(umbral):
    """El 0.55 estaba en duro en el cuerpo del endpoint."""
    from app.services.service_desk import predictive_analytics_service as svc

    assert svc.UMBRAL_DE_RIESGO_DE_SLA == umbral
