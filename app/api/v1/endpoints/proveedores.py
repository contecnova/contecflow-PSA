"""/suppliers — proveedores y externalizacion (docs/PROVEEDORES_Y_EXTERNALIZACION.md).

Lectura: gestores (`require_any_manager`, capacidad `proveedores.ver`).
Escritura, finanzas y GRC: admin y PM (`require_admin_or_pm`,
`proveedores.gestionar`). Las plantillas de contrato son configuracion
(`proveedores.config`, admin y PM).

Migracion 191: referencias para los selectores de la ficha, contactos del
portal del proveedor, adjuntos de informes, aprobacion por importe (motor
comun) y fuentes de medicion (CMDB, API e importacion). El portal del propio
proveedor esta en `proveedores_portal.py` (`/supplier-portal`).
"""
from __future__ import annotations

from datetime import date
from typing import Optional

from fastapi import APIRouter, Depends, File, Query, Request, UploadFile
from sqlalchemy.orm import Session

from app.core.abac_enforce import enforce_abac
from app.core.network import ip_del_cliente
from app.core.deps import requiere_capacidad
from app.core.responses import APIListResponse, APIResponse
from app.core.uploads import UploadProfile, read_and_validate_upload_sync, safe_filename
from app.db.session import get_db
from app.models.user import User
from app.schemas.proveedores import (
    AccesoIn, AltaDeFreelance, Clasificacion, ConciliarIn, ConsumoIn, ContactoDelPortalIn, ContratoIn, DocumentoIn,
    EvaluacionIn, ImportacionDeRecuentosIn, InformeIn, LineaIn, Motivo, PaqueteIn, PeriodoIn, RecuentoIn, RevisionIn,
    ServicioIn, TareasDelPaquete, VistaPreviaDeMedicionIn,
)
from app.services.proveedores import (
    consumo, contratos, facturacion, ficha, grc, medicion, paquetes, portal, referencias, rendimiento, servicios, tipos,
)

router = APIRouter()
# Guardas por capacidad (19-11-2026, `app.core.deps.requiere_capacidad`), explicitas en
# cada firma para que los barridos de guardas las reconozcan: `proveedores.ver`
# (gestores), `proveedores.gestionar` y `proveedores.config` (admin y PM).


def _set(payload) -> dict:
    return payload.model_dump(exclude_unset=True)


def _periodo(desde: Optional[date], hasta: Optional[date]) -> tuple[date, date]:
    import calendar

    from app.core import timeutil
    hoy = timeutil.today()
    hasta = hasta or hoy.replace(day=calendar.monthrange(hoy.year, hoy.month)[1])
    desde = desde or hasta.replace(day=1)
    return desde, hasta


# ── Ficha ────────────────────────────────────────────────────────────────────

@router.get("/meta", summary="Enumeraciones de proveedores")
def meta(_: User = Depends(requiere_capacidad("proveedores.ver"))):
    return APIResponse.ok(data=tipos.meta())


@router.get("/references", summary="Datos para los selectores de la ficha (presupuestos, centros de coste, "
                                     "contratos ALM, catálogo del service desk, sesiones UAT, CMDB)")
def referencias_de_la_ficha(project_id: Optional[str] = None, sub_id: Optional[str] = None,
                            db: Session = Depends(get_db), _: User = Depends(requiere_capacidad("proveedores.ver"))):
    sub = ficha.exigir(db, sub_id) if sub_id else None
    return APIResponse.ok(data=referencias.referencias(db, sub, project_id))


@router.post("/metering/preview", summary="Probar una fuente de medición (cuántos contaría hoy, sin guardar)")
def vista_previa_de_medicion(payload: VistaPreviaDeMedicionIn, db: Session = Depends(get_db), _: User = Depends(requiere_capacidad("proveedores.gestionar"))):
    return APIResponse.ok(data=medicion.vista_previa(db, payload.metering_source, payload.metering_config or {},
                                                     payload.unit))


@router.get("/overview", summary="Cuadro global de proveedores")
def overview(db: Session = Depends(get_db), _: User = Depends(requiere_capacidad("proveedores.ver"))):
    return APIResponse.ok(data=ficha.resumen_global(db))


