"""Las dos auditorías de activos: el ámbito explícito y la carga sin tope.

Auditoría 2026-08 (P3-22). Las dos consultaban `Asset` **sin filtro de
organización**, y hay que decir con precisión lo que eso significaba y lo que no.

**En producción no era una fuga.** `SessionLocal` usa `TenantSession`, que
sobrescribe `query()` y añade el filtro por `organization_id` —`Asset` tiene la
columna—, así que el filtro estaba, sólo que implícito.

**Pero era la única capa.** Y este módulo entero —dieciocho funciones de
`asset_service.py`— **no menciona `organization_id` ni una vez**, así que no
había nada detrás si esa capa falla. Ya falló una vez: el criterio rancio del
§3.bis dejaba a cero a toda organización menos la primera del proceso.
`/license-audit` devuelve `license_key`, que es una credencial.

**Lo que sí era un defecto sin mitigar es la carga.** `/software-audit` hacía
`db.query(Asset).all()` —todos los activos, como objetos del ORM, sin tope— para
acabar contando etiquetas. Ahora son dos consultas acotadas, y la de hardware
trae sólo la columna `tags`.

Estos tests van contra el servicio, donde el filtro implícito no actúa (la suite
usa otra factoría de sesiones), así que lo que prueban es la guarda explícita:
**antes del arreglo devolverían las filas ajenas**.
"""
from __future__ import annotations

import pytest

ORG = "org-act-mia"
OTRA = "org-act-ajena"


class _Usuario:
    def __init__(self, organization_id, superadmin=False):
        self.id = "u-act"
        self.organization_id = organization_id
        self.is_superadmin = superadmin


@pytest.fixture()
def inventario(db):
    """Licencias y hardware desplegado en las dos organizaciones."""
    from app.models.service_desk import Asset, AssetStatus, AssetType

    for i, org in enumerate((ORG, OTRA)):
        # Una licencia con butacas: 5 contratadas, 1 usada -> 20%, sobrada.
        db.add(Asset(
            id=f"lic-{org}", code=f"LIC-{i}", name=f"Office de {org}",
            asset_type=AssetType.license, vendor="Microsoft",
            license_seats=5, license_used=1,
            license_key=f"CLAVE-SECRETA-DE-{org}",
            organization_id=org))
        # Hardware desplegado con la etiqueta del software.
        db.add(Asset(
            id=f"hw-{org}", code=f"HW-{i}", name=f"Portatil de {org}",
            asset_type=AssetType.hardware, status=AssetStatus.deployed,
            tags=f"office de {org},antivirus", organization_id=org))
    db.commit()


# -- La auditoría de licencias ---------------------------------------------

def test_EL_HALLAZGO_la_auditoria_de_licencias_no_lista_las_de_otro_cliente(
    db, inventario
):
    """Devuelve `license_key`: lo que se filtraba era una credencial."""
    from app.services.service_desk import asset_service as svc

    datos = svc.auditoria_de_licencias(db, _Usuario(ORG))
    claves = {i["license_key"] for i in datos["items"]}
    assert claves == {f"CLAVE-SECRETA-DE-{ORG}"}, (
        f"la auditoría expone claves de otras organizaciones: {claves}")
    assert datos["summary"]["total_licenses"] == 1


def test_EL_ESCENARIO_la_consulta_de_antes_alcanzaba_las_dos(db, inventario):
    """Que el escenario es real: sin filtro se ven las dos organizaciones."""
    from app.models.service_desk import Asset, AssetType

    filas = (
        db.query(Asset)
        .filter(Asset.asset_type.in_([AssetType.software, AssetType.license]))
        .all()
    )
    assert {a.organization_id for a in filas} == {ORG, OTRA}, (
        "la consulta sin ámbito ya no alcanza las dos organizaciones; "
        "revisar si estos tests siguen midiendo lo que dicen")


def test_el_estado_de_la_licencia_y_su_umbral(db, inventario):
    """El 40 estaba en duro en el cuerpo del endpoint."""
    from app.services.service_desk import asset_service as svc

    assert svc.UMBRAL_DE_LICENCIA_SOBRADA == 40

    datos = svc.auditoria_de_licencias(db, _Usuario(ORG))
    fila = datos["items"][0]
    assert fila["utilization_pct"] == 20.0
    assert fila["status"] == "over_licensed"
    assert datos["summary"]["over_licensed_count"] == 1
    assert datos["summary"]["under_licensed_count"] == 0


