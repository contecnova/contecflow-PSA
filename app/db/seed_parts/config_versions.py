"""Seed v14/v15/v16: email templates, Slack config, presupuesto, AI governance."""
import os

from app.core.config import settings

def seed_v14(db):
    """Seed v14 — email templates, onboarding states for existing users, demo widget layouts."""
    from app.models.cab import EmailTemplate
    import json
    from app.db.base import Base
    from app.db.session import engine as _eng_v14
    Base.metadata.create_all(bind=_eng_v14)

    # ── Email templates (seed only if empty)
    if db.query(EmailTemplate).count() == 0:
        email_templates_path = os.getenv("SEED_EMAIL_TEMPLATES_PATH", "seed_email_templates.json")
        if os.path.exists(email_templates_path):
            with open(email_templates_path, "r") as f:
                templates_data = json.load(f)
            templates = [EmailTemplate(
                name=tpl["name"],
                subject=tpl["subject"],
                body_html=tpl["body_html"],
                category=tpl["category"],
                is_system=tpl.get("is_system", True),
                variables=json.dumps(tpl.get("variables", [])),
            ) for tpl in templates_data]
        else:
            templates = [
                EmailTemplate(
                    name="Tarea vencida",
                    subject="[Contecflow] Tarea vencida: {{task_title}}",
                    body_html="<h2>Tarea vencida</h2><p>La tarea <strong>{{task_title}}</strong> en el proyecto {{project_name}} ha vencido.</p><p>Responsable: {{assignee_name}}</p>",
                    category="automation", is_system=True,
                    variables=json.dumps(["task_title","project_name","assignee_name","due_date"]),
                ),
                EmailTemplate(
                    name="Alerta de presupuesto",
                    subject="[Contecflow] Presupuesto al {{pct_used}}%: {{project_name}}",
                    body_html="<h2>Alerta de presupuesto</h2><p>El proyecto <strong>{{project_name}}</strong> ha consumido el {{pct_used}}% del presupuesto.</p><p>Total: {{budget_total}}€ | Consumido: {{budget_used}}€</p>",
                    category="alert", is_system=True,
                    variables=json.dumps(["project_name","budget_total","budget_used","pct_used"]),
                ),
                EmailTemplate(
                    name="Informe programado",
                    subject="[Contecflow] Informe: {{report_name}}",
                    body_html="<h2>Informe: {{report_name}}</h2><p>Generado el {{generated_at}} para el período {{period}}.</p><p>Accede a Contecflow para ver el informe completo.</p>",
                    category="report", is_system=True,
                    variables=json.dumps(["report_name","generated_at","period"]),
                ),
                EmailTemplate(
                    name="Ticket SLA vencido",
                    subject="[Service Desk] SLA vencido: #{{ticket_number}}",
                    body_html="<h2>SLA incumplido</h2><p>El ticket <strong>#{{ticket_number}} — {{ticket_title}}</strong> ha superado el SLA.</p><p>Asignado a: {{assignee_name}}</p>",
                    category="alert", is_system=True,
                    variables=json.dumps(["ticket_number","ticket_title","assignee_name","sla_due"]),
                ),
            ]
        for t in templates:
            db.add(t)
        db.flush()

    db.commit()
    print("  ✓ seed_v14: email templates")


def seed_v15(db):
    """Seed v15 — default Slack config, sample budget."""
    from app.models.mfa import SlackConfig, Budget, BudgetEntry
    import datetime

    if db.query(SlackConfig).count() == 0:
        db.add(SlackConfig(
            platform="slack",
            workspace_name="Mi empresa",
            default_channel="#contecflow-alerts",
            is_active=False,
            subscriptions='["task_overdue","budget_alert","ticket_sla"]',
        ))
        db.flush()

    year = datetime.date.today().year
    if db.query(Budget).filter(Budget.year == year).count() == 0:
        b = Budget(
            name=f"Presupuesto TI {year}",
            year=year, department="Tecnología",
            total_amount=120000, currency=settings.DEFAULT_CURRENCY,
        )
        db.add(b); db.flush()
        for m in range(1, 13):
            db.add(BudgetEntry(budget_id=b.id, month=m, planned=10000.0))
        db.flush()

    db.commit()
    print("  ✓ seed_v15")


def seed_v16(db):
    """Seed v16 — AI governance config defaults."""
    from app.models.ai_chat import AIGovernanceConfig
    modules = [
        "nexusassist", "nexusagent", "nexusoracle",
        "meeting_assistant", "contract_intelligence", "knowledge_base", "voice",
    ]
    existing = {c.module for c in db.query(AIGovernanceConfig).all()}
    for mod in modules:
        if mod not in existing:
            db.add(AIGovernanceConfig(
                module=mod, is_enabled=True,
                requires_approval_for='[]',
                allowed_roles='["admin","pm","team_lead"]',
            ))
    db.commit()
    print("  ✓ seed_v16: AI governance configs")
