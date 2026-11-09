"""
bi_etl.py — Conectores ETL de BI (revisión 2026-11): una lista y un panel.

  GET    /bi/etl/connectors                  conectores del registro + fuentes REST, y la ficha del genérico
  GET    /bi/etl/connectors/{id}             uno, con sus últimas sincronizaciones
  PATCH  /bi/etl/connectors/{id}             activar, entidad y credenciales (un secreto vacío no cambia)
  POST   /bi/etl/connectors/{id}/test        conecta y extrae sin guardar: cuántos registros, o el error
  POST   /bi/etl/connectors/{id}/sync        sincroniza ahora y devuelve el resultado real
  GET    /bi/etl/connectors/{id}/log         historial, lo último primero
  GET    /bi/etl/data/{id}                   lo último que se trajo
  POST   /bi/etl/sources                     da de alta una fuente REST genérica
  DELETE /bi/etl/sources/{id}                la quita

La sincronización manual corre en la petición: antes se mandaba a la cola
`etl_{id}`, que ningún worker escucha, y la pantalla decía «encolada» para
siempre. La periódica la hace el worker (`bi-connector-sync`).
"""
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.core.deps import require_admin
from app.core.ratelimit import limiter
from app.core.responses import APIResponse
from app.db.session import get_db
from app.integrations import bi_etl_connectors as _etl
from app.models.user import User
from app.services import bi_etl_service as svc

router = APIRouter(prefix="/bi/etl", tags=["BI ETL Connectors"])


def _org(u: User) -> Optional[str]:
    org = getattr(u, "organization_id", None)
    return str(org) if org else None


class ConfigIn(BaseModel):
    enabled: Optional[bool] = None
    entity: Optional[str] = Field(None, max_length=64)
    config: Optional[dict] = None


class FuenteIn(BaseModel):
    nombre: str = Field(..., min_length=2, max_length=80)
    config: dict = Field(default_factory=dict)


def _llamar(f, *a, **kw):
    try:
        return f(*a, **kw)
    except svc.NoEncontrado:
        raise HTTPException(status_code=404, detail="Conector no encontrado")
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.get("/connectors", summary="Conectores ETL, su estado y la ficha de la fuente REST genérica")
@limiter.limit("60/minute")
def list_connectors(request: Request, db: Session = Depends(get_db), current_user: User = Depends(require_admin)):
    items = svc.listar(db, _org(current_user))
    return APIResponse.ok(data={"connectors": items, "count": len(items), "generico": _etl.ficha(_etl.TIPO_GENERICO)})


@router.get("/connectors/{connector_id}", summary="Detalle de un conector ETL")
@limiter.limit("60/minute")
def get_connector_detail(request: Request, connector_id: str, db: Session = Depends(get_db),
                         current_user: User = Depends(require_admin)):
    org = _org(current_user)
    fila = _llamar(svc.uno, db, org, connector_id)
    return APIResponse.ok(data={**fila, "recent_log": svc.registro(db, org, connector_id, 10)})


@router.patch("/connectors/{connector_id}", summary="Activar un conector y darle entidad y credenciales")
@limiter.limit("30/minute")
def configure_connector(request: Request, connector_id: str, body: ConfigIn, db: Session = Depends(get_db),
                        current_user: User = Depends(require_admin)):
    return APIResponse.ok(data=_llamar(svc.configurar, db, _org(current_user), connector_id,
                                       enabled=body.enabled, entity=body.entity, config=body.config))


@router.post("/connectors/{connector_id}/test", summary="Probar un conector sin guardar nada")
@limiter.limit("10/minute")
def test_connector(request: Request, connector_id: str, db: Session = Depends(get_db),
                   current_user: User = Depends(require_admin)):
    return APIResponse.ok(data=_llamar(svc.probar, db, _org(current_user), connector_id))


@router.post("/connectors/{connector_id}/sync", summary="Sincronizar ahora")
@limiter.limit("10/minute")
def trigger_sync(request: Request, connector_id: str, db: Session = Depends(get_db),
                 current_user: User = Depends(require_admin)):
    return APIResponse.ok(data=_llamar(svc.sincronizar, db, _org(current_user), connector_id))


@router.get("/connectors/{connector_id}/log", summary="Historial de sincronizaciones")
@limiter.limit("60/minute")
def get_sync_log(request: Request, connector_id: str, limit: int = Query(20, ge=1, le=100),
                 db: Session = Depends(get_db), current_user: User = Depends(require_admin)):
    entries = _llamar(svc.registro, db, _org(current_user), connector_id, limit)
    return APIResponse.ok(data={"connector_id": connector_id, "entries": entries, "count": len(entries)})


@router.get("/data/{connector_id}", summary="Lo último que trajo un conector")
@limiter.limit("30/minute")
def get_synced_data(request: Request, connector_id: str, db: Session = Depends(get_db),
                    current_user: User = Depends(require_admin)):
    return APIResponse.ok(data={"connector_id": connector_id,
                                "data": _llamar(svc.datos, db, _org(current_user), connector_id)})


@router.post("/sources", summary="Dar de alta una fuente REST genérica")
@limiter.limit("20/minute")
def create_source(request: Request, body: FuenteIn, db: Session = Depends(get_db),
                  current_user: User = Depends(require_admin)):
    return APIResponse.ok(data=_llamar(svc.crear_fuente, db, _org(current_user), body.nombre, body.config))


@router.delete("/sources/{connector_id}", summary="Quitar una fuente REST")
@limiter.limit("20/minute")
def delete_source(request: Request, connector_id: str, db: Session = Depends(get_db),
                  current_user: User = Depends(require_admin)):
    _llamar(svc.borrar_fuente, db, _org(current_user), connector_id)
    return APIResponse.ok(data={"deleted": connector_id})
