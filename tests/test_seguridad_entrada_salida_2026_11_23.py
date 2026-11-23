"""Seguridad transversal de entrada y salida (auditoría 22-11-2026, arreglos del 23-11-2026).

01 M4/M5/M6/M7/M10, 02 C4/A27/A28/A37/A38/A39/M59/M80/M94, 03 A-RZ2/A-RZ4.
Documentado en docs/seguridad/entrada_y_salida.md.
"""
from __future__ import annotations

import asyncio
import json
import re
import socket
import sqlite3
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

RAIZ = Path(__file__).resolve().parents[1]
APP = RAIZ / "app"


# ── SSRF: un solo guardia ─────────────────────────────────────────────────────

@pytest.mark.parametrize("url", [
    "http://100.64.1.1/", "http://[::ffff:127.0.0.1]/", "http://[64:ff9b::a9fe:a9fe]/",
    "http://metadata.google.internal/", "https://u:p@example.com/", "file:///etc/passwd",
    "http://169.254.169.254/latest/meta-data/", "http://intranet.local/",
])
def test_el_guardia_central_rechaza_destinos_internos(url):
    from app.core.errores import ErrorDeDominio
    from app.core.outbound_url import validate_outbound_url
    with pytest.raises(ErrorDeDominio):
        validate_outbound_url(url)


def test_no_hay_otro_validador_ssrf():
    """Los antiguos (webhooks, automatizaciones, reservas, OIDC, network) delegan."""
    propios = []
    for f in APP.rglob("*.py"):
        rel = f.relative_to(APP).as_posix()
        if rel in {"core/outbound_url.py", "services/session_security.py"}:
            continue
        texto = f.read_text(encoding="utf-8")
        if re.search(r"\.is_link_local\b|\bip\w*\.is_private\b|getaddrinfo\(", texto):
            propios.append(rel)
    assert propios == []


#: Ficheros que aún llaman a httpx directamente, con por qué es seguro
#: (docs/seguridad/entrada_y_salida.md, «Salidas que quedan»).
_SALIDAS_REVISADAS = {
    "core/outbound_url.py",                      # el propio guardia
    "services/conectores/anfitrion.py",          # `httpx` es la salida segura (_SalidaSegura)
    "services/bi_o365_service.py", "services/m365_bi_embed_service.py", "services/m365_service.py",
    "services/collaboration/_integrations.py", "services/collaboration/_integrations_clients.py",
    "services/collaboration/_transcription.py", "services/exchange_rate_service.py",
    "services/stripe_service.py", "services/stt/google_stt.py", "services/stt/openai_stt.py",
    "services/stt/azure_stt.py", "services/reuniones/bots/recall.py",
    "services/reuniones/conectores/__init__.py", "services/teams_bot.py",
    "services/service_desk/canal_slack.py", "services/service_desk/buzones.py",
    "services/cab_service/integraciones.py",
}


def test_nadie_nuevo_llama_a_httpx_sin_el_guardia():
    nuevos = []
    for f in APP.rglob("*.py"):
        rel = f.relative_to(APP).as_posix()
        if rel in _SALIDAS_REVISADAS:
            continue
        if re.search(r"\bhttpx\.(get|post|put|patch|delete|request|stream|Client|AsyncClient)\(|urlopen\(",
                     f.read_text(encoding="utf-8")):
            nuevos.append(rel)
    assert nuevos == [], ("Llamada saliente sin `cliente_httpx`/`peticion` de app/core/outbound_url.py; "
                          "si el host es fijo de plataforma, añádelo a _SALIDAS_REVISADAS con su motivo")


def test_la_ip_conectada_se_comprueba_aunque_la_url_haya_pasado(monkeypatch):
    """DNS rebinding: aunque la validación previa pase, conectar a una IP interna se corta."""
    from app.core import outbound_url
    servidor = socket.socket()
    servidor.bind(("127.0.0.1", 0))
    servidor.listen(8)  # dos conexiones sin aceptar (síncrona y asíncrona): cola > 1
    puerto = servidor.getsockname()[1]
    monkeypatch.setattr(outbound_url, "_validar_peticion", lambda request: None)
    try:
        with outbound_url.cliente_httpx(timeout=3) as c, pytest.raises(outbound_url.ConexionBloqueada):
            c.get(f"http://127.0.0.1:{puerto}/")

        async def _asincrono():
            async with outbound_url.cliente_httpx_async(timeout=3) as c:
                await c.get(f"http://127.0.0.1:{puerto}/")
        with pytest.raises(outbound_url.ConexionBloqueada):
            asyncio.run(_asincrono())
    finally:
        servidor.close()


