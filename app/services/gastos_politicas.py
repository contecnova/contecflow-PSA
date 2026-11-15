"""Gastos sobre el motor de políticas (tarea #27, rev. 166).

El envío de un gasto sigue la secuencia del motor (README, «Policies & rules
engine» → «Extension points»):

1. `politicas.evaluar` (sin efectos);
2. si alguna política lo BLOQUEA explícitamente → 422 con sus mensajes. Un
   exceso nunca bloquea por sí mismo: pide aprobación (niveles, pasos) o avisa;
3. requisitos pendientes (`require_attachment` / `require_justification`) →
   422 con lo que falta: son lo que hay que aportar para enviarlo;
4. `aplicar_campos` (`set_field`);
5. el gasto pasa a enviado con su resumen (`policy_flags`);
6. `registrar_evaluacion` (la explicación que ven el dueño y quien aprueba);
7. `fuentes.abrir(…, evaluacion=ev)`: las políticas añaden niveles y pasos a la
   solicitud (o la abren aunque no haya flujo), avisan a quien digan o la
   aprueban solas.

`previsualizar` hace lo mismo SIN efectos para la pantalla de confirmación:
qué políticas aplican y qué pasará (niveles, avisos, documentos, avisos a
terceros) antes de enviar.
"""
from __future__ import annotations

import json
from typing import Optional

from sqlalchemy.orm import Session

from app.core.errores import ErrorDeDominio
from app.models.expenses import Expense
from app.services import politicas

DOMINIO = "gastos"


def _resumen_guardable(ev: dict) -> dict:
    """Lo que se guarda en `expenses.policy_flags`: el resumen del motor más los avisos con su origen."""
    r = ev["resultado"]
    return {**politicas.resumen(ev),
            "avisos_detalle": [{"politica": a.get("politica"), "regla": a.get("regla"), "mensaje": a.get("mensaje")}
                               for a in r.get("avisos") or []]}


def resumen_guardado(e: Expense) -> Optional[dict]:
    """El resumen de la evaluación al enviar (None si no se ha enviado con el motor)."""
    if not e.policy_flags:
        return None
    try:
        v = json.loads(e.policy_flags)
    except ValueError:
        return None
    return v if isinstance(v, dict) else None


def avisos_guardados(e: Expense) -> list[dict]:
    """Los avisos con los que se envió (política, regla y mensaje)."""
    r = resumen_guardado(e)
    return list((r or {}).get("avisos_detalle") or [])


def _pasos_previstos(db: Session, e: Expense, ev: dict) -> dict:
    """El flujo que se elegiría y los pasos que añadirían las políticas (como `pasos.anadir_por_politicas`)."""
    from app.models.user import User
    from app.services.approval_engine._base import elegir_flujo
    from app.services.approval_engine.pasos import es_informativo, nivel_de_responsable_del_flujo
    r = ev["resultado"]
    u = db.query(User).filter(User.id == e.user_id).first()
    wf = elegir_flujo(db, "expense", {"amount": e.amount, "category": str(getattr(e.category, "value", e.category)),
                                      "project_id": e.project_id, "policy_exceeded": _excede(ev),
                                      "department": getattr(u, "department", None)})
    del_flujo = list(wf.steps or []) if wf else []
    base = nivel_de_responsable_del_flujo(del_flujo)
    return {
        "flujo": {"id": wf.id, "nombre": wf.name} if wf else None,
        "pasos_del_flujo": [{"nombre": s.name, "informar": es_informativo(s)}
                            for s in sorted(del_flujo, key=lambda s: s.step_order)],
        "niveles_anadidos": [base + k for k in range(1, int(r.get("niveles") or 0) + 1)],
        "pasos_anadidos": [{"nombre": p.get("nombre"), "approver_type": p.get("approver_type"),
                            "informar": p.get("kind") == "inform", "politica": (p.get("origen") or {}).get("politica")}
                           for p in r.get("pasos") or []],
    }


def _excede(ev: dict) -> bool:
    r = ev["resultado"]
    return bool(r.get("avisos") or r.get("niveles") or r.get("pasos") or r.get("bloqueos"))


def _excesos(ev: dict) -> list[dict]:
    salida = []
    for p in ev.get("explicacion") or []:
        for fila in p.get("reglas") or []:
            x = fila.get("exceso") or {}
            if fila.get("cumple") and x.get("exceso_pct") is not None:
                salida.append({"politica": p.get("politica"), "regla": fila.get("regla"),
                               "exceso_pct": x.get("exceso_pct"), "valor": x.get("valor"),
                               "referencia": x.get("referencia"), "moneda": x.get("moneda"), "banda": x.get("banda")})
    return salida