@router.get("/assignable", summary="Empresas de outsourcing a las que se puede externalizar")
def assignable(project_id: Optional[str] = None, db: Session = Depends(get_db), _: User = Depends(requiere_capacidad("proveedores.ver"))):
    items = ficha.asignables(db, project_id)
    return APIListResponse.ok(items=items, total=len(items))


@router.post("/freelance", summary="Alta de freelance en un paso (proveedor + persona + recurso)", status_code=201)
def alta_freelance(payload: AltaDeFreelance, db: Session = Depends(get_db), u: User = Depends(requiere_capacidad("proveedores.gestionar"))):
    return APIResponse.ok(data=ficha.alta_freelance(db, payload, u))


@router.get("/by-project/{project_id}", summary="Paquetes y tareas externalizadas de un proyecto")
def por_proyecto(project_id: str, db: Session = Depends(get_db), _: User = Depends(requiere_capacidad("proveedores.ver"))):
    return APIResponse.ok(data=paquetes.del_proyecto(db, project_id))


@router.get("/contract-templates", summary="Plantillas de contrato")
def plantillas(db: Session = Depends(get_db), _: User = Depends(requiere_capacidad("proveedores.ver"))):
    items = contratos.listar_plantillas(db)
    return APIListResponse.ok(items=items, total=len(items))


@router.post("/contract-templates", summary="Crear plantilla de contrato", status_code=201)
def crear_plantilla(payload: ContratoIn, db: Session = Depends(get_db), u: User = Depends(requiere_capacidad("proveedores.config"))):
    return APIResponse.ok(data=contratos.crear(db, None, _set(payload), u, plantilla=True))


@router.patch("/contract-templates/{tid}", summary="Editar plantilla de contrato")
def editar_plantilla(tid: str, payload: ContratoIn, db: Session = Depends(get_db), u: User = Depends(requiere_capacidad("proveedores.config"))):
    return APIResponse.ok(data=contratos.actualizar(db, contratos.exigir(db, tid, True), _set(payload), u))


@router.delete("/contract-templates/{tid}", summary="Borrar plantilla de contrato")
def borrar_plantilla(tid: str, db: Session = Depends(get_db), u: User = Depends(requiere_capacidad("proveedores.config"))):
    enforce_abac(db, u, "supplier_contract", tid, action="delete")
    return APIResponse.ok(data=contratos.borrar_plantilla(db, contratos.exigir(db, tid, True), u))


@router.get("/{sub_id}/profile", summary="Ficha completa del proveedor")
def perfil(sub_id: str, db: Session = Depends(get_db), _: User = Depends(requiere_capacidad("proveedores.ver"))):
    return APIResponse.ok(data=ficha.perfil(db, ficha.exigir(db, sub_id)))


@router.patch("/{sub_id}/classification", summary="Tipo, modos y datos de GRC de la ficha")
def clasificar(sub_id: str, payload: Clasificacion, db: Session = Depends(get_db), u: User = Depends(requiere_capacidad("proveedores.gestionar"))):
    return APIResponse.ok(data=ficha.clasificar(db, ficha.exigir(db, sub_id), _set(payload), u))


@router.post("/{sub_id}/suspend", summary="Suspender (sin trabajo nuevo, sin acceso de sus personas)")
def suspender(sub_id: str, payload: Motivo, db: Session = Depends(get_db), u: User = Depends(requiere_capacidad("proveedores.gestionar"))):
    return APIResponse.ok(data=ficha.suspender(db, ficha.exigir(db, sub_id), payload.reason, u))


@router.post("/{sub_id}/reactivate", summary="Reactivar")
def reactivar(sub_id: str, db: Session = Depends(get_db), u: User = Depends(requiere_capacidad("proveedores.gestionar"))):
    return APIResponse.ok(data=ficha.reactivar(db, ficha.exigir(db, sub_id), u))


@router.post("/{sub_id}/offboard", summary="Baja del proveedor (offboarding completo)")
def baja(sub_id: str, payload: Motivo, db: Session = Depends(get_db), u: User = Depends(requiere_capacidad("proveedores.gestionar"))):
    return APIResponse.ok(data=ficha.dar_de_baja(db, ficha.exigir(db, sub_id), payload.reason, u))


