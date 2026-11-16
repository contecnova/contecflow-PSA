"""Asignación universal de licencias y activos (licencias y hardware, fase 1 — 16-11-2026).

Un recurso (licencia o activo) pasa a un titular —persona, proyecto,
departamento, cliente o dispositivo— durante un intervalo, con motivo, quién lo
hizo y, si la empresa tiene un flujo para `alm_assignment`, con aprobación del
motor común (`approval_engine.fuentes`). Nada se borra: una asignación se
cierra (``ended``) y cada paso queda en `ALMEvento`, inmutable.

Modelo: `app.models.alm.ALMAsignacion` (ver la cabecera de `app/models/alm.py`).

Reglas de asientos por métrica de la licencia (`ALMLicense.metric`):

- ``named_user``: titular persona; un proyecto, departamento o cliente recibe
  una **bolsa** (``mode = pool``) de ``quantity`` asientos que reparte con
  asignaciones hijas (``parent_id``) a personas.
- ``device``: titular dispositivo (activo), o bolsa.
- ``volume``: cada asignación consume su ``quantity``.
- ``concurrent``: las asignaciones dan derecho de uso y no consumen asientos;
  el cumplimiento se mide con el pico (`registrar_pico`).
- ``site``: sin límite.

Una asignación pendiente de aprobar reserva su asiento.

Interfaz pública (la usan las fases 2 y 4; no cambiar la firma sin avisar):

    asignar(db, *, actor, holder_type, holder_id, license_id=None, asset_id=None, ...)
    prestar(db, *, actor, asset_id, holder_type, holder_id, valid_to, ...)
    liberar(db, asignacion_id, *, actor=None, motivo=None, tipo="released", origen=None)
    devolver(db, asignacion_id, *, actor, motivo=None, checklist=None, condition=None, a_reparar=False)
    liberar_licencias_de_usuario(db, user_id, *, actor=None, motivo=None, origen="offboarding")
    equipos_de_usuario(db, user_id)        -> list[ALMAsignacion] de activos vigentes
    asignaciones_de_usuario(db, user_id, incluir_cerradas=False)
    titulares_vigentes(db, license_id, dia=None)
    registrar_pico(db, license_id, pico, medido_en=None, fuente="manual")

Los errores son `ErrorDeDominio` con un código ``alm_*`` como detalle; la
interfaz lo traduce (`alm.err_<código>`).
"""
from __future__ import annotations

import json
import logging
from datetime import date, datetime
from typing import Iterable, Optional

from sqlalchemy import or_
from sqlalchemy.orm import Session

from app.core import timeutil
from app.core.errores import ErrorDeDominio
from app.models.alm import (
    COLUMNA_DE_TITULAR, TIPOS_DE_TITULAR, ALMAsignacion, ALMAsset, ALMEvento, ALMLicense,
    ALMPicoConcurrencia, LicenseMetric,
)

logger = logging.getLogger(__name__)

#: Tipo de la solicitud en el motor de aprobaciones.
TIPO_DE_APROBACION = "alm_assignment"

#: Códigos de paso del historial (`ALMEvento.event`). La interfaz los traduce.
EVENTOS = (
    "requested", "assigned", "approved", "rejected", "cancelled", "revoked", "released", "returned",
    "expired", "lent", "transferred", "received", "repair_sent", "repair_done", "retired", "disposed",
    "lost", "stolen", "found", "act_created", "act_signed", "key_viewed", "peak_recorded",
    "renewal_decided", "renewed", "auto_renewed", "contract_expired", "seats_changed", "cancelled_at_term",
)

#: Estados del activo desde los que se puede asignar o prestar.
ESTADOS_ASIGNABLES = ("available",)


# ── Utilidades ────────────────────────────────────────────────────────────────

def _fecha(valor, campo: str) -> Optional[date]:
    if valor in (None, ""):
        return None
    if isinstance(valor, datetime):
        return valor.date()
    if isinstance(valor, date):
        return valor
    try:
        return date.fromisoformat(str(valor)[:10])
    except ValueError:
        raise ErrorDeDominio(422, f"alm_fecha_invalida:{campo}")


def _modelo_de_titular(tipo: str):
    from app.models.clients import Client
    from app.models.project import Project
    from app.models.settings import Department
    from app.models.user import User
    return {"user": User, "project": Project, "department": Department, "client": Client, "asset": ALMAsset}[tipo]


def nombre_de_titular(db: Session, tipo: Optional[str], titular_id: Optional[str]) -> Optional[str]:
    """Nombre legible de un titular (persona, proyecto, departamento, cliente o activo)."""
    if not tipo or not titular_id or tipo not in COLUMNA_DE_TITULAR:
        return None
    obj = db.get(_modelo_de_titular(tipo), titular_id)
    if obj is None:
        return None
    if tipo == "user":
        return obj.full_name
    if tipo == "project":
        return f"{obj.code} · {obj.name}" if getattr(obj, "code", None) else obj.name
    if tipo == "asset":
        return f"{obj.name} ({obj.asset_tag})" if obj.asset_tag else obj.name
    return obj.name


