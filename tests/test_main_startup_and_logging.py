"""Las fases del arranque y el logging de peticiones de `app/main.py`.

Auditoría 2026-08 (P3-18). Dos funciones de `main.py` estaban entre las más
complejas del proyecto y ninguna tenía un solo test propio:

  `lifespan`        216 líneas, complejidad 29 — el **arranque** de la aplicación
  `request_logger`   50 líneas, complejidad 11 — se ejecuta en **cada** petición

Se partieron en fases con nombre. Estos tests fijan lo que antes no se podía
probar porque vivía dentro de un middleware y de un gestor de contexto asíncrono:

  · que el arranque completo se ejecuta y la aplicación queda servible
  · que los servicios de apoyo son *best-effort* de verdad — que uno falle no
    puede impedir que la aplicación arranque (lo contrario dejaría el servicio
    entero caído por una funcionalidad opcional)
  · que el nivel de log de cada familia de respuestas es el que se decidió, con
    la excepción de los 401 esperados que existe para que un log a WARNING no se
    llene de ruido de renovación de cookies
  · que los secretos de la URL no acaban en el log

El caso de los secretos no es cosmético: `request_logger` loguea la URL completa
en todo 4xx/5xx, y un `/callback?code=...` fallido es exactamente un 4xx.
"""
from __future__ import annotations

import logging
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from app.main import (
    _arrancar_planificador,
    _arrancar_planificador_de_colaboracion,
    _arrancar_servicios_de_apoyo,
    _comprobar_dependencias_opcionales,
    _nivel_y_icono,
    _parar_planificador_de_colaboracion,
    _parar_servicios,
    _pista_de_usuario,
    _url_sin_secretos,
    app,
)


# ── El arranque de punta a punta ──────────────────────────────────────────────
#
# El TestClient como gestor de contexto ejecuta `lifespan` entero: entrada,
# `yield` y salida. Es la red de seguridad real del refactor.

def test_el_arranque_completo_deja_la_aplicacion_servible():
    with TestClient(app) as cliente:
        assert cliente.get("/health").status_code == 200


def test_el_arranque_registra_el_router_completo():
    """Si una fase del arranque revienta a media, el router queda incompleto.

    El umbral no es decorativo: es la comprobación que cazó que FastAPI 0.139
    enumeraba **9** rutas en vez de dos mil por hacer `include_router` perezoso,
    y con ello 19 tests culpando al producto de un problema que no existía. Se
    fija un mínimo y no el número exacto para que añadir un endpoint no rompa el
    test, pero cualquier caída de ese orden de magnitud sí.

    Los websocket no cuentan aquí porque no tienen `.methods`, que es el mismo
    criterio con el que el arranque loguea su cifra de endpoints.
    """
    con_metodos = [r for r in app.routes if hasattr(r, "methods")]
    assert len(con_metodos) > 1900, f"solo {len(con_metodos)} rutas registradas"


# ── Las fases son best-effort de verdad ───────────────────────────────────────

def test_un_servicio_de_apoyo_caido_no_impide_el_arranque(monkeypatch, caplog):
    """La razón de que cada bloque lleve su propio `try`.

    Se simula que la gestión de claves revienta. En un entorno que no es
    producción tiene que quedar en un error logueado, no en una excepción: un
    servicio de apoyo caído degrada una funcionalidad, un arranque abortado
    tumba el servicio entero.
    """
    import app.services.key_management as km
    monkeypatch.setattr(
        km, "rotate_due_materials", lambda: (_ for _ in ()).throw(RuntimeError("boom"))
    )
    monkeypatch.setattr("app.main.settings.ENVIRONMENT", "development")

    with caplog.at_level(logging.ERROR):
        _arrancar_servicios_de_apoyo()   # no debe lanzar

    assert any("Key management init failed" in r.message % r.args if r.args else
               "Key management init failed" in r.message for r in caplog.records)


def test_en_produccion_un_fallo_de_claves_si_aborta_el_arranque(monkeypatch):
    """La excepción a la regla anterior, y es deliberada.

    Arrancar en producción sin gestión de claves significa servir con material
    criptográfico sin rotar. Ahí sí se prefiere no arrancar.
    """
    import app.services.key_management as km
    monkeypatch.setattr(
        km, "rotate_due_materials", lambda: (_ for _ in ()).throw(RuntimeError("boom"))
    )
    monkeypatch.setattr("app.main.settings.ENVIRONMENT", "production")

    with pytest.raises(RuntimeError):
        _arrancar_servicios_de_apoyo()


