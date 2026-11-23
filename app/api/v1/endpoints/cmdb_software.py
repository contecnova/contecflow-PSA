"""CMDB de software, composición y vulnerabilidades — `/api/v1/cmdb/software/*` (19-11-2026).

Diseño: `docs/CMDB_SOFTWARE_Y_VULNERABILIDADES.md`. Servicios:
`app/services/cmdb_software/`.

Guardas (capacidades de `app/core/capacidades.py`):

- `software.ver` / `software.gestionar` → `require_admin_or_pm` (como la CMDB);
- `software.aprobar` (excepciones, líneas base) y `software.config`
  (fuentes, credenciales, SLA) → `require_admin`.

GRC: módulo `cmdb` (primer segmento de la ruta); ABAC `software_*` en las
bajas. Todo cambio se audita en el servicio; la API confirma.
"""
from __future__ import annotations

from typing import Any, Optional

from fastapi import APIRouter, Body, Depends, File, Form, Query, UploadFile
from fastapi.responses import Response
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.core.abac_enforce import enforce_abac
from app.core.codigos_de_error import error
from app.core.constantes import MAX_TAMANO_DE_PAGINA
from app.core.deps import requiere_capacidad
from app.core.responses import APIListResponse, APIResponse
from app.core.uploads import UploadProfile, max_bytes_for, read_and_validate_upload, read_upload_within_limit
from app.core.async_db import run_db
from app.db.session import get_db
from app.models.cmdb_software import (SoftwareBaseline, SoftwareComponent, SoftwareInstance, Vulnerability,
                                      VulnerabilityAffect, VulnerabilitySyncRun)
from app.models.user import User
from app.services.cmdb_software.transaccion import confirmar as _confirmar
from app.services.cmdb_software import (ajustes, analisis, avisos, catalogo as cat, correlacion, fuentes, gestion,
                                        importacion)

router = APIRouter()


def _org(u: User) -> Optional[str]:
    return u.organization_id


async def _leer(fichero: UploadFile) -> bytes:
    contenido = await read_and_validate_upload(fichero, UploadProfile.DATA_IMPORT)
    importacion.comprobar_fichero(contenido)
    return contenido


async def _leer_paquete(fichero: UploadFile) -> bytes:
    """Lectura con tope para los ficheros de componentes, que admiten un zip
    (lo abre el servicio con sus propios límites): sin validación de tipo."""
    contenido = await read_upload_within_limit(fichero, max_bytes_for(UploadProfile.DATA_IMPORT))
    importacion.comprobar_fichero(contenido)
    return contenido


# ── Esquemas de entrada (libres: el servicio valida y responde con código) ──

class Datos(BaseModel):
    model_config = {"extra": "allow"}


def _d(payload: Datos) -> dict:
    return payload.model_dump(exclude_unset=True)


# ── Meta y cuadro de mando ───────────────────────────────────────────────────

@router.get("/meta", summary="Valores permitidos (categorías, orígenes, entornos, relaciones...)")
def meta(current_user: User = Depends(requiere_capacidad("software.gestionar"))):
    from app.services.cmdb_software import configuracion as cfg, formatos, licencias
    return APIResponse.ok(data={
        "categories": cat.CATEGORIAS, "origins": cat.ORIGENES, "criticalities": cat.CRITICIDADES,
        "lifecycles": cat.CICLOS, "distributions": cat.DISTRIBUCIONES, "environments": cat.ENTORNOS,
        "instance_statuses": cat.ESTADOS_INSTANCIA, "exposures": cat.EXPOSICIONES, "relations": cat.RELACIONES,
        "component_relations": cat.RELACIONES_COMPONENTE, "scopes": cat.AMBITOS, "baseline_ops": cfg.OPERADORES,
        "config_formats": tuple(cfg.PARSEADORES), "sbom_formats": formatos.FORMATOS,
        "license_families": licencias.FAMILIAS, "finding_statuses": ("open", "triaged", "in_progress", "mitigated",
                                                                     "resolved", "false_positive", "accepted"),
        "severities": ("critical", "high", "medium", "low", "none", "unknown"), "sources": fuentes.FUENTES,
        "csv_columns": importacion.CSV_COLUMNAS})


@router.get("/dashboard", summary="Cuadro de mando de software y vulnerabilidades")
def dashboard(db: Session = Depends(get_db), current_user: User = Depends(requiere_capacidad("software.gestionar"))):
    return APIResponse.ok(data=analisis.cuadro_de_mando(db, _org(current_user)))


# ── Productos ────────────────────────────────────────────────────────────────

@router.get("/products", summary="Catálogo de software")
def list_products(q: Optional[str] = None, category: Optional[str] = None, origin: Optional[str] = None,
                  lifecycle: Optional[str] = None, include_retired: bool = False, apps_only: bool = False,
                  page: int = Query(1, ge=1), page_size: int = Query(50, ge=1, le=500),
                  db: Session = Depends(get_db), current_user: User = Depends(requiere_capacidad("software.gestionar"))):
    r = analisis.listar_productos(db, _org(current_user), q, category, origin, lifecycle, include_retired, apps_only,
                                  page, page_size)
    return APIListResponse.ok(items=r["items"], total=r["total"], page=page, page_size=page_size)


@router.post("/products", summary="Alta de software en el catálogo", status_code=201)
def create_product(payload: Datos, db: Session = Depends(get_db), current_user: User = Depends(requiere_capacidad("software.gestionar"))):
    p = cat.crear_producto(db, _org(current_user), _d(payload), current_user)
    _confirmar(db)
    return APIResponse.ok(data=cat.serializar_producto(p))