def nombres_de_titulares(db: Session, pares) -> dict:
    """{(tipo, id): nombre} de muchos titulares con una consulta por tipo (listados sin N+1)."""
    por_tipo: dict = {}
    for tipo, ident in pares:
        if tipo in COLUMNA_DE_TITULAR and ident:
            por_tipo.setdefault(tipo, set()).add(ident)
    salida: dict = {}
    for tipo, ids in por_tipo.items():
        modelo = _modelo_de_titular(tipo)
        for obj in db.query(modelo).filter(modelo.id.in_(list(ids))).all():
            if tipo == "user":
                nombre = obj.full_name
            elif tipo == "project":
                nombre = f"{obj.code} · {obj.name}" if getattr(obj, "code", None) else obj.name
            elif tipo == "asset":
                nombre = f"{obj.name} ({obj.asset_tag})" if obj.asset_tag else obj.name
            else:
                nombre = obj.name
            salida[(tipo, obj.id)] = nombre
    return salida


def _exigir_titular(db: Session, tipo: str, titular_id: Optional[str]) -> None:
    """El titular existe y es de la empresa de la sesión (la consulta pasa por el filtro de tenant)."""
    if tipo not in TIPOS_DE_TITULAR:
        raise ErrorDeDominio(422, "alm_titular_tipo_invalido")
    if not titular_id:
        raise ErrorDeDominio(422, "alm_titular_obligatorio")
    modelo = _modelo_de_titular(tipo)
    consulta = db.query(modelo.id).filter(modelo.id == titular_id)
    if hasattr(modelo, "is_active") and tipo != "user":
        consulta = consulta.filter(modelo.is_active.isnot(False))
    if consulta.first() is None:
        raise ErrorDeDominio(404, "alm_titular_no_encontrado")


def registrar_evento(db: Session, *, evento: str, resource_type: str, license_id: Optional[str] = None,
                     asset_id: Optional[str] = None, contract_id: Optional[str] = None,
                     asignacion: Optional[ALMAsignacion] = None, actor_id: Optional[str] = None,
                     motivo: Optional[str] = None, datos: Optional[dict] = None,
                     holder_type: Optional[str] = None, holder_id: Optional[str] = None) -> ALMEvento:
    """Una fila del historial inmutable. No confirma."""
    if asignacion is not None:
        holder_type = holder_type or asignacion.holder_type
        holder_id = holder_id or asignacion.holder_id
        license_id = license_id or asignacion.license_id
        asset_id = asset_id or asignacion.asset_id
    ev = ALMEvento(
        resource_type=resource_type, license_id=license_id, asset_id=asset_id, contract_id=contract_id,
        assignment_id=asignacion.id if asignacion is not None else None, event=evento,
        holder_type=holder_type, holder_id=holder_id,
        holder_name=(nombre_de_titular(db, holder_type, holder_id) or None),
        actor_id=actor_id, reason=motivo, data=json.dumps(datos, default=str) if datos else None,
    )
    if asignacion is not None and asignacion.organization_id:
        ev.organization_id = asignacion.organization_id
    db.add(ev)
    return ev


def _licencia(db: Session, license_id: str) -> ALMLicense:
    lic = db.query(ALMLicense).filter(ALMLicense.id == license_id, ALMLicense.is_active.is_(True)).first()
    if lic is None:
        raise ErrorDeDominio(404, "alm_licencia_no_encontrada")
    return lic


def _activo(db: Session, asset_id: str) -> ALMAsset:
    a = db.query(ALMAsset).filter(ALMAsset.id == asset_id, ALMAsset.is_active.is_(True)).first()
    if a is None:
        raise ErrorDeDominio(404, "alm_activo_no_encontrado")
    return a


def _asignacion(db: Session, asignacion_id: str) -> ALMAsignacion:
    a = db.query(ALMAsignacion).filter(ALMAsignacion.id == asignacion_id).first()
    if a is None:
        raise ErrorDeDominio(404, "alm_asignacion_no_encontrada")
    return a


def _valor(v):
    return getattr(v, "value", v)


# ── Asientos ──────────────────────────────────────────────────────────────────

def asientos_usados(db: Session, lic: ALMLicense) -> int:
    """Asientos ocupados: las asignaciones de primer nivel activas o pendientes (las hijas
    de una bolsa consumen de su bolsa, no de la licencia)."""
    filas = db.query(ALMAsignacion.quantity).filter(
        ALMAsignacion.license_id == lic.id, ALMAsignacion.parent_id.is_(None),
        ALMAsignacion.status.in_(("active", "pending"))).all()
    return int(sum(q or 0 for (q,) in filas))


