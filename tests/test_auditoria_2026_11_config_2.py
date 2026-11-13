"""Segunda auditoría 2026-11: configuración (16), escalas (17) y geo-IP (30).

Medido antes (HEAD bcae33d1, AST de `app/`): 95 lecturas de entorno
(`os.environ[...]`, `os.environ.get`, `os.getenv`, `os.environ.setdefault`, con
alias como `_os.getenv`) en 36 ficheros, 64 nombres literales más 3 nombres
dinámicos (15 variables OAuth de colaboración). Después: 5 lecturas en 3
ficheros, todas en `PERMITIDAS`.
"""
from __future__ import annotations

import ast
import logging
from pathlib import Path

import pytest

from app.core.config import Settings, settings

APP = Path(__file__).resolve().parents[1] / "app"

#: (fichero relativo a la raíz, variable) → por qué se queda en el entorno.
PERMITIDAS = {
    ("app/core/entorno.py", "TESTING"):
        "señal del arnés de pruebas; las pruebas la cambian con monkeypatch.setenv tras construir Settings",
    ("app/core/entorno.py", "PYTEST_CURRENT_TEST"): "la pone pytest en cada prueba",
    ("app/core/metrics.py", "PROMETHEUS_MULTIPROC_DIR"):
        "la consume prometheus_client del entorno del proceso; metrics.py la fija con setdefault",
    ("app/db/migrate_to_pg.py", "DATABASE_URL"): "CLI autónomo que debe correr sin el resto de Settings",
}


def _lecturas_de_entorno():
    for fichero in APP.rglob("*.py"):
        arbol = ast.parse(fichero.read_text(encoding="utf-8"))
        rel = fichero.relative_to(APP.parent).as_posix()
        for nodo in ast.walk(arbol):
            nombre = None
            if isinstance(nodo, ast.Call):
                f = ast.unparse(nodo.func)
                if f.endswith(("getenv", "environ.get", "environ.setdefault", "environ.pop")):
                    nombre = nodo.args[0] if nodo.args else None
            elif (isinstance(nodo, ast.Subscript) and isinstance(nodo.ctx, ast.Load)
                  and ast.unparse(nodo.value).endswith("environ")):
                nombre = nodo.slice
            else:
                continue
            if nombre is None:
                continue
            literal = nombre.value if isinstance(nombre, ast.Constant) else f"<dinámico: {ast.unparse(nombre)}>"
            yield rel, literal, nodo.lineno


def test_EL_HALLAZGO_no_hay_lecturas_de_entorno_fuera_de_settings_salvo_las_permitidas():
    lecturas = list(_lecturas_de_entorno())
    fuera = sorted(f"{f}:{ln} {v}" for f, v, ln in lecturas if (f, v) not in PERMITIDAS)
    assert fuera == [], (
        "Lectura de entorno fuera de Settings. Añade el campo a app/core/config_groups/proceso_config.py "
        f"(y su fila en README §4.2) o justifícala en PERMITIDAS: {fuera}")
    assert len(lecturas) == 5  # TESTING, PYTEST_CURRENT_TEST, 2× PROMETHEUS_MULTIPROC_DIR, DATABASE_URL


def test_tampoco_se_importa_environ_o_getenv_suelto():
    for fichero in APP.rglob("*.py"):
        for nodo in ast.walk(ast.parse(fichero.read_text(encoding="utf-8"))):
            if isinstance(nodo, ast.ImportFrom) and nodo.module == "os":
                nombres = {a.name for a in nodo.names}
                assert not nombres & {"environ", "getenv"}, f"{fichero}: from os import {nombres}"


