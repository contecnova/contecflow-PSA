"""«Del ticket al PR» (migración 203, docs/integraciones/TICKET_A_PR.md).

Con el motor simulado (`MotorSimulado`) y el cliente Git simulado
(`ClienteGitSimulado`): sin Docker, sin credenciales Git y sin modelo reales.
Lo crítico:

- módulo apagado por defecto (y sin Docker no se ejecuta nada);
- permisos (capacidades literales `ticket_pr.*`) y credenciales delegadas vetadas;
- plan → aprobación humana → build → PR → cambio → CAB → estado del PR, sin
  fusionar nunca;
- bloqueo por ficheros protegidos, secretos (también la clave del modelo),
  enlaces simbólicos y tests que fallan;
- límites por empresa y día (ejecuciones y coste);
- aislamiento por empresa y visibilidad del origen;
- datos personales ocultos en la instrucción;
- auditoría y coste de IA imputado;
- piezas puras: globs, detector de secretos, órdenes de Docker, configuración de OpenCode.
"""
from __future__ import annotations

import json

import pytest

from app.models.ai_providers import AIUsageLog
from app.models.enterprise import AuditLog
from app.models.ticket_a_pr import TicketPrRun
from tests.conftest import auth

BASE = "/api/v1/ticket-pr"
CLAVE_DEL_MODELO = "sk-ant-clave-del-modelo-de-pruebas-123456"


# ── Preparación ──────────────────────────────────────────────────────────────

@pytest.fixture()
def motor():
    from app.services.ticket_a_pr import motor as _motor
    m = _motor.MotorSimulado()
    _motor.forzar_motor(m)
    yield m
    _motor.forzar_motor(None)


@pytest.fixture()
def git():
    from app.services.ticket_a_pr import git_clientes
    g = git_clientes.ClienteGitSimulado()
    git_clientes.forzar_cliente(g)
    yield g
    git_clientes.forzar_cliente(None)


@pytest.fixture()
def cab(db):
    """Cola del CAB: pm y dev (el solicitante no vota el suyo)."""
    from app.models.service_desk import AgentGroup, AgentGroupMember, SupportLevel
    from app.models.settings import AppSetting
    from app.services.settings_service import invalidate_cache
    g = AgentGroup(id="cola-cab-tpr", name="CAB", support_level=SupportLevel.l3, organization_id="1")
    db.add(g)
    db.flush()
    db.add_all([AgentGroupMember(group_id=g.id, user_id="pm-test-id", is_lead=True, organization_id="1"),
                AgentGroupMember(group_id=g.id, user_id="dev-test-id", organization_id="1")])
    db.add(AppSetting(key="SD_CAB_GROUP_ID", value=g.id, organization_id="1"))
    db.commit()
    invalidate_cache("SD_CAB_GROUP_ID")
    yield g
    invalidate_cache("SD_CAB_GROUP_ID")


def _proveedor_de_ia(db, org="1"):
    from app.core.encryption import encrypt_value
    from app.models.ai_providers import AIProvider
    p = AIProvider(name="Claude pruebas", provider="anthropic", api_key=encrypt_value(CLAVE_DEL_MODELO),
                   default_model="claude-sonnet-4-5", is_default=True, organization_id=org)
    db.add(p)
    db.commit()
    return p


def _proyecto(db, org="1", codigo="TPR"):
    from app.models.project import Project, ProjectStatus
    p = Project(code=codigo, name=f"Proyecto {codigo}", status=ProjectStatus.active, project_type="development",
                organization_id=org)
    db.add(p)
    db.commit()
    return p


def _ticket(db, proyecto_id, org="1", descripcion="La app falla al guardar. Escribidme a ana.garcia@example.com o al 612345678."):
    from app.models.service_desk import Ticket, TicketType
    t = Ticket(number=f"INC-{abs(hash((proyecto_id, org))) % 10000:04d}", ticket_type=TicketType.incident,
               title="Error al guardar", description=descripcion, project_id=proyecto_id, organization_id=org)
    db.add(t)
    db.commit()
    return t