def usados_en_bolsa(db: Session, bolsa: ALMAsignacion) -> int:
    filas = db.query(ALMAsignacion.quantity).filter(
        ALMAsignacion.parent_id == bolsa.id, ALMAsignacion.status.in_(("active", "pending"))).all()
    return int(sum(q or 0 for (q,) in filas))


def _limite_de_asientos(lic: ALMLicense) -> Optional[int]:
    """None: sin límite por asignaciones (sitio, concurrente o sin total)."""
    if lic.metric in (LicenseMetric.site.value, LicenseMetric.concurrent.value):
        return None
    return lic.total_seats


def _comprobar_licencia(db: Session, lic: ALMLicense, holder_type: str, mode: str, quantity: int,
                        padre: Optional[ALMAsignacion], holder_id: str) -> None:
    if _valor(lic.status) in ("cancelled", "expired"):
        raise ErrorDeDominio(409, "alm_licencia_no_asignable")
    if lic.expiry_date and lic.expiry_date < timeutil.today():
        raise ErrorDeDominio(409, "alm_licencia_vencida")
    if mode == "loan":
        raise ErrorDeDominio(422, "alm_prestamo_solo_activos")
    metrica = lic.metric or LicenseMetric.named_user.value
    if padre is not None:
        if padre.license_id != lic.id or padre.mode != "pool" or padre.status != "active":
            raise ErrorDeDominio(422, "alm_bolsa_invalida")
        if holder_type not in ("user", "asset"):
            raise ErrorDeDominio(422, "alm_bolsa_solo_personas_o_equipos")
        if usados_en_bolsa(db, padre) + quantity > (padre.quantity or 0):
            raise ErrorDeDominio(409, "alm_bolsa_sin_asientos")
    elif mode == "pool":
        if holder_type not in ("project", "department", "client"):
            raise ErrorDeDominio(422, "alm_bolsa_titular_invalido")
    if metrica == LicenseMetric.named_user.value and holder_type == "asset":
        raise ErrorDeDominio(422, "alm_metrica_nominal_sin_equipos")
    if metrica == LicenseMetric.device.value and holder_type == "user":
        raise ErrorDeDominio(422, "alm_metrica_dispositivo_sin_personas")
    if holder_type in ("user", "asset"):
        columna = getattr(ALMAsignacion, COLUMNA_DE_TITULAR[holder_type])
        repetida = db.query(ALMAsignacion.id).filter(
            ALMAsignacion.license_id == lic.id, columna == holder_id,
            ALMAsignacion.status.in_(("active", "pending"))).first()
        if repetida is not None and metrica != LicenseMetric.volume.value:
            raise ErrorDeDominio(409, "alm_ya_asignada")
    if padre is None:
        limite = _limite_de_asientos(lic)
        if limite is not None and asientos_usados(db, lic) + quantity > limite:
            raise ErrorDeDominio(409, "alm_sin_asientos")


def _comprobar_activo(activo: ALMAsset, holder_type: str, holder_id: str, mode: str,
                      valid_from: date, valid_to: Optional[date]) -> None:
    if _valor(activo.status) not in ESTADOS_ASIGNABLES:
        raise ErrorDeDominio(409, "alm_activo_no_disponible")
    if mode == "pool":
        raise ErrorDeDominio(422, "alm_bolsa_solo_licencias")
    if holder_type == "asset" and holder_id == activo.id:
        raise ErrorDeDominio(422, "alm_activo_titular_de_si_mismo")
    if mode == "loan" and valid_to is None:
        raise ErrorDeDominio(422, "alm_prestamo_sin_devolucion")


def _comprobar_cargo(db: Session, charge_project_id, charge_cost_center_id, charge_client_id) -> None:
    from app.models.alm import ALMCostCenter
    from app.models.clients import Client
    from app.models.project import Project
    for modelo, valor, codigo in ((Project, charge_project_id, "alm_cargo_proyecto"),
                                  (ALMCostCenter, charge_cost_center_id, "alm_cargo_centro"),
                                  (Client, charge_client_id, "alm_cargo_cliente")):
        if valor and db.query(modelo.id).filter(modelo.id == valor).first() is None:
            raise ErrorDeDominio(404, codigo)


# ── Aprobación ────────────────────────────────────────────────────────────────

def _hay_flujo(db: Session, actor, contexto: dict) -> bool:
    if actor is None:
        return False
    try:
        from app.services.approval_engine._base import elegir_flujo
        return elegir_flujo(db, TIPO_DE_APROBACION, {**contexto, "department": getattr(actor, "department", None)}) is not None
    except Exception:
        logger.warning("no se pudo consultar el flujo de %s", TIPO_DE_APROBACION, exc_info=True)
        return False


def _resumen(db: Session, a: ALMAsignacion) -> str:
    recurso = (a.license.name if a.license is not None else a.asset.name if a.asset is not None else "")
    return f"{recurso} → {nombre_de_titular(db, a.holder_type, a.holder_id) or a.holder_type}"


# ── Asignar ───────────────────────────────────────────────────────────────────