@pytest.mark.parametrize("campo,defecto", [
    ("ENABLE_APSCHEDULER", True), ("ENABLE_CELERY_BEAT", False), ("CELERY_BEAT", False),
    ("FAIL_ON_DUAL_SCHEDULER", True), ("FAIL_ON_SCHEMA_DRIFT", None), ("EXPOSE_API_DOCS", False),
    ("CSRF_DOUBLE_SUBMIT", False), ("DISABLE_CSRF_MIDDLEWARE", False), ("ENABLE_SUPERADMIN_BYPASS", False),
    ("TENANT_AUTO_FILTER_GLOBAL", True), ("TENANT_AUTO_STAMP_ON_INSERT", True),
    ("REDIS_RECONNECT_BACKOFF_SECONDS", 30.0), ("PREDICTIVE_STATS_MAX_TICKETS", 200),
    ("CHANGE_BATCH_SCORE_MAX", 100), ("UPLOADS_DIR", "uploads"), ("COLLAB_SIGNED_MAX_ENTRIES", 20000),
    ("COLLAB_STORAGE_BACKEND", "local"), ("COLLAB_SEARCH_BACKEND", "auto"), ("COLLAB_BUS_BACKEND", "memory"),
    ("NATS_URL", "nats://localhost:4222"), ("OPENSEARCH_URL", "http://localhost:9200"),
    ("LIVEKIT_URL", "wss://livekit.local"), ("CLAMAV_PORT", 3310), ("CLAMAV_TIMEOUT", 30.0),
    ("VAPID_CONTACT", "mailto:noreply@contecflow.local"), ("APP_PUBLIC_URL", "http://localhost:3000"),
    ("MS365_TENANT_ID", "common"), ("WHISPER_BIN", "whisper"), ("WHISPER_MODEL", "base"),
    ("WHISPER_LOCAL_LANGUAGE", "es"), ("SEED_USERS_DATA_PATH", "seed_users_data.json"),
    ("GEOIP_LOOKUP_ENABLED", False), ("GEOIP_LOOKUP_URL", "https://ipapi.co/{ip}/json/"),
])
def test_cada_variable_movida_conserva_nombre_y_defecto(campo, defecto):
    assert Settings.model_fields[campo].default == defecto


def test_las_credenciales_oauth_de_colaboracion_estan_todas_en_settings():
    from app.services.collaboration._integrations import PROVIDERS
    nombres = {n for p in PROVIDERS.values() for n in (p.client_id_env, p.client_secret_env, p.redirect_env)}
    assert len(nombres) == 15
    assert nombres <= set(Settings.model_fields)


def test_un_interruptor_vacio_vale_su_defecto_y_true_cuenta(monkeypatch):
    monkeypatch.setenv("ENABLE_APSCHEDULER", "")
    monkeypatch.setenv("TENANT_AUTO_FILTER_GLOBAL", " ")
    monkeypatch.setenv("CSRF_DOUBLE_SUBMIT", "true")
    s = Settings()
    assert s.ENABLE_APSCHEDULER is True and s.TENANT_AUTO_FILTER_GLOBAL is True
    assert s.CSRF_DOUBLE_SUBMIT is True


# ── Interruptores de seguridad al arrancar ───────────────────────────────────

@pytest.mark.parametrize("entorno", ["production", "staging"])
def test_EL_HALLAZGO_csrf_desactivado_no_arranca_en_produccion(monkeypatch, entorno):
    from app import main
    monkeypatch.setattr(settings, "ENVIRONMENT", entorno)
    monkeypatch.setattr(settings, "DISABLE_CSRF_MIDDLEWARE", True)
    with pytest.raises(RuntimeError, match="DISABLE_CSRF_MIDDLEWARE"):
        main._enforce_security_switches_safety()


def test_csrf_desactivado_se_permite_en_desarrollo(monkeypatch):
    from app import main
    monkeypatch.setattr(settings, "ENVIRONMENT", "development")
    monkeypatch.setattr(settings, "DISABLE_CSRF_MIDDLEWARE", True)
    main._enforce_security_switches_safety()


def test_bypass_de_superadmin_sigue_sin_arrancar_fuera_de_desarrollo(monkeypatch):
    from app import main
    monkeypatch.setattr(settings, "ENVIRONMENT", "staging")
    monkeypatch.setattr(settings, "ENABLE_SUPERADMIN_BYPASS", True)
    with pytest.raises(RuntimeError, match="ENABLE_SUPERADMIN_BYPASS"):
        main._enforce_superadmin_bypass_safety()