def _encender(client, admin_token, **config):
    datos = {"enabled": True, "engine_version": "1.2.3", **config}
    r = client.patch(f"{BASE}/config", headers=auth(admin_token), json=datos)
    assert r.status_code == 200, r.text
    from app.services import settings_service
    settings_service.invalidate_cache()
    return r.json()["data"]


def _repo(client, admin_token, proyecto_id, **extra):
    r = client.post(f"{BASE}/repos", headers=auth(admin_token),
                    json={"project_id": proyecto_id, "provider": "github", "repo_full_name": "acme/app",
                          "default_branch": "main", **extra})
    assert r.status_code == 200, r.text
    return r.json()["data"]


def _preparado(client, db, admin_token, **config):
    _proveedor_de_ia(db)
    p = _proyecto(db)
    t = _ticket(db, p.id)
    _encender(client, admin_token, **config)
    repo = _repo(client, admin_token, p.id)
    return p, t, repo


def _lanzar(client, token, ticket_id, repo_id, **extra):
    return client.post(f"{BASE}/origen/ticket/{ticket_id}/ejecuciones", headers=auth(token),
                       json={"repo_id": repo_id, "base_branch": "main", **extra})


def _acciones(db) -> list[str]:
    return [a.action for a in db.query(AuditLog).filter(AuditLog.resource == "ticket_pr_run").order_by(AuditLog.created_at).all()]


# ── Módulo apagado y Docker ──────────────────────────────────────────────────

def test_apagado_por_defecto_no_ofrece_ni_lanza(client, db, admin_token, motor, git):
    _proveedor_de_ia(db)
    p = _proyecto(db)
    t = _ticket(db, p.id)
    r = client.get(f"{BASE}/origen/ticket/{t.id}", headers=auth(admin_token))
    assert r.status_code == 200
    panel = r.json()["data"]
    assert panel["enabled"] is False and panel["can_launch"] is False and panel["reason"] == "ticket_pr_apagado"
    r = _lanzar(client, admin_token, t.id, "cualquiera")
    assert r.status_code == 409 and r.json()["code"] == "ticket_pr_apagado"
    assert db.query(TicketPrRun).count() == 0


def test_sin_docker_no_se_ejecuta_nada(client, db, admin_token, git, monkeypatch):
    from app.services.ticket_a_pr import motor as _motor
    from app.services.ticket_a_pr import sandbox
    _motor.forzar_motor(None)
    monkeypatch.setattr(sandbox, "disponible", lambda: (False, None))
    _, t, repo = _preparado(client, db, admin_token)
    r = _lanzar(client, admin_token, t.id, repo["id"])
    assert r.status_code == 409 and r.json()["code"] == "ticket_pr_docker_no_disponible"
    assert db.query(TicketPrRun).count() == 0
    # Y el sandbox se niega a ejecutar aunque lo llame otro camino.
    with pytest.raises(sandbox.DockerNoDisponible):
        sandbox.ejecutar(sandbox.Pedido(imagen="x:1", argumentos=[], espacio=b"", limites=sandbox.Limites()))


def test_version_del_motor_fijada(client, db, admin_token, motor, git):
    r = client.patch(f"{BASE}/config", headers=auth(admin_token), json={"engine_version": "latest"})
    assert r.status_code == 422 and r.json()["code"] == "ticket_pr_version_sin_fijar"
    _, t, repo = _preparado(client, db, admin_token, engine_version="")
    r = _lanzar(client, admin_token, t.id, repo["id"])
    assert r.status_code == 409 and r.json()["code"] == "ticket_pr_version_sin_fijar"


# ── Permisos ─────────────────────────────────────────────────────────────────