def asignar(db: Session, *, actor, holder_type: str, holder_id: str,
            license_id: Optional[str] = None, asset_id: Optional[str] = None,
            quantity: int = 1, valid_from=None, valid_to=None, reason: Optional[str] = None,
            mode: Optional[str] = None, parent_id: Optional[str] = None,
            charge_project_id: Optional[str] = None, charge_cost_center_id: Optional[str] = None,
            charge_client_id: Optional[str] = None, rebillable: Optional[bool] = None,
            source: str = "manual", notes: Optional[str] = None, require_approval: Optional[bool] = None,
            checklist: Optional[list] = None, condition: Optional[str] = None,
            observations: Optional[str] = None, commit: bool = True) -> ALMAsignacion:
    """Asigna una licencia o un activo a un titular.

    - ``actor``: el `User` que asigna (None: el sistema; nunca pide aprobación).
    - ``mode``: ``assignment`` (por defecto), ``loan`` (activos; exige
      ``valid_to``) o ``pool``. Una licencia a un proyecto, departamento o
      cliente es siempre una bolsa.
    - ``require_approval``: None decide la empresa (hay flujo activo para
      ``alm_assignment``); True/False lo fuerzan (False solo si hay actor gestor).
    - Para un activo con titular persona se emite el acta de entrega (si
      `ALM_HANDOVER_ACT_ENABLED`), con ``checklist``/``condition``/``observations``.

    Devuelve la asignación (``status`` ``active`` o ``pending``).
    """
    if bool(license_id) == bool(asset_id):
        raise ErrorDeDominio(422, "alm_recurso_obligatorio")
    holder_type = (holder_type or "").strip()
    _exigir_titular(db, holder_type, holder_id)
    try:
        quantity = int(quantity or 1)
    except (TypeError, ValueError):
        raise ErrorDeDominio(422, "alm_cantidad_invalida")
    if quantity < 1:
        raise ErrorDeDominio(422, "alm_cantidad_invalida")
    desde = _fecha(valid_from, "valid_from") or timeutil.today()
    hasta = _fecha(valid_to, "valid_to")
    if hasta is not None and hasta < desde:
        raise ErrorDeDominio(422, "alm_fin_antes_de_inicio")
    _comprobar_cargo(db, charge_project_id, charge_cost_center_id, charge_client_id)

    padre = _asignacion(db, parent_id) if parent_id else None
    if license_id:
        lic = _licencia(db, license_id)
        if mode is None:
            mode = "pool" if holder_type in ("project", "department", "client") and padre is None else "assignment"
        if mode not in ("assignment", "pool", "loan"):
            raise ErrorDeDominio(422, "alm_modo_invalido")
        _comprobar_licencia(db, lic, holder_type, mode, quantity, padre, holder_id)
        recurso = "license"
        activo = None
    else:
        activo = _activo(db, asset_id)
        mode = mode or "assignment"
        if mode not in ("assignment", "loan", "pool"):
            raise ErrorDeDominio(422, "alm_modo_invalido")
        if padre is not None:
            raise ErrorDeDominio(422, "alm_bolsa_solo_licencias")
        _comprobar_activo(activo, holder_type, holder_id, mode, desde, hasta)
        quantity = 1
        recurso = "asset"
        lic = None

    a = ALMAsignacion(
        resource_type=recurso, license_id=license_id or None, asset_id=asset_id or None,
        holder_type=holder_type, mode=mode, parent_id=padre.id if padre else None, quantity=quantity,
        status="pending", valid_from=desde, valid_to=hasta, reason=(reason or None),
        source=source or "manual", assigned_by=getattr(actor, "id", None),
        charge_project_id=charge_project_id or None, charge_cost_center_id=charge_cost_center_id or None,
        charge_client_id=charge_client_id or None, rebillable=rebillable, notes=(notes or None),
    )
    setattr(a, COLUMNA_DE_TITULAR[holder_type], holder_id)
    if lic is not None:
        a.organization_id = lic.organization_id
    elif activo is not None:
        a.organization_id = activo.organization_id
    db.add(a)
    db.flush()

    contexto = {"resource_type": recurso, "holder_type": holder_type, "mode": mode, "quantity": quantity,
                "amount": _coste_anual_estimado(lic, activo, quantity)}
    pedir = _hay_flujo(db, actor, contexto) if require_approval is None else bool(require_approval and actor)
    acta = {"checklist": checklist, "condition": condition, "observations": observations}
    if not pedir:
        _activar(db, a, actor, acta)
        if commit:
            db.commit()
            db.refresh(a)
        return a

    registrar_evento(db, evento="requested", resource_type=recurso, asignacion=a,
                     actor_id=getattr(actor, "id", None), motivo=reason, datos={"mode": mode, "quantity": quantity})
    db.commit()
    from app.services.approval_engine import fuentes
    fuentes.abrir(db, TIPO_DE_APROBACION, a.id, _resumen(db, a), actor.id, contexto=contexto)
    if fuentes.estado(db, TIPO_DE_APROBACION, a.id) != "pending":
        # Sin solicitud abierta (el flujo dejó de aplicar, o la aprobó sola): se activa ya.
        a = _asignacion(db, a.id)
        if a.status == "pending":
            _activar(db, a, actor, acta)
            db.commit()
    db.refresh(a)
    return a


