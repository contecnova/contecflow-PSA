"""Uso de herramientas (*tool use*) con cualquier proveedor de IA.

El agente NexusAgent no sólo responde: llama a funciones del propio producto
—crear una tarea, buscar proyectos, reasignar tickets— y encadena pasos con sus
resultados. Eso es *tool use*, y cada familia de proveedores lo expresa a su
manera.

Hasta 2026-09 el bucle del agente hablaba **sólo el dialecto de Anthropic**. Con
cualquier otro proveedor caía en «modo degradado»: analizaba la instrucción y no
ejecutaba nada. Avisaba de ello, que es mejor que fallar en silencio, pero
dejaba al producto con una funcionalidad de menos según quién pagara la API.

Este módulo traduce las tres partes que cambian y **nada más**:

1. **El esquema de las herramientas** que se le ofrecen al modelo.
2. **Cómo pide el modelo una llamada** en su respuesta.
3. **Cómo se le devuelve el resultado** para que siga el turno siguiente.

El bucle del agente queda igual para los tres, y las herramientas se definen una
sola vez en `AGENT_TOOLS` con la forma de Anthropic, que es la que ya había.

## Los tres dialectos, uno al lado de otro

| | herramientas | el modelo pide | se le responde |
|---|---|---|---|
| Anthropic | `{name, description, input_schema}` | bloque `tool_use` en `content` | bloque `tool_result` con `tool_use_id` |
| OpenAI y compatibles | `{type:"function", function:{...}}` | `message.tool_calls[]` | mensaje `role:"tool"` con `tool_call_id` |
| Gemini | `function_declarations[]` | `parts[].functionCall` | `parts[].functionResponse` |

La familia «OpenAI y compatibles» incluye Groq, Mistral, DeepSeek y Azure, que
hablan el mismo formato — igual que ya asumía `_call_openai_compat`.

**Ollama queda fuera a propósito.** Su API de chat admite herramientas sólo en
algunos modelos y sin garantía, así que decir que las soporta sería prometer
algo que depende del modelo que cada cual tenga instalado. `soporta_herramientas`
devuelve `False` y el agente entra en modo degradado avisando, que es lo honesto.
"""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field

import httpx

from app.core.config import settings

_logger = logging.getLogger("ai_tools")

#: Proveedores que hablan el formato de OpenAI para herramientas.
FAMILIA_OPENAI = frozenset({"openai", "groq", "mistral", "deepseek", "azure"})

#: Proveedores con uso de herramientas comprobado.
CON_HERRAMIENTAS = FAMILIA_OPENAI | {"anthropic", "gemini"}


def soporta_herramientas(proveedor: str | None) -> bool:
    """¿Puede este proveedor ejecutar acciones, y no sólo redactar?"""
    return (proveedor or "").strip().lower() in CON_HERRAMIENTAS


@dataclass
class LlamadaDeHerramienta:
    """Una herramienta que el modelo quiere ejecutar, ya normalizada."""

    id: str
    nombre: str
    argumentos: dict


@dataclass
class TurnoDelAgente:
    """Lo que el modelo devuelve en un turno, en forma común.

    `crudo` guarda la respuesta tal cual del proveedor porque el mensaje del
    asistente hay que devolvérselo **con su propia forma** en el turno
    siguiente: reconstruirlo desde los campos normalizados perdería lo que cada
    proveedor necesita para hilar la conversación.
    """

    texto: str
    llamadas: list[LlamadaDeHerramienta] = field(default_factory=list)
    crudo: dict = field(default_factory=dict)

    @property
    def quiere_herramientas(self) -> bool:
        return bool(self.llamadas)


# ── 1. El esquema de las herramientas ────────────────────────────────────────

def herramientas_para(proveedor: str, herramientas: list[dict]) -> list | dict:
    """Traduce `AGENT_TOOLS` al formato del proveedor."""
    p = proveedor.strip().lower()
    if p == "anthropic":
        return herramientas
    if p in FAMILIA_OPENAI:
        return [
            {
                "type": "function",
                "function": {
                    "name": h["name"],
                    "description": h.get("description", ""),
                    "parameters": h.get("input_schema", {"type": "object", "properties": {}}),
                },
            }
            for h in herramientas
        ]
    if p == "gemini":
        return [{"function_declarations": [
            {
                "name": h["name"],
                "description": h.get("description", ""),
                "parameters": _limpiar_esquema_para_gemini(
                    h.get("input_schema", {"type": "object", "properties": {}})),
            }
            for h in herramientas
        ]}]
    raise ValueError(f"El proveedor '{proveedor}' no soporta herramientas")


