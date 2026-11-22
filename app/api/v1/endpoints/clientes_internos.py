"""/internal-clients — gestión de clientes internos (rev. 193, docs/CLIENTES_INTERNOS.md §10).

Dirección y finanzas: `interno.gestionar` (admin, pm). Emitir, exportar y
anular cargos y los servicios compartidos: `interno.cargos` (admin). Aprobar o
rechazar un cargo que excede el presupuesto: el responsable de la unidad (lo
comprueba el servicio, con segregación). Lógica en `app/services/clientes_internos/`.
"""
from __future__ import annotations

from datetime import date
from typing import Optional

from fastapi import APIRouter, Depends, Query
from fastapi.responses import Response
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.core.deps import get_current_user, requiere_capacidad
from app.core.responses import APIListResponse, APIResponse
from app.db.session import get_db
from app.models.user import User
from app.services.clientes_internos import cargos as K
from app.services.clientes_internos import costes as C
from app.services.clientes_internos import gobierno as G
from app.services.clientes_internos import paneles
from app.services.clientes_internos import unidades as U
from app.services.clientes_internos.presupuesto import estado as estado_de_presupuesto

router = APIRouter()

# Capacidad que ve todos los cargos (las rutas la citan en literal: los barridos leen el literal).
GESTIONAR = "interno.gestionar"


class RolIn(BaseModel):
    user_id: str
    role: str = Field(..., max_length=20)


class GenerarIn(BaseModel):
    client_id: str
    period: str = Field(..., pattern=r"^\d{4}-\d{2}$")


class NotaIn(BaseModel):
    note: Optional[str] = Field(default=None, max_length=2000)


class ServicioIn(BaseModel):
    name: Optional[str] = Field(default=None, min_length=1, max_length=200)
    description: Optional[str] = Field(default=None, max_length=4000)
    monthly_amount: Optional[float] = Field(default=None, ge=0)
    currency: Optional[str] = Field(default=None, max_length=3)
    criterion: Optional[str] = None
    fixed_shares: Optional[dict[str, float]] = None
    is_active: Optional[bool] = None


class AdopcionIn(BaseModel):
    kind: Optional[str] = None
    title: Optional[str] = Field(default=None, max_length=200)
    due_date: Optional[date] = None
    status: Optional[str] = None
    target_users: Optional[int] = Field(default=None, ge=0)
    reached_users: Optional[int] = Field(default=None, ge=0)
    project_id: Optional[str] = None
    course_id: Optional[str] = None


class BeneficioIn(BaseModel):
    name: Optional[str] = Field(default=None, max_length=200)
    kind: Optional[str] = None
    unit: Optional[str] = Field(default=None, max_length=30)
    baseline: Optional[float] = None
    target: Optional[float] = None
    actual: Optional[float] = None
    target_date: Optional[date] = None
    measured_at: Optional[date] = None
    owner_id: Optional[str] = None
    notes: Optional[str] = Field(default=None, max_length=4000)


def _lista(items: list):
    return APIListResponse.ok(items=items, total=len(items))


# ── Cuadro de dirección y selectores ─────────────────────────────────────────

@router.get("/overview", summary="Cuadro de dirección: coste por unidad y fuente, presupuesto frente a real, cartera")
def overview(year: Optional[int] = Query(None, ge=2000, le=2100), db: Session = Depends(get_db),
             u: User = Depends(requiere_capacidad("interno.gestionar"))):
    return APIResponse.ok(data=paneles.overview(db, u, year))


@router.get("/options", summary="Opciones de la ficha de una unidad interna (departamentos, áreas, centros…)")
def opciones(db: Session = Depends(get_db), u: User = Depends(requiere_capacidad("finanzas.ver"))):
    # Lo usa el formulario de clientes: quien puede gestionar clientes (finanzas.ver).
    return APIResponse.ok(data=U.opciones(db, u))


# ── Cargos (antes de /{cid} para que no se confundan las rutas) ──────────────

@router.get("/charges", summary="Cargos internos (showback, chargeback, intercompañía)")
def cargos(client_id: Optional[str] = None, period: Optional[str] = None, status: Optional[str] = None,
           db: Session = Depends(get_db), u: User = Depends(requiere_capacidad("interno.gestionar"))):
    return _lista(K.listar(db, u, client_id, period, status))


@router.post("/charges/generate", status_code=201, summary="Generar el borrador del mes de una unidad")
def generar(payload: GenerarIn, db: Session = Depends(get_db), u: User = Depends(requiere_capacidad("interno.gestionar"))):
    return APIResponse.ok(data=K.generar(db, u, payload.client_id, payload.period))


@router.get("/charges/export", summary="CSV de asientos de los chargebacks emitidos del mes (los marca exportados)")
def exportar(period: str = Query(..., pattern=r"^\d{4}-\d{2}$"), db: Session = Depends(get_db),
             u: User = Depends(requiere_capacidad("interno.cargos"))):
    contenido = K.exportar(db, u, period)
    return Response(content=contenido, media_type="text/csv; charset=utf-8",
                    headers={"Content-Disposition": f'attachment; filename="cargos-internos-{period}.csv"'})


