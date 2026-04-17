#!/bin/bash

# ============================================================
#  Clarive — Script de instalación y arranque
#  Compatible: macOS y Linux
#  Uso:
#    ./setup.sh          → instala todo y arranca
#    ./setup.sh start    → solo arranca (ya instalado)
#    ./setup.sh update   → actualiza dependencias y BD
# ============================================================

set -e

CYAN='\033[0;36m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
BOLD='\033[1m'
NC='\033[0m'

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
BACKEND_PORT=8000
FRONTEND_PORT=3000
PYTHON_MIN="3.10"
VENV_DIR=""
PY_BIN=""
PIP_BIN=""

print_banner() {
  echo ""
  echo -e "${CYAN}${BOLD}"
  echo ""
  echo -e "  ${CYAN}╔══════════════════════════════════════════╗${NC}"
  echo -e "  ${CYAN}║                                          ║${NC}"
  echo -e "  ${CYAN}║   ◈  CLARIVE                             ║${NC}"
  echo -e "  ${CYAN}║   Professional Services Automation       ║${NC}"
  echo -e "  ${CYAN}║                                          ║${NC}"
  echo -e "  ${CYAN}╚══════════════════════════════════════════╝${NC}"
  echo -e "  ${BOLD}clarive2024! — Plataforma PSA Enterprise${NC}"
  echo ""
}

log()     { echo -e "${GREEN}▶${NC} $1"; }
warn()    { echo -e "${YELLOW}⚠${NC}  $1"; }
error()   { echo -e "${RED}✗${NC}  $1"; }
section() { echo -e "\n${CYAN}${BOLD}── $1 ──${NC}"; }

# ── Check commands ────────────────────────────────────────────────────────────
check_command() {
  command -v "$1" &>/dev/null
}

hash_file() {
  local file="$1"
  if check_command shasum; then
    shasum -a 256 "$file" 2>/dev/null | awk '{print $1}'
  elif check_command md5sum; then
    md5sum "$file" 2>/dev/null | awk '{print $1}'
  elif check_command md5; then
    md5 -q "$file" 2>/dev/null
  else
    echo "nohash"
  fi
}

hash_file_list() {
  if check_command shasum; then
    tr '\n' '\0' | xargs -0 shasum -a 256 2>/dev/null | shasum -a 256 2>/dev/null | awk '{print $1}'
  elif check_command md5sum; then
    tr '\n' '\0' | xargs -0 md5sum 2>/dev/null | md5sum 2>/dev/null | awk '{print $1}'
  elif check_command md5; then
    tr '\n' '\0' | xargs -0 md5 2>/dev/null | md5 -q 2>/dev/null
  else
    echo "nohash"
  fi
}

