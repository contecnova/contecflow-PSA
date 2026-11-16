"""Recuperación (harvesting) de licencias sin uso, gobernada por el motor de políticas.

Cada día (worker) y en cada empresa:

1. Para cada asignación vigente de licencia (persona o equipo) se calcula el
   uso real y el contexto del dominio `licencias`, y se evalúan las políticas
   publicadas (`politicas.evaluar`, sin efectos).
2. Protecciones que mandan sobre cualquier política: no se reclama a quien
   está ausente hoy (ausencia aprobada), ni una asignación más joven que
   `ALM_RECLAIM_GRACE_DAYS`, ni con datos desactualizados o sin datos, ni a quien
   dijo que la sigue necesitando (hasta `conservar_hasta`).
3. Si una política da `recuperar` y no hay proceso abierto, se abre
   (`aviso_persona`) y se avisa a la persona.
4. Un proceso abierto avanza cuando vence su paso:
   `aviso_persona` → `aviso_responsable` (responsable directo, jefe del
   proyecto o responsable del contrato, según la política) → liberar. Si la
   política pide aprobación, pasa a `pendiente_aprobacion`: se abre en la
   bandeja de aprobaciones (tipo `license_reclaim`) si la empresa tiene flujo,
   y un gestor puede aprobarlo también desde la pantalla de Recuperación.
   Liberar = `alm_asignaciones.liberar(tipo="released", origen="usage")`: la
   licencia vuelve a la bolsa.
5. Si mientras tanto la persona vuelve a usarla, el proceso se cierra solo.

Todo paso queda en `historial` del proceso y en la auditoría.
"""
from __future__ import annotations

import logging
from datetime import timedelta
from typing import Optional

from sqlalchemy.orm import Session

from app.core import timeutil
from app.core.errores import ErrorDeDominio
from app.models.alm import ALMLicense
from app.models.alm import ALMLicenseAssignment as Asignacion
from app.models.alm_uso import ALMUsoRecuperacion
from app.services.alm_uso._comun import (
    ahora, aware, cargar_json, coste_unitario_anual, exigir_org, moneda_de_licencia, umbrales, volcar_json,
)

logger = logging.getLogger(__name__)

ABIERTOS = ("aviso_persona", "aviso_responsable", "pendiente_aprobacion")
TIPO_DE_APROBACION = "license_reclaim"


# ── Contexto del dominio ──────────────────────────────────────────────────────

def contexto_de_asignacion(db: Session, a: Asignacion, fila: Optional[dict] = None) -> dict:
    """El contexto del dominio `licencias` para una asignación (solo lectura)."""
    from app.models.user import User
    from app.services.alm_uso.estado import Lector
    org = a.organization_id
    if fila is None:
        fila = Lector(db, org, [a.license_id]).de_asignacion(a)
    lic = db.query(ALMLicense).filter(ALMLicense.id == a.license_id).first()
    u = db.query(User).filter(User.id == a.holder_user_id).first() if a.holder_user_id else None
    rol = getattr(getattr(u, "role", None), "value", getattr(u, "role", None))
    unit = coste_unitario_anual(lic)
    hoy = timeutil.today()
    return {
        "dias_sin_uso": fila.get("dias_sin_uso"), "dias_sin_uso_efectivos": fila.get("dias_sin_uso_efectivos"),
        "estado_de_uso": fila.get("estado"), "frecuencia": fila.get("frecuencia"), "fiabilidad": fila.get("fiabilidad"),
        "fuente": fila.get("fuente"), "cuenta_desactivada": bool(fila.get("cuenta_desactivada")),
        "datos_desactualizados": bool(fila.get("datos_desactualizados")),
        "licencia": a.license_id, "producto": getattr(lic, "product_name", None) or getattr(lic, "name", None),
        "proveedor": getattr(lic, "vendor_id", None), "metrica": getattr(lic, "metric", None),
        "tipo_de_licencia": getattr(getattr(lic, "type", None), "value", getattr(lic, "type", None)),
        "coste_anual": {"cantidad": unit, "moneda": moneda_de_licencia(db, lic, org)} if unit is not None else None,
        "dias_desde_asignacion": (hoy - a.valid_from).days if a.valid_from else None,
        "en_ausencia": bool(fila.get("en_ausencia")),
        "titular": "persona" if a.holder_type == "user" else "dispositivo",
        "persona": a.holder_user_id, "rol": rol, "departamento": getattr(u, "department", None),
        "equipo": getattr(u, "team", None), "proyecto": a.charge_project_id,
        "_sujeto": {"usuario_id": a.holder_user_id, "rol": rol, "departamento": getattr(u, "department", None),
                    "equipo": getattr(u, "team", None), "pais": None, "ciudad": None},
        "_fecha": hoy,
        "_uso": fila,
    }


