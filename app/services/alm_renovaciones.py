"""Renovaciones, avisos de vencimiento y préstamos (licencias y hardware, fase 3 — 16-11-2026).

**Fechas.** Un contrato renueva en ``renewal_date`` (o, sin ella, ``end_date``);
el preaviso para cancelar o reducir acaba ``notice_days`` antes. Una licencia
sin contrato renueva en ``expiry_date`` con preaviso
`ALM_LICENSE_NOTICE_DAYS`. (Una licencia con contrato renueva con él.)

**Avisos** (barrido diario `escanear`, una vez por fecha y tipo gracias a
`ALMRenewalAlert`): ``notice`` cuando faltan `ALM_RENEWAL_LEAD_DAYS` para que
acabe el preaviso, ``deadline`` el último día de preaviso, ``expired`` si
vence sin renovar y ``auto_renewed`` al prorrogarse. Van al responsable del
contrato o, sin él, a los roles de `ALM_RENEWAL_NOTIFY_ROLES`. Préstamos:
``loan_due`` a la persona `ALM_LOAN_REMINDER_DAYS` antes, y ``loan_overdue``
cada semana mientras no se devuelva (a la persona y a quien prestó).

**Decisión** (`decidir`): renovar, reducir (asientos nuevos o coste nuevo) o
cancelar, con el uso que había al decidir (`uso_de_licencia`). Se aplica al
llegar la fecha: cancelar cierra el contrato y libera sus licencias; reducir
cambia asientos/coste y prorroga; renovar prorroga. Sin decisión: si
``auto_renew``, se prorroga un periodo (``billing_cycle``); si no, vence.

**Punto de lectura del uso (fase 2).** `uso_de_licencia(db, license_id)` llama
a `app.services.alm_uso.uso_de_licencia(db, license_id)` si existe y, si no,
responde con lo que sabe la fase 1 (asignaciones y pico) y ``source =
"assignments"``. Forma del diccionario (la fase 2 debe devolver estas claves;
puede añadir otras):

    {"assigned": int, "total": int | None, "in_use": int | None,
     "underused": int | None, "unused": int | None, "no_data": int | None,
     "concurrent_peak": int | None, "source": str, "measured_at": str | None}
"""
from __future__ import annotations

import json
import logging
from datetime import date, timedelta
from typing import Optional

from sqlalchemy.orm import Session

from app.core import timeutil
from app.core.errores import ErrorDeDominio
from app.models.alm import ALMAsignacion, ALMContract, ALMLicense, ALMRenewalAlert, ALMRenovacion

logger = logging.getLogger(__name__)

DECISIONES = ("renew", "reduce", "cancel")
MESES_POR_CICLO = {"monthly": 1, "quarterly": 3, "annual": 12, "biennial": 24, "one_time": 12}


# ── Uso (punto de lectura de la fase 2) ───────────────────────────────────────

def uso_de_licencia(db: Session, license_id: str) -> dict:
    try:
        from app.services.alm_uso import uso_de_licencia as uso_real  # fase 2
    except ImportError:
        uso_real = None
    if uso_real is not None:
        try:
            datos = uso_real(db, license_id)
            if isinstance(datos, dict):
                return datos
        except Exception:
            logger.warning("alm_uso.uso_de_licencia(%s) falló; uso de la fase 1", license_id, exc_info=True)
    from app.services.alm_asignaciones import asientos_usados
    lic = db.get(ALMLicense, license_id)
    if lic is None:
        raise ErrorDeDominio(404, "alm_licencia_no_encontrada")
    return {"assigned": asientos_usados(db, lic), "total": lic.total_seats, "in_use": None, "underused": None,
            "unused": None, "no_data": None, "concurrent_peak": lic.concurrent_peak, "source": "assignments",
            "measured_at": lic.concurrent_peak_at.isoformat() if lic.concurrent_peak_at else None}


# ── Fechas ────────────────────────────────────────────────────────────────────

def sumar_meses(d: date, meses: int) -> date:
    import calendar
    y, m = divmod(d.month - 1 + meses, 12)
    y += d.year
    m += 1
    return date(y, m, min(d.day, calendar.monthrange(y, m)[1]))


def fecha_de_renovacion(entidad) -> Optional[date]:
    if isinstance(entidad, ALMContract):
        return entidad.renewal_date or entidad.end_date
    return entidad.expiry_date


