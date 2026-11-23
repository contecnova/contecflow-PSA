"""
Clients — Entidad central del sistema.
Un cliente puede tener: proyectos, contratos, licencias ALM, activos,
usuarios de portal y acceso al Service Desk independientemente de
si tiene proyectos vinculados.
"""
from fastapi import APIRouter, Depends, HTTPException, Body, Query, Response
from sqlalchemy.orm import Session
from typing import List, Optional
from pydantic import BaseModel, Field
from app.db.session import get_db
from app.core.deps import get_current_user, requiere_capacidad
from app.core.abac_enforce import enforce_abac
from app.core.paginacion import Paginacion, lista_paginada, paginacion
from app.core.responses import APIListResponse, APIResponse
from app.models.user import User
from app.services.client_service import (
    get_client_detail as _out_detail,
    get_scoped_client_or_404 as _get_scoped_client_or_404,
    create_client_record as svc_create_client,
    get_client_360 as svc_client_360,
)
import app.services.client_service as _svc
from app.core.codigos_de_error import error_http

router = APIRouter()


# ── CRUD principal ─────────────────────────────────────────────────────────────

@router.get("", response_model=APIListResponse[dict])
def list_clients(
    q: Optional[str] = None,
    status: Optional[str] = None,
    industry: Optional[str] = None,
    limit: Optional[int] = None,
    kind: Optional[str] = Query(None, pattern="^(externo|interno)$"),
    pagina: Paginacion = Depends(paginacion),
    db: Session = Depends(get_db),
    cu: User = Depends(get_current_user),
    response: Response = None,
):
    """Segunda auditoria 2026-11: ``page``/``page_size`` se aceptaban y se
    ignoraban (siempre la lista entera, con ``meta.page_size=50`` aunque fueran
    mil). Ahora paginan de verdad; sin ellos, la lista entera hasta
    ``LIST_MAX_ROWS``. ``limit`` sigue siendo «solo las primeras N»."""
    from app.services.politica_de_visibilidad import recortar_ficha_de_cliente
    return lista_paginada(response, _svc.list_clients(
        db, cu, q=q, status=status, industry=industry, limit=limit, pagina=pagina, kind=kind,
    ).mapear(lambda f: recortar_ficha_de_cliente(cu, f)))


@router.post("")
def create_client(data: dict = Body(...), db: Session = Depends(get_db), cu: User = Depends(get_current_user), response: Response = None,
    _rol: User = Depends(requiere_capacidad("clientes.gestionar")),  # auditoria 2026-09: sus hermanas del fichero usan esa guarda
):
    return APIResponse.ok(data=svc_create_client(data, cu, db))


@router.get("/{cid}")
def get_client(cid: str, db: Session = Depends(get_db), _=Depends(get_current_user), response: Response = None):
    cu = _
    c = _get_scoped_client_or_404(db, cu, cid)
    # Mínimo privilegio: el externo no ve el email ni el teléfono de las personas del cliente.
    from app.services.politica_de_visibilidad import recortar_ficha_de_cliente
    return APIResponse.ok(data=recortar_ficha_de_cliente(cu, _out_detail(c, db)))


@router.patch("/{cid}")
def update_client(cid: str, data: dict = Body(...), db: Session = Depends(get_db), cu: User = Depends(get_current_user), response: Response = None,
    _rol: User = Depends(requiere_capacidad("clientes.gestionar")),  # auditoria 2026-09: sus hermanas del fichero usan esa guarda
):
    return APIResponse.ok(data=_svc.update_client(cid, data, cu, db))


@router.delete("/{cid}")
def delete_client(cid: str, db: Session = Depends(get_db), cu: User = Depends(get_current_user), response: Response = None,
    _rol: User = Depends(requiere_capacidad("clientes.gestionar")),  # auditoria 2026-09: sus hermanas del fichero usan esa guarda
):
    enforce_abac(db, cu, "client", cid, action="delete")
    return APIResponse.ok(data=_svc.delete_client(cid, cu, db))


# ── Contactos ─────────────────────────────────────────────────────────────────

@router.get("/{cid}/contacts")
def list_contacts(cid: str, db: Session = Depends(get_db), cu: User = Depends(get_current_user)):
    return APIListResponse.ok(items=_svc.list_contacts(cid, db, cu))


@router.post("/{cid}/contacts")
def add_contact(cid: str, data: dict = Body(...), db: Session = Depends(get_db), cu: User = Depends(get_current_user),
    _rol: User = Depends(requiere_capacidad("clientes.gestionar")),  # auditoria 2026-09: sus hermanas del fichero usan esa guarda
):
    return APIResponse.ok(data=_svc.add_contact(cid, data, db, cu))