def proteccion(ctx: dict, a: Asignacion, gracia_dias: int, rec: Optional[ALMUsoRecuperacion] = None) -> Optional[str]:
    """Motivo por el que NO se reclama ahora (o None). No depende de ninguna política."""
    if ctx.get("en_ausencia"):
        return "en_ausencia"
    if ctx.get("dias_desde_asignacion") is not None and ctx["dias_desde_asignacion"] < gracia_dias:
        return "periodo_de_gracia"
    if ctx.get("estado_de_uso") == "sin_datos":
        return "sin_datos"
    if ctx.get("datos_desactualizados"):
        return "datos_desactualizados"
    return None


def _recuperar_de(evaluacion: dict) -> Optional[dict]:
    propios = (evaluacion.get("resultado") or {}).get("propios") or []
    return next((p for p in propios if p.get("tipo") == "recuperar"), None)


def _conservada(db: Session, org: str, assignment_id: str) -> Optional[ALMUsoRecuperacion]:
    hoy = timeutil.today()
    return db.query(ALMUsoRecuperacion).filter(
        ALMUsoRecuperacion.organization_id == org, ALMUsoRecuperacion.assignment_id == assignment_id,
        ALMUsoRecuperacion.estado == "conservada", ALMUsoRecuperacion.conservar_hasta >= hoy).first()


def _abierta(db: Session, org: str, assignment_id: str) -> Optional[ALMUsoRecuperacion]:
    return db.query(ALMUsoRecuperacion).filter(
        ALMUsoRecuperacion.organization_id == org, ALMUsoRecuperacion.assignment_id == assignment_id,
        ALMUsoRecuperacion.estado.in_(ABIERTOS)).first()


# ── Avisos ────────────────────────────────────────────────────────────────────

def _avisar(db: Session, user_ids: set, titulo: str, cuerpo: str, canales: list, rec: ALMUsoRecuperacion) -> int:
    from app.models.user import User
    from app.services.notifications import notify_user
    from app.services.preferencias_de_aviso import quiere
    n = 0
    for uid in sorted(i for i in user_ids if i):
        if "app" in canales:
            notify_user(db, uid, "system", titulo[:255], cuerpo[:1000], resource="alm_uso_recuperacion",
                        resource_id=rec.id, action_url="/alm?tab=usage")
            n += 1
        if "email" in canales and quiere(db, uid, "system", "email"):
            fila = db.query(User.email).filter(User.id == uid, User.organization_id == rec.organization_id).first()
            if fila and fila[0]:
                from app.core.segundo_plano import encolar
                from app.services.notification_service import send_email_notification
                encolar(send_email_notification, fila[0], titulo[:255], cuerpo[:1000])
                n += 1
    if "canal" in canales:
        try:
            from app.services.integrations import notify_event
            notify_event("alm.license_reclaim", {"title": titulo, "summary": cuerpo, "id": rec.id}, db,
                         organization_id=rec.organization_id)
            n += 1
        except Exception:
            logger.warning("no se pudo avisar al canal de la recuperación", exc_info=True)
    return n


