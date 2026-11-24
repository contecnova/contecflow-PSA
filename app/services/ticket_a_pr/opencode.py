"""Motor OpenCode (opencode.ai, licencia MIT) dentro del contenedor aislado.

Se ejecuta la imagen oficial fijada (`ghcr.io/anomalyco/opencode:<versión>`,
Configuración) en modo no interactivo:

    opencode run --agent plan|build --format json --model <proveedor>/<modelo> "<instrucción>"

con la configuración en `OPENCODE_CONFIG_CONTENT` (sin ficheros del host):

- `permission`: DENEGAR por defecto lo peligroso. PLAN: ni editar, ni shell, ni
  red. BUILD: editar sí; shell solo las órdenes de la lista de la empresa
  (`bash_allow`, por defecto ninguna); nunca `webfetch` ni directorios fuera del
  espacio de trabajo; nunca leer `.env`, claves ni certificados (que además no
  se copian al contenedor). Nada en «ask»: no hay nadie para contestar.
- `autoupdate: false`, `share: "disabled"`, sin servidores MCP.

La clave del modelo va en la variable que espera cada proveedor, por
`--env-file` (ver `sandbox`). Los tokens y el coste se leen de los eventos JSON
de `opencode run`; si no vienen, se estiman con el catálogo de modelos.

POR VERIFICAR con OpenCode real (TICKET_A_PR.md §Qué falta): el nombre exacto
de las claves de `permission` en la versión fijada, `--format json` y la forma
de sus eventos, y los hosts que la imagen necesita al arrancar (`hosts_propios`).
"""
from __future__ import annotations

import json
import logging
from typing import Any, Optional
from urllib.parse import urlparse

from app.services.ticket_a_pr import diff as _diff
from app.services.ticket_a_pr import sandbox
from app.services.ticket_a_pr.motor import Contexto, Modelo, MotorDeAgente, ResultadoMotor

logger = logging.getLogger(__name__)

#: Proveedor de IA de contecflow → (proveedor de OpenCode, variable de la clave).
PROVEEDORES: dict[str, tuple[str, str]] = {
    "anthropic": ("anthropic", "ANTHROPIC_API_KEY"),
    "openai": ("openai", "OPENAI_API_KEY"),
    "gemini": ("google", "GOOGLE_GENERATIVE_AI_API_KEY"),
    "deepseek": ("deepseek", "DEEPSEEK_API_KEY"),
    "groq": ("groq", "GROQ_API_KEY"),
    "mistral": ("mistral", "MISTRAL_API_KEY"),
    # Compatibles con OpenAI por su URL base (Azure OpenAI, Ollama local).
    "azure": ("contecflow", "CONTECFLOW_MODEL_API_KEY"),
    "ollama": ("contecflow", "CONTECFLOW_MODEL_API_KEY"),
}

#: Lo que el agente nunca lee (y que además no se copia al contenedor).
LECTURA_DENEGADA = ("*.env", ".env", ".env.*", "**/.env", "*.pem", "*.key", "id_rsa*", "id_ed25519*", "*.p12",
                    "*.pfx", ".npmrc", ".pypirc", ".netrc")


def host_del_modelo(modelo: Modelo) -> Optional[tuple[str, int]]:
    """(host, puerto) de la API del modelo: el único destino obligatorio de la lista blanca."""
    from app.services.ai_provider_service.catalogo import PROVIDER_CATALOG
    url = modelo.base_url or str(PROVIDER_CATALOG.get(modelo.proveedor, {}).get("base_url") or "")
    p = urlparse(url)
    if not p.hostname:
        return None
    return p.hostname.lower(), p.port or (443 if p.scheme == "https" else 80)


def configuracion(modelo: Modelo, fase: str, bash_permitido: list[str]) -> dict:
    """El `opencode.json` de la ejecución (va en `OPENCODE_CONFIG_CONTENT`)."""
    proveedor, _ = PROVEEDORES.get(modelo.proveedor, ("contecflow", "CONTECFLOW_MODEL_API_KEY"))
    if fase == "plan":
        permisos: dict[str, Any] = {"edit": "deny", "bash": "deny"}
    else:
        bash: dict[str, str] = {"*": "deny"}
        for orden in bash_permitido:
            bash[orden] = "allow"
        permisos = {"edit": "allow", "bash": bash}
    permisos.update({"webfetch": "deny", "websearch": "deny", "external_directory": "deny", "doom_loop": "deny",
                     "read": {"*": "allow", **{p: "deny" for p in LECTURA_DENEGADA}}})
    cfg: dict[str, Any] = {
        "$schema": "https://opencode.ai/config.json",
        "model": f"{proveedor}/{modelo.modelo}",
        "autoupdate": False,
        "share": "disabled",
        "mcp": {},
        "permission": permisos,
    }
    if proveedor == "contecflow":
        base = (modelo.base_url or "").rstrip("/")
        if modelo.proveedor == "ollama" and not base.endswith("/v1"):
            base = base.removesuffix("/api/chat").rstrip("/") + "/v1"
        cfg["provider"] = {"contecflow": {
            "npm": "@ai-sdk/openai-compatible", "name": "contecflow",
            "options": {"baseURL": base, "apiKey": "{env:CONTECFLOW_MODEL_API_KEY}"},
            "models": {modelo.modelo: {}},
        }}
    return cfg


def argumentos(modelo: Modelo, fase: str, instruccion: str) -> list[str]:
    proveedor, _ = PROVEEDORES.get(modelo.proveedor, ("contecflow", ""))
    return ["run", "--agent", "plan" if fase == "plan" else "build", "--format", "json",
            "--model", f"{proveedor}/{modelo.modelo}", instruccion]


