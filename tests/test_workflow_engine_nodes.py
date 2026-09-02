"""Los nodos del motor de flujos del service desk, uno por uno.

Auditoría 2026-08 (P3-18 + desajuste encontrado de paso). `_execute_node` era
complejidad 22: diez `if ntype == ...` secuenciales, cada uno con su `return` de
tres elementos. Es la función que decide **qué se ejecuta en cada nodo** de un
flujo, y no tenía ningún test que ejecutara un nodo: la cobertura que había era
del diseñador (validar y publicar el grafo), no del motor.

## El desajuste que apareció al escribir la tabla

Tres capas no coinciden sobre el tipo de nodo `action` («Acción»):

| Capa | ¿Soporta `action`? |
|---|---|
| Catálogo y `validate_graph` | sí |
| Editor del diseñador | **no** — no ofrece ni un campo |
| Motor `_execute_node` | **no** — lanza `ValueError` |

El catálogo lo incluye a propósito (su comentario lo dice) porque hay grafos que
lo usan y `validate_graph` los rechazaba. Así que no se retira. Y no se
implementa: `action` + `params` no dice qué debe hacer, el diseñador no ofrece
campos para rellenarlo, y una de las acciones que su comentario menciona es
`run_script` — ejecutar un script arbitrario guardado en una definición de flujo
es una superficie de ejecución remota de código, y eso no se decide en un
refactor.

Lo que sí se hizo: `validate_graph` **avisa al guardar**. Antes el flujo se
guardaba como válido y moría al llegar el primer caso real.
"""
from __future__ import annotations

import json
from types import SimpleNamespace

import pytest

from app.services.service_desk.workflow_engine import (
    TIPOS_EJECUTABLES,
    WAIT,
    _execute_node,
)


def _run(contexto=None, **campos) -> SimpleNamespace:
    base = dict(
        context_json=contexto if contexto is not None else {},
        target_entity_id=None,
        target_entity_type=None,
        organization_id="1",
    )
    base.update(campos)
    return SimpleNamespace(**base)


# ── Los nodos triviales ───────────────────────────────────────────────────────

def test_el_nodo_de_inicio_sigue_adelante():
    assert _execute_node("start", {}, _run(), None) == ("next", {}, 0)


def test_el_nodo_final_termina():
    assert _execute_node("end", {}, _run(), None) == ("end", {}, 0)


def test_un_tipo_desconocido_lanza_y_no_sigue_en_silencio():
    """Lanzar y no devolver «next» es lo correcto: un nodo que no se sabe
    ejecutar y deja pasar el flujo lo dejaría avanzar como si hubiera hecho su
    trabajo, y el run acabaría en éxito sin haberlo hecho."""
    with pytest.raises(ValueError, match="no soportado por el motor"):
        _execute_node("tipo_inventado", {}, _run(), None)


# ── Estado: escribe en el contexto, que es lo que ve la siguiente decisión ────

def test_el_nodo_de_estado_escribe_en_el_contexto_del_run():
    """La razón de que el contexto se pase como el MISMO diccionario que se
    guarda: si `state` escribiera en una copia, la decisión siguiente evaluaría
    el estado anterior y el flujo tomaría la rama equivocada."""
    run = _run({"otro": 1})
    rama, payload, espera = _execute_node("state", {"status": "in_progress"}, run, None)

    assert rama == "next"
    assert espera == 0
    assert run.context_json["status"] == "in_progress"
    assert run.context_json["otro"] == 1, "no puede perder lo que ya había"
    assert payload["status"] == "in_progress"


def test_un_estado_sin_status_no_toca_el_contexto():
    run = _run({"status": "open"})
    _execute_node("state", {"assignee_role": "support_l1"}, run, None)
    assert run.context_json == {"status": "open"}


def test_el_estado_devuelve_tambien_el_rol_y_el_sla():
    _, payload, _ = _execute_node(
        "state", {"status": "open", "assignee_role": "l2", "sla_hours": 4}, _run(), None
    )
    assert payload == {"status": "open", "assignee_role": "l2", "sla_hours": 4}


# ── Decisión: la rama depende del resultado de la expresión ───────────────────

def test_la_decision_toma_la_rama_verdadera(monkeypatch):
    run = _run({"priority": "p1_critical"})
    rama, payload, _ = _execute_node(
        "decision", {"expression": "priority == 'p1_critical'"}, run, None
    )
    assert rama == "true"
    assert payload["result"] is True