def _responsables(db: Session, a: Asignacion, escalar_a: str) -> set:
    from app.models.project import Project
    from app.services.approval_engine._base import responsable_de_nivel
    if escalar_a == "responsable" and a.holder_user_id:
        r = responsable_de_nivel(db, a.holder_user_id, 1)
        return {r} if r else set()
    if escalar_a == "jefe_de_proyecto" and a.charge_project_id:
        p = db.query(Project.pm_id).filter(Project.id == a.charge_project_id,
                                           Project.organization_id == a.organization_id).first()
        return {p[0]} if p and p[0] else set()
    if escalar_a == "propietario":
        lic = a.license
        contrato = getattr(lic, "contract", None)
        return {contrato.owner_id} if contrato is not None and contrato.owner_id else set()
    return set()


def _nota(rec: ALMUsoRecuperacion, paso: str, detalle: str = "", por: Optional[str] = None) -> None:
    h = cargar_json(rec.historial, []) or []
    h.append({"at": ahora().isoformat(), "paso": paso, "detalle": detalle, "por": por})
    rec.historial = volcar_json(h)


def _nombre(a: Asignacion) -> str:
    lic = a.license
    return getattr(lic, "name", None) or a.license_id


# ── Pasos ─────────────────────────────────────────────────────────────────────

def _abrir(db: Session, a: Asignacion, ctx: dict, recuperar: dict) -> ALMUsoRecuperacion:
    lic = a.license
    rec = ALMUsoRecuperacion(
        organization_id=a.organization_id, assignment_id=a.id, license_id=a.license_id, user_id=a.holder_user_id,
        asset_id=a.holder_asset_id, estado="aviso_persona", politica_id=recuperar.get("politica_id"),
        politica=recuperar.get("politica"), parametros=volcar_json(recuperar),
        dias_sin_uso=ctx.get("dias_sin_uso_efectivos"), coste_anual=coste_unitario_anual(lic),
        iniciada_at=ahora(), ultimo_paso_at=ahora(),
        siguiente_paso_at=ahora() + timedelta(days=int(recuperar.get("dias_hasta_responsable") or 0)))
    db.add(rec)
    db.flush()
    _nota(rec, "aviso_persona", f"{ctx.get('dias_sin_uso_efectivos')} días sin uso ({ctx.get('fuente')})")
    destinatarios = {a.holder_user_id} if a.holder_user_id else set()
    if not destinatarios:   # equipo sin persona: directamente al responsable que diga la política
        destinatarios = _responsables(db, a, recuperar.get("escalar_a") or "propietario")
    mensaje = (recuperar.get("mensaje") or "").strip()
    _avisar(db, destinatarios, f"Licencia sin uso: {_nombre(a)}",
            (mensaje or f"No consta uso de {_nombre(a)} desde hace {ctx.get('dias_sin_uso_efectivos')} días. "
                        "Si la sigues necesitando, indícalo; si no, se liberará.")[:1000],
            recuperar.get("canales") or ["app"], rec)
    return rec


def _avanzar(db: Session, rec: ALMUsoRecuperacion, a: Asignacion) -> None:
    p = cargar_json(rec.parametros, {}) or {}
    canales = p.get("canales") or ["app"]
    if rec.estado == "aviso_persona":
        escalar = p.get("escalar_a") or "responsable"
        if escalar != "ninguno":
            rec.estado = "aviso_responsable"
            rec.ultimo_paso_at = ahora()
            rec.siguiente_paso_at = ahora() + timedelta(days=int(p.get("dias_hasta_liberar") or 0))
            quienes = _responsables(db, a, escalar)
            _nota(rec, "aviso_responsable", f"{escalar}: {len(quienes)} destinatario(s)")
            _avisar(db, quienes, f"Licencia sin uso en tu equipo: {_nombre(a)}",
                    f"La licencia {_nombre(a)} lleva {rec.dias_sin_uso} días sin uso y no hubo respuesta. "
                    "Si nadie dice que se necesita, se liberará.", canales, rec)
            return
    _a_liberar(db, rec, a, p)


