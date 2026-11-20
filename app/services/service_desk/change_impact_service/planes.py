"""Analisis completo guardado, plan de marcha atras y plan de pruebas.

Parte de `app.services.service_desk.change_impact_service` (auditoria 2026-11, #24): se partio por responsabilidad
sin cambiar el codigo. El paquete reexporta todos los nombres.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Optional
from sqlalchemy.orm import Session
from app.models.service_desk import ITSMChangeRequest

from app.services.service_desk.change_impact_service.riesgo import (
    _get_ci_details,
    generate_impact_report,
    get_risk_matrix_for_change,
    score_change_risk,
)
from app.core.codigos_de_error import error
from app.services.service_desk.change_impact_service.textos import (
    con_textos,
    diferido,
    idioma_de,
    pintar,
    pintar_datos,
    riesgo_diferido,
    tiene_textos,
    traducir_anterior,
)

#: Tipo de plan -> prefijo de su clave en `AppSetting` (`<prefijo>.<change_id>`).
CLAVES_DE_PLAN = {
    "impacto": "sd.change.impact",
    "vuelta": "sd.change.rollback",
    "pruebas": "sd.change.testing",
    "comunicaciones": "sd.change.comms",
}


def plan_guardado(db: Session, tipo: str, change_id: str, idioma: Optional[str] = None, *,
                  org_id: Optional[str] = None, user_id: Optional[str] = None) -> Optional[dict]:
    """El ultimo plan `tipo` guardado del cambio, pintado en `idioma`, o None si
    aun no se ha generado (19-11-2026).

    Un plan guardado antes de las claves (sin `_textos`) se traduce con el
    servicio de traduccion de la empresa `org_id` si esta activo (si no, con su
    IA si la tiene y la deja usar: 20-11-2026), y lleva
    `textos_anteriores` para que la pantalla ofrezca regenerarlo
    (`textos.traducir_anterior`)."""
    clave = f"{CLAVES_DE_PLAN[tipo]}.{change_id}"
    datos = _get_json_setting(db, clave)
    if not datos:
        return None
    if not tiene_textos(datos):
        if org_id is None:
            change = db.query(ITSMChangeRequest.organization_id).filter(ITSMChangeRequest.id == change_id).first()
            org_id = change[0] if change else None
        return traducir_anterior(db, datos, idioma, org_id, user_id, clave_del_plan=clave)
    return pintar_datos(datos, idioma)


def _get_json_setting(db: Session, key: str) -> dict:
    from app.models.settings import AppSetting
    row = db.query(AppSetting).filter(AppSetting.key == key).first()
    if not row or not row.value:
        return {}
    try:
        return json.loads(row.value)
    except (json.JSONDecodeError, TypeError):
        return {}


def _set_json_setting(db: Session, key: str, data: dict) -> None:
    from app.models.settings import AppSetting
    row = db.query(AppSetting).filter(AppSetting.key == key).first()
    serialized = json.dumps(data, ensure_ascii=False)
    if row:
        row.value = serialized
    else:
        row = AppSetting(key=key, value=serialized, description=f"Change impact: {key}")
        db.add(row)
    db.flush()


def analyze_change_impact_full(
    db: Session,
    change_id: str,
    current_user_id: Optional[str] = None,
    idioma: Optional[str] = None,
) -> dict:
    """Full automated impact analysis: score + risk matrix + narrative + cache.

    El resumen sale en `idioma` (sin el, el de `current_user_id`)."""
    idioma = idioma_de(db, user_id=current_user_id, idioma=idioma)
    report = generate_impact_report(db, change_id, idioma=idioma)
    matrix = get_risk_matrix_for_change(db, change_id)
    report["detailed_risk_matrix"] = matrix[:20]
    report["analyzed_by"] = current_user_id

    # Persist
    _set_json_setting(db, f"sd.change.impact.{change_id}", report)
    db.commit()
    return pintar_datos(report, idioma)


def get_cached_impact_analysis(db: Session, change_id: str, idioma: Optional[str] = None) -> Optional[dict]:
    """El análisis de impacto guardado, o None si aún no se ha generado (19-11-2026:
    antes 404; quien llama comprueba antes que el cambio existe). Pintado en `idioma`."""
    return plan_guardado(db, "impacto", change_id, idioma)


def generate_rollback_plan(
    db: Session,
    change_id: str,
    current_user_id: Optional[str] = None,
    idioma: Optional[str] = None,
) -> dict:
    """Generate a structured rollback plan for the change.

    Devuelve el plan pintado en `idioma` (sin el, el de `current_user_id`); lo
    guardado lleva sus textos por clave para pintarlo luego en otro idioma."""
    change = db.query(ITSMChangeRequest).filter(ITSMChangeRequest.id == change_id).first()
    if not change:
        raise error(404, "no_encontrado", detail=f"Change {change_id} not found", que="cambio")

    cached = _get_json_setting(db, f"sd.change.impact.{change_id}")
    overall_risk = cached.get("risk_label", "medium") if cached else "medium"
    affected_count = cached.get("affected_cis", {}).get("expanded_count", 0) if cached else 0

    # 19-11-2026: accion y responsable por clave (`cambio.vuelta.N`,
    # `cambio.rol.*`), pintados en el idioma de quien lee (`textos.py`).
    idioma = idioma_de(db, user_id=current_user_id, idioma=idioma)
    minutos_restaurar = 30 if overall_risk in ("high", "critical") else 15
    filas = ((5, "operaciones"), (10, "cmdb"), (minutos_restaurar, "tecnico"), (20, "qa_dev"),
             (10, "noc"), (5, "gestor"), (15, "gestor"))
    steps = [
        con_textos({"step": n, "estimated_minutes": minutos}, idioma,
                   action=diferido(f"cambio.vuelta.{n}", titulo=change.title or ""),
                   responsible=diferido(f"cambio.rol.{rol}"))
        for n, (minutos, rol) in enumerate(filas, start=1)
    ]

    plan = {
        "change_id": change_id,
        "change_number": change.number,
        "change_title": change.title,
        "overall_risk": overall_risk,
        "affected_ci_count": affected_count,
        "rollback_steps": steps,
        "total_estimated_minutes": sum(s["estimated_minutes"] for s in steps),
        "generated_at": datetime.now(tz=timezone.utc).isoformat(),
        "generated_by": current_user_id,
    }

    _set_json_setting(db, f"sd.change.rollback.{change_id}", plan)
    db.commit()
    return pintar_datos(plan, idioma)


# ══════════════════════════════════════════════════════════════════════════════
# Testing Plan — structured, executable test steps by phase
# ══════════════════════════════════════════════════════════════════════════════

#: El plan de pruebas, declarado. Cada fila es un paso:
#:
#:    (fase, tipo, minutos, responsable, automatizado, comando, condición)
#:
#: `condición` recibe el contexto del cambio y decide si el paso aplica;
#: `None` significa «siempre». Los minutos se calculan con ese mismo contexto.
#:
#: 19-11-2026: la descripción y el resultado esperado son textos por clave
#: (`cambio.prueba.<fase>.<tipo>.desc|esperado`, `textos_de_salida_itsm.py`) y
#: el responsable un rol (`cambio.rol.<rol>`): salen en el idioma de quien lee.
#:
#: Auditoría 2026-09 (hallazgo 18): esto eran 197 líneas de llamadas a un
#: ayudante anidado, con las condiciones repartidas entre ellas — complejidad
#: 14. Un plan de pruebas **es** una tabla: verlo entero es lo que hace falta
#: para revisarlo con quien lo va a ejecutar, y añadir un paso es añadir una
#: fila en el sitio que le toca, no una rama en medio de un bloque.
_PASOS_DEL_PLAN: tuple[tuple, ...] = (
    # ── Antes del cambio ─────────────────────────────────────────────────────
    ("pre_change", "sanity", 10, "cmdb", False, "", None),
    ("pre_change", "backup", 15, "tecnico", False, "", None),
    ("pre_change", "readiness", 10, "gestor", False, "", "riesgo_medio"),
    ("pre_change", "noc_alert", 5, "noc", False, "", "riesgo_alto"),
    ("pre_change", "maintenance_mode", 10, "operaciones", True,
     "cmdb update-status --ci-ids <affected_ids> --status maintenance", "hay_parada"),

    # ── Durante el cambio ────────────────────────────────────────────────────
    ("execution", "milestone", 5, "gestor", False, "", None),
    ("execution", "monitoring", "minutos_de_monitorizacion", "noc", True,
     "monitoring check --ci-ids <affected_ids> --interval 5m", None),
    ("execution", "checkpoint", 10, "tecnico", False, "", "muchos_cis"),
    ("execution", "go_nogo", 10, "gestor", False, "", "riesgo_alto"),

    # ── Después del cambio ───────────────────────────────────────────────────
    ("post_change", "smoke", 15, "qa_devops", True,
     "smoke-test --suite post_change --ci-ids <affected_ids>", None),
    ("post_change", "functional", 20, "qa_dev", True,
     "pytest tests/functional/ --marker change_validation -v", None),
    ("post_change", "performance", 15, "qa_devops", True,
     "perf-test --baseline pre_change --ci-ids <affected_ids>", "riesgo_alto"),
    ("post_change", "cmdb_update", 10, "cmdb", False, "", None),
    ("post_change", "monitoring_30min", 30, "noc", True,
     "monitoring watch --duration 30m --alert-on-anomaly --ci-ids <affected_ids>", None),
    ("post_change", "maintenance_off", 5, "operaciones", True,
     "cmdb update-status --ci-ids <affected_ids> --status active", "hay_parada"),

    # ── Si hay que volver atrás ──────────────────────────────────────────────
    ("rollback_validation", "config_restore", 15, "tecnico", False, "", None),
    ("rollback_validation", "smoke", 15, "qa_devops", True,
     "smoke-test --suite post_rollback --ci-ids <affected_ids>", None),
    ("rollback_validation", "cmdb_revert", 10, "cmdb", False, "", None),
    ("rollback_validation", "incident_check", 10, "noc", True,
     "monitoring check --duration 15m --ci-ids <affected_ids>", None),
)

#: Las cuatro fases, en el orden en que se ejecutan. La tabla ya va ordenada,
#: pero el informe agrupa por fase y ese orden tiene que estar declarado.
_FASES_DEL_PLAN = ("pre_change", "execution", "post_change", "rollback_validation")


def _contexto_del_plan(change, riesgo: str, ci_details: list[dict]) -> dict:
    """Los datos con los que se deciden y se rellenan los pasos."""
    parada = change.downtime_minutes or 0
    n_cis = len(ci_details)
    return {
        # Sin CI, «N/D» en el idioma de quien lee (texto por clave).
        "cis": ", ".join(c["name"] for c in ci_details[:3]) or diferido("cambio.sin_cis"),
        "mitad_de_cis": min(n_cis // 2, 5),
        # La monitorización dura lo que dure la parada, con un tope: sin parada
        # declarada, o con una muy larga, media hora es lo razonable.
        "minutos_de_monitorizacion": parada if 0 < parada <= 60 else 30,
        "riesgo_alto": riesgo in ("high", "critical"),
        "riesgo_medio": riesgo in ("medium", "high", "critical"),
        "hay_parada": parada > 0,
        "muchos_cis": n_cis > 3,
    }


def _pasos_aplicables(ctx: dict, idioma: Optional[str] = None) -> list[dict]:
    """Los pasos de la tabla que aplican a este cambio, ya numerados y pintados en `idioma`."""
    pasos: list[dict] = []
    datos = {"cis": ctx["cis"], "mitad_de_cis": ctx["mitad_de_cis"]}
    for fase, tipo, minutos, rol, automatico, comando, condicion in _PASOS_DEL_PLAN:
        if condicion and not ctx[condicion]:
            continue
        entrada = {
            "step": len(pasos) + 1,
            "phase": fase,
            "test_type": tipo,
            "estimated_minutes": ctx[minutos] if isinstance(minutos, str) else minutos,
            "automated": automatico,
        }
        con_textos(entrada, idioma,
                   description=diferido(f"cambio.prueba.{fase}.{tipo}.desc", **datos),
                   expected_result=diferido(f"cambio.prueba.{fase}.{tipo}.esperado", **datos),
                   responsible=diferido(f"cambio.rol.{rol}"))
        if comando:
            entrada["command"] = comando
        pasos.append(entrada)
    return pasos


def generate_testing_plan(
    db: Session,
    change_id: str,
    current_user_id: Optional[str] = None,
    idioma: Optional[str] = None,
) -> dict:
    """Plan de pruebas con pasos ejecutables, adaptado al riesgo y al nº de CIs.

    Cuatro fases: validación previa, hitos durante la ventana, pruebas de humo
    y funcionales al terminar, y confirmación si hay que volver atrás.

    Se guarda en `AppSetting` para poder consultarlo después. Sale en `idioma`
    (sin el, el de `current_user_id`); lo guardado lleva sus textos por clave.
    """
    change = db.query(ITSMChangeRequest).filter(ITSMChangeRequest.id == change_id).first()
    if not change:
        raise error(404, "no_encontrado", detail=f"Change {change_id} not found", que="cambio")

    idioma = idioma_de(db, user_id=current_user_id, idioma=idioma)
    riesgo = score_change_risk(db, change)
    etiqueta = riesgo["risk_label"]
    ci_details = _get_ci_details(db, riesgo["ci_ids_expanded"])

    pasos = _pasos_aplicables(_contexto_del_plan(change, etiqueta, ci_details), idioma)

    plan = {
        "change_id": change_id,
        "change_number": change.number,
        "change_title": change.title,
        "risk_label": etiqueta,
        "total_steps": len(pasos),
        "estimated_total_minutes": sum(p["estimated_minutes"] for p in pasos),
        "phases": {
            fase: [p for p in pasos if p["phase"] == fase] for fase in _FASES_DEL_PLAN
        },
        "steps": pasos,
        "generated_at": datetime.now(tz=timezone.utc).isoformat(),
        "generated_by": current_user_id,
    }

    _set_json_setting(db, f"sd.change.testing.{change_id}", plan)
    # El resumen en texto sólo se escribe si el campo está vacío: si alguien
    # redactó un plan a mano, generar otro no lo borra.
    # Es texto libre del cambio (se edita a mano): queda en el idioma de quien lo genera.
    if hasattr(change, "test_plan") and not change.test_plan:
        lineas = [pintar(diferido("cambio.plan_pruebas.cabecera", riesgo=riesgo_diferido(etiqueta),
                                  n=len(pasos)), idioma)]
        lineas += [f"{p['step']}. [{p['phase']}] {p['description']}" for p in pasos]
        change.test_plan = "\n".join(lineas)
    db.commit()
    return pintar_datos(plan, idioma)
