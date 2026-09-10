"""`approve-baseline` no podía aprobar nada, y nadie comprobaba el proveedor.

Auditoría 2026-08 (P3-22).

## El endpoint que no podía funcionar nunca

`POST /cmdb/discovery/providers/{provider_id}/approve-baseline` buscaba así:

    db.query(CMDBItem).filter(CMDBItem.discovery_provider == provider_id)

Y `CMDBItem.discovery_provider` guarda el **tipo** de proveedor —`aws`,
`kubernetes`, `vsphere`; así lo escribe la reconciliación, con las constantes de
`services/cmdb/utils.py`—, mientras `provider_id` es el UUID de una fila de
`cmdb_discovery_providers`. Medido:

    id del proveedor       1add5ac0-82a0-4d6c-812c-e2e1e46794a6
    provider_type          aws
    CI.discovery_provider  aws

    consulta del endpoint (por id) ->  0 CIs
    consulta por provider_type     ->  1 CI

Cero filas **siempre**, así que la respuesta era invariablemente
`{"ok": false, "error": "No CIs found..."}`. Es la misma clase de defecto que el
nodo «crear ticket» de los flujos de trabajo: escrito, expuesto, con respuesta
de éxito prevista, y sin un solo camino que llegue a ella.

## Y el ámbito, que tampoco estaba

No había ninguna comprobación de a quién pertenece el proveedor, mientras su
vecino `list_discovery_jobs` **sí** la hacía y lo decía en un comentario. Con la
consulta arreglada eso pasa de inocuo a una **escritura cruzada entre
clientes**: aprobar la línea base de los CIs de otro cliente le quita la marca
de deriva, es decir le apaga una alerta de configuración.
"""
from __future__ import annotations

import json

import pytest
from fastapi import HTTPException

ORG = "org-cmdb-mia"
OTRA = "org-cmdb-ajena"


class _Usuario:
    def __init__(self, organization_id, uid="u-cmdb", superadmin=False):
        self.id = uid
        self.organization_id = organization_id
        self.is_superadmin = superadmin


@pytest.fixture()
def dos_nubes(db):
    """Un proveedor AWS y un CI descubierto en cada organización."""
    from datetime import datetime, timezone

    from app.models.cmdb import CMDBDiscoveryProvider, CMDBItem

    creados = {}
    for org in (ORG, OTRA):
        prov = CMDBDiscoveryProvider(
            id=f"prov-{org}", name=f"AWS de {org}", provider_type="aws",
            organization_id=org, is_active=True)
        db.add(prov)
        db.flush()
        ci = CMDBItem(
            id=f"ci-{org}", name=f"i-{org}", ci_type="server",
            discovery_provider="aws", is_discovered=True,
            attributes=json.dumps({"instance_type": "t3.micro"}),
            # Hay deriva detectada: aprobar la línea base la debe limpiar.
            drift_detected_at=datetime.now(timezone.utc),
            organization_id=org)
        db.add(ci)
        db.flush()
        creados[org] = {"proveedor": prov, "ci": ci}
    db.commit()
    return creados


# -- El endpoint que no podía aprobar nada ----------------------------------

def test_EL_ESCENARIO_la_consulta_de_antes_no_encontraba_ni_un_CI(db, dos_nubes):
    """Que el defecto era real, medido y no contado."""
    from app.models.cmdb import CMDBItem

    prov = dos_nubes[ORG]["proveedor"]
    assert prov.id != prov.provider_type

    por_id = db.query(CMDBItem).filter(
        CMDBItem.discovery_provider == prov.id).count()
    por_tipo = db.query(CMDBItem).filter(
        CMDBItem.discovery_provider == prov.provider_type).count()

    assert por_id == 0, "la consulta de antes encuentra algo: revisar el esquema"
    assert por_tipo > 0


def test_EL_HALLAZGO_aprobar_la_linea_base_ahora_aprueba(db, dos_nubes):
    from app.services.cmdb.models import aprobar_linea_base

    ci = dos_nubes[ORG]["ci"]
    assert ci.baseline_attributes is None
    assert ci.drift_detected_at is not None

    datos = aprobar_linea_base(
        db, _Usuario(ORG), dos_nubes[ORG]["proveedor"].id)

    assert datos == {"ok": True, "approved": 1}, (
        f"la aprobación sigue sin encontrar CIs: {datos}")

    # El servicio no confirma: la frontera de transacción es del endpoint, que
    # sólo confirma cuando `ok` es cierto. Aquí se hace lo mismo.
    db.commit()
    db.refresh(ci)
    assert json.loads(ci.baseline_attributes) == {"instance_type": "t3.micro"}
    assert ci.drift_detected_at is None, (
        "la marca de deriva no se ha limpiado, así que el CI seguirá "
        "apareciendo como derivado hasta el próximo scan")


def test_EL_HALLAZGO_no_se_aprueba_la_linea_base_de_otro_cliente(db, dos_nubes):
    """Es una escritura cruzada: le apaga una alerta de configuración."""
    from app.services.cmdb.models import aprobar_linea_base

    ajeno = dos_nubes[OTRA]
    with pytest.raises(HTTPException) as exc:
        aprobar_linea_base(db, _Usuario(ORG), ajeno["proveedor"].id)
    assert exc.value.status_code == 404

    db.refresh(ajeno["ci"])
    assert ajeno["ci"].baseline_attributes is None
    assert ajeno["ci"].drift_detected_at is not None


