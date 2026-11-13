"""Segunda auditoria 2026-11: n.º 12, 20 y 31 (bucle de eventos y trabajo de fondo).

12. Endpoints `async def` que bloqueaban el bucle de eventos (BD sincrona, red
    sincrona, subprocesos). Guarda AST: ningun endpoint async llama a algo
    conocido como bloqueante sin pasar por `run_db`/`to_thread`.
20. Trabajo lento sacado de la peticion con `encolar`.
31. `jira_integration` ya no pasa la sesion de la peticion a una tarea de fondo.
"""
from __future__ import annotations

import ast
import pathlib

import pytest

RAIZ = pathlib.Path(__file__).resolve().parent.parent
API = RAIZ / "app" / "api"

# ── 12. Guarda AST ────────────────────────────────────────────────────────────

_METODOS = {"get", "post", "put", "patch", "delete", "head", "options", "websocket", "api_route"}
#: Metodos de una sesion SQLAlchemy que hablan con la base.
_DE_SESION = {"query", "execute", "commit", "flush", "refresh", "scalar", "scalars",
              "get", "add", "add_all", "delete", "rollback", "merge"}
_NOMBRES_DE_SESION = {"db", "session", "self.db"}
#: Prefijos de llamadas de red/proceso sincronas.
_BLOQUEANTES = ("requests.", "urllib.request.urlopen", "urlopen", "subprocess.",
                "smtplib.", "time.sleep", "httpx.get", "httpx.post", "httpx.put",
                "httpx.patch", "httpx.delete", "httpx.request", "httpx.head", "httpx.Client")
#: Llamadas que reciben la sesion pero no la usan para consultar.
_PASAN_DB_SIN_CONSULTAR = {"publicar_contexto_de_tenant", "run_db", "run_in_threadpool",
                           "asyncio.to_thread", "to_thread", "Depends", "_ejecutar_comando_del_bot",
                           "asyncio.create_task"}
_DESCARGAN = {"run_db", "run_in_threadpool", "asyncio.to_thread", "to_thread"}


def _es_endpoint(fn) -> bool:
    for d in fn.decorator_list:
        f = d.func if isinstance(d, ast.Call) else d
        if isinstance(f, ast.Attribute) and f.attr in _METODOS:
            return True
    return False


def _nodos(nodo):
    """Hijos sin entrar en funciones anidadas ni lambdas (lo que va a run_db)."""
    for hijo in ast.iter_child_nodes(nodo):
        if isinstance(hijo, (ast.FunctionDef, ast.AsyncFunctionDef, ast.Lambda, ast.ClassDef)):
            continue
        yield hijo
        yield from _nodos(hijo)


def _bloqueos_directos(fn, corrutinas: frozenset = frozenset()) -> tuple[list[str], list[str]]:
    """(bloqueos, nombres de funciones del modulo llamadas sin descargar).

    `corrutinas`: funciones `async` del modulo. Llamarlas solo crea la corrutina
    (p. ej. dentro de `create_task`); su cuerpo se sigue aparte.
    """
    esperadas = {id(n.value) for n in _nodos(fn) if isinstance(n, ast.Await)}
    descargadas = set()
    for n in _nodos(fn):
        if isinstance(n, ast.Call) and ast.unparse(n.func) in _DESCARGAN:
            descargadas.update(id(a) for a in n.args)
    hallados, llamadas = [], []
    for n in _nodos(fn):
        if not isinstance(n, ast.Call) or id(n) in descargadas:
            continue
        nombre = ast.unparse(n.func)
        if isinstance(n.func, ast.Name):
            llamadas.append(nombre)
        if id(n) in esperadas or nombre in corrutinas or nombre.lstrip("_")[:1].isupper():
            continue  # await, corrutina del modulo o constructor
        if (isinstance(n.func, ast.Attribute) and n.func.attr in _DE_SESION
                and ast.unparse(n.func.value) in _NOMBRES_DE_SESION):
            hallados.append(f"{n.lineno}:{nombre}")
        elif nombre.startswith(_BLOQUEANTES) or nombre == "urlopen":
            hallados.append(f"{n.lineno}:{nombre}")
        elif nombre not in _PASAN_DB_SIN_CONSULTAR and any(
                isinstance(a, ast.Name) and a.id == "db"
                for a in [*n.args, *(k.value for k in n.keywords)]):
            hallados.append(f"{n.lineno}:{nombre}(db)")
    return hallados, llamadas


