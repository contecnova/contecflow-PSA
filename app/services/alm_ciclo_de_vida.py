"""Ciclo de vida de los activos de ALM: historial, CI, vencimientos y renovacion.

Auditoria 2026-11: habia dos inventarios. Esto venia de los activos del Service
Desk (`sd_assets`, sin pantalla) y ahora trabaja sobre `alm_assets`, el que
tiene pantalla. Lo que no se trajo, y por que:

- la amortizacion propia (vida fija de 5 anos en el codigo): el serializador de
  ALM ya calcula el valor contable con `depreciation_years` de cada activo;
- las auditorias de licencias y de software: ALM las tiene sobre licencias e
  instalaciones de verdad (`/alm/compliance`), no sobre contadores escritos a
  mano en el activo.
"""
from __future__ import annotations

from datetime import date, timedelta
from typing import Optional
from uuid import uuid4

from sqlalchemy.orm import Session

from app.core import timeutil
from app.models.alm import ALMAsset, ALMAssetHistory
from app.core.errores import ErrorDeDominio

#: Fechas que vencen, en el orden en que se leen.
VENCIMIENTOS = ("warranty_expiry", "eol_date", "lease_expiry", "next_maintenance_date")

#: Campos cuyo cambio queda en el historial.
CAMPOS_CON_HISTORIAL = (
    "name", "status", "condition", "assigned_to_id", "location", "ci_id", "serial_number",
    "warranty_expiry", "eol_date", "lease_expiry", "next_maintenance_date", "maintenance_contract",
    "project_id", "department_id", "disposal_reason", "disposal_method",
)


def _texto(v) -> Optional[str]:
    if v is None:
        return None
    v = getattr(v, "value", v)
    return (v.isoformat() if isinstance(v, date) else str(v))[:500]


def anotar(db: Session, activo: ALMAsset, campo: str, antes, despues,
           usuario_id: Optional[str], nota: Optional[str] = None) -> None:
    """Una fila de historial si el valor cambia de verdad."""
    if _texto(antes) == _texto(despues):
        return
    db.add(ALMAssetHistory(
        organization_id=activo.organization_id, asset_id=activo.id, field_name=campo,
        old_value=_texto(antes), new_value=_texto(despues), changed_by=usuario_id, note=nota,
    ))


def aplicar_con_historial(db: Session, activo: ALMAsset, cambios: dict, usuario_id: Optional[str],
                          nota: Optional[str] = None) -> None:
    for campo, valor in cambios.items():
        if campo in CAMPOS_CON_HISTORIAL:
            anotar(db, activo, campo, getattr(activo, campo), valor, usuario_id, nota)
        setattr(activo, campo, valor)


def exigir_ci(db: Session, ci_id: Optional[str], current_user) -> None:
    """El CI tiene que existir y verse desde la organizacion de quien enlaza."""
    if not ci_id:
        return
    from app.services.service_desk.cmdb_service import get_scoped_ci_by_id
    if get_scoped_ci_by_id(db, current_user, ci_id) is None:
        raise ErrorDeDominio(422, "El CI no existe")


def activo_o_404(db: Session, activo_id: str) -> ALMAsset:
    a = db.query(ALMAsset).filter(ALMAsset.id == activo_id, ALMAsset.is_active.is_(True)).first()
    if a is None:
        raise ErrorDeDominio(404, "Activo no encontrado")
    return a


def historial(db: Session, activo_id: str) -> list[dict]:
    filas = (db.query(ALMAssetHistory).filter(ALMAssetHistory.asset_id == activo_id)
             .order_by(ALMAssetHistory.changed_at.desc()).all())
    return [{
        "id": h.id, "field": h.field_name, "old_value": h.old_value, "new_value": h.new_value,
        "note": h.note, "user_name": h.changed_by_user.full_name if h.changed_by_user else None,
        "changed_at": h.changed_at.isoformat() if h.changed_at else None,
    } for h in filas]


def activos_del_ci(db: Session, ci_id: str) -> list[ALMAsset]:
    return (db.query(ALMAsset).filter(ALMAsset.ci_id == ci_id, ALMAsset.is_active.is_(True))
            .order_by(ALMAsset.name).all())


def proximos_vencimientos(db: Session, dias: Optional[int] = None, *, p=None) -> list[dict]:
    """Una fila por fecha que vence en los proximos `dias` (incluidas las de hoy).

    Con ``p`` (``Periodo`` con ``sentido="futuro"``, periodo libre 16-11-2026)
    la ventana son los dias de calendario ``[p.fecha_desde, p.fecha_hasta]``;
    ``days_remaining`` sigue contando desde hoy.
    Un activo retirado no vence. Ordenadas de la mas cercana a la mas lejana.
    """
    hoy = timeutil.today()
    if p is not None:
        inicio, fin = p.fecha_desde, p.fecha_hasta
    else:
        inicio, fin = hoy, hoy + timedelta(days=dias or 0)
    filas = []
    for a in db.query(ALMAsset).filter(ALMAsset.is_active.is_(True), ALMAsset.status.notin_(("retired", "disposed"))):
        for campo in VENCIMIENTOS:
            fecha = getattr(a, campo)
            if fecha is None:
                continue
            quedan = (fecha - hoy).days
            if inicio <= fecha <= fin:
                filas.append({
                    "asset_id": a.id, "name": a.name, "asset_tag": a.asset_tag,
                    "type": _texto(a.type), "expiry_type": campo, "expiry_date": fecha.isoformat(),
                    "days_remaining": quedan, "refresh_ticket_id": a.refresh_ticket_id,
                })
    return sorted(filas, key=lambda f: f["days_remaining"])


