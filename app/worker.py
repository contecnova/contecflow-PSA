from celery import Celery
from celery.schedules import crontab
from app.core.config import settings

celery_app = Celery(
    "clarive",
    broker=settings.REDIS_URL,
    backend=settings.REDIS_URL,
    include=["app.tasks"],
)

celery_app.conf.beat_schedule = {
    # Run alert engine every day at 8am
    "run-alert-engine-daily": {
        "task": "app.worker.run_alert_engine",
        "schedule": crontab(hour=8, minute=0),
    },
    # Weekly load report every Monday at 9am
    "weekly-load-report": {
        "task": "app.worker.send_weekly_report",
        "schedule": crontab(hour=9, minute=0, day_of_week=1),
    },
    # Check missing imputations every weekday at 18:00
    "check-missing-imputations": {
        "task": "app.worker.check_missing_imputations",
        "schedule": crontab(hour=18, minute=0, day_of_week="1-5"),
    },
    # Recurring retainer invoices — runs daily at 07:00, checks retainer_day
    "generate-retainer-invoices": {
        "task": "app.worker.generate_retainer_invoices",
        "schedule": crontab(hour=7, minute=0),
    },
    # Scheduled reports — check every hour
    "run-scheduled-reports": {
        "task": "app.worker.run_scheduled_reports",
        "schedule": crontab(minute=0),  # every hour at :00
    },
    # Key material rotation
    "run-key-rotation": {
        "task": "app.worker.run_scheduled_rotation",
        "schedule": crontab(hour=settings.KEY_ROTATION_RUN_HOUR_UTC, minute=17),
    },
    # Jira bidirectional sync — pull updated issues every 30 minutes
    "jira-periodic-sync": {
        "task": "app.worker.jira_periodic_sync",
        "schedule": crontab(minute="*/30"),
    },
}

celery_app.conf.timezone = settings.DEFAULT_TIMEZONE


@celery_app.task(name="app.worker.run_alert_engine")
def run_alert_engine():
    from app.db.session import SessionLocal
    from app.api.v1.endpoints.alerts import AlertEngine
    db = SessionLocal()
    try:
        engine = AlertEngine(db)
        count = engine.run_all()
        return {"alerts_generated": count}
    finally:
        db.close()


@celery_app.task(name="app.worker.check_missing_imputations")
def check_missing_imputations():
    """Reminder to employees who haven't logged their expected hours today."""
    from app.db.session import SessionLocal
    from app.models.user import User, UserRole, UserStatus
    from app.models.imputation import Imputation
    from sqlalchemy import func
    from datetime import date

    db = SessionLocal()
    today = date.today()
    if today.weekday() >= 5:  # Skip weekends
        return

    try:
        employees = db.query(User).filter(
            User.is_active.is_(True),
            User.status == UserStatus.active,
            User.role == UserRole.employee,
        ).all()

        missing = []
        for emp in employees:
            # Daily capacity = weekly_capacity / 5 working days
            daily_capacity = (emp.weekly_capacity_hours or 40.0) / 5
            hours_today = db.query(func.sum(Imputation.hours)).filter(
                Imputation.user_id == emp.id,
                Imputation.date == today,
            ).scalar() or 0.0
            if hours_today < daily_capacity:
                missing.append(emp.email)

        return {"missing_today": len(missing), "users": missing}
    finally:
        db.close()


@celery_app.task(name="app.worker.send_weekly_report")
def send_weekly_report():
    """Send weekly load summary to managers."""
    from app.db.session import SessionLocal
    from app.models.user import User, UserRole
    db = SessionLocal()
    try:
        admins = db.query(User).filter(
            User.role.in_([UserRole.admin, UserRole.hr]),
            User.is_active == True,
        ).all()
        # Here you would generate and send the report
        return {"report_sent_to": [u.email for u in admins]}
    finally:
        db.close()