def dias_de_preaviso(db: Session, entidad) -> int:
    if isinstance(entidad, ALMContract):
        return int(entidad.notice_days or 0)
    from app.services.alm_ajustes import ajuste_int
    return ajuste_int(db, "ALM_LICENSE_NOTICE_DAYS", entidad.organization_id)


def _estado(v) -> str:
    return getattr(v, "value", v)


def _vigente(entidad) -> bool:
    if not entidad.is_active:
        return False
    if isinstance(entidad, ALMContract):
        return _estado(entidad.status) == "active"
    return _estado(entidad.status) not in ("cancelled",) and entidad.contract_id is None


def decision_vigente(db: Session, entity_type: str, entidad) -> Optional[ALMRenovacion]:
    termino = fecha_de_renovacion(entidad)
    if termino is None:
        return None
    col = ALMRenovacion.contract_id if entity_type == "contract" else ALMRenovacion.license_id
    return (db.query(ALMRenovacion).filter(col == entidad.id, ALMRenovacion.term_date == termino,
                                           ALMRenovacion.status == "pending")
            .order_by(ALMRenovacion.decided_at.desc()).first())


# ── Listado y decisión ────────────────────────────────────────────────────────

def _fila(db: Session, entity_type: str, e, hoy: date) -> dict:
    termino = fecha_de_renovacion(e)
    preaviso = dias_de_preaviso(db, e)
    limite = termino - timedelta(days=preaviso) if termino else None
    dec = decision_vigente(db, entity_type, e)
    if entity_type == "contract":
        uso = None
        lics = [lic for lic in (e.licenses or []) if lic.is_active]
        if lics:
            usos = [uso_de_licencia(db, lic.id) for lic in lics]
            uso = {"licenses": [{"license_id": lic.id, "name": lic.name, **u} for lic, u in zip(lics, usos)]}
        coste = e.annual_value
        nombre = e.title
    else:
        uso = uso_de_licencia(db, e.id)
        coste = e.annual_cost
        nombre = e.name
    return {
        "entity_type": entity_type, "id": e.id, "name": nombre,
        "vendor_name": e.vendor.name if e.vendor else None,
        "renewal_date": termino.isoformat() if termino else None,
        "notice_days": preaviso, "notice_deadline": limite.isoformat() if limite else None,
        "days_to_renewal": (termino - hoy).days if termino else None,
        "days_to_deadline": (limite - hoy).days if limite else None,
        "auto_renew": bool(getattr(e, "auto_renew", False)), "annual_cost": coste,
        "total_seats": getattr(e, "total_seats", None),
        "billing_cycle": _estado(getattr(e, "billing_cycle", None)),
        "owner_id": getattr(e, "owner_id", None),
        "decision": None if dec is None else {
            "id": dec.id, "decision": dec.decision, "new_seats": dec.new_seats,
            "new_annual_cost": dec.new_annual_cost, "reason": dec.reason,
            "decided_by_name": dec.decider.full_name if dec.decider else None,
            "decided_at": dec.decided_at.isoformat() if dec.decided_at else None},
        "usage": uso,
    }


def proximas(db: Session, dias: int = 120) -> list[dict]:
    """Contratos y licencias que renuevan en los próximos ``dias`` (y los ya pasados sin resolver)."""
    hoy = timeutil.today()
    tope = hoy + timedelta(days=max(0, dias))
    salida = []
    for c in db.query(ALMContract).filter(ALMContract.is_active.isnot(False)).all():
        t = fecha_de_renovacion(c)
        if _vigente(c) and t and t <= tope:
            salida.append(_fila(db, "contract", c, hoy))
    for lic in db.query(ALMLicense).filter(ALMLicense.is_active.is_(True), ALMLicense.contract_id.is_(None)).all():
        t = fecha_de_renovacion(lic)
        if _vigente(lic) and t and t <= tope:
            salida.append(_fila(db, "license", lic, hoy))
    return sorted(salida, key=lambda f: f["renewal_date"] or "9999")


def _entidad(db: Session, entity_type: str, entity_id: str):
    if entity_type == "contract":
        e = db.query(ALMContract).filter(ALMContract.id == entity_id, ALMContract.is_active.isnot(False)).first()
    elif entity_type == "license":
        e = db.query(ALMLicense).filter(ALMLicense.id == entity_id, ALMLicense.is_active.is_(True)).first()
    else:
        raise ErrorDeDominio(422, "alm_entidad_invalida")
    if e is None:
        raise ErrorDeDominio(404, "alm_entidad_no_encontrada")
    return e