def _a_liberar(db: Session, rec: ALMUsoRecuperacion, a: Asignacion, p: dict) -> None:
    if p.get("requiere_aprobacion", True):
        rec.estado = "pendiente_aprobacion"
        rec.ultimo_paso_at = ahora()
        rec.siguiente_paso_at = None
        _nota(rec, "pendiente_aprobacion")
        solicitante = a.holder_user_id or next(iter(_responsables(db, a, "propietario")), None)
        if solicitante:
            from app.services.approval_engine import fuentes
            fuentes.abrir(db, TIPO_DE_APROBACION, rec.id,
                          f"Liberar {_nombre(a)} ({rec.dias_sin_uso} días sin uso)", solicitante,
                          contexto={"license_id": a.license_id, "dias_sin_uso": rec.dias_sin_uso,
                                    "coste_anual": rec.coste_anual})
        return
    _liberar(db, rec, a, None, "liberada sin aprobación (política)")


def _liberar(db: Session, rec: ALMUsoRecuperacion, a: Asignacion, actor, nota: str) -> None:
    from app.services import alm_asignaciones
    if a.status == "active":
        alm_asignaciones.liberar(db, a.id, actor=actor, motivo=f"Sin uso: {rec.dias_sin_uso} días ({nota})"[:500],
                                 tipo="released", origen="usage", commit=False)
    rec.estado = "liberada"
    rec.cerrada_at = ahora()
    rec.cerrada_por = getattr(actor, "id", None)
    rec.motivo = nota[:500]
    _nota(rec, "liberada", nota, getattr(actor, "id", None))
    p = cargar_json(rec.parametros, {}) or {}
    _avisar(db, {a.holder_user_id} if a.holder_user_id else set(), f"Licencia liberada: {_nombre(a)}",
            f"Se ha liberado {_nombre(a)} por falta de uso. Si la necesitas, pídela de nuevo.",
            p.get("canales") or ["app"], rec)
    from app.services.audit import audit_log
    audit_log(db, actor, "UPDATE", "alm_uso_recuperacion", rec.id, _nombre(a),
              new_values={"estado": "liberada", "assignment_id": a.id, "nota": nota})


def _cerrar(db: Session, rec: ALMUsoRecuperacion, estado: str, motivo: str, actor=None) -> None:
    rec.estado = estado
    rec.cerrada_at = ahora()
    rec.cerrada_por = getattr(actor, "id", None)
    rec.motivo = (motivo or "")[:500] or None
    rec.siguiente_paso_at = None
    _nota(rec, estado, motivo, getattr(actor, "id", None))
    from app.services.approval_engine import fuentes
    fuentes.cerrar(db, TIPO_DE_APROBACION, rec.id, "cancelled", motivo or estado)


# ── Pasada diaria ─────────────────────────────────────────────────────────────

def _evaluaciones(db: Session, org: str):
    """(asignación, contexto, evaluación) de cada asignación vigente de persona o equipo. Sin efectos."""
    from app.services import politicas
    from app.services.alm_uso.estado import Lector
    asignaciones = db.query(Asignacion).filter(Asignacion.organization_id == org, Asignacion.resource_type == "license",
                                               Asignacion.status == "active",
                                               Asignacion.holder_type.in_(("user", "asset"))).all()
    lector = Lector(db, org, sorted({a.license_id for a in asignaciones}))
    for a in asignaciones:
        ctx = contexto_de_asignacion(db, a, lector.de_asignacion(a))
        ev = politicas.evaluar(db, "licencias", contexto={k: v for k, v in ctx.items() if k != "_uso"},
                               organization_id=org)
        yield a, ctx, ev


