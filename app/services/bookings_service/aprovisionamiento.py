"""Acciones de aprovisionamiento de los flujos: identidad, Terraform y Ansible.

Parte de `app.services.bookings_service` (auditoria 2026-11, #24): se partio por responsabilidad
sin cambiar el codigo. El paquete reexporta todos los nombres.
"""
from __future__ import annotations

import json
import shutil
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from app.core.config import settings

from app.services.bookings_service._comun import logger


ALLOWED_TERRAFORM_COMMANDS = {"plan", "apply", "destroy"}


def _render_step_value(value, context: dict):
    if isinstance(value, str):
        try:
            return value.format_map({k: ("" if v is None else v) for k, v in context.items()})
        except Exception:
            logger.debug("Workflow step value templating failed; keeping raw value=%r", value, exc_info=True)
            return value
    if isinstance(value, list):
        return [_render_step_value(v, context) for v in value]
    if isinstance(value, dict):
        return {k: _render_step_value(v, context) for k, v in value.items()}
    return value


def _provisioning_root() -> "Path":
    """Return the operator-controlled provisioning root, or raise if provisioning
    is disabled / unconfigured (fail-closed)."""
    if not settings.PROVISIONING_ENABLED:
        raise PermissionError("Infrastructure provisioning is disabled (set PROVISIONING_ENABLED=1)")
    root = (settings.PROVISIONING_ROOT_DIR or "").strip()
    if not root:
        raise PermissionError("PROVISIONING_ROOT_DIR is not configured; refusing to run provisioning")
    return Path(root).resolve()


def _safe_provision_path(candidate, *, label: str, required: bool = True) -> "str | None":
    """Resolve *candidate* and guarantee it stays inside PROVISIONING_ROOT_DIR.

    Blocks path-traversal / absolute-path escapes / symlink breakout so a
    tenant-supplied workdir/playbook/var_file/inventory can never make the
    runner execute code outside the vetted module tree. Returns the resolved
    absolute path as a string, or None when *candidate* is empty and not
    required. Raises ValueError on any containment violation.
    """
    if candidate is None or str(candidate).strip() == "":
        if required:
            raise ValueError(f"Provisioning '{label}' is required")
        return None
    root = _provisioning_root()
    resolved = (root / str(candidate)).resolve()
    try:
        resolved.relative_to(root)
    except ValueError:
        raise ValueError(f"Provisioning '{label}' escapes the provisioning root")
    return str(resolved)


def _run_cli(cmd: list[str], cwd: str | None = None, timeout_seconds: int = 1200) -> dict:
    started = datetime.now(timezone.utc)
    proc = subprocess.run(
        cmd,
        cwd=cwd,
        capture_output=True,
        text=True,
        timeout=timeout_seconds,
        check=False,
    )
    finished = datetime.now(timezone.utc)
    return {
        "ok": proc.returncode == 0,
        "exit_code": proc.returncode,
        "stdout": (proc.stdout or "")[-4000:],
        "stderr": (proc.stderr or "")[-4000:],
        "duration_ms": int((finished - started).total_seconds() * 1000),
        "command": cmd,
    }


def _validate_provision_url(url: str) -> None:
    """Validate provisioning URL to prevent SSRF attacks against internal networks."""
    import ipaddress as _ipaddress
    import socket as _socket
    from urllib.parse import urlparse as _urlparse

    parsed = _urlparse(url or "")
    if parsed.scheme.lower() != "https" or not parsed.netloc:
        raise ValueError("Provision URL must be a valid HTTPS URL")

    hostname = (parsed.hostname or "").strip().lower()
    if not hostname:
        raise ValueError("Provision URL must include a hostname")

    if hostname in {"localhost", "localhost.localdomain"} or hostname.endswith(".local"):
        raise ValueError("Provision URL cannot target local hosts")

    try:
        ip_obj = _ipaddress.ip_address(hostname)
    except ValueError:
        ip_obj = None

    if ip_obj is not None and (
        ip_obj.is_private
        or ip_obj.is_loopback
        or ip_obj.is_link_local
        or ip_obj.is_multicast
        or ip_obj.is_reserved
        or ip_obj.is_unspecified
    ):
        raise ValueError("Provision URL targets a disallowed network range")

    try:
        addrinfo = _socket.getaddrinfo(hostname, parsed.port or 443, proto=_socket.IPPROTO_TCP)
    except Exception:
        logger.warning("Fallo resolviendo getaddrinfo para hostname=%s en validación SSRF", hostname, exc_info=True)
        addrinfo = []

    for entry in addrinfo:
        ip_raw = entry[4][0]
        resolved_ip = _ipaddress.ip_address(ip_raw)
        if (
            resolved_ip.is_private
            or resolved_ip.is_loopback
            or resolved_ip.is_link_local
            or resolved_ip.is_multicast
            or resolved_ip.is_reserved
            or resolved_ip.is_unspecified
        ):
            raise ValueError("Provision URL resolves to a disallowed network range")


