"""
RACI service — business logic extracted from raci.py endpoint.
Covers: serialisers for User / RACIEntry / ChangelogEntry / UATCase,
        sprint retrospective insights computation, and burnout risk computation.
"""
from __future__ import annotations

from datetime import date, datetime, timedelta
from typing import TYPE_CHECKING, Optional

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.services.settings_service.por_empresa import capacidad_semanal
from app.models.user import User
from app.models.task import Task, TaskStatus
from app.models.sprints import Sprint, SprintTask
from app.models.imputation import Imputation
from app.models.raci import (
    RACIEntry,
    BurnoutRiskLevel,
    ProjectChangelogEntry,
    UATCase,
)
from app.models.project import Project
from app.models.raci import RACIRole
from app.models.raci import SprintRetroNote
from app.models.raci import BurnoutRiskSnapshot
from app.models.raci import ProjectChangelogEntry as PCE, ChangelogEntryType
from app.models.raci import UATStatus
from app.models.sprints import Sprint as _Sprint
from app.models.task import Task as _Task, TaskPriority
from app.models.user import User as _User
from app.models.user import UserStatus
from datetime import timezone
from app.core import timeutil
from app.core.codigos_de_error import ErrorConCodigo

if TYPE_CHECKING:
    pass   # avoid circular imports at runtime


# ── Serialisers ───────────────────────────────────────────────────────────────

def serialize_user(u: User) -> dict:
    return {
        "id": u.id,
        "full_name": u.full_name,
        "role": u.role,
        "department": u.department,
        "job_title": getattr(u, "job_title", None),
        "avatar_initials": u.full_name[:2].upper(),
    }


def serialize_raci_entry(e: RACIEntry) -> dict:
    return {
        "id": e.id,
        "project_id": e.project_id,
        "item_type": e.item_type,
        "item_label": e.item_label,
        "item_id": e.item_id,
        "user_id": e.user_id,
        "role": e.role.value,
        "user": serialize_user(e.user) if e.user else None,
    }


def serialize_changelog_entry(e: ProjectChangelogEntry) -> dict:
    return {
        "id": e.id,
        "project_id": e.project_id,
        "version_tag": e.version_tag,
        "entry_date": e.entry_date.isoformat() if e.entry_date else None,
        "entry_type": e.entry_type.value,
        "title": e.title,
        "description": e.description,
        "is_auto_generated": e.is_auto_generated,
        "author": serialize_user(e.author) if e.author else None,
        "created_at": e.created_at.isoformat() if e.created_at else None,
    }


def serialize_uat_case(c: UATCase) -> dict:
    return {
        "id": c.id,
        "project_id": c.project_id,
        "task_id": c.task_id,
        "title": c.title,
        "description": c.description,
        "expected_result": c.expected_result,
        "actual_result": c.actual_result,
        "status": c.status.value if c.status else "pending",
        "priority": c.priority,
        "assigned_to_id": c.assigned_to_id,
        "assigned_to": serialize_user(c.assigned_to) if c.assigned_to else None,
        "task_title": c.task.title if c.task else None,
        "notes": c.notes,
        "executed_at": c.executed_at.isoformat() if c.executed_at else None,
        "created_at": c.created_at.isoformat() if c.created_at else None,
        "updated_at": c.updated_at.isoformat() if c.updated_at else None,
    }


# ── Sprint retrospective ──────────────────────────────────────────────────────