def _limpiar_esquema_para_gemini(esquema: dict) -> dict:
    """Gemini rechaza un `properties` vacío y las claves que no conoce.

    Su validador es más estricto que el de los otros dos: un
    `{"type":"object","properties":{}}` —que Anthropic acepta sin más— devuelve
    400. Se omite `parameters` en ese caso, que es como se declara una
    herramienta sin argumentos.
    """
    limpio = {k: v for k, v in esquema.items()
              if k in ("type", "properties", "required", "description", "enum", "items")}
    propiedades = limpio.get("properties") or {}
    if not propiedades:
        # Sin `parameters`: así se declara una herramienta sin argumentos.
        return {}
    limpio["properties"] = {
        nombre: {k: v for k, v in definicion.items()
                 if k in ("type", "description", "enum", "items")}
        for nombre, definicion in propiedades.items()
    }
    return limpio


# ── 2 y 3. Pedir un turno y devolver los resultados ──────────────────────────

def pedir_turno(*, proveedor: str, api_key: str, modelo: str, base_url: str,
                mensajes: list, system: str, herramientas: list[dict],
                max_tokens: int = 4096) -> TurnoDelAgente:
    """Un turno del agente contra el proveedor que sea."""
    p = proveedor.strip().lower()
    if p == "anthropic":
        return _turno_anthropic(api_key, modelo, mensajes, system, herramientas, max_tokens)
    if p in FAMILIA_OPENAI:
        return _turno_openai(base_url, api_key, modelo, mensajes, system,
                             herramientas, max_tokens)
    if p == "gemini":
        return _turno_gemini(api_key, modelo, mensajes, system, herramientas, max_tokens)
    raise ValueError(f"El proveedor '{proveedor}' no soporta herramientas")


def mensajes_del_turno(proveedor: str, turno: TurnoDelAgente,
                       resultados: list[tuple[LlamadaDeHerramienta, dict]]) -> list[dict]:
    """Lo que se añade a la conversación: lo que dijo el modelo y qué salió.

    Devuelve una lista porque el número de mensajes cambia según el proveedor:
    Anthropic y Gemini agrupan todos los resultados en uno, y OpenAI manda uno
    por llamada.
    """
    p = proveedor.strip().lower()

    if p == "anthropic":
        return [
            {"role": "assistant", "content": turno.crudo.get("content", [])},
            {"role": "user", "content": [
                {"type": "tool_result", "tool_use_id": ll.id, "content": json.dumps(r)}
                for ll, r in resultados
            ]},
        ]

    if p in FAMILIA_OPENAI:
        mensaje_asistente = turno.crudo.get("choices", [{}])[0].get("message", {})
        salida = [mensaje_asistente]
        salida += [
            {"role": "tool", "tool_call_id": ll.id, "name": ll.nombre,
             "content": json.dumps(r)}
            for ll, r in resultados
        ]
        return salida

    if p == "gemini":
        partes_modelo = (turno.crudo.get("candidates", [{}])[0]
                         .get("content", {}).get("parts", []))
        return [
            {"role": "model", "parts": partes_modelo},
            {"role": "user", "parts": [
                {"functionResponse": {"name": ll.nombre, "response": {"resultado": r}}}
                for ll, r in resultados
            ]},
        ]

    raise ValueError(f"El proveedor '{proveedor}' no soporta herramientas")


# ── Implementación por familia ───────────────────────────────────────────────

def _turno_anthropic(api_key, modelo, mensajes, system, herramientas, max_tokens):
    cuerpo = {
        "model": modelo, "max_tokens": max_tokens, "messages": mensajes,
        "tools": herramientas_para("anthropic", herramientas),
    }
    if system:
        cuerpo["system"] = system
    datos = _post(
        f"{settings.ANTHROPIC_API_URL.rstrip('/')}/messages", cuerpo,
        {"x-api-key": api_key, "anthropic-version": "2023-06-01",
         "content-type": "application/json"},
        "Anthropic")

    bloques = datos.get("content", [])
    texto = "".join(b.get("text", "") for b in bloques if b.get("type") == "text")
    llamadas = [
        LlamadaDeHerramienta(id=b["id"], nombre=b["name"], argumentos=b.get("input", {}))
        for b in bloques if b.get("type") == "tool_use"
    ]
    return TurnoDelAgente(texto=texto, llamadas=llamadas, crudo=datos)