def decidir(db: Session, actor, entity_type: str, entity_id: str, decision: str, *,
            new_seats: Optional[int] = None, new_annual_cost: Optional[float] = None,
            reason: Optional[str] = None) -> dict:
    """Anota la decisión para la próxima renovación (sustituye a la anterior, que queda en el historial)."""
    if decision not in DECISIONES:
        raise ErrorDeDominio(422, "alm_decision_invalida")
    e = _entidad(db, entity_type, entity_id)
    termino = fecha_de_renovacion(e)
    if termino is None:
        raise ErrorDeDominio(409, "alm_sin_fecha_de_renovacion")
    if decision == "reduce":
        if new_seats is None and new_annual_cost is None:
            raise ErrorDeDominio(422, "alm_reducir_sin_cambios")
        if new_seats is not None:
            if entity_type != "license":
                raise ErrorDeDominio(422, "alm_reducir_asientos_solo_licencias")
            new_seats = int(new_seats)
            if new_seats < 0 or (e.total_seats is not None and new_seats >= e.total_seats):
                raise ErrorDeDominio(422, "alm_reducir_asientos_invalido")
        if new_annual_cost is not None and float(new_annual_cost) < 0:
            raise ErrorDeDominio(422, "alm_importe_invalido")
    if decision == "cancel" and not (reason or "").strip():
        raise ErrorDeDominio(422, "alm_motivo_obligatorio")
    col = ALMRenovacion.contract_id if entity_type == "contract" else ALMRenovacion.license_id
    for anterior in db.query(ALMRenovacion).filter(col == e.id, ALMRenovacion.term_date == termino,
                                                    ALMRenovacion.status == "pending"):
        anterior.status = "superseded"
    uso = (uso_de_licencia(db, e.id) if entity_type == "license"
           else _fila(db, "contract", e, timeutil.today())["usage"])
    r = ALMRenovacion(entity_type=entity_type, contract_id=e.id if entity_type == "contract" else None,
                      license_id=e.id if entity_type == "license" else None, term_date=termino, decision=decision,
                      new_seats=new_seats, new_annual_cost=float(new_annual_cost) if new_annual_cost is not None else None,
                      reason=reason, usage_snapshot=json.dumps(uso, default=str), decided_by=getattr(actor, "id", None))
    r.organization_id = e.organization_id
    db.add(r)
    if decision == "cancel" and entity_type == "contract":
        e.auto_renew = False
    from app.services.alm_asignaciones import registrar_evento
    registrar_evento(db, evento="renewal_decided", resource_type=entity_type,
                     license_id=e.id if entity_type == "license" else None,
                     contract_id=e.id if entity_type == "contract" else None, actor_id=getattr(actor, "id", None),
                     motivo=reason, datos={"decision": decision, "term": termino, "new_seats": new_seats,
                                           "new_annual_cost": new_annual_cost})
    from app.services.audit import audit_log
    audit_log(db, actor, "UPDATE", f"alm_{entity_type}", e.id, getattr(e, "title", None) or getattr(e, "name", None),
              new_values={"renewal_decision": decision, "term": termino.isoformat()})
    db.commit()
    return _fila(db, entity_type, e, timeutil.today())


# ── Aplicar al llegar la fecha ────────────────────────────────────────────────

def _prorrogar(e, meses: int) -> date:
    termino = fecha_de_renovacion(e)
    nuevo = sumar_meses(termino, meses)
    if isinstance(e, ALMContract):
        if e.renewal_date:
            e.renewal_date = nuevo
        if e.end_date:
            e.end_date = sumar_meses(e.end_date, meses) if e.end_date >= termino else nuevo
    else:
        e.expiry_date = nuevo
    return nuevo


def _cerrar_licencias(db: Session, licencias, motivo: str) -> None:
    from app.services.alm_asignaciones import liberar
    for lic in licencias:
        for a in db.query(ALMAsignacion).filter(ALMAsignacion.license_id == lic.id, ALMAsignacion.parent_id.is_(None),
                                                ALMAsignacion.status.in_(("active", "pending"))).all():
            liberar(db, a.id, actor=None, motivo=motivo, tipo="released", origen="renewal", commit=False)
        lic.status = "cancelled"


