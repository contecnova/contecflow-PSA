"""
ALM — Asset & License Management endpoints
Enterprise-grade gestión de proveedores, contratos, licencias y activos.

Fases 1 y 3 de licencias y hardware (16-11-2026): asignación universal con
historial, ciclo de vida del hardware con actas firmadas, coste por titular y
día, renovaciones y conciliación con facturas y gastos.

Permisos (mínimo privilegio):

- gestores (`require_any_manager`): escribir, y leer lo económico o de
  terceros (contratos, panel, costes, facturas, renovaciones, historial,
  asignaciones, cumplimiento, claves);
- personal interno (`require_internal_user`, sin subcontratistas): los
  catálogos que usan los selectores (proveedores, licencias, activos);
- cualquiera con sesión: sus propias actas (`/me/acts`) y firmar la suya.
"""
from datetime import date
from typing import Optional

from fastapi import APIRouter, Body, Depends, File, Form, Query, Request, Response, UploadFile
from sqlalchemy.orm import Session

from app.core.abac_enforce import enforce_abac
from app.core.deps import get_current_user, require_any_manager, require_internal_user
from app.core.errores import ErrorDeDominio
from app.core.periodo import SIN_HORA, Periodo, periodo
from app.core.paginacion import Paginacion, lista_paginada, paginacion
from app.core.responses import APIListResponse, APIResponse
from app.db.session import get_db
from app.services import alm_actas, alm_asignaciones, alm_conciliacion, alm_costes, alm_renovaciones
from app.services.alm_ciclo_de_vida import (
    abrir_ticket_de_renovacion_confirmado, activo_o_404, activos_del_ci, historial, proximos_vencimientos,
    transicion,
)
from app.services.alm_service import (
    get_alm_dashboard,
    list_vendors_records, create_vendor_record, get_vendor_record,
    update_vendor_record, delete_vendor_record,
    list_contracts_records, create_contract_record, get_contract_record,
    update_contract_record, delete_contract_record,
    list_licenses_records, create_license_record, get_license_record,
    update_license_record, delete_license_record,
    assign_license_record, revoke_assignment_record,
    list_assets_records, create_asset_record, get_asset_record, serialize_asset,
    update_asset_record, delete_asset_record, assign_asset_record,
    list_cost_centers_records, create_cost_center_record,
    update_cost_center_record, delete_cost_center_record,
    add_install_record, remove_install_record,
    get_compliance_report,
)

router = APIRouter()

_GESTORES = {"admin", "pm", "team_lead", "hr"}


def _es_gestor(usuario) -> bool:
    return getattr(getattr(usuario, "role", None), "value", getattr(usuario, "role", None)) in _GESTORES


def _fecha_q(valor: Optional[str], defecto: date) -> date:
    if not valor:
        return defecto
    try:
        return date.fromisoformat(valor[:10])
    except ValueError:
        raise ErrorDeDominio(422, "alm_fecha_invalida")


# ── Dashboard / KPIs ──────────────────────────────────────────────────────────
@router.get("/dashboard", summary="KPIs del módulo ALM")
def alm_dashboard(db: Session = Depends(get_db), _=Depends(require_any_manager)):
    return APIResponse.ok(data=get_alm_dashboard(db))


@router.get("/config", summary="Ajustes de ALM que necesita la interfaz (checklist, días de préstamo)")
def alm_config(db: Session = Depends(get_db), cu=Depends(require_internal_user)):
    from app.services.alm_ajustes import ajuste_bool, ajuste_float, ajuste_int, ajuste_str
    org = getattr(cu, "organization_id", None)
    return APIResponse.ok(data={
        "checklist": alm_actas.checklist_de(db, org),
        "acts_enabled": ajuste_bool(db, "ALM_HANDOVER_ACT_ENABLED", org),
        "loan_default_days": ajuste_int(db, "ALM_LOAN_DEFAULT_DAYS", org),
        "rebill_markup_pct": ajuste_float(db, "ALM_REBILL_MARKUP_PCT", org),
        "esign_provider": ajuste_str(db, "ALM_ACT_ESIGN_PROVIDER", org),
    })


