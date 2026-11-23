"""
ALM service — business logic extracted from alm.py endpoint.
Covers: input data cleaning, serialisers for Vendor / Contract / License / Asset,
        linked-client query helpers, and all CRUD record operations.
"""
from __future__ import annotations

import logging
from datetime import date, datetime, timedelta
from typing import Any, Optional

from sqlalchemy import func, or_
from sqlalchemy.orm import Session, joinedload, selectinload
from app.models.alm import (
    ALMVendor, ALMContract, ALMLicense, ALMAsignacion,
    ALMAsset, ALMCostCenter, ALMSoftwareInstall, LicenseMetric,
)
from app.core import timeutil
from app.core.serializers import DIAS_RENOVACION_URGENTE
from app.core.errores import ErrorDeDominio
from app.core.paginacion import Pagina, Paginacion, paginar
from app.core.codigos_de_error import error

logger = logging.getLogger(__name__)


# ── Input cleaner ─────────────────────────────────────────────────────────────

# Fields that must NEVER be set from client-supplied payloads (mass-assignment
# guard). Tenant isolation (organization_id), identity (id), audit timestamps and
# the soft-delete flag are owned by the server, not the caller.
PROTECTED_FIELDS = frozenset({
    "id",
    "organization_id",
    "created_at",
    "updated_at",
    "created_by",
    "is_active",
})


def _a_fecha_alm(valor):
    """`'2026-09-15'` a `date`. Una fecha ilegible es `None`, no un error."""
    partes = str(valor).split("-")
    return date(int(partes[0]), int(partes[1]), int(partes[2]))


def _convertir(valor, conversor, campo: str):
    """Aplica el conversor. Lo que no se pueda convertir se guarda como `None`.

    Es deliberado y viene del origen del dato: esto limpia un payload de
    formulario, donde un campo mal escrito es un campo sin rellenar, no una
    petición inválida. El valor original queda en el registro de depuración.
    """
    try:
        return conversor(valor)
    except Exception:
        logger.debug("ALM clean_input: invalid %s field %s=%r → None", campo, campo, valor,
                     exc_info=True)
        return None


def clean_input(data: dict, model_cls, date_fields=None, int_fields=None,
                float_fields=None) -> dict:
    """Limpia el dict del frontend: '' → None, tipos correctos, ignora campos sin columna.

    Aplica además una deny-list (PROTECTED_FIELDS) para impedir mass-assignment
    de campos de tenant/identidad/auditoría desde el payload del cliente.

    Auditoría 2026-09 (hallazgo 18): los tres conversores eran tres bloques
    `try/except` idénticos salvo por la función. Declararlos como tabla deja un
    solo sitio donde se decide qué pasa con un valor ilegible.
    """
    conversores = [
        (set(date_fields or []), _a_fecha_alm, "date"),
        (set(int_fields or []), int, "int"),
        (set(float_fields or []), float, "float"),
    ]

    out = {}
    for clave, valor in data.items():
        # La deny-list va primero: un campo protegido no se toca ni para
        # ponerlo a None.
        if clave in PROTECTED_FIELDS or not hasattr(model_cls, clave):
            continue
        if valor == "" or valor is None:
            out[clave] = None
            continue

        for campos, conversor, nombre in conversores:
            if clave in campos:
                out[clave] = _convertir(valor, conversor, nombre)
                break
        else:
            out[clave] = valor
    return out


# ── Linked-client query helpers ───────────────────────────────────────────────

def _clientes_vinculados(db: Session, enlace, columna: str, ids: list) -> dict:
    """``{id: [{"id", "name"}]}`` de los clientes enlazados, en UNA consulta.

    Segunda auditoria 2026-11 (N+1): antes eran 1 consulta de enlaces por fila
    mas 1 por cliente enlazado; un listado de 50 licencias con un cliente cada
    una hacia 100 consultas solo para esto.
    """
    from app.models.clients import Client

    resultado: dict = {i: [] for i in ids}
    if not ids:
        return resultado
    clave = getattr(enlace, columna)
    filas = (
        db.query(clave, Client.id, Client.name)
        .join(Client, Client.id == enlace.client_id)
        .filter(clave.in_(ids))
        .all()
    )
    for propietario, cid, nombre in filas:
        resultado[propietario].append({"id": cid, "name": nombre})
    return resultado


def clientes_de_licencias(ids: list, db: Session) -> dict:
    from app.models.clients import ClientLicenseLink
    return _clientes_vinculados(db, ClientLicenseLink, "license_id", ids)


def clientes_de_contratos(ids: list, db: Session) -> dict:
    from app.models.clients import ClientContractLink
    return _clientes_vinculados(db, ClientContractLink, "contract_id", ids)


def get_linked_clients_for_license(license_id, db: Session) -> list:
    """Devuelve los clientes vinculados a una licencia via client_license_links."""
    return clientes_de_licencias([license_id], db)[license_id]


def get_linked_clients_for_contract(contract_id, db: Session) -> list:
    """Devuelve los clientes vinculados a un contrato pipeline via client_contract_links."""
    return clientes_de_contratos([contract_id], db)[contract_id]


# ── Serialisers (Refactored with ModelSerializer base class) ─────────────────

from app.core.serializers import VendorSerializer, ContractSerializer, LicenseSerializer, AssetSerializer


def serialize_vendor(v: ALMVendor) -> dict[str, Any]:
    """Serialize Vendor using base class."""
    return VendorSerializer(v).to_dict()