@router.get("/products/{product_id}", summary="Ficha de software (versiones, instancias, uso, licencias)")
def get_product(product_id: str, db: Session = Depends(get_db), current_user: User = Depends(requiere_capacidad("software.gestionar"))):
    org = _org(current_user)
    return APIResponse.ok(data=analisis.ficha(db, org, cat.producto(db, org, product_id)))


@router.patch("/products/{product_id}", summary="Cambiar software del catálogo")
def update_product(product_id: str, payload: Datos, db: Session = Depends(get_db),
                   current_user: User = Depends(requiere_capacidad("software.gestionar"))):
    org = _org(current_user)
    p = cat.actualizar_producto(db, org, cat.producto(db, org, product_id), _d(payload), current_user)
    _confirmar(db)
    return APIResponse.ok(data=cat.serializar_producto(p))


@router.delete("/products/{product_id}", summary="Retirar software del catálogo (baja lógica)")
def delete_product(product_id: str, db: Session = Depends(get_db), current_user: User = Depends(requiere_capacidad("software.gestionar"))):
    enforce_abac(db, current_user, "software_product", product_id, action="delete")
    org = _org(current_user)
    cat.retirar_producto(db, cat.producto(db, org, product_id), current_user)
    _confirmar(db)
    return APIResponse.ok(data={"ok": True})


@router.post("/products/{product_id}/versions", summary="Alta de versión", status_code=201)
def create_version(product_id: str, payload: Datos, db: Session = Depends(get_db),
                   current_user: User = Depends(requiere_capacidad("software.gestionar"))):
    org = _org(current_user)
    v = cat.crear_version(db, org, cat.producto(db, org, product_id), _d(payload), current_user)
    _confirmar(db)
    return APIResponse.ok(data=cat.serializar_version(v))


@router.post("/products/{product_id}/lifecycle", summary="Ciclo de vida por ramas (formato endoflife.date)")
def import_lifecycle(product_id: str, payload: list[dict] = Body(...), db: Session = Depends(get_db),
                     current_user: User = Depends(requiere_capacidad("software.gestionar"))):
    org = _org(current_user)
    p = cat.producto(db, org, product_id)
    n = fuentes.aplicar_ciclos(db, org, p, payload, fuente="import")
    from app.services.audit import audit_log
    audit_log(db, current_user, "IMPORT", "sw_lifecycle", p.id, p.name, metadata={"cycles": n})
    _confirmar(db)
    return APIResponse.ok(data={"cycles": n})


@router.post("/products/{product_id}/licenses", summary="Vincular una licencia de Activos")
def link_license(product_id: str, payload: Datos, db: Session = Depends(get_db),
                 current_user: User = Depends(requiere_capacidad("software.gestionar"))):
    org = _org(current_user)
    p = cat.producto(db, org, product_id)
    cat.vincular_licencia(db, org, p, _d(payload).get("license_id"), current_user)
    _confirmar(db)
    return APIResponse.ok(data=cat.licencias_de(db, org, p))


@router.delete("/products/{product_id}/licenses/{license_id}", summary="Desvincular una licencia de Activos")
def unlink_license(product_id: str, license_id: str, db: Session = Depends(get_db),
                   current_user: User = Depends(requiere_capacidad("software.gestionar"))):
    org = _org(current_user)
    p = cat.producto(db, org, product_id)
    cat.desvincular_licencia(db, org, p, license_id, current_user)
    _confirmar(db)
    return APIResponse.ok(data=cat.licencias_de(db, org, p))


@router.get("/products/{product_id}/baselines", summary="Líneas base de configuración del producto")
def list_baselines(product_id: str, db: Session = Depends(get_db), current_user: User = Depends(requiere_capacidad("software.gestionar"))):
    org = _org(current_user)
    p = cat.producto(db, org, product_id)
    return APIListResponse.ok(items=[cat.serializar_linea_base(b) for b in cat._q(db, SoftwareBaseline, org)
                                     .filter(SoftwareBaseline.product_id == p.id)])


@router.post("/products/{product_id}/baselines", summary="Alta de línea base", status_code=201)
def create_baseline(product_id: str, payload: Datos, db: Session = Depends(get_db),
                    current_user: User = Depends(requiere_capacidad("software.gestionar"))):
    org = _org(current_user)
    b = cat.guardar_linea_base(db, org, cat.producto(db, org, product_id), _d(payload), current_user)
    _confirmar(db)
    return APIResponse.ok(data=cat.serializar_linea_base(b))


def _linea_base(db, org, id_) -> SoftwareBaseline:
    return cat._uno(db, SoftwareBaseline, org, id_, "sw_linea_base_no_encontrada")


@router.patch("/baselines/{baseline_id}", summary="Cambiar línea base (retira su aprobación)")
def update_baseline(baseline_id: str, payload: Datos, db: Session = Depends(get_db),
                    current_user: User = Depends(requiere_capacidad("software.gestionar"))):
    org = _org(current_user)
    b = _linea_base(db, org, baseline_id)
    b = cat.guardar_linea_base(db, org, cat.producto(db, org, b.product_id), _d(payload), current_user, b)
    _confirmar(db)
    return APIResponse.ok(data=cat.serializar_linea_base(b))


@router.post("/baselines/{baseline_id}/approve", summary="Aprobar línea base (dirección)")
def approve_baseline(baseline_id: str, db: Session = Depends(get_db), current_user: User = Depends(requiere_capacidad("software.administrar"))):
    b = _linea_base(db, _org(current_user), baseline_id)
    cat.aprobar_linea_base(db, b, current_user)
    _confirmar(db)
    return APIResponse.ok(data=cat.serializar_linea_base(b))


