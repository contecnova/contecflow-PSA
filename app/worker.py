from celery import Celery
from celery.schedules import crontab
from app.core.config import settings

celery_app = Celery(
    "contecflow",
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
    # Approval timeout escalation — check every hour
    "process-approval-timeouts": {
        "task": "app.worker.process_approval_timeouts",
        "schedule": crontab(minute=0),  # every hour at :00
    },
    # ASC 606 monthly revenue recognition — 1st of every month at 02:00
    "revenue-monthly-recognition": {
        "task": "app.worker.revenue_monthly_recognition",
        "schedule": crontab(day_of_month=1, hour=2, minute=0),
    },
    # ML model retraining — 1st of every month at 03:00 (after revenue recognition)
    "ml-model-retrain": {
        "task": "app.worker.ml_model_retrain",
        "schedule": crontab(day_of_month=1, hour=3, minute=0),
    },
    # OLAP nightly ETL — incremental load PostgreSQL → DuckDB every night at 01:00
    "olap-nightly-etl": {
        "task": "app.worker.olap_nightly_etl",
        "schedule": crontab(hour=1, minute=0),
    },
}

celery_app.conf.timezone = settings.DEFAULT_TIMEZONE

import logging as _logging
_worker_logger = _logging.getLogger(__name__)


@celery_app.task(
    bind=True,
    name="app.worker.deliver_webhook",
    max_retries=3,
)
def deliver_webhook_task(self, webhook_id: int, body: str, event: str):
    """Deliver a single outbound webhook with automatic retry on network errors.

    Retry schedule: 60s → 300s → 1800s (attempt 1 → 2 → 3).
    Each attempt is logged as a WebhookDelivery row regardless of outcome.
    """
    import httpx
    import time
    from datetime import datetime, timezone
    from app.db.session import SessionLocal
    from app.models.enterprise import Webhook, WebhookDelivery
    from app.core.encryption import decrypt_value
    from app.services.webhooks import _sign_payload

    # Explicit retry schedule requested for transient webhook failures.
    retry_schedule = (60, 300, 1800)
    transient_statuses = {408, 425, 429, 500, 502, 503, 504}

    db = SessionLocal()
    try:
        hook = db.query(Webhook).filter(
            Webhook.id == webhook_id,
            Webhook.is_active == True,
        ).first()

        if not hook:
            return {"skipped": True, "reason": "webhook not found or inactive"}

        status_code = None
        response_text = None
        success = False
        error = None
        duration_ms = None
        http_exc = None

        try:
            headers = {
                "Content-Type": "application/json",
                "User-Agent": "Contecflow-Webhooks/1.0",
                "X-Contecflow-Event": event,
            }
            if hook.secret:
                secret = decrypt_value(hook.secret) or hook.secret
                headers["X-Contecflow-Signature"] = _sign_payload(secret, body)

            start = time.time()
            with httpx.Client(timeout=10.0) as client:
                resp = client.post(hook.url, content=body, headers=headers)
            duration_ms = int((time.time() - start) * 1000)
            status_code = resp.status_code
            response_text = resp.text[:500]
            success = 200 <= resp.status_code < 300

        except httpx.HTTPError as exc:
            error = str(exc)[:500]
            http_exc = exc
        except Exception as exc:
            error = str(exc)[:500]

        # Log every attempt — including failed ones — before deciding to retry.
        delivery = WebhookDelivery(
            webhook_id=hook.id,
            event=event,
            payload=body[:10000],
            status_code=status_code,
            response=response_text,
            success=success,
            error=error,
            duration_ms=duration_ms,
        )
        db.add(delivery)
        hook.total_deliveries = (hook.total_deliveries or 0) + 1
        hook.last_triggered_at = datetime.now(timezone.utc)

        if success:
            # Reset circuit-breaker counter on any successful delivery.
            hook.consecutive_failures = 0
        else:
            hook.failed_deliveries = (hook.failed_deliveries or 0) + 1
            hook.consecutive_failures = (hook.consecutive_failures or 0) + 1

            # Circuit breaker — suspend after WEBHOOK_CB_THRESHOLD consecutive failures
            # so a permanently dead endpoint stops receiving attempts automatically.
            cb_threshold = getattr(settings, "WEBHOOK_CB_THRESHOLD", 5)
            if hook.consecutive_failures >= cb_threshold and hook.is_active:
                hook.is_active = False
                hook.suspended_at = datetime.now(timezone.utc)
                _worker_logger.error(
                    "Circuit breaker: webhook %s (%s) suspended after %d consecutive "
                    "failures. Re-enable via the admin panel once the endpoint is fixed.",
                    hook.id, hook.url, hook.consecutive_failures,
                )
                # Emit a system event so admins receive an in-app notification.
                try:
                    from app.core.events import emit_event
                    from app.db.session import SessionLocal as _SL
                    _db2 = _SL()
                    try:
                        emit_event(
                            _db2,
                            "webhook.suspended",
                            {
                                "webhook_id": hook.id,
                                "webhook_name": hook.name,
                                "url": hook.url,
                                "consecutive_failures": hook.consecutive_failures,
                            },
                        )
                    finally:
                        _db2.close()
                except Exception as _ne:
                    _worker_logger.debug("Could not emit webhook.suspended event: %s", _ne)

        db.commit()

        # Retry transient failures with fixed exponential backoff schedule.
        # Only retry if the circuit breaker has not tripped (hook still active after commit).
        should_retry = (
            hook.is_active
            and (
                http_exc is not None
                or (status_code in transient_statuses)
            )
        )
        if should_retry:
            if self.request.retries < len(retry_schedule):
                countdown = retry_schedule[self.request.retries]
                retry_reason = http_exc or RuntimeError(f"HTTP {status_code}")
                _worker_logger.warning(
                    "Webhook %s transient failure (attempt %d/%d), retrying in %ds: %s",
                    webhook_id,
                    self.request.retries + 1,
                    self.max_retries + 1,
                    countdown,
                    retry_reason,
                )
                raise self.retry(exc=retry_reason, countdown=countdown)
            _worker_logger.error(
                "Webhook %s transient failure exhausted retries (attempt %d/%d). Last status=%s error=%s",
                webhook_id,
                self.request.retries + 1,
                self.max_retries + 1,
                status_code,
                error,
            )

        return {"success": success, "status_code": status_code, "suspended": not hook.is_active}

    finally:
        db.close()


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
            # Evitar facturas duplicadas este mes
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

                # Obtener datos del cliente si están disponibles
                client_name = getattr(proj, "client_name", None)
                client_email = getattr(proj, "client_email", None)
                client_address = getattr(proj, "client_address", None)
                # Si el proyecto no tiene estos datos, intentar obtenerlos del cliente
                if not all([client_name, client_email, client_address]) and proj.client_id:
                    from app.models.client import Client
                    client = db.query(Client).filter(Client.id == proj.client_id).first()
                    if client:
                        client_name = client_name or getattr(client, "name", None)
                        client_email = client_email or getattr(client, "email", None)
                        client_address = client_address or getattr(client, "address", None)
                inv = Invoice(
                    id=str(uuid.uuid4()),
                    number=inv_number,
                    project_id=proj.id,
                    client_id=proj.client_id,
                    client_name=client_name,
                    client_email=client_email,
                    client_address=client_address,
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
    time_limit=settings.CELERY_AGENT_TASK_TIME_LIMIT,
    soft_time_limit=settings.CELERY_AGENT_TASK_SOFT_TIME_LIMIT,
)
def run_agent_task(
    self,
    execution_id: str,
    instruction: str,
    user_id: str,
    auto_approve: bool = False,
):
    """
    Run the ContecflowAgent agentic loop in a Celery worker.
    Writes results back to AIAgentExecution.  Called by run_agent() via .delay().
    """
    import json
    import time
    from datetime import datetime, timezone

    from app.db.session import SessionLocal
    from app.models.ai_chat import AIAgentExecution, AIAgentStep
    from app.models.user import User
    from app.core.config import settings
    from app.services.ai_chat_service import (
        execute_tool as _execute_tool,
        AGENT_TOOLS,
        build_agent_system_prompt as _build_agent_system_prompt,
        log_action as _log_action,
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
                    module="contecflowagent", user_id=user_id, max_tokens=800,
                )
            except Exception:
                result_summary = (
                    f"⚠ Sin proveedor IA configurado. Instrucción recibida: *{instruction}*\n\n"
                    f"Configura un proveedor en IA & Conectores para ejecutar instrucciones reales."
                )
            execution.status = "done"
            execution.result = result_summary
            execution.completed_at = datetime.now(timezone.utc)
            _log_action(db, current_user.id, "contecflowagent", "execute",
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
            else settings.CONTECFLOW_AI_MODEL
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
        _log_action(db, current_user.id, "contecflowagent", "execute",
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


@celery_app.task(name="app.worker.process_approval_timeouts")
def process_approval_timeouts():
    """
    Scan all pending ApprovalRequests and fire timeout actions for overdue steps.

    Runs every hour (configured in beat_schedule).  For each step that has
    exceeded its timeout_hours, applies on_timeout: escalate | auto_approve | reject.
    """
    from app.db.session import SessionLocal
    from app.services.approval_engine import process_approval_timeouts as _process

    db = SessionLocal()
    try:
        result = _process(db)
        return result
    finally:
        db.close()


@celery_app.task(name="app.worker.revenue_monthly_recognition")
def revenue_monthly_recognition():
    """
    ASC 606 / IFRS 15 monthly recognition batch.
    Runs on the 1st of each month at 02:00 UTC.
    Processes over_time, consumption, and straight_line contracts for the
    previous calendar month across all organizations.
    Milestone-method contracts are skipped (recognized on milestone completion).
    """
    from datetime import date
    from app.db.session import SessionLocal
    from app.services.revenue_service import run_monthly_recognition

    today = date.today()
    # Recognize the previous month (this task runs on the 1st)
    if today.month == 1:
        year, month = today.year - 1, 12
    else:
        year, month = today.year, today.month - 1

    db = SessionLocal()
    try:
        result = run_monthly_recognition(db, year, month)
        _worker_logger.info("ASC 606 recognition complete: %s", result)
        return result
    finally:
        db.close()


@celery_app.task(name="app.worker.olap_nightly_etl")
def olap_nightly_etl():
    """
    Nightly incremental ETL: PostgreSQL → DuckDB OLAP star schema.
    Runs at 01:00 UTC. Loads last 2 days of imputations + full dim/fact refresh.
    Pass since=date(2023,1,1) in a manual call for a full historical load.
    """
    from app.db.session import SessionLocal
    from app.services.olap.etl import run_full_etl

    db = SessionLocal()
    try:
        result = run_full_etl(db)
        _worker_logger.info("OLAP ETL result: %s", result)
        return result
    finally:
        db.close()


@celery_app.task(name="app.worker.ml_model_retrain")
def ml_model_retrain():
    """
    Retrain overrun prediction ML models for all active organizations.
    Runs on the 1st of each month at 03:00 UTC, after revenue recognition.
    Skips orgs with fewer than MIN_TRAINING_SAMPLES completed projects.
    Requires scikit-learn; skips gracefully if not available.
    """
    from app.db.session import SessionLocal
    from app.services.ml_trainer import train_all_orgs

    db = SessionLocal()
    try:
        results = train_all_orgs(db)
        trained = sum(1 for r in results if r.get("status") == "trained")
        skipped = sum(1 for r in results if r.get("status") == "skipped")
        _worker_logger.info("ML retrain: %d trained, %d skipped", trained, skipped)
        return {"trained": trained, "skipped": skipped, "results": results}
    finally:
        db.close()