def previsualizar(db: Session, usuario, expense_id: str) -> dict:
    """Qué pasará al enviar el gasto, sin efectos."""
    from app.services.gastos_avanzados import _gasto
    e = _gasto(db, usuario, expense_id)
    ev = politicas.evaluar(db, DOMINIO, e)
    r = ev["resultado"]
    pendientes = politicas.requisitos_pendientes(db, DOMINIO, e, r)
    claves_pendientes = {(q["tipo"], tuple(q.get("tipos_de_documento") or [])) for q in pendientes}
    requisitos = [{**{k: q.get(k) for k in ("tipo", "tipos_de_documento", "mensaje", "politica", "regla")},
                   "cumplido": (q["tipo"], tuple(q.get("tipos_de_documento") or [])) not in claves_pendientes}
                  for q in r.get("requisitos") or []]
    origen = lambda o: {k: o.get(k) for k in ("politica", "regla", "mensaje")}  # noqa: E731
    return {
        "decision": ev["decision"],
        "puede_enviar": ev["decision"] != "block" and not pendientes,
        "bloqueos": [origen(b) for b in r.get("bloqueos") or []],
        "avisos": [origen(a) for a in r.get("avisos") or []],
        "requisitos": requisitos,
        "niveles": int(r.get("niveles") or 0),
        "avisar": [{"politica": a.get("politica"), "mensaje": a.get("mensaje"), "canales": a.get("canales"),
                    "destinatarios": a.get("destinatarios")} for a in r.get("avisar") or []],
        "etiquetas": list(r.get("etiquetas") or []),
        "campos": {k: v.get("valor") for k, v in (r.get("campos") or {}).items()},
        "auto_aprobar": bool(r.get("auto_aprobar")),
        "excesos": _excesos(ev),
        "aprobacion": _pasos_previstos(db, e, ev),
        "politicas_que_aplican": sorted({p["politica"] for p in ev["explicacion"] if p.get("aplica")
                                         and any(f.get("cumple") for f in p.get("reglas") or [])}),
        "explicacion": ev["explicacion"],
    }


def al_enviar(db: Session, e: Expense, usuario_id: str) -> dict:
    """Pasos 1-5 del envío. Devuelve la evaluación; no hace commit."""
    ev = politicas.evaluar(db, DOMINIO, e)
    r = ev["resultado"]
    if ev["decision"] == "block":
        mensajes = [b.get("mensaje") for b in r.get("bloqueos") or []]
        raise ErrorDeDominio(422, {"message": "No se puede enviar: " + "; ".join(m for m in mensajes if m),
                                   "bloqueos": mensajes})
    pendientes = politicas.requisitos_pendientes(db, DOMINIO, e, r)
    if pendientes:
        raise ErrorDeDominio(422, {
            "message": "Falta: " + "; ".join(q.get("mensaje") or q["tipo"] for q in pendientes),
            "requisitos": [{k: q.get(k) for k in ("tipo", "tipos_de_documento", "mensaje", "politica")}
                           for q in pendientes]})
    politicas.aplicar_campos(db, DOMINIO, e, r)
    e.policy_flags = json.dumps(_resumen_guardable(ev), ensure_ascii=False, default=str)
    return ev


def tras_enviar(db: Session, e: Expense, ev: dict, usuario_id: str) -> None:
    """Pasos 6-7: la explicación y la solicitud de aprobación con lo que piden las políticas."""
    from app.models.billing_reports import ApprovalRequest
    from app.services.approval_engine import fuentes
    fila = politicas.registrar_evaluacion(db, DOMINIO, e.id, ev, usuario_id=usuario_id,
                                          organization_id=e.organization_id)
    db.commit()
    fuentes.abrir(db, "expense", e.id,
                  f"Gasto {e.code or ''} · {e.description or ''} · {e.amount} {e.currency}", usuario_id,
                  {"amount": e.amount, "category": str(getattr(e.category, "value", e.category)),
                   "project_id": e.project_id, "policy_exceeded": _excede(ev)},
                  evaluacion=ev)
    req = db.query(ApprovalRequest).filter(ApprovalRequest.entity_type == "expense",
                                           ApprovalRequest.entity_id == e.id) \
        .order_by(ApprovalRequest.created_at.desc()).first()
    if req is not None and fila.solicitud_id is None:
        fila.solicitud_id = req.id
        db.commit()


def pendiente_con_pasos_de_politica(db: Session, expense_id: str) -> bool:
    """Si el gasto tiene una solicitud pendiente con pasos de aprobación que pidió una política."""
    from app.models.billing_reports import ApprovalRequest, ApprovalRequestStep
    return db.query(ApprovalRequestStep.id).join(ApprovalRequest, ApprovalRequest.id == ApprovalRequestStep.request_id) \
        .filter(ApprovalRequest.entity_type == "expense", ApprovalRequest.entity_id == expense_id,
                ApprovalRequest.status == "pending", ApprovalRequestStep.kind == "approve").first() is not None