def pasada(db: Session, org: str) -> dict:
    """La pasada diaria de una empresa (worker). Confirma al final."""
    exigir_org(org)
    gracia = umbrales(db, org).gracia_dias
    cuenta = {"evaluadas": 0, "abiertas": 0, "avanzadas": 0, "cerradas_por_uso": 0, "protegidas": 0}
    for a, ctx, ev in _evaluaciones(db, org):
        cuenta["evaluadas"] += 1
        rec = _abierta(db, org, a.id)
        if rec is not None:
            if ctx.get("estado_de_uso") == "en_uso":
                _cerrar(db, rec, "cancelada", "volvió a usarla")
                cuenta["cerradas_por_uso"] += 1
                continue
            if ctx.get("en_ausencia") and rec.siguiente_paso_at is not None:
                # Ausente: el reloj del paso se para hasta que vuelva.
                rec.siguiente_paso_at = aware(rec.siguiente_paso_at) + timedelta(days=1)
                cuenta["protegidas"] += 1
                continue
            if rec.estado != "pendiente_aprobacion" and rec.siguiente_paso_at and aware(rec.siguiente_paso_at) <= ahora():
                _avanzar(db, rec, a)
                cuenta["avanzadas"] += 1
            continue
        recuperar = _recuperar_de(ev)
        if recuperar is None:
            continue
        if proteccion(ctx, a, gracia) or _conservada(db, org, a.id):
            cuenta["protegidas"] += 1
            continue
        _abrir(db, a, ctx, recuperar)
        cuenta["abiertas"] += 1
    db.commit()
    return cuenta


def previsualizar(db: Session, org: str) -> dict:
    """Simulador: qué haría HOY la pasada con las políticas publicadas. No escribe nada."""
    exigir_org(org)
    gracia = umbrales(db, org).gracia_dias
    items = []
    resumen = {"iniciaria": 0, "avanzaria": 0, "cerraria_por_uso": 0, "protegida": 0, "sin_politica": 0,
               "ahorro_anual_potencial": 0.0}
    for a, ctx, ev in _evaluaciones(db, org):
        rec = _abierta(db, org, a.id)
        recuperar = _recuperar_de(ev)
        accion, motivo = None, None
        if rec is not None:
            if ctx.get("estado_de_uso") == "en_uso":
                accion = "cerraria_por_uso"
            elif rec.estado != "pendiente_aprobacion" and rec.siguiente_paso_at and aware(rec.siguiente_paso_at) <= ahora():
                accion = "avanzaria"
        elif recuperar is not None:
            motivo = proteccion(ctx, a, gracia) or ("conservada" if _conservada(db, org, a.id) else None)
            accion = "protegida" if motivo else "iniciaria"
        elif ctx.get("estado_de_uso") in ("sin_uso", "infrautilizada"):
            accion = "sin_politica"
        if accion is None:
            continue
        resumen[accion] += 1
        coste = (ctx.get("coste_anual") or {}).get("cantidad")
        if accion == "iniciaria" and coste:
            resumen["ahorro_anual_potencial"] += coste
        items.append({"assignment_id": a.id, "license_id": a.license_id, "licencia": _nombre(a),
                      "user_id": a.holder_user_id, "asset_id": a.holder_asset_id, "accion": accion, "motivo": motivo,
                      "estado_actual": rec.estado if rec else None, "estado_de_uso": ctx.get("estado_de_uso"),
                      "dias_sin_uso_efectivos": ctx.get("dias_sin_uso_efectivos"), "fuente": ctx.get("fuente"),
                      "fiabilidad": ctx.get("fiabilidad"), "coste_anual": coste,
                      "politica": (recuperar or {}).get("politica")})
    if db.new or db.dirty or db.deleted:
        db.rollback()
        raise ErrorDeDominio(500, "La simulación intentó escribir datos: se ha deshecho")
    resumen["ahorro_anual_potencial"] = round(resumen["ahorro_anual_potencial"], 2)
    from app.services.alm_uso._comun import con_nombres
    return {"resumen": resumen, "items": con_nombres(db, org, items)}


# ── Lectura y acciones de la pantalla ─────────────────────────────────────────

