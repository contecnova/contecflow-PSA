"""Service Desk — Autonomous Agents REST API.

Bot-driven ticket resolution, playbook management, and execution audit log.

Mejoras de mercado (16-11-2026): todo se acota a la empresa de quien llama
(antes los playbooks, el registro y las estadisticas eran de toda la
instalacion y `/scan` lo lanzaba cualquier usuario sobre todas las empresas),
hay configuracion por empresa (encendido, modo sugerir/ejecutar, umbrales y
playbooks de serie apagados) y las propuestas del modo sugerir se aplican o
descartan desde aqui.
"""
from typing import Literal, Optional

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.core.deps import require_internal_user, requiere_capacidad
from app.core.tenancy import org_scoped_or_404
from app.db.session import get_db
from app.models.user import User
from app.core.abac_enforce import enforce_abac
from app.core.constantes import MAX_TAMANO_DE_PAGINA
from app.core.responses import APIResponse, APIListResponse
from app.services.audit import auditar_y_confirmar
from app.services.service_desk.autonomous_agent_service import (
    configuracion_del_agente,
    create_playbook,
    deactivate_playbook,
    decidir_sugerencia,
    evaluate_ticket_for_autonomy,
    get_execution_log,
    get_execution_stats,
    guardar_configuracion_del_agente,
    list_playbooks,
    run_autonomous_resolution,
    run_autonomous_scan,
    update_playbook,
)

router = APIRouter(prefix="/autonomous", tags=["Autonomous Agents"])


def _org(user: User):
    return getattr(user, "organization_id", None)


def _idioma(db: Session, user: User) -> str:
    """Idioma de quien llama: nombres de los playbooks de serie y motivos (19-11-2026)."""
    from app.services.formato_regional import idioma_de_salida
    return idioma_de_salida(db, user_id=str(user.id))


# ── Pydantic schemas ───────────────────────────────────────────────────────────

class PasoIn(BaseModel):
    type: Literal["comment", "notify", "escalate", "resolve"]
    content: str = Field("", max_length=4000)


class PlaybookCreateIn(BaseModel):
    name: str = Field(..., min_length=2, max_length=255)
    playbook_type: Optional[str] = Field(None, max_length=50)
    description: Optional[str] = Field(None, max_length=2000)
    steps: list[PasoIn] = []
    conditions: dict = {}


class PlaybookUpdateIn(BaseModel):
    name: Optional[str] = Field(None, min_length=2, max_length=255)
    description: Optional[str] = Field(None, max_length=2000)
    steps: Optional[list[PasoIn]] = None
    conditions: Optional[dict] = None
    is_active: Optional[bool] = None


class ConfigIn(BaseModel):
    enabled: Optional[bool] = None
    mode: Optional[Literal["suggest", "execute"]] = None
    resolve_threshold: Optional[float] = Field(None, ge=0, le=1)
    suggest_threshold: Optional[float] = Field(None, ge=0, le=1)
    disabled_playbooks: Optional[list[str]] = None


class EjecutarIn(BaseModel):
    # Sin modo, el de la empresa. Forzar `suggest` sirve para ver que haria.
    mode: Optional[Literal["suggest", "execute"]] = None


# ── Configuracion ─────────────────────────────────────────────────────────────

@router.get("/config", summary="Configuración del agente autónomo de la empresa")
def get_config(db: Session = Depends(get_db), current_user: User = Depends(require_internal_user)):
    return APIResponse.ok(data=configuracion_del_agente(db, _org(current_user)))


@router.put("/config", summary="Guardar la configuración del agente autónomo (admin)")
def put_config(payload: ConfigIn, db: Session = Depends(get_db), current_user: User = Depends(requiere_capacidad("sd.administrar"))):
    antes = configuracion_del_agente(db, _org(current_user))
    despues = guardar_configuracion_del_agente(db, _org(current_user), payload.model_dump(exclude_none=True))
    auditar_y_confirmar(db, current_user, "UPDATE", "sd_autonomous_agent", _org(current_user),
                        old_values=antes, new_values=despues)
    return APIResponse.ok(data=despues)


# ── Playbooks ─────────────────────────────────────────────────────────────────

@router.get("/playbooks", summary="Listar playbooks (de serie y de la empresa)")
def get_playbooks(db: Session = Depends(get_db), current_user: User = Depends(require_internal_user)):
    return APIListResponse.ok(items=list_playbooks(db, _org(current_user), _idioma(db, current_user)))


@router.post("/playbooks", summary="Crear playbook de la empresa")
def post_playbook(payload: PlaybookCreateIn, db: Session = Depends(get_db),
                  current_user: User = Depends(requiere_capacidad("sd.administrar"))):
    result = create_playbook(db, payload.model_dump(), _org(current_user))
    auditar_y_confirmar(db, current_user, "CREATE", "sd_playbook", result["id"], resource_name=result["name"])
    return APIResponse.ok(data=result)


