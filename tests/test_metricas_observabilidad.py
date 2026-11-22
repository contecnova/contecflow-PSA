"""Observabilidad por empresa (22-11-2026, docs/OBSERVABILIDAD.md).

Cubre:
* la etiqueta `empresa` (slug acotado, tope `METRICS_TENANT_MAX`, `otras`,
  `sin_empresa`);
* el colector de negocio contra una base de prueba (recuentos por empresa, y que
  un bloque roto no tumba a los demás);
* que lo que sale por /metrics no lleva datos personales (ids, correos, nombres,
  IPs de usuarios) ni URLs reales, solo rutas-plantilla;
* la configuración estática de la pila (compose, reglas, Grafana) y los
  ayudantes de `scripts/docker_stack.py`.
"""
from __future__ import annotations

import json
import pathlib
import uuid
from datetime import datetime, timedelta, timezone

import pytest
from fastapi import Request  # a nivel de módulo: con `annotations` FastAPI resuelve la anotación aquí
from prometheus_client import CollectorRegistry, generate_latest

from app.core import metricas_empresa as me
from app.core.metricas_negocio import ColectorDeNegocio

REPO = pathlib.Path(__file__).resolve().parents[1]


@pytest.fixture
def metricas_activas(monkeypatch):
    from app.core.config import settings
    monkeypatch.setattr(settings, "METRICS_ENABLED", True)
    monkeypatch.setattr(settings, "METRICS_TENANT_MAX", 50)
    monkeypatch.setattr(settings, "METRICS_TENANT_LABEL", "slug")
    me.invalidar_cache()
    yield settings
    me.invalidar_cache()


def _org(db, slug, minutos_antes=0):
    from app.models.mfa import Organization
    org = Organization(id=str(uuid.uuid4()), name=f"Empresa {slug}", slug=slug, is_active=True,
                       created_at=datetime.now(timezone.utc) - timedelta(minutes=minutos_antes))
    db.add(org)
    db.commit()
    return org


def _render(colector) -> str:
    registro = CollectorRegistry()
    registro.register(colector)
    return generate_latest(registro).decode("utf-8")


def _colector(db):
    from tests.conftest import TestSession
    return ColectorDeNegocio(ttl=0, sesion=TestSession)


def _muestra(salida: str, nombre: str, valor=None, **etiquetas) -> bool:
    """¿Hay una muestra `nombre` con esas etiquetas (y ese valor)? Sin depender del
    orden de las etiquetas: prometheus_client las escribe ordenadas por nombre."""
    from prometheus_client.parser import text_string_to_metric_families
    for familia in text_string_to_metric_families(salida):
        for m in familia.samples:
            if m.name == nombre and m.labels == etiquetas and (valor is None or m.value == valor):
                return True
    return False


# ── Etiqueta de empresa ──────────────────────────────────────────────────────

def test_etiqueta_es_el_slug_y_se_acota_con_el_tope(db, metricas_activas, monkeypatch):
    vieja = _org(db, "Alfa S.L.", minutos_antes=600)
    nueva = _org(db, "beta", minutos_antes=1)
    monkeypatch.setattr(metricas_activas, "METRICS_TENANT_MAX", 1)  # solo la más antigua
    me.invalidar_cache()
    assert me.etiqueta_de_empresa(vieja.id, db) == "alfa-s-l"
    assert me.etiqueta_de_empresa(nueva.id, db) == me.OTRAS
    assert me.etiqueta_de_empresa(None, db) == me.SIN_EMPRESA


def test_etiqueta_por_id_si_se_pide(db, metricas_activas, monkeypatch):
    org = _org(db, "gamma")
    monkeypatch.setattr(metricas_activas, "METRICS_TENANT_LABEL", "id")
    me.invalidar_cache()
    assert me.etiqueta_de_empresa(org.id, db) == org.id


def test_sin_metricas_no_toca_la_base(db, monkeypatch):
    from app.core.config import settings
    monkeypatch.setattr(settings, "METRICS_ENABLED", False)
    me.invalidar_cache()
    assert me.etiqueta_de_empresa("lo-que-sea", db) == me.OTRAS
    assert me._cache["mapa"] == {}


# ── Colector de negocio ──────────────────────────────────────────────────────

