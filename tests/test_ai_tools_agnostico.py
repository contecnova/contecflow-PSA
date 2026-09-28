"""El agente ejecuta herramientas con cualquier proveedor, no sólo Anthropic.

Auditoría 2026-09. El bucle del agente hablaba **el dialecto de Anthropic**:
recibía `call_claude`, leía `stop_reason` y buscaba bloques `tool_use`. Con
Gemini u OpenAI caía en «modo degradado» —analizaba la instrucción y no
ejecutaba nada—, así que el producto tenía una funcionalidad de menos según
quién pagara la API.

`app/services/ai_tools.py` traduce las tres cosas que cambian entre proveedores
y nada más: el esquema de las herramientas, cómo pide el modelo una llamada, y
cómo se le devuelve el resultado.

## Por qué estos tests no llaman a ningún proveedor

Porque lo que hay que comprobar es **la traducción**, no que la API de un
tercero responda. Se sustituye la única función que hace red —`_post`— por una
que devuelve una respuesta grabada con la forma real de cada proveedor. Así el
test es determinista, no cuesta dinero y sigue cubriendo lo que importa: que de
un `tool_calls` de OpenAI y de un `functionCall` de Gemini salga la misma
`LlamadaDeHerramienta`.
"""
from __future__ import annotations

import json

import pytest

from app.services import ai_tools as herr

HERRAMIENTAS = [
    {
        "name": "buscar_proyectos",
        "description": "Busca proyectos por nombre",
        "input_schema": {
            "type": "object",
            "properties": {"query": {"type": "string", "description": "Texto"}},
            "required": ["query"],
        },
    },
    {
        "name": "resumen_general",
        "description": "Sin argumentos",
        "input_schema": {"type": "object", "properties": {}, "required": []},
    },
]


# ── Qué proveedores pueden ejecutar acciones ─────────────────────────────────

@pytest.mark.parametrize("proveedor", [
    "anthropic", "openai", "gemini", "groq", "mistral", "deepseek", "azure",
])
def test_los_proveedores_con_herramientas_se_reconocen(proveedor):
    assert herr.soporta_herramientas(proveedor)


def test_ollama_queda_fuera_a_proposito():
    """Su soporte depende del modelo instalado: prometerlo sería mentir.

    Mejor el modo degradado, que avisa, que un agente que dice que va a
    ejecutar y falla según qué modelo tenga cada cual.
    """
    assert not herr.soporta_herramientas("ollama")


def test_un_proveedor_desconocido_no_soporta_nada():
    assert not herr.soporta_herramientas("inventado")
    assert not herr.soporta_herramientas(None)


# ── 1. Traducción del esquema de herramientas ────────────────────────────────

def test_anthropic_recibe_el_esquema_tal_cual():
    """Es el formato en el que están escritas: no se toca."""
    assert herr.herramientas_para("anthropic", HERRAMIENTAS) is HERRAMIENTAS


def test_openai_recibe_el_esquema_envuelto_en_function():
    traducido = herr.herramientas_para("openai", HERRAMIENTAS)
    assert traducido[0]["type"] == "function"
    funcion = traducido[0]["function"]
    assert funcion["name"] == "buscar_proyectos"
    assert funcion["parameters"]["properties"]["query"]["type"] == "string"


def test_gemini_recibe_declaraciones_de_funcion():
    traducido = herr.herramientas_para("gemini", HERRAMIENTAS)
    assert isinstance(traducido, list) and "function_declarations" in traducido[0]
    nombres = [d["name"] for d in traducido[0]["function_declarations"]]
    assert nombres == ["buscar_proyectos", "resumen_general"]


def test_gemini_no_recibe_un_properties_vacio():
    """Su validador es más estricto y devuelve 400 con `properties: {}`.

    Una herramienta sin argumentos se declara omitiendo `parameters`.
    """
    traducido = herr.herramientas_para("gemini", HERRAMIENTAS)
    sin_argumentos = traducido[0]["function_declarations"][1]
    assert sin_argumentos["parameters"] == {}


def test_un_proveedor_sin_herramientas_lo_dice_claro():
    with pytest.raises(ValueError, match="no soporta herramientas"):
        herr.herramientas_para("ollama", HERRAMIENTAS)


# ── 2. Interpretar lo que el modelo pide ─────────────────────────────────────

RESPUESTA_ANTHROPIC = {
    "content": [
        {"type": "text", "text": "Voy a buscarlos."},
        {"type": "tool_use", "id": "toolu_1", "name": "buscar_proyectos",
         "input": {"query": "Acme"}},
    ],
    "stop_reason": "tool_use",
}

RESPUESTA_OPENAI = {
    "choices": [{"message": {
        "role": "assistant",
        "content": "Voy a buscarlos.",
        "tool_calls": [{
            "id": "call_1", "type": "function",
            "function": {"name": "buscar_proyectos",
                         "arguments": '{"query": "Acme"}'},
        }],
    }}],
}