def bloqueos_en_endpoints_async() -> dict[str, list[str]]:
    """`fichero:linea nombre` -> llamadas bloqueantes dentro del bucle de eventos.

    Sigue, dentro del mismo modulo, las funciones a las que el endpoint llama
    o espera (una funcion sincrona del modulo que hace `urlopen` bloquea igual).
    """
    resultado: dict[str, list[str]] = {}
    for fichero in sorted(API.rglob("*.py")):
        arbol = ast.parse(fichero.read_text(encoding="utf-8"))
        del_modulo = {f.name: f for f in arbol.body
                      if isinstance(f, (ast.FunctionDef, ast.AsyncFunctionDef))}
        corrutinas = frozenset(n for n, f in del_modulo.items() if isinstance(f, ast.AsyncFunctionDef))
        for fn in ast.walk(arbol):
            if not (isinstance(fn, ast.AsyncFunctionDef) and _es_endpoint(fn)):
                continue
            hallados, pendientes, vistos = [], [fn], set()
            while pendientes:
                actual = pendientes.pop()
                if id(actual) in vistos:
                    continue
                vistos.add(id(actual))
                h, llamadas = _bloqueos_directos(actual, corrutinas)
                origen = "" if actual is fn else f"{actual.name}:"
                hallados += [origen + x for x in h]
                pendientes += [del_modulo[c] for c in llamadas if c in del_modulo]
            clave = f"{fichero.relative_to(RAIZ).as_posix()}:{fn.lineno} {fn.name}"
            resultado[clave] = hallados
    return resultado


def test_12_ningun_endpoint_async_bloquea_el_bucle():
    medidos = bloqueos_en_endpoints_async()
    assert len(medidos) >= 40, "la guarda no encuentra los endpoints async"
    malos = {k: v for k, v in medidos.items() if v}
    assert not malos, malos


def test_12_la_guarda_detecta_los_patrones():
    codigo = '''
import subprocess, httpx
def _ayuda():
    subprocess.run(["x"])
@router.post("/a")
async def a(db=Depends(get_db)):
    db.query(X).all()
    httpx.post("u")
    servicio(db, 1)
    _ayuda()
    await run_db(servicio, db, 1)
'''
    arbol = ast.parse(codigo)
    fn = next(f for f in arbol.body if isinstance(f, ast.AsyncFunctionDef))
    hallados, llamadas = _bloqueos_directos(fn)
    assert any("db.query" in h for h in hallados)
    assert any("httpx.post" in h for h in hallados)
    assert any("servicio(db)" in h for h in hallados)
    assert len(hallados) == 3  # el `await run_db(...)` no cuenta
    assert "_ayuda" in llamadas
    assert _bloqueos_directos(arbol.body[1])[0]  # subprocess dentro de _ayuda


# ── encolar: contexto de empresa ──────────────────────────────────────────────

@pytest.fixture
def cola(monkeypatch):
    """Simula un broker: `encolar` manda a la cola y aqui se ve lo que manda."""
    from app.core import segundo_plano as sp
    enviados = []
    monkeypatch.setattr(sp, "_hay_cola", lambda: True)
    monkeypatch.setattr(sp, "enviar_tarea", lambda nombre, args=(), kwargs=None, **o: enviados.append((nombre, args)))
    return enviados


class _SesionFalsa:
    def __init__(self, info=None):
        self.info = dict(info or {})
        self.cerrada = False

    def close(self):
        self.cerrada = True


