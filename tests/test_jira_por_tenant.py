"""Empujar un ticket a Jira no comprobaba de quién era la configuración.

Auditoría 2026-08 (P3-22). En `endpoints/jira_integration.py` cuatro endpoints
usaban `org_scoped_or_404` y otros tres buscaban por id a secas. La asimetría
dentro del mismo fichero es el patrón que aparece en toda esta auditoría, y aquí
lo que estaba sin acotar es lo que más pesa:

* **`push_ticket`** buscaba el ticket **y la configuración de Jira** por id.
  Una `JiraConfig` guarda `jira_email` y `jira_api_token_enc`: usar la de otro
  cliente es empujar un ticket **con sus credenciales**.
* **`run_manual_sync`** pasaba el `config_id` a una tarea de fondo sin
  comprobar nada, así que un administrador disparaba la sincronización de la
  configuración de otro.
* **El listado contaba el total sin acotar.** Un total sin filtro diría «hay
  12» y devolvería 3.

Lo único que lo impedía era el filtro implícito de `TenantSession`. Estos tests
van contra el servicio, donde ese filtro no actúa (la suite usa otra factoría),
así que lo que comprueban es la guarda explícita: **antes del arreglo
devolverían la fila ajena**.

> **Y una comprobación que hice y descartó un defecto que iba a reportar.**
> `run_manual_sync` pasa la sesión de la petición a `background_tasks`, y creía
> que en FastAPI moderno la dependencia se cierra antes de que la tarea corra.
> Medido con un `TestClient` sobre FastAPI 0.135: la sesión **sigue abierta**
> cuando la tarea se ejecuta. No es un defecto, y no lo reporto.
"""
from __future__ import annotations

import pytest
from fastapi import HTTPException
from app.core.errores import ErrorDeDominio

ORG = "org-jira-mia"
OTRA = "org-jira-ajena"


class _Usuario:
    def __init__(self, organization_id):
        self.id = f"u-{organization_id}"
        self.organization_id = organization_id


@pytest.fixture()
def escenario(db):
    """Una configuración de Jira y un ticket en cada organización."""
    from app.models.jira_integration import JiraConfig
    from app.models.service_desk import Ticket

    creados = {}
    for org in (ORG, OTRA):
        cfg = JiraConfig(
            organization_id=org, name=f"Jira de {org}",
            jira_base_url="https://x.atlassian.net",
            jira_email=f"cuenta-{org}@example.com",
            jira_api_token_enc=f"token-secreto-de-{org}",
            jira_project_key="TEST", is_active=True,
        )
        db.add(cfg)
        db.flush()
        # `number`, `ticket_type`, `title` y `description` son NOT NULL.
        t = Ticket(
            organization_id=org, number=f"T-{org}", ticket_type="incident",
            title=f"Ticket de {org}", description="cuerpo")
        db.add(t)
        db.flush()
        creados[org] = {"config": cfg, "ticket": t}
    db.commit()
    return creados


# ── La configuración lleva credenciales ─────────────────────────────────────

def test_EL_HALLAZGO_no_se_puede_usar_la_configuracion_de_otro_cliente(db, escenario):
    """Es la guarda que más pesa: esa fila guarda el token de Jira del otro."""
    from app.services.service_desk import jira_sync_service as svc

    ajena = escenario[OTRA]["config"]
    with pytest.raises((HTTPException, ErrorDeDominio)) as exc:
        svc.configuracion_activa_propia(db, _Usuario(ORG), ajena.id)
    assert exc.value.status_code == 404

    mia = escenario[ORG]["config"]
    assert svc.configuracion_activa_propia(db, _Usuario(ORG), mia.id).id == mia.id


def test_una_configuracion_parada_no_sirve_para_empujar(db, escenario):
    """`configuracion_activa_propia` exige que esté activa, no sólo que sea mía."""
    from app.services.service_desk import jira_sync_service as svc

    mia = escenario[ORG]["config"]
    mia.is_active = False
    db.commit()

    with pytest.raises((HTTPException, ErrorDeDominio)) as exc:
        svc.configuracion_activa_propia(db, _Usuario(ORG), mia.id)
    assert exc.value.status_code == 404
    # Pero sigue siendo suya para verla y editarla.
    assert svc.configuracion_propia(db, _Usuario(ORG), mia.id).id == mia.id