def serialize_contract(c: ALMContract, db: Optional[Session] = None,
                       vinculados: Optional[dict] = None) -> dict[str, Any]:
    """Serialize Contract using base class. Note: linked_clients not included by base class.

    ``vinculados`` es el mapa ya cargado en lote por ``clientes_de_contratos``;
    sin el, se consulta este contrato solo.
    """
    result = ContractSerializer(c).to_dict()
    if vinculados is not None:
        result["linked_clients"] = vinculados.get(c.id, [])
    elif db:
        result["linked_clients"] = get_linked_clients_for_contract(c.id, db)
    else:
        result["linked_clients"] = []
    return result


def serialize_license(lic: ALMLicense, db: Session, vinculados: Optional[dict] = None) -> dict[str, Any]:
    """Serialize License using base class. Note: linked_clients not included by base class."""
    result = LicenseSerializer(lic).to_dict()
    result["linked_clients"] = (vinculados.get(lic.id, []) if vinculados is not None
                                else get_linked_clients_for_license(lic.id, db))
    return result


#: Relaciones que leen los serializadores de cada listado, cargadas de antemano.
_CARGA_PROVEEDOR = (selectinload(ALMVendor.contracts),)
_CARGA_CONTRATO = (joinedload(ALMContract.vendor), joinedload(ALMContract.owner),
                   selectinload(ALMContract.licenses))
_CARGA_LICENCIA = (joinedload(ALMLicense.vendor), selectinload(ALMLicense.assignments))
_CARGA_ACTIVO = (joinedload(ALMAsset.vendor), joinedload(ALMAsset.assigned_to),
                 joinedload(ALMAsset.ci), selectinload(ALMAsset.installs), selectinload(ALMAsset.assignments))


def serialize_asset(a: ALMAsset, nombres: Optional[dict] = None) -> dict[str, Any]:
    """Serialize Asset using base class, con el nombre del titular vigente y las acciones posibles.

    ``nombres``: {(tipo, id): nombre} ya resuelto en lote por el listado
    (`alm_asignaciones.nombres_de_titulares`); sin él, se consulta este titular.
    """
    from sqlalchemy.orm import object_session
    from app.services.alm_asignaciones import nombre_de_titular
    from app.services.alm_ciclo_de_vida import acciones_posibles
    out = AssetSerializer(a).to_dict()
    clave = (out.get("holder_type"), out.get("holder_id"))
    if nombres is not None:
        out["holder_name"] = nombres.get(clave)
    else:
        sesion = object_session(a)
        out["holder_name"] = nombre_de_titular(sesion, *clave) if sesion is not None else None
    out["actions"] = acciones_posibles(a)
    return out


# ── Dashboard / KPIs ─────────────────────────────────────────────────────────

def get_alm_dashboard(db: Session) -> dict:

    today = timeutil.today()
    in_60 = today + timedelta(days=60)
    in_90 = today + timedelta(days=90)

    total_contracts   = db.query(ALMContract).filter(ALMContract.status == "active", ALMContract.is_active == True).count()
    expiring_soon     = db.query(ALMContract).filter(
        ALMContract.status == "active",
        ALMContract.is_active == True,
        ALMContract.renewal_date.isnot(None),
        ALMContract.renewal_date <= in_60,
    ).count()
    total_licenses    = db.query(ALMLicense).filter(ALMLicense.status != "cancelled", ALMLicense.is_active == True).count()
    expired_licenses  = db.query(ALMLicense).filter(
        ALMLicense.expiry_date < today,
        ALMLicense.status != "cancelled",
        ALMLicense.is_active == True,
    ).count()
    total_assets      = db.query(ALMAsset).filter(ALMAsset.status != "retired", ALMAsset.is_active == True).count()
    assets_in_use     = db.query(ALMAsset).filter(ALMAsset.status == "in_use", ALMAsset.is_active == True).count()
    warranty_expiring = db.query(ALMAsset).filter(
        ALMAsset.warranty_expiry.isnot(None),
        ALMAsset.warranty_expiry <= in_90,
        ALMAsset.warranty_expiry >= today,
        ALMAsset.is_active == True,
    ).count()
    total_vendors     = db.query(ALMVendor).filter(ALMVendor.is_active == True).count()

    annual_cost, contract_cost = coste_anual_vigente(db)

    upcoming = db.query(ALMContract).filter(
        ALMContract.status == "active",
        ALMContract.is_active == True,
        ALMContract.renewal_date.isnot(None),
        ALMContract.renewal_date >= today,
        ALMContract.renewal_date <= in_60,
    ).order_by(ALMContract.renewal_date).limit(5).all()

    return {
        "kpis": {
            "total_contracts": total_contracts,
            "expiring_soon": expiring_soon,
            "total_licenses": total_licenses,
            "expired_licenses": expired_licenses,
            "total_assets": total_assets,
            "assets_in_use": assets_in_use,
            "warranty_expiring_90d": warranty_expiring,
            "total_vendors": total_vendors,
            "annual_license_cost": round(annual_cost, 2),
            "annual_contract_cost": round(contract_cost, 2),
            "total_annual_cost": round(annual_cost + contract_cost, 2),
            "pending_approvals": db.query(func.count(ALMAsignacion.id)).filter(ALMAsignacion.status == "pending").scalar() or 0,
            "loans_overdue": db.query(func.count(ALMAsignacion.id)).filter(
                ALMAsignacion.mode == "loan", ALMAsignacion.status == "active",
                ALMAsignacion.valid_to.isnot(None), ALMAsignacion.valid_to < today).scalar() or 0,
            "acts_pending_signature": _actas_pendientes(db),
        },
        "upcoming_renewals": [serialize_contract(c, db) for c in upcoming],
    }