def _metricas_de_sprint(sprint: Sprint, db: Session) -> dict:
    """Los números del sprint. Sin juicio: sólo cuentas."""
    tareas = (
        db.query(Task)
        .join(SprintTask, SprintTask.task_id == Task.id)
        .filter(SprintTask.sprint_id == sprint.id)
        .all()
    )
    total = len(tareas)
    hechas = [t for t in tareas if t.status == TaskStatus.done]
    bloqueadas = [t for t in tareas if t.status == TaskStatus.blocked]
    en_curso = [t for t in tareas if t.status == TaskStatus.in_progress]

    horas_planificadas = sum(t.estimated_hours or 0 for t in tareas)
    # Para las hechas se usan las horas reales, y las estimadas sólo si no hay
    # reales: lo contrario mediría la planificación, no la entrega.
    horas_hechas = sum(t.actual_hours or t.estimated_hours or 0 for t in hechas)

    # Tareas metidas con el sprint ya empezado: el indicador de scope creep.
    metidas_a_media = 0
    if sprint.start_date and hasattr(SprintTask, "added_at"):
        inicio = datetime.combine(sprint.start_date, datetime.min.time())
        metidas_a_media = sum(
            1 for st in db.query(SprintTask).filter(SprintTask.sprint_id == sprint.id).all()
            if st.added_at and st.added_at > inicio
        )

    arrastre = len(en_curso) + len([
        t for t in tareas if t.status not in (TaskStatus.done, TaskStatus.cancelled)
    ])

    return {
        "total_tasks": total,
        "completed": len(hechas),
        "blocked": len(bloqueadas),
        "carryover": arrastre,
        "added_mid_sprint": metidas_a_media,
        "completion_rate_pct": round(len(hechas) / total * 100, 1) if total > 0 else 0,
        "planned_hours": horas_planificadas,
        "completed_hours": horas_hechas,
        "velocity_ratio_pct": (
            round(horas_hechas / horas_planificadas * 100, 1) if horas_planificadas > 0 else 0
        ),
    }


#: Las conclusiones, como tabla: (condición, apartado, texto, acción, riesgo).
#:
#: Auditoría 2026-09 (hallazgo 18): eran once `if` encadenados con los textos en
#: línea, y de ahí salía la complejidad 14. Como tabla se puede leer entera de
#: una vez —que es lo que hace falta para discutir los umbrales con quien lleva
#: el equipo— y añadir una regla es añadir una fila.
#:
#: La condición recibe el diccionario de métricas y devuelve un booleano. El
#: texto se formatea con esas mismas métricas.
_REGLAS_DE_RETRO: tuple[tuple, ...] = (
    (lambda m: m["completion_rate_pct"] >= 85, "went_well",
     "raci.r_completitud", None, None),
    (lambda m: m["completion_rate_pct"] >= 95, "went_well",
     "raci.r_predecible", None, None),
    (lambda m: m["blocked"] == 0, "went_well",
     "raci.r_sin_bloqueos", None, None),
    (lambda m: m["velocity_ratio_pct"] >= 90, "went_well",
     "raci.r_velocity", None, None),

    (lambda m: m["completion_rate_pct"] < 70, "improve",
     "raci.r_completitud_baja",
     "raci.a_criterios", None),
    (lambda m: m["blocked"] > 0, "improve",
     "raci.r_bloqueadas",
     "raci.a_standup", None),
    (lambda m: m["added_mid_sprint"] > 2, "improve",
     "raci.r_scope_creep",
     "raci.a_politica", None),
    (lambda m: m["carryover"] > 0, "improve",
     "raci.r_carryover", None, None),
    (lambda m: m["velocity_ratio_pct"] < 70, "improve",
     "raci.r_velocity_baja", None,
     "raci.k_optimistas"),

    (lambda m: m["completion_rate_pct"] >= 80 and m["blocked"] == 0, None, None,
     "raci.a_continuar", None),
)


def compute_retro_insights(sprint: Sprint, db: Session) -> dict:
    """Conclusiones de retrospectiva a partir de los datos del sprint.

    No necesita modelo de lenguaje: son reglas sobre métricas, y por eso el
    resultado es el mismo dos veces seguidas, que es lo que una retrospectiva
    necesita para poder discutirse.
    """
    m = _metricas_de_sprint(sprint, db)
    from app.services.textos_de_salida_servicios_m_z import texto_para
    org_id = db.query(Project.organization_id).filter(Project.id == sprint.project_id).scalar()

    def _t(clave: str, **p) -> str:
        return texto_para(db, clave, org_id=org_id, **p)

    went_well: list[str] = []
    improve: list[str] = []
    actions: list[dict] = []
    risks: list[str] = []
    cajones = {"went_well": went_well, "improve": improve}

    for condicion, apartado, texto, accion, riesgo in _REGLAS_DE_RETRO:
        if not condicion(m):
            continue
        if apartado and texto:
            cajones[apartado].append(_t(texto, **m))
        if accion:
            actions.append({"text": _t(accion), "owner_id": None})
        if riesgo:
            risks.append(_t(riesgo))

    # Una retrospectiva sin nada que decir no ayuda a nadie: si ninguna regla
    # encajó, se dice eso explícitamente en vez de dejar la lista vacía.
    if not went_well:
        went_well.append(_t("raci.bien_defecto"))
    if not improve:
        improve.append(_t("raci.mejorar_defecto"))

    return {
        "metrics": m,
        "went_well": went_well,
        "improve": improve,
        "actions": actions,
        "risks": risks,
    }