@router.patch("/{cid}/contacts/{contact_id}")
def update_contact(cid: str, contact_id: str, data: dict = Body(...),
    _rol: User = Depends(requiere_capacidad("clientes.gestionar")),  # auditoria 2026-09: sus hermanas del fichero usan esa guarda
                   db: Session = Depends(get_db), cu: User = Depends(get_current_user)):
    return APIResponse.ok(data=_svc.update_contact(cid, contact_id, data, db, cu))


@router.post("/{cid}/contacts/{contact_id}/primary")
def set_primary_contact(cid: str, contact_id: str,
    _rol: User = Depends(requiere_capacidad("clientes.gestionar")),
                        db: Session = Depends(get_db), cu: User = Depends(get_current_user)):
    """Marca el contacto como principal del cliente (único) y lo copia en la ficha."""
    return APIResponse.ok(data=_svc.marcar_contacto_principal(cid, contact_id, cu, db))


class AccesoAlPortalIn(BaseModel):
    # 23-11-2026 (M10 del 04b): sin contraseña, se genera y se envía al contacto por correo.
    password: Optional[str] = Field(None, min_length=8, max_length=128)
    language: Optional[str] = Field(None, min_length=2, max_length=10)
    project_ids: Optional[List[str]] = None


@router.post("/{cid}/contacts/{contact_id}/portal-access")
def give_portal_access(cid: str, contact_id: str, payload: AccesoAlPortalIn,
    _rol: User = Depends(requiere_capacidad("clientes.gestionar")),
                       db: Session = Depends(get_db), cu: User = Depends(get_current_user)):
    """Crea el usuario del portal del contacto con sus datos (mismo alta y tope que la pestaña del portal)."""
    return APIResponse.ok(data=_svc.dar_acceso_al_portal(
        cid, contact_id, payload.model_dump(exclude_none=True), cu, db))


@router.delete("/{cid}/contacts/{contact_id}")
def delete_contact(
    cid: str,
    contact_id: str,
    db: Session = Depends(get_db),
    cu: User = Depends(get_current_user),
    # Auditoria 2026-09: el unico control era `enforce_abac`, que sin
    # politicas activas no comprueba nada.
    #
    # La ficha de un cliente —sus contactos, sus licencias, sus
    # contratos, sus proyectos— es dato comercial: se consulta mucho y
    # se destruye poco. Ninguna de las 15 rutas de escritura de este
    # fichero tenia control de rol; queda anotado en el traspaso que el
    # hallazgo real es mas ancho que estos cuatro borrados.
    _: User = Depends(requiere_capacidad("clientes.gestionar")),
):
    enforce_abac(db, cu, "client_contact", contact_id, action="delete")
    return APIResponse.ok(data=_svc.delete_contact(cid, contact_id, db, cu))


# ── Vinculación de licencias ───────────────────────────────────────────────────

@router.get("/{cid}/licenses")
def list_client_licenses(cid: str, db: Session = Depends(get_db), _=Depends(get_current_user)):
    return APIListResponse.ok(items=_svc.list_client_licenses(cid, db))


@router.post("/{cid}/licenses")
def link_license(cid: str, data: dict = Body(...), db: Session = Depends(get_db), cu: User = Depends(get_current_user),
    _rol: User = Depends(requiere_capacidad("clientes.gestionar")),  # auditoria 2026-09: sus hermanas del fichero usan esa guarda
):
    return APIResponse.ok(data=_svc.link_license(cid, data, db))


@router.delete("/{cid}/licenses/{link_id}")
def unlink_license(
    cid: str,
    link_id: str,
    db: Session = Depends(get_db),
    cu: User = Depends(get_current_user),
    # Auditoria 2026-09: el unico control era `enforce_abac`, que sin
    # politicas activas no comprueba nada.
    #
    # La ficha de un cliente —sus contactos, sus licencias, sus
    # contratos, sus proyectos— es dato comercial: se consulta mucho y
    # se destruye poco. Ninguna de las 15 rutas de escritura de este
    # fichero tenia control de rol; queda anotado en el traspaso que el
    # hallazgo real es mas ancho que estos cuatro borrados.
    _: User = Depends(requiere_capacidad("clientes.gestionar")),
):
    enforce_abac(db, cu, "client_license_link", link_id, action="delete")
    return APIResponse.ok(data=_svc.unlink_license(cid, link_id, db))


# ── Vinculación de contratos ───────────────────────────────────────────────────

@router.get("/{cid}/contracts")
def list_client_contracts(cid: str, db: Session = Depends(get_db), _=Depends(get_current_user)):
    return APIListResponse.ok(items=_svc.list_client_contracts(cid, db))


@router.post("/{cid}/contracts")
def link_contract(cid: str, data: dict = Body(...), db: Session = Depends(get_db), cu: User = Depends(get_current_user),
    _rol: User = Depends(requiere_capacidad("clientes.gestionar")),  # auditoria 2026-09: sus hermanas del fichero usan esa guarda
):
    return APIResponse.ok(data=_svc.link_contract(cid, data, db))