def test_encolar_manda_el_envoltorio_con_la_organizacion(cola):
    from app.core import segundo_plano as sp
    from app.services.scheduled_reports import execute_report_now

    r = sp.encolar(execute_report_now, "inf-1", _sesion=_SesionFalsa({"organization_id": "org-a"}))
    assert r is sp.EN_COLA
    nombre, args = cola[0]
    assert nombre == "app.worker.ejecutar_en_segundo_plano"
    assert args[0] == "app.core.segundo_plano:_ejecutar_con_contexto"
    assert args[1] == ["app.services.scheduled_reports:execute_report_now", "org-a", ["inf-1"], {}]
    assert args[2] == {}
    # La explicita manda sobre la de la sesion; ninguna llega a la funcion.
    sp.encolar(execute_report_now, "inf-1", _organizacion="org-b", _sesion=_SesionFalsa({"organization_id": "org-a"}))
    assert cola[1][1][1][1] == "org-b" and "_sesion" not in cola[1][1][1][3]


def test_el_worker_abre_sesion_propia_con_el_contexto_publicado(monkeypatch):
    import contextlib

    from app.core import segundo_plano as sp
    import app.db.session as sesiones

    abiertas = []

    @contextlib.contextmanager
    def _fabrica():
        s = _SesionFalsa()
        abiertas.append(s)
        yield s
        s.close()

    monkeypatch.setattr(sesiones, "worker_db_session", _fabrica)
    vistos = {}

    def _objetivo(db, informe, *, extra=None):
        vistos.update(info=dict(db.info), informe=informe, extra=extra, org=sp.organizacion_en_curso())
        return "hecho"

    monkeypatch.setattr(sp, "_objetivo_de_prueba", _objetivo, raising=False)
    r = sp._ejecutar_con_contexto("app.core.segundo_plano:_objetivo_de_prueba", "org-a", ["i1"], {"extra": 2})
    assert r == "hecho"
    assert vistos == {"info": {"organization_id": "org-a", "is_superadmin": False},
                      "informe": "i1", "extra": 2, "org": "org-a"}
    assert abiertas[0].cerrada and sp.organizacion_en_curso() is None

    # Sin organizacion: sesion «no inicializada» (trabajo de plataforma).
    sp._ejecutar_con_contexto("app.core.segundo_plano:_objetivo_de_prueba", None, ["i2"], {})
    assert vistos["info"] == {}

    # Una funcion sin `db` no abre sesion.
    monkeypatch.setattr(sp, "_objetivo_de_prueba", lambda a: a * 2, raising=False)
    assert sp._ejecutar_con_contexto("app.core.segundo_plano:_objetivo_de_prueba", "o", [3], {}) == 6
    assert len(abiertas) == 2


def test_en_linea_usa_la_sesion_de_la_peticion():
    from app.core import segundo_plano as sp

    peticion = _SesionFalsa({"organization_id": "org-a"})
    assert sp.encolar(lambda db, x: (db, x), 1, _sesion=peticion) == (peticion, 1)


def test_el_worker_no_ejecuta_rutas_ajenas():
    from app.core import segundo_plano as sp
    with pytest.raises(ValueError):
        sp._ejecutar_con_contexto("os:system", None, ["echo"], {})


# ── 20. Endpoints que encolan ─────────────────────────────────────────────────

def test_20_recuperar_contrasena_encola_el_correo_y_responde_igual(client, cola):
    from tests.conftest import auth  # noqa: F401  (misma convencion de import)
    r = client.post("/api/v1/auth/password/forgot", json={"email_or_username": "admin"})
    assert r.status_code == 200, r.text
    assert r.json()["ok"] is True
    rutas = [args[1][0] for _, args in cola]
    assert "app.services.auth_service.tokens_y_cookies:send_password_reset_email" in rutas
    _, args = cola[rutas.index("app.services.auth_service.tokens_y_cookies:send_password_reset_email")]
    destinatario, enlace = args[1][2]
    assert destinatario == "admin@contecflow.com" and "reset-password?token=" in enlace
    assert "db" not in args[1][3]  # la sesion la abre el worker