@router.delete("/baselines/{baseline_id}", summary="Borrar línea base")
def delete_baseline(baseline_id: str, db: Session = Depends(get_db), current_user: User = Depends(requiere_capacidad("software.gestionar"))):
    enforce_abac(db, current_user, "software_baseline", baseline_id, action="delete")
    b = _linea_base(db, _org(current_user), baseline_id)
    cat.borrar_linea_base(db, b, current_user)
    _confirmar(db)
    return APIResponse.ok(data={"ok": True})


# ── Versiones y composición ──────────────────────────────────────────────────

@router.patch("/versions/{version_id}", summary="Cambiar versión (fechas de soporte y fin de vida)")
def update_version(version_id: str, payload: Datos, db: Session = Depends(get_db),
                   current_user: User = Depends(requiere_capacidad("software.gestionar"))):
    v = cat.actualizar_version(db, cat.version(db, _org(current_user), version_id), _d(payload), current_user)
    _confirmar(db)
    return APIResponse.ok(data=cat.serializar_version(v))


@router.delete("/versions/{version_id}", summary="Borrar versión (y su composición)")
def delete_version(version_id: str, db: Session = Depends(get_db), current_user: User = Depends(requiere_capacidad("software.gestionar"))):
    enforce_abac(db, current_user, "software_version", version_id, action="delete")
    cat.borrar_version(db, cat.version(db, _org(current_user), version_id), current_user)
    _confirmar(db)
    return APIResponse.ok(data={"ok": True})


@router.get("/versions/{version_id}/tree", summary="Árbol de dependencias de una versión de software")
def version_tree(version_id: str, db: Session = Depends(get_db), current_user: User = Depends(requiere_capacidad("software.gestionar"))):
    org = _org(current_user)
    return APIResponse.ok(data=analisis.arbol(db, org, cat.version(db, org, version_id)))


@router.post("/versions/{version_id}/components", summary="Añadir componente (lenguaje, framework, librería...)",
             status_code=201)
def add_component(version_id: str, payload: Datos, db: Session = Depends(get_db),
                  current_user: User = Depends(requiere_capacidad("software.gestionar"))):
    org = _org(current_user)
    c = cat.anadir_componente(db, org, cat.version(db, org, version_id), _d(payload), current_user)
    _confirmar(db)
    return APIResponse.ok(data=cat.serializar_componente(c))


@router.delete("/components/{component_id}", summary="Quitar componente")
def delete_component(component_id: str, db: Session = Depends(get_db), current_user: User = Depends(requiere_capacidad("software.gestionar"))):
    enforce_abac(db, current_user, "software_component", component_id, action="delete")
    org = _org(current_user)
    c = cat._uno(db, SoftwareComponent, org, component_id, "sw_componente_no_encontrado")
    cat.borrar_componente(db, org, c, current_user)
    _confirmar(db)
    return APIResponse.ok(data={"ok": True})


@router.post("/versions/{version_id}/import", summary="Importar SBOM, fichero de dependencias o informe de escáner")
async def import_components(version_id: str, file: Optional[UploadFile] = File(None),
                            files: Optional[list[UploadFile]] = File(None), format: Optional[str] = Form(None),
                            replace: bool = Form(False), db: Session = Depends(get_db),
                            current_user: User = Depends(requiere_capacidad("software.gestionar"))):
    """Un fichero (`file`) o varios (`files`: pom.xml con su padre, requirements + lock, un zip...)."""
    org = _org(current_user)
    lista = [f for f in ([file] if file else []) + list(files or []) if f is not None]
    ficheros = [(f.filename or "", await _leer_paquete(f)) for f in lista[:50]]

    def _hacer():
        v = cat.version(db, org, version_id)
        if not lista:
            raise error(422, "sw_fichero_vacio")
        r = importacion.importar_ficheros_de_componentes(db, org, v, ficheros, format, current_user, replace)
        correlacion.reevaluar(db, org, current_user)
        _confirmar(db)
        return r
    return APIResponse.ok(data=await run_db(_hacer))


# ── Instancias ───────────────────────────────────────────────────────────────

@router.get("/instances", summary="Instancias desplegadas")
def list_instances(product_id: Optional[str] = None, ci_id: Optional[str] = None, environment: Optional[str] = None,
                   include_retired: bool = False, db: Session = Depends(get_db),
                   current_user: User = Depends(requiere_capacidad("software.gestionar"))):
    from app.models.cmdb_software import SoftwareProduct
    from app.models.service_desk.cmdb import ConfigurationItem
    org = _org(current_user)
    q = cat._q(db, SoftwareInstance, org)
    if not include_retired:
        q = q.filter(SoftwareInstance.is_active.is_(True))
    if product_id:
        q = q.filter(SoftwareInstance.product_id == product_id)
    if ci_id:
        q = q.filter(SoftwareInstance.ci_id == ci_id)
    if environment:
        q = q.filter(SoftwareInstance.environment == environment)
    filas = q.limit(2000).all()
    prods = {p.id: p for p in cat._q(db, SoftwareProduct, org).filter(
        SoftwareProduct.id.in_({i.product_id for i in filas} or {""}))}
    cis = {c.id: c for c in cat._q(db, ConfigurationItem, org).filter(
        ConfigurationItem.id.in_({i.ci_id for i in filas if i.ci_id} or {""}))}
    return APIListResponse.ok(items=[cat.serializar_instancia(i, prods.get(i.product_id), cis.get(i.ci_id))
                                     for i in filas])


@router.post("/instances", summary="Alta de instancia (qué corre dónde y con qué configuración)", status_code=201)
def create_instance(payload: Datos, db: Session = Depends(get_db), current_user: User = Depends(requiere_capacidad("software.gestionar"))):
    org = _org(current_user)
    i = cat.crear_instancia(db, org, _d(payload), current_user)
    correlacion.reevaluar(db, org, current_user)
    _confirmar(db)
    return APIResponse.ok(data=cat.serializar_instancia(i))


