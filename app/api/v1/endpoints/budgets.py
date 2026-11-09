"""Presupuestos por departamento y ejercicio.

Auditoria 2026-08 (hallazgo 22). Estas rutas vivian en
`app/api/v1/endpoints/mfa.py`, un fichero de 640 lineas con **38 rutas de ocho
dominios** —MFA, organizaciones, Slack, presupuestos, planificacion asistida,
escenarios, PDF y tokens de BI— servidas por un router llamado «mfa».

La mala ubicacion no fue solo desorden: el CRUD de organizaciones estaba
escondido ahi, y por eso nadie noto que a esos endpoints les faltaba la guarda de
superadministrador que su propio `summary` anunciaba. Fue la causa proxima del P0
numero 1 de la auditoria.

**Los paths no han cambiado.** ABAC y GRC derivan el modulo de la ruta, asi que
tocarlos alteraria los permisos en silencio.
"""
from datetime import date
from typing import Optional

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

import app.services.budgets_service as _budgets
from app.core.deps import require_any_manager
from app.core.responses import APIListResponse, APIResponse
from app.db.session import get_db
from app.models.user import User

router = APIRouter()

# Revisión 2026-11: presupuestos con partidas, real calculado, versiones y
# aprobación. Leer es de los responsables (`require_any_manager`); crear, editar
# y aprobar lo deciden `BUDGET_MANAGER_ROLES` y `BUDGET_APPROVER_ROLES` dentro
# del servicio. Ver `app/services/budgets_service.py`.


class PresupuestoIn(BaseModel):
    name: Optional[str] = Field(None, max_length=255)
    ambito: Optional[str] = Field(None, pattern="^(proyecto|proyecto_previsto|departamento|area)$")
    department: Optional[str] = Field(None, max_length=100)
    area: Optional[str] = Field(None, max_length=255)
    project_id: Optional[str] = None
    cliente_id: Optional[str] = None
    tipo_proyecto: Optional[str] = Field(None, max_length=30)
    periodo_desde: Optional[date] = None
    periodo_hasta: Optional[date] = None
    currency: Optional[str] = Field(None, max_length=3)
    notes: Optional[str] = None
    # Revisión 2026-11 (preparar a fondo)
    area_id: Optional[str] = None
    padre_id: Optional[str] = None
    techo: Optional[float] = Field(None, ge=0)
    responsable_id: Optional[str] = None
    campana_id: Optional[str] = None
    escenario: Optional[str] = Field(None, max_length=40)
    supuestos: Optional[dict] = None
    plantilla_id: Optional[str] = None
    copiar_de: Optional[str] = None
    base: Optional[str] = Field(None, pattern="^(plan|real)$")
    ajuste_pct: Optional[float] = Field(None, ge=-100, le=1000)


class PartidaIn(BaseModel):
    tipo: Optional[str] = Field(None, max_length=30)
    descripcion: Optional[str] = Field(None, max_length=500)
    user_id: Optional[str] = None
    perfil: Optional[str] = Field(None, max_length=120)
    horas: Optional[float] = Field(None, ge=0)
    coste_hora: Optional[float] = Field(None, ge=0)
    importe: Optional[float] = Field(None, ge=0)
    meses: Optional[dict[str, float]] = None
    sentido: Optional[str] = Field(None, pattern="^(gasto|ingreso)$")
    naturaleza: Optional[str] = Field(None, pattern="^(opex|capex)$")
    vida_meses: Optional[int] = Field(None, ge=1, le=600)
    unidades: Optional[float] = Field(None, ge=0)
    precio_unitario: Optional[float] = Field(None, ge=0)
    recurrencia: Optional[str] = Field(None, pattern="^(unica|mensual|trimestral|anual)$")
    mes_desde: Optional[str] = Field(None, pattern=r"^\d{4}-\d{2}$")
    mes_hasta: Optional[str] = Field(None, pattern=r"^\d{4}-\d{2}$")
    dedicacion_pct: Optional[float] = Field(None, gt=0, le=100)
    fecha_alta: Optional[date] = None
    pais: Optional[str] = Field(None, min_length=2, max_length=2)
    salario_anual: Optional[float] = Field(None, ge=0)
    justificacion: Optional[str] = Field(None, max_length=4000)