def test_las_dependencias_opcionales_solo_avisan(monkeypatch, caplog):
    """Sin `qrcode`/`pyotp` la aplicación arranca; sólo el MFA queda sin poder
    configurarse. Se comprueba que avisa y que no lanza."""
    import builtins
    real = builtins.__import__

    def sin_qrcode(nombre, *a, **k):
        if nombre == "qrcode":
            raise ImportError("simulado")
        return real(nombre, *a, **k)

    monkeypatch.setattr(builtins, "__import__", sin_qrcode)
    with caplog.at_level(logging.WARNING):
        _comprobar_dependencias_opcionales()
    assert any("MFA dependencies missing" in r.message for r in caplog.records)


def test_las_dependencias_opcionales_callan_cuando_estan_todas(caplog):
    with caplog.at_level(logging.WARNING):
        _comprobar_dependencias_opcionales()
    assert not [r for r in caplog.records if "MFA dependencies missing" in r.message]


# ── El planificador ───────────────────────────────────────────────────────────

def test_el_planificador_no_se_levanta_si_esta_deshabilitado():
    assert _arrancar_planificador(False, False) is None


def test_el_modo_dual_aborta_el_arranque(monkeypatch):
    """Ésta es la que importa, y la guarda NO está en `_arrancar_planificador`.

    Con APScheduler y Celery beat activos a la vez las 4 tareas periódicas se
    ejecutan **dos veces**: informes enviados dos veces, rotación de claves dos
    veces, motor de alertas dos veces. `_arrancar_planificador(True, True)`
    levanta el planificador igualmente — lo que impide llegar ahí es
    `_enforce_scheduler_mode_safety()`, que corre antes y aborta.

    Se comprueba que aborta **por defecto**, sin necesidad de configurar nada, y
    que sólo se puede desactivar poniéndolo explícitamente a 0.
    """
    from app.main import _enforce_scheduler_mode_safety

    monkeypatch.setenv("ENABLE_APSCHEDULER", "1")
    monkeypatch.setenv("ENABLE_CELERY_BEAT", "1")
    monkeypatch.delenv("FAIL_ON_DUAL_SCHEDULER", raising=False)

    with pytest.raises(RuntimeError, match="Dual scheduler"):
        _enforce_scheduler_mode_safety()


def test_el_modo_dual_se_puede_permitir_explicitamente(monkeypatch):
    """La salida de emergencia existe, pero hay que pedirla a mano."""
    from app.main import _enforce_scheduler_mode_safety

    monkeypatch.setenv("ENABLE_APSCHEDULER", "1")
    monkeypatch.setenv("ENABLE_CELERY_BEAT", "1")
    monkeypatch.setenv("FAIL_ON_DUAL_SCHEDULER", "0")
    _enforce_scheduler_mode_safety()   # no debe lanzar


@pytest.mark.parametrize(
    "aps,beat,modo",
    [("1", "0", "apscheduler"), ("0", "1", "celery_beat"),
     ("0", "0", "none"), ("1", "1", "dual")],
)
def test_el_modo_de_planificador_se_resuelve_de_los_flags(monkeypatch, aps, beat, modo):
    from app.main import _scheduler_mode

    monkeypatch.setenv("ENABLE_APSCHEDULER", aps)
    monkeypatch.setenv("ENABLE_CELERY_BEAT", beat)
    monkeypatch.delenv("CELERY_BEAT", raising=False)
    assert _scheduler_mode() == modo


def test_parar_el_planificador_tolera_que_no_haya_ninguno():
    _parar_servicios(None)   # no debe lanzar


def test_parar_el_planificador_tolera_uno_ya_detenido():
    """`shutdown()` sobre un planificador parado lanza. Pasa de verdad cuando
    uvicorn recarga: el proceso viejo ya lo paró."""
    _parar_servicios(SimpleNamespace(running=False))


def test_el_planificador_de_colaboracion_se_omite_en_pruebas(monkeypatch):
    llamado = []
    monkeypatch.setattr(
        "app.services.collaboration._scheduler.start", lambda: llamado.append(1)
    )
    _arrancar_planificador_de_colaboracion(_is_testing=True)
    assert llamado == []


def test_el_planificador_de_colaboracion_arranca_fuera_de_pruebas(monkeypatch):
    llamado = []
    monkeypatch.setattr(
        "app.services.collaboration._scheduler.start", lambda: llamado.append(1)
    )
    _arrancar_planificador_de_colaboracion(_is_testing=False)
    assert llamado == [1]