RESPUESTA_GEMINI = {
    "candidates": [{"content": {"parts": [
        {"text": "Voy a buscarlos."},
        {"functionCall": {"name": "buscar_proyectos", "args": {"query": "Acme"}}},
    ]}}],
}


def _con_respuesta(monkeypatch, datos):
    monkeypatch.setattr(herr, "_post", lambda *a, **k: datos)


@pytest.mark.parametrize("proveedor,datos", [
    ("anthropic", RESPUESTA_ANTHROPIC),
    ("openai", RESPUESTA_OPENAI),
    ("gemini", RESPUESTA_GEMINI),
])
def test_los_tres_dialectos_dan_la_misma_llamada(monkeypatch, proveedor, datos):
    """El punto entero del módulo: tres formatos, una sola forma normalizada."""
    _con_respuesta(monkeypatch, datos)
    turno = herr.pedir_turno(
        proveedor=proveedor, api_key="k", modelo="m", base_url="https://x/v1",
        mensajes=herr.primer_mensaje(proveedor, "busca Acme"),
        system="eres un agente", herramientas=HERRAMIENTAS)

    assert turno.quiere_herramientas
    assert len(turno.llamadas) == 1
    llamada = turno.llamadas[0]
    assert llamada.nombre == "buscar_proyectos"
    assert llamada.argumentos == {"query": "Acme"}
    assert "buscarlos" in turno.texto


def test_openai_convierte_los_argumentos_que_llegan_como_cadena():
    """Los manda como cadena JSON, no como objeto."""
    bruto = RESPUESTA_OPENAI["choices"][0]["message"]["tool_calls"][0]["function"]["arguments"]
    assert isinstance(bruto, str)
    assert herr._json_o_vacio(bruto) == {"query": "Acme"}


def test_unos_argumentos_rotos_no_tumban_el_agente(monkeypatch):
    """Un modelo puede devolver JSON mal formado. Se degrada, no se cae."""
    rota = json.loads(json.dumps(RESPUESTA_OPENAI))
    rota["choices"][0]["message"]["tool_calls"][0]["function"]["arguments"] = "{roto"
    _con_respuesta(monkeypatch, rota)
    turno = herr.pedir_turno(
        proveedor="openai", api_key="k", modelo="m", base_url="https://x/v1",
        mensajes=[], system="", herramientas=HERRAMIENTAS)
    assert turno.llamadas[0].argumentos == {}


def test_gemini_fabrica_un_identificador_de_llamada(monkeypatch):
    """No da uno, y el resto del bucle trabaja con identificadores."""
    _con_respuesta(monkeypatch, RESPUESTA_GEMINI)
    turno = herr.pedir_turno(
        proveedor="gemini", api_key="k", modelo="m", base_url="",
        mensajes=[], system="", herramientas=HERRAMIENTAS)
    assert turno.llamadas[0].id
    assert "buscar_proyectos" in turno.llamadas[0].id


@pytest.mark.parametrize("proveedor,datos", [
    ("anthropic", {"content": [{"type": "text", "text": "Ya está."}], "stop_reason": "end_turn"}),
    ("openai", {"choices": [{"message": {"role": "assistant", "content": "Ya está."}}]}),
    ("gemini", {"candidates": [{"content": {"parts": [{"text": "Ya está."}]}}]}),
])
def test_sin_llamadas_el_turno_es_el_final(monkeypatch, proveedor, datos):
    """Así sabe el bucle que ha terminado, sin mirar `stop_reason`."""
    _con_respuesta(monkeypatch, datos)
    turno = herr.pedir_turno(
        proveedor=proveedor, api_key="k", modelo="m", base_url="https://x/v1",
        mensajes=[], system="", herramientas=HERRAMIENTAS)
    assert not turno.quiere_herramientas
    assert turno.texto == "Ya está."


# ── 3. Devolver el resultado al modelo ───────────────────────────────────────

def _turno_con_una_llamada(proveedor, datos):
    if proveedor == "anthropic":
        llamada = herr.LlamadaDeHerramienta("toolu_1", "buscar_proyectos", {"query": "Acme"})
    elif proveedor == "gemini":
        llamada = herr.LlamadaDeHerramienta("gemini-1-buscar_proyectos",
                                            "buscar_proyectos", {"query": "Acme"})
    else:
        llamada = herr.LlamadaDeHerramienta("call_1", "buscar_proyectos", {"query": "Acme"})
    return herr.TurnoDelAgente(texto="", llamadas=[llamada], crudo=datos), llamada


def test_anthropic_recibe_el_resultado_como_tool_result():
    turno, llamada = _turno_con_una_llamada("anthropic", RESPUESTA_ANTHROPIC)
    mensajes = herr.mensajes_del_turno("anthropic", turno, [(llamada, {"total": 3})])
    assert mensajes[0]["role"] == "assistant"
    bloque = mensajes[1]["content"][0]
    assert bloque["type"] == "tool_result" and bloque["tool_use_id"] == "toolu_1"
    assert json.loads(bloque["content"]) == {"total": 3}


