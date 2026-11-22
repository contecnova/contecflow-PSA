"""/internal-portal — portal interno de las unidades internas (rev. 193, docs/CLIENTES_INTERNOS.md §5).

Para empleados (capacidad `interno.portal`, mismo login/SSO). Todo se acota
en `app/services/clientes_internos/portal.py` a las unidades de quien llama:
sin pertenencia, 403 `interno_sin_acceso`. `GET /me` responde siempre (200).
"""
from __future__ import annotations

from datetime import date
from typing import Literal, Optional

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.core.deps import requiere_capacidad
from app.core.responses import APIListResponse, APIResponse
from app.db.session import get_db
from app.models.user import User
from app.services.clientes_internos import portal

router = APIRouter()



class FirmaHitoIn(BaseModel):
    approve: bool
    note: Optional[str] = Field(default=None, max_length=2000)


class FirmaUatIn(BaseModel):
    result: str = Field(..., max_length=20)
    notes: Optional[str] = Field(default=None, max_length=4000)


class PeticionIn(BaseModel):
    title: str = Field(..., min_length=1, max_length=255)
    description: Optional[str] = Field(default=None, max_length=10000)
    kind: Literal["proyecto", "servicio"] = "proyecto"
    estimated_budget: Optional[float] = Field(default=None, ge=0)
    wanted_start: Optional[date] = None
    wanted_end: Optional[date] = None


class ValoracionIn(BaseModel):
    score: int
    comment: Optional[str] = Field(default=None, max_length=2000)
    survey_type: Literal["nps", "csat"] = "nps"


def _lista(items: list):
    return APIListResponse.ok(items=items, total=len(items))


@router.get("/me", summary="Mis unidades internas y mi papel en cada una")
def yo(db: Session = Depends(get_db), u: User = Depends(requiere_capacidad("interno.portal"))):
    return APIResponse.ok(data=portal.yo(db, u))


@router.get("/units/{cid}/summary", summary="Mi departamento: resumen")
def resumen(cid: str, db: Session = Depends(get_db), u: User = Depends(requiere_capacidad("interno.portal"))):
    return APIResponse.ok(data=portal.resumen(db, u, cid))


@router.get("/units/{cid}/projects", summary="Proyectos de la unidad y su avance")
def proyectos(cid: str, db: Session = Depends(get_db), u: User = Depends(requiere_capacidad("interno.portal"))):
    return _lista(portal.proyectos(db, u, cid))


@router.get("/units/{cid}/milestones", summary="Hitos pendientes de firma")
def hitos(cid: str, db: Session = Depends(get_db), u: User = Depends(requiere_capacidad("interno.portal"))):
    return _lista(portal.hitos(db, u, cid))


@router.post("/milestones/{mid}/sign", summary="Firmar (aprobar o rechazar) un hito: responsable de la unidad")
def firmar_hito(mid: str, payload: FirmaHitoIn, db: Session = Depends(get_db),
                u: User = Depends(requiere_capacidad("interno.portal"))):
    return APIResponse.ok(data=portal.firmar_hito(db, u, mid, payload.approve, payload.note))


@router.get("/units/{cid}/uat", summary="Sesiones UAT de los proyectos de la unidad")
def uat(cid: str, db: Session = Depends(get_db), u: User = Depends(requiere_capacidad("interno.portal"))):
    return _lista(portal.uat(db, u, cid))


@router.post("/uat/{sid}/sign", summary="Firmar una UAT: usuario clave o responsable")
def firmar_uat(sid: str, payload: FirmaUatIn, db: Session = Depends(get_db),
               u: User = Depends(requiere_capacidad("interno.portal"))):
    return APIResponse.ok(data=portal.firmar_uat(db, u, sid, payload.result, payload.notes))


@router.get("/units/{cid}/tickets", summary="Tickets de la unidad")
def tickets(cid: str, db: Session = Depends(get_db), u: User = Depends(requiere_capacidad("interno.portal"))):
    return _lista(portal.tickets(db, u, cid))


@router.get("/units/{cid}/sla", summary="SLA/OLA de los servicios de la unidad")
def sla(cid: str, desde: Optional[date] = None, hasta: Optional[date] = None, db: Session = Depends(get_db),
        u: User = Depends(requiere_capacidad("interno.portal"))):
    return APIResponse.ok(data=portal.sla(db, u, cid, desde, hasta))


@router.get("/units/{cid}/cost", summary="Coste y presupuesto de la unidad (responsable y finanzas)")
def coste(cid: str, year: Optional[int] = Query(None, ge=2000, le=2100), db: Session = Depends(get_db),
          u: User = Depends(requiere_capacidad("interno.portal"))):
    return APIResponse.ok(data=portal.coste(db, u, cid, year))


@router.get("/units/{cid}/charges", summary="Cargos emitidos a la unidad (responsable y finanzas)")
def cargos(cid: str, db: Session = Depends(get_db), u: User = Depends(requiere_capacidad("interno.portal"))):
    return _lista(portal.cargos(db, u, cid))


@router.get("/units/{cid}/requests", summary="Peticiones de proyectos y servicios de la unidad")
def peticiones(cid: str, db: Session = Depends(get_db), u: User = Depends(requiere_capacidad("interno.portal"))):
    return APIResponse.ok(data=portal.peticiones(db, u, cid))


@router.post("/units/{cid}/requests", status_code=201, summary="Pedir un proyecto o un servicio (flujo de demanda)")
def pedir(cid: str, payload: PeticionIn, db: Session = Depends(get_db), u: User = Depends(requiere_capacidad("interno.portal"))):
    return APIResponse.ok(data=portal.pedir(db, u, cid, payload.model_dump(exclude_unset=True)))


@router.post("/units/{cid}/satisfaction", status_code=201, summary="Valorar la satisfacción (NPS o CSAT)")
def valorar(cid: str, payload: ValoracionIn, db: Session = Depends(get_db),
            u: User = Depends(requiere_capacidad("interno.portal"))):
    return APIResponse.ok(data=portal.valorar(db, u, cid, payload.model_dump()))


@router.get("/units/{cid}/adoption", summary="Plan de adopción y formación de la unidad")
def adopcion(cid: str, db: Session = Depends(get_db), u: User = Depends(requiere_capacidad("interno.portal"))):
    return _lista(portal.adopcion(db, u, cid))


@router.get("/units/{cid}/benefits", summary="Beneficios de los proyectos de la unidad")
def beneficios(cid: str, db: Session = Depends(get_db), u: User = Depends(requiere_capacidad("interno.portal"))):
    return _lista(portal.beneficios(db, u, cid))