@celery_app.task(name="app.worker.generate_retainer_invoices")
def generate_retainer_invoices():
    """
    Auto-generate monthly invoices for recurring_retainer projects.
    Runs daily; only creates an invoice if today matches project.retainer_day
    and no invoice has been created this month yet.
    """
    import uuid
    from datetime import date

    from app.db.session import SessionLocal
    from app.models.project import Project
    from app.models.billing_reports import Invoice, InvoiceStatus

    db = SessionLocal()
    today = date.today()
    generated = []
    try:
        retainer_projects = db.query(Project).filter(
            Project.billing_type == "recurring_retainer",
            Project.retainer_amount != None,
            Project.retainer_day != None,
            Project.is_billable == True,
        ).all()

        for proj in retainer_projects:
            if proj.retainer_day != today.day:
                continue
            # Check no invoice this month already (avoid duplicates)
            try:
                existing = db.query(Invoice).filter(
                    Invoice.project_id == proj.id,
                    Invoice.period_from >= date(today.year, today.month, 1),
                ).first()
                if existing:
                    continue

                # Generate invoice number via the locked numbering service
                from app.services.numbering import next_numbered_code
                inv_number = next_numbered_code(
                    db,
                    "invoice",
                    prefix="INV",
                    padding=4,
                    include_year=True,
                    reset_yearly=True,
                    year_separator="-",
                )

                inv = Invoice(
                    id=str(uuid.uuid4()),
                    number=inv_number,
                    project_id=proj.id,
                    client_id=proj.client_id,
                    total=proj.retainer_amount,
                    currency=proj.currency or "EUR",
                    issue_date=today,
                    period_from=date(today.year, today.month, 1),
                    period_to=today,
                    status=InvoiceStatus.draft,
                    notes=f"Retainer mensual automático — {today.strftime('%B %Y')}",
                )
                db.add(inv)
                generated.append(proj.code)
            except Exception as inv_err:
                import logging
                logging.getLogger(__name__).error(f"Retainer invoice error for {proj.code}: {inv_err}")

        db.commit()
        return {"generated": generated, "count": len(generated)}
    finally:
        db.close()


@celery_app.task(name="app.worker.run_scheduled_reports")
def run_scheduled_reports():
    """Execute due scheduled reports. Called every hour."""
    from app.services.scheduled_reports import run_due_reports
    run_due_reports()
    return {"ok": True}


@celery_app.task(name="app.worker.run_scheduled_rotation")
def run_scheduled_rotation():
    """Execute key material rotation checks on schedule."""
    from app.services.key_management import run_scheduled_rotation as _run
    _run()
    return {"ok": True}