def aplicar_al_vencer(db: Session, entity_type: str, e, hoy: date) -> Optional[str]:
    """Lo que toca hacer si la renovación ya llegó. Devuelve el evento (o None)."""
    from app.services.alm_asignaciones import registrar_evento
    termino = fecha_de_renovacion(e)
    if termino is None or termino > hoy or not _vigente(e):
        return None
    dec = decision_vigente(db, entity_type, e)
    ciclo = MESES_POR_CICLO.get(_estado(getattr(e, "billing_cycle", None)) or "annual", 12)
    if entity_type == "license":
        ciclo = 12
    kw = {"resource_type": entity_type, "license_id": e.id if entity_type == "license" else None,
          "contract_id": e.id if entity_type == "contract" else None}
    if dec is not None and dec.decision == "cancel":
        if entity_type == "contract":
            e.status = "cancelled"
            e.auto_renew = False
            _cerrar_licencias(db, [lic for lic in (e.licenses or []) if lic.is_active], dec.reason or "")
        else:
            _cerrar_licencias(db, [e], dec.reason or "")
        evento = "cancelled_at_term"
    elif dec is not None or getattr(e, "auto_renew", False):
        if dec is not None and dec.decision == "reduce":
            if dec.new_seats is not None and entity_type == "license":
                e.total_seats = dec.new_seats
                registrar_evento(db, evento="seats_changed", **kw, datos={"seats": dec.new_seats})
        if dec is not None and dec.new_annual_cost is not None:
            if entity_type == "contract":
                e.annual_value = dec.new_annual_cost
            else:
                e.annual_cost = dec.new_annual_cost
        nuevo = _prorrogar(e, ciclo)
        evento = "renewed" if dec is not None else "auto_renewed"
        registrar_evento(db, evento=evento, **kw, datos={"new_term": nuevo})
        if dec is not None:
            dec.status = "applied"
            dec.applied_at = timeutil.utcnow()
        return evento
    else:
        e.status = "expired"
        evento = "contract_expired"
    if dec is not None:
        dec.status = "applied"
        dec.applied_at = timeutil.utcnow()
    registrar_evento(db, evento=evento, **kw, datos={"term": termino})
    return evento


# ── Avisos ────────────────────────────────────────────────────────────────────

def _ya_avisado(db: Session, entity_type: str, entity_id: str, kind: str, referencia: date) -> bool:
    return db.query(ALMRenewalAlert.id).filter(
        ALMRenewalAlert.entity_type == entity_type, ALMRenewalAlert.entity_id == entity_id,
        ALMRenewalAlert.kind == kind, ALMRenewalAlert.reference_date == referencia).first() is not None


def _destinatarios(db: Session, e) -> list[str]:
    from app.models.user import User
    from app.services.alm_ajustes import ajuste_lista
    if getattr(e, "owner_id", None):
        return [e.owner_id]
    roles = ajuste_lista(db, "ALM_RENEWAL_NOTIFY_ROLES", e.organization_id) or ["admin"]
    q = db.query(User.id).filter(User.role.in_(roles), User.is_active.is_(True))
    if e.organization_id:
        q = q.filter(User.organization_id == e.organization_id)
    return [i for (i,) in q.all()]


def _avisar(db: Session, entity_type: str, e, kind: str, referencia: date, dias: int, destinatarios: list[str],
            titulo: str, cuerpo: str, url: str) -> bool:
    if _ya_avisado(db, entity_type, e.id, kind, referencia):
        return False
    from app.services.notifications import notify_user
    for uid in dict.fromkeys(u for u in destinatarios if u):
        try:
            notify_user(db, uid, "system", titulo, body=cuerpo, resource=f"alm_{entity_type}", resource_id=e.id,
                        action_url=url)
        except Exception:
            logger.warning("aviso %s de %s %s a %s falló", kind, entity_type, e.id, uid, exc_info=True)
    alerta = ALMRenewalAlert(entity_type=entity_type, entity_id=e.id, kind=kind, reference_date=referencia,
                             alert_date=timeutil.today(), days_before=dias, is_sent=True, sent_at=timeutil.utcnow(),
                             recipient_id=destinatarios[0] if destinatarios else None)
    alerta.organization_id = e.organization_id
    db.add(alerta)
    db.flush()
    return True