def test_colector_cuenta_tickets_y_proyectos_por_empresa(db, metricas_activas):
    from app.models.project import Project, ProjectStatus
    from app.models.service_desk._enums import SLAStatus, TicketPriority, TicketStatus, TicketType
    from app.models.service_desk.tickets import Ticket

    org = _org(db, "delta")
    for i, (estado, prio, sla) in enumerate((
            (TicketStatus.new, TicketPriority.p1_critical, SLAStatus.breached),
            (TicketStatus.in_progress, TicketPriority.p1_critical, SLAStatus.at_risk),
            (TicketStatus.closed, TicketPriority.p3_medium, SLAStatus.ok))):
        db.add(Ticket(id=str(uuid.uuid4()), organization_id=org.id, number=f"T-{i}", ticket_type=TicketType.incident,
                      title="x", description="x", status=estado, priority=prio, sla_resolution_status=sla))
    db.add(Project(id=str(uuid.uuid4()), organization_id=org.id, code="P-1", name="Proyecto",
                   project_type="internal", status=ProjectStatus.active, is_active=True))
    db.commit()

    salida = _render(_colector(db))
    assert _muestra(salida, "contecflow_negocio_tickets_abiertos", 2.0, empresa="delta", prioridad="p1_critical")
    assert _muestra(salida, "contecflow_negocio_sla", 1.0, empresa="delta", ambito="tickets", estado="incumplido")
    assert _muestra(salida, "contecflow_negocio_sla", 1.0, empresa="delta", ambito="tickets", estado="en_riesgo")
    assert _muestra(salida, "contecflow_negocio_proyectos", 1.0, empresa="delta", estado="active")
    assert 'bloque="tickets"' not in salida
    assert 'bloque="proyectos"' not in salida


def test_un_bloque_roto_no_tumba_los_demas(db, metricas_activas):
    def roto(_c):
        raise RuntimeError("tabla que no existe")

    from app.core.metricas_negocio import BLOQUES
    colector = ColectorDeNegocio(bloques=[("roto", roto)] + [b for b in BLOQUES if b[0] == "proyectos"],
                                 ttl=0, sesion=__import__("tests.conftest", fromlist=["TestSession"]).TestSession)
    salida = _render(colector)
    assert _muestra(salida, "contecflow_negocio_colector_errores_total", 1.0, bloque="roto")
    assert "contecflow_negocio_proyectos" in salida


def test_el_colector_cachea(db, metricas_activas):
    llamadas = []

    def bloque(_c):
        llamadas.append(1)
        return []

    from tests.conftest import TestSession
    colector = ColectorDeNegocio(bloques=[("b", bloque)], ttl=3600, sesion=TestSession)
    _render(colector)
    list(colector.collect())
    list(colector.collect())
    assert len(llamadas) == 1


# ── Sin datos personales ─────────────────────────────────────────────────────

def test_metrics_no_expone_datos_personales(db, metricas_activas):
    from app.models.ai_providers import AIUsageLog
    from app.models.sessions import UserSession
    from app.models.user import User

    org = _org(db, "epsilon")
    usuario = db.query(User).filter(User.id == "admin-test-id").first()
    usuario.organization_id = org.id
    usuario.last_login = datetime.now(timezone.utc)
    db.add(AIUsageLog(id=str(uuid.uuid4()), organization_id=org.id, user_id=usuario.id, module="nexusagent",
                      tokens_in=10, tokens_out=5, cost_usd=0.01, success=True))
    db.add(UserSession(id=str(uuid.uuid4()), organization_id=org.id, user_id=usuario.id,
                       refresh_token_jti=str(uuid.uuid4()), ip_address="203.0.113.77",
                       expires_at=datetime.now(timezone.utc) + timedelta(days=1)))
    db.commit()

    # Los contadores en caliente resuelven la etiqueta sin sesión (SessionLocal, que en
    # pruebas no es la base de prueba): el mapa se carga antes desde la de prueba.
    me.mapa_de_empresas(db, forzar=True)
    me.contar_login("fallido", org.id)
    me.contar_uso_de_ia(org.id, "nexusagent", ok=True, tokens_in=10, tokens_out=5, coste_usd=0.01)
    salida = _render(_colector(db)) + generate_latest().decode("utf-8")

    assert 'empresa="epsilon"' in salida
    # (El `username` del admin de pruebas es «admin», que aparece en rutas como
    # /api/v1/admin/...: no sirve como testigo.)
    for dato in (usuario.id, usuario.email, usuario.full_name, "203.0.113.77", org.name):
        assert dato and dato not in salida, f"dato personal o identificativo en /metrics: {dato!r}"


def test_el_middleware_usa_la_ruta_plantilla_y_el_codigo_del_catalogo(metricas_activas):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from prometheus_client import REGISTRY

    app = FastAPI()
    app.add_middleware(me.MetricasPorEmpresaMiddleware)

    @app.get("/pruebas-metricas/{usuario_id}")
    def _ruta(usuario_id: str, request: Request):
        request.state.empresa_metricas = "zeta"
        me.anotar_codigo_de_error(request, "ticket_no_encontrado")
        from fastapi.responses import JSONResponse
        return JSONResponse({"detail": "x"}, status_code=404)

    TestClient(app).get("/pruebas-metricas/persona-secreta@example.com")
    salida = generate_latest(REGISTRY).decode("utf-8")
    assert "persona-secreta" not in salida
    assert _muestra(salida, "contecflow_http_errores_total", empresa="zeta", ruta="/pruebas-metricas/{usuario_id}",
                    estado="404", codigo="ticket_no_encontrado")