@router.put("/playbooks/{playbook_id}", summary="Actualizar playbook de la empresa")
def put_playbook(playbook_id: str, payload: PlaybookUpdateIn, db: Session = Depends(get_db),
                 current_user: User = Depends(requiere_capacidad("sd.administrar"))):
    result = update_playbook(db, playbook_id, payload.model_dump(exclude_unset=True), _org(current_user))
    auditar_y_confirmar(db, current_user, "UPDATE", "sd_playbook", playbook_id,
                        new_values=payload.model_dump(exclude_unset=True))
    return APIResponse.ok(data=result)


@router.delete("/playbooks/{playbook_id}", summary="Desactivar playbook de la empresa")
def delete_playbook(
    playbook_id: str,
    db: Session = Depends(get_db),
    # Un playbook es configuracion de automatizacion: desactivarlo apaga
    # resoluciones automaticas para toda la organizacion. Es de administrador.
    current_user: User = Depends(requiere_capacidad("sd.administrar")),
):
    enforce_abac(db, current_user, "sd_playbook", playbook_id, action="delete")
    result = deactivate_playbook(db, playbook_id, _org(current_user))
    auditar_y_confirmar(db, current_user, "DELETE", "sd_playbook", playbook_id)
    return APIResponse.ok(data=result)


# ── Tickets ───────────────────────────────────────────────────────────────────

@router.post("/tickets/{ticket_id}/evaluate", summary="Evaluar si un ticket es apto para resolución autónoma")
def evaluate_ticket(ticket_id: str, db: Session = Depends(get_db),
                    current_user: User = Depends(require_internal_user)):
    from app.models.service_desk import Ticket
    ticket = org_scoped_or_404(db, Ticket, ticket_id, current_user, detail="Ticket not found")
    return APIResponse.ok(data=evaluate_ticket_for_autonomy(db, ticket, _idioma(db, current_user)))


@router.post("/tickets/{ticket_id}/resolve", summary="Pasar el agente autónomo por un ticket")
def resolve_ticket(ticket_id: str, payload: EjecutarIn = EjecutarIn(), db: Session = Depends(get_db),
                   current_user: User = Depends(requiere_capacidad("sd.administrar"))):
    resultado = run_autonomous_resolution(db, ticket_id, acting_user_id=current_user.id, origen="manual",
                                          org_id=_org(current_user), modo=payload.mode)
    auditar_y_confirmar(db, current_user, "EXECUTE", "sd_autonomous_agent", ticket_id,
                        metadata={"mode": resultado.get("mode"), "action": resultado.get("action")})
    return APIResponse.ok(data=resultado)


@router.post("/executions/{execution_id}/apply", summary="Aplicar la propuesta del agente (modo sugerir)")
def apply_suggestion(execution_id: str, db: Session = Depends(get_db),
                     current_user: User = Depends(require_internal_user)):
    resultado = decidir_sugerencia(db, execution_id, current_user, aplicar=True)
    auditar_y_confirmar(db, current_user, "APPROVE", "sd_autonomous_execution", execution_id)
    return APIResponse.ok(data=resultado)


@router.post("/executions/{execution_id}/discard", summary="Descartar la propuesta del agente (modo sugerir)")
def discard_suggestion(execution_id: str, db: Session = Depends(get_db),
                       current_user: User = Depends(require_internal_user)):
    resultado = decidir_sugerencia(db, execution_id, current_user, aplicar=False)
    auditar_y_confirmar(db, current_user, "REJECT", "sd_autonomous_execution", execution_id)
    return APIResponse.ok(data=resultado)


@router.post("/scan", summary="Pasar ahora el agente por los tickets nuevos de la empresa (admin)")
def autonomous_scan(db: Session = Depends(get_db), current_user: User = Depends(requiere_capacidad("sd.administrar"))):
    """La misma pasada que corre cada 5 minutos, solo sobre la empresa de quien llama."""
    return APIResponse.ok(data=run_autonomous_scan(db, org_id=_org(current_user)))


@router.get("/stats", summary="Estadísticas del agente autónomo de la empresa")
def agent_stats(db: Session = Depends(get_db), current_user: User = Depends(require_internal_user)):
    return APIResponse.ok(data=get_execution_stats(db, _org(current_user)))


@router.get("/log", summary="Registro de lo que hizo o propuso el agente autónomo")
def execution_log(
    page: int = Query(1, ge=1),
    page_size: int = Query(25, ge=1, le=MAX_TAMANO_DE_PAGINA),
    status: Optional[str] = Query(None, max_length=20),
    ticket_id: Optional[str] = Query(None, max_length=36),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_internal_user),
):
    result = get_execution_log(db, page=page, page_size=page_size, org_id=_org(current_user),
                               estado=status, ticket_id=ticket_id,
                               # Migracion 192: el motivo, en el idioma de quien lo lee.
                               idioma=_idioma(db, current_user))
    return APIListResponse.ok(items=result["items"], total=result["total"], page=result["page"],
                              page_size=page_size)
