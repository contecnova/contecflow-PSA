"""/supplier-portal — portal del proveedor (migracion 191, docs/PROVEEDORES_Y_EXTERNALIZACION.md §13).

Para personas externas (rol `subcontractor`, capacidad `proveedores.portal`) marcadas como
contacto del portal de su proveedor (`subcontractor_workers.supplier_portal`).
Todo se acota en `app/services/proveedores/portal.py` al proveedor de la
persona que llama: ninguna ruta recibe el id del proveedor. Sin la marca, 403
`proveedor_portal_sin_acceso`; con el acceso retirado o caducado, 401 en
`get_current_user` (`externos.ciclo.acceso_vigente`). `GET /me` responde
siempre (200) para que la pantalla sepa si mostrar el portal.
"""
from __future__ import annotations

from datetime import date
from typing import Optional

from fastapi import APIRouter, Depends, File, Query, Request, UploadFile
from sqlalchemy.orm import Session

from app.core.abac_enforce import enforce_abac
from app.core.deps import requiere_capacidad
from app.core.responses import APIListResponse, APIResponse
from app.db.session import get_db
from app.models.user import User
from app.schemas.proveedores import InformeIn
from app.services.proveedores import portal

router = APIRouter()


def _periodo(desde: Optional[date], hasta: Optional[date]) -> tuple[date, date]:
    from app.api.v1.endpoints.proveedores import _periodo as periodo
    return periodo(desde, hasta)


def _ip(request: Request) -> Optional[str]:
    return request.client.host if request.client else None


@router.get("/me", summary="¿Soy contacto del portal? De qué proveedor y qué puedo hacer")
def yo(db: Session = Depends(get_db), u: User = Depends(requiere_capacidad("proveedores.portal"))):
    return APIResponse.ok(data=portal.yo(db, u))


@router.get("/work-packages", summary="Paquetes de trabajo de mi proveedor")
def paquetes(db: Session = Depends(get_db), u: User = Depends(requiere_capacidad("proveedores.portal"))):
    items = portal.paquetes(db, u)
    return APIListResponse.ok(items=items, total=len(items))


@router.get("/services", summary="Servicios gestionados de mi proveedor")
def servicios(db: Session = Depends(get_db), u: User = Depends(requiere_capacidad("proveedores.portal"))):
    items = portal.servicios(db, u)
    return APIListResponse.ok(items=items, total=len(items))


@router.get("/services/{sid}/sla", summary="SLA medido de un servicio de mi proveedor")
def sla(sid: str, desde: Optional[date] = Query(None), hasta: Optional[date] = Query(None),
        db: Session = Depends(get_db), u: User = Depends(requiere_capacidad("proveedores.portal"))):
    return APIResponse.ok(data=portal.sla(db, u, sid, *_periodo(desde, hasta)))


@router.get("/reports", summary="Informes, partes y evidencias de mi proveedor")
def informes(db: Session = Depends(get_db), u: User = Depends(requiere_capacidad("proveedores.portal"))):
    items = portal.informes(db, u)
    return APIListResponse.ok(items=items, total=len(items))


@router.post("/reports", summary="Subir informe periódico, parte de servicio, evidencia de SLA o avance",
             status_code=201)
def crear_informe(payload: InformeIn, db: Session = Depends(get_db), u: User = Depends(requiere_capacidad("proveedores.portal"))):
    enforce_abac(db, u, "supplier_portal", None, action="create")
    return APIResponse.ok(data=portal.crear_informe(db, u, payload.model_dump(exclude_unset=True)))


@router.post("/reports/{rid}/attachments", summary="Adjuntar un fichero (evidencia) a un informe propio",
             status_code=201)
def adjuntar(rid: str, request: Request, file: UploadFile = File(...), db: Session = Depends(get_db),
             u: User = Depends(requiere_capacidad("proveedores.portal"))):
    enforce_abac(db, u, "supplier_portal", rid, action="update")
    return APIResponse.ok(data=portal.subir_adjunto(db, u, rid, file.filename or "", file.content_type or "",
                                                    file.file.read(), _ip(request)))


@router.get("/reports/{rid}/attachments/{doc_id}/open", summary="Enlace firmado de un adjunto propio (auditado)")
def abrir_adjunto(rid: str, doc_id: str, request: Request, db: Session = Depends(get_db), u: User = Depends(requiere_capacidad("proveedores.portal"))):
    return APIResponse.ok(data=portal.abrir_adjunto_propio(db, u, rid, doc_id, _ip(request)))


@router.get("/usage", summary="Consumo medido del periodo de mi proveedor (por contrato)")
def consumo(desde: Optional[date] = Query(None), hasta: Optional[date] = Query(None),
            db: Session = Depends(get_db), u: User = Depends(requiere_capacidad("proveedores.portal"))):
    return APIResponse.ok(data=portal.consumo(db, u, *_periodo(desde, hasta)))


@router.get("/statements", summary="Estados de cuenta de mi proveedor")
def estados(db: Session = Depends(get_db), u: User = Depends(requiere_capacidad("proveedores.portal"))):
    items = portal.estados_de_cuenta(db, u)
    return APIListResponse.ok(items=items, total=len(items))
