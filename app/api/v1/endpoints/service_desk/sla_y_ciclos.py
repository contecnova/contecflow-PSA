"""SLA condicionales, OLA por prioridad y ciclos de vida por tipo de ticket
(mejoras de mercado 16-11-2026, migracion 174).

Leer es del equipo (usuario interno); cambiar, de administrador. Todo se acota
a la empresa de quien llama y queda en la auditoria.
"""
from typing import Optional

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.core.deps import require_admin, require_internal_user, require_worker
from app.core.responses import APIListResponse, APIResponse
from app.db.session import get_db
from app.models.user import User
from app.services.audit import auditar_y_confirmar
from app.services.service_desk import ciclos_de_vida, reglas_sla
from app.services.service_desk.scoping import get_scoped_ticket_or_404

router = APIRouter(tags=["Service Desk - SLA condicionales y ciclos de vida"])


def _org(u: User):
    return getattr(u, "organization_id", None)


class ReglaIn(BaseModel):
    name: str = Field(..., min_length=2, max_length=150)
    is_active: bool = True
    sort_order: int = Field(0, ge=0, le=10000)
    service_item_id: Optional[str] = None
    ticket_type: Optional[str] = None
    client_id: Optional[str] = None
    contract_id: Optional[str] = None
    priority: Optional[str] = None
    response_hours: Optional[float] = Field(None, gt=0, le=8760)
    resolution_hours: Optional[float] = Field(None, gt=0, le=8760)
    sla_policy_id: Optional[str] = None


class OlaIn(BaseModel):
    # {prioridad: horas | null}; null quita el objetivo de esa prioridad
    targets: dict[str, Optional[float]]


class EstadoIn(BaseModel):
    key: str = Field(..., min_length=1, max_length=50, pattern=r"^[a-z0-9_]+$")
    label: str = Field(..., min_length=1, max_length=100)
    base_status: str
    is_initial: bool = False
    color: Optional[str] = Field(None, max_length=30)


class TransicionIn(BaseModel):
    from_key: str
    to_key: str


class CicloIn(BaseModel):
    ticket_type: str
    name: str = Field(..., min_length=2, max_length=150)
    is_active: bool = True
    restrict_transitions: bool = False
    states: list[EstadoIn] = Field(..., min_length=1, max_length=40)
    transitions: list[TransicionIn] = []


# ── SLA condicionales ─────────────────────────────────────────────────────────

@router.get("/sla-rules", summary="Reglas de SLA condicionales de la empresa")
def list_rules(db: Session = Depends(get_db), current_user: User = Depends(require_internal_user)):
    return APIListResponse.ok(items=reglas_sla.listar_reglas(db, _org(current_user)))


@router.post("/sla-rules", summary="Crear regla de SLA condicional", status_code=201)
def create_rule(payload: ReglaIn, db: Session = Depends(get_db), current_user: User = Depends(require_admin)):
    r = reglas_sla.guardar_regla(db, _org(current_user), payload.model_dump())
    auditar_y_confirmar(db, current_user, "CREATE", "sd_sla_rule", r["id"], r["name"], new_values=r)
    return APIResponse.ok(data=r)


@router.put("/sla-rules/{rule_id}", summary="Cambiar regla de SLA condicional")
def update_rule(rule_id: str, payload: ReglaIn, db: Session = Depends(get_db),
                current_user: User = Depends(require_admin)):
    r = reglas_sla.guardar_regla(db, _org(current_user), payload.model_dump(), rule_id)
    auditar_y_confirmar(db, current_user, "UPDATE", "sd_sla_rule", rule_id, r["name"], new_values=r)
    return APIResponse.ok(data=r)


@router.delete("/sla-rules/{rule_id}", summary="Borrar regla de SLA condicional")
def delete_rule(rule_id: str, db: Session = Depends(get_db), current_user: User = Depends(require_admin)):
    reglas_sla.borrar_regla(db, _org(current_user), rule_id)
    auditar_y_confirmar(db, current_user, "DELETE", "sd_sla_rule", rule_id)
    return APIResponse.ok(data={"ok": True})


# ── OLA por prioridad ─────────────────────────────────────────────────────────

@router.get("/groups/{group_id}/ola-targets", summary="OLA de la cola por prioridad")
def get_ola(group_id: str, db: Session = Depends(get_db), current_user: User = Depends(require_internal_user)):
    return APIResponse.ok(data=reglas_sla.ola_de_la_cola(db, _org(current_user), group_id))


@router.put("/groups/{group_id}/ola-targets", summary="Fijar el OLA de la cola por prioridad")
def put_ola(group_id: str, payload: OlaIn, db: Session = Depends(get_db), current_user: User = Depends(require_admin)):
    r = reglas_sla.guardar_ola(db, _org(current_user), group_id, payload.targets)
    auditar_y_confirmar(db, current_user, "UPDATE", "sd_ola_targets", group_id, new_values=r["targets"])
    return APIResponse.ok(data=r)


# ── Ciclos de vida ────────────────────────────────────────────────────────────

@router.get("/lifecycles", summary="Ciclos de vida por tipo de ticket")
def list_lifecycles(db: Session = Depends(get_db), current_user: User = Depends(require_internal_user)):
    return APIListResponse.ok(items=ciclos_de_vida.listar(db, _org(current_user)))


@router.put("/lifecycles", summary="Crear o sustituir el ciclo de vida de un tipo de ticket")
def put_lifecycle(payload: CicloIn, db: Session = Depends(get_db), current_user: User = Depends(require_admin)):
    r = ciclos_de_vida.guardar(db, _org(current_user), payload.model_dump())
    auditar_y_confirmar(db, current_user, "UPDATE", "sd_ticket_lifecycle", r["id"], r["name"], new_values=r)
    return APIResponse.ok(data=r)


@router.delete("/lifecycles/{lifecycle_id}", summary="Borrar un ciclo de vida (el tipo vuelve a los estados base)")
def delete_lifecycle(lifecycle_id: str, db: Session = Depends(get_db), current_user: User = Depends(require_admin)):
    ciclos_de_vida.borrar(db, _org(current_user), lifecycle_id)
    auditar_y_confirmar(db, current_user, "DELETE", "sd_ticket_lifecycle", lifecycle_id)
    return APIResponse.ok(data={"ok": True})


@router.get("/tickets/{ticket_id}/lifecycle", summary="Estados a los que puede pasar el ticket")
def ticket_lifecycle(ticket_id: str, db: Session = Depends(get_db), current_user: User = Depends(require_worker)):
    # Externos como internos (16-11-2026): solo de un ticket de su alcance (`get_scoped_ticket_or_404`).
    ticket = get_scoped_ticket_or_404(db, current_user, ticket_id)
    return APIResponse.ok(data=ciclos_de_vida.opciones_del_ticket(db, ticket))