def test_capacidades(client, db, admin_token, pm_token, dev_token, sub_token, motor, git):
    _, t, repo = _preparado(client, db, admin_token)
    # Configurar: solo dirección.
    assert client.get(f"{BASE}/config", headers=auth(pm_token)).status_code == 403
    assert client.post(f"{BASE}/repos", headers=auth(pm_token), json={}).status_code in (403, 422)
    # Ver: internos; el externo no.
    assert client.get(f"{BASE}/estado", headers=auth(dev_token)).status_code == 200
    assert client.get(f"{BASE}/estado", headers=auth(sub_token)).status_code == 403
    # Lanzar: admin, pm, jefe de equipo; el empleado no.
    assert _lanzar(client, dev_token, t.id, repo["id"]).status_code == 403
    # Un empleado solo ve los tickets que pidió o tiene asignados (si no, 404):
    # se le asigna para que el panel diga POR QUÉ no puede lanzar.
    t.assigned_to_user_id = "dev-test-id"
    db.commit()
    panel = client.get(f"{BASE}/origen/ticket/{t.id}", headers=auth(dev_token)).json()["data"]
    assert panel["can_launch"] is False and panel["reason"] == "ticket_pr_sin_capacidad"
    assert _lanzar(client, pm_token, t.id, repo["id"]).status_code == 200
    run_id = db.query(TicketPrRun).first().id
    # Aprobar el plan: el empleado no.
    r = client.post(f"{BASE}/ejecuciones/{run_id}/plan", headers=auth(dev_token), json={"approve": True})
    assert r.status_code == 403


def test_una_credencial_delegada_no_abre_el_modulo():
    from app.core.credenciales_delegadas import comprobar_alcance
    for ruta in ("/api/v1/ticket-pr/estado", "/api/v1/ticket-pr/config", "/api/v1/ticket-pr/origen/ticket/x/ejecuciones"):
        with pytest.raises(Exception):
            comprobar_alcance("POST", ruta, ["admin"])


# ── Flujo completo ───────────────────────────────────────────────────────────

def test_plan_aprobacion_build_pr_cambio_y_cab(client, db, admin_token, pm_token, dev_token, motor, git, cab):
    _, t, repo = _preparado(client, db, admin_token)
    r = _lanzar(client, pm_token, t.id, repo["id"])
    assert r.status_code == 200, r.text
    run = r.json()["data"]
    # PLAN (en línea en los tests): solo lectura, plan guardado, esperando aprobación.
    assert run["status"] == "awaiting_approval", run
    assert run["plan_text"] and run["plan_files"] == ["app.py"]
    assert motor.llamadas[0]["fase"] == "plan" and motor.llamadas[0]["imagen"].endswith(":1.2.3")
    assert git.prs == [] and git.publicados == []

    r = client.post(f"{BASE}/ejecuciones/{run['id']}/plan", headers=auth(admin_token), json={"approve": True, "note": "adelante"})
    assert r.status_code == 200, r.text
    run = client.get(f"{BASE}/ejecuciones/{run['id']}", headers=auth(pm_token)).json()["data"]
    # BUILD: rama nueva contecflow/<ticket>-<id>, PR abierto y estado del CAB pendiente.
    assert run["status"] == "awaiting_cab", run
    assert git.publicados[0]["rama"].startswith("contecflow/inc-") and git.publicados[0]["cambios"] == [("app.py", "update")]
    assert git.prs and git.prs[0]["base"] == "main" and "contecflow nunca fusiona" in git.prs[0]["cuerpo"]
    assert "ana.garcia@example.com" not in git.prs[0]["cuerpo"]
    assert git.estados[0]["estado"] == "pending"
    # Cambio vinculado: lo pide quien lanzó, enlazado al ticket, en el CAB.
    from app.models.service_desk import ITSMChangeRequest
    cambio = db.get(ITSMChangeRequest, run["change"]["id"])
    assert cambio.requester_id == "pm-test-id" and cambio.related_ticket_id == t.id
    assert getattr(cambio.status, "value", cambio.status) == "cab_review"
    assert run["pr_url"] in cambio.description
    # El CAB (dev; pm es el solicitante y no vota) aprueba → el PR pasa a éxito. Nadie fusiona.
    # Vota por la ruta del miembro del CAB: `/changes/{id}/approve` es la decisión
    # del administrador por encima del comité (exige `sd.administrar`).
    r = client.post(f"/api/v1/sd/changes/{cambio.id}/cab/vote", headers=auth(dev_token), json={"approve": True})
    assert r.status_code == 200, r.text
    r = client.post(f"{BASE}/ejecuciones/{run['id']}/sincronizar", headers=auth(pm_token))
    assert r.status_code == 200 and r.json()["data"]["status"] == "cab_approved"
    assert git.estados[-1]["estado"] == "success"
    assert not hasattr(git, "fusionar") and git.estado == "open"
    # Trazabilidad: auditoría, coste imputado y horas del agente.
    acciones = _acciones(db)
    for a in ("TICKET_PR_LAUNCH", "TICKET_PR_PLAN_APPROVE", "TICKET_PR_PR_OPENED", "TICKET_PR_CHANGE_LINKED", "TICKET_PR_CAB_SYNC"):
        assert a in acciones, acciones
    fila = db.get(TicketPrRun, run["id"])
    assert float(fila.cost_usd) == pytest.approx(0.02) and fila.agent_seconds >= 150
    assert db.query(AIUsageLog).filter(AIUsageLog.module == "ticket_pr").count() == 2
    assert r.json()["data"]["agent_hours"] > 0