def test_20_pasada_de_calidad_de_la_kb_responde_202(client, admin_token, cola):
    from tests.conftest import auth
    r = client.post("/api/v1/sd/kb/quality/run", headers=auth(admin_token))
    assert r.status_code == 202, r.text
    assert r.json()["data"] == {"ok": True, "status": "queued"}
    assert cola[0][1][1][0] == "app.services.service_desk.kb_calidad:pasada"


def test_20_sin_cola_la_pasada_responde_como_siempre(client, admin_token):
    from tests.conftest import auth
    r = client.post("/api/v1/sd/kb/quality/run", headers=auth(admin_token))
    assert r.status_code == 200, r.text
    assert set(r.json()["data"]) == {"stale", "contradictions"}


def test_20_los_endpoints_de_lotes_encolan():
    """Cada endpoint movido llama a `encolar` (medido en el codigo, no en red)."""
    movidos = {
        "app/api/v1/routers/auth_core.py": "password_forgot",
        "app/api/v1/endpoints/billing_reports.py": "run_scheduled_report",
        "app/api/v1/endpoints/bi_intelligence.py": ("phase2_delivery_run_now", "send_delivery_now"),
        "app/api/v1/endpoints/service_desk/cmdb.py": "_discovery_en_segundo_plano",
        "app/api/v1/endpoints/service_desk/alert_correlation.py": "run_correlation_scan",
        "app/api/v1/endpoints/service_desk/kb.py": "pasar_calidad",
        "app/api/v1/endpoints/currency_sync.py": "sync_ecb_exchange_rates",
        "app/api/v1/endpoints/jira.py": "push_nexus_to_jira",
        "app/api/v1/endpoints/jira_integration.py": "run_manual_sync",
        "app/api/v1/endpoints/salesforce_sync.py": "sync_salesforce_opportunities",
        "app/api/v1/endpoints/bookings.py": "process_workflow_queue",
        "app/api/v1/endpoints/collaboration/admin.py": "run_digest",
    }
    for fichero, nombres in movidos.items():
        arbol = ast.parse((RAIZ / fichero).read_text(encoding="utf-8"))
        funciones = {f.name: f for f in ast.walk(arbol) if isinstance(f, ast.FunctionDef)}
        for nombre in (nombres if isinstance(nombres, tuple) else (nombres,)):
            llamadas = {ast.unparse(n.func) for n in ast.walk(funciones[nombre]) if isinstance(n, ast.Call)}
            assert "encolar" in llamadas, f"{fichero}:{nombre} no encola"


# ── 31. Jira: la tarea de fondo no hereda la sesion de la peticion ────────────

def test_31_sincronizacion_jira_viaja_con_el_id_y_la_empresa(monkeypatch, cola):
    from types import SimpleNamespace

    from app.api.v1.endpoints import jira_integration as modulo

    config = SimpleNamespace(id="cfg-1", organization_id="org-a")
    monkeypatch.setattr(modulo, "configuracion_propia", lambda db, u, cid: config)
    r = modulo.run_manual_sync("cfg-1", db=_SesionFalsa(), current_user=SimpleNamespace())
    assert r.data["ok"] is True
    _, args = cola[0]
    assert args[1] == ["app.services.service_desk.jira_sync_service:run_incremental_sync",
                       "org-a", [], {"config_id": "cfg-1"}]
    arbol = ast.parse((RAIZ / "app/api/v1/endpoints/jira_integration.py").read_text(encoding="utf-8"))
    assert not any(isinstance(n, ast.Call) and ast.unparse(n.func).endswith("add_task")
                   and any(ast.unparse(a) == "db" for a in n.args) for n in ast.walk(arbol))
