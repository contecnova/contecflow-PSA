"""Dos puertas al mismo marketplace, y ninguna era la buena en todo.

Auditoría 2026-08 (P3-22). `/api/v1/integrations/*` y `/api/v1/sd/connectors/*`
instalan la misma cosa —una `IntegrationInstance` sobre un
`IntegrationConnector`— con dos implementaciones distintas escritas a mano. Cada
una era mejor en algo:

| | integrations | service_desk |
|---|---|---|
| valida `sync_direction`/`sync_frequency` | **sí** | no |
| cifra la configuración | **sí** | no la recibía |
| siembra el catálogo | **sí** | no |
| lista lo instalado sin N+1 | no (una consulta por instancia) | **sí** (JOIN) |

**El defecto con consecuencia** es el de la configuración. La puerta del Service
Desk no la recibía, así que la instancia se guardaba con `encrypted_config` a
NULL. Quien la consume la lee así —comprobado en `endpoints/salesforce_sync.py`—:

    config = json.loads(decrypt_value(inst.encrypted_config) if inst.encrypted_config else "{}")

...y sin `instance_url` ni `access_token` responde **503 «credentials
incomplete»**. Y no hay endpoint para rellenarla después: la integración quedaba
instalada y muerta para siempre.

Estos tests van contra el servicio, que es donde vive ahora la lógica
compartida. La forma de las respuestas de las tres rutas del Service Desk no
cambia: son API publicada.
"""
from __future__ import annotations

import json

import pytest
from fastapi import HTTPException

ORG = "org-mkt-mia"
OTRA = "org-mkt-ajena"


class _Usuario:
    def __init__(self, organization_id, uid="u-mkt"):
        self.id = uid
        self.organization_id = organization_id


# -- El defecto con consecuencia: la instalación sin credenciales -----------

def test_EL_HALLAZGO_instalar_desde_el_service_desk_guarda_la_configuracion(db):
    """Antes se guardaba `encrypted_config` a NULL y la integración nacía muerta."""
    from app.core.encryption import decrypt_value
    from app.services import marketplace_service as svc

    catalogo = svc.catalogo_para_service_desk(db, _Usuario(ORG))
    assert catalogo, "el catálogo no se ha sembrado"
    conector = catalogo[0]

    inst = svc.instalar_por_id(db, _Usuario(ORG), {
        "connector_id": conector["id"],
        "name": "Mi Jira",
        "sync_direction": "bidirectional",
        "sync_frequency": "hourly",
        "config": {"instance_url": "https://x.example", "access_token": "t"},
    })

    assert inst.encrypted_config is not None, (
        "la instalación se ha guardado sin configuración: quien la consuma "
        "responderá 503 «credentials incomplete» y no hay forma de rellenarla")
    # Y va cifrada, no en claro.
    assert "access_token" not in inst.encrypted_config
    assert json.loads(decrypt_value(inst.encrypted_config))["access_token"] == "t"


def test_sin_configuracion_se_guarda_un_objeto_vacio_y_no_un_nulo(db):
    """Instalar sin credenciales sigue permitido, pero deja el hueco explícito."""
    from app.core.encryption import decrypt_value
    from app.services import marketplace_service as svc

    conector = svc.catalogo_para_service_desk(db, _Usuario(ORG))[0]
    inst = svc.instalar_por_id(db, _Usuario(ORG), {
        "connector_id": conector["id"], "name": "Sin credenciales",
    })
    assert json.loads(decrypt_value(inst.encrypted_config)) == {}


# -- La validación que sólo tenía una de las dos puertas --------------------

@pytest.mark.parametrize("campo,valor", [
    ("sync_direction", "hacia-arriba"),
    ("sync_frequency", "cuando-pueda"),
])
def test_EL_HALLAZGO_el_service_desk_ya_no_acepta_cualquier_cadena(db, campo, valor):
    """Aceptaba cualquier valor y lo guardaba; la otra puerta daba 422."""
    from app.services import marketplace_service as svc

    conector = svc.catalogo_para_service_desk(db, _Usuario(ORG))[0]
    datos = {"connector_id": conector["id"], "name": "X", campo: valor}
    with pytest.raises(HTTPException) as exc:
        svc.instalar_por_id(db, _Usuario(ORG), datos)
    assert exc.value.status_code == 422
    assert campo in str(exc.value.detail)


def test_las_dos_puertas_usan_la_misma_lista_blanca(db):
    """El estructural: si alguien añade un valor en un sitio y no en el otro."""
    from app.services import marketplace_service as svc

    assert svc.SENTIDOS_DE_SINCRONIZACION == {
        "inbound", "outbound", "bidirectional"}
    assert svc.FRECUENCIAS_DE_SINCRONIZACION == {
        "realtime", "hourly", "daily", "manual"}

    # Y las dos entradas la aplican: la de `slug` y la de `id`.
    conector = svc.catalogo_para_service_desk(db, _Usuario(ORG))[0]
    with pytest.raises(HTTPException) as por_id:
        svc.instalar_por_id(db, _Usuario(ORG), {
            "connector_id": conector["id"], "name": "X",
            "sync_direction": "no-vale"})
    with pytest.raises(HTTPException) as por_slug:
        svc.install_integration_connector(
            connector_slug=conector["slug"], name="X", config={},
            sync_direction="no-vale", sync_frequency="hourly",
            organization_id=ORG, user_id="u-mkt", db=db)
    assert por_id.value.status_code == por_slug.value.status_code == 422


