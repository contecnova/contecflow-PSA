#!/usr/bin/env python3
"""Audit sensitive DB fields to ensure encrypted-at-rest format.

Fails with exit code 1 when plaintext/legacy-looking values are found.
"""

from __future__ import annotations

from pathlib import Path
import sys
from typing import Iterable

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.db.session import SessionLocal
from app.core.encryption import decrypt_value, encrypt_value
from app.models.ai_providers import AIProvider
from app.models.cab import IntegrationConfig
from app.models.enterprise import SSOConfig, Webhook
from app.models.marketplace import IntegrationInstance
from app.models.settings import AppSetting


def _is_encrypted(value: str | None) -> bool:
    if not value:
        return True
    return value.startswith("v2:") or value.startswith("kmsv1:")


def _scan_rows(
    rows: Iterable[object],
    field: str,
    label: str,
    out: list[str],
    *,
    remediate: bool,
    touched: list[int],
) -> None:
    for row in rows:
        value = getattr(row, field, None)
        if isinstance(value, str) and not _is_encrypted(value):
            rid = getattr(row, "id", "?")
            out.append(f"{label} id={rid} field={field}")
            if remediate:
                plain = decrypt_value(value)
                if plain:
                    setattr(row, field, encrypt_value(plain))
                    touched[0] += 1
                else:
                    setattr(row, field, encrypt_value(value))
                    touched[0] += 1


def main() -> int:
    import argparse

    parser = argparse.ArgumentParser(description="Audit encrypted-at-rest sensitive fields")
    parser.add_argument(
        "--remediate",
        action="store_true",
        help="Encrypt legacy plaintext values in-place before returning.",
    )
    args = parser.parse_args()

    db = SessionLocal()
    try:
        findings: list[str] = []
        touched = [0]

        _scan_rows(db.query(AIProvider).all(), "api_key", "ai_providers", findings, remediate=args.remediate, touched=touched)

        integrations = db.query(IntegrationConfig).all()
        _scan_rows(
            integrations,
            "access_token",
            "integration_configs",
            findings,
            remediate=args.remediate,
            touched=touched,
        )
        _scan_rows(
            integrations,
            "refresh_token",
            "integration_configs",
            findings,
            remediate=args.remediate,
            touched=touched,
        )

        _scan_rows(
            db.query(SSOConfig).all(),
            "oidc_client_secret",
            "sso_configs",
            findings,
            remediate=args.remediate,
            touched=touched,
        )
        _scan_rows(db.query(Webhook).all(), "secret", "webhooks", findings, remediate=args.remediate, touched=touched)

        _scan_rows(
            db.query(IntegrationInstance).all(),
            "encrypted_config",
            "integration_instances",
            findings,
            remediate=args.remediate,
            touched=touched,
        )

        settings_rows = db.query(AppSetting).filter(AppSetting.key.in_(["jira_api_token"])).all()
        _scan_rows(settings_rows, "value", "app_settings", findings, remediate=args.remediate, touched=touched)

        if args.remediate and touched[0] > 0:
            db.commit()
            print(f"[secrets-audit] remediated rows: {touched[0]}")

        if findings:
            print("[secrets-audit] PLAINTEXT OR LEGACY CIPHERTEXT FOUND:")
            for f in findings:
                print(f"- {f}")
            return 0 if args.remediate else 1

        print("[secrets-audit] OK: all audited sensitive fields are encrypted (v2/kmsv1)")
        return 0
    finally:
        db.close()


if __name__ == "__main__":
    raise SystemExit(main())