# ── Contratos y precios ──────────────────────────────────────────────────────

@router.get("/{sub_id}/contracts", summary="Contratos del proveedor")
def listar_contratos(sub_id: str, db: Session = Depends(get_db), _: User = Depends(requiere_capacidad("proveedores.ver"))):
    ficha.exigir(db, sub_id)
    items = contratos.listar(db, sub_id)
    return APIListResponse.ok(items=items, total=len(items))


@router.post("/{sub_id}/contracts", summary="Crear contrato", status_code=201)
def crear_contrato(sub_id: str, payload: ContratoIn, db: Session = Depends(get_db), u: User = Depends(requiere_capacidad("proveedores.gestionar"))):
    return APIResponse.ok(data=contratos.crear(db, ficha.exigir(db, sub_id), _set(payload), u))


@router.post("/{sub_id}/contracts/from-template/{tid}", summary="Contrato desde plantilla", status_code=201)
def desde_plantilla(sub_id: str, tid: str, db: Session = Depends(get_db), u: User = Depends(requiere_capacidad("proveedores.gestionar"))):
    return APIResponse.ok(data=contratos.desde_plantilla(db, ficha.exigir(db, sub_id), contratos.exigir(db, tid, True), u))


@router.patch("/contracts/{cid}", summary="Editar contrato")
def editar_contrato(cid: str, payload: ContratoIn, db: Session = Depends(get_db), u: User = Depends(requiere_capacidad("proveedores.gestionar"))):
    return APIResponse.ok(data=contratos.actualizar(db, contratos.exigir(db, cid), _set(payload), u))


@router.post("/contracts/{cid}/activate", summary="Activar contrato (exige requisitos de GRC)")
def activar_contrato(cid: str, db: Session = Depends(get_db), u: User = Depends(requiere_capacidad("proveedores.gestionar"))):
    return APIResponse.ok(data=contratos.activar(db, contratos.exigir(db, cid), u))


@router.post("/contracts/{cid}/terminate", summary="Terminar contrato")
def terminar_contrato(cid: str, db: Session = Depends(get_db), u: User = Depends(requiere_capacidad("proveedores.gestionar"))):
    return APIResponse.ok(data=contratos.terminar(db, contratos.exigir(db, cid), u))


@router.post("/contracts/{cid}/pricing", summary="Añadir línea de precio", status_code=201)
def crear_linea(cid: str, payload: LineaIn, db: Session = Depends(get_db), u: User = Depends(requiere_capacidad("proveedores.gestionar"))):
    c = contratos.exigir(db, cid, None)  # tambien plantillas
    if not c.is_template and c.status in ("terminated", "expired"):
        from app.core.codigos_de_error import error
        raise error(409, "proveedor_contrato_cerrado")
    return APIResponse.ok(data=contratos.crear_linea(db, c, _set(payload), u))


@router.post("/contract-templates/{tid}/pricing", summary="Añadir línea de precio a una plantilla", status_code=201)
def crear_linea_de_plantilla(tid: str, payload: LineaIn, db: Session = Depends(get_db), u: User = Depends(requiere_capacidad("proveedores.config"))):
    return APIResponse.ok(data=contratos.crear_linea(db, contratos.exigir(db, tid, True), _set(payload), u))


@router.patch("/pricing/{lid}", summary="Editar línea de precio")
def editar_linea(lid: str, payload: LineaIn, db: Session = Depends(get_db), u: User = Depends(requiere_capacidad("proveedores.gestionar"))):
    return APIResponse.ok(data=contratos.actualizar_linea(db, contratos.exigir_linea(db, lid), _set(payload), u))


@router.delete("/pricing/{lid}", summary="Quitar línea de precio")
def borrar_linea(lid: str, db: Session = Depends(get_db), u: User = Depends(requiere_capacidad("proveedores.gestionar"))):
    enforce_abac(db, u, "supplier_pricing_line", lid, action="delete")
    return APIResponse.ok(data=contratos.borrar_linea(db, contratos.exigir_linea(db, lid), u))


