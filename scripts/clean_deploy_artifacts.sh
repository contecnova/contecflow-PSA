#!/usr/bin/env bash
# Limpieza de artefactos locales no necesarios para deploy.
#
# Uso:
#   ./scripts/clean_deploy_artifacts.sh
#   ./scripts/clean_deploy_artifacts.sh --full-local
#   ./scripts/clean_deploy_artifacts.sh --purge-uploads
#   ./scripts/clean_deploy_artifacts.sh --full-local --purge-uploads
#
# Modos:
# - default: limpia caches/temporales/reports/DB local, mantiene .venv y frontend/node_modules
# - --full-local: además elimina .venv y frontend/node_modules
# - --purge-uploads: elimina uploads/documents/*

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

FULL_LOCAL=0
PURGE_UPLOADS=0

for arg in "$@"; do
  case "$arg" in
    --full-local)
      FULL_LOCAL=1
      ;;
    --purge-uploads)
      PURGE_UPLOADS=1
      ;;
    -h|--help)
      sed -n '1,40p' "$0"
      exit 0
      ;;
    *)
      echo "Argumento no reconocido: $arg"
      echo "Usa --help para ver opciones."
      exit 1
      ;;
  esac
done

echo "[clean] Root: $ROOT_DIR"

# 1) Caches y directorios temporales comunes
echo "[clean] Eliminando caches de Python/tests/lint..."
find . \
  -type d \( \
    -name '__pycache__' -o \
    -name '.pytest_cache' -o \
    -name '.mypy_cache' -o \
    -name '.ruff_cache' -o \
    -name '.cache' -o \
    -name 'playwright-report' -o \
    -name 'test-results' -o \
    -name 'htmlcov' \
  \) \
  -not -path './.git/*' \
  -exec rm -rf {} +

# 1.b) Builds/artefactos de frontend no necesarios para deploy desde código fuente
echo "[clean] Eliminando builds locales de frontend..."
rm -rf ./frontend/dist

# 2) Archivos temporales/logs/cobertura
echo "[clean] Eliminando temporales, logs y cobertura..."
find . \
  -type f \( \
    -name '*.pyc' -o \
    -name '*.pyo' -o \
    -name '*.tmp' -o \
    -name '*.log' -o \
    -name '.DS_Store' -o \
    -name '.coverage*' -o \
    -name 'coverage.xml' -o \
    -name 'junit*.xml' -o \
    -name 'npm-debug.log*' -o \
    -name 'yarn-error.log*' -o \
    -name '*.db-wal' -o \
    -name '*.db-shm' -o \
    -name '*.sqlite-wal' -o \
    -name '*.sqlite-shm' \
  \) \
  -not -path './.git/*' \
  -delete

# 3) Bases locales de desarrollo
echo "[clean] Eliminando DB local de desarrollo..."
rm -f ./contecflow.db ./contecflow_legacy.db

# 4) Limpieza opcional de uploads locales
if [[ "$PURGE_UPLOADS" -eq 1 ]]; then
  echo "[clean] Eliminando uploads/documents/* ..."
  rm -rf ./uploads/documents/*
fi

# 5) Limpieza profunda opcional de dependencias locales
if [[ "$FULL_LOCAL" -eq 1 ]]; then
  echo "[clean] --full-local activo: eliminando .venv y frontend/node_modules ..."
  rm -rf ./.venv ./frontend/node_modules
fi

# 6) Estado final
echo "[clean] Limpieza completada."
if git rev-parse --git-dir >/dev/null 2>&1; then
  echo "[clean] Estado git (si hay cambios tracked, no se tocan):"
  git status --short
fi