def test_el_cab_rechaza_y_el_pr_queda_bloqueado(client, db, admin_token, pm_token, dev_token, motor, git, cab):
    _, t, repo = _preparado(client, db, admin_token)
    run = _lanzar(client, pm_token, t.id, repo["id"]).json()["data"]
    client.post(f"{BASE}/ejecuciones/{run['id']}/plan", headers=auth(admin_token), json={"approve": True})
    run = client.get(f"{BASE}/ejecuciones/{run['id']}", headers=auth(pm_token)).json()["data"]
    r = client.post(f"/api/v1/sd/changes/{run['change']['id']}/cab/vote", headers=auth(dev_token),
                    json={"approve": False, "note": "Sin plan de vuelta atrás"})  # votar en contra pide motivo
    assert r.status_code == 200, r.text
    r = client.post(f"{BASE}/ejecuciones/{run['id']}/sincronizar", headers=auth(pm_token))
    assert r.json()["data"]["status"] == "cab_rejected"
    assert git.estados[-1]["estado"] == "failure"


def test_sin_cab_el_pr_queda_pendiente(client, db, admin_token, pm_token, motor, git):
    _, t, repo = _preparado(client, db, admin_token)
    run = _lanzar(client, pm_token, t.id, repo["id"]).json()["data"]
    client.post(f"{BASE}/ejecuciones/{run['id']}/plan", headers=auth(admin_token), json={"approve": True})
    run = client.get(f"{BASE}/ejecuciones/{run['id']}", headers=auth(pm_token)).json()["data"]
    assert run["status"] == "awaiting_cab" and run["pr_status_state"] == "pending"
    assert run["status_code"] == "cab_no_configurado"
    assert all(e["estado"] == "pending" for e in git.estados)


def test_plan_rechazado_no_construye(client, db, admin_token, pm_token, motor, git):
    _, t, repo = _preparado(client, db, admin_token)
    run = _lanzar(client, pm_token, t.id, repo["id"]).json()["data"]
    r = client.post(f"{BASE}/ejecuciones/{run['id']}/plan", headers=auth(admin_token), json={"approve": False, "note": "no"})
    assert r.status_code == 200 and r.json()["data"]["status"] == "rejected"
    assert [x["fase"] for x in motor.llamadas] == ["plan"] and git.publicados == []
    assert "TICKET_PR_PLAN_REJECT" in _acciones(db)
    # Ya decidido: no se puede volver a decidir.
    r = client.post(f"{BASE}/ejecuciones/{run['id']}/plan", headers=auth(admin_token), json={"approve": True})
    assert r.status_code == 409 and r.json()["code"] == "ticket_pr_estado_no_valido"