# ── Find Python 3.10+ ─────────────────────────────────────────────────────────
find_python() {
  for cmd in python3.12 python3.11 python3.10 python3; do
    if check_command "$cmd"; then
      version=$("$cmd" -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')" 2>/dev/null)
      major=$(echo "$version" | cut -d. -f1)
      minor=$(echo "$version" | cut -d. -f2)
      if [ "$major" -ge 3 ] && [ "$minor" -ge 10 ]; then
        echo "$cmd"
        return 0
      fi
    fi
  done
  return 1
}

resolve_venv_bins() {
  if [ -x ".venv/bin/python" ]; then
    VENV_DIR=".venv"
  elif [ -x "venv/bin/python" ]; then
    VENV_DIR="venv"
  elif [ -d ".venv" ]; then
    VENV_DIR=".venv"
  else
    VENV_DIR="venv"
  fi
  PY_BIN="$VENV_DIR/bin/python"
  PIP_BIN="$VENV_DIR/bin/pip"
}

get_demo_password() {
  local pwd
  pwd=$(grep -E '^DEFAULT_USER_PASSWORD=' .env 2>/dev/null | tail -1 | cut -d'=' -f2-)
  if [ -z "$pwd" ]; then
    pwd="clarive2024!"
  fi
  echo "$pwd"
}

preflight_start_checks() {
  section "Preflight"

  if [[ "$OSTYPE" == "darwin"* ]]; then
    if ! check_command brew; then
      warn "Homebrew no detectado en PATH."
      warn "Se intentara instalar automaticamente cuando sea necesario."
      warn "Si falla, instala Homebrew manualmente: https://brew.sh"
    else
      log "Homebrew detectado"
    fi
  fi

  if ! check_command node; then
    warn "Node.js no detectado en PATH. Se instalara automaticamente para el frontend."
  else
    log "Node.js detectado: $(node --version)"
  fi

  if ! check_command lsof; then
    warn "lsof no detectado. No se podran liberar puertos automaticamente."
  fi
}

# ── Install Homebrew if missing (macOS only) ──────────────────────────────────
install_homebrew() {
  if ! check_command brew; then
    warn "Homebrew no encontrado. Instalando..."
    /bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"
    # Add to PATH for Apple Silicon
    if [ -f "/opt/homebrew/bin/brew" ]; then
      eval "$(/opt/homebrew/bin/brew shellenv)"
    fi
  fi
}

# ── Install Python ────────────────────────────────────────────────────────────
install_python() {
  section "Instalando Python 3.12"
  if [[ "$OSTYPE" == "darwin"* ]]; then
    install_homebrew
    brew install python@3.12
    brew link python@3.12 --force 2>/dev/null || true
  else
    # Linux
    if check_command apt-get; then
      sudo apt-get update -qq
      sudo apt-get install -y python3.12 python3.12-venv python3.12-dev
    elif check_command dnf; then
      sudo dnf install -y python3.12
    else
      error "No se pudo instalar Python automáticamente. Instálalo manualmente desde https://python.org"
      exit 1
    fi
  fi
}

# ── Install Node.js ───────────────────────────────────────────────────────────
install_node() {
  section "Instalando Node.js"
  if [[ "$OSTYPE" == "darwin"* ]]; then
    install_homebrew
    brew install node
  else
    curl -fsSL https://deb.nodesource.com/setup_lts.x | sudo -E bash -
    sudo apt-get install -y nodejs
  fi
}

# ── Setup backend ─────────────────────────────────────────────────────────────
setup_backend() {
  section "Configurando backend"
  cd "$SCRIPT_DIR"

  PYTHON=$(find_python) || { install_python; PYTHON=$(find_python) || { error "Python no disponible"; exit 1; }; }
  log "Usando Python: $PYTHON ($($PYTHON --version))"

  resolve_venv_bins

  # Create venv if not exists
  if [ ! -x "$PY_BIN" ]; then
    log "Creando entorno virtual..."
    $PYTHON -m venv "$VENV_DIR"
  fi

  # Solo instalar si requirements.txt cambió o venv está recién creado
  REQ_HASH_FILE="$VENV_DIR/.req_hash"
  REQ_HASH=$(hash_file requirements.txt)
  if [ ! -f "$REQ_HASH_FILE" ] || [ "$(cat $REQ_HASH_FILE)" != "$REQ_HASH" ]; then
    log "Instalando dependencias Python..."
    "$PIP_BIN" install --quiet --upgrade pip
    "$PIP_BIN" install --quiet -r requirements.txt
    echo "$REQ_HASH" > "$REQ_HASH_FILE"
  else
    log "Dependencias Python sin cambios, omitiendo pip install"
  fi

  # Create .env if not exists
  if [ ! -f ".env" ]; then
    log "Creando archivo .env..."
    if ! cp .env.example .env 2>/dev/null; then
      PORTAL_SECRET=$($PYTHON -c "import secrets; print(secrets.token_hex(32))" 2>/dev/null || openssl rand -hex 32 2>/dev/null || echo "REPLACE_ME_$(date +%s)")
      GEN_SECRET_KEY=$($PYTHON -c "import secrets; print(secrets.token_hex(32))" 2>/dev/null || openssl rand -hex 32 2>/dev/null || echo "REPLACE_ME_$(date +%s)")
      cat > .env << ENVEOF
DATABASE_URL=sqlite:///./clarive.db
SECRET_KEY=${GEN_SECRET_KEY}
CLIENT_PORTAL_SECRET=${PORTAL_SECRET}
ACCESS_TOKEN_EXPIRE_MINUTES=60
REFRESH_TOKEN_EXPIRE_DAYS=30
ALLOWED_ORIGINS=["http://localhost:3000","http://localhost:5173","http://localhost:8000"]
SUPERADMIN_EMAIL=admin@company.com
SUPERADMIN_PASSWORD=clarive2024!
DEFAULT_USER_PASSWORD=clarive2024!
ANTHROPIC_API_KEY=
NEXUS_AI_MODEL=claude-haiku-4-5
ENVEOF
    fi
  fi

  # Patch existing .env: ensure required variables are present
  for REQUIRED_VAR in CLIENT_PORTAL_SECRET SECRET_KEY SUPERADMIN_EMAIL SUPERADMIN_PASSWORD DEFAULT_USER_PASSWORD; do
    if ! grep -q "^${REQUIRED_VAR}=" .env 2>/dev/null; then
      warn "${REQUIRED_VAR} no encontrado en .env — añadiendo valor por defecto"
      case "$REQUIRED_VAR" in
        CLIENT_PORTAL_SECRET)
          VAL=$($PYTHON -c "import secrets; print(secrets.token_hex(32))" 2>/dev/null || echo "clarive-portal-secret-change-in-production!!")
          ;;
        SECRET_KEY)
          VAL=$($PYTHON -c "import secrets; print(secrets.token_hex(32))" 2>/dev/null || openssl rand -hex 32 2>/dev/null || echo "REPLACE_ME_CHANGE_THIS_NOW")
          ;;
        SUPERADMIN_EMAIL)
          VAL="admin@company.com"
          ;;
        SUPERADMIN_PASSWORD)
          VAL="clarive2024!"
          ;;
        DEFAULT_USER_PASSWORD)
          VAL="clarive2024!"
          ;;
      esac
      echo "${REQUIRED_VAR}=${VAL}" >> .env
    fi
  done

  # Solo migrar si la BD no existe o los modelos cambiaron
  MODELS_HASH_FILE="$VENV_DIR/.models_hash"
  MODELS_HASH=$(find app/models -type f -name "*.py" 2>/dev/null | sort | hash_file_list)
  if [ ! -f "clarive.db" ] || [ ! -f "$MODELS_HASH_FILE" ] || [ "$(cat $MODELS_HASH_FILE)" != "$MODELS_HASH" ]; then
    log "Aplicando migraciones de base de datos..."
    "$PY_BIN" -m app.db.migrate
    echo "$MODELS_HASH" > "$MODELS_HASH_FILE"
  else
    log "Modelos sin cambios, omitiendo migración"
  fi

  # Check if DB has valid users with passwords
  DB_OK=$("$PY_BIN" -c "
from app.db.session import SessionLocal
from app.models.user import User
try:
    db = SessionLocal()
    count = db.query(User).filter(User.hashed_password != None).count()
    db.close()
    print('ok' if count > 0 else 'empty')
except:
    print('error')
" 2>/dev/null || echo "error")

  if [ "$DB_OK" != "ok" ]; then
    log "Inicializando base de datos..."
    rm -f clarive.db
    "$PY_BIN" -m app.db.migrate
    "$PY_BIN" -m app.db.seed
  else
    log "Base de datos OK"
  fi

  # Keep demo users aligned with DEFAULT_USER_PASSWORD in .env
  sync_demo_passwords
}