# ── Vendors ───────────────────────────────────────────────────────────────────
@router.get("/vendors")
def list_vendors(response: Response, q: Optional[str] = None, category: Optional[str] = None,
                 pagina: Paginacion = Depends(paginacion),
                 db: Session = Depends(get_db), _=Depends(require_internal_user)):
    return lista_paginada(response, list_vendors_records(q, category, db, pagina))

@router.post("/vendors")
def create_vendor(data: dict = Body(...), db: Session = Depends(get_db), _=Depends(require_any_manager)):
    return APIResponse.ok(data=create_vendor_record(data, db))

@router.get("/vendors/{vid}")
def get_vendor(vid: str, db: Session = Depends(get_db), _=Depends(require_internal_user)):
    return APIResponse.ok(data=get_vendor_record(vid, db))

@router.patch("/vendors/{vid}")
def update_vendor(vid: str, data: dict = Body(...), db: Session = Depends(get_db), _=Depends(require_any_manager)):
    return APIResponse.ok(data=update_vendor_record(vid, data, db))

@router.delete("/vendors/{vid}")
def delete_vendor(vid: str, db: Session = Depends(get_db), cu=Depends(require_any_manager)):
    enforce_abac(db, cu, "alm_vendor", vid, action="delete")
    return APIResponse.ok(data=delete_vendor_record(vid, db))


# ── Contracts ─────────────────────────────────────────────────────────────────
@router.get("/contracts")
def list_contracts(vendor_id: Optional[str] = None, status: Optional[str] = None,
                   expiring_days: Optional[int] = None, q: Optional[str] = None,
                   renewal_urgent: bool = False, response: Response = None,
                   pagina: Paginacion = Depends(paginacion),
                   # Personal interno: el detalle de un ticket elige el contrato UC del proveedor.
                   db: Session = Depends(get_db), _=Depends(require_internal_user)):
    return lista_paginada(response, list_contracts_records(
        vendor_id, status, expiring_days, db, pagina, q=q, renewal_urgent=renewal_urgent))

@router.post("/contracts")
def create_contract(data: dict = Body(...), db: Session = Depends(get_db), cu=Depends(require_any_manager)):
    return APIResponse.ok(data=create_contract_record(data, cu.id, db))

@router.get("/contracts/{cid}")
def get_contract(cid: str, db: Session = Depends(get_db), _=Depends(require_internal_user)):
    return APIResponse.ok(data=get_contract_record(cid, db))

@router.patch("/contracts/{cid}")
def update_contract(cid: str, data: dict = Body(...), db: Session = Depends(get_db), _=Depends(require_any_manager)):
    return APIResponse.ok(data=update_contract_record(cid, data, db))

@router.delete("/contracts/{cid}")
def delete_contract(cid: str, db: Session = Depends(get_db), cu=Depends(require_any_manager)):
    enforce_abac(db, cu, "alm_contract", cid, action="delete")
    return APIResponse.ok(data=delete_contract_record(cid, db))


# ── Licenses ──────────────────────────────────────────────────────────────────
@router.get("/licenses")
def list_licenses(vendor_id: Optional[str] = None, status: Optional[str] = None,
                  expiring_days: Optional[int] = None, compliance_only: bool = False,
                  q: Optional[str] = None, type: Optional[str] = None,
                  response: Response = None, pagina: Paginacion = Depends(paginacion),
                  db: Session = Depends(get_db), _=Depends(require_internal_user)):
    return lista_paginada(response, list_licenses_records(
        vendor_id, status, expiring_days, compliance_only, db, pagina, q=q, type=type))

@router.post("/licenses")
def create_license(data: dict = Body(...), db: Session = Depends(get_db), _=Depends(require_any_manager)):
    return APIResponse.ok(data=create_license_record(data, db))

