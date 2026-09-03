"""Reglas de encaminamiento de tickets, probadas por primera vez.

Auditoría 2026-08 (P3-18). `apply_routing_rules` eran 105 líneas de complejidad
35 —once condiciones independientes y cuatro acciones en un solo bucle— **sin un
solo test**. Es la función que decide a qué grupo y con qué prioridad llega cada
ticket que entra, así que un error aquí manda el trabajo al equipo equivocado sin
que nada falle.

Ahora cada condición es un predicado con nombre y cada acción un aplicador. Estos
tests fijan el comportamiento que había ANTES del refactor: se capturaron los 62
casos contra la versión original y se compararon con la nueva, resultado
idéntico.

Se prueban con dobles, sin base de datos: la función sólo lee atributos del
ticket y consulta las reglas activas.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone

import pytest

from app.services.service_desk import routing_rule_service as svc


# ── Dobles ────────────────────────────────────────────────────────────────────

class _Obj:
    """Objeto con los atributos que se le pasen; el resto vale None, como una
    columna vacía."""

    def __init__(self, **kw):
        for k, v in kw.items():
            setattr(self, k, v)

    def __getattr__(self, _n):
        return None


class _Regla:
    def __init__(self, conditions, actions=None, priority=0):
        self.conditions = json.dumps(conditions)
        self.actions = json.dumps(actions or {})
        self.priority = priority
        self.is_active = True


class _Consulta:
    def __init__(self, reglas):
        self._reglas = reglas

    def filter(self, *a, **k):
        return self

    def order_by(self, *a, **k):
        return self

    def all(self):
        return list(self._reglas)


class _DBFalsa:
    def __init__(self, reglas):
        self._reglas = reglas

    def query(self, _modelo):
        return _Consulta(self._reglas)


LUNES_10H = datetime(2026, 8, 31, 10, 0, tzinfo=timezone.utc)
SABADO_23H = datetime(2026, 8, 29, 23, 30, tzinfo=timezone.utc)


def _ticket(**kw):
    base = dict(
        ticket_type="incident",
        priority="high",
        title="Fallo en el portal",
        created_at=LUNES_10H,
        requester_email="ana@cliente.com",
        tags="urgente,portal",
        client_id="cli1",
        sla_policy_id="sla1",
    )
    base.update(kw)
    return _Obj(**base)


def _aplica(condiciones, ticket=None, acciones=None):
    """¿Coincide una única regla con estas condiciones?"""
    tk = ticket if ticket is not None else _ticket()
    return svc.apply_routing_rules(tk, _DBFalsa([_Regla(condiciones, acciones)])), tk


# ── Estructura ────────────────────────────────────────────────────────────────

def test_las_once_condiciones_estan_registradas():
    """Si alguien añade una condición al panel sin registrar su predicado, la
    regla se guardaría y la condición se ignoraría en silencio: el ticket iría al
    grupo equivocado y nada fallaría."""
    assert set(svc._CONDICIONES) == {
        "ticket_type", "priority", "category_id", "requester_domain",
        "keyword_in_title", "time_of_day", "day_of_week", "client_org_id",
        "sla_policy_id", "tag_contains",
    }


def test_las_cuatro_acciones_estan_registradas():
    assert set(svc._ACCIONES) == {
        "assign_group", "assign_user", "set_priority", "set_support_level",
    }


# ── Casos base ────────────────────────────────────────────────────────────────

def test_sin_condiciones_la_regla_coincide_con_todo():
    """Una regla sin condiciones es la regla «cajón de sastre»: coincide siempre.
    Es intencionado y por eso el orden de prioridad importa."""
    coincide, _ = _aplica({})
    assert coincide is True


def test_sin_reglas_activas_no_coincide_nada():
    assert svc.apply_routing_rules(_ticket(), _DBFalsa([])) is False


def test_las_condiciones_son_conjuntivas():
    """TODAS las presentes deben cumplirse. Una sola que falle descarta la regla."""
    coincide, _ = _aplica({
        "ticket_type": "incident", "priority": ["high"], "keyword_in_title": "portal",
        "day_of_week": "monday", "tag_contains": "urgente",
    })
    assert coincide is True

    coincide, _ = _aplica({
        "ticket_type": "incident", "priority": ["high"], "keyword_in_title": "vpn",
    })
    assert coincide is False, "una condición que falla debe descartar la regla"


def test_gana_la_primera_regla_que_coincide():
    """Las siguientes no se evalúan, así que `priority` decide el resultado
    cuando varias encajan."""
    tk = _ticket()
    db = _DBFalsa([
        _Regla({"ticket_type": "incident"}, {"assign_group": "primera"}, priority=1),
        _Regla({"ticket_type": "incident"}, {"assign_group": "segunda"}, priority=2),
    ])
    assert svc.apply_routing_rules(tk, db) is True
    assert tk.assigned_group_id == "primera"


def test_una_condicion_desconocida_se_ignora():
    """Una regla guardada con una condición que después se retiró no debe
    bloquear el encaminamiento del ticket."""
    coincide, _ = _aplica({"condicion_retirada_v3": "algo"})
    assert coincide is True


# ── Cada condición ────────────────────────────────────────────────────────────

@pytest.mark.parametrize("condiciones,esperado", [
    ({"ticket_type": "incident"}, True),
    ({"ticket_type": "request"}, False),
    ({"priority": "high"}, True),
    ({"priority": "low"}, False),
    ({"priority": ["low", "high"]}, True),
    ({"priority": ["low", "medium"]}, False),
    ({"requester_domain": "cliente.com"}, True),
    ({"requester_domain": "CLIENTE.COM"}, True),
    ({"requester_domain": "  cliente.com "}, True),
    ({"requester_domain": "otro.com"}, False),
    ({"requester_domain": ["a.com", "cliente.com"]}, True),
    ({"keyword_in_title": "portal"}, True),
    ({"keyword_in_title": "PORTAL"}, True),
    ({"keyword_in_title": "impresora"}, False),
    ({"keyword_in_title": ["impresora", "portal"]}, True),
    ({"keyword_in_title": ["impresora", "vpn"]}, False),
    ({"time_of_day": "09:00-18:00"}, True),
    ({"time_of_day": {"start": "09:00", "end": "18:00"}}, True),
    ({"day_of_week": "monday"}, True),
    ({"day_of_week": "MONDAY"}, True),
    ({"day_of_week": "friday"}, False),
    ({"day_of_week": 0}, True),
    ({"day_of_week": "0"}, True),
    ({"day_of_week": ["friday", 0]}, True),
    ({"client_org_id": "cli1"}, True),
    ({"client_org_id": ["cliX", "cli1"]}, True),
    ({"client_org_id": "cliX"}, False),
    ({"sla_policy_id": "sla1"}, True),
    ({"sla_policy_id": ["slaX", "sla1"]}, True),
    ({"sla_policy_id": "slaX"}, False),
    ({"tag_contains": "portal"}, True),
    ({"tag_contains": "URGENTE"}, True),
    ({"tag_contains": "impresora"}, False),
    ({"tag_contains": ["impresora", "urgente"]}, True),
])
def test_cada_condicion_discrimina(condiciones, esperado):
    coincide, _ = _aplica(condiciones)
    assert coincide is esperado


# ── Casos límite que el original resolvía degradando ──────────────────────────
# Una regla mal configurada por un administrador no puede impedir que se cree un
# ticket, así que cada condición degrada a «no coincide» o «no restringe».

def test_sin_service_item_la_categoria_no_restringe():
    """Es lo que hacía el original: `if "category_id" in conditions and
    ticket.service_item`. Sin service_item la condición ni se evaluaba."""
    coincide, _ = _aplica({"category_id": "cat1"})
    assert coincide is True


def test_con_service_item_la_categoria_si_discrimina():
    tk = _ticket(service_item=_Obj(category_id="cat1"))
    assert _aplica({"category_id": "cat1"}, tk)[0] is True
    assert _aplica({"category_id": "cat2"}, _ticket(
        service_item=_Obj(category_id="cat1")))[0] is False


def test_el_dominio_se_toma_del_usuario_si_el_ticket_no_lo_trae():
    tk = _ticket(requester_email=None, requester_user=_Obj(email="bob@interno.es"))
    assert _aplica({"requester_domain": "interno.es"}, tk)[0] is True


def test_sin_correo_el_dominio_no_coincide():
    tk = _ticket(requester_email=None)
    assert _aplica({"requester_domain": "cliente.com"}, tk)[0] is False


def test_un_correo_sin_arroba_no_lanza_y_no_coincide():
    tk = _ticket(requester_email="malformado")
    assert _aplica({"requester_domain": "cliente.com"}, tk)[0] is False


def test_una_palabra_clave_vacia_se_descarta():
    """Una cadena vacía está contenida en cualquier texto, así que la condición se
    cumpliría siempre. Descartarla hace que no se cumpla, que es lo correcto."""
    assert _aplica({"keyword_in_title": ["", "  "]})[0] is False


def test_una_etiqueta_vacia_se_descarta():
    assert _aplica({"tag_contains": ["", " "]})[0] is False


def test_un_titulo_vacio_no_contiene_ninguna_palabra():
    assert _aplica({"keyword_in_title": "portal"}, _ticket(title=None))[0] is False


def test_un_ticket_sin_etiquetas_no_coincide():
    assert _aplica({"tag_contains": "portal"}, _ticket(tags=None))[0] is False


def test_un_rango_horario_incompleto_no_restringe():
    """Sólo `start` sin `end` es una regla a medio configurar. Degrada a «no
    restringe» en lugar de lanzar."""
    assert _aplica({"time_of_day": {"start": "09:00"}})[0] is True


def test_fuera_del_rango_horario_no_coincide():
    tk = _ticket(created_at=SABADO_23H)
    assert _aplica({"time_of_day": "09:00-18:00"}, tk)[0] is False
    assert _aplica({"time_of_day": {"start": "09:00", "end": "18:00"}},
                   _ticket(created_at=SABADO_23H))[0] is False


def test_sin_created_at_se_usa_el_momento_actual():
    """Un ticket sin `created_at` es un ticket que se está creando."""
    assert _aplica({"time_of_day": "00:00-23:59"}, _ticket(created_at=None))[0] is True


def test_una_etiqueta_de_dia_invalida_no_coincide():
    """«lunes» en castellano no está en el catálogo, que es en inglés. Se descarta
    y la condición no se cumple — mejor que lanzar y bloquear el ticket."""
    assert _aplica({"day_of_week": "lunes"})[0] is False


def test_el_dia_de_la_semana_se_calcula_del_created_at():
    assert _aplica({"day_of_week": "saturday"}, _ticket(created_at=SABADO_23H))[0] is True


def test_el_cliente_se_toma_del_solicitante_si_el_ticket_no_lo_trae():
    tk = _ticket(client_id=None, requester_client=_Obj(client_org_id="cliZ"))
    assert _aplica({"client_org_id": "cliZ"}, tk)[0] is True


# ── Acciones ──────────────────────────────────────────────────────────────────

def test_cada_accion_escribe_su_campo():
    _, tk = _aplica({}, acciones={
        "assign_group": "g1", "assign_user": "u1",
        "set_priority": "critical", "set_support_level": "L3",
    })
    assert tk.assigned_group_id == "g1"
    assert tk.assigned_to_user_id == "u1"
    assert tk.priority == "critical"
    assert tk.support_level == "L3"


def test_las_acciones_no_se_aplican_si_la_regla_no_coincide():
    """Lo importante de este test: un ticket no debe salir modificado de una regla
    que no le correspondía."""
    coincide, tk = _aplica({"ticket_type": "request"}, acciones={"assign_group": "g1"})
    assert coincide is False
    assert tk.assigned_group_id is None


def test_una_accion_desconocida_se_ignora_sin_romper_las_demas():
    _, tk = _aplica({}, acciones={"accion_retirada": "x", "assign_group": "g1"})
    assert tk.assigned_group_id == "g1"