# ── Setup frontend ────────────────────────────────────────────────────────────
setup_frontend() {
  section "Configurando frontend"
  cd "$SCRIPT_DIR/frontend"

  if ! check_command node; then
    install_node
  fi

  NODE_VER=$(node --version | cut -d. -f1 | tr -d 'v')
  if [ "$NODE_VER" -lt 18 ]; then
    warn "Node.js $NODE_VER detectado. Se recomienda v18+."
    install_node
  fi

  log "Node.js $(node --version) · npm $(npm --version)"

  PKG_HASH_FILE="node_modules/.pkg_hash"
  PKG_HASH=$(hash_file package.json)
  NEED_NPM_INSTALL=0
  # Si falta node_modules, el hash, o cambió package.json
  if [ ! -d "node_modules" ] || [ ! -f "$PKG_HASH_FILE" ] || [ "$(cat $PKG_HASH_FILE)" != "$PKG_HASH" ]; then
    NEED_NPM_INSTALL=1
  fi
  # Si falta el binario de vite, forzar npm install
  if [ ! -f "node_modules/vite/dist/node/cli.js" ]; then
    warn "Vite no encontrado en node_modules. Ejecutando npm install..."
    NEED_NPM_INSTALL=1
  fi
  if [ $NEED_NPM_INSTALL -eq 1 ]; then
    log "Instalando dependencias npm (puede tardar unos minutos en la primera ejecución)..."
    if ! npm install --no-fund --no-audit --prefer-offline --legacy-peer-deps; then
      error "npm install falló. Revisa los logs y ejecuta frontend/npm install manualmente."
      exit 1
    fi
    echo "$PKG_HASH" > "$PKG_HASH_FILE"
  else
    log "Dependencias npm sin cambios, omitiendo npm install"
  fi

  cd "$SCRIPT_DIR"
}