class DecisionIn(BaseModel):
    aprobado: bool
    motivo: Optional[str] = Field(None, max_length=2000)


class VinculoIn(BaseModel):
    project_id: str


@router.get("/budgets", summary="Presupuestos (última versión de cada uno) con plan, real y previsión")
def list_budgets(year: Optional[int] = None, ambito: Optional[str] = None, estado: Optional[str] = None,
                 db: Session = Depends(get_db), current_user: User = Depends(require_any_manager)):
    items = _budgets.listar(db, current_user, year=year, ambito=ambito, estado=estado)
    return APIListResponse.ok(items=items, total=len(items))


@router.get("/budgets/summary", summary="Resumen del ejercicio: plan, real y previsión por mes")
def budget_summary(year: Optional[int] = Query(default=None), db: Session = Depends(get_db),
                   current_user: User = Depends(require_any_manager)):
    return APIResponse.ok(data=_budgets.resumen(db, current_user, year))


@router.post("/budgets", summary="Crear presupuesto (proyecto, proyecto previsto, departamento o área)")
def create_budget(body: PresupuestoIn, db: Session = Depends(get_db), current_user: User = Depends(require_any_manager)):
    return APIResponse.ok(data=_budgets.crear(db, current_user, body.model_dump(exclude_unset=True)))


@router.get("/budgets/{budget_id}", summary="Ficha: partidas, seguimiento, versiones y aprobación")
def get_budget(budget_id: str, db: Session = Depends(get_db), current_user: User = Depends(require_any_manager)):
    return APIResponse.ok(data=_budgets.detalle(db, current_user, budget_id))


@router.patch("/budgets/{budget_id}", summary="Editar la cabecera (borrador o rechazado)")
def update_budget(budget_id: str, body: PresupuestoIn, db: Session = Depends(get_db),
                  current_user: User = Depends(require_any_manager)):
    return APIResponse.ok(data=_budgets.editar(db, current_user, budget_id, body.model_dump(exclude_unset=True)))


@router.post("/budgets/{budget_id}/lines", summary="Añadir una partida")
def add_line(budget_id: str, body: PartidaIn, db: Session = Depends(get_db),
             current_user: User = Depends(require_any_manager)):
    return APIResponse.ok(data=_budgets.crear_linea(db, current_user, budget_id, body.model_dump(exclude_unset=True)))


@router.patch("/budgets/{budget_id}/lines/{line_id}", summary="Editar una partida")
def update_line(budget_id: str, line_id: str, body: PartidaIn, db: Session = Depends(get_db),
                current_user: User = Depends(require_any_manager)):
    return APIResponse.ok(data=_budgets.editar_linea(db, current_user, budget_id, line_id,
                                                     body.model_dump(exclude_unset=True)))


@router.delete("/budgets/{budget_id}/lines/{line_id}", summary="Quitar una partida")
def delete_line(budget_id: str, line_id: str, db: Session = Depends(get_db),
                current_user: User = Depends(require_any_manager)):
    return APIResponse.ok(data=_budgets.borrar_linea(db, current_user, budget_id, line_id))


@router.post("/budgets/{budget_id}/submit", summary="Enviar a aprobación")
def submit_budget(budget_id: str, db: Session = Depends(get_db), current_user: User = Depends(require_any_manager)):
    return APIResponse.ok(data=_budgets.enviar(db, current_user, budget_id))


@router.post("/budgets/{budget_id}/decision", summary="Aprobar o rechazar (BUDGET_APPROVER_ROLES)")
def decide_budget(budget_id: str, body: DecisionIn, db: Session = Depends(get_db),
                  current_user: User = Depends(require_any_manager)):
    return APIResponse.ok(data=_budgets.decidir(db, current_user, budget_id, body.aprobado, body.motivo))


@router.post("/budgets/{budget_id}/new-version", summary="Reprevisión: versión nueva a partir de ésta")
def new_version(budget_id: str, db: Session = Depends(get_db), current_user: User = Depends(require_any_manager)):
    return APIResponse.ok(data=_budgets.nueva_version(db, current_user, budget_id))


@router.post("/budgets/{budget_id}/link-project", summary="Vincular un proyecto previsto al proyecto ya creado")
def link_project(budget_id: str, body: VinculoIn, db: Session = Depends(get_db),
                 current_user: User = Depends(require_any_manager)):
    return APIResponse.ok(data=_budgets.vincular_proyecto(db, current_user, budget_id, body.project_id))