# ── Servicios gestionados ────────────────────────────────────────────────────

@router.get("/{sub_id}/services", summary="Servicios gestionados del proveedor")
def listar_servicios(sub_id: str, db: Session = Depends(get_db), _: User = Depends(requiere_capacidad("proveedores.ver"))):
    ficha.exigir(db, sub_id)
    items = servicios.listar(db, sub_id)
    return APIListResponse.ok(items=items, total=len(items))


@router.post("/{sub_id}/services", summary="Alta de servicio gestionado", status_code=201)
def crear_servicio(sub_id: str, payload: ServicioIn, db: Session = Depends(get_db), u: User = Depends(requiere_capacidad("proveedores.gestionar"))):
    return APIResponse.ok(data=servicios.crear(db, ficha.exigir(db, sub_id), _set(payload), u))


@router.patch("/services/{sid}", summary="Editar servicio")
def editar_servicio(sid: str, payload: ServicioIn, db: Session = Depends(get_db), u: User = Depends(requiere_capacidad("proveedores.gestionar"))):
    return APIResponse.ok(data=servicios.actualizar(db, servicios.exigir(db, sid), _set(payload), u))


@router.post("/services/{sid}/end", summary="Terminar servicio")
def terminar_servicio(sid: str, db: Session = Depends(get_db), u: User = Depends(requiere_capacidad("proveedores.gestionar"))):
    return APIResponse.ok(data=servicios.terminar(db, servicios.exigir(db, sid), u))


@router.post("/services/{sid}/metering/measure", summary="Medir ahora (fuente automática del servicio: CMDB)")
def medir_servicio(sid: str, db: Session = Depends(get_db), u: User = Depends(requiere_capacidad("proveedores.gestionar"))):
    return APIResponse.ok(data=medicion.medir_servicio(db, servicios.exigir(db, sid), u))


@router.post("/services/{sid}/metering/ingest", summary="Recuento de un sistema externo (SIEM, MDM…) por API",
             status_code=201)
def ingerir_recuento(sid: str, payload: RecuentoIn, db: Session = Depends(get_db), u: User = Depends(requiere_capacidad("proveedores.gestionar"))):
    enforce_abac(db, u, "supplier_service", sid, action="update")
    return APIResponse.ok(data=medicion.ingerir(db, servicios.exigir(db, sid), payload.model_dump(), u))


@router.post("/{sub_id}/metering/import", summary="Importar recuentos de un sistema externo (fila a fila)")
def importar_recuentos(sub_id: str, payload: ImportacionDeRecuentosIn, db: Session = Depends(get_db),
                       u: User = Depends(requiere_capacidad("proveedores.gestionar"))):
    enforce_abac(db, u, "supplier", sub_id, action="update")
    ficha.exigir(db, sub_id)
    return APIResponse.ok(data=medicion.importar(db, [f.model_dump() for f in payload.rows], u, sub_id))


@router.get("/services/{sid}/sla", summary="SLA del servicio en el periodo (su cola del service desk)")
def sla_del_servicio(sid: str, desde: Optional[date] = Query(None), hasta: Optional[date] = Query(None),
                     db: Session = Depends(get_db), _: User = Depends(requiere_capacidad("proveedores.ver"))):
    return APIResponse.ok(data=servicios.sla(db, servicios.exigir(db, sid), *_periodo(desde, hasta)))


# ── Paquetes de trabajo e informes ───────────────────────────────────────────

@router.get("/{sub_id}/work-packages", summary="Paquetes de trabajo externalizados")
def listar_paquetes(sub_id: str, db: Session = Depends(get_db), _: User = Depends(requiere_capacidad("proveedores.ver"))):
    ficha.exigir(db, sub_id)
    items = paquetes.listar(db, sub_id)
    return APIListResponse.ok(items=items, total=len(items))


@router.post("/{sub_id}/work-packages", summary="Externalizar trabajo (paquete)", status_code=201)
def crear_paquete(sub_id: str, payload: PaqueteIn, db: Session = Depends(get_db), u: User = Depends(requiere_capacidad("proveedores.gestionar"))):
    return APIResponse.ok(data=paquetes.crear(db, ficha.exigir(db, sub_id), _set(payload), u))