def test_la_decision_toma_la_rama_falsa():
    run = _run({"priority": "p3_medium"})
    rama, payload, _ = _execute_node(
        "decision", {"expression": "priority == 'p1_critical'"}, run, None
    )
    assert rama == "false"
    assert payload["result"] is False


def test_una_decision_sin_expresion_no_revienta():
    """Cae en la rama falsa. Un grafo a medio configurar no puede tumbar el run."""
    rama, _, _ = _execute_node("decision", {}, _run(), None)
    assert rama in ("true", "false")


# ── Aprobación y espera: las dos bloquean ─────────────────────────────────────

def test_la_aprobacion_bloquea_esperando_a_alguien():
    """No emite nada: alguien externo debe llamar a /resume."""
    rama, payload, espera = _execute_node(
        "approval", {"approver_role": "manager", "deadline_hours": 24}, _run(), None
    )
    assert rama == WAIT
    assert espera == 0
    assert payload["approver_role"] == "manager"


def test_la_espera_convierte_minutos_en_segundos():
    rama, _, espera = _execute_node("wait", {"wait_minutes": 15}, _run(), None)
    assert rama == WAIT
    assert espera == 900


@pytest.mark.parametrize("valor", ["no es un número", None, "", {}, [1]])
def test_una_espera_ilegible_cuenta_como_cero(valor):
    """Cero y no un error a propósito: un temporizador mal configurado no puede
    dejar el flujo colgado para siempre. Sigue de inmediato."""
    _, _, espera = _execute_node("wait", {"wait_minutes": valor}, _run(), None)
    assert espera == 0


def test_una_espera_de_minutos_en_texto_si_se_entiende():
    """El diseñador manda los números como texto desde un input HTML."""
    _, _, espera = _execute_node("wait", {"wait_minutes": "30"}, _run(), None)
    assert espera == 1800


# ── Notificar ─────────────────────────────────────────────────────────────────

def test_notificar_a_un_rol_usa_notify_role(monkeypatch):
    llamadas = []
    monkeypatch.setattr(
        "app.services.notifications.notify_role",
        lambda db, rol, *a, **k: llamadas.append(rol) or 3,
    )
    rama, payload, _ = _execute_node(
        "notify", {"recipients": "support_l1", "title": "Hola", "body": "Cuerpo"},
        _run(), None,
    )
    assert rama == "next"
    assert llamadas == ["support_l1"]
    assert payload["notified_count"] == 3
    assert payload["delivered"] is True


def test_notificar_a_una_lista_usa_notify_user_una_vez_por_usuario(monkeypatch):
    enviados = []
    monkeypatch.setattr(
        "app.services.notifications.notify_user",
        lambda db, uid, *a, **k: enviados.append(uid),
    )
    _, payload, _ = _execute_node(
        "notify", {"recipients": ["u1", "u2", "u3"], "title": "T"}, _run(), None
    )
    assert enviados == ["u1", "u2", "u3"]
    assert payload["notified_count"] == 3


def test_si_la_notificacion_falla_el_flujo_toma_la_rama_de_fallo(monkeypatch):
    """Y no propaga: el nodo `notify` declara la rama `failure`, así que el flujo
    puede tratar el problema en vez de morir el run entero."""
    def revienta(*a, **k):
        raise RuntimeError("el servicio de avisos no responde")

    monkeypatch.setattr("app.services.notifications.notify_role", revienta)
    rama, payload, _ = _execute_node(
        "notify", {"recipients": "l1", "title": "T"}, _run(), None
    )
    assert rama == "failure"
    assert payload["delivered"] == 0
    assert "no responde" in payload["error"]


def test_el_error_de_notificacion_se_recorta(monkeypatch):
    """El payload se guarda en base: un mensaje enorme no puede llenar la fila."""
    def revienta(*a, **k):
        raise RuntimeError("x" * 5000)

    monkeypatch.setattr("app.services.notifications.notify_role", revienta)
    _, payload, _ = _execute_node("notify", {"recipients": "l1"}, _run(), None)
    assert len(payload["error"]) <= 300


def test_notificar_sin_destinatarios_no_manda_nada_pero_sigue(monkeypatch):
    monkeypatch.setattr(
        "app.services.notifications.notify_role",
        lambda *a, **k: pytest.fail("no debería llamarse sin destinatarios"),
    )
    rama, payload, _ = _execute_node("notify", {"title": "T"}, _run(), None)
    assert rama == "next"
    assert payload["notified_count"] == 0