def coste_anual_vigente(db: Session) -> tuple[float, float]:
    """(licencias, contratos) del coste anual vigente, sin contar dos veces.

    Fase 1 (16-11-2026): el panel sumaba la cuota de TODAS las licencias
    (también canceladas o borradas) más la de todos los contratos, así que una
    licencia de un contrato contaba en los dos. Ahora:

    - licencias activas, no canceladas ni vencidas;
    - un contrato activo cuenta su ``annual_value``; sus licencias con cuota
      propia van dentro y no suman aparte, salvo que la suma de ellas pase del
      contrato, y entonces cuenta la suma;
    - las licencias sin contrato vigente cuentan su cuota.
    """
    hoy = timeutil.today()
    lics = db.query(ALMLicense).filter(ALMLicense.is_active == True,  # noqa: E712
                                       ALMLicense.status.notin_(("cancelled", "expired"))).all()
    lics = [lic for lic in lics if not (lic.expiry_date and lic.expiry_date < hoy)]
    contratos = {c.id: c for c in db.query(ALMContract).filter(ALMContract.status == "active",
                                                               ALMContract.is_active == True).all()}  # noqa: E712
    # M2 (auditoría 22-11-2026): cada cuota en la moneda de la empresa con el
    # tipo de hoy (antes se sumaban euros, dólares y libras tal cual). Un tipo
    # que falte se cuenta 1:1 y queda en el `TiposQueFaltan` de quien llama.
    from app.services.currency_rates_service import TablaDeTipos, tipo_o_aviso
    from app.services.settings_service.por_empresa import moneda_de_empresa
    moneda = moneda_de_empresa(db)

    def _en_moneda(importe, de) -> float:
        de = (de or moneda).upper()
        return float(importe or 0) * (tipo_o_aviso(db, de, moneda, hoy) if de != moneda else 1.0)

    por_contrato: dict = {}
    sueltas = 0.0
    with TablaDeTipos(db):
        for lic in lics:
            cuota = _en_moneda(lic.annual_cost, getattr(lic.contract, "currency", None) if lic.contract_id else None)
            if lic.contract_id in contratos:
                por_contrato[lic.contract_id] = por_contrato.get(lic.contract_id, 0.0) + cuota
            else:
                sueltas += cuota
        valores = {cid: _en_moneda(c.annual_value, getattr(c, "currency", None)) for cid, c in contratos.items()}
    contratos_total = 0.0
    licencias_en_contrato = 0.0
    for cid, c in contratos.items():
        propias = por_contrato.get(cid, 0.0)
        valor = valores[cid]
        if propias > valor:
            licencias_en_contrato += propias
        else:
            contratos_total += valor
    return sueltas + licencias_en_contrato, contratos_total


def _actas_pendientes(db: Session) -> int:
    from app.models.alm import ALMActa
    return db.query(func.count(ALMActa.id)).filter(ALMActa.status == "pending_signature").scalar() or 0


# ── Vendor record operations ──────────────────────────────────────────────────

def list_vendors_records(q: Optional[str], category: Optional[str], db: Session,
                         pagina: Optional[Paginacion] = None) -> Pagina:

    query = db.query(ALMVendor).options(*_CARGA_PROVEEDOR).filter(ALMVendor.is_active == True)
    if q:
        query = query.filter(ALMVendor.name.ilike(f"%{q}%"))
    if category:
        query = query.filter(ALMVendor.category == category)
    return paginar(query.order_by(ALMVendor.name), pagina, "alm.vendors").mapear(serialize_vendor)


def create_vendor_record(data: dict, db: Session) -> dict:

    clean = clean_input(data, ALMVendor)
    v = ALMVendor(**clean)
    db.add(v)
    db.commit()
    db.refresh(v)
    return serialize_vendor(v)


def get_vendor_record(vid: str, db: Session) -> dict:

    v = db.query(ALMVendor).filter(ALMVendor.id == vid, ALMVendor.is_active == True).first()
    if not v:
        raise error(404, "no_encontrado", detail="Proveedor no encontrado", que="proveedor")
    return serialize_vendor(v)


def update_vendor_record(vid: str, data: dict, db: Session) -> dict:

    v = db.query(ALMVendor).filter(ALMVendor.id == vid, ALMVendor.is_active == True).first()
    if not v:
        raise ErrorDeDominio(404)
    clean = clean_input(data, ALMVendor)
    for k, val in clean.items():
        setattr(v, k, val)
    db.commit()
    db.refresh(v)
    return serialize_vendor(v)


def delete_vendor_record(vid: str, db: Session) -> dict:

    v = db.query(ALMVendor).filter(ALMVendor.id == vid, ALMVendor.is_active == True).first()
    if not v:
        raise ErrorDeDominio(404)
    active_contracts = db.query(func.count(ALMContract.id)).filter(
        ALMContract.vendor_id == vid,
        ALMContract.is_active == True,
    ).scalar() or 0
    active_licenses = db.query(func.count(ALMLicense.id)).filter(
        ALMLicense.vendor_id == vid,
        ALMLicense.is_active == True,
    ).scalar() or 0
    active_assets = db.query(func.count(ALMAsset.id)).filter(
        ALMAsset.vendor_id == vid,
        ALMAsset.is_active == True,
    ).scalar() or 0
    if active_contracts or active_licenses or active_assets:
        raise error(400, "alm_no_eliminable_contratos_licencias_activos", detail=f"No se puede eliminar: contratos={active_contracts}, licencias={active_licenses}, activos={active_assets}", contratos=active_contracts, licencias=active_licenses, activos=active_assets)
    v.is_active = False
    db.commit()
    return {"ok": True, "message": "Proveedor eliminado correctamente"}