def _turno_openai(base_url, api_key, modelo, mensajes, system, herramientas, max_tokens):
    destino = (base_url or "").rstrip("/")
    if not destino.endswith("/chat/completions"):
        destino += "/chat/completions"

    todos = ([{"role": "system", "content": system}] if system else []) + list(mensajes)
    cuerpo = {
        "model": modelo, "messages": todos, "max_tokens": max_tokens,
        "tools": herramientas_para("openai", herramientas),
        "tool_choice": "auto",
    }
    datos = _post(destino, cuerpo,
                  {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
                  "OpenAI-compatible")

    mensaje = datos.get("choices", [{}])[0].get("message", {})
    llamadas = []
    for tc in mensaje.get("tool_calls") or []:
        funcion = tc.get("function", {})
        llamadas.append(LlamadaDeHerramienta(
            id=tc.get("id", ""),
            nombre=funcion.get("name", ""),
            # Los argumentos llegan como CADENA JSON, no como objeto. Un modelo
            # puede devolver una cadena vacía o algo mal formado; eso no debe
            # tumbar el agente entero, así que se degrada a un dict vacío y la
            # herramienta decidirá qué hacer sin argumentos.
            argumentos=_json_o_vacio(funcion.get("arguments")),
        ))
    return TurnoDelAgente(texto=mensaje.get("content") or "", llamadas=llamadas, crudo=datos)


def _turno_gemini(api_key, modelo, mensajes, system, herramientas, max_tokens):
    url = f"{settings.GEMINI_API_URL}/models/{modelo}:generateContent?key={api_key}"
    cuerpo = {
        "contents": mensajes,
        "tools": herramientas_para("gemini", herramientas),
        "generationConfig": {"maxOutputTokens": max_tokens},
    }
    if system:
        # `system_instruction` es el campo propio de Gemini; mandarlo como un
        # turno más de la conversación funcionaba para el chat simple pero aquí
        # confunde al modelo sobre de quién es cada parte.
        cuerpo["system_instruction"] = {"parts": [{"text": system}]}

    datos = _post(url, cuerpo, {"Content-Type": "application/json"}, "Gemini")

    partes = (datos.get("candidates", [{}])[0].get("content", {}).get("parts", []))
    texto = "".join(p.get("text", "") for p in partes if "text" in p)
    llamadas = []
    for i, parte in enumerate(partes):
        fc = parte.get("functionCall")
        if not fc:
            continue
        # Gemini no da identificador de llamada: la respuesta se empareja por
        # NOMBRE. Se fabrica uno estable para que el resto del bucle —que sí
        # trabaja con identificadores— no tenga que saberlo.
        llamadas.append(LlamadaDeHerramienta(
            id=f"gemini-{i}-{fc.get('name', '')}",
            nombre=fc.get("name", ""),
            argumentos=fc.get("args") or {},
        ))
    return TurnoDelAgente(texto=texto, llamadas=llamadas, crudo=datos)


def _post(url: str, cuerpo: dict, cabeceras: dict, quien: str) -> dict:
    resp = httpx.post(url, json=cuerpo, headers=cabeceras, timeout=90)
    if resp.status_code != 200:
        raise ConnectionError(f"{quien} {resp.status_code}: {resp.text[:200]}")
    return resp.json()


def _json_o_vacio(bruto) -> dict:
    if isinstance(bruto, dict):
        return bruto
    if not bruto:
        return {}
    try:
        cargado = json.loads(bruto)
        return cargado if isinstance(cargado, dict) else {}
    except (ValueError, TypeError):
        _logger.warning("Argumentos de herramienta no son JSON válido: %r", str(bruto)[:120])
        return {}


def primer_mensaje(proveedor: str, instruccion: str) -> list[dict]:
    """La conversación inicial, en la forma que espera cada proveedor."""
    if proveedor.strip().lower() == "gemini":
        return [{"role": "user", "parts": [{"text": instruccion}]}]
    return [{"role": "user", "content": instruccion}]


def base_url_por_defecto(proveedor: str) -> str:
    """La URL del proveedor cuando no se ha configurado una propia.

    Se lee del catálogo del servicio de proveedores, que es donde ya vive, y se
    importa aquí dentro para no crear un ciclo: `ai_provider_service` no depende
    de este módulo, pero sí al revés en el futuro.
    """
    from app.services.ai_provider_service import PROVIDER_CATALOG
    return PROVIDER_CATALOG.get(proveedor.strip().lower(), {}).get("base_url", "")