def _execute_provision_action(config: dict, context: dict) -> dict:
    """Execute real provisioning call against external IdM/IAM APIs.

    Expected config keys:
      - operation: create_ad_user|disable_ad_user|assign_license|revoke_license
      - url: endpoint URL (must be HTTPS and must not target internal networks)
      - method: POST|PATCH|PUT|DELETE (default POST)
      - headers: dict (optional)
      - payload: dict/list/string template rendered from context (optional)
      - timeout_seconds: int (optional, default 15)
    """
    import httpx

    operation = str(config.get("operation") or config.get("type") or "provision").lower()
    url = config.get("url")
    if not url:
        raise ValueError("Provision action requires 'url'")

    # SSRF protection: block requests to internal/private networks
    _validate_provision_url(url)

    method = str(config.get("method") or "POST").upper()
    headers = _render_step_value(config.get("headers") or {}, context)
    payload = _render_step_value(config.get("payload") or {}, context)
    timeout_seconds = int(config.get("timeout_seconds", 15))

    started = datetime.now(timezone.utc)
    with httpx.Client(timeout=timeout_seconds) as client:
        resp = client.request(method, url, headers=headers, json=payload)
    finished = datetime.now(timezone.utc)

    return {
        "operation": operation,
        "ok": 200 <= resp.status_code < 300,
        "status_code": resp.status_code,
        "response": resp.text[:2000],
        "request_url": url,
        "duration_ms": int((finished - started).total_seconds() * 1000),
    }


def _execute_terraform_action(config: dict, context: dict) -> dict:
    """Run Terraform command (init+apply/destroy/plan) for provisioning.

    All filesystem paths are forced inside PROVISIONING_ROOT_DIR (server-side),
    so a tenant-supplied workdir/var_file can never make the runner execute a
    module tree outside the operator-vetted root.
    """
    # Containment first — raises if provisioning is disabled or paths escape root.
    workdir = _safe_provision_path(_render_step_value(config.get("workdir"), context), label="workdir")
    command = str(config.get("command") or "apply").lower()
    allowed_commands = {
        str(c).lower() for c in (config.get("allowed_commands") or sorted(ALLOWED_TERRAFORM_COMMANDS))
    }
    if command not in allowed_commands:
        raise ValueError(f"Terraform command '{command}' is not in allowed_commands")
    if command not in ALLOWED_TERRAFORM_COMMANDS:
        raise ValueError(f"Terraform command '{command}' is not allowed by runtime policy")
    if not shutil.which("terraform"):
        raise RuntimeError("terraform executable not found in PATH")

    auto_approve = bool(config.get("auto_approve", True))
    var_file = _safe_provision_path(
        _render_step_value(config.get("var_file"), context), label="var_file", required=False
    )
    vars_map = _render_step_value(config.get("vars") or {}, context)
    timeout_seconds = int(config.get("timeout_seconds", 1800))

    init_res = _run_cli(["terraform", "init", "-input=false"], cwd=workdir, timeout_seconds=timeout_seconds)
    if not init_res["ok"]:
        return {"ok": False, "phase": "init", **init_res}

    cmd = ["terraform", command, "-input=false"]
    if command in ("apply", "destroy") and auto_approve:
        cmd.append("-auto-approve")
    if var_file:
        cmd.extend(["-var-file", str(var_file)])
    for k, v in vars_map.items():
        cmd.extend(["-var", f"{k}={v}"])

    run_res = _run_cli(cmd, cwd=workdir, timeout_seconds=timeout_seconds)
    run_res["phase"] = command
    return run_res