def test_EL_HALLAZGO_no_se_puede_empujar_el_ticket_de_otro_cliente(db, escenario):
    from app.services.service_desk import jira_sync_service as svc

    ajeno = escenario[OTRA]["ticket"]
    with pytest.raises((HTTPException, ErrorDeDominio)) as exc:
        svc.ticket_propio(db, _Usuario(ORG), ajeno.id)
    assert exc.value.status_code == 404

    mio = escenario[ORG]["ticket"]
    assert svc.ticket_propio(db, _Usuario(ORG), mio.id).id == mio.id


# ── Listado y total ─────────────────────────────────────────────────────────

def test_EL_HALLAZGO_el_total_del_listado_se_cuenta_con_el_mismo_filtro(db, escenario):
    """Un total sin acotar diría «hay 2» y devolvería 1."""
    from app.services.service_desk import jira_sync_service as svc

    filas, total = svc.listar_configuraciones(
        db, _Usuario(ORG), page=1, page_size=50)
    assert total == 1, "el total no coincide con lo que se devuelve"
    assert [c.organization_id for c in filas] == [ORG]


def test_el_registro_de_sincronizacion_se_acota_por_su_configuracion(db, escenario):
    """El log no lleva filtro de organización a propósito: cuelga de una
    configuración ya comprobada, así que el ámbito llega por la clave padre."""
    from app.models.jira_integration import JiraSyncLog
    from app.services.service_desk import jira_sync_service as svc

    mia = escenario[ORG]["config"]
    ajena = escenario[OTRA]["config"]
    db.add(JiraSyncLog(
        organization_id=ORG, config_id=mia.id, event_type="created",
        direction="contecflow_to_jira", success=True))
    db.add(JiraSyncLog(
        organization_id=OTRA, config_id=ajena.id, event_type="created",
        direction="contecflow_to_jira", success=True))
    db.commit()

    filas, total = svc.registro_de_sincronizacion(
        db, mia, page=1, page_size=50)
    assert total == 1
    assert filas[0].config_id == mia.id


# ── Alta y baja ─────────────────────────────────────────────────────────────

def test_una_configuracion_nueva_queda_en_la_organizacion_de_quien_la_crea(db):
    from app.services.service_desk import jira_sync_service as svc

    cfg = svc.crear_configuracion(db, _Usuario(ORG), {
        "name": "Nueva", "jira_base_url": "https://y.atlassian.net",
        "jira_email": "a@b.c", "jira_api_token_enc": "t",
        "jira_project_key": "NEW",
    })
    assert cfg.organization_id == ORG
    assert cfg.created_by_user_id == f"u-{ORG}"


def test_no_se_puede_borrar_la_configuracion_de_otro_cliente(db, escenario):
    from app.services.service_desk import jira_sync_service as svc

    ajena = escenario[OTRA]["config"]
    with pytest.raises((HTTPException, ErrorDeDominio)) as exc:
        svc.borrar_configuracion(db, _Usuario(ORG), ajena.id)
    assert exc.value.status_code == 404


def test_el_parche_serializa_los_mapas_y_cifra_el_token(db, escenario):
    """Tres campos no se asignan por nombre y esa asimetría se fija aquí."""
    import json

    from app.services.service_desk import jira_sync_service as svc

    mia = escenario[ORG]["config"]
    svc.aplicar_cambios_de_configuracion(db, mia, {
        "jira_api_token": "token-nuevo",
        "status_map": {"open": "To Do"},
        "priority_map": {"high": "High"},
        "name": "Renombrada",
    })
    # Auditoria 2026-11: el token se cifra (antes quedaba en claro).
    assert mia.jira_api_token_enc != "token-nuevo"
    assert svc.jira_token_en_claro(mia) == "token-nuevo"
    assert json.loads(mia.status_map_json) == {"open": "To Do"}
    assert json.loads(mia.priority_map_json) == {"high": "High"}
    assert mia.name == "Renombrada"
