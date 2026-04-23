#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PY="${ROOT_DIR}/venv/bin/python"

if [[ ! -x "$PY" ]]; then
  PY="python3"
fi

echo "[regression] Backend regression suite"
"$PY" -m pytest \
  "${ROOT_DIR}/tests/test_regression_invoices_created_at.py" \
  "${ROOT_DIR}/tests/test_regression_api_get_smoke.py" \
  "${ROOT_DIR}/tests/test_regression_api_operations_smoke.py" \
  -v --tb=short

echo "[regression] E2E regression suite"
"$PY" -m pytest \
  "${ROOT_DIR}/tests_e2e/test_e2e_sidebar_menu_smoke.py" \
  "${ROOT_DIR}/tests_e2e/test_e2e_dashboard_reporting_smoke.py" \
  "${ROOT_DIR}/tests_e2e/test_e2e_all_pages_regression.py" \
  "${ROOT_DIR}/tests_e2e/test_e2e_public_protected_regression.py" \
  -v --tb=short

echo "[regression] Done"