@router.get("/licenses/{lid}")
def get_license(lid: str, db: Session = Depends(get_db), _=Depends(require_any_manager)):
    return APIResponse.ok(data=get_license_record(lid, db))

@router.patch("/licenses/{lid}")
def update_license(lid: str, data: dict = Body(...), db: Session = Depends(get_db), _=Depends(require_any_manager)):
    return APIResponse.ok(data=update_license_record(lid, data, db))

@router.delete("/licenses/{lid}")
def delete_license(lid: str, db: Session = Depends(get_db), cu=Depends(require_any_manager)):
    enforce_abac(db, cu, "alm_license", lid, action="delete")
    return APIResponse.ok(data=delete_license_record(lid, db))

@router.get("/licenses/{lid}/key", summary="Ver la clave de la licencia (queda en el historial)")
def get_license_key(lid: str, request: Request, db: Session = Depends(get_db), cu=Depends(require_any_manager)):
    from app.services.audit import audit_log
    lic = alm_asignaciones._licencia(db, lid)
    alm_asignaciones.registrar_evento(db, evento="key_viewed", resource_type="license", license_id=lic.id,
                                      actor_id=cu.id)
    audit_log(db, cu, "VIEW_FINANCIAL", "alm_license_key", lic.id, lic.name,
              ip_address=request.client.host if request.client else None)
    db.commit()
    return APIResponse.ok(data={"license_key": lic.license_key})

@router.get("/licenses/{lid}/usage", summary="Uso de la licencia (fase 2 si está; si no, asignaciones)")
def get_license_usage(lid: str, db: Session = Depends(get_db), _=Depends(require_any_manager)):
    return APIResponse.ok(data=alm_renovaciones.uso_de_licencia(db, lid))

@router.get("/licenses/{lid}/peaks", summary="Medidas de uso simultáneo")
def list_license_peaks(lid: str, db: Session = Depends(get_db), _=Depends(require_any_manager)):
    from app.models.alm import ALMPicoConcurrencia
    filas = (db.query(ALMPicoConcurrencia).filter(ALMPicoConcurrencia.license_id == lid)
             .order_by(ALMPicoConcurrencia.measured_at.desc()).limit(100).all())
    return APIListResponse.ok(items=[{"id": p.id, "peak": p.peak, "source": p.source,
                                      "measured_at": p.measured_at.isoformat()} for p in filas])

@router.post("/licenses/{lid}/peaks", summary="Anotar un pico de uso simultáneo")
def add_license_peak(lid: str, data: dict = Body(...), db: Session = Depends(get_db), cu=Depends(require_any_manager)):
    alm_asignaciones.registrar_pico(db, lid, data.get("peak"), fuente="manual", actor_id=cu.id)
    return APIResponse.ok(data=get_license_record(lid, db))


# ── Asignaciones (licencias y activos) ────────────────────────────────────────
@router.post("/licenses/{lid}/assign", summary="Asignar la licencia a una persona, equipo, proyecto, departamento o cliente")
def assign_license(lid: str, data: dict = Body(...), db: Session = Depends(get_db),
                   cu=Depends(require_any_manager)):
    return APIResponse.ok(data=assign_license_record(lid, data, cu, db))

@router.delete("/licenses/{lid}/assignments/{aid}", summary="Liberar una asignación (compatibilidad)")
def revoke_assignment(lid: str, aid: str, db: Session = Depends(get_db), cu=Depends(require_any_manager)):
    enforce_abac(db, cu, "alm_license_assignment", aid, action="delete")
    return APIResponse.ok(data=revoke_assignment_record(lid, aid, db, actor=cu))