def entorno(modelo: Modelo, fase: str, bash_permitido: list[str]) -> dict[str, str]:
    _, variable = PROVEEDORES.get(modelo.proveedor, ("contecflow", "CONTECFLOW_MODEL_API_KEY"))
    salida = {"OPENCODE_CONFIG_CONTENT": json.dumps(configuracion(modelo, fase, bash_permitido))}
    if modelo.api_key:
        salida[variable] = modelo.api_key
    return salida


def _recorrer(obj: Any, acumulado: dict) -> None:
    if isinstance(obj, dict):
        tokens = obj.get("tokens")
        if isinstance(tokens, dict) and ("input" in tokens or "output" in tokens):
            acumulado["in"] += int(tokens.get("input") or 0)
            acumulado["out"] += int(tokens.get("output") or 0) + int(tokens.get("reasoning") or 0)
            if isinstance(obj.get("cost"), (int, float)):
                acumulado["coste"] += float(obj["cost"])
        if obj.get("type") == "text" and isinstance(obj.get("text"), str):
            acumulado["texto"].append(obj["text"])
        for v in obj.values():
            if isinstance(v, (dict, list)):
                _recorrer(v, acumulado)
    elif isinstance(obj, list):
        for v in obj:
            _recorrer(v, acumulado)


def leer_eventos(salida: str) -> dict:
    """Texto final, tokens y coste de la salida de `opencode run --format json` (tolerante)."""
    acumulado = {"in": 0, "out": 0, "coste": 0.0, "texto": []}
    json_vistos = False
    for linea in (salida or "").splitlines():
        linea = linea.strip()
        if not linea.startswith("{"):
            continue
        try:
            evento = json.loads(linea)
        except ValueError:
            continue
        json_vistos = True
        _recorrer(evento, acumulado)
    texto = acumulado["texto"][-1] if acumulado["texto"] else ("" if json_vistos else (salida or "").strip())
    return {"texto": texto[-20000:], "tokens_in": acumulado["in"], "tokens_out": acumulado["out"],
            "coste": acumulado["coste"]}


class MotorOpenCode(MotorDeAgente):
    nombre = "opencode"

    def hosts_propios(self) -> list[tuple[str, int]]:
        from app.core.config import settings
        hosts = []
        for h in str(getattr(settings, "TICKET_PR_ENGINE_EGRESS_HOSTS", "") or "").split(","):
            h = h.strip().lower()
            if h:
                hosts.append((h, 443))
        return hosts

    def _hosts(self, ctx: Contexto) -> list[tuple[str, int]]:
        modelo = host_del_modelo(ctx.modelo)
        return list(dict.fromkeys(([modelo] if modelo else []) + self.hosts_propios() + list(ctx.hosts_extra)))

    def _ejecutar(self, ctx: Contexto, fase: str) -> ResultadoMotor:
        pedido = sandbox.Pedido(
            imagen=ctx.imagen, argumentos=argumentos(ctx.modelo, fase, ctx.instruccion),
            espacio=_diff.escribir_tar(ctx.arbol), limites=ctx.limites, hosts_permitidos=self._hosts(ctx),
            entorno=entorno(ctx.modelo, fase, ctx.bash_permitido), solo_lectura=(fase == "plan"),
            devolver_espacio=(fase == "build"))
        r = sandbox.ejecutar(pedido)
        eventos = leer_eventos(r.salida)
        coste = eventos["coste"]
        if not coste and (eventos["tokens_in"] or eventos["tokens_out"]):
            from app.services.ai_provider_service.gasto import coste_estimado
            coste = coste_estimado(ctx.modelo.proveedor, ctx.modelo.modelo, eventos["tokens_in"], eventos["tokens_out"])
        base = dict(texto=eventos["texto"], tokens_in=eventos["tokens_in"], tokens_out=eventos["tokens_out"],
                    coste_usd=coste, segundos=r.segundos, log=(r.salida or "")[-100_000:] + "\n" + (r.errores or "")[-50_000:])
        if r.agotado:
            return ResultadoMotor(False, codigo="ticket_pr_tiempo_agotado",
                                  params={"minutos": max(1, ctx.limites.segundos // 60)}, **base)
        if r.codigo_salida != 0:
            return ResultadoMotor(False, codigo="ticket_pr_motor_fallo", params={"codigo": r.codigo_salida}, **base)
        arbol = None
        if fase == "build":
            arbol = _diff.leer_tar(r.espacio or b"", max_bytes=ctx.max_bytes)
        return ResultadoMotor(True, arbol=arbol, **base)

    def planificar(self, ctx: Contexto) -> ResultadoMotor:
        return self._ejecutar(ctx, "plan")

    def construir(self, ctx: Contexto) -> ResultadoMotor:
        return self._ejecutar(ctx, "build")

    def ejecutar_tests(self, ctx: Contexto, orden: str) -> ResultadoMotor:
        """La orden de tests (la pone la empresa, no el agente) en otro contenedor igual de aislado.

        Sin el modelo: la lista blanca es solo la salida extra de la empresa
        (registros de paquetes); sin ella, sin red.
        """
        pedido = sandbox.Pedido(
            imagen=ctx.imagen, argumentos=["-c", orden], entrypoint="sh", espacio=_diff.escribir_tar(ctx.arbol),
            limites=ctx.limites, hosts_permitidos=list(ctx.hosts_extra))
        r = sandbox.ejecutar(pedido)
        log = (r.salida or "")[-50_000:] + "\n" + (r.errores or "")[-20_000:]
        if r.agotado:
            return ResultadoMotor(False, segundos=r.segundos, log=log, codigo="ticket_pr_tiempo_agotado",
                                  params={"minutos": max(1, ctx.limites.segundos // 60)})
        return ResultadoMotor(r.codigo_salida == 0, segundos=r.segundos, log=log,
                              params={"codigo": r.codigo_salida})