# ── Burnout risk ──────────────────────────────────────────────────────────────

#: Señales de agotamiento: (condición sobre las métricas, puntos, texto).
#: `puntos` puede ser `None` cuando la señal sólo añade una observación sin
#: subir la puntuación — cuatro semanas seguidas ya han sumado por la racha.
#:
#: Auditoría 2026-09 (hallazgo 18): eran cinco `if` seguidos con los textos en
#: línea. Como tabla se ve la escala de pesos de un vistazo, que es lo que hay
#: que poder revisar con quien lleva el equipo.
_SENALES_DE_AGOTAMIENTO: tuple[tuple, ...] = (
    (lambda m: m["current"] > 100, 25, "raci.b_actual"),
    (lambda m: m["media_4s"] > 90, 20, "raci.b_media"),
    (lambda m: m["racha"] >= 2, "racha_x10", "raci.b_racha"),
    (lambda m: m["racha"] >= 4, None, "raci.b_alto"),
    (lambda m: m["current"] > 130, 20, "raci.b_severa"),
)

#: Umbrales de nivel, de más grave a menos. El primero que alcance manda.
_NIVELES_DE_AGOTAMIENTO = (
    (70, BurnoutRiskLevel.red),
    (45, BurnoutRiskLevel.orange),
    (20, BurnoutRiskLevel.yellow),
    (0, BurnoutRiskLevel.green),
)


def _semanas_de_carga(user: User, db: Session, today: date) -> list[dict]:
    """La carga semanal de las últimas ocho semanas, la más reciente primero."""
    semanas = []
    for w in range(8):
        fin = today - timedelta(days=today.weekday()) - timedelta(weeks=w - 1)
        inicio = fin - timedelta(days=7)
        horas = db.query(func.sum(Imputation.hours)).filter(
            Imputation.user_id == user.id,
            Imputation.date >= inicio,
            Imputation.date < fin,
        ).scalar() or 0.0
        capacidad = capacidad_semanal(db, user)
        semanas.append({
            "week_start": inicio,
            "hours": horas,
            "capacity": capacidad,
            # Ronda 2 auditoría 2026-11-22: capacidad 0 (jornada sin horas,
            # baja, externo sin contrato) daba ZeroDivisionError → 500.
            "load_pct": round(horas / capacidad * 100, 1) if capacidad else (100.0 if horas else 0.0),
        })
    return semanas


def compute_user_burnout_risk(user: User, db: Session, today: date) -> dict:
    """Riesgo de agotamiento de una persona, según su carga de las últimas 8 semanas."""
    semanas = _semanas_de_carga(user, db, today)

    actual = semanas[0]["load_pct"] if semanas else 0
    media_4s = (
        sum(w["load_pct"] for w in semanas[:4]) / 4 if len(semanas) >= 4 else actual
    )

    # Semanas consecutivas por encima del 100 %, contando desde la más reciente:
    # el bucle para en la primera que no lo esté, y eso es lo que hace que sea
    # una racha viva y no un recuento histórico.
    racha = 0
    for w in semanas:
        if w["load_pct"] <= 100:
            break
        racha += 1

    from app.services.textos_de_salida_servicios_m_z import texto_para
    m = {"current": actual, "media_4s": media_4s, "racha": racha}
    puntos = 0.0
    factores = []
    for condicion, peso, texto in _SENALES_DE_AGOTAMIENTO:
        if not condicion(m):
            continue
        if peso == "racha_x10":
            puntos += racha * 10
        elif peso:
            puntos += peso
        factores.append(texto_para(db, texto, user_id=user.id, **m))

    puntos = min(puntos, 100)
    nivel = next(n for umbral, n in _NIVELES_DE_AGOTAMIENTO if puntos >= umbral)

    return {
        "user_id": user.id,
        "full_name": user.full_name,
        "department": user.department,
        "job_title": getattr(user, "job_title", None),
        "current_load_pct": actual,
        "avg_load_4w": round(media_4s, 1),
        "overload_weeks_streak": racha,
        "risk_score": round(puntos, 1),
        "risk_level": nivel.value,
        "factors": factores,
        "weekly_history": [
            {
                "week_start": w["week_start"].isoformat(),
                "load_pct": w["load_pct"],
                "hours": round(w["hours"], 1),
            }
            for w in semanas
        ],
    }


