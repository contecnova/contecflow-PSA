"""Seed enterprise: webhooks, SSO, subcontratistas, previsión de ingresos, permisos."""
from app.core.config import settings

def seed_enterprise():
    """Seed enterprise demo data: webhooks, SSO config, subcontractors, revenue forecast."""
    from app.db.session import SessionLocal
    import json
    import secrets
    from datetime import date, timedelta
    from app.models.user import User
    from app.models.project import Project
    from app.models.enterprise import (
        Webhook, SSOConfig, SSOProvider,
        Subcontractor, SubcontractorRate, SubcontractorAssignment,
        RevenueForecast, ProjectPermission, ProjectPermissionLevel,
    )

    from app.db.base import Base as _Base
    from app.db.session import engine as _eng
    _Base.metadata.create_all(bind=_eng)
    from app.db.seed_parts._sesion import sesion_de_siembra
    db = sesion_de_siembra()
    print("  Seeding enterprise modules...")

    admin = db.query(User).filter(User.username == "admin").first()
    ana   = db.query(User).filter(User.username == "ana.torres").first()
    luis  = db.query(User).filter(User.username == "luis.vega").first()

    # Only seed if empty
    if db.query(Webhook).count() > 0:
        db.close()
        return

    # ── Webhooks demo ──────────────────────────────────────────────────────────
    hooks = [
        Webhook(
            name="Slack — Alertas de proyecto",
            url="https://hooks.slack.com/services/DEMO/WEBHOOK/contecflow",
            events=json.dumps(["project.created","project.closed","risk.created","expense.approved"]),
            is_active=True,
            total_deliveries=47, failed_deliveries=2,
            created_by=admin.id if admin else None,
        ),
        Webhook(
            name="Microsoft Teams — Notificaciones SD",
            url="https://outlook.office.com/webhook/demo/contecflow",
            events=json.dumps(["ticket.created","ticket.resolved"]),
            is_active=True,
            total_deliveries=128, failed_deliveries=0,
            created_by=admin.id if admin else None,
        ),
        Webhook(
            name="ERP interno — Sincronización horas",
            url="https://erp.empresa.com/api/contecflow/timesheets",
            # Secreto HMAC generado en cada seed: nunca un valor fijo en el repo, para
            # que activar este webhook de demo no implique una clave de firma pública.
            secret=secrets.token_urlsafe(32),
            events=json.dumps(["timesheet.approved","expense.approved"]),
            is_active=False,
            total_deliveries=12, failed_deliveries=5,
            created_by=admin.id if admin else None,
        ),
    ]
    db.add_all(hooks)
    db.flush()

    # ── SSO demo config (SAML, inactive — just example) ───────────────────────
    sso = SSOConfig(
        provider=SSOProvider.saml,
        is_active=False,
        is_default=False,
        saml_entity_id="https://sso.empresa.com/saml/metadata",
        saml_sso_url="https://sso.empresa.com/saml/sso",
        saml_slo_url="https://sso.empresa.com/saml/slo",
        saml_certificate="DEMO-CERTIFICATE-PLACEHOLDER",
        saml_attribute_email="email",
        saml_attribute_name="displayName",
        saml_attribute_role="contecflowRole",
        role_mapping=json.dumps({"Contecflow-Admin": "admin", "Contecflow-PM": "pm", "Contecflow-Dev": "employee"}),
        auto_create_users=True,
        default_role="employee",
        allowed_domains="empresa.com,filial.com",
        created_by=admin.id if admin else None,
    )
    db.add(sso)
    db.flush()

    # ── Subcontractors ─────────────────────────────────────────────────────────
    sub1 = Subcontractor(
        code="SUB-0001", name="Carlos Mendoza",
        company="Freelance Dev", email="carlos@freelance.com",
        country="España", currency=settings.DEFAULT_CURRENCY, is_active=True,
        notes="Especialista React/Node. Disponible a tiempo parcial.",
    )
    sub2 = Subcontractor(
        code="SUB-0002", name="TechPartners SL",
        company="TechPartners SL", email="proyectos@techpartners.es",
        country="España", vat_number="B-12345678", currency=settings.DEFAULT_CURRENCY, is_active=True,
        notes="Empresa de infraestructura DevOps y cloud.",
    )
    sub3 = Subcontractor(
        code="SUB-0003", name="DataAnalytics GmbH",
        company="DataAnalytics GmbH", email="contact@dataanalytics.de",
        country="Alemania", vat_number="DE-987654321", currency=settings.DEFAULT_CURRENCY, is_active=True,
        notes="Consultora de BI y analítica de datos.",
    )
    db.add_all([sub1, sub2, sub3])
    db.flush()

    # Rates
    r1 = SubcontractorRate(subcontractor_id=sub1.id, description="Desarrollo Frontend Senior", cost_rate=65.0, sell_rate=90.0, currency=settings.DEFAULT_CURRENCY)
    r2 = SubcontractorRate(subcontractor_id=sub2.id, description="DevOps / Cloud Engineer", cost_rate=80.0, sell_rate=110.0, currency=settings.DEFAULT_CURRENCY)
    r2b = SubcontractorRate(subcontractor_id=sub2.id, description="Arquitecto de soluciones", cost_rate=120.0, sell_rate=160.0, currency=settings.DEFAULT_CURRENCY)
    r3 = SubcontractorRate(subcontractor_id=sub3.id, description="Data Analyst", cost_rate=70.0, sell_rate=95.0, currency=settings.DEFAULT_CURRENCY)
    db.add_all([r1, r2, r2b, r3])
    db.flush()

    # Assign to projects
    project = db.query(Project).filter(Project.status == "active").first()
    if project:
        db.add(SubcontractorAssignment(
            subcontractor_id=sub1.id, project_id=project.id, rate_id=r1.id,
            po_number="PO-2025-001", po_amount=15000.0, hours_contracted=200.0, hours_logged=87.5,
            start_date=date.today() - timedelta(days=45),
            end_date=date.today() + timedelta(days=45),
        ))
        db.add(SubcontractorAssignment(
            subcontractor_id=sub2.id, project_id=project.id, rate_id=r2.id,
            po_number="PO-2025-002", po_amount=24000.0, hours_contracted=300.0, hours_logged=142.0,
            start_date=date.today() - timedelta(days=60),
            end_date=date.today() + timedelta(days=60),
        ))
        db.flush()

        # ── Revenue Forecast ───────────────────────────────────────────────────
        today = date.today()
        year = today.year
        for month in range(1, 13):
            is_past = month < today.month
            is_current = month == today.month

            rev_plan = 45000 + (month % 3) * 8000
            rev_actual = rev_plan * (0.92 + (month % 4) * 0.03) if is_past else (rev_plan * 0.45 if is_current else 0)
            rev_forecast = rev_plan if not is_past else rev_actual
            cost_plan = rev_plan * 0.65
            cost_actual = cost_plan * (0.88 + (month % 3) * 0.04) if is_past else (cost_plan * 0.5 if is_current else 0)

            margin = round((rev_forecast - (cost_actual or cost_plan)) / rev_forecast * 100, 1) if rev_forecast > 0 else None

            db.add(RevenueForecast(
                project_id=project.id, year=year, month=month,
                revenue_planned=round(rev_plan, 2),
                revenue_actual=round(rev_actual, 2),
                revenue_forecast=round(rev_forecast, 2),
                cost_planned=round(cost_plan, 2),
                cost_actual=round(cost_actual, 2),
                hours_planned=round(rev_plan / 75, 1),
                hours_actual=round(rev_actual / 75, 1) if rev_actual > 0 else 0,
                margin_pct=margin,
            ))
        db.flush()

    # ── Project permissions demo ───────────────────────────────────────────────
    if project and luis and ana:
        db.add(ProjectPermission(
            project_id=project.id, user_id=luis.id,
            level=ProjectPermissionLevel.member,
            can_see_financials=False, can_see_rates=False, can_export=True,
            granted_by=ana.id,
            note="Acceso como desarrollador asignado al proyecto",
        ))
        db.flush()

    # ── Welcome notifications ──────────────────────────────────────────────────
    if admin:
        from app.services.notifications import notify_user
        notify_user(db, admin.id, "system",
                   "🎉 Contecflow v11 Enterprise activo",
                   "Audit log, SSO, webhooks, permisos granulares y previsión de ingresos ya están disponibles.",
                   action_url="/enterprise")
        if ana:
            notify_user(db, ana.id, "sprint_started",
                       "Sprint 2 en curso",
                       "El sprint activo tiene 4 tareas asignadas. Burndown actualizado.",
                       resource="sprints", action_url="/sprints")
        if luis:
            notify_user(db, luis.id, "expense_rejected",
                       "Gasto rechazado: Tren AVE Valencia",
                       "Falta adjuntar el billete como justificante. Puedes editarlo y volver a enviarlo.",
                       resource="expenses", action_url="/expenses")

    db.commit()
    db.close()
    print("  ✓ Enterprise seed completado")
