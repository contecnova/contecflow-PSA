#!/bin/bash
# Clarive — Arranque en Mac/Linux (solo Python 3.12)
set -e
GREEN='\033[0;32m'; CYAN='\033[0;36m'; YELLOW='\033[1;33m'; RED='\033[0;31m'; NC='\033[0m'
log()  { echo -e "${CYAN}▶ $1${NC}"; }
ok()   { echo -e "${GREEN}✅ $1${NC}"; }
err()  { echo -e "${RED}❌ $1${NC}"; exit 1; }

DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$DIR"
CMD="${1:-start}"

if [ -x ".venv/bin/python" ]; then
  PY_BIN=".venv/bin/python"
  PIP_BIN=".venv/bin/pip"
  VENV_DIR=".venv"
elif [ -x "venv/bin/python" ]; then
  PY_BIN="venv/bin/python"
  PIP_BIN="venv/bin/pip"
  VENV_DIR="venv"
else
  PY_BIN=""
  PIP_BIN=""
  VENV_DIR=""
fi

detect_python() {
  for cmd in python3.12 python3.11 python3.10 python3; do
    if command -v "$cmd" &>/dev/null; then
      MAJOR=$("$cmd" -c "import sys; print(sys.version_info.major)")
      MINOR=$("$cmd" -c "import sys; print(sys.version_info.minor)")
      if [ "$MAJOR" = "3" ] && [ "$MINOR" -ge "10" ]; then
        echo "$cmd"; return
      fi
    fi
  done
  err "Necesitas Python 3.10 o superior.\nDescárgalo en: https://www.python.org/downloads/"
}

if [ -z "$PY_BIN" ]; then
  PY_BIN="$(detect_python)"
fi

case "$CMD" in
setup|install)
  log "Detectando Python compatible..."
  PYTHON=$(detect_python)
  ok "Usando: $($PYTHON --version)"
  log "Creando entorno virtual..."
  if [ -z "$VENV_DIR" ]; then
    $PYTHON -m venv .venv
    PY_BIN=".venv/bin/python"
    PIP_BIN=".venv/bin/pip"
    VENV_DIR=".venv"
  fi
  ok "Entorno virtual listo"
  log "Instalando dependencias..."
  "$PIP_BIN" install --upgrade pip -q
  "$PIP_BIN" install -r requirements.txt -q
  ok "Dependencias instaladas"
  log "Inicializando base de datos..."
  "$PY_BIN" -c "from app.db.base import Base; from app.db.session import engine; Base.metadata.create_all(bind=engine); print('BD creada')"
  log "Cargando datos de prueba..."
  "$PY_BIN" -m app.db.seed
  echo ""
  echo -e "${GREEN}╔══════════════════════════════════════════╗${NC}"
  echo -e "${GREEN}║  Setup completado ✅  Ahora ejecuta:     ║${NC}"
  echo -e "${GREEN}║         ./start.sh                       ║${NC}"
  echo -e "${GREEN}╚══════════════════════════════════════════╝${NC}"
  ;;
start|"")
  echo ""
  echo -e "  ${CYAN}╔══════════════════════════════════════════╗${NC}"
  echo -e "  ${CYAN}║          ◈  CLARIVE  PSA                 ║${NC}"
  echo -e "  ${CYAN}║   Professional Services Automation        ║${NC}"
  echo -e "  ${CYAN}╚══════════════════════════════════════════╝${NC}"
  echo ""
  echo -e "  🌐  App:    ${CYAN}http://localhost:3000${NC}"
  echo -e "  🔧  API:    ${CYAN}http://localhost:8000/api/v1/docs${NC}"
  echo -e "  📡  WS:     ${CYAN}ws://localhost:8000/api/v1/ws/notifications${NC}"
  echo ""
  DEMO_PASSWORD=$(grep -E '^DEFAULT_USER_PASSWORD=' .env 2>/dev/null | tail -1 | cut -d'=' -f2-)
  [ -z "$DEMO_PASSWORD" ] && DEMO_PASSWORD="clarive2024!"
  echo -e "  ${YELLOW}Credenciales de demo:${NC}"
  echo -e "    admin      /  ${DEMO_PASSWORD}   ${GREEN}(Administrador)${NC}"
  echo -e "    ana.torres /  ${DEMO_PASSWORD}   ${GREEN}(Project Manager)${NC}"
  echo -e "    luis.vega  /  ${DEMO_PASSWORD}   ${GREEN}(Developer)${NC}"
  echo -e "    rrhh       /  ${DEMO_PASSWORD}   ${GREEN}(RRHH)${NC}"
  echo ""
  echo -e "  Pulsa ${RED}Ctrl+C${NC} para parar"
  echo ""
  # Migración automática clarive_legacy.db → clarive.db (compatibilidad)
  if [ -f "clarive_legacy.db" ] && [ ! -f "clarive.db" ]; then
    echo "  🔄 Migrando clarive_legacy.db → clarive.db..."
    cp clarive_legacy.db clarive.db
    echo "  ✅ Base de datos migrada"
  fi
  UVICORN_LOG_LEVEL="${LOG_LEVEL:-info}"
  UVICORN_RELOAD="${UVICORN_RELOAD:-1}"
  if [ "$UVICORN_RELOAD" = "1" ]; then
    "$PY_BIN" -m uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload --log-level "$UVICORN_LOG_LEVEL"
  else
    "$PY_BIN" -m uvicorn app.main:app --host 0.0.0.0 --port 8000 --log-level "$UVICORN_LOG_LEVEL"
  fi
  ;;
seed)
  "$PY_BIN" -m app.db.seed
  ;;
reset)
  warn() { echo -e "${YELLOW}⚠  $1${NC}"; }
  warn "Borrará toda la base de datos."
  read -p "¿Continuar? (s/N): " c
  if [ "$c" = "s" ] || [ "$c" = "S" ]; then
    rm -f clarive.db
    "$PY_BIN" -c "from app.db.base import Base; from app.db.session import engine; Base.metadata.create_all(bind=engine)"
    "$PY_BIN" -m app.db.seed
    ok "Base de datos reiniciada"
  fi
  ;;
esac
