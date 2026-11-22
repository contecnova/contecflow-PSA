"""Índice de riesgo y gestión de vulnerabilidades — `/api/v1/cmdb/software/risk/*` (22-11-2026).

Diseño: `docs/CMDB_SOFTWARE_Y_VULNERABILIDADES.md`, §11. Servicios:
`app/services/cmdb_software/riesgo/`.

Guardas (como el resto de la CMDB de software, `app/core/capacidades.py`):
leer, `software.ver` (`require_admin_or_pm`); escribir (recalcular, controles,
importaciones, vistas, informes, exposición), `software.gestionar`
(`require_admin_or_pm`); pesos y avisos, `software.config` (`require_admin`).
Todo cambio se audita en el servicio; la API confirma.
"""
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, File, Form, Query, UploadFile
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.core.deps import require_admin, require_admin_or_pm
from app.core.responses import APIListResponse, APIResponse
from app.db.session import get_db
from app.models.user import User
from app.services.cmdb_software import importacion
from app.services.cmdb_software.riesgo import ajustes as aj
from app.services.cmdb_software.riesgo import calculo, controles, informes, metricas, terceros

router = APIRouter()


class Datos(BaseModel):
    model_config = {"extra": "allow"}


def _d(p: Optional[Datos]) -> dict:
    return p.model_dump(exclude_unset=True) if p is not None else {}


def _org(u: User) -> Optional[str]:
    return u.organization_id


def _confirmar(db: Session) -> None:
    try:
        db.commit()
    except Exception:
        db.rollback()
        raise


async def _leer(fichero: UploadFile) -> bytes:
    contenido = await fichero.read(importacion.TAMANO_MAXIMO_MB * 1024 * 1024 + 1)
    importacion.comprobar_fichero(contenido)
    return contenido


def _bool(v: Optional[str], defecto: bool) -> bool:
    if v is None or v == "":
        return defecto
    return str(v).lower() in ("1", "true", "yes", "si", "sí", "on")


@router.get("/meta", summary="Valores del índice de riesgo (ámbitos, factores, controles, superficies, fuentes)")
def meta(current_user: User = Depends(require_admin_or_pm)):
    from app.services.cmdb_software.escaneos import TIPOS_TERCEROS
    return APIResponse.ok(data={
        "scope_types": calculo.AMBITOS, "factors": aj.FACTORES, "control_types": controles.TIPOS,
        "control_reductions": aj.REDUCCION_POR_TIPO, "surfaces": metricas.SUPERFICIES, "sources": terceros.FUENTES,
        "connector_types": TIPOS_TERCEROS, "report_types": informes.TIPOS, "frequencies": informes.FRECUENCIAS,
        "alert_kinds": ("kev_new", "index_above", "sla_due_days"), "exploit_actions": controles.ACCIONES,
        "event_kinds": calculo.TIPOS_DE_EVENTO, "columns": metricas.COLUMNAS, "roles": aj.ROLES})


# ── Índice ───────────────────────────────────────────────────────────────────

@router.get("/index", summary="Índice de riesgo (0-100) de un ámbito, con su desglose")
def get_index(scope_type: str = "org", scope_id: Optional[str] = None, db: Session = Depends(get_db),
              current_user: User = Depends(require_admin_or_pm)):
    return APIResponse.ok(data=calculo.indice_de_ambito(db, _org(current_user), scope_type, scope_id))


@router.get("/history", summary="Histórico diario del índice de un ámbito")
def get_history(scope_type: str = "org", scope_id: Optional[str] = None, days: int = Query(90, ge=1, le=3650),
                db: Session = Depends(get_db), current_user: User = Depends(require_admin_or_pm)):
    return APIListResponse.ok(items=calculo.historico(db, _org(current_user), scope_type, scope_id, days))


@router.get("/compare", summary="Comparar el índice entre clientes, unidades, servicios, máquinas o aplicaciones")
def compare(scope_type: str = "client", internal: Optional[bool] = None, limit: int = Query(50, ge=1, le=1000),
            db: Session = Depends(get_db), current_user: User = Depends(require_admin_or_pm)):
    return APIListResponse.ok(items=calculo.comparar(db, _org(current_user), scope_type, internal, limit))


@router.post("/recalculate", summary="Recalcular el índice de todos los ámbitos y guardar la foto del día")
def recalculate(db: Session = Depends(get_db), current_user: User = Depends(require_admin_or_pm)):
    r = calculo.recalcular(db, _org(current_user), current_user)
    _confirmar(db)
    return APIResponse.ok(data=r)


@router.get("/plan", summary="Plan de reducción de riesgo: de X a Y, ordenado por impacto")
def get_plan(scope_type: str = "org", scope_id: Optional[str] = None, target: Optional[float] = None,
             db: Session = Depends(get_db), current_user: User = Depends(require_admin_or_pm)):
    return APIResponse.ok(data=calculo.plan(db, _org(current_user), scope_type, scope_id, target))