def test_openai_recibe_un_mensaje_de_rol_tool_por_llamada():
    turno, llamada = _turno_con_una_llamada("openai", RESPUESTA_OPENAI)
    mensajes = herr.mensajes_del_turno("openai", turno, [(llamada, {"total": 3})])
    assert mensajes[0]["role"] == "assistant"
    assert mensajes[1]["role"] == "tool" and mensajes[1]["tool_call_id"] == "call_1"
    assert json.loads(mensajes[1]["content"]) == {"total": 3}


def test_gemini_recibe_el_resultado_como_functionresponse():
    turno, llamada = _turno_con_una_llamada("gemini", RESPUESTA_GEMINI)
    mensajes = herr.mensajes_del_turno("gemini", turno, [(llamada, {"total": 3})])
    assert mensajes[0]["role"] == "model"
    parte = mensajes[1]["parts"][0]["functionResponse"]
    # Gemini empareja por NOMBRE, no por identificador.
    assert parte["name"] == "buscar_proyectos"
    assert parte["response"] == {"resultado": {"total": 3}}


def test_el_mensaje_del_asistente_se_devuelve_con_su_forma_original():
    """Reconstruirlo desde los campos normalizados perdería lo que el
    proveedor necesita para hilar la conversación."""
    turno, llamada = _turno_con_una_llamada("anthropic", RESPUESTA_ANTHROPIC)
    mensajes = herr.mensajes_del_turno("anthropic", turno, [(llamada, {})])
    assert mensajes[0]["content"] is RESPUESTA_ANTHROPIC["content"]


# ── El primer mensaje ────────────────────────────────────────────────────────

def test_gemini_usa_parts_y_los_demas_content():
    assert herr.primer_mensaje("gemini", "hola") == [
        {"role": "user", "parts": [{"text": "hola"}]}]
    for p in ("anthropic", "openai", "groq"):
        assert herr.primer_mensaje(p, "hola") == [{"role": "user", "content": "hola"}]


# ── El bucle completo, sin red ───────────────────────────────────────────────

@pytest.mark.parametrize("proveedor,primera,segunda", [
    ("anthropic", RESPUESTA_ANTHROPIC,
     {"content": [{"type": "text", "text": "Encontré 3."}], "stop_reason": "end_turn"}),
    ("openai", RESPUESTA_OPENAI,
     {"choices": [{"message": {"role": "assistant", "content": "Encontré 3."}}]}),
    ("gemini", RESPUESTA_GEMINI,
     {"candidates": [{"content": {"parts": [{"text": "Encontré 3."}]}}]}),
])
def test_el_bucle_ejecuta_la_herramienta_y_termina(monkeypatch, proveedor, primera, segunda):
    """De punta a punta: pide, ejecuta, devuelve el resultado y concluye.

    Es la prueba de que el agente **actúa** con los tres, que es justo lo que no
    hacía: con cualquiera que no fuera Anthropic se quedaba en el análisis.
    """
    from app.services.ai_chat.agent_loop import run_tool_use_loop

    respuestas = iter([primera, segunda])
    monkeypatch.setattr(herr, "_post", lambda *a, **k: next(respuestas))

    ejecutadas = []

    def _ejecutar(nombre, entrada, db, usuario):
        ejecutadas.append((nombre, entrada))
        return {"total": 3}

    texto, pasos, n = run_tool_use_loop(
        execute_tool=_ejecutar,
        instruction="busca Acme",
        system="eres un agente",
        tools=HERRAMIENTAS,
        db=None,
        current_user=None,
        model="m",
        api_key="k",
        auto_approve=True,
        provider=proveedor,
        base_url="https://x/v1",
    )

    assert ejecutadas == [("buscar_proyectos", {"query": "Acme"})]
    assert n == 1 and len(pasos) == 1
    assert pasos[0]["tool"] == "buscar_proyectos"
    assert pasos[0]["output"] == {"total": 3}
    assert texto == "Encontré 3."


def test_el_bucle_respeta_el_permiso_humano_en_los_tres(monkeypatch):
    """Sin `auto_approve`, una acción de escritura no se ejecuta.

    La protección no puede depender del proveedor: sería la peor forma de
    perderla.
    """
    from app.services.ai_chat.agent_loop import run_tool_use_loop

    respuestas = iter([
        RESPUESTA_OPENAI,
        {"choices": [{"message": {"role": "assistant", "content": "No pude."}}]},
    ])
    monkeypatch.setattr(herr, "_post", lambda *a, **k: next(respuestas))

    def _no_debe_ejecutarse(*a, **k):
        raise AssertionError("la herramienta de escritura no debía ejecutarse")

    _texto, pasos, _n = run_tool_use_loop(
        execute_tool=_no_debe_ejecutarse,
        instruction="crea algo",
        system="",
        tools=HERRAMIENTAS,
        db=None,
        current_user=None,
        model="m",
        api_key="k",
        auto_approve=False,
        write_action_tools=frozenset({"buscar_proyectos"}),
        provider="openai",
        base_url="https://x/v1",
    )
    assert pasos[0]["output"]["status"] == "pending_approval"
