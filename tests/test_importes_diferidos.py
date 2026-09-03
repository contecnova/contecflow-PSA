"""Importes diferidos que apuntan a cosas que no existen.

Auditoría 2026-08. Un import dentro de una función **no revienta al arrancar**:
falla la primera vez que alguien llama a esa función. Si además está dentro de un
`try/except`, no falla nunca de forma visible — sólo devuelve un resultado
degradado. Esa combinación produjo **nueve funciones que no podían funcionar**, y
tres de ellas en completo silencio:

| Sitio | Qué importaba | Efecto real |
|---|---|---|
| `olap/query_engine.py` | `Resource` de `app.models.resources` — **no existe en ningún sitio** | el **Informe de Utilización salía siempre vacío**: el `ImportError` era la primera línea del `try` |
| `integrations.py` | `SlackConfig` de `app.models.slack` — el módulo no existe (está en `mfa`) | `get_slack_webhook_url` devolvía **siempre `None`**, y el `except ImportError: return None` lo explicaba como «no configurado». **Las notificaciones de Slack nunca salían**, con datos válidos sembrados |
| `customer_health_service.py` | `PortalSession` — **no existe** (es `ClientSession`) | el componente «actividad en el portal» del score de salud valía **50.0 constante para todos los clientes** |
| `worker.py` ×2 | `app.models.client` (el módulo es `clients`, plural) | fallo en tiempo de llamada |
| `capacity_planning_service.py`, `sd_reporting_service.py` | `app.models.auth` — no existe (es `user`) | dos informes que **fallaban en cada llamada** |
| `predictive_observability.py` | `Organization` de `enterprise` (está en `mfa`) | la comprobación anti-enumeración de IDs lanzaba `ImportError` en vez de validar |

## El detector, y las dos veces que lo tuve mal

La primera versión comparaba con `hasattr(modulo, nombre)`. **Da falsos
positivos con submódulos**: `from app.services import dev_plan_service` funciona
aunque `hasattr(app.services, "dev_plan_service")` sea falso hasta que se
importe. Con eso conté 8 roturas donde había 3.

Antes de eso, otra versión comparaba contra las clases que cada módulo declara
por AST, y dio **412 «fallos»** — entre ellos `Money` y `Rate`, que obviamente
existen. Si esa cifra se hubiera publicado sin comprobarla, el informe habría
sido basura.

Así que este test **no razona sobre el código: ejecuta el import**. Es la única
comprobación que no se puede equivocar sobre si un import funciona.
"""
from __future__ import annotations

import ast
import importlib
import pathlib

import pytest

#: Importes diferidos que se sabe que NO resuelven, con el motivo. Son puntos de
#: integración que nunca se construyeron, no rutas mal escritas: implementarlos
#: es trabajo de producto (qué evento de SLA corresponde, por qué canal se avisa
#: a un observador, qué modelo responde en el bot), así que quedan aquí
#: registrados en vez de arreglados a ciegas.
#:
#: El código de cada sitio distingue ya `ImportError` («no está escrito») de un
#: fallo de la llamada, para que el día que se implementen un error suyo se vea.
NO_IMPLEMENTADOS = {
    ("app.services.service_desk.sla_event_service", "record_sla_event"):
        "el evento de cierre de SLA en una auto-resolución nunca se registra",
    ("app.services.service_desk.watcher_service", "notify_watchers"):
        "a los observadores de un ticket no se les avisa de la auto-resolución",
    ("app.services.ai_chat_service", "quick_answer"):
        "la vía de IA del bot Nexus nunca responde; cae al resumidor ingenuo",
}