@router.get("/assignments", summary="Asignaciones con filtros (recurso, titular, estado, préstamos vencidos)")
def list_assignments(response: Response, license_id: Optional[str] = None, asset_id: Optional[str] = None,
                     holder_type: Optional[str] = None, holder_id: Optional[str] = None,
                     status: Optional[str] = Query(None, description="CSV: pending,active,ended,rejected,cancelled"),
                     mode: Optional[str] = None, overdue: bool = False, resource_type: Optional[str] = None,
                     pagina: Paginacion = Depends(paginacion),
                     db: Session = Depends(get_db), _=Depends(require_any_manager)):
    estados = [e for e in (status or "").split(",") if e] or None
    return lista_paginada(response, alm_asignaciones.listar(
        db, license_id=license_id, asset_id=asset_id, holder_type=holder_type, holder_id=holder_id,
        status=estados, mode=mode, vencidos=overdue, resource_type=resource_type, pagina=pagina))

@router.post("/assignments/{aid}/end", summary="Cerrar una asignación: liberar o revocar (con motivo)")
def end_assignment(aid: str, data: dict = Body(default={}), db: Session = Depends(get_db),
                   cu=Depends(require_any_manager)):
    from app.services.audit import audit_log
    tipo = data.get("kind") or "released"
    if tipo not in ("released", "revoked"):
        raise ErrorDeDominio(422, "alm_fin_invalido")
    a = alm_asignaciones.liberar(db, aid, actor=cu, motivo=data.get("reason"), tipo=tipo)
    audit_log(db, cu, "UPDATE", "alm_assignment", a.id, None, new_values={"status": a.status, "end_kind": a.end_kind})
    db.commit()
    return APIResponse.ok(data=alm_asignaciones.serializar(db, a))

@router.post("/assignments/{aid}/return", summary="Devolver un activo (acta de devolución)")
def return_assignment(aid: str, data: dict = Body(default={}), db: Session = Depends(get_db),
                      cu=Depends(require_any_manager)):
    a = alm_asignaciones.devolver(db, aid, actor=cu, motivo=data.get("reason"), checklist=data.get("checklist"),
                                  condition=data.get("condition") or None, observations=data.get("observations"),
                                  a_reparar=bool(data.get("to_repair")))
    return APIResponse.ok(data=alm_asignaciones.serializar(db, a))

@router.get("/history", summary="Historial inmutable: quién tuvo qué, cuándo y por qué")
def list_history(response: Response, license_id: Optional[str] = None, asset_id: Optional[str] = None,
                 contract_id: Optional[str] = None, holder_type: Optional[str] = None,
                 holder_id: Optional[str] = None, pagina: Paginacion = Depends(paginacion),
                 db: Session = Depends(get_db), _=Depends(require_any_manager)):
    return lista_paginada(response, alm_asignaciones.historial(
        db, license_id=license_id, asset_id=asset_id, contract_id=contract_id, holder_type=holder_type,
        holder_id=holder_id, pagina=pagina))


# ── Assets ────────────────────────────────────────────────────────────────────
# Las rutas fijas van antes de `/assets/{aid}` para que no las capture.

@router.get("/assets/expiring", summary="Fechas de activos que vencen en los próximos días")
def list_expiring_assets(p: Periodo = Depends(periodo(dias_por_defecto=90, granularidades=SIN_HORA, serie=False,
                                                       sentido="futuro", alias_dias=("days",), dias_alias_max=730)),
                         db: Session = Depends(get_db), _=Depends(require_internal_user)):
    # Periodo libre (16-11-2026): horizonte hacia delante; fechas de calendario -> sin hora.
    return APIListResponse.ok(items=proximos_vencimientos(db, p=p))

@router.get("/assets/by-ci/{ci_id}", summary="Activos enlazados a un CI")
def list_assets_by_ci(ci_id: str, db: Session = Depends(get_db), _=Depends(require_internal_user)):
    return APIListResponse.ok(items=[serialize_asset(a) for a in activos_del_ci(db, ci_id)])

@router.get("/assets")
def list_assets(type: Optional[str] = None, status: Optional[str] = None,
                assigned_to: Optional[str] = None, q: Optional[str] = None,
                response: Response = None, pagina: Paginacion = Depends(paginacion),
                db: Session = Depends(get_db), _=Depends(require_internal_user)):
    return lista_paginada(response, list_assets_records(type, status, assigned_to, q, db, pagina))