def _ticket_abierto(db: Session, activo: ALMAsset):
    from app.models.service_desk import Ticket, TicketStatus
    if not activo.refresh_ticket_id:
        return None
    t = db.get(Ticket, activo.refresh_ticket_id)
    cerrados = {TicketStatus.resolved, TicketStatus.closed, TicketStatus.cancelled}
    return t if t is not None and t.status not in cerrados else None


def abrir_ticket_de_renovacion(db: Session, activo: ALMAsset, usuario_id: Optional[str]) -> dict:
    """Peticion de servicio para renovar o sustituir el activo. No confirma.

    Si ya hay una abierta para este activo, la devuelve en vez de abrir otra.
    Nace en la organizacion del activo, con su CI, y por el mismo numerador
    que el resto de tickets.
    """
    from app.models.service_desk import Ticket, TicketPriority, TicketStatus, TicketType
    from app.services.sla_service import next_ticket_number

    abierto = _ticket_abierto(db, activo)
    if abierto is not None:
        return {"ticket_id": abierto.id, "number": abierto.number, "created": False}

    vence = [(campo, getattr(activo, campo)) for campo in VENCIMIENTOS if getattr(activo, campo)]
    campo, fecha = min(vence, key=lambda x: x[1]) if vence else (None, None)
    t = Ticket(
        id=str(uuid4()),
        organization_id=activo.organization_id,
        number=next_ticket_number(TicketType.service_request, db, activo.organization_id),
        ticket_type=TicketType.service_request,
        status=TicketStatus.new,
        priority=TicketPriority.p3_medium,
        title=activo.name,
        description=activo.name,
        requester_user_id=usuario_id,
        created_by_user_id=usuario_id,
        ci_id=activo.ci_id,
        source="asset_lifecycle",
    )
    # Traduccion en tiempo real: texto del sistema en el idioma de cada cual.
    from app.services.traduccion.textos_del_sistema import aplicar
    aplicar(db, t, "alm_renewal", {"name": activo.name, "tag": activo.asset_tag, "serial": activo.serial_number,
                                   "field": campo, "due": fecha.isoformat() if fecha else None})
    db.add(t)
    db.flush()
    anotar(db, activo, "refresh_ticket_id", activo.refresh_ticket_id, t.id, usuario_id, f"Ticket {t.number}")
    activo.refresh_ticket_id = t.id
    return {"ticket_id": t.id, "number": t.number, "created": True}


def abrir_ticket_de_renovacion_confirmado(db: Session, activo_id: str, usuario_id: Optional[str]) -> dict:
    """La accion del endpoint: busca el activo (404), abre el ticket y confirma."""
    datos = abrir_ticket_de_renovacion(db, activo_o_404(db, activo_id), usuario_id)
    db.commit()
    return datos


def escanear_vencimientos(db: Session) -> dict:
    """Pasada diaria: un ticket de renovacion por activo que vence pronto.

    Cuanto es «pronto» lo decide `SD_ASSET_REFRESH_DAYS` de la organizacion
    del activo. Auditoria 2026-11: antes buscaba si ya habia ticket por un
    `LIKE` sobre el titulo y lo creaba sin organizacion, asi que nadie lo veia.
    """
    from app.services import settings_service as ss

    mayor = 0
    dias_de: dict[Optional[str], int] = {}
    orgs = {o for (o,) in db.query(ALMAsset.organization_id).filter(ALMAsset.is_active.is_(True)).distinct()}
    for org in orgs:
        dias_de[org] = ss.get_runtime_int(db, "SD_ASSET_REFRESH_DAYS", org) or 0
        mayor = max(mayor, dias_de[org])

    creados = existentes = 0
    vistos: set[str] = set()
    for fila in proximos_vencimientos(db, mayor):
        if fila["asset_id"] in vistos:
            continue
        activo = db.get(ALMAsset, fila["asset_id"])
        dias = dias_de.get(activo.organization_id, 0)
        if dias <= 0 or fila["days_remaining"] > dias:  # 0 apaga el escaneo
            continue
        vistos.add(activo.id)
        if abrir_ticket_de_renovacion(db, activo, None)["created"]:
            creados += 1
        else:
            existentes += 1
    return {"vencen": len(vistos), "tickets_creados": creados, "ya_abiertos": existentes}


# ── Ciclo de vida del hardware (fase 1, 16-11-2026) ───────────────────────────
#
# compra (ordered) → almacén (available) → asignado (in_use) | préstamo
# (on_loan) → reparación (in_repair) → baja (retired) → reciclaje (disposed).
# Asignar, prestar y devolver van por `alm_asignaciones` (crean la asignación y
# el acta); el resto de pasos, por `transicion`. Cada paso queda en el
# historial de campos (`alm_asset_history`) y en el inmutable (`alm_eventos`).

