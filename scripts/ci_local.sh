#!/usr/bin/env bash
# ══════════════════════════════════════════════════════════════════════════════
# Contecflow PSA — verificación local de calidad
# Uso: ./scripts/ci_local.sh            (todo)
#      ./scripts/ci_local.sh --fast     (omite pytest y cobertura, ~2 min)
#      ./scripts/ci_local.sh --info     (solo los gates informativos)
#
# Este proyecto no usa CI/CD por decisión de diseño: los gates se pasan aquí, a
# mano, antes de commitear. Este script es el único sitio donde están reunidos.
#
# ── Bloqueantes vs informativos ───────────────────────────────────────────────
# BLOQUEANTES: verdes a fecha de la auditoría 2026-08. Si uno falla, es una
#   regresión que acabas de introducir.
# INFORMATIVOS: rojos hoy por deuda ya medida y documentada. No bloquean; cada
#   uno lleva el nº de hallazgo de la auditoría que hay que cerrar para
#   promoverlo. Promover = mover su llamada de `info` a `blocking`.
#
# ── Nota sobre el fallo que tenía la versión anterior ─────────────────────────
# Usaba `if cmd | tail -3; then ok; fi`, que evalúa el estado de salida de
# `tail`, NO el del comando: un pytest en rojo reportaba "✅ Backend tests".
# Aquí el estado se captura del propio comando (ver `run_gate`).
# ══════════════════════════════════════════════════════════════════════════════
set -uo pipefail   # sin -e: queremos seguir y dar el resumen completo al final

cd "$(dirname "${BASH_SOURCE[0]}")/.." || exit 1

GREEN='\033[0;32m'; RED='\033[0;31m'; YELLOW='\033[1;33m'; CYAN='\033[0;36m'; NC='\033[0m'
PASS=0; FAIL=0; WARN=0
FAILED_GATES=()

# ── Intérprete Python ─────────────────────────────────────────────────────────
# Busca primero el venv del repo. La versión anterior solo probaba
# "$VIRTUAL_ENV/bin/python" (layout POSIX), así que en Windows caía al python
# del sistema — sin las dependencias instaladas.
PY_BIN=""
for candidate in \
  "${VIRTUAL_ENV:-}/bin/python" "${VIRTUAL_ENV:-}/Scripts/python.exe" \
  ".venv/bin/python" ".venv/Scripts/python.exe" \
  "venv/bin/python" "venv/Scripts/python.exe"; do
  if [[ -n "$candidate" && -x "$candidate" ]]; then PY_BIN="$candidate"; break; fi
done
if [[ -z "$PY_BIN" ]]; then
  PY_BIN="$(command -v python3 || command -v python || true)"
  [[ -n "$PY_BIN" ]] && echo -e "${YELLOW}⚠ Sin venv detectado; usando $PY_BIN${NC}"
fi
if [[ -z "$PY_BIN" ]]; then
  echo -e "${RED}No se encontró intérprete Python.${NC}"; exit 1
fi

step() { echo -e "\n${CYAN}══ $1 ══${NC}"; }

# run_gate <bloqueante|informativo> <nombre> <comando...>
# Captura la salida y el estado de salida REAL del comando.
run_gate() {
  local kind="$1"; local name="$2"; shift 2
  local out status
  out="$("$@" 2>&1)"; status=$?
  if [[ $status -eq 0 ]]; then
    echo -e "${GREEN}✅ $name${NC}"
    PASS=$((PASS+1))
  elif [[ "$kind" == "informativo" ]]; then
    echo -e "${YELLOW}⚠  $name — deuda conocida, no bloquea${NC}"
    echo "$out" | tail -4 | sed 's/^/     /'
    WARN=$((WARN+1))
  else
    echo -e "${RED}✗  $name${NC}"
    echo "$out" | tail -15 | sed 's/^/     /'
    FAIL=$((FAIL+1)); FAILED_GATES+=("$name")
  fi
}

MODE="${1:-all}"

