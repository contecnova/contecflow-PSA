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
from app.core.codigos_de_error import ErrorConCodigo


ALLOWED_TERRAFORM_COMMANDS = {"plan", "apply", "destroy"}


_MARCADOR = __import__("re").compile(r"\{([A-Za-z_][A-Za-z0-9_]*)\}")


def _render_step_value(value, context: dict):
    """Sustituye ``{nombre}`` por el valor del contexto.

    Auditoría 22-11-2026 (M58): antes era ``str.format_map`` con plantillas que
    escribe la empresa, que admite ``{x.__class__}`` o ``{x[0]}`` (lectura de
    atributos internos). Ahora solo nombres simples; lo demás se deja tal cual.
    """
    if isinstance(value, str):
        def _uno(m):
            nombre = m.group(1)
            if nombre not in context:
                return m.group(0)
            return "" if context[nombre] is None else str(context[nombre])
        return _MARCADOR.sub(_uno, value)
    if isinstance(value, list):
        return [_render_step_value(v, context) for v in value]
    if isinstance(value, dict):
        return {k: _render_step_value(v, context) for k, v in value.items()}
    return value


def _provisioning_root(org_id=None) -> "Path":
    """Return the operator-controlled provisioning root, or raise if provisioning
    is disabled / unconfigured (fail-closed).

    Auditoría 22-11-2026 (A13): con empresa, la raíz es ``<raíz>/<org_id>``:
    una empresa no puede ejecutar ni destruir los módulos de otra (estándar de
    los orquestadores con espacios de trabajo por inquilino). Sin empresa, la
    raíz común solo la usan llamadas internas de la plataforma.
    """
    if not settings.PROVISIONING_ENABLED:
        raise PermissionError("Infrastructure provisioning is disabled (set PROVISIONING_ENABLED=1)")
    root = (settings.PROVISIONING_ROOT_DIR or "").strip()
    if not root:
        raise PermissionError("PROVISIONING_ROOT_DIR is not configured; refusing to run provisioning")
    base = Path(root).resolve()
    if org_id:
        sub = (base / str(org_id)).resolve()
        if sub.parent != base:
            raise ErrorConCodigo("aprovisionamiento_ruta_no_permitida", detail="bad organization folder",
                                 campo="organization_id")
        return sub
    return base


def _safe_provision_path(candidate, *, label: str, required: bool = True, org_id=None) -> "str | None":
    """Resolve *candidate* and guarantee it stays inside PROVISIONING_ROOT_DIR
    (``/<org_id>`` when given: A13).

    Blocks path-traversal / absolute-path escapes / symlink breakout so a
    tenant-supplied workdir/playbook/var_file/inventory can never make the
    runner execute code outside the vetted module tree. Returns the resolved
    absolute path as a string, or None when *candidate* is empty and not
    required. Raises ValueError on any containment violation.
    """
    if candidate is None or str(candidate).strip() == "":
        if required:
            raise ErrorConCodigo("campo_obligatorio", detail=f"Provisioning '{label}' is required", campo=label)
        return None
    root = _provisioning_root(org_id)
    resolved = (root / str(candidate)).resolve()
    try:
        resolved.relative_to(root)
    except ValueError:
        raise ErrorConCodigo("aprovisionamiento_ruta_no_permitida", detail=f"Provisioning '{label}' escapes the provisioning root", campo=label)
    return str(resolved)


#: A13: variables del entorno que hereda la herramienta (nada de secretos del
#: worker: ni `SECRET_KEY`, ni `DATABASE_URL`, ni credenciales de nube). Las
#: credenciales de cada módulo van en su `var_file` dentro de la carpeta de la empresa.
_ENTORNO_PERMITIDO = ("PATH", "HOME", "USERPROFILE", "SYSTEMROOT", "TEMP", "TMP", "LANG", "LC_ALL")


def _entorno_minimo() -> dict:
    import os
    env = {k: os.environ[k] for k in _ENTORNO_PERMITIDO if k in os.environ}
    env["TF_IN_AUTOMATION"] = "1"
    env["ANSIBLE_NOCOLOR"] = "1"
    return env