@router.patch("/work-packages/{wid}", summary="Editar paquete")
def editar_paquete(wid: str, payload: PaqueteIn, db: Session = Depends(get_db), u: User = Depends(requiere_capacidad("proveedores.gestionar"))):
    return APIResponse.ok(data=paquetes.actualizar(db, paquetes.exigir(db, wid), _set(payload), u))


@router.post("/work-packages/{wid}/tasks", summary="Externalizar tareas al paquete")
def tareas_del_paquete(wid: str, payload: TareasDelPaquete, db: Session = Depends(get_db), u: User = Depends(requiere_capacidad("proveedores.gestionar"))):
    return APIResponse.ok(data=paquetes.externalizar_tareas(db, paquetes.exigir(db, wid), payload.task_ids, u))


@router.post("/work-packages/{wid}/reject", summary="Rechazar la entrega")
def rechazar_paquete(wid: str, payload: Motivo, db: Session = Depends(get_db), u: User = Depends(requiere_capacidad("proveedores.gestionar"))):
    return APIResponse.ok(data=paquetes.transicion(db, paquetes.exigir(db, wid), "reject", u, payload.reason))


@router.post("/work-packages/{wid}/{accion}", summary="Iniciar, entregar, aceptar o cancelar el paquete")
def mover_paquete(wid: str, accion: str, db: Session = Depends(get_db), u: User = Depends(requiere_capacidad("proveedores.gestionar"))):
    return APIResponse.ok(data=paquetes.transicion(db, paquetes.exigir(db, wid), accion, u))


@router.get("/{sub_id}/reports", summary="Informes de avance y periódicos")
def listar_informes(sub_id: str, db: Session = Depends(get_db), _: User = Depends(requiere_capacidad("proveedores.ver"))):
    ficha.exigir(db, sub_id)
    items = paquetes.listar_informes(db, sub_id)
    return APIListResponse.ok(items=items, total=len(items))


@router.post("/{sub_id}/reports", summary="Registrar informe", status_code=201)
def crear_informe(sub_id: str, payload: InformeIn, db: Session = Depends(get_db), u: User = Depends(requiere_capacidad("proveedores.gestionar"))):
    return APIResponse.ok(data=paquetes.crear_informe(db, ficha.exigir(db, sub_id), _set(payload), u))


@router.post("/reports/{rid}/review", summary="Revisar informe")
def revisar_informe(rid: str, payload: RevisionIn, db: Session = Depends(get_db), u: User = Depends(requiere_capacidad("proveedores.gestionar"))):
    return APIResponse.ok(data=paquetes.revisar_informe(db, rid, payload.review_notes, u))


def _informe(db: Session, rid: str):
    return paquetes.informe_o_404(db, rid)


@router.post("/reports/{rid}/attachments", summary="Adjuntar evidencia a un informe", status_code=201)
def adjuntar_al_informe(rid: str, request: Request, file: UploadFile = File(...), db: Session = Depends(get_db),
                        u: User = Depends(requiere_capacidad("proveedores.gestionar"))):
    enforce_abac(db, u, "supplier_report", rid, action="update")
    r = _informe(db, rid)
    contenido = read_and_validate_upload_sync(file, UploadProfile.DOCUMENT)
    return APIResponse.ok(data=portal.guardar_adjunto(
        db, u, ficha.exigir(db, r.subcontractor_id), r, safe_filename(file.filename), file.content_type or "",
        contenido, ip_del_cliente(request), via="internal"))


@router.get("/reports/{rid}/attachments/{doc_id}/open", summary="Enlace firmado de un adjunto (auditado)")
def abrir_adjunto(rid: str, doc_id: str, request: Request, db: Session = Depends(get_db), u: User = Depends(requiere_capacidad("proveedores.ver"))):
    return APIResponse.ok(data=portal.abrir_adjunto(db, u, _informe(db, rid), doc_id,
                                                    ip_del_cliente(request)))


# ── Portal del proveedor: contactos ──────────────────────────────────────────