@router.delete("/{cid}/contracts/{link_id}")
def unlink_contract(
    cid: str,
    link_id: str,
    db: Session = Depends(get_db),
    cu: User = Depends(get_current_user),
    response: Response = None,
    # Auditoria 2026-09: el unico control era `enforce_abac`, que sin
    # politicas activas no comprueba nada.
    #
    # La ficha de un cliente —sus contactos, sus licencias, sus
    # contratos, sus proyectos— es dato comercial: se consulta mucho y
    # se destruye poco. Ninguna de las 15 rutas de escritura de este
    # fichero tenia control de rol; queda anotado en el traspaso que el
    # hallazgo real es mas ancho que estos cuatro borrados.
    _: User = Depends(requiere_capacidad("clientes.gestionar")),
):
    enforce_abac(db, cu, "client_contract_link", link_id, action="delete")
    return APIResponse.ok(data=_svc.unlink_contract(cid, link_id, db))


# ── Config portal ─────────────────────────────────────────────────────────────

@router.get("/{cid}/portal-config")
def get_portal_config(cid: str, db: Session = Depends(get_db), _=Depends(get_current_user), response: Response = None):
    return APIResponse.ok(data=_svc.get_portal_config(cid, db))


@router.patch("/{cid}/portal-config")
def update_portal_config(cid: str, data: dict = Body(...), db: Session = Depends(get_db), cu: User = Depends(get_current_user), response: Response = None,
    _rol: User = Depends(requiere_capacidad("clientes.gestionar")),  # auditoria 2026-09: sus hermanas del fichero usan esa guarda
):
    return APIResponse.ok(data=_svc.update_portal_config(cid, data, db))


# ── Facturas del cliente ──────────────────────────────────────────────────────

@router.get("/{cid}/invoices")
def list_client_invoices(
    cid: str,
    pagina: Paginacion = Depends(paginacion),
    db: Session = Depends(get_db),
    _=Depends(get_current_user),
    response: Response = None,
):
    return lista_paginada(response, _svc.list_client_invoices(cid, db, pagina))


# ── Tickets del cliente ────────────────────────────────────────────────────────

@router.get("/{cid}/tickets")
def list_client_tickets(
    cid: str,
    status: Optional[str] = None,
    db: Session = Depends(get_db),
    _=Depends(get_current_user),
    response: Response = None,
):
    return APIListResponse.ok(items=_svc.list_client_tickets(cid, status, db))


# ── Usuarios de portal del cliente ────────────────────────────────────────────







# ── Vinculación de proyectos ───────────────────────────────────────────────────

@router.get("/{cid}/projects")
def list_client_projects(cid: str, db: Session = Depends(get_db), _=Depends(get_current_user)):
    return APIListResponse.ok(items=_svc.list_client_projects(cid, db))


@router.get("/{cid}/projects/available")
def list_available_projects(cid: str, db: Session = Depends(get_db), _=Depends(get_current_user), response: Response = None):
    try:
        return APIListResponse.ok(items=_svc.list_available_projects(cid, db))
    except Exception as e:
        import logging
        logging.getLogger(__name__).exception("Error al cargar los proyectos del cliente %s: %s", cid, e)
        raise error_http(500, "clientes_error_proyectos")


@router.post("/{cid}/projects/{project_id}/link")
def link_project(cid: str, project_id: str, db: Session = Depends(get_db), cu: User = Depends(get_current_user), response: Response = None,
    _rol: User = Depends(requiere_capacidad("clientes.gestionar")),  # auditoria 2026-09: sus hermanas del fichero usan esa guarda
):
    return APIResponse.ok(data=_svc.link_project(cid, project_id, db))


@router.delete("/{cid}/projects/{project_id}/link")
def unlink_project(
    cid: str,
    project_id: str,
    db: Session = Depends(get_db),
    cu: User = Depends(get_current_user),
    response: Response = None,
    # Auditoria 2026-09: el unico control era `enforce_abac`, que sin
    # politicas activas no comprueba nada.
    #
    # La ficha de un cliente —sus contactos, sus licencias, sus
    # contratos, sus proyectos— es dato comercial: se consulta mucho y
    # se destruye poco. Ninguna de las 15 rutas de escritura de este
    # fichero tenia control de rol; queda anotado en el traspaso que el
    # hallazgo real es mas ancho que estos cuatro borrados.
    _: User = Depends(requiere_capacidad("clientes.gestionar")),
):
    enforce_abac(db, cu, "client", cid, action="delete")
    return APIResponse.ok(data=_svc.unlink_project(cid, project_id, db))


# ── Visión 360: resumen ejecutivo del cliente ─────────────────────────────────

@router.get("/{cid}/360")
def client_360(cid: str, db: Session = Depends(get_db), _=Depends(get_current_user), response: Response = None):
    """Vista 360 del cliente: KPIs, actividad reciente, estado de salud."""
    return APIResponse.ok(data=svc_client_360(cid, db))