@celery_app.task(
    name="app.worker.run_agent_task",
    bind=True,
    max_retries=0,
    time_limit=300,
    soft_time_limit=280,
)
def run_agent_task(
    self,
    execution_id: str,
    instruction: str,
    user_id: str,
    auto_approve: bool = False,
):
    """
    Run the NexusAgent agentic loop in a Celery worker.
    Writes results back to AIAgentExecution.  Called by run_agent() via .delay().
    """
    import json
    import time
    from datetime import datetime, timezone

    from app.db.session import SessionLocal
    from app.models.ai_chat import AIAgentExecution, AIAgentStep
    from app.models.user import User
    from app.core.config import settings
    from app.api.v1.endpoints.ai_chat import (
        _execute_tool, AGENT_TOOLS,
        _build_agent_system_prompt, _log_action,
    )
    from app.services.ai_client import (
        call_claude as _call_claude,
        extract_text as _extract_text,
        get_api_key as _api_key,
    )

    db = SessionLocal()
    execution = None
    step_num = 0
    result_summary = ""

    try:
        execution = db.query(AIAgentExecution).filter(
            AIAgentExecution.id == execution_id
        ).first()
        if not execution:
            return {"error": "execution not found"}

        current_user = db.query(User).filter(User.id == user_id).first()
        if not current_user:
            execution.status = "failed"
            execution.error = "User not found"
            db.commit()
            return {"error": "user not found"}

        execution.status = "running"
        db.commit()

        t0 = time.time()
        SYSTEM = _build_agent_system_prompt(db, current_user)

        from app.api.v1.endpoints.ai_providers import get_default_provider as _gdp
        from app.api.v1.endpoints.ai_providers import call_ai
        active_prov = _gdp(db)
        has_anthropic_tools = bool(
            _api_key() or (
                active_prov and active_prov.provider == "anthropic" and active_prov.api_key
            )
        )

        if not has_anthropic_tools:
            try:
                result_summary = call_ai(
                    db,
                    messages=[{"role": "user", "content": instruction}],
                    system=SYSTEM + "\n\nNota: ejecuta un análisis y plan de acción sin usar herramientas reales.",
                    module="nexusagent", user_id=user_id, max_tokens=800,
                )
            except Exception:
                result_summary = (
                    f"⚠ Sin proveedor IA configurado. Instrucción recibida: *{instruction}*\n\n"
                    f"Configura un proveedor en IA & Conectores para ejecutar instrucciones reales."
                )
            execution.status = "done"
            execution.result = result_summary
            execution.completed_at = datetime.now(timezone.utc)
            _log_action(db, current_user.id, "nexusagent", "execute",
                        instruction[:200], result_summary[:200], status="success")
            db.commit()
            return {"ok": True}

        agent_api_key = (
            active_prov.api_key
            if (active_prov and active_prov.provider == "anthropic" and active_prov.api_key)
            else _api_key()
        )
        agent_model = (
            active_prov.default_model
            if (active_prov and active_prov.provider == "anthropic" and active_prov.default_model)
            else settings.NEXUS_AI_MODEL
        )

        messages = [{"role": "user", "content": instruction}]
        max_steps = 20

        while step_num < max_steps:
            resp = _call_claude(
                messages, system=SYSTEM, tools=AGENT_TOOLS,
                model=agent_model, max_tokens=4096, api_key=agent_api_key,
            )
            stop_reason = resp.get("stop_reason")
            content = resp.get("content", [])
            messages.append({"role": "assistant", "content": content})

            if stop_reason == "end_turn":
                result_summary = _extract_text(resp)
                break

            if stop_reason == "tool_use":
                tool_results_content = []
                for block in content:
                    if block.get("type") != "tool_use":
                        continue
                    tool_name = block["name"]
                    tool_input = block.get("input", {})
                    tool_use_id = block["id"]
                    step_num += 1

                    tool_result = _execute_tool(tool_name, tool_input, db, current_user)

                    step = AIAgentStep(
                        execution_id=execution.id,
                        step_number=step_num,
                        tool_name=tool_name,
                        tool_input=json.dumps(tool_input),
                        tool_output=json.dumps(tool_result),
                        status="done" if "error" not in tool_result else "failed",
                    )
                    db.add(step)
                    db.flush()
                    tool_results_content.append({
                        "type": "tool_result",
                        "tool_use_id": tool_use_id,
                        "content": json.dumps(tool_result),
                    })
                messages.append({"role": "user", "content": tool_results_content})
            else:
                result_summary = _extract_text(resp)
                break

        if not result_summary:
            result_summary = f"Agente completó {step_num} pasos."

        latency = int((time.time() - t0) * 1000)
        execution.status = "done"
        execution.result = result_summary
        execution.steps_count = step_num
        execution.completed_at = datetime.now(timezone.utc)
        _log_action(db, current_user.id, "nexusagent", "execute",
                    instruction[:200], result_summary[:200],
                    tokens=0, latency=latency, status="success")
        db.commit()
        return {"ok": True, "steps": step_num}

    except Exception as exc:
        if execution:
            execution.status = "failed"
            execution.error = str(exc)[:500]
            execution.completed_at = datetime.now(timezone.utc)
            try:
                db.commit()
            except Exception:
                db.rollback()
        raise
    finally:
        db.close()