@router.post("/assets")
def create_asset(data: dict = Body(...), db: Session = Depends(get_db), cu=Depends(require_any_manager)):
    return APIResponse.ok(data=create_asset_record(data, db, cu))

@router.get("/assets/{aid}")
def get_asset(aid: str, db: Session = Depends(get_db), _=Depends(require_internal_user)):
    return APIResponse.ok(data=get_asset_record(aid, db))

@router.patch("/assets/{aid}")
def update_asset(aid: str, data: dict = Body(...), db: Session = Depends(get_db), cu=Depends(require_any_manager)):
    return APIResponse.ok(data=update_asset_record(aid, data, db, cu))

@router.delete("/assets/{aid}")
def delete_asset(aid: str, db: Session = Depends(get_db), cu=Depends(require_any_manager)):
    enforce_abac(db, cu, "alm_asset", aid, action="delete")
    return APIResponse.ok(data=delete_asset_record(aid, db, cu))

@router.post("/assets/{aid}/assign", summary="Asignar o prestar el activo (con acta de entrega)")
def assign_asset(aid: str, data: dict = Body(...), db: Session = Depends(get_db),
                 cu=Depends(require_any_manager)):
    return APIResponse.ok(data=assign_asset_record(aid, data, db, cu))

@router.post("/assets/{aid}/lifecycle", summary="Paso del ciclo de vida: recibir, reparar, baja, reciclaje, pérdida...")
def asset_lifecycle(aid: str, data: dict = Body(...), db: Session = Depends(get_db),
                    cu=Depends(require_any_manager)):
    activo = transicion(db, aid, data.get("action") or "", cu, motivo=data.get("reason"), datos=data.get("data"))
    return APIResponse.ok(data=serialize_asset(activo))

@router.get("/assets/{aid}/history", summary="Historial de cambios del activo")
def get_asset_history(aid: str, db: Session = Depends(get_db), _=Depends(require_any_manager)):
    activo_o_404(db, aid)
    return APIListResponse.ok(items=historial(db, aid))

@router.post("/assets/{aid}/refresh-ticket", summary="Abrir (o recuperar) el ticket de renovación del activo")
def open_refresh_ticket(aid: str, db: Session = Depends(get_db), cu=Depends(require_any_manager)):
    return APIResponse.ok(data=abrir_ticket_de_renovacion_confirmado(db, aid, cu.id))

@router.get("/assets/{aid}/attachments", summary="Fotos y documentos del activo")
def list_asset_attachments(aid: str, db: Session = Depends(get_db), _=Depends(require_any_manager)):
    activo_o_404(db, aid)
    return APIListResponse.ok(items=alm_actas.adjuntos(db, asset_id=aid))

@router.post("/assets/{aid}/attachments", summary="Subir una foto o documento del activo")
def add_asset_attachment(aid: str, file: UploadFile = File(...), kind: str = Form("photo"),
                         db: Session = Depends(get_db), cu=Depends(require_any_manager)):
    from app.core.uploads import read_and_validate_upload_sync, safe_filename
    activo_o_404(db, aid)
    contenido = read_and_validate_upload_sync(file)
    adj = alm_actas.adjuntar(db, cu, contenido, safe_filename(file.filename), file.content_type or "application/octet-stream",
                             kind=kind, asset_id=aid)
    return APIResponse.ok(data={"id": adj.id, "document_id": adj.document_id})


# ── Actas ─────────────────────────────────────────────────────────────────────
@router.get("/acts", summary="Actas de entrega y devolución")
def list_acts(asset_id: Optional[str] = None, assignment_id: Optional[str] = None, status: Optional[str] = None,
              db: Session = Depends(get_db), _=Depends(require_any_manager)):
    return APIListResponse.ok(items=alm_actas.listar(db, asset_id=asset_id, assignment_id=assignment_id, status=status))

@router.get("/me/acts", summary="Mis actas (las que firmo yo)")
def list_my_acts(db: Session = Depends(get_db), cu=Depends(get_current_user)):
    return APIListResponse.ok(items=alm_actas.listar(db, signer_user_id=cu.id))