# ── RACI Matrix CRUD ──────────────────────────────────────────────────────────

def get_project_raci(project_id: str, db: Session) -> dict:
    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        raise ErrorConCodigo("no_encontrado", detail="Proyecto no encontrado", que="proyecto")
    entries = (
        db.query(RACIEntry)
        .filter(
            RACIEntry.project_id == project_id,
            RACIEntry.is_active == True,  # audit #36 soft-delete
        )
        .order_by(RACIEntry.item_type, RACIEntry.item_label)
        .all()
    )
    items: dict = {}
    for e in entries:
        key = (e.item_type, e.item_label, e.item_id or "")
        if key not in items:
            items[key] = {"item_type": e.item_type, "item_label": e.item_label,
                          "item_id": e.item_id, "assignments": []}
        items[key]["assignments"].append({
            "entry_id": e.id, "user_id": e.user_id, "role": e.role.value,
            "user": serialize_user(e.user) if e.user else None,
        })
    return {
        "project_id": project_id,
        "project_name": project.name,
        "items": list(items.values()),
        "raw_entries": [serialize_raci_entry(e) for e in entries],
        "total": len(entries),
    }


def upsert_raci(project_id: str, entries_in: list, db: Session) -> dict:
    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        raise ErrorConCodigo("no_encontrado", detail="Proyecto no encontrado", que="proyecto")
    created, updated = 0, 0
    for entry_in in entries_in:
        try:
            role_enum = RACIRole(entry_in.role.upper())
        except ValueError:
            raise ErrorConCodigo("raci_rol_no_valido", detail=f"422:Rol RACI inválido: '{entry_in.role}'. Usa R, A, C o I.", rol=entry_in.role)
        user = db.query(_User).filter(_User.id == entry_in.user_id).first()
        if not user:
            raise ErrorConCodigo("no_encontrado", detail=f"Usuario {entry_in.user_id} no encontrado", que="usuario")
        existing = (
            db.query(RACIEntry)
            .filter(
                RACIEntry.project_id == project_id,
                RACIEntry.item_label == entry_in.item_label,
                RACIEntry.user_id == entry_in.user_id,
            )
            .first()
        )
        if existing:
            existing.role = role_enum
            existing.item_type = entry_in.item_type
            existing.item_id = entry_in.item_id
            existing.is_active = True  # audit #36 — re-upsert reactiva
            existing.updated_at = datetime.now(timezone.utc)
            updated += 1
        else:
            db.add(RACIEntry(
                project_id=project_id,
                item_type=entry_in.item_type,
                item_label=entry_in.item_label,
                item_id=entry_in.item_id,
                user_id=entry_in.user_id,
                role=role_enum,
            ))
            created += 1
    db.commit()
    return {"created": created, "updated": updated}


def delete_raci_entry(project_id: str, entry_id: str, db: Session) -> None:
    entry = db.query(RACIEntry).filter(
        RACIEntry.id == entry_id, RACIEntry.project_id == project_id
    ).first()
    if not entry:
        raise ErrorConCodigo("no_encontrado", detail="Entrada RACI no encontrada", que="entrada_raci")
    # audit #36 soft-delete — la matriz RACI conserva histórico de responsables.
    entry.is_active = False
    db.commit()


# ── Sprint Retrospective ──────────────────────────────────────────────────────

def get_sprint_retrospective(project_id: str, sprint_id: str, db: Session) -> dict:
    import json as _json
    sprint = db.query(_Sprint).filter(
        _Sprint.id == sprint_id, _Sprint.project_id == project_id
    ).first()
    if not sprint:
        raise ErrorConCodigo("no_encontrado", detail="Sprint no encontrado", que="sprint")
    insights = compute_retro_insights(sprint, db)
    saved = db.query(SprintRetroNote).filter(SprintRetroNote.sprint_id == sprint_id).first()
    return {
        "sprint_id": sprint_id,
        "sprint_name": sprint.name,
        "sprint_status": sprint.status.value if sprint.status else None,
        "start_date": sprint.start_date.isoformat() if sprint.start_date else None,
        "end_date": sprint.end_date.isoformat() if sprint.end_date else None,
        "computed_insights": insights,
        "saved_notes": {
            "id": saved.id,
            "manual_notes": saved.manual_notes,
            "action_items": _json.loads(saved.action_items) if saved and saved.action_items else [],
            "updated_at": saved.updated_at.isoformat() if saved and saved.updated_at else None,
        } if saved else None,
    }