# ── Contract record operations ────────────────────────────────────────────────

def _contiene(columna, texto: str):
    """``columna`` contiene ``texto`` sin distinguir mayúsculas; % y _ cuentan como texto."""
    escapado = texto.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
    return columna.ilike(f"%{escapado}%", escape="\\")


def list_contracts_records(
    vendor_id: Optional[str],
    status: Optional[str],
    expiring_days: Optional[int],
    db: Session,
    pagina: Optional[Paginacion] = None,
    q: Optional[str] = None,
    renewal_urgent: bool = False,
) -> Pagina:

    query = db.query(ALMContract).options(*_CARGA_CONTRATO).filter(ALMContract.is_active == True)
    if vendor_id:
        query = query.filter(ALMContract.vendor_id == vendor_id)
    if status:
        query = query.filter(ALMContract.status == status)
    texto = (q or "").strip()
    if texto:
        query = query.filter(or_(
            _contiene(ALMContract.title, texto),
            _contiene(ALMContract.reference, texto),
            ALMContract.vendor.has(_contiene(ALMVendor.name, texto)),
        ))
    if renewal_urgent:
        # Misma definición que `renewal_urgent` del serializador: renueva de hoy a +N días.
        hoy = timeutil.today()
        query = query.filter(
            ALMContract.renewal_date.isnot(None),
            ALMContract.renewal_date >= hoy,
            ALMContract.renewal_date <= hoy + timedelta(days=DIAS_RENOVACION_URGENTE),
        )
    if expiring_days:
        cutoff = timeutil.today() + timedelta(days=expiring_days)
        query = query.filter(
            ALMContract.renewal_date.isnot(None),
            ALMContract.renewal_date <= cutoff,
            ALMContract.renewal_date >= timeutil.today(),
        )
    resultado = paginar(query.order_by(ALMContract.renewal_date.nullsfirst()), pagina, "alm.contracts")
    vinculados = clientes_de_contratos([c.id for c in resultado.items], db)
    return resultado.mapear(lambda c: serialize_contract(c, db, vinculados))


def _limpiar_contrato(data: dict) -> dict:
    """Lo mismo para el alta y el cambio.

    Auditoria 2026-11: el cambio guardaba los valores tal como llegaban, asi
    que un numero vacio («») iba a una columna `Float` (error en Postgres) y
    una fecha mal escrita se perdia sin decirlo solo en ese camino.
    """
    clean = clean_input(
        data, ALMContract,
        date_fields=["start_date", "end_date", "renewal_date"],
        int_fields=["notice_days"],
        float_fields=["total_value", "annual_value", "resolution_hours", "response_hours"],
    )
    for campo in ("resolution_hours", "response_hours"):
        if clean.get(campo) is not None and clean[campo] <= 0:
            raise error(422, "uc_plazos_no_validos")
    return clean


def create_contract_record(data: dict, created_by_id: str, db: Session) -> dict:

    clean = _limpiar_contrato(data)
    clean["created_by"] = created_by_id
    c = ALMContract(**clean)
    db.add(c)
    db.commit()
    db.refresh(c)
    return serialize_contract(c, db)


def get_contract_record(cid: str, db: Session) -> dict:

    c = db.query(ALMContract).filter(ALMContract.id == cid, ALMContract.is_active == True).first()
    if not c:
        raise ErrorDeDominio(404)
    return serialize_contract(c, db)


def update_contract_record(cid: str, data: dict, db: Session) -> dict:

    c = db.query(ALMContract).filter(ALMContract.id == cid, ALMContract.is_active == True).first()
    if not c:
        raise ErrorDeDominio(404)
    for k, v in _limpiar_contrato(data).items():
        setattr(c, k, v)
    db.commit()
    db.refresh(c)
    return serialize_contract(c, db)


def delete_contract_record(cid: str, db: Session) -> dict:

    c = db.query(ALMContract).filter(ALMContract.id == cid, ALMContract.is_active == True).first()
    if not c:
        raise ErrorDeDominio(404)
    active_licenses = db.query(func.count(ALMLicense.id)).filter(
        ALMLicense.contract_id == cid,
        ALMLicense.is_active == True,
    ).scalar() or 0
    if active_licenses > 0:
        raise error(400, "alm_no_eliminable_licencias", detail=f"No se puede eliminar: {active_licenses} licencia(s) activas asociadas", licencias=active_licenses)
    c.is_active = False
    c.status = "cancelled"
    db.commit()
    return {"ok": True, "message": "Contrato eliminado correctamente"}


# ── License record operations ─────────────────────────────────────────────────

def list_licenses_records(
    vendor_id: Optional[str],
    status: Optional[str],
    expiring_days: Optional[int],
    compliance_only: bool,
    db: Session,
    pagina: Optional[Paginacion] = None,
    q: Optional[str] = None,
    type: Optional[str] = None,
) -> Pagina:

    query = db.query(ALMLicense).options(*_CARGA_LICENCIA).filter(ALMLicense.is_active == True)
    if vendor_id:
        query = query.filter(ALMLicense.vendor_id == vendor_id)
    if status:
        query = query.filter(ALMLicense.status == status)
    if type:
        query = query.filter(ALMLicense.type == type)
    texto = (q or "").strip()
    if texto:
        query = query.filter(or_(
            _contiene(ALMLicense.name, texto),
            ALMLicense.vendor.has(_contiene(ALMVendor.name, texto)),
        ))
    if expiring_days:
        cutoff = timeutil.today() + timedelta(days=expiring_days)
        query = query.filter(
            ALMLicense.expiry_date.isnot(None),
            ALMLicense.expiry_date <= cutoff,
        )
    if compliance_only:
        query = query.filter(ALMLicense.is_compliance_req == True)
    resultado = paginar(query.order_by(ALMLicense.name), pagina, "alm.licenses")
    vinculados = clientes_de_licencias([lic.id for lic in resultado.items], db)
    return resultado.mapear(lambda lic: serialize_license(lic, db, vinculados))