# ── Preparar a fondo (revisión 2026-11) ──────────────────────────────────────

class EscenarioIn(BaseModel):
    nombre: str = Field(..., min_length=1, max_length=40)
    supuestos: Optional[dict] = None


class CompararIn(BaseModel):
    ids: list[str] = Field(..., min_length=2, max_length=6)


class PlantillaIn(BaseModel):
    nombre: Optional[str] = Field(None, max_length=200)
    ambito: Optional[str] = Field(None, pattern="^(proyecto|proyecto_previsto|departamento|area)$")
    tipo_proyecto: Optional[str] = Field(None, max_length=30)
    partidas: Optional[list[dict]] = None
    desde_presupuesto: Optional[str] = None


class CampanaIn(BaseModel):
    nombre: Optional[str] = Field(None, max_length=200)
    year: Optional[int] = Field(None, ge=2000, le=2100)
    fecha_limite: Optional[date] = None
    abierta: Optional[bool] = None
    instrucciones: Optional[str] = Field(None, max_length=4000)


@router.post("/budgets/{budget_id}/scenario", summary="Otro escenario (optimista, pesimista…) con sus supuestos")
def new_scenario(budget_id: str, body: EscenarioIn, db: Session = Depends(get_db),
                 current_user: User = Depends(require_any_manager)):
    return APIResponse.ok(data=_budgets.crear_escenario(db, current_user, budget_id, body.nombre, body.supuestos))


@router.post("/budgets/compare", summary="Comparar versiones o escenarios: gasto, ingreso y margen por tipo y mes")
def compare_budgets(body: CompararIn, db: Session = Depends(get_db), current_user: User = Depends(require_any_manager)):
    from app.services.presupuestos_preparar import comparar
    return APIResponse.ok(data=comparar(db, body.ids))


@router.get("/budget-templates", summary="Plantillas de presupuesto")
def list_templates(db: Session = Depends(get_db), current_user: User = Depends(require_any_manager)):
    items = _budgets.listar_plantillas(db, current_user)
    return APIListResponse.ok(items=items, total=len(items))


@router.post("/budget-templates", summary="Crear plantilla (o guardar un presupuesto como plantilla)")
def create_template(body: PlantillaIn, db: Session = Depends(get_db), current_user: User = Depends(require_any_manager)):
    return APIResponse.ok(data=_budgets.guardar_plantilla(db, current_user, body.model_dump(exclude_unset=True)))


@router.patch("/budget-templates/{template_id}", summary="Editar plantilla")
def update_template(template_id: str, body: PlantillaIn, db: Session = Depends(get_db),
                    current_user: User = Depends(require_any_manager)):
    return APIResponse.ok(data=_budgets.guardar_plantilla(db, current_user, body.model_dump(exclude_unset=True), template_id))


@router.delete("/budget-templates/{template_id}", summary="Borrar plantilla")
def delete_template(template_id: str, db: Session = Depends(get_db), current_user: User = Depends(require_any_manager)):
    return APIResponse.ok(data=_budgets.borrar_plantilla(db, current_user, template_id))


@router.get("/budget-campaigns", summary="Campañas de presupuestos con su avance")
def list_campaigns(db: Session = Depends(get_db), current_user: User = Depends(require_any_manager)):
    items = _budgets.listar_campanas(db, current_user)
    return APIListResponse.ok(items=items, total=len(items))


@router.post("/budget-campaigns", summary="Abrir campaña (BUDGET_APPROVER_ROLES)")
def create_campaign(body: CampanaIn, db: Session = Depends(get_db), current_user: User = Depends(require_any_manager)):
    return APIResponse.ok(data=_budgets.guardar_campana(db, current_user, body.model_dump(exclude_unset=True)))


@router.patch("/budget-campaigns/{campaign_id}", summary="Editar o cerrar campaña (BUDGET_APPROVER_ROLES)")
def update_campaign(campaign_id: str, body: CampanaIn, db: Session = Depends(get_db),
                    current_user: User = Depends(require_any_manager)):
    return APIResponse.ok(data=_budgets.guardar_campana(db, current_user, body.model_dump(exclude_unset=True), campaign_id))