@router.get("/{sub_id}/portal-contacts", summary="Personas del proveedor y quién es contacto del portal")
def contactos_del_portal(sub_id: str, db: Session = Depends(get_db), _: User = Depends(requiere_capacidad("proveedores.gestionar"))):
    items = portal.contactos(db, ficha.exigir(db, sub_id))
    return APIListResponse.ok(items=items, total=len(items))


@router.put("/{sub_id}/portal-contacts/{worker_id}", summary="Dar o quitar el acceso al portal del proveedor")
def marcar_contacto(sub_id: str, worker_id: str, payload: ContactoDelPortalIn, db: Session = Depends(get_db),
                    u: User = Depends(requiere_capacidad("proveedores.gestionar"))):
    enforce_abac(db, u, "subcontractor_worker", worker_id, action="update")
    items = portal.marcar_contacto(db, ficha.exigir(db, sub_id), worker_id, payload.supplier_portal, u)
    return APIListResponse.ok(items=items, total=len(items))


# ── Consumo y facturación ────────────────────────────────────────────────────

@router.get("/{sub_id}/usage", summary="Consumo registrado")
def listar_consumo(sub_id: str, contract_id: Optional[str] = None, db: Session = Depends(get_db), _: User = Depends(requiere_capacidad("proveedores.gestionar"))):
    ficha.exigir(db, sub_id)
    items = consumo.listar(db, sub_id, contract_id)
    return APIListResponse.ok(items=items, total=len(items))


@router.post("/{sub_id}/usage", summary="Registrar consumo", status_code=201)
def registrar_consumo(sub_id: str, payload: ConsumoIn, db: Session = Depends(get_db), u: User = Depends(requiere_capacidad("proveedores.gestionar"))):
    return APIResponse.ok(data=consumo.registrar(db, ficha.exigir(db, sub_id), payload.model_dump(), u))


@router.delete("/usage/{uid}", summary="Borrar consumo registrado")
def borrar_consumo(uid: str, db: Session = Depends(get_db), u: User = Depends(requiere_capacidad("proveedores.gestionar"))):
    enforce_abac(db, u, "supplier_usage_record", uid, action="delete")
    return APIResponse.ok(data=consumo.borrar(db, uid, u))


@router.get("/contracts/{cid}/forecast", summary="Previsión de factura del periodo")
def prevision(cid: str, desde: Optional[date] = Query(None), hasta: Optional[date] = Query(None),
              db: Session = Depends(get_db), _: User = Depends(requiere_capacidad("proveedores.gestionar"))):
    return APIResponse.ok(data=facturacion.prever(db, contratos.exigir(db, cid), *_periodo(desde, hasta)))


@router.post("/contracts/{cid}/statements", summary="Cerrar periodo (estado de cuenta)", status_code=201)
def cerrar_periodo(cid: str, payload: PeriodoIn, db: Session = Depends(get_db), u: User = Depends(requiere_capacidad("proveedores.gestionar"))):
    return APIResponse.ok(data=facturacion.cerrar_periodo(db, contratos.exigir(db, cid), payload.period_start,
                                                          payload.period_end, u))


@router.get("/{sub_id}/statements", summary="Estados de cuenta")
def listar_estados(sub_id: str, db: Session = Depends(get_db), _: User = Depends(requiere_capacidad("proveedores.gestionar"))):
    ficha.exigir(db, sub_id)
    items = facturacion.listar(db, sub_id)
    return APIListResponse.ok(items=items, total=len(items))


@router.post("/statements/{stid}/reconcile", summary="Conciliar con la factura del proveedor")
def conciliar(stid: str, payload: ConciliarIn, db: Session = Depends(get_db), u: User = Depends(requiere_capacidad("proveedores.gestionar"))):
    return APIResponse.ok(data=facturacion.conciliar(db, facturacion.exigir_estado(db, stid), payload.invoice_id, u))


@router.post("/statements/{stid}/approve", summary="Aprobar: con flujo del motor (tipo supplier_statement) va a "
                                               "la bandeja; sin flujo, directo (segregación: no quien cerró "
                                               "ni quien registró)")
