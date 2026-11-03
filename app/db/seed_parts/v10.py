"""Seed v10: Sprints, Expenses, Automations."""
from datetime import date, timedelta, datetime, timezone

from app.core.config import settings

def seed_v10():
    """Seed demo data for v10 modules: Sprints, Expenses, Automations."""
    from app.db.session import SessionLocal
    import json
    from app.models.user import User
    from app.models.project import Project, ProjectStatus as PS
    from app.models.task import Task
    from app.models.sprints import Sprint, SprintTask, SprintStatus
    from app.models.expenses import Expense, ExpenseCategory, ExpenseStatus
    from app.models.automations import AutomationRule, TriggerType
    from app.db.base import Base
    from app.db.session import engine as _eng_v10
    Base.metadata.create_all(bind=_eng_v10)

    db = SessionLocal()
    print("  Seeding v10 modules: Sprints, Expenses, Automations...")

    admin = db.query(User).filter(User.username == "admin").first()
    ana   = db.query(User).filter(User.username == "ana.torres").first()
    luis  = db.query(User).filter(User.username == "luis.vega").first()
    sara  = db.query(User).filter(User.username == "sara.lope").first()

    # Fetch the first active project
    project = db.query(Project).filter(Project.status == PS.active).first()

    if project:
        tasks = db.query(Task).filter(Task.project_id == project.id).limit(12).all()

        # ── SPRINTS ────────────────────────────────────────────────────────
        # Sprint 1 — Completed
        s1 = Sprint(
            project_id=project.id, number=1,
            name="Sprint 1 — Setup y arquitectura",
            goal="Establecer la base técnica del proyecto y arquitectura inicial",
            status=SprintStatus.completed,
            start_date=date.today() - timedelta(days=28),
            end_date=date.today() - timedelta(days=14),
            planned_points=34, completed_points=28, velocity=2.0,
            went_well="Buena coordinación del equipo. Arquitectura aprobada en primera revisión.",
            to_improve="Las estimaciones fueron optimistas. Daily demasiado largas.",
            action_items="Reducir daily a 15min. Usar poker planning para próximo sprint.",
            created_by=ana.id if ana else None,
        )
        db.add(s1); db.flush()

        # Assign first 4 tasks to sprint 1 as done
        for i, task in enumerate(tasks[:4]):
            db.add(SprintTask(sprint_id=s1.id, task_id=task.id, backlog_order=i))

        # Sprint 2 — Active
        s2 = Sprint(
            project_id=project.id, number=2,
            name="Sprint 2 — Módulo de usuarios",
            goal="Completar CRUD de usuarios, permisos y autenticación JWT",
            status=SprintStatus.active,
            start_date=date.today() - timedelta(days=7),
            end_date=date.today() + timedelta(days=7),
            planned_points=26,
            created_by=ana.id if ana else None,
        )
        db.add(s2); db.flush()

        # Assign next 4 tasks to sprint 2
        for i, task in enumerate(tasks[4:8]):
            db.add(SprintTask(sprint_id=s2.id, task_id=task.id, backlog_order=i))

        # Sprint 3 — Planning (not started)
        s3 = Sprint(
            project_id=project.id, number=3,
            name="Sprint 3 — Integración y reporting",
            goal="Conectar con APIs externas e implementar dashboard de métricas",
            status=SprintStatus.planning,
            start_date=date.today() + timedelta(days=8),
            end_date=date.today() + timedelta(days=22),
            created_by=ana.id if ana else None,
        )
        db.add(s3); db.flush()
        db.flush()
        print("    ✓ 3 sprints creados")

    # ── EXPENSES ───────────────────────────────────────────────────────────
    if project and luis and ana and sara:
        expenses_data = [
            Expense(code="EXP-0001", user_id=luis.id, project_id=project.id,
                category=ExpenseCategory.travel, description="Vuelo Madrid-Barcelona cliente Acme",
                amount=187.50, currency=settings.DEFAULT_CURRENCY, expense_date=date.today() - timedelta(days=20),
                is_billable=True, status=ExpenseStatus.reimbursed,
                submitted_at=datetime.now(timezone.utc)-timedelta(days=18),
                reviewed_by=ana.id, reviewed_at=datetime.now(timezone.utc)-timedelta(days=16),
                reimbursed_at=datetime.now(timezone.utc)-timedelta(days=10),
                notes="Reunión de kick-off con el cliente"),
            Expense(code="EXP-0002", user_id=sara.id, project_id=project.id,
                category=ExpenseCategory.accommodation, description="Hotel 2 noches Barcelona",
                amount=298.00, currency=settings.DEFAULT_CURRENCY, expense_date=date.today() - timedelta(days=19),
                is_billable=True, status=ExpenseStatus.approved,
                submitted_at=datetime.now(timezone.utc)-timedelta(days=17),
                reviewed_by=ana.id, reviewed_at=datetime.now(timezone.utc)-timedelta(days=15)),
            Expense(code="EXP-0003", user_id=luis.id, project_id=project.id,
                category=ExpenseCategory.meals, description="Comida de trabajo con el cliente",
                amount=64.30, currency=settings.DEFAULT_CURRENCY, expense_date=date.today() - timedelta(days=19),
                is_billable=True, status=ExpenseStatus.submitted,
                submitted_at=datetime.now(timezone.utc)-timedelta(days=1)),
            Expense(code="EXP-0004", user_id=ana.id, project_id=project.id,
                category=ExpenseCategory.software, description="Licencia Figma Pro anual",
                amount=144.00, currency=settings.DEFAULT_CURRENCY, expense_date=date.today() - timedelta(days=5),
                is_billable=False, status=ExpenseStatus.submitted,
                submitted_at=datetime.now(timezone.utc)-timedelta(hours=8),
                notes="Herramienta de diseño para mockups del cliente"),
            Expense(code="EXP-0005", user_id=sara.id, project_id=project.id,
                category=ExpenseCategory.training, description="Curso Docker Avanzado (Udemy)",
                amount=29.99, currency=settings.DEFAULT_CURRENCY, expense_date=date.today() - timedelta(days=3),
                is_billable=False, status=ExpenseStatus.draft),
            Expense(code="EXP-0006", user_id=luis.id, project_id=project.id,
                category=ExpenseCategory.travel, description="Tren AVE Valencia reunión técnica",
                amount=112.00, currency=settings.DEFAULT_CURRENCY, expense_date=date.today() - timedelta(days=10),
                is_billable=True, status=ExpenseStatus.rejected,
                submitted_at=datetime.now(timezone.utc)-timedelta(days=9),
                reviewed_by=ana.id, reviewed_at=datetime.now(timezone.utc)-timedelta(days=8),
                rejection_reason="Falta adjuntar el billete como justificante"),
        ]
        db.add_all(expenses_data); db.flush()
        print("    ✓ 6 gastos de ejemplo creados")

    # ── AUTOMATIONS ────────────────────────────────────────────────────────
    # Con la organizacion: una regla sin ella no salta nunca.
    _org_reglas = getattr(admin, "organization_id", None) or getattr(ana, "organization_id", None)
    rules = [
        AutomationRule(
            name="Alerta presupuesto al 85%",
            description="Crea una alerta cuando el gasto supera el 85% del presupuesto del proyecto",
            is_global=True, is_active=True, organization_id=_org_reglas,
            trigger_type=TriggerType.budget_threshold.value,
            trigger_conditions=json.dumps({"field": "budget_pct", "operator": "greater_than", "value": "85"}),
            actions=json.dumps([{"type": "create_alert", "params": {"message": "⚠ Presupuesto superado al 85% — revisar consumo", "severity": "warning"}}]),
            run_count=0, created_by=admin.id if admin else None,
        ),
        AutomationRule(
            name="Notificar equipo al iniciar sprint",
            description="Avisa a todos los empleados cuando se inicia un nuevo sprint",
            is_global=True, is_active=True, organization_id=_org_reglas,
            trigger_type=TriggerType.sprint_started.value,
            trigger_conditions=None,
            actions=json.dumps([{"type": "notify_role", "params": {"role": "employee", "message": "🚀 Nuevo sprint iniciado — revisa el backlog y tus tareas asignadas", "severity": "info"}}]),
            run_count=0, created_by=admin.id if admin else None,
        ),
        AutomationRule(
            name="Recordatorio timesheet viernes",
            description="Recuerda enviar el timesheet cada viernes al equipo",
            is_global=True, is_active=True, organization_id=_org_reglas,
            trigger_type=TriggerType.timesheet_not_submitted.value,
            trigger_conditions=None,
            actions=json.dumps([{"type": "notify_role", "params": {"role": "employee", "message": "📋 Viernes: recuerda enviar tu timesheet semanal antes de las 18h", "severity": "info"}}]),
            run_count=0, created_by=admin.id if admin else None,
        ),
        AutomationRule(
            name="Escalar ticket P1 a L2",
            description="Escala automáticamente los tickets P1 al nivel L2 cuando se crean",
            is_global=True, is_active=True, organization_id=_org_reglas,
            trigger_type=TriggerType.ticket_created.value,
            trigger_conditions=json.dumps({"field": "priority", "operator": "equals", "value": "p1_critical"}),
            actions=json.dumps([
                {"type": "escalate_ticket", "params": {"to_level": "l2"}},
                {"type": "notify_role", "params": {"role": "admin", "message": "🚨 Ticket P1 creado — requiere atención inmediata", "severity": "critical"}},
            ]),
            run_count=0, created_by=admin.id if admin else None,
        ),
        AutomationRule(
            name="Alertar tarea vencida (pausada)",
            description="PAUSADA — Notificar al PM cuando una tarea vence sin completar",
            is_global=True, is_active=False, organization_id=_org_reglas,
            trigger_type=TriggerType.task_overdue.value,
            trigger_conditions=None,
            actions=json.dumps([{"type": "notify_role", "params": {"role": "pm", "message": "⏰ Tarea vencida sin completar en el proyecto", "severity": "warning"}}]),
            run_count=0, created_by=ana.id if ana else None,
        ),
        AutomationRule(
            name="Notificar gasto pendiente de aprobación",
            description="Avisa al PM cuando un empleado envía un gasto para aprobar",
            is_global=True, is_active=True, organization_id=_org_reglas,
            trigger_type=TriggerType.expense_submitted.value,
            trigger_conditions=None,
            actions=json.dumps([{"type": "notify_role", "params": {"role": "pm", "message": "💸 Gasto enviado pendiente de aprobación — revísalo en Gastos > Pendientes", "severity": "info"}}]),
            run_count=0, created_by=admin.id if admin else None,
        ),
    ]
    db.add_all(rules); db.flush()
    print("    ✓ 6 reglas de automatización creadas")

    db.commit()
    db.close()
    print("  ✓ v10 seed completado")