@router.get("/acts/{act_id}", summary="Detalle de un acta (gestores o la persona que firma)")
def get_act(act_id: str, db: Session = Depends(get_db), cu=Depends(get_current_user)):
    acta = alm_actas.acta_para(db, act_id, cu, _es_gestor(cu))
    return APIResponse.ok(data=alm_actas.serializar(db, acta))

@router.post("/acts/{act_id}/sign", summary="Firmar el acta en la aplicación (solo la persona del acta)")
def sign_act(act_id: str, request: Request, db: Session = Depends(get_db), cu=Depends(get_current_user)):
    acta = alm_actas.firmar(db, act_id, cu, ip=request.client.host if request.client else None)
    return APIResponse.ok(data=alm_actas.serializar(db, acta))

@router.post("/acts/{act_id}/regenerate", summary="Volver a generar el PDF o la solicitud de firma")
def regenerate_act(act_id: str, db: Session = Depends(get_db), cu=Depends(require_any_manager)):
    return APIResponse.ok(data=alm_actas.serializar(db, alm_actas.regenerar(db, act_id, cu)))

@router.post("/acts/{act_id}/void", summary="Anular un acta sin firmar")
def void_act(act_id: str, data: dict = Body(default={}), db: Session = Depends(get_db),
             cu=Depends(require_any_manager)):
    return APIResponse.ok(data=alm_actas.serializar(db, alm_actas.anular(db, act_id, cu, data.get("reason"))))

@router.post("/acts/{act_id}/attachments", summary="Subir una foto del estado al acta")
def add_act_attachment(act_id: str, file: UploadFile = File(...), kind: str = Form("photo"),
                       db: Session = Depends(get_db), cu=Depends(require_any_manager)):
    from app.core.uploads import read_and_validate_upload_sync, safe_filename
    contenido = read_and_validate_upload_sync(file)
    adj = alm_actas.adjuntar(db, cu, contenido, safe_filename(file.filename), file.content_type or "application/octet-stream",
                             kind=kind, act_id=act_id)
    return APIResponse.ok(data={"id": adj.id, "document_id": adj.document_id})


# ── Cost Centers ──────────────────────────────────────────────────────────────
@router.get("/cost-centers")
def list_cost_centers(db: Session = Depends(get_db), _=Depends(require_internal_user)):
    return APIListResponse.ok(items=list_cost_centers_records(db))

@router.post("/cost-centers")
def create_cost_center(data: dict = Body(...), db: Session = Depends(get_db), _=Depends(require_any_manager)):
    return APIResponse.ok(data=create_cost_center_record(data, db))

@router.patch("/cost-centers/{cid}")
def update_cost_center(cid: str, data: dict = Body(...), db: Session = Depends(get_db), _=Depends(require_any_manager)):
    return APIResponse.ok(data=update_cost_center_record(cid, data, db))

@router.delete("/cost-centers/{cid}")
def delete_cost_center(cid: str, db: Session = Depends(get_db), cu=Depends(require_any_manager)):
    enforce_abac(db, cu, "alm_cost_center", cid, action="delete")
    return APIResponse.ok(data=delete_cost_center_record(cid, db))


# ── Software Installs ─────────────────────────────────────────────────────────
@router.post("/assets/{aid}/installs")
def add_install(aid: str, data: dict = Body(...), db: Session = Depends(get_db), cu=Depends(require_any_manager)):
    return APIResponse.ok(data=add_install_record(aid, data, cu.id, db))

@router.delete("/assets/{aid}/installs/{iid}")
def remove_install(
    aid: str,
    iid: str,
    db: Session = Depends(get_db),
    cu=Depends(get_current_user),
    # Auditoria 2026-09: el unico control era `enforce_abac`, que sin
    # politicas activas no comprueba nada. `POST /alm/assets/{aid}/installs` ya exige
    # gestor; borrar la instalacion no puede pedir menos que crearla.
    _=Depends(require_any_manager),
):
    enforce_abac(db, cu, "alm_software_install", iid, action="delete")
    return APIResponse.ok(data=remove_install_record(aid, iid, db))


