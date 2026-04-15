import ast, re as _re

with open("app/api/v1/endpoints/cab.py", encoding="utf-8") as f:
    src = f.read()

replacements = 0

# 1. Add import after "router = APIRouter()\n\n\n# ═══"
old = "router = APIRouter()\n\n\n# \u2550\u2550\u2550"
new = "router = APIRouter()\nimport app.services.cab_service as _svc\n\n\n# \u2550\u2550\u2550"
if old in src:
    src = src.replace(old, new, 1); replacements += 1; print("Added _svc import")
else:
    print("WARNING: router pattern not found, trying alternate")
    # try without triple ═
    old2 = "router = APIRouter()\n"
    idx = src.find(old2)
    if idx >= 0:
        src = src[:idx] + "router = APIRouter()\nimport app.services.cab_service as _svc\n" + src[idx+len(old2):]
        replacements += 1; print("Added _svc import (alternate)")

# 2. _trigger_out
old = '''def _trigger_out(t: WebhookTrigger) -> dict:
    return {
        "id": t.id, "name": t.name, "slug": t.slug,
        "workflow_id": t.workflow_id,
        "is_active": t.is_active,
        "fire_count": t.fire_count or 0,
        "last_fired_at": str(t.last_fired_at)[:16] if t.last_fired_at else None,
        "endpoint": f"/api/v1/webhooks/fire/{t.slug}",
    }'''
new = '''def _trigger_out(t: WebhookTrigger) -> dict:
    return _svc.trigger_out(t)'''
if old in src:
    src = src.replace(old, new, 1); replacements += 1; print("Replaced _trigger_out")
else:
    print("WARNING: _trigger_out not found")

# 3. _execute_workflow_from_webhook
old = '''def _execute_workflow_from_webhook(workflow_id: str, context: dict):
    """Background task: enqueue workflow triggered by incoming webhook."""
    from app.models.bookings import WorkflowQueueItem
    from app.db.session import SessionLocal
    bg_db = SessionLocal()
    try:
        item = WorkflowQueueItem(
            workflow_id=workflow_id,
            trigger_data=json.dumps(context),
            execute_at=datetime.now(timezone.utc),
            status="pending",
        )
        bg_db.add(item); bg_db.commit()
    except Exception as e:
        bg_db.rollback()
        logger.error(f"Failed to create webhook trigger: {e}", exc_info=True)
    finally:
        bg_db.close()'''
new = '''def _execute_workflow_from_webhook(workflow_id: str, context: dict):
    return _svc.execute_workflow_from_webhook(workflow_id, context)'''
if old in src:
    src = src.replace(old, new, 1); replacements += 1; print("Replaced _execute_workflow_from_webhook")
else:
    print("WARNING: _execute_workflow_from_webhook not found")

# 4. SYSTEM_EMAIL_TEMPLATES (large list — use regex)
match = _re.search(r'SYSTEM_EMAIL_TEMPLATES = \[.*?\]\n\n\n@router', src, _re.DOTALL)
if match:
    src = src[:match.start()] + 'SYSTEM_EMAIL_TEMPLATES = _svc.SYSTEM_EMAIL_TEMPLATES\n\n\n@router' + src[match.end():]
    replacements += 1; print("Replaced SYSTEM_EMAIL_TEMPLATES")
else:
    print("WARNING: SYSTEM_EMAIL_TEMPLATES not found")

# 5. _render_template
old = '''def _render_template(template_str: str, variables: dict) -> str:
    """Simple {{variable}} substitution \u2014 no Jinja2 required."""
    for key, value in (variables or {}).items():
        template_str = template_str.replace(f"{{{{{key}}}}}", str(value))
    return template_str'''
new = '''def _render_template(template_str: str, variables: dict) -> str:
    return _svc.render_template(template_str, variables)'''
if old in src:
    src = src.replace(old, new, 1); replacements += 1; print("Replaced _render_template")
else:
    print("WARNING: _render_template not found")

# 6. _send_email_smtp (use regex — multi-line body)
match2 = _re.search(
    r'def _send_email_smtp\(to: list, subject: str, body_html: str, cc: list = None\) -> bool:.*?return True  # Return True so the log shows .sent.\n',
    src, _re.DOTALL)
