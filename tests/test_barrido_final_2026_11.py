"""Barrido final 2026-11: lo que ninguna auditoría anterior había mirado.

Cada test fija un hallazgo medido (ver DOCS.md, «Segunda auditoría 2026-11:
cambios de comportamiento», apartado «Barrido final»).
"""
from __future__ import annotations

import contextlib
import importlib.util
import re
from pathlib import Path
from types import SimpleNamespace

import pytest
import sqlalchemy as sa

from tests.conftest import auth

REPO = Path(__file__).resolve().parents[1]


# ── Errores internos que llegaban al cliente ─────────────────────────────────

def test_health_composite_no_devuelve_el_texto_de_la_excepcion(client, admin_token, monkeypatch):
    from app.api.v1.endpoints import health_composite as mod

    def _revienta(*_a, **_k):
        raise RuntimeError("boom-detalle-interno")

    monkeypatch.setattr(mod, "compute_composite_health", _revienta)
    r = client.get("/api/v1/clients/x/health-composite", headers=auth(admin_token))
    assert r.status_code == 500
    assert "boom-detalle-interno" not in r.text


def test_health_composite_conserva_el_codigo_de_un_error_de_dominio(client, admin_token, monkeypatch):
    """Antes un 403 de dominio salía como 500 «Error inesperado: …»."""
    from app.api.v1.endpoints import health_composite as mod
    from app.core.errores import ErrorDeDominio

    def _prohibido(*_a, **_k):
        raise ErrorDeDominio(403, "sin permiso")

    monkeypatch.setattr(mod, "compute_composite_health", _prohibido)
    r = client.get("/api/v1/customers/x/health-composite", headers=auth(admin_token))
    assert r.status_code == 403


def test_resumen_ia_no_devuelve_el_error_del_proveedor(client, admin_token, monkeypatch):
    """El error de un proveedor puede citar parte de la clave («Incorrect API key provided: sk-…»)."""
    from app.api.v1.endpoints import documents as mod

    doc = SimpleNamespace(versions=[SimpleNamespace(file_key="k", file_name="a.txt", file_mime_type="text/plain")])
    monkeypatch.setattr(mod, "get_document_or_404", lambda *_a, **_k: doc)
    monkeypatch.setattr(mod, "check_document_access", lambda *_a, **_k: None)
    monkeypatch.setattr(mod.doc_svc, "extract_document_text", lambda *_a, **_k: "texto")

    def _falla(*_a, **_k):
        raise RuntimeError("Incorrect API key provided: sk-abc123SECRETO")

    monkeypatch.setattr(mod, "call_ai", _falla)
    r = client.post("/api/v1/documents/d1/ai-summary", headers=auth(admin_token))
    assert r.status_code == 503
    assert "SECRETO" not in r.text


def test_la_transcripcion_no_devuelve_el_texto_de_la_excepcion():
    fuente = (REPO / "app/api/v1/endpoints/ai_modules.py").read_text(encoding="utf-8")
    assert "Error inesperado de transcripción: {" not in fuente


# ── Fechas mal formadas: 422/400, no 500 ─────────────────────────────────────

@pytest.mark.parametrize("url", [
    "/api/v1/bookings/conflicts?start_date=no-es-fecha",
    "/api/v1/bookings/gantt-leveling?end_date=2026-13-40",
    "/api/v1/capacity/board?week_from=ayer",
    "/api/v1/resource-forecast/availability?from_date=x",
    "/api/v1/resource-forecast/weeks?from_date=x",
])
def test_fecha_mal_formada_en_query_es_422(client, pm_token, url):
    r = client.get(url, headers=auth(pm_token))
    assert r.status_code == 422, r.text


def test_plan_de_capacidad_con_fecha_mala_es_400(client, pm_token):
    r = client.post("/api/v1/capacity/plans", headers=auth(pm_token),
                    json={"week_start": "31/02/2026", "planned_hours": 8})
    assert r.status_code == 400, r.text


# ── Índices de claves ajenas calientes ───────────────────────────────────────

def _migracion_163():
    ruta = REPO / "alembic/versions/163_indices_de_claves_ajenas_calientes.py"
    spec = importlib.util.spec_from_file_location("m163", ruta)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_los_modelos_declaran_los_indices_de_la_163():
    from app.db.base import Base
    import app.models  # noqa: F401

    m = _migracion_163()
    for tabla, columna in m.INDICES:
        nombres = {i.name for i in Base.metadata.tables[tabla].indexes}
        assert m._nombre(tabla, columna) in nombres, (tabla, columna)


def test_la_163_crea_los_indices_y_es_idempotente(tmp_path):
    from alembic.migration import MigrationContext
    from alembic.operations import Operations

    m = _migracion_163()
    motor = sa.create_engine(f"sqlite:///{tmp_path / 'm.db'}")
    with motor.begin() as c:
        for tabla in {t for t, _ in m.INDICES}:
            cols = ", ".join(f'"{col}" TEXT' for t, col in m.INDICES if t == tabla)
            c.exec_driver_sql(f'CREATE TABLE "{tabla}" (id TEXT PRIMARY KEY, {cols})')
    for _ in range(2):  # la segunda pasada no debe fallar
        with motor.connect() as c:
            ctx = MigrationContext.configure(c)
            # Fuera del runner de Alembic no hay transacción que cerrar; la
            # cadena completa la ejercita tests/test_alembic_schema_parity.py.
            ctx.autocommit_block = contextlib.nullcontext
            with Operations.context(ctx):
                m.upgrade()
            c.commit()
    insp = sa.inspect(motor)
    for tabla, columna in m.INDICES:
        assert m._nombre(tabla, columna) in {i["name"] for i in insp.get_indexes(tabla)}