@router.get("/instances/{instance_id}", summary="Instancia con relaciones e historial de configuración")
def get_instance(instance_id: str, db: Session = Depends(get_db), current_user: User = Depends(requiere_capacidad("software.gestionar"))):
    from app.models.cmdb_software import SoftwareInstanceRelation
    from sqlalchemy import or_
    org = _org(current_user)
    i = cat.instancia(db, org, instance_id)
    producto, ci = cat.producto_y_ci_de(db, i)
    relaciones = [cat.serializar_relacion(r) for r in cat._q(db, SoftwareInstanceRelation, org).filter(or_(
        SoftwareInstanceRelation.source_instance_id == i.id, SoftwareInstanceRelation.target_instance_id == i.id))]
    return APIResponse.ok(data={
        **cat.serializar_instancia(i, producto, ci),
        "relations": relaciones, "config_history": cat.historial_de_configuracion(db, org, i, 20)})


@router.patch("/instances/{instance_id}", summary="Cambiar instancia (versión, configuración, CI...)")
def update_instance(instance_id: str, payload: Datos, db: Session = Depends(get_db),
                    current_user: User = Depends(requiere_capacidad("software.gestionar"))):
    org = _org(current_user)
    i = cat.actualizar_instancia(db, org, cat.instancia(db, org, instance_id), _d(payload), current_user)
    correlacion.reevaluar(db, org, current_user)
    _confirmar(db)
    return APIResponse.ok(data=cat.serializar_instancia(i))


@router.delete("/instances/{instance_id}", summary="Retirar instancia")
def delete_instance(instance_id: str, db: Session = Depends(get_db), current_user: User = Depends(requiere_capacidad("software.gestionar"))):
    enforce_abac(db, current_user, "software_instance", instance_id, action="delete")
    org = _org(current_user)
    cat.retirar_instancia(db, org, cat.instancia(db, org, instance_id), current_user)
    correlacion.reevaluar(db, org, current_user)
    _confirmar(db)
    return APIResponse.ok(data={"ok": True})


@router.get("/instances/{instance_id}/config-history", summary="Historial de configuración (enmascarado)")
def config_history(instance_id: str, limit: int = Query(50, ge=1, le=500), db: Session = Depends(get_db),
                   current_user: User = Depends(requiere_capacidad("software.gestionar"))):
    org = _org(current_user)
    return APIListResponse.ok(items=cat.historial_de_configuracion(db, org, cat.instancia(db, org, instance_id), limit))


@router.post("/instances/{instance_id}/approve-baseline", summary="Aprobar la configuración actual como línea base")
def approve_instance_baseline(instance_id: str, db: Session = Depends(get_db),
                              current_user: User = Depends(requiere_capacidad("software.administrar"))):
    org = _org(current_user)
    i = cat.instancia(db, org, instance_id)
    cat.aprobar_linea_base_de_instancia(db, i, current_user)
    _confirmar(db)
    return APIResponse.ok(data=cat.serializar_instancia(i))


@router.post("/relations", summary="Relacionar instancias (depende de, se conecta a, publica en...)", status_code=201)
def create_relation(payload: Datos, db: Session = Depends(get_db), current_user: User = Depends(requiere_capacidad("software.gestionar"))):
    r = cat.crear_relacion(db, _org(current_user), _d(payload), current_user)
    _confirmar(db)
    return APIResponse.ok(data=cat.serializar_relacion(r))


@router.delete("/relations/{relation_id}", summary="Quitar relación")
def delete_relation(relation_id: str, db: Session = Depends(get_db), current_user: User = Depends(requiere_capacidad("software.gestionar"))):
    enforce_abac(db, current_user, "software_relation", relation_id, action="delete")
    cat.borrar_relacion(db, _org(current_user), relation_id, current_user)
    _confirmar(db)
    return APIResponse.ok(data={"ok": True})


# ── Análisis ─────────────────────────────────────────────────────────────────

@router.get("/where-used", summary="Dónde se usa: «nginx», «php < 8.2», «pkg:npm/lodash»")
def where_used(q: str = Query(..., min_length=1), op: Optional[str] = None, version: Optional[str] = None,
               environment: Optional[str] = None, exact: bool = False, db: Session = Depends(get_db),
               current_user: User = Depends(requiere_capacidad("software.gestionar"))):
    return APIResponse.ok(data=analisis.donde_se_usa(db, _org(current_user), q, op, version, environment, exact))


@router.get("/impact", summary="Impacto inverso: software, máquinas, servicios y clientes afectados")
def impact(product_id: Optional[str] = None, instance_id: Optional[str] = None,
           vulnerability_id: Optional[str] = None, finding_id: Optional[str] = None,
           db: Session = Depends(get_db), current_user: User = Depends(requiere_capacidad("software.gestionar"))):
    if not any((product_id, instance_id, vulnerability_id, finding_id)):
        raise error(422, "sw_valor_no_valido", campo="product_id", valor="")
    return APIResponse.ok(data=analisis.impacto(db, _org(current_user), product_id, instance_id, vulnerability_id,
                                                finding_id))


@router.get("/analysis/eol", summary="Software sin soporte o en fin de vida (y el que vence pronto)")
def analysis_eol(days: Optional[int] = Query(None, ge=0, le=3650), prod_only: bool = False,
                 db: Session = Depends(get_db), current_user: User = Depends(requiere_capacidad("software.gestionar"))):
    return APIResponse.ok(data=analisis.fin_de_vida(db, _org(current_user), days, prod_only))