#: Campos de la licencia que no llegan del formulario tal cual.
_INT_LICENCIA = ["total_seats", "tier_rank", "amortization_months"]
_PROTEGIDOS_LICENCIA = {"concurrent_peak", "concurrent_peak_at", "license_key_hint", "_license_key"}


def _limpiar_licencia(data: dict) -> dict:
    clean = clean_input(
        {k: v for k, v in data.items() if k not in _PROTEGIDOS_LICENCIA}, ALMLicense,
        date_fields=["purchase_date", "expiry_date"],
        int_fields=_INT_LICENCIA,
        float_fields=["purchase_price", "annual_cost"],
    )
    if "metric" in clean:
        metrica = clean["metric"] or LicenseMetric.named_user.value
        if metrica not in {m.value for m in LicenseMetric}:
            raise ErrorDeDominio(422, "alm_metrica_invalida")
        clean["metric"] = metrica
    for campo in ("total_seats", "amortization_months"):
        if clean.get(campo) is not None and clean[campo] < 0:
            raise ErrorDeDominio(422, "alm_valor_negativo")
    if clean.get("license_key") is None:
        # Vacío = no tocar la clave: el formulario nunca la recibe para editarla.
        clean.pop("license_key", None)
    return clean


def metrica_por_tipo(tipo) -> str:
    """La métrica que implica un tipo antiguo (`named`, `device`, `concurrent`, `volume`)."""
    tipo = getattr(tipo, "value", tipo)
    return {"device": "device", "concurrent": "concurrent", "volume": "volume"}.get(tipo or "", "named_user")


def create_license_record(data: dict, db: Session) -> dict:

    clean = _limpiar_licencia(data)
    if not clean.get("metric"):
        clean["metric"] = metrica_por_tipo(clean.get("type"))
    lic = ALMLicense(**clean)
    db.add(lic)
    db.commit()
    db.refresh(lic)
    return serialize_license(lic, db)


def get_license_record(lid: str, db: Session) -> dict:

    from app.services.alm_asignaciones import serializar
    lic = db.query(ALMLicense).filter(ALMLicense.id == lid, ALMLicense.is_active == True).first()
    if not lic:
        raise ErrorDeDominio(404, "alm_licencia_no_encontrada")
    out = serialize_license(lic, db)
    vigentes = [a for a in lic.assignments if a.is_active]
    vigentes.sort(key=lambda a: (a.parent_id is not None, a.valid_from))
    out["assignments"] = [serializar(db, a) for a in vigentes]
    out["installs"] = [
        {"id": i.id, "asset_id": i.asset_id, "asset_name": i.asset.name if i.asset else None,
         "version": i.version, "installed_at": i.installed_at.isoformat() if i.installed_at else None}
        for i in lic.installs if i.is_active
    ]
    out["contract_title"] = lic.contract.title if lic.contract else None
    return out


def update_license_record(lid: str, data: dict, db: Session) -> dict:

    lic = db.query(ALMLicense).filter(ALMLicense.id == lid, ALMLicense.is_active == True).first()
    if not lic:
        raise ErrorDeDominio(404)
    clean = _limpiar_licencia(data)
    if clean.get("total_seats") is not None:
        from app.services.alm_asignaciones import asientos_usados
        metrica = clean.get("metric") or lic.metric
        if metrica not in ("concurrent", "site") and clean["total_seats"] < asientos_usados(db, lic):
            raise ErrorDeDominio(409, "alm_asientos_por_debajo_de_lo_asignado")
    for k, v in clean.items():
        setattr(lic, k, v)
    db.commit()
    db.refresh(lic)
    return serialize_license(lic, db)


def delete_license_record(lid: str, db: Session) -> dict:

    lic = db.query(ALMLicense).filter(ALMLicense.id == lid, ALMLicense.is_active == True).first()
    if not lic:
        raise ErrorDeDominio(404)
    active_assignments = db.query(func.count(ALMAsignacion.id)).filter(
        ALMAsignacion.license_id == lid,
        ALMAsignacion.status.in_(("active", "pending")),
    ).scalar() or 0
    active_installs = db.query(func.count(ALMSoftwareInstall.id)).filter(
        ALMSoftwareInstall.license_id == lid,
        ALMSoftwareInstall.is_active == True,
    ).scalar() or 0
    if active_assignments or active_installs:
        raise error(400, "alm_no_eliminable_asignaciones_instalaciones", detail=f"No se puede eliminar: asignaciones={active_assignments}, instalaciones={active_installs}", asignaciones=active_assignments, instalaciones=active_installs)
    lic.is_active = False
    lic.status = "cancelled"
    db.commit()
    return {"ok": True, "message": "Licencia eliminada correctamente"}