# ── Compliance report ─────────────────────────────────────────────────────────
@router.get("/compliance")
def compliance_report(db: Session = Depends(get_db), _=Depends(require_any_manager)):
    return APIResponse.ok(data=get_compliance_report(db))


# ── Costes (fase 3) ───────────────────────────────────────────────────────────
# Periodo libre (16-11-2026): costes por día de calendario -> sin hora; no son
# series. `from`/`to` (fechas incluidas) siguen valiendo; como `from` no puede
# ser nombre de parámetro de la dependencia común, se leen aquí. Sin nada, el
# mes en curso hasta hoy, como antes.
_PERIODO_COSTES = periodo(dias_por_defecto=30, granularidades=SIN_HORA, serie=False, alias_dias=("days",))


def _rango_de_costes(p: Periodo, date_from: Optional[str], date_to: Optional[str]) -> tuple[date, date]:
    if p.origen in ("rango", "days"):
        return p.fecha_desde, p.fecha_hasta
    from app.core import timeutil
    hasta = _fecha_q(date_to, timeutil.today())
    desde = _fecha_q(date_from, date(hasta.year, hasta.month, 1))
    if hasta < desde:
        raise ErrorDeDominio(422, "alm_fin_antes_de_inicio")
    return desde, hasta


@router.get("/costs", summary="Coste por titular y día, agrupado (titular, proyecto, centro, cliente, recurso)")
def costs(date_from: Optional[str] = Query(None, alias="from"), date_to: Optional[str] = Query(None, alias="to"),
          group_by: str = "holder", project_id: Optional[str] = None, currency: Optional[str] = None,
          p: Periodo = Depends(_PERIODO_COSTES),
          db: Session = Depends(get_db), _=Depends(require_any_manager)):
    desde, hasta = _rango_de_costes(p, date_from, date_to)
    return APIResponse.ok(data=alm_costes.resumen(db, desde, hasta, group_by, currency, project_id))

@router.get("/costs/rebillable", summary="Coste refacturable por cliente (con margen)")
def costs_rebillable(date_from: Optional[str] = Query(None, alias="from"), date_to: Optional[str] = Query(None, alias="to"),
                     currency: Optional[str] = None, p: Periodo = Depends(_PERIODO_COSTES),
                     db: Session = Depends(get_db), _=Depends(require_any_manager)):
    desde, hasta = _rango_de_costes(p, date_from, date_to)
    return APIResponse.ok(data=alm_costes.refacturable(db, desde, hasta, currency))


# ── Renovaciones (fase 3) ─────────────────────────────────────────────────────
@router.get("/renewals", summary="Contratos y licencias que renuevan pronto, con preaviso, decisión y uso")
def renewals(p: Periodo = Depends(periodo(dias_por_defecto=120, granularidades=SIN_HORA, serie=False,
                                          sentido="futuro", alias_dias=("days",), dias_alias_max=730)),
             db: Session = Depends(get_db), _=Depends(require_any_manager)):
    # Periodo libre (16-11-2026): horizonte hacia delante; fechas de calendario -> sin hora.
    return APIListResponse.ok(items=alm_renovaciones.proximas(db, p=p))

@router.post("/renewals", summary="Decidir la próxima renovación: renovar, reducir o cancelar")
def decide_renewal(data: dict = Body(...), db: Session = Depends(get_db), cu=Depends(require_any_manager)):
    return APIResponse.ok(data=alm_renovaciones.decidir(
        db, cu, data.get("entity_type") or "", data.get("entity_id") or "", data.get("decision") or "",
        new_seats=data.get("new_seats"), new_annual_cost=data.get("new_annual_cost"), reason=data.get("reason")))