def test_codigo_de_error_con_texto_libre_se_descarta():
    class _Estado:
        pass

    class _Peticion:
        state = _Estado()

    p = _Peticion()
    me.anotar_codigo_de_error(p, "Usuario juan@example.com no existe")
    assert not hasattr(p.state, "codigo_error")


# ── Pila de observabilidad (estática) ────────────────────────────────────────

def test_grafana_sin_anonimo_y_dashboards_provisionados():
    import yaml
    compose = yaml.safe_load((REPO / "docker-compose.yml").read_text(encoding="utf-8"))
    grafana = compose["services"]["grafana"]
    assert grafana["environment"]["GF_AUTH_ANONYMOUS_ENABLED"] == "false"
    assert grafana["environment"]["GF_USERS_ALLOW_SIGN_UP"] == "false"
    assert all(str(p).startswith("${GRAFANA_PORT:-127.0.0.1:") for p in grafana["ports"])
    for nombre in ("prometheus", "alertmanager", "grafana"):
        assert "observability" in compose["services"][nombre]["profiles"]
    # Los volúmenes reales siguen siendo externos: `down -v` no los borra.
    assert compose["volumes"]["postgres_data"]["external"] is True
    assert compose["volumes"]["s3_data"]["external"] is True

    uid = yaml.safe_load((REPO / "ops/grafana/provisioning/datasources/prometheus.yml").read_text(
        encoding="utf-8"))["datasources"][0]["uid"]
    tableros = list((REPO / "ops/grafana/dashboards").glob("*.json"))
    assert len(tableros) >= 6
    for fichero in tableros:
        tablero = json.loads(fichero.read_text(encoding="utf-8"))
        for panel in tablero["panels"]:
            if panel.get("type") != "row":
                assert panel["datasource"]["uid"] == uid, fichero.name


def test_reglas_de_alerta_cargan_y_cubren_lo_pedido():
    import yaml
    nombres = set()
    for fichero in (REPO / "ops/prometheus/rules").glob("*.yml"):
        for grupo in yaml.safe_load(fichero.read_text(encoding="utf-8"))["groups"]:
            for regla in grupo["rules"]:
                assert regla["labels"]["severity"] in ("critical", "warning", "info")
                nombres.add(regla["alert"])
    for esperada in ("ApiCaida", "TasaDeErrores5xxAlta", "LatenciaP95Alta", "ColaDeCeleryAtascada",
                     "CeleryWorkerCaido", "CeleryBeatCaido", "PostgresCaido", "RedisCaido",
                     "PostgresConexionesAlLimite", "RedisMemoriaAlLimite", "DiscoCasiLleno", "MemoriaCasiAgotada",
                     "IaErroresAltos", "IaPresupuestoAgotado", "SlaIncumplidoNuevo", "SlaEnRiesgo"):
        assert esperada in nombres, esperada


def test_prometheus_no_lleva_el_token_escrito():
    texto = (REPO / "ops/prometheus/prometheus.yml").read_text(encoding="utf-8")
    assert "credentials_file: /run/contecflow/metrics_token" in texto
    assert "credentials:" not in texto.replace("credentials_file", "")


# ── scripts/docker_stack.py ──────────────────────────────────────────────────

def test_docker_stack_env_conserva_lo_existente(tmp_path):
    import importlib.util
    spec = importlib.util.spec_from_file_location("docker_stack", REPO / "scripts/docker_stack.py")
    ds = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(ds)

    ruta = tmp_path / ".env"
    ruta.write_bytes(b"A=1\r\nGRAFANA_ADMIN_PASSWORD=CHANGE_ME\r\n")
    env = ds.Env(ruta)
    assert env.leer("A") == "1"
    assert env.leer("GRAFANA_ADMIN_PASSWORD") == ""   # marcador = sin valor
    env.poner("B", "2")
    env.poner("A", "3")
    assert ruta.read_bytes() == b"A=3\r\nGRAFANA_ADMIN_PASSWORD=CHANGE_ME\r\nB=2\r\n"
    assert ds._puerto("127.0.0.1:8080", "x") == ("localhost", "8080")
    assert ds._puerto("", "127.0.0.1:3001") == ("localhost", "3001")
    assert ds._puerto("0.0.0.0:9090", "x") == ("localhost", "9090")