@router.get("/analysis/drift", summary="Deriva de configuración e incumplimientos de línea base")
def analysis_drift(db: Session = Depends(get_db), current_user: User = Depends(requiere_capacidad("software.gestionar"))):
    return APIResponse.ok(data=analisis.deriva(db, _org(current_user)))


@router.get("/analysis/licenses", summary="Licencias de componentes y compatibilidad")
def analysis_licenses(db: Session = Depends(get_db), current_user: User = Depends(requiere_capacidad("software.gestionar"))):
    return APIResponse.ok(data=analisis.licencias(db, _org(current_user)))


@router.get("/machines/{ci_id}", summary="Vista por máquina: software, configuración, hallazgos, activo y licencias")
def machine(ci_id: str, db: Session = Depends(get_db), current_user: User = Depends(requiere_capacidad("software.gestionar"))):
    return APIResponse.ok(data=analisis.maquina(db, _org(current_user), ci_id))


@router.get("/graph", summary="Grafo de relaciones (formato del grafo de la CMDB)")
def graph(product_id: Optional[str] = None, instance_id: Optional[str] = None, ci_id: Optional[str] = None,
          db: Session = Depends(get_db), current_user: User = Depends(requiere_capacidad("software.gestionar"))):
    return APIResponse.ok(data=analisis.grafo(db, _org(current_user), product_id, instance_id, ci_id))


@router.get("/ci-summary", summary="Software de unos CIs (cambios, incidentes y problemas)")
def ci_summary(ci_ids: str = Query(..., description="ids separados por comas"), db: Session = Depends(get_db),
               current_user: User = Depends(requiere_capacidad("software.gestionar"))):
    return APIResponse.ok(data=analisis.resumen_de_cis(db, _org(current_user),
                                                       [x for x in ci_ids.split(",") if x.strip()][:200]))


# ── Conciliación e importación ───────────────────────────────────────────────

@router.get("/reconciliation/duplicates", summary="Software que parece duplicado")
def duplicates(db: Session = Depends(get_db), current_user: User = Depends(requiere_capacidad("software.gestionar"))):
    return APIListResponse.ok(items=importacion.productos_duplicados(db, _org(current_user)))


@router.post("/reconciliation/merge", summary="Fundir dos productos del catálogo")
def merge(payload: Datos, db: Session = Depends(get_db), current_user: User = Depends(requiere_capacidad("software.gestionar"))):
    org = _org(current_user)
    d = _d(payload)
    r = cat.fusionar_productos(db, org, cat.producto(db, org, d.get("source_id")),
                               cat.producto(db, org, d.get("target_id")), current_user)
    correlacion.reevaluar(db, org, current_user)
    _confirmar(db)
    return APIResponse.ok(data=r)


@router.post("/import/csv", summary="Importar catálogo e instancias desde CSV")
async def import_csv(file: UploadFile = File(...), db: Session = Depends(get_db),
                     current_user: User = Depends(requiere_capacidad("software.gestionar"))):
    org = _org(current_user)
    contenido = await _leer(file)

    def _hacer():
        r = importacion.importar_csv(db, org, contenido, current_user)
        correlacion.reevaluar(db, org, current_user)
        _confirmar(db)
        return r
    return APIResponse.ok(data=await run_db(_hacer))


@router.post("/import/alm", summary="Conciliar desde Activos (instalaciones de licencias en equipos con CI)")
def import_alm(db: Session = Depends(get_db), current_user: User = Depends(requiere_capacidad("software.gestionar"))):
    org = _org(current_user)
    r = importacion.importar_desde_alm(db, org, current_user)
    correlacion.reevaluar(db, org, current_user)
    _confirmar(db)
    return APIResponse.ok(data=r)


@router.post("/import/inventory", summary="Inventario de software de una máquina (formato del agente o de un escáner)")
def import_inventory(payload: dict = Body(...), db: Session = Depends(get_db),
                     current_user: User = Depends(requiere_capacidad("software.gestionar"))):
    org = _org(current_user)
    c = cat.ci(db, org, payload.get("ci_id"))
    r = importacion.aplicar_inventario(db, org, c.id, payload.get("inventory") or {}, origen="scan",
                                       usuario=current_user)
    correlacion.reevaluar(db, org, current_user)
    _confirmar(db)
    return APIResponse.ok(data=r)


# ── Hallazgos ────────────────────────────────────────────────────────────────

@router.get("/findings", summary="Hallazgos de vulnerabilidad (prioridad, SLA, impacto)")
def list_findings(status: Optional[str] = "live", severity: Optional[str] = None, product_id: Optional[str] = None,
                  ci_id: Optional[str] = None, kev: Optional[bool] = None, out_of_sla: Optional[bool] = None,
                  q: Optional[str] = None, environment: Optional[str] = None, possible: Optional[bool] = None,
                  page: int = Query(1, ge=1),
                  page_size: int = Query(50, ge=1, le=500), db: Session = Depends(get_db),
                  current_user: User = Depends(requiere_capacidad("software.gestionar"))):
    r = gestion.listar(db, _org(current_user), status, severity, product_id, ci_id, kev, out_of_sla, q, environment,
                       page, page_size, possible)
    return APIListResponse.ok(items=r["items"], total=r["total"], page=page, page_size=page_size)


@router.get("/findings/{finding_id}", summary="Hallazgo con aviso, impacto y excepciones")
def get_finding(finding_id: str, db: Session = Depends(get_db), current_user: User = Depends(requiere_capacidad("software.gestionar"))):
    org = _org(current_user)
    return APIResponse.ok(data=gestion.detalle(db, org, gestion.hallazgo(db, org, finding_id)))