def _coste_anual_estimado(lic: Optional[ALMLicense], activo: Optional[ALMAsset], cantidad: int) -> float:
    """Para las condiciones del flujo de aprobación (`amount`)."""
    if lic is not None:
        if lic.annual_cost and lic.total_seats:
            return round(float(lic.annual_cost) / lic.total_seats * cantidad, 2)
        return float(lic.annual_cost or 0)
    if activo is not None:
        return float(activo.purchase_price or 0)
    return 0.0


def _activar(db: Session, a: ALMAsignacion, actor, acta: Optional[dict] = None, aprobado: bool = False) -> None:
    """Pasa a ``active`` y aplica sus efectos (estado del activo, reflejo del titular, acta)."""
    actor_id = getattr(actor, "id", None)
    a.status = "active"
    if aprobado:
        a.approved_by = actor_id
        a.approved_at = timeutil.utcnow()
    if a.resource_type == "asset" and a.asset is not None:
        _reflejar_titular(db, a.asset, a, actor_id)
    registrar_evento(db, evento="approved" if aprobado else ("lent" if a.mode == "loan" else "assigned"),
                     resource_type=a.resource_type, asignacion=a, actor_id=actor_id, motivo=a.reason,
                     datos={"mode": a.mode, "quantity": a.quantity, "valid_to": a.valid_to,
                            "parent_id": a.parent_id})
    if aprobado:
        registrar_evento(db, evento="lent" if a.mode == "loan" else "assigned", resource_type=a.resource_type,
                         asignacion=a, actor_id=actor_id, motivo=a.reason)
    db.flush()
    if a.resource_type == "asset" and a.holder_type == "user":
        from app.services import alm_actas
        if alm_actas.actas_activadas(db, a.organization_id):
            alm_actas.crear_acta(db, a, "delivery", actor, **(acta or {}))


def _reflejar_titular(db: Session, activo: ALMAsset, a: Optional[ALMAsignacion], actor_id: Optional[str],
                      estado: Optional[str] = None, nota: Optional[str] = None,
                      anterior: Optional[ALMAsignacion] = None) -> None:
    """Las columnas de reflejo del activo (persona, proyecto, departamento) y su estado.

    Al cerrar (``a`` None) se quita el proyecto o departamento solo si venían de
    la asignación que acaba (``anterior``); si eran datos propios del activo, se quedan."""
    from app.services.alm_ciclo_de_vida import aplicar_con_historial
    if a is None or a.status != "active":
        cambios = {"assigned_to_id": None, "status": estado or "available"}
        if anterior is not None and anterior.holder_type == "project" and activo.project_id == anterior.holder_project_id:
            cambios["project_id"] = None
        if anterior is not None and anterior.holder_type == "department" and activo.department_id == anterior.holder_department_id:
            cambios["department_id"] = None
    else:
        cambios = {
            "assigned_to_id": a.holder_user_id if a.holder_type == "user" else None,
            "status": estado or ("on_loan" if a.mode == "loan" else "in_use"),
        }
        if a.holder_type == "project":
            cambios["project_id"] = a.holder_project_id
        if a.holder_type == "department":
            cambios["department_id"] = a.holder_department_id
    aplicar_con_historial(db, activo, cambios, actor_id, nota=nota)


def prestar(db: Session, *, actor, asset_id: str, holder_type: str, holder_id: str, valid_to,
            valid_from=None, reason: Optional[str] = None, **kw) -> ALMAsignacion:
    """Préstamo de un activo con fecha de devolución (``valid_to``, obligatoria).

    El barrido diario avisa antes del vencimiento (`ALM_LOAN_REMINDER_DAYS`) y
    después, mientras no se devuelva."""
    return asignar(db, actor=actor, asset_id=asset_id, holder_type=holder_type, holder_id=holder_id,
                   valid_from=valid_from, valid_to=valid_to, reason=reason, mode="loan", **kw)


# ── Aprobación desde la bandeja ───────────────────────────────────────────────

def aplicar_decision(db: Session, asignacion_id: str, aprobado: bool, actor, nota: Optional[str]) -> None:
    """La decisión final del motor de aprobaciones (`fuentes.aplicar`)."""
    a = db.query(ALMAsignacion).filter(ALMAsignacion.id == asignacion_id).first()
    if a is None or a.status != "pending":
        return
    if aprobado:
        _activar(db, a, actor, aprobado=True)
    else:
        a.status = "rejected"
        a.ended_at = timeutil.utcnow()
        a.ended_by = getattr(actor, "id", None)
        a.end_reason = nota
        registrar_evento(db, evento="rejected", resource_type=a.resource_type, asignacion=a,
                         actor_id=getattr(actor, "id", None), motivo=nota)
    db.commit()