def test_plan_por_otra_persona_si_la_empresa_lo_exige(client, db, admin_token, motor, git):
    _, t, repo = _preparado(client, db, admin_token, plan_requires_other_person=True)
    run = _lanzar(client, admin_token, t.id, repo["id"]).json()["data"]
    r = client.post(f"{BASE}/ejecuciones/{run['id']}/plan", headers=auth(admin_token), json={"approve": True})
    assert r.status_code == 403 and r.json()["code"] == "ticket_pr_plan_propio"


def test_cancelar_queda_auditado(client, db, admin_token, pm_token, motor, git):
    _, t, repo = _preparado(client, db, admin_token)
    run = _lanzar(client, pm_token, t.id, repo["id"]).json()["data"]
    r = client.post(f"{BASE}/ejecuciones/{run['id']}/cancelar", headers=auth(pm_token))
    assert r.status_code == 200 and r.json()["data"]["status"] == "cancelled"
    assert "TICKET_PR_CANCEL" in _acciones(db)
    assert client.post(f"{BASE}/ejecuciones/{run['id']}/cancelar", headers=auth(pm_token)).status_code == 409


# ── Bloqueos antes del PR ────────────────────────────────────────────────────

@pytest.mark.parametrize("cambios, codigo", [
    ({".github/workflows/ci.yml": b"on: push\n"}, "ticket_pr_bloqueo_fichero_protegido"),
    ({"config/.env": b"X=1\n"}, "ticket_pr_bloqueo_fichero_protegido"),
    ({"app.py": b'AWS = "AKIAABCDEFGHIJKLMNOP"\n'}, "ticket_pr_bloqueo_secreto"),
    ({"app.py": f"KEY = '{CLAVE_DEL_MODELO}'\n".encode()}, "ticket_pr_bloqueo_secreto"),
    ({"enlace": ("enlace", "/etc/passwd")}, "ticket_pr_bloqueo_fichero_no_admitido"),
    ({"logo.png": b"\x89PNG\x00\x00\x01"}, "ticket_pr_bloqueo_binario"),
    ({}, "ticket_pr_sin_cambios"),
])
def test_bloqueos_antes_de_abrir_el_pr(client, db, admin_token, pm_token, motor, git, cambios, codigo):
    motor.cambios = cambios
    _, t, repo = _preparado(client, db, admin_token)
    run = _lanzar(client, pm_token, t.id, repo["id"]).json()["data"]
    client.post(f"{BASE}/ejecuciones/{run['id']}/plan", headers=auth(admin_token), json={"approve": True})
    run = client.get(f"{BASE}/ejecuciones/{run['id']}", headers=auth(pm_token)).json()["data"]
    assert run["status"] == "blocked" and run["status_code"] == codigo, run
    assert git.publicados == [] and git.prs == []
    assert "TICKET_PR_BLOCKED" in _acciones(db)