# ── Sync demo user passwords to match current DEFAULT_USER_PASSWORD ──────────
sync_demo_passwords() {
  cd "$SCRIPT_DIR"
  resolve_venv_bins

  DEMO_PWD=$(get_demo_password)
  # Use a hash of the password as a change-detection sentinel
  if check_command shasum; then
    PWD_HASH=$(echo -n "$DEMO_PWD" | shasum -a 256 | awk '{print $1}')
  else
    PWD_HASH=$(echo -n "$DEMO_PWD" | md5sum 2>/dev/null | awk '{print $1}' || echo "nocheck")
  fi
  PWD_HASH_FILE="$VENV_DIR/.pwd_hash"

  if [ -f "$PWD_HASH_FILE" ] && [ "$(cat $PWD_HASH_FILE)" = "$PWD_HASH" ]; then
    log "Contraseñas demo sin cambios, omitiendo rehash"
    return 0
  fi

  log "Sincronizando contraseñas demo con DEFAULT_USER_PASSWORD..."
  SYNC_RESULT=$("$PY_BIN" -c "
import sys
from app.db.session import SessionLocal
from app.models.user import User
from app.core.security import get_password_hash

pwd = '''$DEMO_PWD'''
db = SessionLocal()
updated = 0
for username in ['admin', 'ana.torres', 'luis.vega', 'rrhh']:
    user = db.query(User).filter(User.username == username).first()
    if user:
        user.hashed_password = get_password_hash(pwd)
        updated += 1
db.commit()
db.close()
print('ok:' + str(updated))
" 2>&1)
  if echo "$SYNC_RESULT" | grep -q '^ok:'; then
    UPDATED=$(echo "$SYNC_RESULT" | grep -o '[0-9]*$')
    log "Contraseñas actualizadas para $UPDATED usuario(s) demo"
    echo "$PWD_HASH" > "$PWD_HASH_FILE"
  else
    warn "No se pudieron sincronizar las contraseñas demo: $SYNC_RESULT"
  fi
}

# ── Start services ────────────────────────────────────────────────────────────
start_services() {
  section "Arrancando Clarive"
  cd "$SCRIPT_DIR"
  resolve_venv_bins
  preflight_start_checks

  if [ ! -x "$PY_BIN" ]; then
    warn "Entorno virtual no encontrado. Inicializando backend automáticamente..."
    setup_backend
    resolve_venv_bins
  fi

  if [ ! -d "$SCRIPT_DIR/frontend/node_modules" ] || [ ! -f "$SCRIPT_DIR/frontend/node_modules/vite/dist/node/cli.js" ]; then
    warn "Frontend no preparado. Inicializando frontend automáticamente..."
    setup_frontend
  fi

  # Always sync demo passwords before starting — ensures hash matches .env even on 'start'
  sync_demo_passwords

  # Kill any existing processes on our ports
  lsof -ti:$BACKEND_PORT | xargs kill -9 2>/dev/null || true
  lsof -ti:$FRONTEND_PORT | xargs kill -9 2>/dev/null || true
  sleep 1

  log "Arrancando backend en puerto $BACKEND_PORT..."
  "$PY_BIN" -m uvicorn app.main:app \
    --host 0.0.0.0 \
    --port $BACKEND_PORT \
    --log-level info \
    --workers 1 \
    > /tmp/clarive-backend.log 2>&1 &
  BACKEND_PID=$!

  # Wait for backend to be ready
  echo -n "  Esperando backend"
  BACKEND_READY=0
  for i in $(seq 1 60); do
    if curl -s http://localhost:$BACKEND_PORT/health > /dev/null 2>&1; then
      echo " ✓ (${i}s)"
      BACKEND_READY=1
      break
    fi
    # Verificar que el proceso sigue vivo
    if ! kill -0 $BACKEND_PID 2>/dev/null; then
      echo ""
      echo -e "${RED}❌ El proceso backend murió inesperadamente.${NC}"
      echo "   Últimas líneas del log:"
      tail -20 /tmp/clarive-backend.log
      exit 1
    fi
    if [ $((i % 10)) -eq 0 ]; then
      echo -n " ${i}s"
    else
      echo -n "."
    fi
    sleep 1
  done
  if [ $BACKEND_READY -eq 0 ]; then
    echo ""
    echo -e "${RED}❌ El backend no respondió en 60 segundos.${NC}"
    echo "   Revisando logs..."
    tail -20 /tmp/clarive-backend.log
    echo ""
    echo -e "${YELLOW}⚠ Posibles causas:${NC}"
    echo "   1. El puerto $BACKEND_PORT ya está en uso (ejecuta: lsof -i :$BACKEND_PORT)"
    echo "   2. Error en Python — revisa: cat /tmp/clarive-backend.log"
    echo "   3. Falta instalar dependencias — ejecuta: cd venv && pip install -r ../requirements.txt"
    exit 1
  fi

  # Solo limpiar caché de Vite si los modelos del frontend cambiaron
  mkdir -p frontend/node_modules
  VITE_HASH_FILE="frontend/node_modules/.vite_src_hash"
  VITE_HASH=$(find frontend/src -type f \( -name "*.jsx" -o -name "*.js" \) 2>/dev/null | sort | hash_file_list)
  if [ ! -f "$VITE_HASH_FILE" ] || [ "$(cat $VITE_HASH_FILE)" != "$VITE_HASH" ]; then
    rm -rf frontend/node_modules/.vite 2>/dev/null || true
    echo "$VITE_HASH" > "$VITE_HASH_FILE"
  fi
  # Validar JSX solo si el código cambió (evita ~5s en cada arranque)
  JSX_HASH_FILE="frontend/node_modules/.jsx_hash"
  JSX_HASH=$(find frontend/src -type f -name "*.jsx" 2>/dev/null | sort | hash_file_list)
  if [ -f "frontend/node_modules/@babel/parser/lib/index.js" ]; then
    if [ ! -f "$JSX_HASH_FILE" ] || [ "$(cat $JSX_HASH_FILE)" != "$JSX_HASH" ]; then
      log "Validando JSX con Babel..."
      if node frontend/validate.cjs; then
        echo -e "${GREEN}✅ JSX validado correctamente${NC}"
        echo "$JSX_HASH" > "$JSX_HASH_FILE"
      else
        echo -e "${RED}❌ Errores en JSX detectados — revisa los archivos marcados${NC}"
        exit 1
      fi
    else
      log "JSX sin cambios, omitiendo validación Babel"
    fi
  fi

    log "Arrancando frontend en puerto $FRONTEND_PORT..."
  cd frontend
  npm run dev -- --port $FRONTEND_PORT > /tmp/clarive-frontend.log 2>&1 &
  FRONTEND_PID=$!
  cd "$SCRIPT_DIR"

  # Wait for frontend
  echo -n "  Esperando frontend"
  for i in $(seq 1 20); do
    if curl -s http://localhost:$FRONTEND_PORT > /dev/null 2>&1; then
      echo " ✓"
      break
    fi
    echo -n "."
    sleep 1
  done

  # Save PIDs
  echo "$BACKEND_PID" > /tmp/clarive-backend.pid
  echo "$FRONTEND_PID" > /tmp/clarive-frontend.pid

  echo ""
  echo -e "${GREEN}${BOLD}╔══════════════════════════════════════════╗${NC}"
  echo -e "${GREEN}${BOLD}║         Clarive listo ✓                  ║${NC}"
  echo -e "${GREEN}${BOLD}╚══════════════════════════════════════════╝${NC}"
  echo ""
  echo -e "  🌐 App:      ${BOLD}http://localhost:$FRONTEND_PORT${NC}"
  echo -e "  📡 API:      http://localhost:$BACKEND_PORT/api/v1/docs"
  echo -e "  📋 Logs:     /tmp/clarive-backend.log"
  echo ""
  DEMO_PASSWORD=$(get_demo_password)
  echo -e "  ${BOLD}Usuarios de prueba:${NC}"
  echo -e "  admin      / ${DEMO_PASSWORD}  → Dirección"
  echo -e "  ana.torres / ${DEMO_PASSWORD}  → PM"
  echo -e "  luis.vega  / ${DEMO_PASSWORD}  → Empleado"
  echo -e "  rrhh       / ${DEMO_PASSWORD}  → RRHH"
  echo ""
  echo -e "  ${YELLOW}Presiona Ctrl+C para parar${NC}"
  echo ""

  # Open browser automatically
  if [[ "$OSTYPE" == "darwin"* ]]; then
    sleep 2 && open "http://localhost:$FRONTEND_PORT" &
  elif check_command xdg-open; then
    sleep 2 && xdg-open "http://localhost:$FRONTEND_PORT" &
  fi

  # Wait and stream logs
  trap "echo ''; log 'Parando Clarive...'; kill $BACKEND_PID $FRONTEND_PID 2>/dev/null; exit 0" INT TERM
  wait $BACKEND_PID $FRONTEND_PID
}

# ── Stop services ─────────────────────────────────────────────────────────────
stop_services() {
  log "Parando Clarive..."
  [ -f /tmp/clarive-backend.pid ]  && kill $(cat /tmp/clarive-backend.pid)  2>/dev/null || true
  [ -f /tmp/clarive-frontend.pid ] && kill $(cat /tmp/clarive-frontend.pid) 2>/dev/null || true
  lsof -ti:$BACKEND_PORT  | xargs kill -9 2>/dev/null || true
  lsof -ti:$FRONTEND_PORT | xargs kill -9 2>/dev/null || true
  log "Parado"
}

# ── Main ──────────────────────────────────────────────────────────────────────
print_banner

case "${1:-}" in
  start)
    log "Modo: solo arrancar"
    start_services
    ;;
  stop)
    stop_services
    ;;
  update)
    log "Modo: actualizar"
    setup_backend
    setup_frontend
    log "Actualización completada. Ejecuta ./setup.sh start para arrancar."
    ;;
  *)
    log "Modo: instalación completa"
    setup_backend
    setup_frontend
    start_services
    ;;
esac