# ── nginx: la SPA salía sin cabeceras de seguridad ───────────────────────────

_NGINX = REPO / "frontend/nginx.frontend.conf"
_SEGURIDAD = ("Content-Security-Policy", "X-Content-Type-Options", "X-Frame-Options",
              "Referrer-Policy", "Permissions-Policy", "Cross-Origin-Opener-Policy")


def _cabeceras(bloque: str) -> dict[str, str]:
    return dict(re.findall(r'add_header\s+(\S+)\s+"([^"]*)"', bloque))


def test_index_html_lleva_las_mismas_cabeceras_que_el_servidor():
    """Un `add_header` en un `location` anula la herencia de los del `server`."""
    conf = _NGINX.read_text(encoding="utf-8")
    servidor = _cabeceras(conf[:re.search(r"^\s*location ", conf, re.M).start()])
    inicio = conf.index("location = /index.html")
    index = _cabeceras(conf[inicio:conf.index("}", inicio)])
    for h in _SEGURIDAD:
        assert index.get(h) == servidor.get(h), h


def test_la_csp_de_nginx_permite_lo_que_la_spa_usa():
    csp = _cabeceras(_NGINX.read_text(encoding="utf-8"))["Content-Security-Policy"]
    assert "https://fonts.googleapis.com" in csp and "https://fonts.gstatic.com" in csp  # src/index.css
    assert "media-src 'self' blob:" in csp  # audio del VoiceCommandModal
    pp = _cabeceras(_NGINX.read_text(encoding="utf-8"))["Permissions-Policy"]
    assert "microphone=(self)" in pp


# ── .env.example: producción no arrancaba con él ─────────────────────────────

def test_env_example_basta_para_arrancar_en_produccion(monkeypatch):
    from app.core.config import Settings

    valores = {}
    for linea in (REPO / ".env.example").read_text(encoding="utf-8").splitlines():
        m = re.match(r"^([A-Z][A-Z0-9_]*)=(.*)$", linea)
        if m:
            valores[m.group(1)] = m.group(2).split(" #")[0].strip()
    # Sólo importa que la variable esté documentada: los valores de ejemplo se
    # sustituyen por unos válidos para producción.
    for k, v in list(valores.items()):
        if not v or "CHANGE_ME" in v:
            valores[k] = "Zq8!" + "x7Kp2Lm9Rt4Vw6Yb3Nc5Hd1Jf0Gs" * 2
        elif "localhost" in v or "127.0.0.1" in v:
            valores[k] = v.replace("localhost", "app.example.com").replace("127.0.0.1", "app.example.com")
    valores["ENVIRONMENT"] = "production"
    valores["DATABASE_URL"] = "postgresql://u:p@db:5432/x"

    for nombre, campo in Settings.model_fields.items():
        env = (campo.json_schema_extra or {}).get("env") if isinstance(campo.json_schema_extra, dict) else None
        for clave in {nombre, env} - {None}:
            if clave not in valores:
                monkeypatch.delenv(clave, raising=False)
    for k, v in valores.items():
        monkeypatch.setenv(k, v)

    Settings(_env_file=None)


def test_prometheus_multiproc_dir_se_lee_de_su_variable(monkeypatch):
    from app.core.config import Settings

    monkeypatch.setenv("PROMETHEUS_MULTIPROC_DIR", "/tmp/prom-x")
    assert Settings().METRICS_MULTIPROC_DIR == "/tmp/prom-x"


def test_env_example_usa_los_nombres_reales_de_azure():
    texto = (REPO / ".env.example").read_text(encoding="utf-8")
    assert "AZURE_AD_" not in texto
    assert "AZURE_TENANT_ID" in texto


# ── Dependencias con avisos de seguridad ─────────────────────────────────────

_MINIMOS = {"pypdf": "6.21.4", "pyasn1": "0.6.5", "certifi": "2026.10.18", "dnspython": "2.9.2",
            "urllib3": "2.8.0", "aiohttp": "3.14.4", "anyio": "4.14.2", "PyJWT": "2.15.0"}


def test_las_versiones_fijadas_incluyen_los_parches():
    from packaging.version import Version

    fijadas = dict(re.findall(r"^([A-Za-z0-9_.-]+)==([^\s;#]+)",
                              (REPO / "requirements.txt").read_text(encoding="utf-8"), re.M))
    for paquete, minimo in _MINIMOS.items():
        assert Version(fijadas[paquete]) >= Version(minimo), paquete
    assert '"axios": "^1.21.1"' in (REPO / "frontend/package.json").read_text(encoding="utf-8")