# ── Facturas de proveedor y conciliación (fase 3) ─────────────────────────────
@router.get("/invoices")
def list_invoices(response: Response, status: Optional[str] = None, vendor_id: Optional[str] = None,
                  contract_id: Optional[str] = None, pagina: Paginacion = Depends(paginacion),
                  db: Session = Depends(get_db), _=Depends(require_any_manager)):
    return lista_paginada(response, alm_conciliacion.listar(db, status=status, vendor_id=vendor_id,
                                                            contract_id=contract_id, pagina=pagina))

@router.get("/invoices/missing", summary="Periodos de facturación sin factura")
def missing_invoices(months: int = Query(12, ge=1, le=36), db: Session = Depends(get_db),
                     _=Depends(require_any_manager)):
    return APIListResponse.ok(items=alm_conciliacion.periodos_sin_factura(db, months))

@router.post("/invoices")
def create_invoice(data: dict = Body(...), db: Session = Depends(get_db), cu=Depends(require_any_manager)):
    return APIResponse.ok(data=alm_conciliacion.crear(db, cu, data))

@router.patch("/invoices/{fid}")
def update_invoice(fid: str, data: dict = Body(...), db: Session = Depends(get_db), cu=Depends(require_any_manager)):
    return APIResponse.ok(data=alm_conciliacion.actualizar(db, cu, fid, data))

@router.delete("/invoices/{fid}")
def delete_invoice(fid: str, db: Session = Depends(get_db), cu=Depends(require_any_manager)):
    enforce_abac(db, cu, "alm_vendor_invoice", fid, action="delete")
    return APIResponse.ok(data=alm_conciliacion.borrar(db, fid))

@router.post("/invoices/{fid}/reconcile", summary="Volver a conciliar la factura")
def reconcile_invoice(fid: str, db: Session = Depends(get_db), cu=Depends(require_any_manager)):
    f = alm_conciliacion.conciliar(db, alm_conciliacion.factura(db, fid), cu)
    return APIResponse.ok(data=alm_conciliacion.serializar(db, f))

@router.get("/invoices/{fid}/candidates", summary="Gastos que pueden pagar la factura")
def invoice_candidates(fid: str, db: Session = Depends(get_db), _=Depends(require_any_manager)):
    return APIListResponse.ok(items=alm_conciliacion.candidatos(db, fid))

@router.post("/invoices/{fid}/expense", summary="Enlazar (o desenlazar) el gasto que paga la factura")
def link_invoice_expense(fid: str, data: dict = Body(...), db: Session = Depends(get_db),
                         cu=Depends(require_any_manager)):
    return APIResponse.ok(data=alm_conciliacion.vincular_gasto(db, cu, fid, data.get("expense_id")))

@router.post("/invoices/{fid}/accept", summary="Aceptar una discrepancia revisada (con nota)")
def accept_invoice(fid: str, data: dict = Body(...), db: Session = Depends(get_db), cu=Depends(require_any_manager)):
    return APIResponse.ok(data=alm_conciliacion.aceptar(db, cu, fid, data.get("note")))

@router.post("/invoices/{fid}/attachments", summary="Adjuntar el PDF de la factura")
def add_invoice_attachment(fid: str, file: UploadFile = File(...), db: Session = Depends(get_db),
                           cu=Depends(require_any_manager)):
    from app.core.uploads import read_and_validate_upload_sync, safe_filename
    alm_conciliacion.factura(db, fid)
    contenido = read_and_validate_upload_sync(file)
    adj = alm_actas.adjuntar(db, cu, contenido, safe_filename(file.filename), file.content_type or "application/octet-stream",
                             kind="invoice", invoice_id=fid)
    return APIResponse.ok(data={"id": adj.id, "document_id": adj.document_id})

@router.get("/invoices/{fid}/attachments")
def list_invoice_attachments(fid: str, db: Session = Depends(get_db), _=Depends(require_any_manager)):
    alm_conciliacion.factura(db, fid)
    return APIListResponse.ok(items=alm_actas.adjuntos(db, invoice_id=fid))