# ── Llamada HTTP ──────────────────────────────────────────────────────────────

class _Respuesta:
    def __init__(self, status_code, text=""):
        self.status_code = status_code
        self.text = text


class _ClienteFalso:
    def __init__(self, respuesta=None, error=None):
        self._r = respuesta
        self._e = error
        self.llamadas = []

    def __call__(self, *a, **k):
        return self

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def request(self, method, url, **k):
        self.llamadas.append((method, url, k))
        if self._e:
            raise self._e
        return self._r


def _con_httpx(monkeypatch, cliente):
    import httpx
    monkeypatch.setattr(httpx, "Client", cliente)


@pytest.mark.parametrize("codigo,rama", [
    (200, "success"), (201, "success"), (299, "success"),
    (300, "failure"), (404, "failure"), (500, "failure"),
])
def test_la_llamada_http_ramifica_por_el_codigo(monkeypatch, codigo, rama):
    """2xx es éxito y el resto fallo. El 300 en la frontera importa: un
    `<= 300` en vez de `< 300` trataría una redirección como éxito."""
    _con_httpx(monkeypatch, _ClienteFalso(_Respuesta(codigo, "cuerpo")))
    r, payload, _ = _execute_node(
        "http_call", {"url": "https://x/y", "method": "post"}, _run(), None
    )
    assert r == rama
    assert payload["status_code"] == codigo


def test_el_metodo_http_se_normaliza_a_mayusculas(monkeypatch):
    cliente = _ClienteFalso(_Respuesta(200))
    _con_httpx(monkeypatch, cliente)
    _execute_node("http_call", {"url": "https://x", "method": "post"}, _run(), None)
    assert cliente.llamadas[0][0] == "POST"


def test_sin_metodo_la_llamada_http_es_un_get(monkeypatch):
    cliente = _ClienteFalso(_Respuesta(200))
    _con_httpx(monkeypatch, cliente)
    _execute_node("http_call", {"url": "https://x"}, _run(), None)
    assert cliente.llamadas[0][0] == "GET"


def test_un_cuerpo_json_valido_va_como_json(monkeypatch):
    cliente = _ClienteFalso(_Respuesta(200))
    _con_httpx(monkeypatch, cliente)
    _execute_node(
        "http_call",
        {"url": "https://x", "method": "POST", "body_template": json.dumps({"a": 1})},
        _run(), None,
    )
    _, _, kwargs = cliente.llamadas[0]
    assert kwargs["json"] == {"a": 1}
    assert kwargs["content"] is None


def test_un_cuerpo_que_no_es_json_va_como_texto(monkeypatch):
    """El respaldo cuando la plantilla no es JSON: se manda tal cual en vez de
    perder el cuerpo o tumbar el nodo."""
    cliente = _ClienteFalso(_Respuesta(200))
    _con_httpx(monkeypatch, cliente)
    _execute_node(
        "http_call", {"url": "https://x", "method": "POST", "body_template": "no soy json"},
        _run(), None,
    )
    _, _, kwargs = cliente.llamadas[0]
    assert kwargs["json"] is None
    assert kwargs["content"] == "no soy json"


def test_una_llamada_http_caida_toma_la_rama_de_fallo(monkeypatch):
    _con_httpx(monkeypatch, _ClienteFalso(error=RuntimeError("sin red")))
    rama, payload, _ = _execute_node("http_call", {"url": "https://x"}, _run(), None)
    assert rama == "failure"
    assert "sin red" in payload["error"]


def test_la_respuesta_http_se_recorta(monkeypatch):
    _con_httpx(monkeypatch, _ClienteFalso(_Respuesta(200, "y" * 5000)))
    _, payload, _ = _execute_node("http_call", {"url": "https://x"}, _run(), None)
    assert len(payload["response"]) <= 500


# ── Crear ticket ──────────────────────────────────────────────────────────────