def save_sprint_retrospective(
    project_id: str, sprint_id: str, payload, current_user_id: str, db: Session
) -> dict:
    import json as _json
    sprint = db.query(_Sprint).filter(
        _Sprint.id == sprint_id, _Sprint.project_id == project_id
    ).first()
    if not sprint:
        raise ErrorConCodigo("no_encontrado", detail="Sprint no encontrado", que="sprint")
    insights = compute_retro_insights(sprint, db)
    m = insights["metrics"]
    saved = db.query(SprintRetroNote).filter(SprintRetroNote.sprint_id == sprint_id).first()
    if saved:
        saved.manual_notes = payload.manual_notes
        if payload.action_items is not None:
            saved.action_items = _json.dumps(payload.action_items)
        saved.updated_at = datetime.now(timezone.utc)
    else:
        saved = SprintRetroNote(
            sprint_id=sprint_id,
            project_id=project_id,
            velocity_completed=m["completed_hours"],
            velocity_planned=m["planned_hours"],
            completion_rate_pct=m["completion_rate_pct"],
            blocked_count=m["blocked"],
            added_mid_sprint=m["added_mid_sprint"],
            carryover_count=m["carryover"],
            went_well_items=_json.dumps(insights["went_well"]),
            improve_items=_json.dumps(insights["improve"]),
            action_items=_json.dumps(payload.action_items or insights["actions"]),
            risk_flags=_json.dumps(insights["risks"]),
            manual_notes=payload.manual_notes,
            facilitated_by_id=current_user_id,
        )
        db.add(saved)
    db.commit()
    db.refresh(saved)
    return {"id": saved.id, "sprint_id": sprint_id, "updated_at": saved.updated_at.isoformat()}


# ── Burnout Risk ──────────────────────────────────────────────────────────────

def get_burnout_risk(department: "Optional[str]", min_risk_level: "Optional[str]", db: Session) -> dict:
    today = timeutil.today()
    q = db.query(_User).filter(_User.is_active == True, _User.status == UserStatus.active)
    if department:
        q = q.filter(_User.department == department)
    users = q.all()
    results = [compute_user_burnout_risk(u, db, today) for u in users]
    if min_risk_level:
        order = [BurnoutRiskLevel.green.value, BurnoutRiskLevel.yellow.value,
                 BurnoutRiskLevel.orange.value, BurnoutRiskLevel.red.value]
        try:
            min_idx = order.index(min_risk_level)
            results = [r for r in results if order.index(r["risk_level"]) >= min_idx]
        # intentional: best-effort fallback, log noise outweighs diagnostic value
        except ValueError:
            pass
    results.sort(key=lambda r: r["risk_score"], reverse=True)
    level_counts = {v.value: 0 for v in BurnoutRiskLevel}
    for r in results:
        level_counts[r["risk_level"]] += 1
    return {
        "computed_at": datetime.now(timezone.utc).isoformat(),
        "total_analyzed": len(results),
        "summary": level_counts,
        "team_avg_load": round(sum(r["current_load_pct"] for r in results) / len(results), 1) if results else 0,
        "members": results,
    }


