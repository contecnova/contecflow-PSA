"""Auditoria 2026-11 de arquitectura, bloque 4 (#43 capas y ciclos, #38 valores fijos).

#43, medido antes con el grafo de `test_sin_ciclos_de_import.py` (ast, todos los
`import`, tambien los de dentro de funciones):
  · 7 imports de capas altas desde capas bajas: `grc_service` -> `app.main`,
    `core/modulos_ia` -> `app.api...governance`, `segundo_plano`,
    `automation_events`, `ticket_events`, `webhooks` y `ai_modules/voice` (este a
    nivel de modulo) -> `app.worker`.
  · 3 imports de servicios a nivel de modulo en `app/core` (`abac`, `abac_enforce`,
    `security`).
  · 10 imports dentro de funciones que cerraban un ciclo (subirlos al modulo
    daria un ciclo de carga): presupuestos_preparar<->budgets_service,
    gastos_avanzados<->expense_service, bi_embed<->m365_bi_embed,
    ticket_ops<->ticket_update, grc_service->app.main, automation_events y
    ticket_events -> app.worker, y los 3 cargadores de `collaboration`.
Despues: 0 / 0 / 3 (los cargadores de plugins, permitidos abajo).
"""
from tests.test_sin_ciclos_de_import import RAIZ, _modulos

import ast

ALTAS = ("app.main", "app.api", "app.worker")
BAJAS = ("app.services", "app.core", "app.db")

#: (modulo, destino): por que se permite.
INVERSIONES_PERMITIDAS: dict[tuple[str, str], str] = {}

#: Imports dentro de funciones que cierran un ciclo a proposito.
CICLOS_PERMITIDOS = {
    ("app.services.collaboration._bus", "app.services.collaboration._bus_redis"):
        "cargador de plugin: `COLLAB_BUS_BACKEND` elige en ejecucion; el backend hereda de `_bus.EventBus`",
    ("app.services.collaboration._bus", "app.services.collaboration._bus_nats"):
        "cargador de plugin: idem, NATS",
    ("app.services.collaboration._storage", "app.services.collaboration._storage_s3"):
        "cargador de plugin: `COLLAB_STORAGE_BACKEND=s3|minio` (boto3 opcional); hereda de `_storage.FileStorage`",
}


def _es(nombre: str, prefijos: tuple[str, ...]) -> bool:
    return any(nombre == p or nombre.startswith(p + ".") for p in prefijos)


def _imports():
    """[(modulo, destino, linea, a_nivel_de_modulo)] con el mismo metodo que el test de ciclos."""
    mods = _modulos()

    def resolver(nombre):
        while nombre and nombre not in mods:
            nombre = nombre.rsplit(".", 1)[0] if "." in nombre else ""
        return nombre or None

    salida = []
    for m, p in mods.items():
        paquete = m if p.name == "__init__.py" else m.rsplit(".", 1)[0]
        arbol = ast.parse(p.read_text(encoding="utf-8"))
        de_modulo = {id(n) for n in arbol.body}
        for n in ast.walk(arbol):
            if isinstance(n, ast.Import):
                destinos = [a.name for a in n.names]
            elif isinstance(n, ast.ImportFrom):
                base = n.module or ""
                if n.level:
                    partes = paquete.split(".")
                    base = ".".join(partes[: len(partes) - n.level + 1] + ([n.module] if n.module else []))
                destinos = [f"{base}.{a.name}" for a in n.names]
            else:
                continue
            for d in destinos:
                t = resolver(d)
                if t and t != m:
                    salida.append((m, t, n.lineno, id(n) in de_modulo))
    return mods, salida


def test_las_capas_bajas_no_importan_main_api_ni_worker():
    mods, imports = _imports()
    malos = sorted({f"{mods[m].relative_to(RAIZ)}:{ln} -> {t}" for m, t, ln, _ in imports
                    if _es(m, BAJAS) and _es(t, ALTAS) and (m, t) not in INVERSIONES_PERMITIDAS})
    assert malos == [], ("app/services, app/core y app/db no importan app.main, app.api ni app.worker "
                         "(tareas: `app.core.segundo_plano.enviar_tarea` por nombre; la app: que la pase la ruta): "
                         f"{malos}")