def _importes_diferidos() -> list[tuple[str, int, str, str]]:
    """Los `from app... import X` que están **dentro de una función**.

    Los de nivel de módulo no hacen falta: si uno estuviera roto, la aplicación
    no arrancaría y no habría suite que ejecutar. El riesgo está justo en los
    otros.
    """
    encontrados = []
    for f in sorted(pathlib.Path("app").rglob("*.py")):
        if "__pycache__" in f.as_posix():
            continue
        try:
            arbol = ast.parse(f.read_text(encoding="utf-8", errors="replace"))
        except SyntaxError:
            continue
        for fn in ast.walk(arbol):
            if not isinstance(fn, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            for n in ast.walk(fn):
                if (isinstance(n, ast.ImportFrom) and n.module
                        and n.module.startswith("app.")):
                    for a in n.names:
                        if a.name != "*":
                            encontrados.append(
                                (f.as_posix(), n.lineno, n.module, a.name))
    return encontrados


def _resuelve(mod: str, nombre: str) -> str | None:
    """`None` si el import funciona; el motivo si no.

    Se **ejecuta** el import en vez de razonar sobre el módulo, porque razonar
    falla con los submódulos: `from app.services import dev_plan_service`
    funciona aunque `dev_plan_service` no sea un atributo cargado.
    """
    try:
        m = importlib.import_module(mod)
    except Exception as exc:
        return "el módulo no importa: %s: %s" % (type(exc).__name__, exc)
    if hasattr(m, nombre):
        return None
    try:
        importlib.import_module("%s.%s" % (mod, nombre))
        return None          # era un submódulo
    except Exception:
        return "el módulo no define '%s'" % nombre


def test_EL_ESTRUCTURAL_ningun_importe_diferido_apunta_a_algo_que_no_existe():
    """El que impide que vuelva a entrar uno.

    Nueve funciones no podían funcionar por esto, tres de ellas en silencio.
    Ninguna daba error en la suite: un import dentro de una función no se
    ejecuta hasta que alguien llama, y dentro de un `try` no se ve nunca.
    """
    roto = []
    for ruta, ln, mod, nombre in _importes_diferidos():
        if (mod, nombre) in NO_IMPLEMENTADOS:
            continue
        motivo = _resuelve(mod, nombre)
        if motivo:
            roto.append("%s:%d  from %s import %s  → %s"
                        % (ruta, ln, mod, nombre, motivo))
    assert not roto, (
        "hay %d importes diferidos que no resuelven:\n  %s\n\n"
        "Un import dentro de una función falla en tiempo de llamada, y si está "
        "dentro de un try/except no falla nunca de forma visible: sólo degrada."
        % (len(roto), "\n  ".join(roto))
    )


@pytest.mark.parametrize("mod,nombre", sorted(NO_IMPLEMENTADOS))
def test_los_no_implementados_siguen_sin_implementarse(mod, nombre):
    """La lista de excepciones tiene que caducar sola.

    Si alguien implementa una de las tres, este test falla y obliga a sacarla de
    `NO_IMPLEMENTADOS` — que es cuando el estructural de arriba empieza a
    vigilarla. Sin esto, la lista se convertiría en el sitio donde se esconden
    los importes rotos nuevos.
    """
    assert _resuelve(mod, nombre) is not None, (
        "'%s' ya existe en %s: sácalo de NO_IMPLEMENTADOS (motivo registrado: %s)"
        % (nombre, mod, NO_IMPLEMENTADOS[(mod, nombre)])
    )


def test_el_detector_encuentra_un_import_roto_plantado():
    """El detector, probado. Un estructural cuyo detector está roto da luz verde
    sin mirar — y este detector ya lo tuve mal dos veces."""
    assert _resuelve("app.models.resources", "NoExisteEstaClase") is not None
    assert _resuelve("app.models.no_existe_este_modulo", "X") is not None


def test_el_detector_no_se_confunde_con_un_submodulo():
    """El falso positivo que tuvo la primera versión: `hasattr` sobre un paquete
    dice que no tiene el submódulo hasta que alguien lo importa, pero el
    `from ... import` funciona igual. Con eso conté 8 roturas donde había 3."""
    assert _resuelve("app.services", "dev_plan_service") is None
    assert _resuelve("app.models", "user") is None


def test_los_arreglados_resuelven():
    """Los nueve del hallazgo, uno a uno, con su módulo correcto."""
    for mod, nombre in [
        ("app.models.clients", "Client"),
        ("app.models.user", "User"),
        ("app.models.mfa", "Organization"),
        ("app.models.mfa", "SlackConfig"),
        ("app.models.client_portal", "ClientSession"),
        ("app.models.client_portal", "ClientUser"),
        ("app.models.user", "User"),
    ]:
        assert _resuelve(mod, nombre) is None, "%s.%s" % (mod, nombre)


def test_las_clases_fantasma_siguen_sin_existir():
    """Fija el diagnóstico: no eran rutas mal escritas de clases que existían en
    otro sitio, es que `Resource` y `PortalSession` **no existen en el repo**.
    Si alguien las crea, este test falla y obliga a revisar si el arreglo que se
    hizo (usar `User.weekly_capacity_hours` y `ClientSession`) sigue siendo el
    correcto."""
    for mod in ("app.models.resources", "app.models.client_portal"):
        m = importlib.import_module(mod)
        assert not hasattr(m, "Resource"), (
            "se ha creado `Resource`: revisa `_pg_utilization_by_user`, que ahora "
            "lee la capacidad de `User.weekly_capacity_hours`"
        )
        assert not hasattr(m, "PortalSession"), (
            "se ha creado `PortalSession`: revisa el score de actividad de portal, "
            "que ahora usa `ClientSession` con join por `ClientUser.client_org_id`"
        )