def titular_del_payload(data: dict) -> tuple:
    """(holder_type, holder_id) del cuerpo: el nuevo (`holder_type`/`holder_id`) o el
    anterior (`user_id`, `asset_id` como dispositivo, `project_id`)."""
    if data.get("holder_type"):
        return data["holder_type"], data.get("holder_id") or None
    for tipo, clave in (("user", "user_id"), ("asset", "asset_id"), ("project", "project_id"),
                        ("department", "department_id"), ("client", "client_id")):
        if data.get(clave):
            return tipo, data[clave]
    raise ErrorDeDominio(422, "alm_titular_obligatorio")


def _parametros_de_asignacion(data: dict) -> dict:
    return {
        "quantity": data.get("quantity") or 1,
        "valid_from": data.get("valid_from"),
        "valid_to": data.get("valid_to") or data.get("expires_at"),
        "reason": data.get("reason"),
        "mode": data.get("mode") or None,
        "parent_id": data.get("parent_id") or None,
        "charge_project_id": data.get("charge_project_id") or None,
        "charge_cost_center_id": data.get("charge_cost_center_id") or None,
        "charge_client_id": data.get("charge_client_id") or None,
        "rebillable": data.get("rebillable") if isinstance(data.get("rebillable"), bool) else None,
        "notes": data.get("notes"),
    }


def assign_license_record(lid: str, data: dict, actor, db: Session) -> dict:
    """Asigna la licencia (`alm_asignaciones.asignar`). Acepta el cuerpo nuevo y el anterior."""
    from app.services.alm_asignaciones import asignar, serializar
    tipo, titular = titular_del_payload(data)
    a = asignar(db, actor=actor, license_id=lid, holder_type=tipo, holder_id=titular,
                **_parametros_de_asignacion(data))
    from app.services.audit import audit_log
    audit_log(db, actor, "ASSIGN", "alm_license", lid, a.license.name if a.license else None,
              new_values={"holder_type": tipo, "holder_id": titular, "status": a.status})
    db.commit()
    return serializar(db, a)


def revoke_assignment_record(lid: str, aid: str, db: Session, actor=None, motivo: Optional[str] = None,
                             tipo: str = "released") -> dict:
    """Cierra la asignación de la licencia (queda en el historial; nunca se borra)."""
    from app.services.alm_asignaciones import liberar, serializar
    a = db.query(ALMAsignacion).filter(ALMAsignacion.id == aid, ALMAsignacion.license_id == lid).first()
    if not a:
        raise ErrorDeDominio(404, "alm_asignacion_no_encontrada")
    a = liberar(db, aid, actor=actor, motivo=motivo, tipo=tipo)
    return serializar(db, a)


# ── Asset record operations ───────────────────────────────────────────────────

def list_assets_records(
    type: Optional[str],
    status: Optional[str],
    assigned_to: Optional[str],
    q: Optional[str],
    db: Session,
    pagina: Optional[Paginacion] = None,
) -> Pagina:

    query = db.query(ALMAsset).options(*_CARGA_ACTIVO).filter(ALMAsset.is_active == True)
    if type:
        query = query.filter(ALMAsset.type == type)
    if status:
        query = query.filter(ALMAsset.status == status)
    if assigned_to:
        query = query.filter(ALMAsset.assigned_to_id == assigned_to)
    if q:
        query = query.filter(or_(
            ALMAsset.name.ilike(f"%{q}%"),
            ALMAsset.serial_number.ilike(f"%{q}%"),
            ALMAsset.asset_tag.ilike(f"%{q}%"),
            ALMAsset.hostname.ilike(f"%{q}%"),
        ))
    from app.services.alm_asignaciones import nombres_de_titulares
    resultado = paginar(query.order_by(ALMAsset.name), pagina, "alm.assets")
    pares = [(asg.holder_type, asg.holder_id) for act in resultado.items for asg in act.assignments
             if asg.status in ("active", "pending")]
    nombres = nombres_de_titulares(db, pares)
    return resultado.mapear(lambda act: serialize_asset(act, nombres))


#: Fechas del activo que llegan como texto del formulario.
FECHAS_DE_ACTIVO = ["purchase_date", "warranty_expiry", "eol_date", "lease_expiry", "next_maintenance_date"]


def create_asset_record(data: dict, db: Session, current_user=None) -> dict:
    from app.services.alm_ciclo_de_vida import anotar, exigir_ci

    clean = clean_input(
        data, ALMAsset,
        date_fields=FECHAS_DE_ACTIVO,
        int_fields=["depreciation_years", "ram_gb", "storage_gb"],
        float_fields=["purchase_price"],
    )
    exigir_ci(db, clean.get("ci_id"), current_user)
    # Fase 1: el titular va por una asignación; `assigned_to_id` en el alta
    # (formulario antiguo, semilla) se convierte en su asignación.
    titular = clean.pop("assigned_to_id", None)
    # El alta puede traer el estado de un inventario anterior (comprado, en reparación,
    # dado de baja...); «asignado» o «prestado» solo existen con su asignación.
    estado = getattr(clean.get("status"), "value", clean.get("status")) or "available"
    clean["status"] = "available" if estado in ("in_use", "on_loan") else estado
    a = ALMAsset(**clean)
    db.add(a)
    db.flush()
    anotar(db, a, "status", None, a.status or "available", getattr(current_user, "id", None), "created")
    from app.services.alm_asignaciones import asignar, registrar_evento
    evento_de_alta = {"available": "received", "ordered": "requested"}.get(getattr(a.status, "value", a.status))
    if evento_de_alta:
        registrar_evento(db, evento=evento_de_alta, resource_type="asset", asset_id=a.id,
                         actor_id=getattr(current_user, "id", None))
    if titular:
        db.flush()
        asignar(db, actor=current_user, asset_id=a.id, holder_type="user", holder_id=titular,
                require_approval=False, commit=False)
    db.commit()
    db.refresh(a)
    return serialize_asset(a)