@router.get("/charges/{chid}", summary="Cargo con sus líneas")
def cargo(chid: str, db: Session = Depends(get_db), u: User = Depends(get_current_user)):
    c = K.cargo_o_404(db, chid)
    from app.core import capacidades
    if not (getattr(u, "is_superadmin", False) or capacidades.tiene(db, u, GESTIONAR)):
        U.exigir_papel(db, u, c.client_id, U.VEN_COSTES)
    return APIResponse.ok(data=K.cargo_dict(db, c, u, con_lineas=True))


@router.post("/charges/{chid}/issue", summary="Emitir (si excede el presupuesto, pasa a por aprobar)")
def emitir(chid: str, db: Session = Depends(get_db), u: User = Depends(requiere_capacidad("interno.cargos"))):
    return APIResponse.ok(data=K.emitir(db, u, chid))


@router.post("/charges/{chid}/approve", summary="Aprobar el exceso de presupuesto (responsable de la unidad)")
def aprobar(chid: str, payload: NotaIn, db: Session = Depends(get_db),
            u: User = Depends(requiere_capacidad("interno.portal"))):  # y responsable de la unidad (servicio)
    return APIResponse.ok(data=K.decidir(db, u, chid, True, payload.note))


@router.post("/charges/{chid}/reject", summary="Rechazar el exceso: el cargo vuelve a borrador")
def rechazar(chid: str, payload: NotaIn, db: Session = Depends(get_db),
             u: User = Depends(requiere_capacidad("interno.portal"))):  # y responsable de la unidad (servicio)
    return APIResponse.ok(data=K.decidir(db, u, chid, False, payload.note))


@router.post("/charges/{chid}/cancel", summary="Anular un cargo")
def anular(chid: str, payload: NotaIn, db: Session = Depends(get_db), u: User = Depends(requiere_capacidad("interno.cargos"))):
    return APIResponse.ok(data=K.anular(db, u, chid, payload.note))


# ── Servicios compartidos ────────────────────────────────────────────────────

@router.get("/shared-costs", summary="Servicios compartidos y su criterio de reparto")
def servicios(db: Session = Depends(get_db), u: User = Depends(requiere_capacidad("interno.cargos"))):
    return _lista(C.listar_servicios(db))


@router.post("/shared-costs", status_code=201, summary="Crear servicio compartido")
def crear_servicio(payload: ServicioIn, db: Session = Depends(get_db), u: User = Depends(requiere_capacidad("interno.cargos"))):
    return APIResponse.ok(data=C.guardar_servicio(db, u, payload.model_dump(exclude_unset=True)))


@router.patch("/shared-costs/{sid}", summary="Cambiar servicio compartido")
def editar_servicio(sid: str, payload: ServicioIn, db: Session = Depends(get_db),
                    u: User = Depends(requiere_capacidad("interno.cargos"))):
    return APIResponse.ok(data=C.guardar_servicio(db, u, payload.model_dump(exclude_unset=True), sid))


@router.delete("/shared-costs/{sid}", summary="Borrar servicio compartido")
def borrar_servicio(sid: str, db: Session = Depends(get_db), u: User = Depends(requiere_capacidad("interno.cargos"))):
    C.borrar_servicio(db, u, sid)
    return APIResponse.ok(data={"deleted": True})


@router.get("/shared-costs/{sid}/allocation", summary="Reparto del servicio entre unidades en un mes")
def reparto(sid: str, period: str = Query(..., pattern=r"^\d{4}-\d{2}$"), db: Session = Depends(get_db),
            u: User = Depends(requiere_capacidad("interno.cargos"))):
    return APIResponse.ok(data=C.reparto_de_servicio(db, u, sid, period))


# ── Beneficios y adopción por id ─────────────────────────────────────────────

@router.get("/projects/{pid}/benefits", summary="Caso de negocio: beneficios del proyecto")
def beneficios(pid: str, db: Session = Depends(get_db), u: User = Depends(requiere_capacidad("interno.gestionar"))):
    return _lista(G.beneficios(db, [pid]))


@router.post("/projects/{pid}/benefits", status_code=201, summary="Añadir beneficio al proyecto")
def crear_beneficio(pid: str, payload: BeneficioIn, db: Session = Depends(get_db),
                    u: User = Depends(requiere_capacidad("interno.gestionar"))):
    return APIResponse.ok(data=G.guardar_beneficio(db, u, payload.model_dump(exclude_unset=True), project_id=pid))


@router.patch("/benefits/{bid}", summary="Cambiar beneficio (objetivo, real, medición)")
def editar_beneficio(bid: str, payload: BeneficioIn, db: Session = Depends(get_db),
                     u: User = Depends(requiere_capacidad("interno.gestionar"))):
    return APIResponse.ok(data=G.guardar_beneficio(db, u, payload.model_dump(exclude_unset=True), bid=bid))