def test_ficheros_protegidos_de_la_empresa_y_tests_que_fallan(client, db, admin_token, pm_token, motor, git):
    motor.cambios = {"deploy/prod.yaml": b"replicas: 9\n"}
    _, t, repo = _preparado(client, db, admin_token, protected_paths=["deploy/**"])
    run = _lanzar(client, pm_token, t.id, repo["id"]).json()["data"]
    client.post(f"{BASE}/ejecuciones/{run['id']}/plan", headers=auth(admin_token), json={"approve": True})
    assert db.get(TicketPrRun, run["id"]).status_code == "ticket_pr_bloqueo_fichero_protegido"

    motor.cambios = {"app.py": b"print('ok')\n"}
    motor.tests_ok = False
    client.patch(f"{BASE}/repos/{repo['id']}", headers=auth(admin_token), json={"test_command": "pytest -q"})
    _encender(client, admin_token, run_tests=True)
    run = _lanzar(client, pm_token, t.id, repo["id"]).json()["data"]
    client.post(f"{BASE}/ejecuciones/{run['id']}/plan", headers=auth(admin_token), json={"approve": True})
    fila = db.get(TicketPrRun, run["id"])
    assert fila.status == "blocked" and fila.status_code == "ticket_pr_bloqueo_tests" and fila.tests_ran
    assert {"fase": "tests", "orden": "pytest -q"} in motor.llamadas


def test_los_ignorados_no_cuentan(client, db, admin_token, pm_token, motor, git, cab):
    motor.cambios = {"app.py": b"print('ok')\n", "node_modules/x/index.js": b"x", "__pycache__/a.pyc": b"\x00"}
    _, t, repo = _preparado(client, db, admin_token)
    run = _lanzar(client, pm_token, t.id, repo["id"]).json()["data"]
    client.post(f"{BASE}/ejecuciones/{run['id']}/plan", headers=auth(admin_token), json={"approve": True})
    assert git.publicados[0]["cambios"] == [("app.py", "update")]


# ── Límites ──────────────────────────────────────────────────────────────────

def test_limite_diario_de_ejecuciones(client, db, admin_token, pm_token, motor, git):
    _, t, repo = _preparado(client, db, admin_token, limits={"max_runs_per_day": 1})
    assert _lanzar(client, pm_token, t.id, repo["id"]).status_code == 200
    r = _lanzar(client, pm_token, t.id, repo["id"])
    assert r.status_code == 429 and r.json()["code"] == "ticket_pr_limite_diario"


def test_limite_diario_de_coste(client, db, admin_token, pm_token, motor, git):
    _, t, repo = _preparado(client, db, admin_token, limits={"max_cost_per_day_usd": 0.01})
    motor.coste = 0.05
    assert _lanzar(client, pm_token, t.id, repo["id"]).status_code == 200
    r = _lanzar(client, pm_token, t.id, repo["id"])
    assert r.status_code == 429 and r.json()["code"] == "ticket_pr_limite_de_coste"


# ── Aislamiento y visibilidad ────────────────────────────────────────────────

def test_aislamiento_por_empresa(client, db, admin_token, pm_token, motor, git):
    from app.models.mfa import Organization
    _, t, repo = _preparado(client, db, admin_token)
    run = _lanzar(client, pm_token, t.id, repo["id"]).json()["data"]
    db.add(Organization(id="org-ajena-tpr", name="Ajena", slug="ajena-tpr"))
    db.commit()
    otro = _proyecto(db, org="org-ajena-tpr", codigo="AJN")
    ajeno = _ticket(db, otro.id, org="org-ajena-tpr")
    # Un ticket de otra empresa no existe; tampoco se puede usar un repositorio con él.
    assert client.get(f"{BASE}/origen/ticket/{ajeno.id}", headers=auth(admin_token)).status_code == 404
    assert _lanzar(client, admin_token, ajeno.id, repo["id"]).status_code in (404, 409)
    # Una ejecución de otra empresa tampoco.
    fila = db.get(TicketPrRun, run["id"])
    fila.organization_id = "org-ajena-tpr"
    db.commit()
    assert client.get(f"{BASE}/ejecuciones/{run['id']}", headers=auth(admin_token)).status_code == 404
    assert client.post(f"{BASE}/ejecuciones/{run['id']}/plan", headers=auth(admin_token),
                       json={"approve": True}).status_code == 404