def _run_cli(cmd: list[str], cwd: str | None = None, timeout_seconds: int = 1200) -> dict:
    started = datetime.now(timezone.utc)
    proc = subprocess.run(
        cmd,
        cwd=cwd,
        capture_output=True,
        text=True,
        timeout=timeout_seconds,
        check=False,
        env=_entorno_minimo(),
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


def _org_del_contexto(context: dict):
    """La empresa del flujo (obligatoria para Terraform/Ansible: A13, fail-closed)."""
    org = context.get("organization_id")
    if not org:
        raise ErrorConCodigo("aprovisionamiento_sin_empresa")
    return str(org)


def _destroy_aprobado(org_id: str, context: dict) -> None:
    """A13: `terraform destroy` solo con una aprobación humana ya concedida
    (`destroy_approval_id` en el contexto: una solicitud de aprobación
    `approved` de la MISMA empresa). Es lo que hacen los orquestadores de
    infraestructura (plan de destrucción revisado y confirmado por una persona);
    un flujo automático nunca destruye por sí solo."""
    aprobacion = context.get("destroy_approval_id")
    if not aprobacion:
        raise ErrorConCodigo("aprovisionamiento_destroy_sin_aprobacion")
    from app.db.session import SessionLocal
    from app.models.billing_reports import ApprovalRequest
    with SessionLocal() as s:
        from app.db.contexto_de_tenant import fijar_contexto as _fijar_contexto
        _fijar_contexto(s, org_id, "aprovisionamiento sin empresa")  # auditoría 22-11-2026: TENANT_SESION_SIN_CONTEXTO=cerrar
        ok = s.query(ApprovalRequest.id).filter(
            ApprovalRequest.id == str(aprobacion), ApprovalRequest.organization_id == org_id,
            ApprovalRequest.status == "approved").first()
    if not ok:
        raise ErrorConCodigo("aprovisionamiento_destroy_sin_aprobacion")


def _validate_provision_url(url: str) -> None:
    """Valida la URL de aprovisionamiento contra SSRF (guardia central).

    22-11-2026 (01 M7): era un tercer validador propio sin resolver el DNS.
    Ahora delega en `app.core.outbound_url` (HTTPS obligatorio) y lanza
    `ErrorConCodigo` (un `ValueError`), como antes.
    """
    from app.core.outbound_url import validar_url_o_valueerror

    validar_url_o_valueerror(url, field="Provision URL", require_https=True)


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
        raise ErrorConCodigo("campo_obligatorio", detail="Provision action requires 'url'", campo="url")

    # SSRF protection: block requests to internal/private networks
    _validate_provision_url(url)

    method = str(config.get("method") or "POST").upper()
    headers = _render_step_value(config.get("headers") or {}, context)
    payload = _render_step_value(config.get("payload") or {}, context)
    timeout_seconds = int(config.get("timeout_seconds", 15))

    started = datetime.now(timezone.utc)
    from app.core.outbound_url import cliente_httpx
    with cliente_httpx(timeout=timeout_seconds) as client:
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
    org = _org_del_contexto(context)
    workdir = _safe_provision_path(_render_step_value(config.get("workdir"), context), label="workdir", org_id=org)
    command = str(config.get("command") or "apply").lower()
    allowed_commands = {
        str(c).lower() for c in (config.get("allowed_commands") or sorted(ALLOWED_TERRAFORM_COMMANDS))
    }
    if command not in allowed_commands:
        raise ErrorConCodigo("aprovisionamiento_comando_no_permitido", detail=f"Terraform command '{command}' is not in allowed_commands", comando=command)
    if command not in ALLOWED_TERRAFORM_COMMANDS:
        raise ErrorConCodigo("aprovisionamiento_comando_no_permitido", detail=f"Terraform command '{command}' is not allowed by runtime policy", comando=command)
    if not shutil.which("terraform"):
        raise RuntimeError("terraform executable not found in PATH")

    if command == "destroy":
        _destroy_aprobado(org, context)
    auto_approve = bool(config.get("auto_approve", True))
    var_file = _safe_provision_path(
        _render_step_value(config.get("var_file"), context), label="var_file", required=False, org_id=org
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
    org = _org_del_contexto(context)
    playbook = _safe_provision_path(_render_step_value(config.get("playbook"), context), label="playbook", org_id=org)
    inventory = _safe_provision_path(
        _render_step_value(config.get("inventory"), context), label="inventory", required=False, org_id=org
    )
    workdir = _safe_provision_path(
        _render_step_value(config.get("workdir"), context), label="workdir", required=False, org_id=org
    )
    timeout_seconds = int(config.get("timeout_seconds", 1800))
    # Optional defense-in-depth: a config allow-list further narrows playbooks
    # (already constrained to the root above). Compared on the resolved path.
    allowed_playbooks = {str(p) for p in (config.get("allowed_playbooks") or [])}
    if allowed_playbooks and str(playbook) not in allowed_playbooks:
        raise ErrorConCodigo("aprovisionamiento_comando_no_permitido", detail=f"Ansible playbook '{playbook}' is not in allowed_playbooks", comando=playbook)

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
    if not context.get("organization_id"):
        # A13: la empresa del flujo, de la sesión (no del payload del paso).
        from app.services.exchange_rate_service import org_de_la_sesion
        org = org_de_la_sesion(db)
        if org:
            context = {**context, "organization_id": org}
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

    raise ErrorConCodigo("valor_no_valido", detail=f"Unsupported action type: {action_type}", valor=action_type)