# ── Gates bloqueantes ─────────────────────────────────────────────────────────
if [[ "$MODE" != "--info" ]]; then
  step "Bloqueantes"
  run_gate bloqueante "ruff (app + tests)"          "$PY_BIN" -m ruff check app tests
  run_gate bloqueante "árbol de dependencias"       "$PY_BIN" -m pip check
  # Los 2 CVEs ignorados no tienen remediación disponible hoy; están listados uno
  # a uno (no se desactiva el gate) para que un CVE NUEVO sí salga en rojo.
  #   PYSEC-2026-3447 setuptools — torch 2.11 exige setuptools<82.
  #   PYSEC-2026-1325 ecdsa      — sin versión corregida publicada; su único
  #     camino alcanzable ya se migró de python-jose a PyJWT.
  run_gate bloqueante "pip-audit" \
    "$PY_BIN" -m pip_audit -r requirements.txt \
      --ignore-vuln PYSEC-2026-3447 --ignore-vuln PYSEC-2026-1325

  if [[ "$MODE" != "--fast" ]]; then
    run_gate bloqueante "pytest (suite completa)" \
      "$PY_BIN" -m pytest tests -q --no-header -p no:cacheprovider -n auto
  else
    echo -e "${YELLOW}⚠  pytest omitido (--fast)${NC}"
  fi

  step "Bloqueantes — frontend"
  run_gate bloqueante "tsc (configuración base)" \
    bash -c 'cd frontend && npx tsc -p tsconfig.json --noEmit'
  run_gate bloqueante "vitest" \
    bash -c 'cd frontend && npx vitest run'
  run_gate bloqueante "build" \
    bash -c 'cd frontend && npm run build --silent'

  # eslint promovido a BLOQUEANTE (auditoría 2026-08, hallazgo 6). Al instalar
  # @typescript-eslint/parser aparecieron 80 errores que nunca se habían visto;
  # están todos corregidos, así que un error nuevo es una regresión.
  #
  # El tope de warnings es la línea base MEDIDA (1.974: sobre todo etiquetas de
  # accesibilidad y reglas del sistema de diseño, que el proyecto configuró como
  # avisos a propósito). Fijarlo así permite que baje y no que suba. Al reducir
  # la deuda, bajar este número — nunca subirlo.
  run_gate bloqueante "eslint (0 errores, warnings ≤ 1974)" \
    bash -c 'cd frontend && npx eslint src --ext .js,.jsx,.ts,.tsx --max-warnings 1974'
fi

# ── Gates informativos ────────────────────────────────────────────────────────
if [[ "$MODE" != "--fast" ]]; then
  step "Informativos (deuda medida, no bloquean)"
  run_gate informativo "ruff scripts/ — hallazgo 17" \
    "$PY_BIN" -m ruff check scripts
  run_gate informativo "tsc estricto — hallazgo 10" \
    bash -c 'cd frontend && npx tsc -p tsconfig.strict.json --noEmit'
  # lint:a11y ya vale algo: hasta la auditoría 2026-08 informaba "0 findings"
  # porque no podía parsear 304 de 343 ficheros. Con el parser instalado sus
  # números son reales (1.480 avisos de etiquetas), y son deuda de marcado que
  # requiere decidir la etiqueta correcta caso por caso.
  run_gate informativo "auditoría de accesibilidad (deuda de marcado)" \
    bash -c 'cd frontend && npm run --silent lint:a11y:report'
  run_gate informativo "check i18n — hallazgo 16" \
    bash -c 'cd frontend && npm run --silent check:i18n'
  run_gate informativo "npm audit — hallazgo 17" \
    bash -c 'cd frontend && npm audit --audit-level=high'
fi

# ── Resumen ───────────────────────────────────────────────────────────────────
echo ""
echo "══════════════════════════════════════════════════════════════"
echo -e "  ${GREEN}✅ $PASS OK${NC}   ${YELLOW}⚠ $WARN deuda conocida${NC}   ${RED}✗ $FAIL fallos${NC}"
echo "══════════════════════════════════════════════════════════════"
if [[ $FAIL -eq 0 ]]; then
  echo -e "${GREEN}Gates bloqueantes: VERDE ✅${NC}"
  exit 0
fi
echo -e "${RED}Gates bloqueantes: ROJO ✗${NC}"
for g in "${FAILED_GATES[@]}"; do echo -e "${RED}  · $g${NC}"; done
exit 1