if match2:
    src = (src[:match2.start()]
           + 'def _send_email_smtp(to: list, subject: str, body_html: str, cc: list = None) -> bool:\n'
           + '    return _svc.send_email_smtp(to, subject, body_html, cc)\n'
           + src[match2.end():])
    replacements += 1; print("Replaced _send_email_smtp")
else:
    print("WARNING: _send_email_smtp not found")

# 7. AVAILABLE_WIDGETS
match3 = _re.search(r'AVAILABLE_WIDGETS = \[.*?\]\n\n\n@router', src, _re.DOTALL)
if match3:
    src = src[:match3.start()] + 'AVAILABLE_WIDGETS = _svc.AVAILABLE_WIDGETS\n\n\n@router' + src[match3.end():]
    replacements += 1; print("Replaced AVAILABLE_WIDGETS")
else:
    print("WARNING: AVAILABLE_WIDGETS not found")

# 8. _default_widget_layout
match4 = _re.search(r'def _default_widget_layout\(role: str\) -> list:.*?}\n        \]\n\n\n@router', src, _re.DOTALL)
if match4:
    src = (src[:match4.start()]
           + 'def _default_widget_layout(role: str) -> list:\n'
           + '    return _svc.default_widget_layout(role)\n\n\n@router'
           + src[match4.end():])
    replacements += 1; print("Replaced _default_widget_layout")
else:
    print("WARNING: _default_widget_layout not found")

# 9. _compute_risk_score
match5 = _re.search(r'def _compute_risk_score\(db: Session, project: Project\) -> dict:.*?return score\n\n\n', src, _re.DOTALL)
if match5:
    src = (src[:match5.start()]
           + 'def _compute_risk_score(db, project):\n'
           + '    return _svc.compute_risk_score(db, project)\n\n\n'
           + src[match5.end():])
    replacements += 1; print("Replaced _compute_risk_score")
else:
    print("WARNING: _compute_risk_score not found")

# 10. _sync_git_commits
match6 = _re.search(r'def _sync_git_commits\(db, config, payload\):.*?return synced, \[\]\n\n\ndef _sync_calendar', src, _re.DOTALL)
if match6:
    src = (src[:match6.start()]
           + 'def _sync_git_commits(db, config, payload):\n'
           + '    return _svc.sync_git_commits(db, config, payload)\n\n\ndef _sync_calendar'
           + src[match6.end():])
    replacements += 1; print("Replaced _sync_git_commits")
else:
    print("WARNING: _sync_git_commits not found")

# 11. _sync_calendar
match7 = _re.search(r'def _sync_calendar\(db, config, payload\):.*?return synced, \[\]\n\n\ndef _sync_accounting', src, _re.DOTALL)
if match7:
    src = (src[:match7.start()]
           + 'def _sync_calendar(db, config, payload):\n'
           + '    return _svc.sync_calendar(db, config, payload)\n\n\ndef _sync_accounting'
           + src[match7.end():])
    replacements += 1; print("Replaced _sync_calendar")
else:
    print("WARNING: _sync_calendar not found")

# 12. _sync_accounting
match8 = _re.search(r'def _sync_accounting\(db, config, payload\):.*?return synced, \[\]\n\n\ndef _sync_jira', src, _re.DOTALL)
if match8:
    src = (src[:match8.start()]
           + 'def _sync_accounting(db, config, payload):\n'
           + '    return _svc.sync_accounting(db, config, payload)\n\n\ndef _sync_jira'
           + src[match8.end():])
    replacements += 1; print("Replaced _sync_accounting")
else:
    print("WARNING: _sync_accounting not found")

# 13. _sync_jira (ends with "return synced, errors[:5]")
match9 = _re.search(r'def _sync_jira\(db, config, payload\):.*?return synced, errors\[:5\]\n', src, _re.DOTALL)
if match9:
    src = (src[:match9.start()]
           + 'def _sync_jira(db, config, payload):\n'
           + '    return _svc.sync_jira(db, config, payload)\n'
           + src[match9.end():])
    replacements += 1; print("Replaced _sync_jira")
else:
    print("WARNING: _sync_jira not found")

with open("app/api/v1/endpoints/cab.py", "w", encoding="utf-8") as f:
    f.write(src)

print(f"\nTotal replacements: {replacements}/13")

try:
    ast.parse(src)
    print("Syntax OK")
except SyntaxError as e:
    print(f"SYNTAX ERROR: {e}")