def get_asset_record(aid: str, db: Session) -> dict:

    a = db.query(ALMAsset).filter(ALMAsset.id == aid, ALMAsset.is_active == True).first()
    if not a:
        raise ErrorDeDominio(404)
    out = serialize_asset(a)
    out["licenses"] = [
        {"id": i.license_id, "install_id": i.id, "name": i.license.name if i.license else None, "version": i.version}
        for i in a.installs if i.is_active
    ]
    return out


def update_asset_record(aid: str, data: dict, db: Session, current_user=None) -> dict:
    from app.services.alm_ciclo_de_vida import aplicar_con_historial, exigir_ci

    a = db.query(ALMAsset).filter(ALMAsset.id == aid, ALMAsset.is_active == True).first()
    if not a:
        raise ErrorDeDominio(404)
    clean = clean_input(
        data, ALMAsset,
        date_fields=FECHAS_DE_ACTIVO,
        int_fields=["depreciation_years", "ram_gb", "storage_gb"],
        float_fields=["purchase_price"],
    )
    if "ci_id" in clean and clean["ci_id"] != a.ci_id:
        exigir_ci(db, clean["ci_id"], current_user)
    # Fase 1: el estado y el titular cambian con las acciones del ciclo de vida
    # (asignar, prestar, devolver, reparar, baja...), no editando el activo.
    clean.pop("assigned_to_id", None)
    nuevo = getattr(clean.get("status"), "value", clean.get("status"))
    actual = getattr(a.status, "value", a.status)
    if nuevo is not None and nuevo != actual:
        if not ({actual, nuevo} <= {"ordered", "available"}):
            raise ErrorDeDominio(409, "alm_estado_por_accion")
    else:
        clean.pop("status", None)
    aplicar_con_historial(db, a, clean, getattr(current_user, "id", None))
    db.commit()
    db.refresh(a)
    return serialize_asset(a)


def delete_asset_record(aid: str, db: Session, current_user=None) -> dict:
    from app.services.alm_ciclo_de_vida import aplicar_con_historial

    a = db.query(ALMAsset).filter(ALMAsset.id == aid, ALMAsset.is_active == True).first()
    if not a:
        raise ErrorDeDominio(404)
    active_installs = db.query(func.count(ALMSoftwareInstall.id)).filter(
        ALMSoftwareInstall.asset_id == aid,
        ALMSoftwareInstall.is_active == True,
    ).scalar() or 0
    active_assignments = db.query(func.count(ALMAsignacion.id)).filter(
        or_(ALMAsignacion.asset_id == aid, ALMAsignacion.holder_asset_id == aid),
        ALMAsignacion.status.in_(("active", "pending")),
    ).scalar() or 0
    if active_installs or active_assignments:
        raise error(400, "alm_no_eliminable_asignaciones_instalaciones", detail=f"No se puede eliminar: instalaciones={active_installs}, asignaciones={active_assignments}", instalaciones=active_installs, asignaciones=active_assignments)
    aplicar_con_historial(db, a, {"status": "retired"}, getattr(current_user, "id", None))
    a.is_active = False
    db.commit()
    return {"ok": True, "message": "Activo eliminado correctamente"}


def assign_asset_record(aid: str, data: dict, db: Session, current_user=None) -> dict:
    """Asigna o presta el activo (`alm_asignaciones.asignar`), con acta de entrega.

    Cuerpo: `holder_type`/`holder_id` (o `user_id`), `mode` (`assignment` |
    `loan`), `valid_to` (obligatoria en un préstamo), `reason`, `checklist`,
    `condition`, `observations`, `location` y los `charge_*`. Compatibilidad:
    `user_id` vacío devuelve el activo (cierra la asignación vigente)."""
    from app.services.alm_asignaciones import asignacion_vigente_de_activo, asignar, liberar
    a = db.query(ALMAsset).filter(ALMAsset.id == aid, ALMAsset.is_active == True).first()
    if not a:
        raise ErrorDeDominio(404, "alm_activo_no_encontrado")
    if not data.get("holder_type") and "user_id" in data and not data.get("user_id"):
        vigente = asignacion_vigente_de_activo(db, aid)
        if vigente is not None:
            liberar(db, vigente.id, actor=current_user, motivo=data.get("reason"), tipo="returned")
        db.refresh(a)
        return serialize_asset(a)
    tipo, titular = titular_del_payload(data)
    if data.get("location"):
        a.location = data["location"]
    parametros = _parametros_de_asignacion(data)
    parametros["quantity"] = 1
    parametros.pop("parent_id", None)
    asignar(db, actor=current_user, asset_id=aid, holder_type=tipo, holder_id=titular,
            checklist=data.get("checklist"), condition=data.get("condition") or None,
            observations=data.get("observations"), **parametros)
    db.refresh(a)
    return serialize_asset(a)


# ── Cost center record operations ─────────────────────────────────────────────

def list_cost_centers_records(db: Session) -> list:

    return [
        {
            "id": c.id, "code": c.code, "name": c.name,
            "budget_annual": c.budget_annual, "currency": c.currency,
            "is_active": c.is_active, "description": c.description,
        }
        for c in db.query(ALMCostCenter).filter(ALMCostCenter.is_active == True).order_by(ALMCostCenter.code).all()
    ]