def compute_and_save_burnout_snapshots(db: Session) -> dict:
    import json as _json
    today = timeutil.today()
    week_start = today - timedelta(days=today.weekday())
    users = db.query(_User).filter(_User.is_active == True, _User.status == UserStatus.active).all()
    saved_count = 0
    for user in users:
        risk_data = compute_user_burnout_risk(user, db, today)
        existing = db.query(BurnoutRiskSnapshot).filter(
            BurnoutRiskSnapshot.user_id == user.id,
            BurnoutRiskSnapshot.week_start == week_start,
        ).first()
        level = BurnoutRiskLevel(risk_data["risk_level"])
        if existing:
            existing.load_pct = risk_data["current_load_pct"]
            existing.overload_weeks_streak = risk_data["overload_weeks_streak"]
            existing.avg_load_4w = risk_data["avg_load_4w"]
            existing.risk_level = level
            existing.risk_score = risk_data["risk_score"]
            existing.factors = _json.dumps(risk_data["factors"])
        else:
            db.add(BurnoutRiskSnapshot(
                user_id=user.id,
                week_start=week_start,
                load_pct=risk_data["current_load_pct"],
                overload_weeks_streak=risk_data["overload_weeks_streak"],
                avg_load_4w=risk_data["avg_load_4w"],
                risk_level=level,
                risk_score=risk_data["risk_score"],
                factors=_json.dumps(risk_data["factors"]),
            ))
            saved_count += 1
    db.commit()
    return {"week_start": week_start.isoformat(), "processed": len(users), "new_snapshots": saved_count}


# ── Project Changelog ─────────────────────────────────────────────────────────

def get_project_changelog(
    project_id: str, entry_type: "Optional[str]", since: "Optional[date]", db: Session
) -> dict:
    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        raise ErrorConCodigo("no_encontrado", detail="Proyecto no encontrado", que="proyecto")
    q = db.query(PCE).filter(
        PCE.project_id == project_id,
        PCE.is_active == True,  # audit #36 soft-delete
    )
    if entry_type:
        try:
            q = q.filter(PCE.entry_type == ChangelogEntryType(entry_type))
        # intentional: best-effort fallback, log noise outweighs diagnostic value
        except ValueError:
            pass
    if since:
        q = q.filter(PCE.entry_date >= since)
    entries = q.order_by(PCE.entry_date.desc()).all()
    return {
        "project_id": project_id,
        "project_name": project.name,
        "total": len(entries),
        "entries": [serialize_changelog_entry(e) for e in entries],
    }


def create_changelog_entry(project_id: str, payload, author_id: str, db: Session) -> dict:
    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        raise ErrorConCodigo("no_encontrado", detail="Proyecto no encontrado", que="proyecto")
    try:
        entry_type = ChangelogEntryType(payload.entry_type)
    except ValueError:
        raise ErrorConCodigo("valor_no_valido", detail=f"422:Tipo de entrada inválido: '{payload.entry_type}'", valor=payload.entry_type)
    entry = PCE(
        project_id=project_id,
        version_tag=payload.version_tag,
        entry_date=payload.entry_date,
        entry_type=entry_type,
        title=payload.title,
        description=payload.description,
        is_auto_generated=False,
        author_id=author_id,
    )
    db.add(entry)
    db.commit()
    db.refresh(entry)
    entry = db.query(PCE).filter(PCE.id == entry.id).first()
    return serialize_changelog_entry(entry)


def generate_changelog(
    project_id: str, weeks: int, version_tag: "Optional[str]", author_id: str, db: Session
) -> dict:
    import json as _json
    from app.services.textos_de_salida_servicios_m_z import texto_para
    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        raise ErrorConCodigo("no_encontrado", detail="Proyecto no encontrado", que="proyecto")
    since = timeutil.today() - timedelta(weeks=weeks)
    since_dt = datetime.combine(since, datetime.min.time())
    completed_tasks = (
        db.query(_Task)
        .filter(
            _Task.project_id == project_id,
            _Task.status == TaskStatus.done,
            # Revisión 2026-11: cuenta cuándo se terminó, no la última edición;
            # una tarea sin ninguna de las dos fechas ya no entra siempre.
            func.coalesce(_Task.completed_at, _Task.updated_at) >= since_dt,
        )
        .order_by(_Task.priority, func.coalesce(_Task.completed_at, _Task.updated_at).desc())
        .limit(100)
        .all()
    )
    if not completed_tasks:
        return {"generated": 0, "message": texto_para(db, "raci.sin_tareas", user_id=author_id)}

    def _guess_type(task) -> ChangelogEntryType:
        title_lower = (task.title or "").lower()
        if any(kw in title_lower for kw in ["bug", "fix", "error", "fallo", "corrección"]):
            return ChangelogEntryType.bugfix
        if any(kw in title_lower for kw in ["mejora", "optimiz", "refactor", "perf"]):
            return ChangelogEntryType.improvement
        if any(kw in title_lower for kw in ["roto", "breaking", "elimina", "depreca"]):
            return ChangelogEntryType.breaking
        if task.priority == TaskPriority.critical:
            return ChangelogEntryType.feature
        return ChangelogEntryType.feature

    created_entries = []
    for task in completed_tasks:
        existing = db.query(PCE).filter(
            PCE.project_id == project_id,
            PCE.source_task_ids.contains(f'"{task.id}"'),
        ).first()
        if existing:
            continue
        entry = PCE(
            project_id=project_id,
            version_tag=version_tag,
            entry_date=(task.completed_at or task.updated_at or task.created_at).date() if (task.completed_at or task.updated_at or task.created_at) else timeutil.today(),
            entry_type=_guess_type(task),
            title=task.title,
            description=task.description,
            is_auto_generated=True,
            source_task_ids=_json.dumps([task.id]),
            author_id=author_id,
        )
        db.add(entry)
        created_entries.append(task.id)
    db.commit()
    return {
        "generated": len(created_entries),
        "version_tag": version_tag,
        "period_weeks": weeks,
        "task_ids": created_entries,
    }