def test_la_url_del_proveedor_de_ia_pasa_por_el_guardia():
    """02 C4: un `api_base_url` de empresa hacia la red interna se rechaza al guardar."""
    from app.core.errores import ErrorDeDominio
    from app.services.ai_provider_service.gestion import proveedor_sin_guardar
    with pytest.raises(ErrorDeDominio):
        proveedor_sin_guardar({"provider": "openai", "api_key": "k", "api_base_url": "http://169.254.169.254/v1"})
    # El de plataforma (Ollama local por defecto) sigue valiendo.
    from app.core.config import settings
    assert proveedor_sin_guardar({"provider": "ollama", "api_base_url": settings.OLLAMA_BASE_URL})


# ── Límite global del cuerpo ──────────────────────────────────────────────────

def _app_con_limite(monkeypatch, mb=1):
    from starlette.applications import Starlette
    from starlette.requests import Request
    from starlette.responses import JSONResponse
    from starlette.routing import Route

    from app.core.config import settings
    from app.core.limite_de_cuerpo import LimiteDeCuerpoMiddleware
    monkeypatch.setattr(settings, "MAX_REQUEST_BODY_MB", mb)

    async def eco(request: Request):
        return JSONResponse({"n": len(await request.body())})
    app = Starlette(routes=[Route("/", eco, methods=["POST"])])
    app.add_middleware(LimiteDeCuerpoMiddleware)
    return app


def test_el_cuerpo_grande_da_413_por_cabecera_y_por_bytes(monkeypatch):
    from starlette.testclient import TestClient
    cliente = TestClient(_app_con_limite(monkeypatch))
    assert cliente.post("/", content=b"x" * 1000).json() == {"n": 1000}
    r = cliente.post("/", content=b"x" * (1024 * 1024 + 1))
    assert r.status_code == 413 and r.json()["code"] == "cuerpo_demasiado_grande"

    def trozos():  # sin Content-Length (chunked)
        for _ in range(3):
            yield b"x" * (512 * 1024)
    assert cliente.post("/", content=trozos()).status_code == 413


# ── Secretos ──────────────────────────────────────────────────────────────────

def test_la_rotacion_cubre_las_columnas_cifradas():
    from app.services.key_management import _secretos_a_recifrar
    cubiertas = {(s.modelo.__name__, c) for s in _secretos_a_recifrar() for c in s.campos}
    for esperado in [("IntegrationCredential", "value_encrypted"), ("JiraConfig", "jira_api_token_enc"),
                     ("SoftwareConfig", "nvd_api_key"), ("SoftwareConfig", "ghsa_token"),
                     ("SlackConfig", "bot_token"), ("CollaborationIntegration", "access_token_enc"),
                     ("IntegrationInstance", "encrypted_config"), ("CMDBDiscoveryProvider", "config_json"),
                     ("User", "mfa_secret"), ("WebhookTrigger", "secret"), ("IntegrationConfig", "config")]:
        assert esperado in cubiertas, esperado


def test_la_rotacion_recifra_lo_anidado_y_deja_lo_que_no_es_secreto():
    from app.core.encryption import decrypt_value, encrypt_value
    from app.services.key_management import _recifrar_segun_modo
    cifrado = encrypt_value("xoxb-1")
    fila = SimpleNamespace(id="1", cfg=json.dumps({"token": cifrado, "url": "https://x", "n": [cifrado]}),
                           plano="no-cifrado", tok=cifrado)
    assert _recifrar_segun_modo(fila, "cfg", "M", "json")
    datos = json.loads(fila.cfg)
    assert datos["token"] != cifrado and decrypt_value(datos["token"]) == "xoxb-1" and datos["url"] == "https://x"
    assert not _recifrar_segun_modo(fila, "plano", "M", "prefijo") and fila.plano == "no-cifrado"
    assert _recifrar_segun_modo(fila, "tok", "M", "prefijo") and decrypt_value(fila.tok) == "xoxb-1"