# ── Liberar, revocar, devolver ────────────────────────────────────────────────

def liberar(db: Session, asignacion_id: str, *, actor=None, motivo: Optional[str] = None,
            tipo: str = "released", origen: Optional[str] = None, fecha=None, commit: bool = True) -> ALMAsignacion:
    """Cierra una asignación activa (o cancela una pendiente).

    ``tipo``: ``released`` (se deja libre), ``revoked`` (se retira), ``returned``
    (devuelta), ``expired``, ``lost`` o ``transferred``. Una bolsa cierra
    también sus hijas. Un activo vuelve al almacén (o a ``lost`` si se perdió).
    ``origen`` (p. ej. ``offboarding``, ``usage``) queda en el historial.
    """
    if tipo not in ("released", "revoked", "returned", "expired", "lost", "transferred"):
        raise ErrorDeDominio(422, "alm_fin_invalido")
    a = _asignacion(db, asignacion_id)
    actor_id = getattr(actor, "id", None)
    if a.status == "pending":
        a.status = "cancelled"
        a.ended_at = timeutil.utcnow()
        a.ended_by = actor_id
        a.end_reason = motivo
        registrar_evento(db, evento="cancelled", resource_type=a.resource_type, asignacion=a,
                         actor_id=actor_id, motivo=motivo, datos={"origin": origen} if origen else None)
        from app.services.approval_engine import fuentes
        fuentes.cerrar(db, TIPO_DE_APROBACION, a.id, "cancelled", motivo or "")
        if commit:
            db.commit()
        return a
    if a.status != "active":
        raise ErrorDeDominio(409, "alm_asignacion_no_activa")
    if tipo == "revoked" and not (motivo or "").strip():
        raise ErrorDeDominio(422, "alm_motivo_obligatorio")
    dia = _fecha(fecha, "fecha") or timeutil.today()
    if dia < a.valid_from:
        dia = a.valid_from
    for hija in list(a.children or []):
        if hija.status in ("active", "pending"):
            liberar(db, hija.id, actor=actor, motivo=motivo, tipo=tipo, origen=origen, fecha=dia, commit=False)
    a.status = "ended"
    a.end_kind = tipo
    a.end_reason = motivo
    a.ended_on = dia
    a.ended_at = timeutil.utcnow()
    a.ended_by = actor_id
    registrar_evento(db, evento=tipo, resource_type=a.resource_type, asignacion=a, actor_id=actor_id,
                     motivo=motivo, datos={"origin": origen} if origen else None)
    if a.resource_type == "asset" and a.asset is not None:
        _reflejar_titular(db, a.asset, None, actor_id, estado="lost" if tipo == "lost" else "available", anterior=a)
    if commit:
        db.commit()
    return a


def devolver(db: Session, asignacion_id: str, *, actor, motivo: Optional[str] = None,
             checklist: Optional[list] = None, condition: Optional[str] = None,
             observations: Optional[str] = None, a_reparar: bool = False) -> ALMAsignacion:
    """Devolución de un activo (asignado o prestado): acta de devolución con
    checklist y estado, y el activo vuelve al almacén o va a reparación."""
    a = _asignacion(db, asignacion_id)
    if a.resource_type != "asset":
        raise ErrorDeDominio(422, "alm_devolucion_solo_activos")
    if a.status != "active":
        raise ErrorDeDominio(409, "alm_asignacion_no_activa")
    activo = a.asset
    if condition and condition not in ("new", "good", "fair", "poor"):
        raise ErrorDeDominio(422, "alm_estado_fisico_invalido")
    liberar(db, a.id, actor=actor, motivo=motivo, tipo="returned", commit=False)
    actor_id = getattr(actor, "id", None)
    if condition:
        from app.services.alm_ciclo_de_vida import aplicar_con_historial
        aplicar_con_historial(db, activo, {"condition": condition}, actor_id, nota="return")
    if a_reparar:
        from app.services.alm_ciclo_de_vida import aplicar_con_historial
        aplicar_con_historial(db, activo, {"status": "in_repair"}, actor_id, nota="return")
        registrar_evento(db, evento="repair_sent", resource_type="asset", asset_id=activo.id,
                         actor_id=actor_id, motivo=motivo)
    db.flush()
    from app.services import alm_actas
    if alm_actas.actas_activadas(db, a.organization_id):
        alm_actas.crear_acta(db, a, "return", actor, checklist=checklist, condition=condition,
                             observations=observations)
    db.commit()
    db.refresh(a)
    return a


