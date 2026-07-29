"""Seed v12: plantillas de proyecto, workflows, facturas de ejemplo, informes."""
from app.core.config import settings

def seed_v12():
    """Seed v12 demo data: project templates, workflows, sample invoices."""
    from app.db.session import SessionLocal
    import json
    from datetime import date, timedelta
    from app.models.user import User
    from app.models.project import Project
    from app.models.advanced_config import ProjectTemplate, TemplatePhase, TemplateTask
    from app.models.billing_reports import AutomationWorkflow, WorkflowStep, WorkflowStatus, StepType, Invoice, InvoiceLine, InvoiceStatus, ReportDefinition

    from app.db.base import Base as _Base
    from app.db.session import engine as _eng
    _Base.metadata.create_all(bind=_eng)
    db = SessionLocal()
    print("  Seeding v12 modules...")

    if db.query(ProjectTemplate).count() > 0:
        db.close()
        return

    admin = db.query(User).filter(User.username == "admin").first()
    ana   = db.query(User).filter(User.username == "ana.torres").first() # noqa: F841 F401

    # ── Project Templates ──────────────────────────────────────────────────────
    tpl1 = ProjectTemplate(
        name="Implementación ERP", description="Proyecto estándar de implementación de sistema ERP para empresa mediana",
        project_type="consulting", estimated_weeks=16, estimated_hours=480, created_by=admin.id if admin else None,
    )
    tpl2 = ProjectTemplate(
        name="Desarrollo Web a medida", description="Desarrollo de aplicación web con backend REST y frontend React",
        project_type="development", estimated_weeks=12, estimated_hours=360, created_by=admin.id if admin else None,
    )
    tpl3 = ProjectTemplate(
        name="Auditoría IT", description="Auditoría de sistemas, infraestructura y procesos TI",
        project_type="consulting", estimated_weeks=4, estimated_hours=80, created_by=admin.id if admin else None,
    )
    db.add_all([tpl1, tpl2, tpl3]); db.flush()

    # Phases for tpl1 (ERP)
    erp_phases = [
        ("Análisis y diseño", 3, [("Kick-off y toma de requisitos", 16), ("Análisis AS-IS", 24), ("Diseño TO-BE", 32), ("Aprobación de diseño", 8)]),
        ("Configuración", 5, [("Configuración módulo financiero", 40), ("Configuración RRHH", 24), ("Migración de datos", 32), ("Integraciones", 40)]),
        ("Formación y pruebas", 4, [("Formación usuarios clave", 32), ("Pruebas funcionales", 40), ("UAT", 32), ("Corrección de incidencias", 24)]),
        ("Go-live y soporte", 4, [("Go-live", 16), ("Soporte post-implantación", 40), ("Documentación final", 16), ("Cierre de proyecto", 8)]),
    ]
    for i, (phase_name, weeks, tasks) in enumerate(erp_phases):
        ph = TemplatePhase(template_id=tpl1.id, name=phase_name, order=i, estimated_weeks=weeks)
        db.add(ph); db.flush()
        for j, (task_title, hours) in enumerate(tasks):
            db.add(TemplateTask(phase_id=ph.id, title=task_title, estimated_hours=hours, order=j))

    # Phases for tpl2 (Web Dev)
    web_phases = [
        ("Análisis y UX", 2, [("Análisis de requisitos", 16), ("Wireframes y prototipos", 24), ("Aprobación de diseño", 8)]),
        ("Backend", 4, [("Setup arquitectura", 16), ("Desarrollo APIs REST", 80), ("Base de datos", 24), ("Autenticación", 16)]),
        ("Frontend", 4, [("Setup React", 8), ("Componentes base", 40), ("Páginas principales", 80), ("Integración API", 32)]),
        ("Testing y deploy", 2, [("Tests unitarios", 24), ("Tests E2E", 16), ("Deploy producción", 8), ("Documentación", 16)]),
    ]
    for i, (phase_name, weeks, tasks) in enumerate(web_phases):
        ph = TemplatePhase(template_id=tpl2.id, name=phase_name, order=i, estimated_weeks=weeks)
        db.add(ph); db.flush()
        for j, (task_title, hours) in enumerate(tasks):
            db.add(TemplateTask(phase_id=ph.id, title=task_title, estimated_hours=hours, order=j))

    db.flush()

    # ── Automation Workflows ───────────────────────────────────────────────────
    wf1 = AutomationWorkflow(
        name="Escalación automática tickets P1",
        description="Cuando se crea un ticket P1: notificar admin, esperar 30 min, si no asignado → escalar a L3",
        trigger_type="ticket_created",
        trigger_conditions=json.dumps({"field": "priority", "operator": "equals", "value": "p1_critical"}),
        status=WorkflowStatus.active,
        is_global=True, run_count=3, success_count=3,
        created_by=admin.id if admin else None,
    )
    db.add(wf1); db.flush()

    steps_wf1 = [
        WorkflowStep(workflow_id=wf1.id, order=0, step_type=StepType.notify, name="Notificar admin",
                     config=json.dumps({"role": "admin", "message": "🚨 Ticket P1 creado"})),
        WorkflowStep(workflow_id=wf1.id, order=1, step_type=StepType.wait, name="Esperar 30 min",
                     config=json.dumps({"duration": 30, "unit": "minutes"})),
        WorkflowStep(workflow_id=wf1.id, order=2, step_type=StepType.condition, name="¿Asignado?",
                     config=json.dumps({"field": "assigned_to", "operator": "not_equals", "value": "null"}),
                     next_step_yes=None, next_step_no=None),
        WorkflowStep(workflow_id=wf1.id, order=3, step_type=StepType.action, name="Escalar a L3",
                     config=json.dumps({"type": "escalate_ticket", "to_level": "l3"})),
    ]
    db.add_all(steps_wf1)

    wf2 = AutomationWorkflow(
        name="Onboarding nuevo empleado",
        description="Al crear un usuario → crear tareas de onboarding, notificar RRHH, asignar buddy",
        trigger_type="project_status_changed",
        trigger_conditions=json.dumps({"field": "status", "operator": "equals", "value": "active"}),
        status=WorkflowStatus.draft,
        is_global=True, run_count=0,
        created_by=admin.id if admin else None,
    )
    db.add(wf2); db.flush()
    db.add(WorkflowStep(workflow_id=wf2.id, order=0, step_type=StepType.notify, name="Notificar equipo",
                        config=json.dumps({"role": "employee", "message": "🚀 Nuevo proyecto activo"})))
    db.add(WorkflowStep(workflow_id=wf2.id, order=1, step_type=StepType.webhook, name="Notificar Slack",
                        config=json.dumps({"url": "https://hooks.slack.com/services/DEMO", "event": "project.activated"})))

    # ── Sample Invoice ─────────────────────────────────────────────────────────
    project = db.query(Project).filter(Project.status == "active").first()
    if project:
        inv = Invoice(
            number="INV-2025-0001",
            project_id=project.id,
            client_name=project.client_name or "Cliente Demo SA",
            client_vat="B-12345678",
            client_email="facturacion@cliente.com",
            issue_date=date.today() - timedelta(days=30),
            due_date=date.today() - timedelta(days=0),
            tax_rate=settings.DEFAULT_TAX_RATE,
            subtotal=12400.0,
            tax_amount=2604.0,
            total=15004.0,
            currency=settings.DEFAULT_CURRENCY,
            period_from=date.today() - timedelta(days=60),
            period_to=date.today() - timedelta(days=31),
            status=InvoiceStatus.sent,
            notes="Factura correspondiente a los servicios de consultoría del mes anterior.",
            created_by=admin.id if admin else None,
        )
        db.add(inv); db.flush()
        db.add(InvoiceLine(invoice_id=inv.id, order=0, description="Consultor Senior (80h × 95€/h)", quantity=80, unit="h", unit_price=95, amount=7600, source_type="timesheet"))
        db.add(InvoiceLine(invoice_id=inv.id, order=1, description="Project Manager (40h × 120€/h)", quantity=40, unit="h", unit_price=120, amount=4800, source_type="timesheet"))
        db.add(InvoiceLine(invoice_id=inv.id, order=2, description="Gastos de viaje", quantity=1, unit="servicio", unit_price=0, amount=0, source_type="expense"))

        # 2nd invoice paid
        inv2 = Invoice(
            number="INV-2025-0002",
            project_id=project.id,
            client_name=project.client_name or "Cliente Demo SA",
            client_vat="B-12345678",
            issue_date=date.today() - timedelta(days=60),
            due_date=date.today() - timedelta(days=30),
            paid_date=date.today() - timedelta(days=25),
            tax_rate=settings.DEFAULT_TAX_RATE, subtotal=9500.0, tax_amount=1995.0, total=11495.0, currency=settings.DEFAULT_CURRENCY,
            status=InvoiceStatus.paid, created_by=admin.id if admin else None,
        )
        db.add(inv2); db.flush()
        db.add(InvoiceLine(invoice_id=inv2.id, order=0, description="Consultor Senior (100h × 95€/h)", quantity=100, unit="h", unit_price=95, amount=9500, source_type="timesheet"))

    # ── Saved Reports ──────────────────────────────────────────────────────────
    db.add(ReportDefinition(
        name="Rentabilidad por proyecto (mes actual)", description="Margen y coste de proyectos activos",
        category="financial", icon="💰", is_public=True, data_source="projects",
        chart_type="bar_grouped", created_by=admin.id if admin else None,
    ))
    db.add(ReportDefinition(
        name="Utilización equipo (últimas 4 semanas)", description="Horas facturables vs no facturables",
        category="utilization", icon="👥", is_public=True, data_source="imputations",
        chart_type="bar_stacked", created_by=admin.id if admin else None,
    ))

    db.commit()
    db.close()
    print("  ✓ v12 seed completado (plantillas, workflows, facturas, informes)")