def recuperacion_dict(r: ALMUsoRecuperacion) -> dict:
    return {"id": r.id, "assignment_id": r.assignment_id, "license_id": r.license_id, "user_id": r.user_id,
            "asset_id": r.asset_id, "estado": r.estado, "politica": r.politica, "dias_sin_uso": r.dias_sin_uso,
            "coste_anual": r.coste_anual, "parametros": cargar_json(r.parametros, {}),
            "iniciada_at": aware(r.iniciada_at).isoformat() if r.iniciada_at else None,
            "siguiente_paso_at": aware(r.siguiente_paso_at).isoformat() if r.siguiente_paso_at else None,
            "conservar_hasta": r.conservar_hasta.isoformat() if r.conservar_hasta else None,
            "cerrada_at": aware(r.cerrada_at).isoformat() if r.cerrada_at else None, "motivo": r.motivo,
            "historial": cargar_json(r.historial, [])}


def listar(db: Session, org: str, estado: Optional[str] = None, user_id: Optional[str] = None) -> dict:
    exigir_org(org)
    q = db.query(ALMUsoRecuperacion).filter(ALMUsoRecuperacion.organization_id == org)
    if estado == "abiertas":
        q = q.filter(ALMUsoRecuperacion.estado.in_(ABIERTOS))
    elif estado:
        q = q.filter(ALMUsoRecuperacion.estado == estado)
    if user_id:
        q = q.filter(ALMUsoRecuperacion.user_id == user_id)
    filas = q.order_by(ALMUsoRecuperacion.iniciada_at.desc()).limit(1000).all()
    liberadas = [r for r in db.query(ALMUsoRecuperacion).filter(ALMUsoRecuperacion.organization_id == org,
                                                                ALMUsoRecuperacion.estado == "liberada")]
    from app.services.alm_uso._comun import con_nombres
    return {"items": con_nombres(db, org, [recuperacion_dict(r) for r in filas]),
            "kpis": {"abiertas": db.query(ALMUsoRecuperacion).filter(ALMUsoRecuperacion.organization_id == org,
                                                                   ALMUsoRecuperacion.estado.in_(ABIERTOS)).count(),
                     "pendientes_de_aprobacion": db.query(ALMUsoRecuperacion).filter(
                         ALMUsoRecuperacion.organization_id == org,
                         ALMUsoRecuperacion.estado == "pendiente_aprobacion").count(),
                     "liberadas": len(liberadas),
                     "ahorro_anual_liberado": round(sum(r.coste_anual or 0 for r in liberadas), 2)}}


def _rec_o_404(db: Session, org: str, rec_id: str) -> ALMUsoRecuperacion:
    r = db.query(ALMUsoRecuperacion).filter(ALMUsoRecuperacion.id == rec_id,
                                            ALMUsoRecuperacion.organization_id == org).first()
    if r is None:
        raise ErrorDeDominio(404, {"code": "ALM_USAGE_RECLAIM_NOT_FOUND", "message": "Recuperación no encontrada"})
    return r


def _asignacion(db: Session, rec: ALMUsoRecuperacion) -> Asignacion:
    return db.query(Asignacion).filter(Asignacion.id == rec.assignment_id,
                                       Asignacion.organization_id == rec.organization_id).one()


def conservar(db: Session, usuario, rec_id: str, motivo: Optional[str], es_gestor: bool) -> dict:
    """«La sigo necesitando»: la persona titular (o un gestor) la conserva `ALM_RECLAIM_KEEP_DAYS` días."""
    from app.services.audit import audit_log
    org = exigir_org(getattr(usuario, "organization_id", None))
    r = _rec_o_404(db, org, rec_id)
    if not es_gestor and r.user_id != usuario.id:
        raise ErrorDeDominio(404, {"code": "ALM_USAGE_RECLAIM_NOT_FOUND", "message": "Recuperación no encontrada"})
    if r.estado not in ABIERTOS:
        raise ErrorDeDominio(409, {"code": "ALM_USAGE_RECLAIM_CLOSED", "message": "Ese proceso ya está cerrado"})
    if not (motivo or "").strip():
        raise ErrorDeDominio(422, {"code": "ALM_USAGE_REASON_REQUIRED", "message": "Explica para qué la necesitas"})
    _cerrar(db, r, "conservada", motivo.strip(), usuario)
    r.conservar_hasta = timeutil.today() + timedelta(days=umbrales(db, org).conservar_dias)
    audit_log(db, usuario, "UPDATE", "alm_uso_recuperacion", r.id, None,
              new_values={"estado": "conservada", "hasta": r.conservar_hasta.isoformat(), "motivo": motivo})
    db.commit()
    return recuperacion_dict(r)