#: acción → (estados desde los que se puede, estado al que lleva). `None`: lo decide la acción.
TRANSICIONES: dict[str, tuple[frozenset, Optional[str]]] = {
    "receive":      (frozenset({"ordered"}), "available"),
    "repair_sent":  (frozenset({"available", "in_use", "on_loan"}), "in_repair"),
    "repair_done":  (frozenset({"in_repair"}), None),        # vuelve a in_use / on_loan si sigue con titular
    # Desde in_use/on_loan solo si no hay asignación vigente (activos anteriores a la fase 1).
    "retired":      (frozenset({"ordered", "available", "in_use", "on_loan", "in_repair", "lost", "stolen"}), "retired"),
    "disposed":     (frozenset({"retired"}), "disposed"),
    "lost":         (frozenset({"available", "in_use", "on_loan", "in_repair"}), "lost"),
    "stolen":       (frozenset({"available", "in_use", "on_loan", "in_repair"}), "stolen"),
    "found":        (frozenset({"lost", "stolen"}), "available"),
}
#: Acciones de `alm_asignaciones` y desde qué estados se ofrecen.
ACCIONES_DE_ASIGNACION = {"assign": frozenset({"available"}), "lend": frozenset({"available"}),
                          "return": frozenset({"in_use", "on_loan"})}
MOTIVOS_DE_BAJA = ("obsolete", "broken", "lost", "stolen", "sold", "other")
METODOS_DE_RECICLAJE = ("recycle", "donate", "sell", "destroy")
#: Estados que solo se alcanzan con una acción (no editando el activo).
ESTADOS_POR_ACCION = frozenset({"in_use", "on_loan", "in_repair", "retired", "disposed", "lost", "stolen"})


def acciones_posibles(activo: ALMAsset) -> list[str]:
    estado = getattr(activo.status, "value", activo.status)
    salida = [a for a, origenes in ACCIONES_DE_ASIGNACION.items() if estado in origenes]
    salida += [a for a, (origenes, _) in TRANSICIONES.items() if estado in origenes]
    return salida


def transicion(db: Session, activo_id: str, accion: str, actor, *, motivo: Optional[str] = None,
               datos: Optional[dict] = None) -> ALMAsset:
    """Un paso del ciclo de vida que no es asignar, prestar ni devolver.

    ``datos``: ``repair_sent`` → {vendor, ticket, expected_back, cost};
    ``retired`` → {reason: MOTIVOS_DE_BAJA}; ``disposed`` → {method:
    METODOS_DE_RECICLAJE, value, date}. Perder o robar un activo con titular
    cierra su asignación (``lost``)."""
    from app.services import alm_asignaciones as asig
    if accion not in TRANSICIONES:
        raise ErrorDeDominio(422, "alm_accion_invalida")
    activo = activo_o_404(db, activo_id)
    estado = getattr(activo.status, "value", activo.status)
    origenes, destino = TRANSICIONES[accion]
    if estado not in origenes:
        raise ErrorDeDominio(409, "alm_transicion_no_permitida")
    datos = dict(datos or {})
    actor_id = getattr(actor, "id", None)
    vigente = asig.asignacion_vigente_de_activo(db, activo.id)
    cambios: dict = {}
    if accion == "repair_done":
        destino = ("on_loan" if vigente.mode == "loan" else "in_use") if vigente is not None and vigente.status == "active"             else "available"
    if accion == "retired":
        if vigente is not None:
            raise ErrorDeDominio(409, "alm_activo_con_titular")
        razon = datos.get("reason") or "other"
        if razon not in MOTIVOS_DE_BAJA:
            raise ErrorDeDominio(422, "alm_motivo_de_baja_invalido")
        cambios.update(disposal_reason=razon, disposal_date=timeutil.today())
    if accion == "disposed":
        metodo = datos.get("method")
        if metodo not in METODOS_DE_RECICLAJE:
            raise ErrorDeDominio(422, "alm_metodo_de_reciclaje_invalido")
        valor = datos.get("value")
        try:
            valor = float(valor) if valor not in (None, "") else None
        except (TypeError, ValueError):
            raise ErrorDeDominio(422, "alm_importe_invalido")
        cambios.update(disposal_method=metodo, disposal_value=valor)
    if accion in ("lost", "stolen") and vigente is not None and vigente.status == "active":
        asig.liberar(db, vigente.id, actor=actor, motivo=motivo or accion, tipo="lost", commit=False)
    elif accion in ("lost", "stolen") and vigente is not None and vigente.status == "pending":
        asig.liberar(db, vigente.id, actor=actor, motivo=motivo or accion, commit=False)
    cambios["status"] = destino
    aplicar_con_historial(db, activo, cambios, actor_id, nota=accion)
    asig.registrar_evento(db, evento=accion, resource_type="asset", asset_id=activo.id, actor_id=actor_id,
                          motivo=motivo, datos=datos or None)
    db.commit()
    db.refresh(activo)
    return activo