def aprobar(stid: str, db: Session = Depends(get_db), u: User = Depends(requiere_capacidad("proveedores.gestionar"))):
    return APIResponse.ok(data=facturacion.aprobar(db, facturacion.exigir_estado(db, stid), u))


@router.post("/statements/{stid}/dispute", summary="Disputar")
def disputar(stid: str, payload: Motivo, db: Session = Depends(get_db), u: User = Depends(requiere_capacidad("proveedores.gestionar"))):
    return APIResponse.ok(data=facturacion.disputar(db, facturacion.exigir_estado(db, stid), payload.reason, u))


# ── GRC de terceros ──────────────────────────────────────────────────────────

@router.get("/{sub_id}/compliance", summary="Cumplimiento del proveedor")
def cumplimiento(sub_id: str, db: Session = Depends(get_db), _: User = Depends(requiere_capacidad("proveedores.ver"))):
    return APIResponse.ok(data=grc.cumplimiento(db, ficha.exigir(db, sub_id)))


@router.post("/{sub_id}/documents", summary="Añadir documento o certificación", status_code=201)
def crear_documento(sub_id: str, payload: DocumentoIn, db: Session = Depends(get_db), u: User = Depends(requiere_capacidad("proveedores.gestionar"))):
    return APIResponse.ok(data=grc.crear_documento(db, ficha.exigir(db, sub_id), _set(payload), u))


@router.patch("/documents/{did}", summary="Editar documento")
def editar_documento(did: str, payload: DocumentoIn, db: Session = Depends(get_db), u: User = Depends(requiere_capacidad("proveedores.gestionar"))):
    return APIResponse.ok(data=grc.actualizar_documento(db, grc.exigir_documento(db, did), _set(payload), u))


@router.delete("/documents/{did}", summary="Retirar documento (se conserva la evidencia)")
def borrar_documento(did: str, db: Session = Depends(get_db), u: User = Depends(requiere_capacidad("proveedores.gestionar"))):
    enforce_abac(db, u, "supplier_document", did, action="delete")
    return APIResponse.ok(data=grc.borrar_documento(db, grc.exigir_documento(db, did), u))


@router.get("/{sub_id}/risk-assessments", summary="Evaluaciones de riesgo")
def listar_evaluaciones(sub_id: str, db: Session = Depends(get_db), _: User = Depends(requiere_capacidad("proveedores.ver"))):
    ficha.exigir(db, sub_id)
    items = grc.listar_evaluaciones(db, sub_id)
    return APIListResponse.ok(items=items, total=len(items))


@router.post("/{sub_id}/risk-assessments", summary="Evaluar riesgo y due diligence", status_code=201)
def evaluar(sub_id: str, payload: EvaluacionIn, db: Session = Depends(get_db), u: User = Depends(requiere_capacidad("proveedores.gestionar"))):
    return APIResponse.ok(data=grc.evaluar(db, ficha.exigir(db, sub_id), payload.model_dump(), u))


@router.post("/{sub_id}/access-grants", summary="Registrar acceso a sistemas o datos", status_code=201)
def conceder(sub_id: str, payload: AccesoIn, db: Session = Depends(get_db), u: User = Depends(requiere_capacidad("proveedores.gestionar"))):
    return APIResponse.ok(data=grc.conceder_acceso(db, ficha.exigir(db, sub_id), payload.model_dump(), u))


@router.post("/access-grants/{gid}/revoke", summary="Revocar acceso")
def revocar(gid: str, payload: Motivo, db: Session = Depends(get_db), u: User = Depends(requiere_capacidad("proveedores.gestionar"))):
    return APIResponse.ok(data=grc.revocar_acceso(db, gid, payload.reason, u))


@router.get("/{sub_id}/scorecard", summary="Cuadro de mando del proveedor")
def scorecard(sub_id: str, desde: Optional[date] = Query(None), hasta: Optional[date] = Query(None),
              db: Session = Depends(get_db), _: User = Depends(requiere_capacidad("proveedores.ver"))):
    return APIResponse.ok(data=rendimiento.cuadro(db, ficha.exigir(db, sub_id), desde, hasta))