@router.get("/events", summary="Todos los eventos de riesgo de un ámbito")
def get_events(scope_type: str = "org", scope_id: Optional[str] = None, kind: Optional[str] = None,
               page: int = Query(1, ge=1), page_size: int = Query(50, ge=1, le=500), db: Session = Depends(get_db),
               current_user: User = Depends(require_admin_or_pm)):
    r = calculo.eventos(db, _org(current_user), scope_type, scope_id, kind, page, page_size)
    return APIListResponse.ok(items=r["items"], total=r["total"], page=page, page_size=page_size)


# ── Métricas, superficies y vistas ───────────────────────────────────────────

@router.get("/metrics", summary="Métricas de gestión de vulnerabilidades")
def get_metrics(scope_type: str = "org", scope_id: Optional[str] = None, days: int = Query(90, ge=1, le=3650),
                db: Session = Depends(get_db), current_user: User = Depends(require_admin_or_pm)):
    return APIResponse.ok(data=metricas.metricas(db, _org(current_user), scope_type, scope_id, days))


@router.get("/surfaces", summary="Activos y hallazgos por superficie")
def get_surfaces(db: Session = Depends(get_db), current_user: User = Depends(require_admin_or_pm)):
    return APIResponse.ok(data=metricas.superficies(db, _org(current_user)))


@router.get("/findings", summary="Hallazgos por superficie, agrupables por CVE o por activo")
def get_findings(surface: Optional[str] = None, group_by: Optional[str] = None, severity: Optional[str] = None,
                 status: Optional[str] = None, q: Optional[str] = None, kev: Optional[bool] = None,
                 page: int = Query(1, ge=1), page_size: int = Query(50, ge=1, le=500), db: Session = Depends(get_db),
                 current_user: User = Depends(require_admin_or_pm)):
    agrupar = None if group_by in (None, "", "none") else group_by
    r = metricas.hallazgos(db, _org(current_user), surface, agrupar, severity, status, q, kev, page, page_size)
    return APIListResponse.ok(items=r["items"], total=r["total"], page=page, page_size=page_size)


@router.get("/views", summary="Vistas guardadas (propias y compartidas)")
def list_views(db: Session = Depends(get_db), current_user: User = Depends(require_admin_or_pm)):
    return APIListResponse.ok(items=metricas.vistas(db, _org(current_user), current_user))


@router.post("/views", summary="Guardar una vista", status_code=201)
def create_view(payload: Datos, db: Session = Depends(get_db), current_user: User = Depends(require_admin_or_pm)):
    r = metricas.crear_vista(db, _org(current_user), _d(payload), current_user)
    _confirmar(db)
    return APIResponse.ok(data=r)


@router.patch("/views/{view_id}", summary="Cambiar una vista propia")
def update_view(view_id: str, payload: Datos, db: Session = Depends(get_db),
                current_user: User = Depends(require_admin_or_pm)):
    r = metricas.cambiar_vista(db, _org(current_user), view_id, _d(payload), current_user)
    _confirmar(db)
    return APIResponse.ok(data=r)


@router.delete("/views/{view_id}", summary="Borrar una vista propia")
def delete_view(view_id: str, db: Session = Depends(get_db), current_user: User = Depends(require_admin_or_pm)):
    metricas.borrar_vista(db, _org(current_user), view_id, current_user)
    _confirmar(db)
    return APIResponse.ok(data={"ok": True})


@router.post("/exposure/detect", summary="Detectar exposición a Internet (puertos públicos en IP pública)")
def detect_exposure(db: Session = Depends(get_db), current_user: User = Depends(require_admin_or_pm)):
    r = metricas.detectar_exposicion(db, _org(current_user), current_user)
    _confirmar(db)
    return APIResponse.ok(data=r)


@router.put("/exposure/ci/{ci_id}", summary="Marcar la exposición de un elemento de la CMDB")
def set_ci_exposure(ci_id: str, payload: Datos, db: Session = Depends(get_db),
                    current_user: User = Depends(require_admin_or_pm)):
    r = metricas.marcar_ci(db, _org(current_user), ci_id, _d(payload).get("exposure"), current_user)
    _confirmar(db)
    return APIResponse.ok(data=r)


# ── Controles compensatorios e intentos de explotación ───────────────────────

@router.get("/controls", summary="Controles compensatorios")
def list_controls(status: Optional[str] = None, finding_id: Optional[str] = None, db: Session = Depends(get_db),
                  current_user: User = Depends(require_admin_or_pm)):
    return APIListResponse.ok(items=controles.listar(db, _org(current_user), status, finding_id))