def test_core_y_db_no_importan_servicios_al_cargarse():
    mods, imports = _imports()
    malos = sorted(f"{mods[m].relative_to(RAIZ)}:{ln} -> {t}" for m, t, ln, arriba in imports
                   if arriba and _es(m, ("app.core", "app.db")) and _es(t, ("app.services",)))
    assert malos == [], f"core/db importan servicios a nivel de modulo: {malos}"


def test_ningun_import_dentro_de_una_funcion_esconde_un_ciclo():
    """Un import diferido A->B con B que ya llega a A a nivel de modulo es un ciclo escondido."""
    mods, imports = _imports()
    arriba: dict[str, set[str]] = {m: set() for m in mods}
    for m, t, _, de_modulo in imports:
        if de_modulo:
            arriba[m].add(t)

    def alcanza(desde, hasta):
        vistos, pila = set(), [desde]
        while pila:
            x = pila.pop()
            if x == hasta:
                return True
            if x not in vistos:
                vistos.add(x)
                pila.extend(arriba[x])
        return False

    ciclos = sorted({f"{mods[m].relative_to(RAIZ)}:{ln} -> {t}" for m, t, ln, de_modulo in imports
                     if not de_modulo and t not in arriba[m] and (m, t) not in CICLOS_PERMITIDOS
                     and alcanza(t, m)})
    assert ciclos == [], f"Imports en funcion que cierran un ciclo (mueve la pieza compartida): {ciclos}"


def test_enviar_tarea_encola_por_nombre_sin_importar_el_worker(monkeypatch):
    import sys

    from app.core import segundo_plano

    enviadas = []

    class _Falso:
        def send_task(self, nombre, args, kwargs, **opciones):
            enviadas.append((nombre, args, kwargs, opciones))

    monkeypatch.setattr(segundo_plano, "_celery", lambda: _Falso())
    segundo_plano.enviar_tarea("app.worker.deliver_webhook", args=("h", "{}", "e"))
    segundo_plano.enviar_tarea("app.worker.automations_procesar_eventos", retry=False)
    assert enviadas == [("app.worker.deliver_webhook", ["h", "{}", "e"], {}, {}),
                        ("app.worker.automations_procesar_eventos", [], {}, {"retry": False})]
    # Los nombres existen en el worker.
    import app.worker as w
    nombres = set(w.celery_app.tasks)
    for n in ("app.worker.deliver_webhook", "app.worker.automations_procesar_eventos",
              "app.worker.sd_procesar_eventos_de_ticket", "app.worker.run_agent_task",
              "app.worker.ejecutar_en_segundo_plano"):
        assert n in nombres, n
    assert "app.worker" in sys.modules


# ── #38 Valores fijos: esperas, hosts y modelos ────────────────────────────────
#
# Medido antes (ast, `timeout=<numero>` en `app/`): 65 en 32 ficheros. Hosts
# (lineas con el literal, `app/`): graph.microsoft.com 12, login.microsoftonline.com 9,
# api.openai.com 4, api.anthropic.com 2, accounts.google.com 2,
# oauth2.googleapis.com 2, adobesign 2. Modelos: claude-haiku-4-5 3,
# all-MiniLM-L6-v2 7, gpt-4o-mini-transcribe 5. Despues: solo en `Settings` y
# las excepciones de abajo.

#: Esperas literales que quedan, con su razon (fichero: cuantas).
ESPERAS_PERMITIDAS = {
    "app/worker.py": (1, "fuera del alcance de este cambio (lo edita otro frente)"),
    "app/services/slack_service.py": (2, "idem"),
    "app/services/jira_service.py": (2, "idem"),
    "app/api/v1/endpoints/jira.py": (2, "idem"),
    "app/api/v1/endpoints/bi_intelligence.py": (1, "espera de sondeo de Redis pub/sub, no una llamada saliente"),
    "app/services/collaboration/_bus_redis.py": (1, "idem"),
    "app/services/cmdb/parser.py": (1, "SNMP por UDP: espera por reintento del protocolo"),
    "app/services/collaboration/_text_extract.py": (2, "subproceso local (pdftotext/libreoffice), no red"),
    "app/services/collaboration/_thumbnails.py": (1, "subproceso local (ffmpeg)"),
    "app/services/collaboration/_transcription.py": (1, "subproceso local (whisper)"),
    "app/services/stt/whisper_local_stt.py": (1, "subproceso local (whisper)"),
}

HOSTS = ("graph.microsoft.com", "login.microsoftonline.com", "api.openai.com", "api.anthropic.com",
         "accounts.google.com", "oauth2.googleapis.com", "adobesign.com",
         "claude-haiku-4-5", "all-MiniLM-L6-v2", "gpt-4o-mini-transcribe")