def test_parar_la_colaboracion_no_propaga_fallos(monkeypatch):
    monkeypatch.setattr(
        "app.services.collaboration._scheduler.stop",
        lambda: (_ for _ in ()).throw(RuntimeError("boom")),
    )
    _parar_planificador_de_colaboracion()   # no debe lanzar


# ── El nivel de log de cada respuesta ─────────────────────────────────────────

@pytest.mark.parametrize(
    "status,nivel",
    [
        (200, logging.INFO),
        (204, logging.INFO),
        (301, logging.INFO),
        (304, logging.INFO),
        (400, logging.WARNING),
        (403, logging.WARNING),
        (404, logging.WARNING),
        (422, logging.WARNING),
        (500, logging.ERROR),
        (502, logging.ERROR),
    ],
)
def test_el_nivel_por_familia_de_respuesta(status, nivel):
    assert _nivel_y_icono(status, "/api/v1/projects")[0] == nivel


def test_un_401_esperado_baja_a_info():
    """El sondeo de sesión al arrancar la aplicación es un 401 normal, no un
    problema. Se loguea a INFO para no llenar de ruido un log a WARNING."""
    nivel, icono = _nivel_y_icono(401, "/api/v1/auth/me")
    assert nivel == logging.INFO
    assert icono == "🔑"


def test_un_401_en_cualquier_otra_ruta_sigue_siendo_aviso():
    """La excepción es una lista cerrada a propósito: un 401 en una ruta de
    datos sí es una señal que hay que ver."""
    assert _nivel_y_icono(401, "/api/v1/projects")[0] == logging.WARNING


# ── La URL del log no puede llevar secretos ───────────────────────────────────

def _peticion(url: str, cabeceras: dict | None = None):
    from starlette.datastructures import Headers
    return SimpleNamespace(url=url, headers=Headers(cabeceras or {}))


@pytest.mark.parametrize(
    "parametro",
    ["token", "access_token", "refresh_token", "code", "state", "id_token"],
)
def test_los_parametros_sensibles_se_tapan(parametro):
    """`request_logger` loguea la URL completa en todo 4xx/5xx, y un
    `/callback?code=...` fallido es exactamente un 4xx."""
    url = f"https://x/api/v1/auth/callback?{parametro}=SECRETO123&otro=1"
    salida = _url_sin_secretos(_peticion(url))
    assert "SECRETO123" not in salida
    assert f"{parametro}=[REDACTED]" in salida
    assert "otro=1" in salida


def test_varios_secretos_en_la_misma_url():
    url = "https://x/cb?code=AAA&state=BBB&id_token=CCC"
    salida = _url_sin_secretos(_peticion(url))
    assert "AAA" not in salida and "BBB" not in salida and "CCC" not in salida


def test_una_url_sin_secretos_no_se_toca():
    url = "https://x/api/v1/projects?page=2&q=hola"
    assert _url_sin_secretos(_peticion(url)) == url


# ── La pista de usuario ───────────────────────────────────────────────────────

def test_sin_cabecera_de_autorizacion_no_hay_pista():
    assert _pista_de_usuario(_peticion("https://x/")) == ""


def test_una_cabecera_que_no_es_bearer_se_ignora():
    peticion = _peticion("https://x/", {"Authorization": "Basic dXNlcjpwYXNz"})
    assert _pista_de_usuario(peticion) == ""


def test_un_token_ilegible_no_tumba_el_logging():
    """El `except` amplio existe por esto: un token corrupto no puede impedir
    que la petición se loguee."""
    peticion = _peticion("https://x/", {"Authorization": "Bearer no-es-un-jwt"})
    assert _pista_de_usuario(peticion) == ""


def test_un_token_valido_deja_los_8_primeros_del_sujeto(monkeypatch):
    monkeypatch.setattr(
        "app.core.security.decode_token", lambda _t: {"sub": "0123456789abcdef"}
    )
    peticion = _peticion("https://x/", {"Authorization": "Bearer x.y.z"})
    assert _pista_de_usuario(peticion) == " | user:01234567"


def test_un_token_sin_sujeto_no_revienta(monkeypatch):
    monkeypatch.setattr("app.core.security.decode_token", lambda _t: {"otro": 1})
    peticion = _peticion("https://x/", {"Authorization": "Bearer x.y.z"})
    assert _pista_de_usuario(peticion) == " | user:?"
