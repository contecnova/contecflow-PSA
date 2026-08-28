"""La tarifa de las simulaciones sale de datos reales (auditoría 2026-08, P2-20).

`activity_service` valoraba las simulaciones de proyecto con un literal
`avg_rate = 80.0`. Cualquier cliente cuyas tarifas no fueran 80 €/h recibía
cifras económicas equivocadas, y nada en la interfaz avisaba de que el número era
una constante del código y no su dato.

Ahora se resuelve por orden de especificidad: tarifa del proyecto → media de los
asignados → valor configurable. El literal sólo sobrevive como último recurso, y
además es ajustable por despliegue.
"""
from __future__ import annotations

import uuid

from app.core.config import settings
from app.services.activity_service import _resolve_simulation_rate


class _Proyecto:
    def __init__(self, billing_rate=None):
        self.billing_rate = billing_rate


class _Tarea:
    def __init__(self, assignee_id=None):
        self.assignee_id = assignee_id


def _mk_user(db, hourly_rate):
    from app.models.user import User, UserRole, UserStatus
    from app.core.security import get_password_hash

    suf = uuid.uuid4().hex[:8]
    u = User(
        id=str(uuid.uuid4()),
        username=f"rate{suf}",
        email=f"rate{suf}@example.test",
        full_name="Rate Test",
        role=UserRole.employee,
        status=UserStatus.active,
        is_active=True,
        organization_id="1",
        hourly_rate=hourly_rate,
        hashed_password=get_password_hash("Rt5!eQwz3_km"),
        weekly_capacity_hours=40.0,
        currency="EUR",
    )
    db.add(u)
    db.commit()
    return u


def test_prioriza_la_tarifa_de_facturacion_del_proyecto(db):
    """Es la que el cliente tiene pactada: manda sobre todo lo demás."""
    tasa = _resolve_simulation_rate(db, _Proyecto(billing_rate=123.5), [])
    assert tasa == 123.5


def test_usa_la_media_de_los_asignados_si_el_proyecto_no_tiene_tarifa(db):
    """Refleja la composición real del equipo."""
    u1 = _mk_user(db, 100.0)
    u2 = _mk_user(db, 60.0)
    tareas = [_Tarea(u1.id), _Tarea(u2.id)]
    tasa = _resolve_simulation_rate(db, _Proyecto(billing_rate=None), tareas)
    assert tasa == 80.0, f"se esperaba la media (100+60)/2, llegó {tasa}"


def test_ignora_a_los_asignados_sin_tarifa(db):
    """Un usuario sin hourly_rate no debe arrastrar la media hacia cero."""
    con = _mk_user(db, 90.0)
    sin = _mk_user(db, None)
    tasa = _resolve_simulation_rate(db, _Proyecto(), [_Tarea(con.id), _Tarea(sin.id)])
    assert tasa == 90.0


def test_cae_al_valor_configurable_si_no_hay_ningun_dato(db):
    tasa = _resolve_simulation_rate(db, _Proyecto(billing_rate=None), [])
    assert tasa == float(settings.DEFAULT_SIMULATION_HOURLY_RATE)


def test_el_valor_por_defecto_es_configurable():
    """La clave: ya no es un literal enterrado en un servicio."""
    assert hasattr(settings, "DEFAULT_SIMULATION_HOURLY_RATE")


def test_ya_no_queda_el_literal_en_el_servicio():
    import inspect

    from app.services import activity_service

    # Se ignoran comentarios: el propio código explica el literal que sustituyó,
    # y buscar la cadena a secas se detectaría a sí mismo.
    codigo = [
        linea
        for linea in inspect.getsource(activity_service).splitlines()
        if not linea.lstrip().startswith("#")
    ]
    infractoras = [l for l in codigo if "avg_rate = 80" in l]
    assert not infractoras, (
        f"volvió el literal de 80 €/h como código: {infractoras}"
    )


def test_una_tarifa_de_proyecto_a_cero_no_se_toma_como_valida(db):
    """0 es "sin definir" en este esquema, no una tarifa gratuita.

    Tomarla al pie de la letra haría que toda la simulación valiese 0 € sin que
    nada lo indicara.
    """
    tasa = _resolve_simulation_rate(db, _Proyecto(billing_rate=0), [])
    assert tasa == float(settings.DEFAULT_SIMULATION_HOURLY_RATE)