def decidir(db: Session, usuario, rec_id: str, aprobar: bool, nota: Optional[str] = None,
            desde_bandeja: bool = False) -> dict:
    """Aprobar (liberar) o rechazar (conservar) una recuperación pendiente de aprobación."""
    from app.services.audit import audit_log
    org = exigir_org(getattr(usuario, "organization_id", None))
    r = _rec_o_404(db, org, rec_id)
    if r.estado != "pendiente_aprobacion":
        raise ErrorDeDominio(409, {"code": "ALM_USAGE_RECLAIM_NOT_PENDING", "message": "No está pendiente de aprobación"})
    a = _asignacion(db, r)
    if aprobar:
        _liberar(db, r, a, usuario, (nota or "aprobada").strip())
    else:
        r.estado = "rechazada"
        r.cerrada_at, r.cerrada_por, r.motivo = ahora(), usuario.id, (nota or "")[:500] or None
        r.conservar_hasta = timeutil.today() + timedelta(days=umbrales(db, org).conservar_dias)
        _nota(r, "rechazada", nota or "", usuario.id)
        audit_log(db, usuario, "REJECT", "alm_uso_recuperacion", r.id, _nombre(a), new_values={"nota": nota})
    if not desde_bandeja:
        from app.services.approval_engine import fuentes
        fuentes.cerrar(db, TIPO_DE_APROBACION, r.id, "approved" if aprobar else "rejected",
                       f"Decidido por {getattr(usuario, 'full_name', '') or usuario.id}")
    db.commit()
    return recuperacion_dict(r)


def liberar_ahora(db: Session, usuario, rec_id: str, nota: Optional[str] = None) -> dict:
    """Un gestor libera ya, sin esperar los plazos (queda en la auditoría)."""
    org = exigir_org(getattr(usuario, "organization_id", None))
    r = _rec_o_404(db, org, rec_id)
    if r.estado not in ABIERTOS:
        raise ErrorDeDominio(409, {"code": "ALM_USAGE_RECLAIM_CLOSED", "message": "Ese proceso ya está cerrado"})
    _liberar(db, r, _asignacion(db, r), usuario, (nota or "liberada a mano").strip())
    from app.services.approval_engine import fuentes
    fuentes.cerrar(db, TIPO_DE_APROBACION, r.id, "approved", "Liberada a mano")
    db.commit()
    return recuperacion_dict(r)


def cancelar(db: Session, usuario, rec_id: str, motivo: Optional[str] = None) -> dict:
    from app.services.audit import audit_log
    org = exigir_org(getattr(usuario, "organization_id", None))
    r = _rec_o_404(db, org, rec_id)
    if r.estado not in ABIERTOS:
        raise ErrorDeDominio(409, {"code": "ALM_USAGE_RECLAIM_CLOSED", "message": "Ese proceso ya está cerrado"})
    _cerrar(db, r, "cancelada", (motivo or "cancelada a mano").strip(), usuario)
    audit_log(db, usuario, "UPDATE", "alm_uso_recuperacion", r.id, None, new_values={"estado": "cancelada"})
    db.commit()
    return recuperacion_dict(r)


def aplicar_desde_bandeja(req, decision: str, actor, db: Session) -> None:
    """Decisión final de la bandeja de aprobaciones sobre una recuperación (`license_reclaim`)."""
    r = db.query(ALMUsoRecuperacion).filter(ALMUsoRecuperacion.id == req.entity_id).first()
    if r is None or r.estado != "pendiente_aprobacion":
        return
    decidir(db, actor, r.id, decision == "approved", req.final_note, desde_bandeja=True)