def create_cost_center_record(data: dict, db: Session) -> dict:

    clean = clean_input(data, ALMCostCenter, float_fields=["budget_annual"])
    c = ALMCostCenter(**clean)
    db.add(c)
    db.commit()
    db.refresh(c)
    return {"id": c.id, "code": c.code, "name": c.name}


def update_cost_center_record(cid: str, data: dict, db: Session) -> dict:

    c = db.query(ALMCostCenter).filter(ALMCostCenter.id == cid, ALMCostCenter.is_active == True).first()
    if not c:
        raise ErrorDeDominio(404)
    clean = clean_input(data, ALMCostCenter, float_fields=["budget_annual"])
    for k, v in clean.items():
        setattr(c, k, v)
    db.commit()
    return {"id": c.id, "code": c.code, "name": c.name}


def delete_cost_center_record(cid: str, db: Session) -> dict:

    c = db.query(ALMCostCenter).filter(ALMCostCenter.id == cid, ALMCostCenter.is_active == True).first()
    if not c:
        raise ErrorDeDominio(404)
    active_contracts = db.query(func.count(ALMContract.id)).filter(
        ALMContract.cost_center_id == cid,
        ALMContract.is_active == True,
    ).scalar() or 0
    active_licenses = db.query(func.count(ALMLicense.id)).filter(
        ALMLicense.cost_center_id == cid,
        ALMLicense.is_active == True,
    ).scalar() or 0
    if active_contracts or active_licenses:
        raise error(400, "alm_no_eliminable_contratos_licencias", detail=f"No se puede eliminar: contratos={active_contracts}, licencias={active_licenses}", contratos=active_contracts, licencias=active_licenses)
    c.is_active = False
    db.commit()
    return {"ok": True, "message": "Centro de coste eliminado correctamente"}


# ── Software install record operations ────────────────────────────────────────

def add_install_record(aid: str, data: dict, installed_by_id: str, db: Session) -> dict:

    license_id = data.get("license_id")
    if not license_id:
        raise error(400, "campo_obligatorio", detail="license_id es obligatorio", campo="license_id")
    asset = db.query(ALMAsset).filter(ALMAsset.id == aid, ALMAsset.is_active == True).first()
    if not asset:
        raise error(404, "no_encontrado", detail="Activo no encontrado", que="activo")
    license_obj = db.query(ALMLicense).filter(ALMLicense.id == license_id, ALMLicense.is_active == True).first()
    if not license_obj:
        raise error(404, "no_encontrado", detail="Licencia no encontrada", que="licencia")
    existing = db.query(ALMSoftwareInstall).filter(
        ALMSoftwareInstall.asset_id == aid,
        ALMSoftwareInstall.license_id == license_id,
        ALMSoftwareInstall.is_active == True,
    ).first()
    if existing:
        raise error(400, "instalacion_ya_existe", detail="La instalacion ya existe")
    inst = ALMSoftwareInstall(
        asset_id     = aid,
        license_id   = license_id,
        installed_by = installed_by_id,
        version      = data.get("version"),
        notes        = data.get("notes"),
    )
    db.add(inst)
    db.commit()
    return {"id": inst.id, "asset_id": aid, "license_id": license_id}


def remove_install_record(aid: str, iid: str, db: Session) -> dict:

    inst = db.query(ALMSoftwareInstall).filter(
        ALMSoftwareInstall.id == iid,
        ALMSoftwareInstall.asset_id == aid,
        ALMSoftwareInstall.is_active == True,
    ).first()
    if not inst:
        raise ErrorDeDominio(404)
    inst.is_active = False
    db.commit()
    return {"ok": True, "message": "Instalacion eliminada correctamente"}


# ── Compliance report ─────────────────────────────────────────────────────────

def get_compliance_report(db: Session) -> dict:

    today = timeutil.today()
    issues = []
    # Fase 1: cada problema lleva un código y sus datos (la interfaz arma la frase).
    from app.services.alm_asignaciones import asientos_usados
    for lic in db.query(ALMLicense).filter(ALMLicense.is_compliance_req == True, ALMLicense.is_active == True).all():
        used = asientos_usados(db, lic)
        metrica = lic.metric or "named_user"
        if lic.expiry_date and lic.expiry_date < today:
            issues.append({"license_id": lic.id, "name": lic.name, "issue": "EXPIRED", "severity": "critical",
                           "params": {"date": lic.expiry_date.isoformat()}})
        if metrica == "concurrent":
            if lic.total_seats and (lic.concurrent_peak or 0) > lic.total_seats:
                issues.append({"license_id": lic.id, "name": lic.name, "issue": "OVER_PEAK", "severity": "critical",
                               "params": {"peak": lic.concurrent_peak, "total": lic.total_seats}})
        elif metrica != "site" and lic.total_seats and used > lic.total_seats:
            issues.append({"license_id": lic.id, "name": lic.name, "issue": "OVERALLOCATED", "severity": "critical",
                           "params": {"used": used, "total": lic.total_seats}})
        if metrica == "device" and lic.total_seats:
            instalaciones = sum(1 for i in lic.installs if i.is_active)
            if instalaciones > lic.total_seats:
                issues.append({"license_id": lic.id, "name": lic.name, "issue": "OVER_INSTALLED",
                               "severity": "warning", "params": {"installs": instalaciones, "total": lic.total_seats}})
    return {
        "issues": issues,
        "total": len(issues),
        "critical": sum(1 for i in issues if i["severity"] == "critical"),
        "warning": sum(1 for i in issues if i["severity"] == "warning"),
    }