def update_changelog_entry(project_id: str, entry_id: str, payload, db: Session) -> dict:
    entry = db.query(PCE).filter(
        PCE.id == entry_id, PCE.project_id == project_id
    ).first()
    if not entry:
        raise ErrorConCodigo("no_encontrado", detail="Entrada no encontrada", que="entrada")
    if payload.version_tag is not None:
        entry.version_tag = payload.version_tag
    if payload.entry_date is not None:
        entry.entry_date = payload.entry_date
    if payload.entry_type is not None:
        try:
            entry.entry_type = ChangelogEntryType(payload.entry_type)
        except ValueError:
            raise ErrorConCodigo("tipo_no_valido_valor", detail=f"422:Tipo inválido: '{payload.entry_type}'", tipo=payload.entry_type)
    if payload.title is not None:
        entry.title = payload.title
    if payload.description is not None:
        entry.description = payload.description
    entry.updated_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(entry)
    entry = db.query(PCE).filter(PCE.id == entry.id).first()
    return serialize_changelog_entry(entry)


def delete_changelog_entry(project_id: str, entry_id: str, db: Session) -> None:
    entry = db.query(PCE).filter(
        PCE.id == entry_id, PCE.project_id == project_id
    ).first()
    if not entry:
        raise ErrorConCodigo("no_encontrado", detail="Entrada no encontrada", que="entrada")
    # audit #36 soft-delete — conserva historial de releases.
    entry.is_active = False
    db.commit()


# ── UAT Cases ─────────────────────────────────────────────────────────────────

def list_uat_cases(
    project_id: str, status: "Optional[str]", task_id: "Optional[str]", db: Session
) -> dict:
    q = db.query(UATCase).filter(
        UATCase.project_id == project_id,
        UATCase.is_active == True,  # audit #36 soft-delete
    )
    if status:
        try:
            q = q.filter(UATCase.status == UATStatus(status))
        # intentional: best-effort fallback, log noise outweighs diagnostic value
        except ValueError:
            pass
    if task_id:
        q = q.filter(UATCase.task_id == task_id)
    cases = q.order_by(UATCase.created_at.desc()).all()
    stats = {
        "total": len(cases),
        "pending": sum(1 for c in cases if c.status == UATStatus.pending),
        "passed": sum(1 for c in cases if c.status == UATStatus.passed),
        "failed": sum(1 for c in cases if c.status == UATStatus.failed),
        "blocked": sum(1 for c in cases if c.status == UATStatus.blocked),
    }
    return {"cases": [serialize_uat_case(c) for c in cases], "stats": stats}


def create_uat_case(project_id: str, payload, db: Session) -> dict:
    case = UATCase(
        project_id=project_id,
        task_id=payload.task_id or None,
        title=payload.title,
        description=payload.description,
        expected_result=payload.expected_result,
        actual_result=payload.actual_result,
        status=UATStatus(payload.status) if payload.status else UATStatus.pending,
        priority=payload.priority or "medium",
        assigned_to_id=payload.assigned_to_id or None,
        notes=payload.notes,
    )
    db.add(case)
    db.commit()
    db.refresh(case)
    return serialize_uat_case(case)