def test_filtro_de_tenant_apagado_en_produccion_queda_en_critical(monkeypatch, caplog):
    from app import main
    monkeypatch.setattr(settings, "ENVIRONMENT", "production")
    monkeypatch.setattr(settings, "TENANT_AUTO_FILTER_GLOBAL", False)
    with caplog.at_level(logging.CRITICAL, logger="contecflow"):
        main._enforce_security_switches_safety()
    assert any("TENANT_AUTO_FILTER_GLOBAL" in r.getMessage() for r in caplog.records)


def test_el_middleware_csrf_lee_settings(monkeypatch):
    from app.core.csrf import CSRFMiddleware
    monkeypatch.setenv("TESTING", "0")
    monkeypatch.setattr(settings, "DISABLE_CSRF_MIDDLEWARE", False)
    monkeypatch.setattr(settings, "CSRF_DOUBLE_SUBMIT", True)
    m = CSRFMiddleware(lambda *a: None)
    assert m._enabled is True and m._double_submit is True
    monkeypatch.setattr(settings, "DISABLE_CSRF_MIDDLEWARE", True)
    assert CSRFMiddleware(lambda *a: None)._enabled is False


def test_deriva_de_esquema_sin_valor_sigue_al_entorno(monkeypatch):
    """`FAIL_ON_SCHEMA_DRIFT` sin fijar: on en staging/producción, off en el resto (como antes)."""
    assert Settings.model_fields["FAIL_ON_SCHEMA_DRIFT"].default is None


# ── Escalas (hallazgo 17) ─────────────────────────────────────────────────────

def _antigua_predictive(r):
    return "critical" if r >= 0.75 else "high" if r >= 0.50 else "medium" if r >= 0.25 else "low"


def _antigua_cambio(r):
    return "critical" if r >= 0.7 else "high" if r >= 0.4 else "medium" if r >= 0.2 else "low"


def _antigua_abandono(p):
    return "high" if p >= 0.6 else "medium" if p >= 0.3 else "low"


_REJILLA = [i / 100 for i in range(0, 101)]


def test_la_escala_de_probabilidad_es_la_de_predictive_analytics():
    from app.core.escalas import nivel_por_probabilidad
    assert [nivel_por_probabilidad(p) for p in _REJILLA] == [_antigua_predictive(p) for p in _REJILLA]


def test_escalas_propias_sin_cambios():
    from app.core.escalas import nivel_de_abandono, nivel_de_riesgo_de_cambio
    assert [nivel_de_riesgo_de_cambio(p) for p in _REJILLA] == [_antigua_cambio(p) for p in _REJILLA]
    assert [nivel_de_abandono(p) for p in _REJILLA] == [_antigua_abandono(p) for p in _REJILLA]


def test_EL_HALLAZGO_ml_trainer_y_oraculo_usan_la_escala_comun():
    from app.services.ai_modules._base import _severity_from_probability
    from app.services.ml_trainer import _risk_level
    # ml_trainer: antes 0,70/0,50/0,30.
    assert _risk_level(0.72, 0.1) == "high"       # antes critical
    assert _risk_level(0.1, 0.27) == "medium"     # antes low
    assert _risk_level(0.8, 0.2) == "critical"
    # oráculo: antes > 0,75 / > 0,5, suelo medium.
    assert _severity_from_probability(0.75) == "critical"   # antes high
    assert _severity_from_probability(0.5) == "high"        # antes medium
    assert _severity_from_probability(0.1) == "medium"      # el suelo se mantiene


def test_EL_HALLAZGO_la_correlacion_usa_un_solo_corte():
    from app.core.escalas import accion_por_correlacion
    assert accion_por_correlacion(0.67, 3) == "create_problem"   # la pasada estructural decía review
    assert accion_por_correlacion(0.67, 2) == "review"
    assert accion_por_correlacion(0.37, 5) == "review"           # la estructural decía monitor
    assert accion_por_correlacion(0.34, 5) == "monitor"


def test_los_cortes_se_ajustan_en_vivo_por_empresa(db):
    from app.core.escalas import accion_por_correlacion, nivel_por_probabilidad
    from app.services import settings_service
    settings_service.set_runtime_value(db, "risk", "RISK_PROBABILITY_CRITICAL", 0.9, "1")
    settings_service.set_runtime_value(db, "service_desk", "ALERT_CORRELATION_PROBLEM_SCORE", 0.8, "1")
    settings_service.invalidate_cache()
    try:
        assert nivel_por_probabilidad(0.8, db=db, org_id="1") == "high"
        assert nivel_por_probabilidad(0.8) == "critical"
        assert accion_por_correlacion(0.7, 3, db=db, org_id="1") == "review"
    finally:
        settings_service.invalidate_cache()