@router.post("/controls", summary="Registrar un control compensatorio sobre uno o varios hallazgos", status_code=201)
def create_controls(payload: Datos, db: Session = Depends(get_db), current_user: User = Depends(require_admin_or_pm)):
    creados = controles.crear(db, _org(current_user), _d(payload), current_user)
    _confirmar(db)
    return APIListResponse.ok(items=[controles.serializar(db, c) for c in creados])


@router.post("/controls/{control_id}/revoke", summary="Revocar un control compensatorio")
def revoke_control(control_id: str, payload: Optional[Datos] = None, db: Session = Depends(get_db),
                   current_user: User = Depends(require_admin_or_pm)):
    c = controles.revocar(db, _org(current_user), control_id, _d(payload).get("reason"), current_user)
    _confirmar(db)
    return APIResponse.ok(data=controles.serializar(db, c))


@router.get("/exploits", summary="Intentos de explotación importados")
def list_exploits(days: int = Query(30, ge=1, le=3650), page: int = Query(1, ge=1),
                  page_size: int = Query(50, ge=1, le=500), db: Session = Depends(get_db),
                  current_user: User = Depends(require_admin_or_pm)):
    r = controles.listar_eventos(db, _org(current_user), days, page, page_size)
    return APIListResponse.ok(items=r["items"], total=r["total"], page=page, page_size=page_size)


@router.post("/exploits/import", summary="Importar intentos de explotación (CSV o JSON de un SIEM/EDR)")
async def import_exploits(file: UploadFile = File(...), db: Session = Depends(get_db),
                          current_user: User = Depends(require_admin_or_pm)):
    contenido = await _leer(file)
    r = controles.importar_eventos(db, _org(current_user), contenido, current_user)
    _confirmar(db)
    return APIResponse.ok(data=r)


# ── Importación de terceros ──────────────────────────────────────────────────

@router.post("/import/file", summary="Importar vulnerabilidades de Trend Vision One, Defender, Qualys, Tenable, "
                                     "Rapid7 o CSV")
async def import_file(file: UploadFile = File(...), source: str = Form(...), create_cis: Optional[str] = Form(None),
                      complete: Optional[str] = Form(None), db: Session = Depends(get_db),
                      current_user: User = Depends(require_admin_or_pm)):
    contenido = await _leer(file)
    r = terceros.importar_fichero(db, _org(current_user), source, contenido, _bool(create_cis, True),
                                  _bool(complete, False), current_user)
    _confirmar(db)
    return APIResponse.ok(data=r)


# ── Ajustes ──────────────────────────────────────────────────────────────────

@router.get("/settings", summary="Pesos, constantes, rangos, objetivo y avisos del índice")
def get_settings(db: Session = Depends(get_db), current_user: User = Depends(require_admin_or_pm)):
    return APIResponse.ok(data=aj.con_defectos(db, _org(current_user)))


@router.put("/settings", summary="Guardar los ajustes del índice (validados y auditados)")
def put_settings(payload: Datos, db: Session = Depends(get_db), current_user: User = Depends(require_admin)):
    r = aj.guardar(db, _org(current_user), _d(payload), current_user)
    _confirmar(db)
    return APIResponse.ok(data=r)


# ── Informes programados ─────────────────────────────────────────────────────

@router.get("/reports", summary="Informes programados de riesgo y vulnerabilidades")
def list_reports(db: Session = Depends(get_db), current_user: User = Depends(require_admin_or_pm)):
    return APIListResponse.ok(items=informes.listar(db, _org(current_user)))


@router.post("/reports", summary="Programar un informe de riesgo", status_code=201)
def create_report(payload: Datos, db: Session = Depends(get_db), current_user: User = Depends(require_admin_or_pm)):
    r = informes.crear(db, _org(current_user), _d(payload), current_user)
    _confirmar(db)
    return APIResponse.ok(data=r)


@router.patch("/reports/{report_id}", summary="Cambiar un informe de riesgo")
def update_report(report_id: str, payload: Datos, db: Session = Depends(get_db),
                  current_user: User = Depends(require_admin_or_pm)):
    r = informes.cambiar(db, _org(current_user), report_id, _d(payload), current_user)
    _confirmar(db)
    return APIResponse.ok(data=r)


@router.delete("/reports/{report_id}", summary="Borrar un informe de riesgo")
def delete_report(report_id: str, db: Session = Depends(get_db), current_user: User = Depends(require_admin_or_pm)):
    informes.borrar(db, _org(current_user), report_id, current_user)
    _confirmar(db)
    return APIResponse.ok(data={"ok": True})


@router.post("/reports/{report_id}/run", summary="Enviar ahora un informe de riesgo")
def run_report(report_id: str, db: Session = Depends(get_db), current_user: User = Depends(require_admin_or_pm)):
    r = informes.enviar_ahora(db, _org(current_user), report_id, current_user)
    _confirmar(db)
    return APIResponse.ok(data=r)