def test_crear_ticket_hereda_la_organizacion_del_run(db):
    """El aislamiento de tenant: el ticket que crea un flujo pertenece a la
    organización del run, no a ninguna por defecto. Sin esto, un flujo crearía
    tickets fuera de su cliente."""
    from app.models.service_desk import Ticket

    run = _run({}, organization_id="1", target_entity_id=None)
    rama, payload, _ = _execute_node(
        "create_ticket", {"title": "Desde el flujo", "queue": "support"}, run, db
    )
    assert rama == "next"
    assert payload["created"] is True

    t = db.query(Ticket).filter(Ticket.id == payload["ticket_id"]).first()
    assert t is not None
    assert t.organization_id == "1"
    assert t.source == "workflow"
    assert t.title == "Desde el flujo"


def test_el_numero_del_ticket_lo_da_el_generador_canonico(db):
    """Y no un cálculo propio del motor: dos generadores producirían números
    repetidos, y el número de ticket es lo que ve el cliente."""
    rama, payload, _ = _execute_node("create_ticket", {"title": "T"}, _run(), db)
    assert rama == "next"
    assert payload["ticket_number"]


def test_un_tipo_de_ticket_invalido_cae_en_incidencia(db):
    from app.models.service_desk import Ticket, TicketType

    _, payload, _ = _execute_node(
        "create_ticket", {"title": "T", "ticket_type": "no_existe"}, _run(), db
    )
    t = db.query(Ticket).filter(Ticket.id == payload["ticket_id"]).first()
    assert t.ticket_type == TicketType.incident


def test_una_prioridad_invalida_cae_en_normal(db):
    from app.models.service_desk import Ticket, TicketPriority

    _, payload, _ = _execute_node(
        "create_ticket", {"title": "T", "priority": "urgentisima"}, _run(), db
    )
    t = db.query(Ticket).filter(Ticket.id == payload["ticket_id"]).first()
    assert t.priority == TicketPriority.p3_medium


def test_el_titulo_del_ticket_se_recorta_a_500(db):
    from app.models.service_desk import Ticket

    _, payload, _ = _execute_node(
        "create_ticket", {"title": "z" * 900}, _run(), db
    )
    t = db.query(Ticket).filter(Ticket.id == payload["ticket_id"]).first()
    assert len(t.title) == 500


# ── Dos defectos de `create_ticket`, encontrados al escribir estos tests ──────

def test_un_create_ticket_sin_descripcion_si_crea_el_ticket(db):
    """El primero, y el peor: el nodo NO podía tener éxito nunca.

    `sd_tickets.description` es NOT NULL y el esquema de la API la declara
    obligatoria, pero el motor pasaba `... or None`. Y el editor del diseñador
    ofrecía sólo cola, plantilla de título y prioridad — **ningún campo de
    descripción**. Así que un nodo `create_ticket` configurado desde la interfaz
    reventaba el INSERT y tomaba la rama `failure` con `created: False`, siempre.

    Se cae al título, que es lo que una persona habría escrito, y ahora el editor
    tiene su campo.
    """
    from app.models.service_desk import Ticket

    rama, payload, _ = _execute_node(
        "create_ticket", {"title": "Sin descripción"}, _run(), db
    )
    assert rama == "next", payload.get("error")
    t = db.query(Ticket).filter(Ticket.id == payload["ticket_id"]).first()
    assert t.description == "Sin descripción"


def test_una_descripcion_explicita_manda_sobre_el_respaldo(db):
    from app.models.service_desk import Ticket

    _, payload, _ = _execute_node(
        "create_ticket",
        {"title": "Título", "description_template": "Descripción de verdad"},
        _run(), db,
    )
    t = db.query(Ticket).filter(Ticket.id == payload["ticket_id"]).first()
    assert t.description == "Descripción de verdad"


def test_un_fallo_al_crear_el_ticket_deja_la_sesion_usable(db):
    """El segundo defecto, y el que hacía daño más allá del nodo.

    El `except` devolvía `failure` sin `db.rollback()`. Un flush fallido deja la
    sesión en transacción abortada, así que **todo lo posterior del run** falla
    con «transaction has been rolled back»: el registro del paso, el avance del
    run e incluso `_record_error`, que es precisamente quien tiene que anotar el
    problema. Un nodo que falla tiene que dejar el run anotable.

    Se provoca un fallo real —un título que no cabe en la columna no basta porque
    se recorta, así que se rompe el generador de número— y después se comprueba
    que la sesión sigue sirviendo.
    """
    import app.services.sla_service as sla

    original = sla.next_ticket_number
    try:
        sla.next_ticket_number = lambda *a, **k: (_ for _ in ()).throw(
            RuntimeError("generador de número caído")
        )
        rama, payload, _ = _execute_node("create_ticket", {"title": "T"}, _run(), db)
    finally:
        sla.next_ticket_number = original

    assert rama == "failure"
    assert payload["created"] is False

    # Lo que importa: la sesión sigue viva después del fallo.
    from app.models.service_desk import Ticket
    assert db.query(Ticket).count() >= 0, "la sesión quedó en transacción abortada"

    # Y un nodo posterior puede trabajar con normalidad.
    rama2, payload2, _ = _execute_node(
        "create_ticket", {"title": "Después del fallo"}, _run(), db
    )
    assert rama2 == "next", payload2.get("error")