def liberar_licencias_de_usuario(db: Session, user_id: str, *, actor=None, motivo: Optional[str] = None,
                                 origen: str = "offboarding") -> list[ALMAsignacion]:
    """Libera todas las licencias de una persona (baja, desactivación SCIM).

    Los activos NO se liberan: tienen que volver físicamente
    (`equipos_de_usuario` para abrir la tarea de devolución). Devuelve las
    asignaciones cerradas. Un solo commit."""
    cerradas = []
    for a in db.query(ALMAsignacion).filter(
            ALMAsignacion.holder_user_id == user_id, ALMAsignacion.resource_type == "license",
            ALMAsignacion.status.in_(("active", "pending"))).all():
        cerradas.append(liberar(db, a.id, actor=actor, motivo=motivo, tipo="released", origen=origen, commit=False))
    db.commit()
    return cerradas


# ── Consultas (fases 2 y 4) ───────────────────────────────────────────────────

def titulares_vigentes(db: Session, license_id: str, dia: Optional[date] = None) -> list[ALMAsignacion]:
    """Asignaciones de la licencia que cuentan ese día (hoy por defecto), bolsas e hijas incluidas."""
    dia = dia or timeutil.today()
    filas = db.query(ALMAsignacion).filter(
        ALMAsignacion.license_id == license_id, ALMAsignacion.status.in_(("active", "ended")),
        ALMAsignacion.valid_from <= dia,
        or_(ALMAsignacion.status == "active", ALMAsignacion.ended_on >= dia)).all()
    return [a for a in filas if a.vigente_en(dia)]


def asignaciones_de_usuario(db: Session, user_id: str, incluir_cerradas: bool = False) -> list[ALMAsignacion]:
    q = db.query(ALMAsignacion).filter(ALMAsignacion.holder_user_id == user_id)
    if not incluir_cerradas:
        q = q.filter(ALMAsignacion.status.in_(("active", "pending")))
    return q.order_by(ALMAsignacion.valid_from.desc()).all()


def equipos_de_usuario(db: Session, user_id: str) -> list[ALMAsignacion]:
    """Activos que la persona tiene ahora (asignados o prestados)."""
    return db.query(ALMAsignacion).filter(
        ALMAsignacion.holder_user_id == user_id, ALMAsignacion.resource_type == "asset",
        ALMAsignacion.status == "active").all()


def asignacion_vigente_de_activo(db: Session, asset_id: str) -> Optional[ALMAsignacion]:
    return db.query(ALMAsignacion).filter(
        ALMAsignacion.asset_id == asset_id, ALMAsignacion.status.in_(("active", "pending"))).first()


# ── Pico concurrente ──────────────────────────────────────────────────────────

def registrar_pico(db: Session, license_id: str, pico: int, medido_en: Optional[datetime] = None,
                   fuente: str = "manual", actor_id: Optional[str] = None, commit: bool = True) -> ALMPicoConcurrencia:
    """Anota una medida de uso simultáneo y deja en la licencia el máximo de la
    ventana `ALM_CONCURRENT_PEAK_WINDOW_DAYS`. Lo llama la fase 2 (o una persona)."""
    from datetime import timedelta
    lic = _licencia(db, license_id)
    try:
        pico = int(pico)
    except (TypeError, ValueError):
        raise ErrorDeDominio(422, "alm_pico_invalido")
    if pico < 0:
        raise ErrorDeDominio(422, "alm_pico_invalido")
    medido_en = medido_en or timeutil.utcnow()
    fila = ALMPicoConcurrencia(license_id=lic.id, peak=pico, measured_at=medido_en, source=fuente or "manual")
    fila.organization_id = lic.organization_id
    db.add(fila)
    db.flush()
    from app.services.alm_ajustes import ajuste_int
    ventana = ajuste_int(db, "ALM_CONCURRENT_PEAK_WINDOW_DAYS", lic.organization_id)
    desde = timeutil.utcnow() - timedelta(days=max(1, ventana))
    maximo = max(((p.peak, p.measured_at) for p in db.query(ALMPicoConcurrencia).filter(
        ALMPicoConcurrencia.license_id == lic.id, ALMPicoConcurrencia.measured_at >= desde)),
        default=(pico, medido_en), key=lambda x: x[0])
    lic.concurrent_peak, lic.concurrent_peak_at = maximo
    registrar_evento(db, evento="peak_recorded", resource_type="license", license_id=lic.id,
                     actor_id=actor_id, datos={"peak": pico, "source": fuente})
    if commit:
        db.commit()
    return fila


# ── Lectura para la interfaz ──────────────────────────────────────────────────