def test_el_bot_token_de_slack_se_guarda_cifrado(db):
    from app.models.mfa import SlackConfig
    from app.services.slack_service import create_or_update_slack_config
    r = create_or_update_slack_config({"platform": "slack", "bot_token": "xoxb-secreto"}, db, organization_id="1")
    fila = db.query(SlackConfig).filter(SlackConfig.id == r["id"]).one()
    assert fila.bot_token.startswith(("v2:", "kmsv1:"))
    # Sin `bot_token` en el formulario se conserva.
    create_or_update_slack_config({"platform": "slack", "workspace_name": "w"}, db, organization_id="1")
    db.refresh(fila)
    assert fila.bot_token.startswith(("v2:", "kmsv1:"))


def test_la_comunidad_snmp_no_se_guarda_en_el_ci():
    texto = (APP / "services/cmdb/discovery.py").read_text(encoding="utf-8")
    assert '"community": community' not in texto


def test_discovery_sin_credenciales_propias_no_usa_las_del_servidor(monkeypatch):
    from app.core.codigos_de_error import ErrorConCodigo
    from app.core.config import settings
    from app.services.cmdb import discovery
    monkeypatch.setattr(settings, "CMDB_DISCOVERY_ALLOW_PLATFORM_CREDENTIALS", False)
    with pytest.raises(ErrorConCodigo):
        discovery._exigir_credenciales_explicitas("AWS", "aws_access_key_id")


# ── Redis y Celery ────────────────────────────────────────────────────────────

def test_la_contrasena_de_redis_entra_en_la_url():
    from app.core.redis_url import con_contrasena
    assert con_contrasena("redis://127.0.0.1:6381/0", "a@b") == "redis://:a%40b@127.0.0.1:6381/0"
    assert con_contrasena("redis://:x@h:1/0", "y") == "redis://:x@h:1/0"


def test_compose_redis_noeviction_y_contrasena():
    compose = (RAIZ / "docker-compose.yml").read_text(encoding="utf-8")
    assert '"allkeys-lru"' not in compose and "--maxmemory-policy noeviction" in compose
    assert "--requirepass" in compose


def test_el_worker_solo_ejecuta_la_lista_blanca():
    from app.core import segundo_plano as sp
    for ruta in sp.FUNCIONES_ENCOLABLES:
        assert callable(sp.resolver(ruta))
    for ajena in ("app.db.rls:main", "app.services.reset_to_admin_only:main", "os:system"):
        with pytest.raises(ValueError):
            sp._ejecutar_con_contexto(ajena, None, [], {})


# ── Exportaciones ─────────────────────────────────────────────────────────────

def test_las_exportaciones_neutralizan_formulas():
    from app.core.celdas_seguras import neutralizar_formula
    from app.services.exportador_tabular import _csv, _xlsx
    assert neutralizar_formula('=HYPERLINK("http://x")') == '\'=HYPERLINK("http://x")'
    assert neutralizar_formula(-5) == -5 and neutralizar_formula("Juan") == "Juan"
    assert b"'=1+1" in _csv(["a"], [["=1+1"]])
    from io import BytesIO

    from openpyxl import load_workbook
    hoja = load_workbook(BytesIO(_xlsx(["a"], [["@SUM(A1)"], [3]], "t"))).active
    assert hoja["A2"].value == "'@SUM(A1)" and hoja["A2"].data_type == "s" and hoja["A3"].value == 3


# ── Copia antes de migrar ─────────────────────────────────────────────────────

def test_la_copia_previa_detecta_las_destructivas_y_copia_sqlite(tmp_path):
    sys.path.insert(0, str(RAIZ / "scripts"))
    import copia_antes_de_migrar as c
    from alembic.config import Config
    from alembic.script import ScriptDirectory
    cfg = Config(str(RAIZ / "alembic.ini"))
    cfg.set_main_option("script_location", str(RAIZ / "alembic"))
    destructivas = c.destructivas(list(ScriptDirectory.from_config(cfg).walk_revisions()))
    assert any(r.startswith("135") for r in destructivas)

    base = tmp_path / "b.db"
    con = sqlite3.connect(base)
    con.execute("create table t (x)")
    con.execute("insert into t values (1)")
    con.commit()
    con.close()
    from sqlalchemy.engine import make_url
    copia = c._copia_sqlite(make_url(f"sqlite:///{base}"), str(tmp_path / "copias"), "rev")
    assert sqlite3.connect(copia).execute("select x from t").fetchone() == (1,)