@router.patch("/findings/{finding_id}", summary="Triaje: estado, responsable y notas")
def update_finding(finding_id: str, payload: Datos, db: Session = Depends(get_db),
                   current_user: User = Depends(requiere_capacidad("software.gestionar"))):
    org = _org(current_user)
    f = gestion.cambiar(db, org, gestion.hallazgo(db, org, finding_id), _d(payload), current_user)
    _confirmar(db)
    return APIResponse.ok(data=gestion.serializar(db, f, org=org))


@router.post("/findings/{finding_id}/remediate", summary="Remediar con ticket, problema, cambio o tarea")
def remediate(finding_id: str, payload: Datos, db: Session = Depends(get_db),
              current_user: User = Depends(requiere_capacidad("software.gestionar"))):
    org = _org(current_user)
    d = _d(payload)
    r = gestion.remediar(db, org, gestion.hallazgo(db, org, finding_id), d.get("type") or "", current_user, d)
    _confirmar(db)
    return APIResponse.ok(data=r)


@router.post("/findings/{finding_id}/exceptions", summary="Pedir excepción (riesgo aceptado con caducidad)",
             status_code=201)
def request_exception(finding_id: str, payload: Datos, db: Session = Depends(get_db),
                      current_user: User = Depends(requiere_capacidad("software.gestionar"))):
    org = _org(current_user)
    e = gestion.pedir_excepcion(db, org, gestion.hallazgo(db, org, finding_id), _d(payload), current_user)
    _confirmar(db)
    return APIResponse.ok(data=gestion.serializar_excepcion(e))


@router.get("/exceptions", summary="Excepciones de vulnerabilidad")
def list_exceptions(status: Optional[str] = None, db: Session = Depends(get_db),
                    current_user: User = Depends(requiere_capacidad("software.gestionar"))):
    return APIListResponse.ok(items=gestion.listar_excepciones(db, _org(current_user), status))


@router.post("/exceptions/{exception_id}/approve", summary="Aprobar excepción (dirección; nunca la propia)")
def approve_exception(exception_id: str, payload: Optional[Datos] = None, db: Session = Depends(get_db),
                      current_user: User = Depends(requiere_capacidad("software.administrar"))):
    org = _org(current_user)
    e = gestion.decidir_excepcion(db, org, gestion.excepcion(db, org, exception_id), True, current_user,
                                  (_d(payload) if payload else {}).get("note"))
    _confirmar(db)
    return APIResponse.ok(data=gestion.serializar_excepcion(e))


@router.post("/exceptions/{exception_id}/reject", summary="Rechazar excepción (dirección)")
def reject_exception(exception_id: str, payload: Optional[Datos] = None, db: Session = Depends(get_db),
                     current_user: User = Depends(requiere_capacidad("software.administrar"))):
    org = _org(current_user)
    e = gestion.decidir_excepcion(db, org, gestion.excepcion(db, org, exception_id), False, current_user,
                                  (_d(payload) if payload else {}).get("note"))
    _confirmar(db)
    return APIResponse.ok(data=gestion.serializar_excepcion(e))


@router.post("/exceptions/{exception_id}/revoke", summary="Revocar excepción (el hallazgo vuelve a abierto)")
def revoke_exception(exception_id: str, db: Session = Depends(get_db), current_user: User = Depends(requiere_capacidad("software.administrar"))):
    org = _org(current_user)
    e = gestion.revocar_excepcion(db, org, gestion.excepcion(db, org, exception_id), current_user)
    _confirmar(db)
    return APIResponse.ok(data=gestion.serializar_excepcion(e))


# ── Avisos y sincronización ──────────────────────────────────────────────────

def _serializar_aviso(v: Vulnerability) -> dict:
    import json
    return {"id": v.id, "vuln_id": v.vuln_id, "aliases": json.loads(v.aliases) if v.aliases else [],
            "source": v.source, "title": v.title, "severity": v.severity, "cvss_score": v.cvss_score,
            "cvss_vector": v.cvss_vector, "epss_score": v.epss_score, "epss_percentile": v.epss_percentile,
            "kev": v.kev, "published_at": v.published_at.isoformat() if v.published_at else None,
            "modified_at": v.modified_at.isoformat() if v.modified_at else None}


@router.get("/vulnerabilities", summary="Avisos conocidos")
def list_vulnerabilities(q: Optional[str] = None, severity: Optional[str] = None, kev: Optional[bool] = None,
                         page: int = Query(1, ge=1), page_size: int = Query(50, ge=1, le=500),
                         db: Session = Depends(get_db), current_user: User = Depends(requiere_capacidad("software.gestionar"))):
    from sqlalchemy import or_
    consulta = cat._q(db, Vulnerability, _org(current_user))
    if q:
        patron = f"%{q.strip()}%"
        consulta = consulta.filter(or_(Vulnerability.vuln_id.ilike(patron), Vulnerability.title.ilike(patron),
                                       Vulnerability.aliases.ilike(patron)))
    if severity:
        consulta = consulta.filter(Vulnerability.severity.in_(severity.split(",")))
    if kev is not None:
        consulta = consulta.filter(Vulnerability.kev.is_(kev))
    total = consulta.count()
    filas = (consulta.order_by(Vulnerability.cvss_score.desc().nullslast(), Vulnerability.vuln_id)
             .offset((page - 1) * page_size).limit(page_size).all())
    return APIListResponse.ok(items=[_serializar_aviso(v) for v in filas], total=total, page=page, page_size=page_size)