# -- El sembrado que le faltaba a una de las dos ----------------------------

def test_EL_HALLAZGO_el_catalogo_del_service_desk_ya_no_sale_vacio(db):
    """No sembraba, así que en un despliegue nuevo devolvía [] mientras la otra
    puerta devolvía los conectores del producto."""
    from app.models.marketplace import IntegrationConnector
    from app.services import marketplace_service as svc

    assert db.query(IntegrationConnector).count() == 0, "la BD no está limpia"
    filas = svc.catalogo_para_service_desk(db, _Usuario(ORG))
    assert len(filas) == len(svc.CONNECTOR_CATALOG)


def test_los_conectores_de_soporte_van_primero(db):
    """El orden destacado estaba en duro en el cuerpo del endpoint."""
    from app.services import marketplace_service as svc

    slugs = [c["slug"] for c in svc.catalogo_para_service_desk(db, _Usuario(ORG))]
    destacados = [s for s in slugs if s in svc.CONECTORES_DESTACADOS]
    assert slugs[:len(destacados)] == destacados, (
        "los conectores destacados ya no salen primero")
    # Y en el orden declarado, no alfabético.
    esperado = [s for s in svc.CONECTORES_DESTACADOS if s in slugs]
    assert destacados == esperado


# -- La visibilidad del catálogo --------------------------------------------

def test_un_conector_privado_de_otra_organizacion_no_se_ve_ni_se_instala(db):
    """Las dos puertas leían el catálogo sin filtro alguno.

    Hoy el catálogo que trae el producto es global y por tanto no había fuga
    medible, pero el modelo permite un conector privado —`organization_id` es
    una columna real— y entonces sí la habría. El filtro es «los globales, más
    los propios».
    """
    from app.models.marketplace import IntegrationConnector
    from app.services import marketplace_service as svc

    svc.catalogo_para_service_desk(db, _Usuario(ORG))  # siembra los globales
    ajeno = IntegrationConnector(
        name="Conector privado", slug="privado-ajeno", category="crm",
        auth_scheme="api_key", is_active=True, organization_id=OTRA)
    db.add(ajeno)
    db.commit()

    slugs = {c["slug"] for c in svc.catalogo_para_service_desk(db, _Usuario(ORG))}
    assert "privado-ajeno" not in slugs, (
        "se está listando el conector privado de otro cliente")

    with pytest.raises(HTTPException) as exc:
        svc.instalar_por_id(db, _Usuario(ORG), {
            "connector_id": ajeno.id, "name": "X"})
    assert exc.value.status_code == 404

    # Su dueña sí lo ve, y sigue viendo los globales.
    slugs_suyos = {
        c["slug"] for c in svc.catalogo_para_service_desk(db, _Usuario(OTRA))}
    assert "privado-ajeno" in slugs_suyos
    assert len(slugs_suyos) == len(svc.CONNECTOR_CATALOG) + 1


# -- Lo instalado: el JOIN, y el ámbito -------------------------------------

def test_lo_instalado_es_solo_de_la_propia_organizacion(db):
    from app.services import marketplace_service as svc

    conector = svc.catalogo_para_service_desk(db, _Usuario(ORG))[0]
    svc.instalar_por_id(db, _Usuario(ORG), {
        "connector_id": conector["id"], "name": "La mia"})
    svc.instalar_por_id(db, _Usuario(OTRA), {
        "connector_id": conector["id"], "name": "La suya"})

    nombres = [i["name"] for i in svc.instalados_para_service_desk(db, _Usuario(ORG))]
    assert nombres == ["La mia"]


def test_un_sujeto_sin_organizacion_no_ve_instalaciones(db):
    """El filtro no es condicional: devuelve vacío, no las de todos."""
    from app.services import marketplace_service as svc

    conector = svc.catalogo_para_service_desk(db, _Usuario(ORG))[0]
    svc.instalar_por_id(db, _Usuario(ORG), {
        "connector_id": conector["id"], "name": "La mia"})

    assert svc.instalados_para_service_desk(db, _Usuario(None)) == []


def test_EL_DEL_N_MAS_1_listar_instancias_no_consulta_una_vez_por_instancia(db):
    """`list_integration_instances` hacía una consulta por instancia.

    Se cuenta el número de sentencias emitidas: con el JOIN es constante, así
    que tres instalaciones no cuestan más consultas que una.
    """
    from sqlalchemy import event as sa_event

    from app.services import marketplace_service as svc

    catalogo = svc.catalogo_para_service_desk(db, _Usuario(ORG))
    for i in range(3):
        svc.instalar_por_id(db, _Usuario(ORG), {
            "connector_id": catalogo[i]["id"], "name": f"Instancia {i}"})

    enlace = db.get_bind()
    contador = {"n": 0}

    def contar(conn, cursor, statement, parameters, context, executemany):
        if statement.lstrip().upper().startswith("SELECT"):
            contador["n"] += 1

    sa_event.listen(enlace, "before_cursor_execute", contar)
    try:
        filas = svc.list_integration_instances(organization_id=ORG, db=db)
    finally:
        sa_event.remove(enlace, "before_cursor_execute", contar)

    assert len(filas) == 3
    assert contador["n"] == 1, (
        f"{contador['n']} consultas para 3 instancias: el N+1 ha vuelto")
