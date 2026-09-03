"""Actualización de tickets: transiciones de estado y reloj del SLA.

Auditoría 2026-08 (P3-18). `apply_ticket_update` eran 117 líneas de complejidad
29 **sin un solo test**, y contenían una duplicación literal: el bloque que
acumula el tiempo en pausa y reanuda el reloj del SLA aparecía dos veces, en la
rama `in_progress` y en el `else`. Dos copias del mismo cálculo son dos sitios
donde corregir un error y uno donde olvidarlo.

Es la función que decide si un SLA se ha incumplido, así que sus resultados
acaban en las métricas que se le enseñan al cliente.

Se prueba con dobles y **reloj congelado**: la función llama a `datetime.now()`,
así que sin congelarlo dos ejecuciones dan marcas distintas. Al capturar la línea
base sin congelar salieron 14 de 23 casos «distintos», y todas las diferencias
eran el reloj — un falso positivo que habría escondido uno real.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from app.services.service_desk import ticket_update_service as svc

AHORA = datetime(2026, 9, 2, 12, 0, tzinfo=timezone.utc)

CAMPOS = (
    "status", "priority", "urgency", "impact", "tags", "support_level",
    "first_response_at", "first_response_minutes", "resolved_at",
    "resolution_minutes", "closed_at", "csat_requested_at",
    "sla_paused_at", "sla_pause_minutes", "sla_response_due",
    "sla_resolution_due", "sla_response_breached", "sla_resolution_breached",
)


class _RelojFijo(datetime):
    """`datetime` con `now()` congelado en AHORA."""

    @classmethod
    def now(cls, tz=None):
        return AHORA if tz else AHORA.replace(tzinfo=None)


@pytest.fixture(autouse=True)
def _congelar_reloj(monkeypatch):
    monkeypatch.setattr(svc, "datetime", _RelojFijo)


class _Ticket:
    def __init__(self, **kw):
        for c in CAMPOS:
            setattr(self, c, None)
        self.created_at = AHORA - timedelta(hours=5)
        self.sla_policy_id = None
        for k, v in kw.items():
            setattr(self, k, v)

    def __getattr__(self, _n):
        return None


class _Payload:
    def __init__(self, **kw):
        self._datos = kw
        for k, v in kw.items():
            setattr(self, k, v)

    def __getattr__(self, _n):
        return None

    def model_dump(self, exclude_unset=True):  # noqa: ARG002
        return dict(self._datos)


class _Consulta:
    def filter(self, *a, **k):
        return self

    def first(self):
        return None

    def all(self):
        return []


class _DBFalsa:
    def query(self, *a, **k):
        return _Consulta()

    def add(self, *a, **k):
        pass

    def flush(self):
        pass


def _aplicar(ticket, payload):
    return svc.apply_ticket_update(
        db=_DBFalsa(), ticket=ticket, ticket_id="T-1", payload=payload,
        current_user_id="u1", old_assigned_to=None,
        old_support_level=None, organization_id="o1",
    )


# ── La duplicación que se eliminó ─────────────────────────────────────────────

def test_reanudar_el_sla_acumula_el_tiempo_en_pausa():
    """El bloque que estaba duplicado, ahora en un solo sitio."""
    t = _Ticket(sla_paused_at=AHORA - timedelta(minutes=90), sla_pause_minutes=30)
    svc._reanudar_sla_pausado(t, AHORA)
    assert t.sla_pause_minutes == 120, "debe SUMAR a los minutos ya acumulados"
    assert t.sla_paused_at is None, "el reloj queda reanudado"


def test_reanudar_interpreta_una_pausa_sin_zona_como_utc():
    """Los timestamps almacenados son UTC; tratarlos como hora local los
    desplazaría por el offset del servidor."""
    t = _Ticket(sla_paused_at=datetime(2026, 9, 2, 10, 30))
    svc._reanudar_sla_pausado(t, AHORA)
    assert t.sla_pause_minutes == 90


def test_reanudar_no_hace_nada_si_no_estaba_en_pausa():
    t = _Ticket(sla_pause_minutes=45)
    svc._reanudar_sla_pausado(t, AHORA)
    assert t.sla_pause_minutes == 45
    assert t.sla_paused_at is None


def test_las_dos_ramas_que_reanudaban_lo_hacen_igual():
    """`in_progress` y cualquier otro estado compartían el bloque duplicado.

    Este test es el que se pondría rojo si alguien vuelve a duplicarlo y las dos
    copias divergen.
    """
    a = _Ticket(status="pending_client", sla_paused_at=AHORA - timedelta(minutes=45))
    b = _Ticket(status="pending_client", sla_paused_at=AHORA - timedelta(minutes=45))
    _aplicar(a, _Payload(status="in_progress"))
    _aplicar(b, _Payload(status="open"))
    assert a.sla_pause_minutes == b.sla_pause_minutes == 45
    assert a.sla_paused_at is b.sla_paused_at is None


# ── Cada transición ───────────────────────────────────────────────────────────

def test_paso_a_en_progreso_sella_la_primera_respuesta():
    t = _Ticket(status="open")
    _aplicar(t, _Payload(status="in_progress"))
    assert t.first_response_at == AHORA
    assert t.first_response_minutes == 300, "5 horas desde la creación"


def test_en_progreso_no_resella_una_respuesta_ya_dada():
    previa = AHORA - timedelta(hours=3)
    t = _Ticket(status="open", first_response_at=previa)
    _aplicar(t, _Payload(status="in_progress"))
    assert t.first_response_at == previa


def test_en_progreso_marca_el_sla_de_respuesta_incumplido():
    t = _Ticket(status="open", sla_response_due=AHORA - timedelta(hours=1))
    _aplicar(t, _Payload(status="in_progress"))
    assert t.sla_response_breached is True


def test_en_progreso_no_marca_un_sla_a_tiempo():
    t = _Ticket(status="open", sla_response_due=AHORA + timedelta(hours=1))
    _aplicar(t, _Payload(status="in_progress"))
    assert t.sla_response_breached is False


def test_resolver_sella_los_tiempos():
    t = _Ticket(status="in_progress")
    _aplicar(t, _Payload(status="resolved"))
    assert t.resolved_at == AHORA
    assert t.resolution_minutes == 300


def test_resolver_sin_haber_respondido_sella_tambien_la_primera_respuesta():
    """Un ticket puede resolverse sin pasar por «en progreso»: entonces la
    primera respuesta es esa misma resolución."""
    t = _Ticket(status="open")
    _aplicar(t, _Payload(status="resolved"))
    assert t.first_response_at == AHORA


def test_el_tiempo_en_pausa_se_descuenta_del_sla_de_resolucion():
    """Lo importante de esta prueba: el reloj NO corre mientras se espera al
    cliente, así que no descontar la pausa marcaría como incumplido un SLA que
    se respetó."""
    t = _Ticket(status="in_progress", sla_pause_minutes=120,
                sla_resolution_due=AHORA - timedelta(minutes=60))
    _aplicar(t, _Payload(status="resolved"))
    assert t.sla_resolution_breached is False, (
        "con 120 min de pausa, un vencimiento hace 60 min NO está incumplido"
    )


def test_sin_pausa_un_vencimiento_pasado_si_esta_incumplido():
    t = _Ticket(status="in_progress", sla_resolution_due=AHORA - timedelta(hours=2))
    _aplicar(t, _Payload(status="resolved"))
    assert t.sla_resolution_breached is True


def test_cerrar_sella_la_fecha_y_pide_la_encuesta():
    t = _Ticket(status="resolved")
    _aplicar(t, _Payload(status="closed"))
    assert t.closed_at == AHORA
    assert t.csat_requested_at == AHORA


def test_cerrar_no_vuelve_a_pedir_la_encuesta():
    previa = AHORA - timedelta(days=1)
    t = _Ticket(status="resolved", csat_requested_at=previa)
    _aplicar(t, _Payload(status="closed"))
    assert t.csat_requested_at == previa


@pytest.mark.parametrize("estado", ["pending_client", "pending_third"])
def test_pasar_a_espera_para_el_reloj(estado, monkeypatch):
    guardados = []
    monkeypatch.setattr(
        svc, "save_pending_snapshot", lambda db, tk: guardados.append(tk)
    )
    t = _Ticket(status="in_progress")
    _aplicar(t, _Payload(status=estado))
    assert t.sla_paused_at == AHORA
    assert len(guardados) == 1, "se guarda una instantánea antes de parar el reloj"


# ── Prioridad ─────────────────────────────────────────────────────────────────

def test_cambiar_la_urgencia_recalcula_la_prioridad():
    t = _Ticket(status="open", urgency="high", impact="enterprise")
    _aplicar(t, _Payload(urgency="high"))
    assert t.priority is not None


def test_una_prioridad_explicita_manda_sobre_la_matriz():
    """Una decisión de una persona no la sobrescribe el cálculo automático.

    El mecanismo: el bucle genérico de campos aplica `priority` del payload, y
    `_recalcular_prioridad` sale sin hacer nada al ver que viene fijada. Escribí
    este test al revés la primera vez —esperando que la matriz no aplicase nada—
    y el código tenía razón: la prioridad explícita se aplica, y la matriz es la
    que se abstiene.
    """
    t = _Ticket(status="open", urgency="high", impact="enterprise", priority="p4_low")
    _aplicar(t, _Payload(urgency="high", priority="p1_critical"))
    assert t.priority == "p1_critical", "la prioridad explícita del payload debe aplicarse"


def test_no_se_recalculan_los_vencimientos_de_un_ticket_resuelto():
    """Su reloj ya paró: recalcular vencimientos falsearía las métricas."""
    t = _Ticket(status="resolved", urgency="high", impact="enterprise")
    _aplicar(t, _Payload(urgency="high"))
    assert t.sla_response_due is None
    assert t.sla_resolution_due is None


# ── El valor devuelto ─────────────────────────────────────────────────────────

@pytest.mark.parametrize("estado,espera", [
    ("resolved", True), ("closed", True),
    ("in_progress", False), ("open", False),
])
def test_solo_resolver_o_cerrar_registra_el_resultado_del_encaminamiento(estado, espera):
    t = _Ticket(status="open")
    r = _aplicar(t, _Payload(status=estado))
    assert r["record_routing_outcome"] is espera


def test_se_detecta_la_reasignacion():
    t = _Ticket(status="open")
    r = svc.apply_ticket_update(
        db=_DBFalsa(), ticket=t, ticket_id="T-1",
        payload=_Payload(assigned_to_user_id="u2"),
        current_user_id="u1", old_assigned_to="u1",
        old_support_level=None, organization_id="o1",
    )
    assert r["reassigned"] is True


def test_no_hay_reasignacion_si_el_responsable_no_cambia():
    t = _Ticket(status="open")
    r = svc.apply_ticket_update(
        db=_DBFalsa(), ticket=t, ticket_id="T-1",
        payload=_Payload(assigned_to_user_id="u1"),
        current_user_id="u1", old_assigned_to="u1",
        old_support_level=None, organization_id="o1",
    )
    assert r["reassigned"] is False


# ── Que la descomposición sigue en pie ────────────────────────────────────────

def test_la_tabla_de_estados_cubre_las_cinco_transiciones():
    """Un estado que se añada al panel sin registrar su función caería en el
    camino por defecto y sólo reanudaría el SLA, en silencio."""
    assert set(svc._POR_ESTADO) == {
        "in_progress", "resolved", "closed", "pending_client", "pending_third",
    }