def test_repositorio_de_otro_proyecto_no_vale(client, db, admin_token, motor, git):
    _, t, _repo_bueno = _preparado(client, db, admin_token)
    otro = _proyecto(db, codigo="OTR")
    repo_ajeno = _repo(client, admin_token, otro.id, repo_full_name="acme/otro")
    r = _lanzar(client, admin_token, t.id, repo_ajeno["id"])
    assert r.status_code == 422 and r.json()["code"] == "ticket_pr_repo_no_permitido"


# ── Datos personales ─────────────────────────────────────────────────────────

def test_la_instruccion_oculta_los_datos_personales(client, db, admin_token, pm_token, motor, git):
    _, t, repo = _preparado(client, db, admin_token)
    r = client.post(f"{BASE}/origen/ticket/{t.id}/instruccion", headers=auth(pm_token), json={"repo_id": repo["id"]})
    assert r.status_code == 200
    texto = r.json()["data"]["instruction"]
    assert "ana.garcia@example.com" not in texto and "612345678" not in texto and "Error al guardar" in texto
    # Lo que se escribe a mano también se oculta al lanzar.
    run = _lanzar(client, pm_token, t.id, repo["id"], instruction="Arregla y avisa a pepe@example.com").json()["data"]
    assert "pepe@example.com" not in run["instruction"]
    assert "pepe@example.com" not in motor.llamadas[0]["instruccion"]


# ── Configuración y GRC ──────────────────────────────────────────────────────

def test_config_auditada_y_sin_secretos(client, db, admin_token):
    r = client.patch(f"{BASE}/config", headers=auth(admin_token), json={"enabled": True, "protected_paths": ["infra/**"]})
    assert r.status_code == 200
    datos = r.json()["data"]
    assert datos["enabled"] is True and "infra/**" in datos["config"]["protected_paths"]
    assert all(i["value"] is None for i in datos["credentials"]["items"] if i["is_secret"])
    acciones = {a.action + ":" + a.resource for a in db.query(AuditLog).all()}
    assert "UPDATE:ticket_pr_config" in acciones and "UPDATE:ticket_pr_module" in acciones
    r = client.patch(f"{BASE}/config", headers=auth(admin_token), json={"extra_egress_hosts": ["169.254.169.254"]})
    assert r.status_code in (400, 422)


def test_retencion_y_bloqueo_legal_registrados():
    from app.db.bloqueo_legal import TIPOS
    tipo = TIPOS["ticket_pr_runs"]
    assert tipo.modelo() is TicketPrRun and "launched_by" in tipo.campos and "ticket_id" in tipo.campos


def test_modulo_apagado_sin_fila_en_la_gobernanza():
    from app.services.governance_service import APAGADOS_SIN_CONFIGURAR
    assert "ticket_pr" in APAGADOS_SIN_CONFIGURAR


# ── Piezas puras ─────────────────────────────────────────────────────────────

def test_globs_de_ficheros_protegidos():
    from app.services.ticket_a_pr.config import PROTEGIDOS_DE_FABRICA
    from app.services.ticket_a_pr.diff import casa
    assert casa(".github/workflows/ci.yml", PROTEGIDOS_DE_FABRICA)
    assert casa("sub/dir/.env", PROTEGIDOS_DE_FABRICA) and casa(".env.local", PROTEGIDOS_DE_FABRICA)
    assert casa("certs/server.pem", PROTEGIDOS_DE_FABRICA) and casa(".gitlab-ci.yml", PROTEGIDOS_DE_FABRICA)
    assert casa("src/app.py", PROTEGIDOS_DE_FABRICA) is None and casa("docs/env.md", PROTEGIDOS_DE_FABRICA) is None


def test_detector_de_secretos():
    from app.services.ticket_a_pr.diff import buscar_secreto
    assert buscar_secreto(["-----BEGIN RSA PRIVATE KEY-----"]) == "clave_privada"
    assert buscar_secreto(["token = 'ghp_" + "a" * 36 + "'"]) == "github_token"
    assert buscar_secreto(['password = "supersecreto123"']) == "asignacion_de_secreto"
    assert buscar_secreto(["x = 1"]) is None
    assert buscar_secreto(["valor abc123secreto456"], literales=["abc123secreto456"]) == "literal"