@router.get("/vulnerabilities/{vulnerability_id}", summary="Aviso con a qué afecta y su impacto en la empresa")
def get_vulnerability(vulnerability_id: str, db: Session = Depends(get_db),
                      current_user: User = Depends(requiere_capacidad("software.gestionar"))):
    import json
    org = _org(current_user)
    v = cat._uno(db, Vulnerability, org, vulnerability_id, "sw_vulnerabilidad_no_encontrada")
    afectas = [{"package_key": a.package_key, "cpe_vendor": a.cpe_vendor, "cpe_product": a.cpe_product,
                "introduced": a.introduced, "fixed": a.fixed, "last_affected": a.last_affected,
                "versions": json.loads(a.versions) if a.versions else [], "range_text": a.range_text}
               for a in cat._q(db, VulnerabilityAffect, org).filter(VulnerabilityAffect.vulnerability_id == v.id)]
    return APIResponse.ok(data={**_serializar_aviso(v), "description": v.description,
                                "references": json.loads(v.references) if v.references else [],
                                "cwe": json.loads(v.cwe) if v.cwe else [], "affects": afectas,
                                "impact": analisis.impacto(db, org, vulnerability_id=v.id)})


@router.post("/vulnerabilities", summary="Alta manual de un aviso (formato común)", status_code=201)
def create_vulnerability(payload: Datos, db: Session = Depends(get_db),
                         current_user: User = Depends(requiere_capacidad("software.gestionar"))):
    org = _org(current_user)
    d = _d(payload)
    if not (d.get("vuln_id") or "").strip():
        raise error(422, "sw_valor_no_valido", campo="vuln_id", valor="")
    r = avisos.guardar_avisos(db, org, [{**d, "source": "manual"}], "manual")
    from app.services.audit import audit_log
    audit_log(db, current_user, "CREATE", "sw_vulnerability", None, d["vuln_id"], metadata=r)
    res = correlacion.reevaluar(db, org, current_user)
    _confirmar(db)
    return APIResponse.ok(data={**r, "findings_new": res["findings_new"]})


@router.post("/vulnerabilities/import", summary="Importar avisos de un fichero (OSV, NVD, GitHub, Trivy, Grype, CSV)")
async def import_vulnerabilities(file: UploadFile = File(...), db: Session = Depends(get_db),
                                 current_user: User = Depends(requiere_capacidad("software.gestionar"))):
    org = _org(current_user)
    contenido = await _leer(file)

    def _hacer():
        r = avisos.importar_fichero_de_avisos(db, org, contenido, file.filename, current_user)
        _confirmar(db)
        return r
    return APIResponse.ok(data=await run_db(_hacer))


@router.post("/reevaluate", summary="Reevaluar hallazgos (correlación, prioridad y SLA)")
def reevaluate(db: Session = Depends(get_db), current_user: User = Depends(requiere_capacidad("software.gestionar"))):
    r = correlacion.reevaluar_y_registrar(db, _org(current_user), current_user)
    _confirmar(db)
    return APIResponse.ok(data={k: v for k, v in r.items() if k != "new_ids"})


@router.post("/sync", summary="Sincronizar fuentes de avisos activas y reevaluar")
def sync(payload: Optional[Datos] = None, db: Session = Depends(get_db),
         current_user: User = Depends(requiere_capacidad("software.gestionar"))):
    org = _org(current_user)
    res = fuentes.sincronizar(db, org, (_d(payload) if payload else {}).get("sources"), current_user)
    cor = correlacion.reevaluar_y_registrar(db, org, current_user)
    _confirmar(db)
    return APIResponse.ok(data={"sources": res, **{k: v for k, v in cor.items() if k != "new_ids"}})


@router.get("/sync/runs", summary="Últimas sincronizaciones e importaciones de avisos")
def sync_runs(limit: int = Query(50, ge=1, le=500), db: Session = Depends(get_db),
              current_user: User = Depends(requiere_capacidad("software.gestionar"))):
    filas = (cat._q(db, VulnerabilitySyncRun, _org(current_user)).order_by(VulnerabilitySyncRun.started_at.desc())
             .limit(limit).all())
    return APIListResponse.ok(items=[{"id": r.id, "source": r.source, "status": r.status,
                                      "started_at": r.started_at.isoformat() if r.started_at else None,
                                      "finished_at": r.finished_at.isoformat() if r.finished_at else None,
                                      "queries": r.queries, "vulnerabilities": r.vulnerabilities,
                                      "findings_new": r.findings_new, "findings_resolved": r.findings_resolved,
                                      "error": r.error, "triggered_by": r.triggered_by} for r in filas])


# ── Configuración (Configuración → Software y vulnerabilidades) ─────────────

@router.get("/config", summary="Configuración del módulo (sin secretos)")
def get_config(db: Session = Depends(get_db), current_user: User = Depends(requiere_capacidad("software.administrar"))):
    return APIResponse.ok(data=ajustes.leer(db, _org(current_user)))


@router.put("/config", summary="Guardar configuración (credenciales cifradas; vacío = no cambia)")
def put_config(payload: dict[str, Any] = Body(...), db: Session = Depends(get_db),
               current_user: User = Depends(requiere_capacidad("software.administrar"))):
    datos = ajustes.guardar(db, _org(current_user), payload, current_user)
    _confirmar(db)
    return APIResponse.ok(data=datos)


@router.post("/config/test/{source}", summary="Probar la conexión con una fuente")
def test_source(source: str, db: Session = Depends(get_db), current_user: User = Depends(requiere_capacidad("software.administrar"))):
    return APIResponse.ok(data=fuentes.probar(db, _org(current_user), source))


# ── Conexiones de escaneo (SSH, WinRM, API de EDR/RMM) ──────────────────────
# Se configuran en Configuración (`software.config`, admin) y se lanzan bajo
# demanda desde la CMDB (`software.gestionar`). Programadas: `cmdb_discovery_run`.