def test_una_licencia_con_mas_uso_que_butacas_sale_como_insuficiente(db):
    from app.models.service_desk import Asset, AssetType
    from app.services.service_desk import asset_service as svc

    db.add(Asset(
        id="lic-pasada", code="LIC-9", name="Jira", asset_type=AssetType.license,
        license_seats=2, license_used=7, organization_id=ORG))
    db.commit()

    fila = svc.auditoria_de_licencias(db, _Usuario(ORG))["items"][0]
    assert fila["status"] == "under_licensed"
    assert fila["utilization_pct"] == 350.0


def test_un_sujeto_sin_organizacion_no_ve_las_licencias_de_todos(db, inventario):
    """El filtro no es condicional: ve las filas sin organización, no todas."""
    from app.services.service_desk import asset_service as svc

    datos = svc.auditoria_de_licencias(db, _Usuario(None))
    assert datos["items"] == []


def test_un_superadmin_si_ve_las_de_todos(db, inventario):
    from app.services.service_desk import asset_service as svc

    datos = svc.auditoria_de_licencias(db, _Usuario(None, superadmin=True))
    assert datos["summary"]["total_licenses"] == 2


# -- La auditoría de software ----------------------------------------------

def test_EL_HALLAZGO_la_auditoria_de_software_no_cuenta_el_hardware_ajeno(
    db, inventario
):
    from app.services.service_desk import asset_service as svc

    datos = svc.auditoria_de_software(db, _Usuario(ORG))
    assert datos["total"] == 1
    fila = datos["audit_rows"][0]
    assert fila["software"] == f"Office de {ORG}"
    # Un portátil propio con la etiqueta, y ninguno ajeno.
    assert fila["deployed_count"] == 1
    assert fila["license_key_present"] is True


def test_la_auditoria_de_software_no_carga_todos_los_activos(db, inventario):
    """El defecto sin mitigar: `db.query(Asset).all()` sin tope.

    Se comprueba que ninguna de las sentencias emitidas es un `SELECT` de la
    tabla de activos **sin cláusula `WHERE`**, que es la forma exacta que tenía.
    """
    from sqlalchemy import event as sa_event

    from app.services.service_desk import asset_service as svc

    enlace = db.get_bind()
    sentencias: list[str] = []

    def anotar(conn, cursor, statement, parameters, context, executemany):
        sentencias.append(" ".join(statement.split()))

    sa_event.listen(enlace, "before_cursor_execute", anotar)
    try:
        svc.auditoria_de_software(db, _Usuario(ORG))
    finally:
        sa_event.remove(enlace, "before_cursor_execute", anotar)

    de_activos = [s for s in sentencias if "sd_assets" in s]
    assert de_activos, "no se ha emitido ninguna consulta de activos"
    sin_where = [s for s in de_activos if "WHERE" not in s.upper()]
    assert not sin_where, f"consulta de activos sin acotar: {sin_where}"

    # Y la de hardware trae sólo la columna que se usa, no el activo entero.
    de_hardware = [s for s in de_activos if "sd_assets.tags" in s]
    assert de_hardware, "no se ve la consulta de etiquetas"
    assert not any("sd_assets.description" in s for s in de_hardware), (
        "la consulta de etiquetas está cargando el activo completo")


def test_sin_etiquetas_el_desplegado_cae_a_las_butacas_usadas(db):
    """El comportamiento original, conservado: es el respaldo declarado."""
    from app.models.service_desk import Asset, AssetType
    from app.services.service_desk import asset_service as svc

    db.add(Asset(
        id="lic-sola", code="LIC-8", name="Solitario",
        asset_type=AssetType.license, license_seats=10, license_used=4,
        organization_id=ORG))
    db.commit()

    fila = svc.auditoria_de_software(db, _Usuario(ORG))["audit_rows"][0]
    assert fila["deployed_count"] == 4


def test_solo_cuenta_el_hardware_desplegado(db):
    """Un portátil en almacén no cuenta como software instalado."""
    from app.models.service_desk import Asset, AssetStatus, AssetType
    from app.services.service_desk import asset_service as svc

    db.add(Asset(id="lic-x", code="LIC-7", name="Antivirus",
                 asset_type=AssetType.license, license_seats=3, license_used=0,
                 organization_id=ORG))
    db.add(Asset(id="hw-almacen", code="HW-7", name="En almacen",
                 asset_type=AssetType.hardware, status=AssetStatus.in_stock,
                 tags="antivirus", organization_id=ORG))
    db.commit()

    fila = svc.auditoria_de_software(db, _Usuario(ORG))["audit_rows"][0]
    assert fila["deployed_count"] == 0