@router.delete("/benefits/{bid}", summary="Borrar beneficio")
def borrar_beneficio(bid: str, db: Session = Depends(get_db), u: User = Depends(requiere_capacidad("interno.gestionar"))):
    G.borrar_beneficio(db, u, bid)
    return APIResponse.ok(data={"deleted": True})


@router.patch("/adoption/{aid}", summary="Cambiar acción del plan de adopción")
def editar_adopcion(aid: str, payload: AdopcionIn, db: Session = Depends(get_db),
                    u: User = Depends(requiere_capacidad("interno.gestionar"))):
    return APIResponse.ok(data=G.guardar_adopcion(db, u, payload.model_dump(exclude_unset=True), aid=aid))


@router.delete("/adoption/{aid}", summary="Borrar acción del plan de adopción")
def borrar_adopcion(aid: str, db: Session = Depends(get_db), u: User = Depends(requiere_capacidad("interno.gestionar"))):
    G.borrar_adopcion(db, u, aid)
    return APIResponse.ok(data={"deleted": True})


# ── Una unidad ───────────────────────────────────────────────────────────────

@router.get("/{cid}/members", summary="Personas de la unidad (deducidas de RR. HH.) y su papel")
def miembros(cid: str, db: Session = Depends(get_db), u: User = Depends(requiere_capacidad("interno.gestionar"))):
    return _lista(U.lista_de_miembros(db, U.unidad_o_404(db, cid, u)))


@router.post("/{cid}/roles", status_code=201, summary="Designar usuario clave, finanzas o delegado")
def designar(cid: str, payload: RolIn, db: Session = Depends(get_db), u: User = Depends(requiere_capacidad("interno.gestionar"))):
    return APIResponse.ok(data=U.designar(db, u, cid, payload.user_id, payload.role))


@router.delete("/{cid}/roles/{rid}", summary="Quitar una designación")
def quitar(cid: str, rid: str, db: Session = Depends(get_db), u: User = Depends(requiere_capacidad("interno.gestionar"))):
    U.quitar_designacion(db, u, cid, rid)
    return APIResponse.ok(data={"deleted": True})


@router.get("/{cid}/cost", summary="Coste de la unidad por fuente en el periodo")
def coste(cid: str, desde: Optional[date] = None, hasta: Optional[date] = None, db: Session = Depends(get_db),
          u: User = Depends(requiere_capacidad("interno.gestionar"))):
    from app.core import timeutil
    hasta = hasta or timeutil.today()
    desde = desde or date(hasta.year, 1, 1)
    return APIResponse.ok(data=C.coste(db, U.unidad_o_404(db, cid, u), desde, hasta))


@router.get("/{cid}/tco", summary="Aplicaciones propias de la unidad (CMDB) y su TCO del año")
def tco(cid: str, year: Optional[int] = Query(None, ge=2000, le=2100), db: Session = Depends(get_db),
        u: User = Depends(requiere_capacidad("interno.gestionar"))):
    from app.core import timeutil
    return APIResponse.ok(data=C.tco(db, U.unidad_o_404(db, cid, u), year or timeutil.today().year))


@router.get("/{cid}/budget", summary="Presupuesto del año, consumo y semáforo")
def presupuesto(cid: str, year: Optional[int] = Query(None, ge=2000, le=2100), db: Session = Depends(get_db),
                u: User = Depends(requiere_capacidad("interno.gestionar"))):
    return APIResponse.ok(data=estado_de_presupuesto(db, U.unidad_o_404(db, cid, u), year))


@router.get("/{cid}/sla", summary="SLA/OLA de los tickets de la unidad")
def sla(cid: str, desde: Optional[date] = None, hasta: Optional[date] = None, db: Session = Depends(get_db),
        u: User = Depends(requiere_capacidad("interno.gestionar"))):
    return APIResponse.ok(data=G.sla(db, U.unidad_o_404(db, cid, u), desde, hasta))


@router.get("/{cid}/satisfaction", summary="NPS/CSAT de la unidad (sin nombres de empleados)")
def satisfaccion(cid: str, db: Session = Depends(get_db), u: User = Depends(requiere_capacidad("interno.gestionar"))):
    return APIResponse.ok(data=G.satisfaccion(db, U.unidad_o_404(db, cid, u), con_items=True))


@router.get("/{cid}/adoption", summary="Plan de adopción y formación de la unidad")
def adopcion(cid: str, db: Session = Depends(get_db), u: User = Depends(requiere_capacidad("interno.gestionar"))):
    return _lista(G.adopcion(db, U.unidad_o_404(db, cid, u)))


@router.post("/{cid}/adoption", status_code=201, summary="Añadir acción al plan de adopción")
def crear_adopcion(cid: str, payload: AdopcionIn, db: Session = Depends(get_db),
                   u: User = Depends(requiere_capacidad("interno.gestionar"))):
    return APIResponse.ok(data=G.guardar_adopcion(db, u, payload.model_dump(exclude_unset=True),
                                                  unidad=U.unidad_o_404(db, cid, u)))