def test_aprobar_con_el_proveedor_propio_no_toca_los_CIs_del_otro(db, dos_nubes):
    """El proveedor es de la organización, pero el filtro de CIs también hace falta.

    Los dos proveedores son de tipo `aws`, así que filtrar sólo por
    `provider_type` habría alcanzado los CIs de las dos organizaciones.
    """
    from app.services.cmdb.models import aprobar_linea_base

    datos = aprobar_linea_base(
        db, _Usuario(ORG), dos_nubes[ORG]["proveedor"].id)
    assert datos["approved"] == 1, (
        f"se han aprobado {datos['approved']} CIs: el filtro por organización "
        "no está actuando y se han tocado los de otro cliente")

    db.refresh(dos_nubes[OTRA]["ci"])
    assert dos_nubes[OTRA]["ci"].baseline_attributes is None


def test_se_puede_aprobar_un_solo_CI(db, dos_nubes):
    from app.services.cmdb.models import aprobar_linea_base

    datos = aprobar_linea_base(
        db, _Usuario(ORG), dos_nubes[ORG]["proveedor"].id,
        ci_id=dos_nubes[ORG]["ci"].id)
    assert datos == {"ok": True, "approved": 1}


def test_un_CI_de_otro_cliente_por_su_id_no_se_aprueba(db, dos_nubes):
    """Pasando el proveedor propio y el id del CI ajeno."""
    from app.services.cmdb.models import aprobar_linea_base

    datos = aprobar_linea_base(
        db, _Usuario(ORG), dos_nubes[ORG]["proveedor"].id,
        ci_id=dos_nubes[OTRA]["ci"].id)
    assert datos["ok"] is False

    db.refresh(dos_nubes[OTRA]["ci"])
    assert dos_nubes[OTRA]["ci"].baseline_attributes is None


def test_un_sujeto_sin_organizacion_no_aprueba_nada(db, dos_nubes):
    """Sin organización, sin acceso: la misma política que `_can_access`.

    El proveedor tiene organización, así que la guarda ya da 404 antes de
    llegar a los CIs — y eso es lo correcto.
    """
    from app.services.cmdb.models import aprobar_linea_base

    with pytest.raises(HTTPException) as exc:
        aprobar_linea_base(db, _Usuario(None), dos_nubes[ORG]["proveedor"].id)
    assert exc.value.status_code == 404


def test_un_superadmin_si_aprueba_los_de_cualquiera(db, dos_nubes):
    """La excepción declarada de toda la política de aislamiento."""
    from app.services.cmdb.models import aprobar_linea_base

    datos = aprobar_linea_base(
        db, _Usuario(None, superadmin=True), dos_nubes[OTRA]["proveedor"].id)
    # Los dos CIs son de tipo `aws`, y un superadmin no filtra por organización.
    assert datos["approved"] == 2


# -- Los proveedores y sus jobs ---------------------------------------------

def test_solo_se_listan_los_proveedores_propios_y_los_globales(db, dos_nubes):
    from app.models.cmdb import CMDBDiscoveryProvider
    from app.services.cmdb.discovery import proveedores_visibles

    # Un proveedor global, de los que el filtro deja pasar a propósito.
    # `fila_global` porque el sellado del `flush` le pondria organizacion y
    # dejaria de ser global — ver el ayudante en `tests/conftest.py`.
    from tests.conftest import fila_global

    with fila_global(db):
        db.add(CMDBDiscoveryProvider(
            id="prov-global", name="Plantilla", provider_type="snmp",
            organization_id=None, is_active=True))
        db.commit()

    ids = {p.id for p in proveedores_visibles(db, _Usuario(ORG))}
    assert ids == {f"prov-{ORG}", "prov-global"}


def test_EL_HALLAZGO_los_jobs_de_un_proveedor_ajeno_dan_404(db, dos_nubes):
    """La comprobación estaba en el endpoint; ahora vive en el servicio.

    Es un movimiento, no un arreglo: el filtro ya estaba y era correcto. Lo que
    cambia es que ya no se puede olvidar al escribir un endpoint nuevo.
    """
    from app.services.cmdb.discovery import jobs_de_un_proveedor

    with pytest.raises(HTTPException) as exc:
        jobs_de_un_proveedor(
            db, _Usuario(ORG), dos_nubes[OTRA]["proveedor"].id,
            page=1, page_size=20)
    assert exc.value.status_code == 404

    filas, total = jobs_de_un_proveedor(
        db, _Usuario(ORG), dos_nubes[ORG]["proveedor"].id,
        page=1, page_size=20)
    assert (filas, total) == ([], 0)


def test_crear_un_proveedor_lo_deja_en_la_organizacion_del_sujeto(db):
    from app.services.cmdb.discovery import crear_proveedor

    prov = crear_proveedor(db, _Usuario(ORG), {
        "name": "Nuevo AWS", "provider_type": "aws", "is_active": True,
        "config": {"region": "eu-west-1"}, "scan_interval_minutes": 30,
    })
    db.commit()

    assert prov.organization_id == ORG
    assert prov.created_by == "u-cmdb"
    assert json.loads(prov.config_json) == {"region": "eu-west-1"}
    assert prov.scan_interval_minutes == 30


def test_crear_un_proveedor_no_hace_commit(db):
    """La frontera de transacción se queda en el endpoint, con las demás."""
    from app.models.cmdb import CMDBDiscoveryProvider
    from app.services.cmdb.discovery import crear_proveedor

    prov = crear_proveedor(db, _Usuario(ORG), {
        "name": "Sin confirmar", "provider_type": "gcp"})
    db.flush()
    db.rollback()

    assert db.query(CMDBDiscoveryProvider).filter(
        CMDBDiscoveryProvider.id == prov.id).first() is None