def _avisos_de_renovacion(db: Session, entity_type: str, e, hoy: date) -> int:
    from app.services.alm_ajustes import ajuste_int, texto_de_aviso
    termino = fecha_de_renovacion(e)
    if termino is None or not _vigente(e):
        return 0
    if decision_vigente(db, entity_type, e) is not None:
        return 0
    limite = termino - timedelta(days=dias_de_preaviso(db, e))
    antelacion = ajuste_int(db, "ALM_RENEWAL_LEAD_DAYS", e.organization_id)
    nombre = getattr(e, "title", None) or e.name
    para = _destinatarios(db, e)
    url = "/alm?tab=renewals"
    if hoy >= limite and hoy < termino:
        return int(_avisar(db, entity_type, e, "deadline", termino, (termino - hoy).days, para,
                           texto_de_aviso("renewal_deadline_title", nombre=nombre),
                           texto_de_aviso("renewal_deadline_body", fecha=termino.isoformat()), url))
    if limite - timedelta(days=max(0, antelacion)) <= hoy < limite:
        return int(_avisar(db, entity_type, e, "notice", termino, (termino - hoy).days, para,
                           texto_de_aviso("renewal_notice_title", nombre=nombre),
                           texto_de_aviso("renewal_notice_body", fecha=termino.isoformat(), limite=limite.isoformat()),
                           url))
    return 0


def _avisos_de_prestamos(db: Session, hoy: date) -> int:
    from app.services.alm_ajustes import ajuste_int, texto_de_aviso
    n = 0
    for a in db.query(ALMAsignacion).filter(ALMAsignacion.mode == "loan", ALMAsignacion.status == "active",
                                            ALMAsignacion.valid_to.isnot(None)).all():
        dias = (a.valid_to - hoy).days
        nombre = a.asset.name if a.asset is not None else ""
        recordatorio = ajuste_int(db, "ALM_LOAN_REMINDER_DAYS", a.organization_id)
        if 0 <= dias <= recordatorio and a.holder_user_id:
            n += _avisar(db, "loan", a, "loan_due", a.valid_to, dias, [a.holder_user_id],
                         texto_de_aviso("loan_due_title", nombre=nombre),
                         texto_de_aviso("loan_due_body", fecha=a.valid_to.isoformat()), "/my-equipment")
        elif dias < 0:
            semana = hoy - timedelta(days=hoy.weekday())
            n += _avisar(db, "loan", a, "loan_overdue", semana, dias, [a.holder_user_id, a.assigned_by],
                         texto_de_aviso("loan_overdue_title", nombre=nombre),
                         texto_de_aviso("loan_overdue_body", fecha=a.valid_to.isoformat(), dias=-dias),
                         "/alm?tab=loans")
    return n


def escanear(db: Session) -> dict:
    """Barrido diario (`app.worker.alm_daily`): vence asignaciones, aplica renovaciones y avisa."""
    from app.services.alm_ajustes import texto_de_aviso
    from app.services.alm_asignaciones import vencer_asignaciones
    hoy = timeutil.today()
    resultado = {"assignments_expired": vencer_asignaciones(db), "renewed": 0, "cancelled": 0, "expired": 0,
                 "notices": 0, "loan_notices": 0}
    entidades = [("contract", c) for c in db.query(ALMContract).filter(ALMContract.is_active.isnot(False)).all()]
    entidades += [("license", lic) for lic in db.query(ALMLicense).filter(
        ALMLicense.is_active.is_(True), ALMLicense.contract_id.is_(None)).all()]
    for tipo, e in entidades:
        try:
            termino = fecha_de_renovacion(e)
            evento = aplicar_al_vencer(db, tipo, e, hoy)
            nombre = getattr(e, "title", None) or e.name
            if evento in ("renewed", "auto_renewed"):
                resultado["renewed"] += 1
                if evento == "auto_renewed":
                    _avisar(db, tipo, e, "auto_renewed", termino, 0, _destinatarios(db, e),
                            texto_de_aviso("auto_renewed_title", nombre=nombre),
                            texto_de_aviso("auto_renewed_body", fecha=fecha_de_renovacion(e).isoformat()),
                            "/alm?tab=renewals")
            elif evento == "cancelled_at_term":
                resultado["cancelled"] += 1
            elif evento == "contract_expired":
                resultado["expired"] += 1
                _avisar(db, tipo, e, "expired", termino, 0, _destinatarios(db, e),
                        texto_de_aviso("expired_title", nombre=nombre),
                        texto_de_aviso("expired_body", fecha=termino.isoformat()), "/alm?tab=renewals")
            else:
                resultado["notices"] += _avisos_de_renovacion(db, tipo, e, hoy)
            db.commit()
        except Exception:
            db.rollback()
            logger.exception("renovación de %s %s", tipo, e.id)
    resultado["loan_notices"] = _avisos_de_prestamos(db, hoy)
    db.commit()
    return resultado