def test_rutas_peligrosas_del_tar():
    from app.services.ticket_a_pr.diff import ruta_segura
    assert ruta_segura("./src/a.py") == "src/a.py"
    assert ruta_segura("../etc/passwd") is None and ruta_segura("/etc/passwd") is None and ruta_segura("a/../../b") is None


def test_ordenes_de_docker_aislan():
    from app.services.ticket_a_pr import sandbox
    nombres = sandbox.nombres_para("abc")
    pedido = sandbox.Pedido(imagen="ghcr.io/anomalyco/opencode:1.2.3", argumentos=["run"], espacio=b"",
                            limites=sandbox.Limites(cpus=1.5, memoria_mb=2048, procesos=256, segundos=600),
                            hosts_permitidos=[("api.anthropic.com", 443)], solo_lectura=True)
    orden = sandbox.orden_del_agente(nombres, pedido, "/tmp/x.env")
    for esperado in ("--read-only", "ALL", "no-new-privileges", "1000:1000", "2048m", "1.5", "256", "--env-file"):
        assert esperado in orden
    montajes = [orden[i + 1] for i, a in enumerate(orden) if a == "-v"]
    assert montajes == [f"{nombres['volumen']}:/workspace:ro"]          # nada del host
    assert "--privileged" not in orden and "/var/run/docker.sock" not in " ".join(orden)
    assert any(a.startswith("HTTPS_PROXY=http://egress:") for a in orden)
    red, _vol, _relleno = sandbox.ordenes_de_preparacion(nombres, "busybox:1.36.1")
    assert "--internal" in red
    conf = sandbox.configuracion_del_proxy([("api.anthropic.com", 443)])
    assert "dstdomain api.anthropic.com" in conf and "http_access deny all" in conf
    limpieza = sandbox.ordenes_de_limpieza(nombres)
    assert ["volume", "rm", "-f", nombres["volumen"]] in limpieza and ["network", "rm", nombres["red"]] in limpieza


def test_configuracion_de_opencode_deniega_por_defecto():
    from app.services.ticket_a_pr.motor import Modelo
    from app.services.ticket_a_pr.opencode import configuracion, entorno, leer_eventos
    m = Modelo(proveedor="anthropic", modelo="claude-sonnet-4-5", api_key="k" * 20)
    plan = configuracion(m, "plan", [])["permission"]
    assert plan["edit"] == "deny" and plan["bash"] == "deny" and plan["webfetch"] == "deny"
    build = configuracion(m, "build", ["npm test*"])["permission"]
    assert build["edit"] == "allow" and build["bash"] == {"*": "deny", "npm test*": "allow"}
    assert build["external_directory"] == "deny" and build["read"]["*.env"] == "deny"
    env = entorno(m, "plan", [])
    assert env["ANTHROPIC_API_KEY"] == "k" * 20 and "OPENCODE_CONFIG_CONTENT" in env
    assert "k" * 20 not in repr(m)
    eventos = "\n".join([json.dumps({"type": "text", "part": {"type": "text", "text": "Hecho"}}),
                         json.dumps({"type": "step_finish", "part": {"tokens": {"input": 100, "output": 20}, "cost": 0.003}})])
    r = leer_eventos(eventos)
    assert r["texto"] == "Hecho" and r["tokens_in"] == 100 and r["tokens_out"] == 20 and r["coste"] == pytest.approx(0.003)


def test_estado_del_pr_segun_el_cambio():
    from app.services.ticket_a_pr.servicio import estado_para_el_pr
    assert estado_para_el_pr("approved") == "success" and estado_para_el_pr("scheduled") == "success"
    assert estado_para_el_pr("cab_review") == "pending" and estado_para_el_pr("draft") == "pending"
    assert estado_para_el_pr("cancelled") == "failure"