def _uat_case_activo(project_id: str, case_id: str, db: Session):
    """El caso UAT vivo del proyecto, o None.

    Segunda auditoria 2026-11: editar y borrar buscaban sin `is_active`, asi
    que un caso borrado (soft-delete) se podia seguir editando por id.
    """
    return db.query(UATCase).filter(
        UATCase.id == case_id, UATCase.project_id == project_id,
        UATCase.is_active == True,  # noqa: E712
    ).first()


def update_uat_case(project_id: str, case_id: str, payload, db: Session) -> dict:
    case = _uat_case_activo(project_id, case_id, db)
    if not case:
        raise ErrorConCodigo("no_encontrado", detail="Caso UAT no encontrado", que="caso_uat")
    for field, val in payload.model_dump(exclude_unset=True).items():
        if field == "status" and val:
            setattr(case, field, UATStatus(val))
        elif field in ("task_id", "assigned_to_id"):
            setattr(case, field, val or None)
        else:
            setattr(case, field, val)
    if payload.status in ("passed", "failed", "blocked"):
        case.executed_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(case)
    return serialize_uat_case(case)


def delete_uat_case(project_id: str, case_id: str, db: Session) -> None:
    case = _uat_case_activo(project_id, case_id, db)
    if not case:
        raise ErrorConCodigo("no_encontrado", detail="Caso UAT no encontrado", que="caso_uat")
    # audit #36 soft-delete — preserva el caso para histórico de QA.
    case.is_active = False
    db.commit()


def export_uat_report(project_id: str, db: Session, idioma: Optional[str] = None) -> dict:
    """El plan de pruebas UAT en Markdown.

    18-11-2026 (auditoria de textos fijos): en `idioma` (por defecto, el de la
    empresa del proyecto) y con la hora en la zona de la empresa y su etiqueta
    (antes «UTC» fijo y castellano).
    """
    from app.services.formato_regional import idioma_de_salida, sello_de_hora
    from app.services.textos_de_salida import texto
    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        raise ErrorConCodigo("no_encontrado", detail="Proyecto no encontrado", que="proyecto")
    cases = db.query(UATCase).filter(
        UATCase.project_id == project_id,
        UATCase.is_active == True,  # audit #36 soft-delete
    ).order_by(UATCase.created_at).all()
    STATUS_EMOJI = {"pending": "⏳", "passed": "✅", "failed": "❌", "blocked": "🔒", "skipped": "⏭"}
    PRIORITY_ORDER = {"critical": 0, "high": 1, "medium": 2, "low": 3}
    sorted_cases = sorted(cases, key=lambda c: PRIORITY_ORDER.get(c.priority, 2))
    org_id = getattr(project, "organization_id", None)
    idioma = idioma_de_salida(db, org_id=org_id, preferido=idioma)

    def t(clave, **datos):
        return texto(clave, idioma, **datos)
    lines = [
        f"# {t('uat.titulo', proyecto=project.name)}",
        t("raci.generado", cuando=sello_de_hora(db, org_id, idioma)),
        "",
        t("uat.totales", total=len(cases),
          pendientes=sum(1 for c in cases if c.status == UATStatus.pending),
          pasados=sum(1 for c in cases if c.status == UATStatus.passed),
          fallidos=sum(1 for c in cases if c.status == UATStatus.failed)),
        "",
        "---",
    ]
    for i, c in enumerate(sorted_cases, 1):
        st = STATUS_EMOJI.get(c.status.value, "?")
        lines += [
            "",
            f"## {i}. {c.title}  {st}",
            f"**{t('uat.prioridad')}:** {c.priority.upper()}  |  **{t('informe.col.estado')}:** {c.status.value}",
        ]
        # Segunda auditoria 2026-11: `UATCase` no tiene `task_title` (es una
        # clave del serializador); leerlo daba AttributeError y el export, 500.
        if c.task:
            lines.append(f"**{t('uat.tarea')}:** {c.task.title}")
        if c.description:
            lines += ["", f"**{t('uat.pasos')}:**", c.description]
        if c.expected_result:
            lines += ["", f"**{t('uat.esperado')}:**", c.expected_result]
        if c.actual_result:
            lines += ["", f"**{t('uat.obtenido')}:**", c.actual_result]
        if c.notes:
            lines += ["", f"**{t('uat.notas')}:**", c.notes]
    return {"project_name": project.name, "text": "\n".join(lines), "cases_count": len(cases)}