#: Donde viven (los defectos de `Settings`).
HOSTS_PERMITIDOS = ("app/core/config.py", "app/core/config_groups/")


def _ficheros_app():
    for p in sorted((RAIZ / "app").rglob("*.py")):
        if "__pycache__" not in p.parts:
            yield p.relative_to(RAIZ).as_posix(), ast.parse(p.read_text(encoding="utf-8"))


def test_sin_esperas_de_red_escritas_en_el_codigo():
    cuenta: dict[str, int] = {}
    for rel, arbol in _ficheros_app():
        for n in ast.walk(arbol):
            if (isinstance(n, ast.keyword) and n.arg == "timeout" and isinstance(n.value, ast.Constant)
                    and isinstance(n.value.value, (int, float)) and not isinstance(n.value.value, bool)):
                cuenta[rel] = cuenta.get(rel, 0) + 1
    sobran = {f: c for f, c in cuenta.items() if c > ESPERAS_PERMITIDAS.get(f, (0, ""))[0]}
    assert sobran == {}, ("usa outbound_http_timeout(db, default=<la de siempre>) u outbound_ai_timeout "
                          f"(app.services.settings_service): {sobran}")


def _docstrings(arbol) -> set[int]:
    ids = set()
    for n in ast.walk(arbol):
        if isinstance(n, (ast.Module, ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)) and n.body:
            primero = n.body[0]
            if isinstance(primero, ast.Expr) and isinstance(primero.value, ast.Constant):
                ids.add(id(primero.value))
    return ids


def test_hosts_y_modelos_solo_en_settings():
    malos = []
    for rel, arbol in _ficheros_app():
        if rel.startswith(HOSTS_PERMITIDOS):
            continue
        docs = _docstrings(arbol)
        for n in ast.walk(arbol):
            if isinstance(n, ast.Constant) and isinstance(n.value, str) and id(n) not in docs:
                malos += [f"{rel}:{n.lineno} {h}" for h in HOSTS if h in n.value]
    assert malos == [], ("MICROSOFT_OAUTH_BASE / MICROSOFT_GRAPH_BASE / GOOGLE_OAUTH_BASE / GOOGLE_TOKEN_URL / "
                         "OPENAI_API_URL / ANTHROPIC_API_URL / ADOBE_SIGN_BASE_URL / CONTECFLOW_AI_MODEL / "
                         f"EMBEDDING_MODEL_NAME / OPENAI_STT_MODEL: {malos}")


def test_la_espera_de_cada_sitio_se_conserva_hasta_que_el_operador_fija_el_ajuste(monkeypatch):
    from app.core.config import settings
    from app.services.settings_service import outbound_ai_timeout, outbound_http_timeout, runtime

    sin_fijar = settings.model_copy()
    object.__setattr__(sin_fijar, "__pydantic_fields_set__",
                       set(settings.model_fields_set) - {"OUTBOUND_HTTP_TIMEOUT_SECONDS", "OUTBOUND_AI_TIMEOUT_SECONDS"})
    monkeypatch.setattr(runtime, "app_settings", sin_fijar)
    assert outbound_http_timeout(default=15) == 15.0
    assert outbound_ai_timeout(default=30) == 30.0
    assert outbound_http_timeout() == sin_fijar.OUTBOUND_HTTP_TIMEOUT_SECONDS
    fijado = sin_fijar.model_copy(update={"OUTBOUND_HTTP_TIMEOUT_SECONDS": 7.0, "OUTBOUND_AI_TIMEOUT_SECONDS": 90.0})
    monkeypatch.setattr(runtime, "app_settings", fijado)
    assert outbound_http_timeout(default=15) == 7.0
    assert outbound_ai_timeout(default=30) == 90.0


def test_graph_y_modelos_salen_de_settings_con_el_defecto_de_siempre():
    from app.core.config import settings
    from app.services import m365_service
    from app.services.service_desk import buzones

    campos = type(settings).model_fields
    assert campos["MICROSOFT_GRAPH_BASE"].default == "https://graph.microsoft.com"
    assert campos["EMBEDDING_MODEL_NAME"].default == "all-MiniLM-L6-v2"
    assert m365_service.GRAPH_BASE == buzones.GRAPH == f"{settings.MICROSOFT_GRAPH_BASE}/v1.0"
