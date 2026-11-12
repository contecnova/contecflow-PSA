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
from app.core.errores import ErrorDeDominio

from app.services.service_desk.change_impact_service.riesgo import (
    _get_ci_details,
    generate_impact_report,
    get_risk_matrix_for_change,
    score_change_risk,
)


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
) -> dict:
    """Full automated impact analysis: score + risk matrix + narrative + cache."""
    report = generate_impact_report(db, change_id)
    matrix = get_risk_matrix_for_change(db, change_id)
    report["detailed_risk_matrix"] = matrix[:20]
    report["analyzed_by"] = current_user_id

    # Persist
    _set_json_setting(db, f"sd.change.impact.{change_id}", report)
    db.commit()
    return report


def get_cached_impact_analysis(db: Session, change_id: str) -> dict:
    """Return cached impact analysis or 404."""
    result = _get_json_setting(db, f"sd.change.impact.{change_id}")
    if not result:
        raise ErrorDeDominio(404, "Análisis de impacto no encontrado. Ejecuta POST /impact-analysis primero.")
    return result


def generate_rollback_plan(
    db: Session,
    change_id: str,
    current_user_id: Optional[str] = None,
) -> dict:
    """Generate a structured rollback plan for the change."""
    change = db.query(ITSMChangeRequest).filter(ITSMChangeRequest.id == change_id).first()
    if not change:
        raise ErrorDeDominio(404, f"Change {change_id} not found")

    cached = _get_json_setting(db, f"sd.change.impact.{change_id}")
    overall_risk = cached.get("risk_label", "medium") if cached else "medium"
    affected_count = cached.get("affected_cis", {}).get("expanded_count", 0) if cached else 0

    steps = [
        {"step": 1, "action": "Detener el despliegue si está en progreso", "responsible": "Ingeniero de operaciones", "estimated_minutes": 5},
        {"step": 2, "action": "Verificar estado de todos los CIs afectados en el CMDB", "responsible": "CMDB Admin", "estimated_minutes": 10},
        {"step": 3, "action": f"Restaurar versión anterior de los componentes de '{change.title}'", "responsible": "Equipo técnico", "estimated_minutes": 30 if overall_risk in ("high", "critical") else 15},
        {"step": 4, "action": "Ejecutar smoke tests en sistemas restaurados", "responsible": "QA / Dev", "estimated_minutes": 20},
        {"step": 5, "action": "Confirmar estado operacional de los CIs afectados", "responsible": "NOC / Operaciones", "estimated_minutes": 10},
        {"step": 6, "action": "Notificar a stakeholders sobre el rollback y estado", "responsible": "Change Manager", "estimated_minutes": 5},
        {"step": 7, "action": "Registrar ticket post-incident y programar PIR", "responsible": "Change Manager", "estimated_minutes": 15},
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
    return plan


# ══════════════════════════════════════════════════════════════════════════════
# Testing Plan — structured, executable test steps by phase
# ══════════════════════════════════════════════════════════════════════════════

#: El plan de pruebas, declarado. Cada fila es un paso:
#:
#:    (fase, tipo, descripción, resultado esperado, minutos, responsable,
#:     automatizado, comando, condición)
#:
#: `condición` recibe el contexto del cambio y decide si el paso aplica;
#: `None` significa «siempre». Descripción, resultado y minutos se formatean o
#: calculan con ese mismo contexto.
#:
#: Auditoría 2026-09 (hallazgo 18): esto eran 197 líneas de llamadas a un
#: ayudante anidado, con las condiciones repartidas entre ellas — complejidad
#: 14. Un plan de pruebas **es** una tabla: verlo entero es lo que hace falta
#: para revisarlo con quien lo va a ejecutar, y añadir un paso es añadir una
#: fila en el sitio que le toca, no una rama en medio de un bloque.
_PASOS_DEL_PLAN: tuple[tuple, ...] = (
    # ── Antes del cambio ─────────────────────────────────────────────────────
    ("pre_change", "sanity",
     "Verificar estado actual de los CIs en CMDB: {cis}",
     "Todos los CIs en estado 'active' con configuración baseline registrada",
     10, "CMDB Admin", False, "", None),
    ("pre_change", "backup",
     "Confirmar snapshots/backups de configuración de CIs críticos",
     "Backups completados y verificados (restore point disponible)",
     15, "Equipo técnico", False, "", None),
    ("pre_change", "readiness",
     "Confirmar disponibilidad del plan de rollback y equipo de soporte",
     "Equipo de rollback en standby, procedimiento revisado y firmado",
     10, "Change Manager", False, "", "riesgo_medio"),
    ("pre_change", "noc_alert",
     "Notificar a NOC y colocar CIs en modo observación anticipada",
     "NOC confirma monitorización activa de alertas sobre CIs afectados",
     5, "NOC / Operaciones", False, "", "riesgo_alto"),
    ("pre_change", "maintenance_mode",
     "Activar modo mantenimiento en sistemas afectados ({cis})",
     "Sistemas en estado maintenance, sin tickets de incidente generados automáticamente",
     10, "Ingeniero de operaciones", True,
     "cmdb update-status --ci-ids <affected_ids> --status maintenance", "hay_parada"),

    # ── Durante el cambio ────────────────────────────────────────────────────
    ("execution", "milestone",
     "Confirmar inicio del cambio y registrar hora real de arranque",
     "Hora de inicio registrada en el Change Request (actual_start actualizado)",
     5, "Change Manager", False, "", None),
    ("execution", "monitoring",
     "Monitorizar métricas de salud de CIs durante el cambio: {cis}",
     "CPU/memoria/latencia dentro de umbrales normales; sin alertas críticas",
     "minutos_de_monitorizacion", "NOC / Operaciones", True,
     "monitoring check --ci-ids <affected_ids> --interval 5m", None),
    ("execution", "checkpoint",
     "Verificar hito intermedio: primeros CIs afectados han completado el cambio",
     "Al menos {mitad_de_cis} CIs en estado post-change sin errores",
     10, "Equipo técnico", False, "", "muchos_cis"),
    ("execution", "go_nogo",
     "Go/No-Go decision point a mitad del cambio",
     "Equipo técnico confirma continuación; si hay anomalías iniciar rollback",
     10, "Change Manager", False, "", "riesgo_alto"),

    # ── Después del cambio ───────────────────────────────────────────────────
    ("post_change", "smoke",
     "Smoke tests de conectividad y disponibilidad de CIs: {cis}",
     "Todos los CIs responden; endpoints críticos retornan HTTP 200 / ping exitoso",
     15, "QA / DevOps", True,
     "smoke-test --suite post_change --ci-ids <affected_ids>", None),
    ("post_change", "functional",
     "Tests funcionales de los servicios afectados por el cambio",
     "Todos los casos de prueba funcionales pasan sin regresiones",
     20, "QA / Dev", True,
     "pytest tests/functional/ --marker change_validation -v", None),
    ("post_change", "performance",
     "Comparación de baseline de rendimiento (antes vs después)",
     "Métricas de rendimiento dentro del ±10% respecto al baseline pre-cambio",
     15, "QA / DevOps", True,
     "perf-test --baseline pre_change --ci-ids <affected_ids>", "riesgo_alto"),
    ("post_change", "cmdb_update",
     "Verificar y actualizar CMDB con el nuevo estado de configuración",
     "CIs actualizados en CMDB; relaciones y atributos reflejan la nueva configuración",
     10, "CMDB Admin", False, "", None),
    ("post_change", "monitoring_30min",
     "Observar métricas de producción durante 30 minutos post-cambio",
     "Sin alertas inesperadas; incidentalidad normal para la ventana horaria",
     30, "NOC / Operaciones", True,
     "monitoring watch --duration 30m --alert-on-anomaly --ci-ids <affected_ids>", None),
    ("post_change", "maintenance_off",
     "Desactivar modo mantenimiento en todos los CIs afectados",
     "CIs vuelven a estado 'active'; monitorización de alertas reactiva",
     5, "Ingeniero de operaciones", True,
     "cmdb update-status --ci-ids <affected_ids> --status active", "hay_parada"),

    # ── Si hay que volver atrás ──────────────────────────────────────────────
    ("rollback_validation", "config_restore",
     "Verificar que la configuración anterior ha sido restaurada correctamente",
     "CIs con versión de configuración idéntica a la del snapshot pre-cambio",
     15, "Equipo técnico", False, "", None),
    ("rollback_validation", "smoke",
     "Smoke tests post-rollback sobre CIs afectados",
     "Todos los CIs responden y funcionan igual que antes del cambio",
     15, "QA / DevOps", True,
     "smoke-test --suite post_rollback --ci-ids <affected_ids>", None),
    ("rollback_validation", "cmdb_revert",
     "Confirmar que el CMDB refleja el estado pre-cambio",
     "Registro de CMDB coincide con el baseline capturado en pre_change",
     10, "CMDB Admin", False, "", None),
    ("rollback_validation", "incident_check",
     "Verificar ausencia de incidentes activos generados por el rollback",
     "Sin tickets de incidente abiertos atribuibles al cambio o su rollback",
     10, "NOC / Operaciones", True,
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
        "cis": ", ".join(c["name"] for c in ci_details[:3]) or "N/A",
        "mitad_de_cis": min(n_cis // 2, 5),
        # La monitorización dura lo que dure la parada, con un tope: sin parada
        # declarada, o con una muy larga, media hora es lo razonable.
        "minutos_de_monitorizacion": parada if 0 < parada <= 60 else 30,
        "riesgo_alto": riesgo in ("high", "critical"),
        "riesgo_medio": riesgo in ("medium", "high", "critical"),
        "hay_parada": parada > 0,
        "muchos_cis": n_cis > 3,
    }


def _pasos_aplicables(ctx: dict) -> list[dict]:
    """Los pasos de la tabla que aplican a este cambio, ya numerados."""
    pasos: list[dict] = []
    for fase, tipo, desc, esperado, minutos, responsable, automatico, comando, condicion in _PASOS_DEL_PLAN:
        if condicion and not ctx[condicion]:
            continue
        entrada = {
            "step": len(pasos) + 1,
            "phase": fase,
            "test_type": tipo,
            "description": desc.format(**ctx),
            "expected_result": esperado.format(**ctx),
            "estimated_minutes": ctx[minutos] if isinstance(minutos, str) else minutos,
            "responsible": responsable,
            "automated": automatico,
        }
        if comando:
            entrada["command"] = comando
        pasos.append(entrada)
    return pasos


def generate_testing_plan(
    db: Session,
    change_id: str,
    current_user_id: Optional[str] = None,
) -> dict:
    """Plan de pruebas con pasos ejecutables, adaptado al riesgo y al nº de CIs.

    Cuatro fases: validación previa, hitos durante la ventana, pruebas de humo
    y funcionales al terminar, y confirmación si hay que volver atrás.

    Se guarda en `AppSetting` para poder consultarlo después.
    """
    change = db.query(ITSMChangeRequest).filter(ITSMChangeRequest.id == change_id).first()
    if not change:
        raise ErrorDeDominio(404, f"Change {change_id} not found")

    riesgo = score_change_risk(db, change)
    etiqueta = riesgo["risk_label"]
    ci_details = _get_ci_details(db, riesgo["ci_ids_expanded"])

    pasos = _pasos_aplicables(_contexto_del_plan(change, etiqueta, ci_details))

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
    if hasattr(change, "test_plan") and not change.test_plan:
        lineas = [f"[Auto-generated — {etiqueta.upper()} risk — {len(pasos)} steps]"]
        lineas += [f"{p['step']}. [{p['phase']}] {p['description']}" for p in pasos]
        change.test_plan = "\n".join(lineas)
    db.commit()
    return plan