@router.get("/scanners", summary="Conexiones de escaneo (sin secretos)")
def list_scanners(db: Session = Depends(get_db), current_user: User = Depends(requiere_capacidad("software.gestionar"))):
    from app.services.cmdb_software import escaneos
    return APIListResponse.ok(items=escaneos.listar(db, _org(current_user)))


@router.get("/scanners/fields", summary="Campos de configuración de cada tipo de conexión")
def scanner_fields(current_user: User = Depends(requiere_capacidad("software.gestionar"))):
    from app.services.cmdb_software import escaneos
    return APIResponse.ok(data={t: [{"key": k.rstrip("*"), "secret": k.endswith("*")} for k in campos]
                                for t, campos in escaneos.CAMPOS.items()})


@router.post("/scanners", summary="Alta de conexión de escaneo (credenciales cifradas)", status_code=201)
def create_scanner(payload: dict = Body(...), db: Session = Depends(get_db), current_user: User = Depends(requiere_capacidad("software.administrar"))):
    from app.services.cmdb_software import escaneos
    c = escaneos.guardar(db, _org(current_user), payload, current_user)
    _confirmar(db)
    return APIResponse.ok(data=escaneos.serializar(c))


@router.patch("/scanners/{scanner_id}", summary="Cambiar conexión de escaneo (secreto vacío = no cambia)")
def update_scanner(scanner_id: str, payload: dict = Body(...), db: Session = Depends(get_db),
                   current_user: User = Depends(requiere_capacidad("software.administrar"))):
    from app.services.cmdb_software import escaneos
    org = _org(current_user)
    c = escaneos.guardar(db, org, payload, current_user, escaneos.conexion(db, org, scanner_id))
    _confirmar(db)
    return APIResponse.ok(data=escaneos.serializar(c))


@router.delete("/scanners/{scanner_id}", summary="Borrar conexión de escaneo")
def delete_scanner(scanner_id: str, db: Session = Depends(get_db), current_user: User = Depends(requiere_capacidad("software.administrar"))):
    from app.services.cmdb_software import escaneos
    enforce_abac(db, current_user, "software_scanner", scanner_id, action="delete")
    org = _org(current_user)
    escaneos.borrar(db, escaneos.conexion(db, org, scanner_id), current_user)
    _confirmar(db)
    return APIResponse.ok(data={"ok": True})


@router.post("/scanners/{scanner_id}/test", summary="Probar la conexión con el primer equipo")
def test_scanner(scanner_id: str, db: Session = Depends(get_db), current_user: User = Depends(requiere_capacidad("software.administrar"))):
    from app.services.cmdb_software import escaneos
    return APIResponse.ok(data=escaneos.probar(db, escaneos.conexion(db, _org(current_user), scanner_id)))


@router.post("/scanners/{scanner_id}/run", summary="Escanear ahora (todos los equipos o los indicados)")
def run_scanner(scanner_id: str, payload: Optional[Datos] = None, db: Session = Depends(get_db),
                current_user: User = Depends(requiere_capacidad("software.gestionar"))):
    from app.services.cmdb_software import escaneos
    org = _org(current_user)
    c = escaneos.conexion(db, org, scanner_id)
    hosts = (_d(payload) if payload else {}).get("hosts")
    r = escaneos.ejecutar_con_registro(db, c, current_user, hosts if isinstance(hosts, list) else None)
    _confirmar(db)
    return APIResponse.ok(data=r)


@router.get("/scanners/{scanner_id}/runs", summary="Ejecuciones de una conexión de escaneo")
def scanner_runs(scanner_id: str, limit: int = Query(20, ge=1, le=MAX_TAMANO_DE_PAGINA), db: Session = Depends(get_db),
                 current_user: User = Depends(requiere_capacidad("software.gestionar"))):
    import json as _json
    from app.models.cmdb import CMDBDiscoveryJob
    from app.services.cmdb_software import escaneos
    c = escaneos.conexion(db, _org(current_user), scanner_id)
    filas = escaneos.ultimas_ejecuciones(db, c, limit)

    def resumen(j):
        try:
            return _json.loads(j.summary_json) if j.summary_json else None
        except ValueError:
            return None
    return APIListResponse.ok(items=[{"id": j.id, "status": j.status, "triggered_by": j.triggered_by,
                                      "started_at": j.started_at.isoformat() if j.started_at else None,
                                      "finished_at": j.finished_at.isoformat() if j.finished_at else None,
                                      "error": j.error_message, "summary": resumen(j)} for j in filas])


# ── Exportación ──────────────────────────────────────────────────────────────

@router.get("/export/findings.csv", summary="Exportar hallazgos (CSV)")
def export_findings(db: Session = Depends(get_db), current_user: User = Depends(requiere_capacidad("software.gestionar"))):
    from app.services.audit import audit_log
    texto = analisis.exportar_hallazgos_csv(db, _org(current_user))
    audit_log(db, current_user, "EXPORT", "sw_findings", None, "findings.csv")
    _confirmar(db)
    return Response(content=texto, media_type="text/csv; charset=utf-8",
                    headers={"Content-Disposition": 'attachment; filename="hallazgos.csv"'})


@router.get("/export/inventory.csv", summary="Exportar inventario de software desplegado (CSV)")
def export_inventory(db: Session = Depends(get_db), current_user: User = Depends(requiere_capacidad("software.gestionar"))):
    from app.services.audit import audit_log
    texto = analisis.exportar_inventario_csv(db, _org(current_user))
    audit_log(db, current_user, "EXPORT", "sw_instances", None, "inventory.csv")
    _confirmar(db)
    return Response(content=texto, media_type="text/csv; charset=utf-8",
                    headers={"Content-Disposition": 'attachment; filename="inventario-software.csv"'})
