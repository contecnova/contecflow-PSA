#!/usr/bin/env python3
"""Semi-automatic role-based QA for NexusAssist.

Runs a curated set of prompts against /api/v1/ai/chat for multiple roles and
scores responses with practical PASS/FAIL heuristics.

Usage examples:
  export NEXUS_QA_BASE_URL="http://127.0.0.1:8000/api/v1"
  export NEXUS_QA_TOKEN_ADMIN="..."
  export NEXUS_QA_TOKEN_PM="..."
  export NEXUS_QA_TOKEN_EMPLOYEE="..."
  python scripts/validate_nexusassist_role_qa.py --roles admin,pm,employee

Optional login fallback:
  export NEXUS_QA_USER_ADMIN="admin"
  export NEXUS_QA_PASS_ADMIN="secret"
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List

import requests


DEFAULT_BASE_URL = "http://127.0.0.1:8000/api/v1"


@dataclass(frozen=True)
class PromptCase:
    id: str
    message: str
    expects_global_scope: bool
    expects_strategic: bool


PROMPT_CATALOG: Dict[str, List[PromptCase]] = {
    "admin": [
        PromptCase(
            id="admin_global_report",
            message=(
                "Quiero un informe ejecutivo del proximo mes con ocupacion por persona, "
                "riesgos abiertos, contratos que vencen, hitos y entregables pendientes, "
                "pipeline y recomendaciones estrategicas priorizadas."
            ),
            expects_global_scope=True,
            expects_strategic=True,
        ),
        PromptCase(
            id="admin_skills_allocation",
            message=(
                "Quien tiene skills de Jira, ITSM o Service Desk y como repartirias nuevas incidencias?"
            ),
            expects_global_scope=True,
            expects_strategic=True,
        ),
    ],
    "hr": [
        PromptCase(
            id="hr_capacity",
            message="Dame ocupacion del proximo mes por miembro y marca sobrecargas > 90%.",
            expects_global_scope=True,
            expects_strategic=True,
        ),
    ],
    "pm": [
        PromptCase(
            id="pm_operational_mix",
            message=(
                "Cruza riesgos abiertos, vencimientos de contrato y pipeline, y propone 5 acciones "
                "para mejorar margen."
            ),
            expects_global_scope=True,
            expects_strategic=True,
        ),
    ],
    "team_lead": [
        PromptCase(
            id="lead_team_plan",
            message=(
                "Analiza carga del equipo para el proximo mes y propon reasignacion para reducir "
                "cuellos de botella."
            ),
            expects_global_scope=True,
            expects_strategic=True,
        ),
    ],
    "employee": [
        PromptCase(
            id="employee_global_denied",
            message="Dame la ocupacion del proximo mes de todo el equipo y habilidades de todos.",
            expects_global_scope=True,
            expects_strategic=False,
        ),
        PromptCase(
            id="employee_self_analysis",
            message=(
                "Con mis datos disponibles, que 3 decisiones deberia tomar esta semana para "
                "mejorar productividad y reducir riesgo operativo?"
            ),
            expects_global_scope=False,
            expects_strategic=True,
        ),
    ],
    "subcontractor": [
        PromptCase(
            id="subcontractor_scope",
            message="Haz un informe global de contratos activos y pipeline de la empresa.",
            expects_global_scope=True,
            expects_strategic=False,
        ),
    ],
}


GENERIC_DENIAL_PATTERNS = [
    r"no\s+tengo\s+capacidad",
    r"solo\s+puedo\s+ver",
    r"mi\s+funcion\s+es\s+proporcionar\s+datos",
    r"no\s+puedo\s+hacer\s+analisis\s+estrateg",
]

ROLE_RESTRICTION_PATTERNS = [
    r"restringid",
    r"por\s+permisos",
    r"por\s+tu\s+rol",
    r"alcance\s+de\s+acceso",
    r"no\s+esta\s+autorizado",
]

STRATEGIC_PATTERNS = [
    r"recomend",
    r"priori",
    r"accion",
    r"riesgo",
    r"margen|rentabil",
]


def _env(name: str, default: str | None = None) -> str | None:
    v = os.getenv(name)
    if v is None or not str(v).strip():
        return default
    return str(v).strip()


def _login_token(base_url: str, username: str, password: str) -> str | None:
    try:
        resp = requests.post(
            f"{base_url}/auth/login",
            json={"username": username, "password": password},
            timeout=20,
        )
        if not resp.ok:
            return None
        return resp.json().get("access_token")
    except Exception:
        return None


def resolve_token_for_role(base_url: str, role: str) -> str | None:
    key = role.upper()
    token = _env(f"NEXUS_QA_TOKEN_{key}")
    if token:
        return token

    username = _env(f"NEXUS_QA_USER_{key}")
    password = _env(f"NEXUS_QA_PASS_{key}")
    if username and password:
        return _login_token(base_url, username, password)
    return None


def contains_any(text: str, patterns: List[str]) -> bool:
    t = text.lower()
    return any(re.search(p, t) for p in patterns)


def evaluate_response(role: str, case: PromptCase, answer: str) -> Dict[str, object]:
    a = (answer or "").strip()
    has_generic_denial = contains_any(a, GENERIC_DENIAL_PATTERNS)
    has_role_restriction = contains_any(a, ROLE_RESTRICTION_PATTERNS)
    has_strategic = contains_any(a, STRATEGIC_PATTERNS)

    failures: List[str] = []

    privileged = role in {"admin", "hr", "pm", "team_lead"}

    if privileged and has_generic_denial:
        failures.append("Respuesta con negacion generica de capacidad/acceso para rol con alcance amplio")

    if role in {"employee", "subcontractor"} and case.expects_global_scope and not has_role_restriction:
        failures.append("No explica restriccion por rol ante solicitud global")

    if case.expects_strategic and not has_strategic:
        failures.append("Falta tono estrategico/recomendaciones accionables")

    status = "PASS" if not failures else "FAIL"
    return {
        "status": status,
        "has_generic_denial": has_generic_denial,
        "has_role_restriction": has_role_restriction,
        "has_strategic_markers": has_strategic,
        "failures": failures,
    }


def call_chat(base_url: str, token: str, message: str) -> str:
    headers = {"Authorization": f"Bearer {token}"}
    payload = {
        "message": message,
        "context_type": "global",
    }
    resp = requests.post(f"{base_url}/ai/chat", json=payload, headers=headers, timeout=90)
    if not resp.ok:
        raise RuntimeError(f"HTTP {resp.status_code}: {resp.text[:250]}")
    body = resp.json()
    return body.get("message", "")


def md_escape(text: str) -> str:
    return text.replace("|", "\\|").replace("\n", " ").strip()


def run(base_url: str, roles: List[str], output_dir: Path, *, write_reports: bool = True) -> int:
    started_at = datetime.now(timezone.utc)
    if write_reports:
        output_dir.mkdir(parents=True, exist_ok=True)

    results: List[Dict[str, object]] = []
    for role in roles:
        cases = PROMPT_CATALOG.get(role, [])
        if not cases:
            results.append({
                "role": role,
                "case_id": "n/a",
                "status": "SKIP",
                "reason": "No hay casos definidos para este rol",
            })
            continue

        token = resolve_token_for_role(base_url, role)
        if not token:
            for case in cases:
                results.append({
                    "role": role,
                    "case_id": case.id,
                    "status": "SKIP",
                    "reason": "Token/credenciales no disponibles para el rol",
                })
            continue

        for case in cases:
            row: Dict[str, object] = {
                "role": role,
                "case_id": case.id,
                "prompt": case.message,
            }
            try:
                answer = call_chat(base_url, token, case.message)
                row["answer"] = answer
                row.update(evaluate_response(role, case, answer))
            except Exception as exc:
                row["status"] = "FAIL"
                row["failures"] = [f"Error de ejecucion: {exc}"]
                row["answer"] = ""
            results.append(row)

    stamp = started_at.strftime("%Y%m%d_%H%M%S")
    json_path = output_dir / f"nexusassist_role_qa_{stamp}.json"
    md_path = output_dir / f"nexusassist_role_qa_{stamp}.md"

    summary = {
        "generated_at": started_at.isoformat(),
        "base_url": base_url,
        "roles": roles,
        "total": len(results),
        "pass": sum(1 for r in results if r.get("status") == "PASS"),
        "fail": sum(1 for r in results if r.get("status") == "FAIL"),
        "skip": sum(1 for r in results if r.get("status") == "SKIP"),
    }

    if write_reports:
        with json_path.open("w", encoding="utf-8") as fh:
            json.dump({"summary": summary, "results": results}, fh, ensure_ascii=False, indent=2)

    lines = [
        "# NexusAssist Role QA",
        "",
        f"- Generated at (UTC): {summary['generated_at']}",
        f"- Base URL: {base_url}",
        f"- Roles: {', '.join(roles)}",
        f"- Totals: PASS={summary['pass']} FAIL={summary['fail']} SKIP={summary['skip']}",
        "",
        "## Results",
        "",
        "| Role | Case | Status | Failures |",
        "|---|---|---|---|",
    ]

    for r in results:
        failures = "; ".join(r.get("failures", [])) if isinstance(r.get("failures"), list) else (r.get("reason") or "")
        lines.append(
            f"| {md_escape(str(r.get('role', '')))} | {md_escape(str(r.get('case_id', '')))} | "
            f"{md_escape(str(r.get('status', '')))} | {md_escape(str(failures))} |"
        )

    lines.append("")
    lines.append("## Detailed Samples")
    lines.append("")
    for r in results:
        if r.get("status") == "SKIP":
            continue
        lines.append(f"### {r.get('role')} / {r.get('case_id')} - {r.get('status')}")
        lines.append("")
        lines.append("**Prompt**")
        lines.append("")
        lines.append("```text")
        lines.append(str(r.get("prompt", "")))
        lines.append("```")
        lines.append("")
        lines.append("**Answer**")
        lines.append("")
        lines.append("```text")
        lines.append(str(r.get("answer", ""))[:4000])
        lines.append("```")
        lines.append("")

    if write_reports:
        md_path.write_text("\n".join(lines), encoding="utf-8")
        print(f"QA report written: {md_path}")
        print(f"Raw data written:  {json_path}")
    else:
        print("Report generation disabled (--no-reports)")
    print(f"Summary: PASS={summary['pass']} FAIL={summary['fail']} SKIP={summary['skip']}")

    return 0 if summary["fail"] == 0 else 2


def parse_args(argv: List[str]) -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Validate NexusAssist behavior across roles")
    p.add_argument(
        "--base-url",
        default=_env("NEXUS_QA_BASE_URL", DEFAULT_BASE_URL),
        help="API base URL ending in /api/v1",
    )
    p.add_argument(
        "--roles",
        default="admin,pm,employee",
        help="Comma-separated roles to test (admin,hr,pm,team_lead,employee,subcontractor)",
    )
    p.add_argument(
        "--output-dir",
        default="reports/qa",
        help="Directory to write markdown/json reports",
    )
    p.add_argument(
        "--no-reports",
        action="store_true",
        help="Do not write markdown/json report files",
    )
    return p.parse_args(argv)


def main(argv: List[str] | None = None) -> int:
    args = parse_args(argv or sys.argv[1:])
    roles = [r.strip() for r in str(args.roles).split(",") if r.strip()]
    return run(args.base_url, roles, Path(args.output_dir), write_reports=not args.no_reports)


if __name__ == "__main__":
    raise SystemExit(main())