def test_no_quedan_cortes_sueltos_en_los_servicios_migrados():
    migrados = [
        "services/ml_trainer.py", "services/ai_modules/_base.py",
        "services/service_desk/predictive_analytics_service.py", "services/bi_anomaly_service.py",
        "services/service_desk/alert_correlation_service.py", "services/service_desk/change_rollout_service.py",
    ]
    for rel in migrados:
        for nodo in ast.walk(ast.parse((APP / rel).read_text(encoding="utf-8"))):
            if isinstance(nodo, ast.Compare):
                for op, der in zip(nodo.ops, nodo.comparators):
                    es_corte = (isinstance(op, (ast.GtE, ast.Gt)) and isinstance(der, ast.Constant)
                                and isinstance(der.value, float) and 0 < der.value < 1)
                    assert not es_corte, f"{rel}:{nodo.lineno} {ast.unparse(nodo)}"


# ── Geo-IP (hallazgo 30) ──────────────────────────────────────────────────────

class _Resp:
    status_code = 200

    def json(self):
        return {"country_code": "ES", "region": "Madrid", "city": "Madrid", "asn": "AS3352", "org": "Telefonica"}


class _Cliente:
    def __init__(self, llamadas, **kw):
        self.llamadas, self.kw = llamadas, kw

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def get(self, url):
        self.llamadas.append((url, self.kw.get("timeout")))
        return _Resp()


class _Peticion:
    headers: dict = {}


@pytest.fixture
def geoip(monkeypatch):
    from app.core import outbound_url
    from app.services import session_security as ss
    llamadas: list = []
    monkeypatch.setattr(outbound_url, "cliente_httpx", lambda **kw: _Cliente(llamadas, **kw))
    monkeypatch.setattr(ss, "_CACHE_GEOIP", {})
    return ss, llamadas


def test_EL_HALLAZGO_sin_activar_no_se_llama_a_terceros(geoip):
    ss, llamadas = geoip
    assert settings.GEOIP_LOOKUP_ENABLED is False
    out = ss._lookup_ip_intel("8.8.8.8", _Peticion())
    assert llamadas == [] and out["city"] is None


def test_activado_consulta_una_vez_por_ip_con_el_timeout_de_salida(geoip, monkeypatch):
    ss, llamadas = geoip
    monkeypatch.setattr(settings, "GEOIP_LOOKUP_ENABLED", True)
    monkeypatch.setattr(settings, "GEOIP_LOOKUP_URL", "https://geo.example/{ip}")
    monkeypatch.setattr(settings, "OUTBOUND_HTTP_TIMEOUT_SECONDS", 4.0)
    a = ss._lookup_ip_intel("8.8.8.8", _Peticion())
    b = ss._lookup_ip_intel("8.8.8.8", _Peticion())
    assert a == b and a["country_code"] == "ES" and a["ip_asn"] == "AS3352"
    assert llamadas == [("https://geo.example/8.8.8.8", 4.0)]


def test_activado_no_consulta_ips_privadas(geoip, monkeypatch):
    ss, llamadas = geoip
    monkeypatch.setattr(settings, "GEOIP_LOOKUP_ENABLED", True)
    for ip in ("10.0.0.1", "192.168.1.5", "127.0.0.1", "::1", "no-es-ip"):
        ss._lookup_ip_intel(ip, _Peticion())
    assert llamadas == []


# ── Clave de OpenAI heredada de la base (antes en os.environ) ─────────────────

def test_la_clave_heredada_ya_no_va_al_entorno(monkeypatch):
    import os
    from app.services.stt import openai_stt
    monkeypatch.setattr(settings, "OPENAI_API_KEY", "")
    monkeypatch.setattr(openai_stt, "_clave_heredada", "")
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    openai_stt.publicar_clave_heredada("sk-de-la-base")
    assert openai_stt.OpenAISTTProvider().is_available()
    assert "OPENAI_API_KEY" not in os.environ