@celery_app.task(name="app.worker.jira_periodic_sync")
def jira_periodic_sync():
    """
    Periodically pull updated Jira issues into local tasks.

    Runs every 30 minutes (configured in beat_schedule).  For each integration
    setting that has Jira configured, fetches issues updated in the last hour so
    the window overlaps between runs and avoids gaps.
    """
    import logging
    import datetime
    import httpx

    from app.db.session import SessionLocal
    from app.models.settings import AppSetting
    from app.models.task import Task, TaskStatus, TaskPriority
    import uuid

    log = logging.getLogger(__name__)
    db = SessionLocal()
    synced = 0
    errors = 0

    def _get(key):
        # Worker has no request context; read only global (org-independent) settings.
        row = db.query(AppSetting).filter(
            AppSetting.key == key, AppSetting.organization_id.is_(None)
        ).first()
        return (row.value or "").strip() if row else ""

    def _jira_headers(email: str, token: str) -> dict:
        import base64
        creds = base64.b64encode(f"{email}:{token}".encode()).decode()
        return {"Authorization": f"Basic {creds}", "Content-Type": "application/json"}

    PRIORITY_MAP = {
        "Highest": TaskPriority.critical,
        "High": TaskPriority.high,
        "Medium": TaskPriority.medium,
        "Low": TaskPriority.low,
        "Lowest": TaskPriority.low,
    }
    STATUS_MAP = {
        "To Do": TaskStatus.todo,
        "In Progress": TaskStatus.in_progress,
        "Done": TaskStatus.done,
        "In Review": TaskStatus.in_review,
        "Blocked": TaskStatus.blocked,
    }

    try:
        jira_url   = _get("jira_url").rstrip("/")
        jira_email = _get("jira_email")
        jira_token = _get("jira_api_token")
        project_key = _get("jira_project_key")

        if not all([jira_url, jira_email, jira_token, project_key]):
            return {"skipped": "Jira not configured or incomplete configuration"}

        # Fetch issues updated in the last 65 minutes (overlap buffer)
        cutoff = (datetime.datetime.utcnow() - datetime.timedelta(minutes=65)).strftime("%Y-%m-%d %H:%M")
        jql = f"project = {project_key} AND updated >= '{cutoff}' ORDER BY updated DESC"

        resp = httpx.post(
            f"{jira_url}/rest/api/3/issue/search",
            headers=_jira_headers(jira_email, jira_token),
            json={"jql": jql, "maxResults": 100,
                  "fields": ["summary", "status", "priority", "description",
                              "duedate", "assignee", "issuetype", "labels"]},
            timeout=25,
        )
        resp.raise_for_status()
        issues = resp.json().get("issues", [])

        for issue in issues:
            try:
                key = issue["key"]
                fields = issue.get("fields", {})
                title = fields.get("summary", key)
                status_name = (fields.get("status") or {}).get("name", "To Do")
                priority_name = (fields.get("priority") or {}).get("name", "Medium")
                due_raw = fields.get("duedate")
                due_date = datetime.date.fromisoformat(due_raw) if due_raw else None

                task_status = STATUS_MAP.get(status_name, TaskStatus.todo)
                task_priority = PRIORITY_MAP.get(priority_name, TaskPriority.medium)

                existing = db.query(Task).filter(Task.jira_issue_key == key).first()
                if existing:
                    existing.title = title
                    existing.status = task_status
                    existing.priority = task_priority
                    if due_date:
                        existing.due_date = due_date
                    synced += 1
                else:
                    new_task = Task(
                        id=str(uuid.uuid4()),
                        title=title,
                        status=task_status,
                        priority=task_priority,
                        due_date=due_date,
                        jira_issue_key=key,
                    )
                    db.add(new_task)
                    synced += 1
            except Exception as task_err:
                log.warning(f"Jira sync: skipped issue {issue.get('key', '?')}: {task_err}")
                errors += 1

        db.commit()
        log.info(f"Jira periodic sync: {synced} issues synced, {errors} errors")
        return {"synced": synced, "errors": errors}

    except Exception as exc:
        log.error(f"Jira periodic sync failed: {exc}")
        db.rollback()
        raise
    finally:
        db.close()