def serializar(db: Session, a: ALMAsignacion) -> dict:
    hoy = timeutil.today()
    return {
        "id": a.id, "resource_type": a.resource_type, "license_id": a.license_id, "asset_id": a.asset_id,
        "resource_name": (a.license.name if a.license is not None else a.asset.name if a.asset is not None else None),
        "holder_type": a.holder_type, "holder_id": a.holder_id,
        "holder_name": nombre_de_titular(db, a.holder_type, a.holder_id),
        "mode": a.mode, "parent_id": a.parent_id, "quantity": a.quantity, "status": a.status,
        "valid_from": a.valid_from.isoformat() if a.valid_from else None,
        "valid_to": a.valid_to.isoformat() if a.valid_to else None,
        "ended_on": a.ended_on.isoformat() if a.ended_on else None,
        "end_kind": a.end_kind, "end_reason": a.end_reason, "reason": a.reason, "source": a.source,
        "assigned_by": a.assigned_by, "assigned_by_name": a.assignor.full_name if a.assignor else None,
        "assigned_at": a.assigned_at.isoformat() if a.assigned_at else None,
        "approved_at": a.approved_at.isoformat() if a.approved_at else None,
        "charge_project_id": a.charge_project_id, "charge_cost_center_id": a.charge_cost_center_id,
        "charge_client_id": a.charge_client_id, "rebillable": a.rebillable, "notes": a.notes,
        "used_in_pool": usados_en_bolsa(db, a) if a.mode == "pool" else None,
        "overdue": bool(a.mode == "loan" and a.status == "active" and a.valid_to and a.valid_to < hoy),
        "days_to_due": (a.valid_to - hoy).days if a.valid_to and a.status == "active" else None,
    }


def listar(db: Session, *, license_id=None, asset_id=None, holder_type=None, holder_id=None,
           status: Optional[Iterable[str]] = None, mode: Optional[str] = None, vencidos: bool = False,
           resource_type: Optional[str] = None, pagina=None):
    from app.core.paginacion import paginar
    q = db.query(ALMAsignacion)
    if resource_type:
        q = q.filter(ALMAsignacion.resource_type == resource_type)
    if license_id:
        q = q.filter(ALMAsignacion.license_id == license_id)
    if asset_id:
        q = q.filter(ALMAsignacion.asset_id == asset_id)
    if holder_type:
        if holder_type not in COLUMNA_DE_TITULAR:
            raise ErrorDeDominio(422, "alm_titular_tipo_invalido")
        q = q.filter(ALMAsignacion.holder_type == holder_type)
        if holder_id:
            q = q.filter(getattr(ALMAsignacion, COLUMNA_DE_TITULAR[holder_type]) == holder_id)
    if status:
        q = q.filter(ALMAsignacion.status.in_(list(status)))
    if mode:
        q = q.filter(ALMAsignacion.mode == mode)
    if vencidos:
        q = q.filter(ALMAsignacion.status == "active", ALMAsignacion.valid_to.isnot(None),
                     ALMAsignacion.valid_to < timeutil.today())
    q = q.order_by(ALMAsignacion.status, ALMAsignacion.valid_from.desc())
    return paginar(q, pagina, "alm.assignments").mapear(lambda a: serializar(db, a))


def historial(db: Session, *, license_id=None, asset_id=None, contract_id=None, holder_type=None,
              holder_id=None, pagina=None):
    """Quién tuvo qué, cuándo y por qué: los eventos, del más reciente al más antiguo."""
    from app.core.paginacion import paginar
    q = db.query(ALMEvento)
    if license_id:
        q = q.filter(ALMEvento.license_id == license_id)
    if asset_id:
        q = q.filter(ALMEvento.asset_id == asset_id)
    if contract_id:
        q = q.filter(ALMEvento.contract_id == contract_id)
    if holder_type:
        q = q.filter(ALMEvento.holder_type == holder_type)
        if holder_id:
            q = q.filter(ALMEvento.holder_id == holder_id)
    q = q.order_by(ALMEvento.created_at.desc(), ALMEvento.id.desc())

    def fila(e: ALMEvento) -> dict:
        try:
            datos = json.loads(e.data) if e.data else None
        except ValueError:
            datos = None
        return {"id": e.id, "event": e.event, "resource_type": e.resource_type, "license_id": e.license_id,
                "asset_id": e.asset_id, "contract_id": e.contract_id, "assignment_id": e.assignment_id,
                "holder_type": e.holder_type, "holder_id": e.holder_id, "holder_name": e.holder_name,
                "actor_id": e.actor_id, "actor_name": e.actor.full_name if e.actor else None,
                "reason": e.reason, "data": datos, "created_at": e.created_at.isoformat() if e.created_at else None}
    return paginar(q, pagina, "alm.history").mapear(fila)


# ── Barrido diario ────────────────────────────────────────────────────────────

def vencer_asignaciones(db: Session) -> int:
    """Cierra las asignaciones de licencia con fin previsto pasado (``expired``).

    Los préstamos de activos no se cierran solos (el equipo tiene que volver):
    los avisa `alm_renovaciones`."""
    hoy = timeutil.today()
    n = 0
    for a in db.query(ALMAsignacion).filter(
            ALMAsignacion.status == "active", ALMAsignacion.resource_type == "license",
            ALMAsignacion.valid_to.isnot(None), ALMAsignacion.valid_to < hoy).all():
        liberar(db, a.id, actor=None, motivo=None, tipo="expired", origen="system", fecha=a.valid_to, commit=False)
        n += 1
    db.commit()
    return n
