#!/usr/bin/env bash
# ══════════════════════════════════════════════════════════════════════════════
# Contecflow PSA — CI local (corre el mismo pipeline que GitHub/GitLab)
# Uso: ./scripts/ci_local.sh
# ══════════════════════════════════════════════════════════════════════════════
set -euo pipefail

GREEN='\033[0;32m'; RED='\033[0;31m'; YELLOW='\033[1;33m'; CYAN='\033[0;36m'; NC='\033[0m'
PASS=0; FAIL=0

step() { echo -e "\n${CYAN}══ $1 ══${NC}"; }
ok()   { echo -e "${GREEN}✅ $1${NC}"; PASS=$((PASS+1)); }
fail() { echo -e "${RED}✗  $1${NC}"; FAIL=$((FAIL+1)); }

# Prefer active venv python, fallback to python3/python.
PY_BIN=""
if [[ -n "${VIRTUAL_ENV:-}" && -x "${VIRTUAL_ENV}/bin/python" ]]; then
  PY_BIN="${VIRTUAL_ENV}/bin/python"
elif command -v python3 >/dev/null 2>&1; then
  PY_BIN="$(command -v python3)"
elif command -v python >/dev/null 2>&1; then
  PY_BIN="$(command -v python)"
else
  echo -e "${RED}No se encontró intérprete Python (python3/python).${NC}"
  exit 1
fi

step "1/4 — Tests de Backend"
if "$PY_BIN" -m pytest tests/ -q --tb=short -p no:warnings 2>&1 | tail -3; then
  ok "Backend tests"
else
  fail "Backend tests FALLARON"
fi

step "2/4 — Cobertura de código"
if "$PY_BIN" -m coverage run -m pytest tests/ -q --tb=no -p no:warnings >/dev/null 2>&1 && \
   "$PY_BIN" -m coverage report --fail-under=55 2>&1 | tail -3; then
  ok "Cobertura OK (≥55%)"
else
  fail "Cobertura insuficiente (<55%)"
fi

step "3/4 — Build del frontend"
if cd frontend && npm run build --silent 2>&1 | tail -2 && cd ..; then
  ok "Frontend build"
else
  fail "Frontend build FALLÓ"
fi

step "4/4 — Python syntax check"
SYNTAX_ERRORS=$("$PY_BIN" -m py_compile $(find app -name "*.py" ! -path "*__pycache__*") 2>&1)
if [[ -z "$SYNTAX_ERRORS" ]]; then
  ok "Sin errores de sintaxis Python"
else
  fail "Errores de sintaxis: $SYNTAX_ERRORS"
fi

echo ""
echo "══════════════════════════════════════════════"
echo -e "  ${GREEN}✅ $PASS pasos OK${NC}  |  ${RED}✗ $FAIL pasos FALLARON${NC}"
echo "══════════════════════════════════════════════"
[[ $FAIL -eq 0 ]] && echo -e "${GREEN}Pipeline CI: VERDE ✅${NC}" || \
  (echo -e "${RED}Pipeline CI: ROJO ✗${NC}" && exit 1)