# ── El desajuste con el catálogo del diseñador ────────────────────────────────

def test_el_catalogo_y_el_motor_solo_difieren_en_action():
    """Fija el desajuste exactamente, en las dos direcciones.

    · Un tipo del catálogo que el motor no ejecute se guarda como válido y muere
      al ejecutarse — es lo que pasa con `action`.
    · Un tipo ejecutable que no esté en el catálogo no se puede diseñar, así que
      sería código muerto en el motor.

    `action` está en la lista de excepciones **con su razón**, no para tapar el
    problema: el día que alguien lo implemente o lo retire, este test falla y
    obliga a actualizar la lista. Es la misma forma que
    `DIFERENCIAS_ESPERADAS` en el test de equivalencia de métricas.
    """
    from app.services.service_desk.workflow_designer_service import ALLOWED_NODE_TYPES

    SIN_MOTOR = {"action"}   # en el catálogo, sin ejecutor; ver el docstring del módulo

    en_catalogo_sin_motor = set(ALLOWED_NODE_TYPES) - set(TIPOS_EJECUTABLES)
    assert en_catalogo_sin_motor == SIN_MOTOR, (
        f"el desajuste catálogo/motor ha cambiado: {en_catalogo_sin_motor}. "
        "Si se ha implementado o retirado un tipo, actualiza SIN_MOTOR."
    )

    ejecutables_fuera_del_catalogo = set(TIPOS_EJECUTABLES) - set(ALLOWED_NODE_TYPES)
    assert not ejecutables_fuera_del_catalogo, (
        f"el motor ejecuta tipos que no se pueden diseñar: {ejecutables_fuera_del_catalogo}"
    )


def test_action_sigue_lanzando_y_esta_documentado():
    """Que el desajuste no se cierre por accidente en silencio. Si alguien
    implementa `action`, este test y el de arriba fallan a la vez y le obligan a
    revisar los dos sitios."""
    with pytest.raises(ValueError, match="no soportado por el motor"):
        _execute_node("action", {"action": "set_priority"}, _run(), None)


def test_el_disenador_avisa_de_los_tipos_que_el_motor_no_ejecuta():
    """La mejora real: el problema se ve al GUARDAR, no al ejecutar.

    Antes el grafo se guardaba como válido y el fallo aparecía cuando ya había
    un caso real dentro, con el run en estado de error y sin que quien lo diseñó
    hubiera recibido ninguna señal.
    """
    from app.services.service_desk.workflow_designer_service import validate_graph

    grafo = {
        "nodes": [
            {"id": "s", "type": "start"},
            {"id": "a", "type": "action", "config": {"action": "set_priority"}},
            {"id": "e", "type": "end"},
        ],
        "edges": [
            {"source": "s", "target": "a", "branch": "next"},
            {"source": "a", "target": "e", "branch": "next"},
        ],
    }
    r = validate_graph(grafo)
    assert r["valid"] is True, "sigue siendo guardable: no se rompen los grafos existentes"
    assert any("no sabe ejecutarlo" in w for w in r["warnings"]), r["warnings"]


def test_un_grafo_solo_con_tipos_ejecutables_no_lleva_ese_aviso():
    from app.services.service_desk.workflow_designer_service import validate_graph

    grafo = {
        "nodes": [
            {"id": "s", "type": "start"},
            {"id": "st", "type": "state", "config": {"status": "open"}},
            {"id": "e", "type": "end"},
        ],
        "edges": [
            {"source": "s", "target": "st", "branch": "next"},
            {"source": "st", "target": "e", "branch": "next"},
        ],
    }
    r = validate_graph(grafo)
    assert not any("no sabe ejecutarlo" in w for w in r["warnings"]), r["warnings"]