def _execute_ansible_action(config: dict, context: dict) -> dict:
    """Run ansible-playbook for provisioning/configuration tasks."""
    if not shutil.which("ansible-playbook"):
        raise RuntimeError("ansible-playbook executable not found in PATH")

    # Containment first — playbook/inventory/workdir are forced inside the
    # operator-controlled PROVISIONING_ROOT_DIR, so a tenant cannot point the
    # runner at an attacker-staged playbook (which could carry local-exec /
    # shell tasks → RCE on the worker).
    playbook = _safe_provision_path(_render_step_value(config.get("playbook"), context), label="playbook")
    inventory = _safe_provision_path(
        _render_step_value(config.get("inventory"), context), label="inventory", required=False
    )
    workdir = _safe_provision_path(
        _render_step_value(config.get("workdir"), context), label="workdir", required=False
    )
    timeout_seconds = int(config.get("timeout_seconds", 1800))
    # Optional defense-in-depth: a config allow-list further narrows playbooks
    # (already constrained to the root above). Compared on the resolved path.
    allowed_playbooks = {str(p) for p in (config.get("allowed_playbooks") or [])}
    if allowed_playbooks and str(playbook) not in allowed_playbooks:
        raise ValueError(f"Ansible playbook '{playbook}' is not in allowed_playbooks")

    cmd = ["ansible-playbook", str(playbook)]
    if inventory:
        cmd.extend(["-i", str(inventory)])

    extra_vars = _render_step_value(config.get("extra_vars") or {}, context)
    if extra_vars:
        cmd.extend(["--extra-vars", json.dumps(extra_vars)])

    tags = _render_step_value(config.get("tags"), context)
    if tags:
        cmd.extend(["--tags", str(tags)])

    return _run_cli(cmd, cwd=workdir, timeout_seconds=timeout_seconds)


def _execute_step_action(config: dict, context: dict, db) -> dict:
    action_type = str(config.get("type", "create_alert")).lower()
    if action_type == "create_alert":
        from app.models.alert import Alert
        from app.services.alert_service import derive_alert_org_id

        db.add(
            Alert(
                alert_type="workflow",
                # Auditoria 2026-08: `Alert` no tiene `message`. Tiene `title` y
                # `description`, y SQLAlchemy responde `TypeError` a una palabra
                # clave que no es columna: la accion «crear alerta» de los
                # flujos de trabajo no creaba ninguna.
                title=config.get("message", "Workflow ejecutado"),
                description=config.get("message", "Workflow ejecutado"),
                severity=config.get("severity", "info"),
                # Sin esto, un workflow sin project_id en contexto crea una alerta
                # con los tres campos de ámbito a NULL, que _scope_alert_to_org
                # trata como visible para todas las organizaciones.
                organization_id=derive_alert_org_id(db, project_id=context.get("project_id")),
                project_id=context.get("project_id"),
            )
        )
        return {"ok": True, "action_type": action_type}

    if action_type == "notify_role":
        from app.services.notifications import notify_role
        from app.services.alert_service import derive_alert_org_id

        notify_role(
            db,
            config.get("role", "admin"),
            "automation",
            config.get("message", "Workflow ejecutado"),
            organization_id=derive_alert_org_id(db, project_id=context.get("project_id")),
        )
        return {"ok": True, "action_type": action_type}

    if action_type in {
        "provision_identity",
        "create_ad_user",
        "disable_ad_user",
        "assign_license",
        "revoke_license",
    }:
        if action_type != "provision_identity":
            config = {**config, "operation": action_type}
        return _execute_provision_action(config, context)

    if action_type in {"terraform", "terraform_apply", "terraform_destroy", "terraform_plan"}:
        if action_type != "terraform":
            mapped_cmd = action_type.replace("terraform_", "")
            config = {**config, "command": mapped_cmd}
        return _execute_terraform_action(config, context)

    if action_type in {"ansible", "ansible_playbook"}:
        return _execute_ansible_action(config, context)

    raise ValueError(f"Unsupported action type: {action_type}")
