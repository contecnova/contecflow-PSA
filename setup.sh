#!/bin/bash

# ============================================================
#  Contecflow — Script de instalación y arranque
#  Compatible: macOS y Linux
#  Uso:
#    ./setup.sh demo     → instala/actualiza y arranca con datos demo
#    ./setup.sh clean    → instala/actualiza y arranca con BD vacía salvo admin
#    ./setup.sh start    → solo arranca, preservando la BD existente
#    ./setup.sh stop     → para servicios
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
USE_DOCKER=0  # Set to 1 if Docker infra is successfully started

print_banner() {
  echo ""
  echo -e "${CYAN}${BOLD}"
  echo ""
  echo -e "  ${CYAN}╔══════════════════════════════════════════╗${NC}"
  echo -e "  ${CYAN}║                                          ║${NC}"
  echo -e "  ${CYAN}║   ◈  CONTECFLOW                             ║${NC}"
  echo -e "  ${CYAN}║   Professional Services Automation       ║${NC}"
  echo -e "  ${CYAN}║                                          ║${NC}"
  echo -e "  ${CYAN}╚══════════════════════════════════════════╝${NC}"
  echo -e "  Plataforma PSA Enterprise${NC}"
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
  # Try Linux/macOS structure first
  if [ -x ".venv/bin/python" ]; then
    VENV_DIR=".venv"
    PY_BIN="$VENV_DIR/bin/python"
    PIP_BIN="$VENV_DIR/bin/pip"
  elif [ -x "venv/bin/python" ]; then
    VENV_DIR="venv"
    PY_BIN="$VENV_DIR/bin/python"
    PIP_BIN="$VENV_DIR/bin/pip"
  # Fallback to Windows structure (Git Bash on Windows)
  elif [ -f ".venv/Scripts/python.exe" ]; then
    VENV_DIR=".venv"
    PY_BIN="$VENV_DIR/Scripts/python.exe"
    PIP_BIN="$VENV_DIR/Scripts/pip.exe"
  elif [ -f "venv/Scripts/python.exe" ]; then
    VENV_DIR="venv"
    PY_BIN="$VENV_DIR/Scripts/python.exe"
    PIP_BIN="$VENV_DIR/Scripts/pip.exe"
  # Create default paths (will be created during setup)
  elif [ -d ".venv" ]; then
    VENV_DIR=".venv"
    PY_BIN="$VENV_DIR/bin/python"
    PIP_BIN="$VENV_DIR/bin/pip"
  else
    VENV_DIR="venv"
    PY_BIN="$VENV_DIR/bin/python"
    PIP_BIN="$VENV_DIR/bin/pip"
  fi
}

get_demo_password() {
  # Sin fallback: inventar una contraseña por defecto aquí significaba que un
  # .env sin DEFAULT_USER_PASSWORD acababa con usuarios cuya contraseña estaba
  # escrita en este script. Si no está definida, quien llama debe abortar.
  grep -E '^DEFAULT_USER_PASSWORD=' .env 2>/dev/null | tail -1 | cut -d'=' -f2-
}

# Entorno declarado en .env. Fail-closed: si no se puede determinar, se asume
# "production" para que ninguna operación destructiva se ejecute por descuido.
get_environment() {
  local env_value
  env_value=$(grep -E '^ENVIRONMENT=' .env 2>/dev/null | tail -1 | cut -d'=' -f2- | tr -d '"'"'"' \r')
  if [ -z "$env_value" ]; then
    echo "production"
  else
    echo "$env_value"
  fi
}

# ¿Es seguro ejecutar operaciones que reescriben datos o credenciales?
is_safe_for_destructive_ops() {
  case "$(get_environment)" in
    development|dev|local|test|testing|demo) return 0 ;;
    *) return 1 ;;
  esac
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
    /bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)" || {
      error "No se pudo instalar Homebrew automáticamente."
      echo "Instálalo manualmente desde https://brew.sh"
      return 1
    }
    # Add to PATH for Apple Silicon
    if [ -f "/opt/homebrew/bin/brew" ]; then
      eval "$(/opt/homebrew/bin/brew shellenv)"
    fi
    if ! check_command brew; then
      error "Homebrew sigue sin estar disponible en PATH."
      echo "Abre una nueva terminal o ejecuta: eval \"$('/opt/homebrew/bin/brew' shellenv)\""
      return 1
    fi
  fi
}

# ── Install Python ────────────────────────────────────────────────────────────
install_python() {
  section "Instalando Python 3.12"
  if [[ "$OSTYPE" == "darwin"* ]]; then
    install_homebrew || return 1
    brew install python@3.12 || {
      error "No se pudo instalar Python con Homebrew."
      echo "Instálalo manualmente desde https://www.python.org/downloads/"
      return 1
    }
    brew link python@3.12 --force 2>/dev/null || true
  else
    # Linux
    if check_command apt-get; then
      sudo apt-get update -qq
      if ! sudo apt-get install -y python3.12 python3.12-venv python3.12-dev; then
        warn "No se pudo instalar Python 3.12 desde apt (repos no disponibles). Intentando Python por defecto..."
        sudo apt-get install -y python3 python3-venv python3-dev || {
          error "No se pudo instalar Python con apt-get."
          echo "Prueba manualmente: sudo apt-get install python3 python3-venv python3-dev"
          return 1
        }
      fi
    elif check_command dnf; then
      sudo dnf install -y python3.12 || sudo dnf install -y python3 || {
        error "No se pudo instalar Python con dnf."
        echo "Prueba manualmente: sudo dnf install python3"
        return 1
      }
    elif check_command yum; then
      sudo yum install -y python3 || {
        error "No se pudo instalar Python con yum."
        echo "Prueba manualmente: sudo yum install python3"
        return 1
      }
    elif check_command pacman; then
      sudo pacman -Sy --noconfirm python || {
        error "No se pudo instalar Python con pacman."
        echo "Prueba manualmente: sudo pacman -Sy python"
        return 1
      }
    elif check_command zypper; then
      sudo zypper --non-interactive install python311 python311-pip || sudo zypper --non-interactive install python3 python3-pip || {
        error "No se pudo instalar Python con zypper."
        echo "Prueba manualmente: sudo zypper install python3 python3-pip"
        return 1
      }
    elif check_command apk; then
      sudo apk add --no-cache python3 py3-pip || {
        error "No se pudo instalar Python con apk."
        echo "Prueba manualmente: sudo apk add --no-cache python3 py3-pip"
        return 1
      }
    else
      error "No se pudo instalar Python automáticamente. Instálalo manualmente desde https://python.org"
      return 1
    fi
  fi

  if ! find_python >/dev/null 2>&1; then
    error "La instalación automática terminó pero Python 3.10+ no está disponible en PATH."
    echo "Abre una nueva terminal o instala Python manualmente desde https://www.python.org/downloads/"
    return 1
  fi
}

# ── Install Node.js ───────────────────────────────────────────────────────────
install_node() {
  section "Instalando Node.js"
  if [[ "$OSTYPE" == "darwin"* ]]; then
    install_homebrew || return 1
    brew install node || {
      error "No se pudo instalar Node.js con Homebrew."
      echo "Instálalo manualmente desde https://nodejs.org/"
      return 1
    }
  else
    if check_command apt-get; then
      curl -fsSL https://deb.nodesource.com/setup_lts.x | sudo -E bash - || {
        warn "No se pudo configurar NodeSource. Intentando paquetes del sistema..."
      }
      sudo apt-get install -y nodejs npm || sudo apt-get install -y nodejs || {
        error "No se pudo instalar Node.js con apt-get."
        echo "Prueba manualmente: sudo apt-get install nodejs npm"
        return 1
      }
    elif check_command dnf; then
      sudo dnf install -y nodejs npm || sudo dnf install -y nodejs || {
        error "No se pudo instalar Node.js con dnf."
        echo "Prueba manualmente: sudo dnf install nodejs npm"
        return 1
      }
    elif check_command yum; then
      sudo yum install -y nodejs npm || sudo yum install -y nodejs || {
        error "No se pudo instalar Node.js con yum."
        echo "Prueba manualmente: sudo yum install nodejs npm"
        return 1
      }
    elif check_command pacman; then
      sudo pacman -Sy --noconfirm nodejs npm || {
        error "No se pudo instalar Node.js con pacman."
        echo "Prueba manualmente: sudo pacman -Sy nodejs npm"
        return 1
      }
    elif check_command zypper; then
      sudo zypper --non-interactive install nodejs20 npm20 || sudo zypper --non-interactive install nodejs npm || {
        error "No se pudo instalar Node.js con zypper."
        echo "Prueba manualmente: sudo zypper install nodejs npm"
        return 1
      }
    elif check_command apk; then
      sudo apk add --no-cache nodejs npm || {
        error "No se pudo instalar Node.js con apk."
        echo "Prueba manualmente: sudo apk add --no-cache nodejs npm"
        return 1
      }
    else
      error "No se pudo instalar Node.js automáticamente. Instálalo manualmente desde https://nodejs.org/"
      return 1
    fi
  fi

  if ! check_command node; then
    error "La instalación automática terminó pero node no está disponible en PATH."
    echo "Abre una nueva terminal o instala Node.js manualmente desde https://nodejs.org/"
    return 1
  fi
  if ! check_command npm; then
    warn "Node.js está instalado pero npm no está disponible en PATH."
    warn "Instala npm manualmente desde el gestor de paquetes de tu distribución."
  fi
}

# ── Docker infrastructure (Postgres + Redis) ──────────────────────────────────
docker_compose_cmd() {
  # Supports both 'docker compose' (plugin v2) and 'docker-compose' (standalone v1).
  if docker compose version > /dev/null 2>&1; then
    docker compose "$@"
  else
    docker-compose "$@"
  fi
}

# Enciende el daemon de Docker si está apagado (Docker Desktop, OrbStack, Colima, systemd) y espera a que responda.
docker_daemon_arrancar() {
  docker info >/dev/null 2>&1 && return 0
  command -v docker >/dev/null 2>&1 || return 1
  echo "  ! El daemon de Docker no responde; intentando arrancarlo..." >&2
  case "$(uname -s)" in
    Darwin)
      if [[ -d /Applications/Docker.app || -d "$HOME/Applications/Docker.app" ]]; then open -ga Docker
      elif [[ -d /Applications/OrbStack.app ]]; then open -ga OrbStack
      elif command -v colima >/dev/null 2>&1; then colima start
      fi ;;
    Linux)
      command -v systemctl >/dev/null 2>&1 && { systemctl start docker 2>/dev/null || sudo systemctl start docker; } ;;
  esac
  local esperado=0
  while ! docker info >/dev/null 2>&1; do
    (( esperado >= 180 )) && return 1
    sleep 3; esperado=$((esperado + 3))
  done
}

detect_docker() {
  # Returns 0 (true) if Docker daemon is running and compose is available.
  check_command docker && docker_daemon_arrancar && \
    (docker compose version > /dev/null 2>&1 || check_command docker-compose)
}

patch_env_for_docker() {
  # Updates DATABASE_URL / REDIS_URL in .env to point to Docker containers.
  # Also writes explicit POSTGRES_* credentials so Docker Compose and
  # DATABASE_URL always use the same value.
  # Treats placeholder values (CHANGE_ME / REPLACE_ME) as unset.
  cd "$SCRIPT_DIR"
  "$PYTHON" - <<'PY'
from pathlib import Path
import os

PLACEHOLDER_PREFIXES = ('CHANGE_ME', 'REPLACE_ME', 'TODO', 'PLACEHOLDER', 'YOUR_')

def is_placeholder(value):
    if not value:
        return True
    return any(value.upper().startswith(p) for p in PLACEHOLDER_PREFIXES)

env_path = Path('.env')
if not env_path.exists():
    raise SystemExit(0)

lines = env_path.read_text(encoding='utf-8').splitlines()

def get_var(name):
    for line in lines:
        if line.startswith(f'{name}='):
            return line.split('=', 1)[1]
    return ''

def set_var(name, value):
    for idx, line in enumerate(lines):
        if line.startswith(f'{name}='):
            lines[idx] = f'{name}={value}'
            return
    lines.append(f'{name}={value}')

# Resolve credentials — ignore placeholder values, fall back to safe dev defaults.
pg_pass_raw = get_var('POSTGRES_PASSWORD')
pg_pass = pg_pass_raw if not is_placeholder(pg_pass_raw) else 'contecflow_dev'

pg_user_raw = get_var('POSTGRES_USER')
pg_user = pg_user_raw if not is_placeholder(pg_user_raw) else 'contecflow'

pg_db_raw = get_var('POSTGRES_DB')
pg_db = pg_db_raw if not is_placeholder(pg_db_raw) else 'contecflow'

# Ports — Contecflow uses 5434/6381 to avoid clashes with Contecmind (5432/6379).
pg_port  = os.environ.get('CF_POSTGRES_PORT', '5434')
red_port = os.environ.get('CF_REDIS_PORT', '6381')

# Write canonical credential values so Docker Compose and DATABASE_URL agree.
set_var('POSTGRES_USER', pg_user)
set_var('POSTGRES_PASSWORD', pg_pass)
set_var('POSTGRES_DB', pg_db)

db_url = get_var('DATABASE_URL')
if not db_url or 'sqlite' in db_url.lower() or is_placeholder(db_url):
    set_var('DATABASE_URL', f'postgresql+psycopg2://{pg_user}:{pg_pass}@127.0.0.1:{pg_port}/{pg_db}')
    set_var('REDIS_URL', f'redis://127.0.0.1:{red_port}/0')
    env_path.write_text('\n'.join(lines) + '\n', encoding='utf-8')
    print('PATCHED')
else:
    env_path.write_text('\n'.join(lines) + '\n', encoding='utf-8')
    print('SKIP')
PY
}

revert_env_to_sqlite() {
  # Reverts DATABASE_URL / REDIS_URL back to SQLite/local when Docker fails.
  # Only reverts if the URL was pointing to 127.0.0.1 (i.e. was set by us).
  cd "$SCRIPT_DIR"
  "$PYTHON" - <<'PY'
from pathlib import Path

env_path = Path('.env')
if not env_path.exists():
    raise SystemExit(0)

lines = env_path.read_text(encoding='utf-8').splitlines()

def get_var(name):
    for line in lines:
        if line.startswith(f'{name}='):
            return line.split('=', 1)[1]
    return ''

def set_var(name, value):
    for idx, line in enumerate(lines):
        if line.startswith(f'{name}='):
            lines[idx] = f'{name}={value}'
            return
    lines.append(f'{name}={value}')

db_url = get_var('DATABASE_URL')
# Only revert if we set it (local Docker URL contains 127.0.0.1 and postgresql)
if db_url and '127.0.0.1' in db_url and 'postgresql' in db_url.lower():
    set_var('DATABASE_URL', 'sqlite:///./contecflow.db')
    redis_url = get_var('REDIS_URL')
    if redis_url and '127.0.0.1' in redis_url:
        set_var('REDIS_URL', 'redis://127.0.0.1:6379/0')
    env_path.write_text('\n'.join(lines) + '\n', encoding='utf-8')
    print('REVERTED')
else:
    print('SKIP')
PY
}

# ── Credenciales y volúmenes del stack Docker ─────────────────────────────────
# Patrón tomado de contecmind y contecweb. El compose declara sus variables
# obligatorias con `${VAR:?}`, así que si falta alguna `up` falla al arrancar en
# vez de caer a un valor por defecto silencioso. Estas funciones se aseguran de
# que existan, generando los secretos UNA VEZ y persistiéndolos en .env.
generate_local_secret() {
  "$PY_BIN" -c "import secrets; print(secrets.token_urlsafe(24))" 2>/dev/null \
    || openssl rand -base64 24 2>/dev/null \
    || date +%s%N | sha256sum | cut -c1-32
}

env_read() {
  grep -E "^$1=" .env 2>/dev/null | tail -1 | cut -d= -f2-
}

env_upsert() {
  local key="$1" value="$2"
  if grep -qE "^${key}=" .env 2>/dev/null; then
    "$PY_BIN" - "$key" "$value" <<'PYEOF'
import pathlib, sys
key, value = sys.argv[1], sys.argv[2]
p = pathlib.Path('.env')
lines = p.read_text(encoding='utf-8').splitlines()
for i, l in enumerate(lines):
    if l.startswith(key + '='):
        lines[i] = f'{key}={value}'
        break
p.write_text('\n'.join(lines) + '\n', encoding='utf-8')
PYEOF
  else
    printf '%s=%s\n' "$key" "$value" >> .env
  fi
}

# Volúmenes con datos irremplazables. Están `external: true` en el compose para
# que `docker compose down -v` NO pueda borrarlos (la lección del incidente de
# contecmind: un `down -v` recreó los volúmenes y se perdió todo). El coste es
# que compose ya no los crea, así que `up` fallaría con "external volume not
# found" en una máquina nueva. Aquí se crean de forma idempotente: se obtiene la
# protección sin fricción de arranque.
CONTECFLOW_PERSISTENT_VOLUMES=(
  contecflow_postgres_data
  contecflow_s3_data
)
ensure_persistent_volumes() {
  local creados=0 v
  for v in "${CONTECFLOW_PERSISTENT_VOLUMES[@]}"; do
    if ! docker volume inspect "$v" >/dev/null 2>&1; then
      docker volume create "$v" >/dev/null && creados=1
      log "Volumen persistente creado: $v"
    fi
  done
  if [ "$creados" -eq 0 ]; then
    log "Volúmenes persistentes ya presentes (protegidos de 'down -v') ✓"
  fi
}

# Si ya existe un volumen de datos, un secreto NUEVO no coincidiría con el que
# se usó al inicializarlo y el servicio rechazaría la autenticación. En ese caso
# se conserva el valor histórico de desarrollo en lugar de generar otro.
ensure_compose_required_env() {
  cd "$SCRIPT_DIR"
  [ -f .env ] || touch .env

  local key actual

  # No secretas: valor local determinista.
  for key in POSTGRES_USER POSTGRES_DB MINIO_ROOT_USER; do
    actual="$(env_read "$key")"
    if [ -z "$actual" ]; then
      actual="contecflow"
      env_upsert "$key" "$actual"
      warn "${key} no estaba definida; se fijó '${actual}' en .env"
    fi
    export "$key=$actual"
  done

  # Secretas: se generan una vez y se persisten.
  for key in POSTGRES_PASSWORD MINIO_ROOT_PASSWORD; do
    actual="$(env_read "$key")"
    if [ -z "$actual" ]; then
      if [ "$key" = "POSTGRES_PASSWORD" ] && docker volume inspect contecflow_postgres_data >/dev/null 2>&1; then
        actual="contecflow_dev"
        env_upsert "$key" "$actual"
        warn "${key} faltaba con el volumen de Postgres ya creado; se aplicó el valor local histórico para no romper la autenticación"
      elif [ "$key" = "MINIO_ROOT_PASSWORD" ] && docker volume inspect contecflow_s3_data >/dev/null 2>&1; then
        actual="contecflow_dev"
        env_upsert "$key" "$actual"
        warn "${key} faltaba con el volumen del almacén S3 ya creado; se aplicó el valor local histórico"
      else
        actual="$(generate_local_secret)"
        env_upsert "$key" "$actual"
        warn "${key} no estaba definida; se generó automáticamente y se guardó en .env"
      fi
    fi
    export "$key=$actual"
  done

  # ENVIRONMENT gobierna el gate de operaciones destructivas.
  if [ -z "$(env_read ENVIRONMENT)" ]; then
    env_upsert ENVIRONMENT development
  fi
}

setup_docker_infra() {
  section "Infraestructura Docker (Postgres + Redis)"
  cd "$SCRIPT_DIR"

  if ! detect_docker; then
    warn "Docker no disponible o no está ejecutándose — usando SQLite como fallback."
    revert_env_to_sqlite
    USE_DOCKER=0
    return 0
  fi

  if [ ! -f "$SCRIPT_DIR/docker-compose.yml" ]; then
    warn "docker-compose.yml no encontrado — usando SQLite como fallback."
    revert_env_to_sqlite
    USE_DOCKER=0
    return 0
  fi

  # El compose exige estas variables con `${VAR:?}`: sin ellas `up` aborta.
  ensure_compose_required_env
  ensure_persistent_volumes

  log "Docker detectado. Levantando la infraestructura (Postgres + Redis)..."
  # El almacén S3 (versitygw) va bajo perfil: en desarrollo la app guarda en
  # `uploads/` y no lo usa. Se levanta con `docker compose --profile s3 up -d`.
  if ! docker_compose_cmd up -d --remove-orphans; then
    warn "No se pudo levantar la infraestructura Docker — usando SQLite como fallback."
    revert_env_to_sqlite
    USE_DOCKER=0
    return 0
  fi

  # Wait for Postgres to be ready
  echo -n "  Esperando Postgres"
  PG_READY=0
  for i in $(seq 1 30); do
    if docker_compose_cmd exec -T postgres \
        pg_isready -U "${POSTGRES_USER:-contecflow}" > /dev/null 2>&1; then
      echo " ✓ (${i}s)"
      PG_READY=1
      break
    fi
    echo -n "."
    sleep 1
  done
  if [ $PG_READY -eq 0 ]; then
    echo ""
    warn "Postgres no respondió en 30s — usando SQLite como fallback."
    revert_env_to_sqlite
    USE_DOCKER=0
    return 0
  fi

  # Wait for Redis to be ready
  echo -n "  Esperando Redis"
  for i in $(seq 1 15); do
    if docker_compose_cmd exec -T redis \
        redis-cli ping > /dev/null 2>&1; then
      echo " ✓"
      break
    fi
    echo -n "."
    sleep 1
  done

  USE_DOCKER=1
  log "Postgres (127.0.0.1:5434) y Redis (127.0.0.1:6381) listos"

  # Patch .env to use Docker service URLs (only if .env is still using SQLite)
  PATCH_RESULT=$(patch_env_for_docker)
  if [ "$PATCH_RESULT" = "PATCHED" ]; then
    log ".env actualizado: DATABASE_URL → PostgreSQL  |  REDIS_URL → Redis"
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
  if [ ! -f "$PY_BIN" ]; then
    log "Creando entorno virtual..."
    $PYTHON -m venv "$VENV_DIR"
    # Re-resolve paths after venv creation in case structure changed
    resolve_venv_bins
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

  # Stack ML (semantic transformer): instalar si requirements-ml.txt existe.
  if [ -f "requirements-ml.txt" ]; then
    REQ_ML_HASH_FILE="$VENV_DIR/.req_ml_hash"
    REQ_ML_HASH=$(hash_file requirements-ml.txt)
    if [ ! -f "$REQ_ML_HASH_FILE" ] || [ "$(cat $REQ_ML_HASH_FILE)" != "$REQ_ML_HASH" ]; then
      log "Instalando dependencias ML (requirements-ml.txt)..."
      "$PIP_BIN" install --quiet -r requirements-ml.txt
      echo "$REQ_ML_HASH" > "$REQ_ML_HASH_FILE"
    else
      log "Dependencias ML sin cambios, omitiendo pip install"
    fi
  fi

  # Dependencias opcionales: CMDB auto-discovery (boto3=AWS, kubernetes=K8s)
  # Se instalan solo si el archivo requirements-discovery.txt existe O si se detectan
  # variables de entorno de proveedor cloud configuradas.
  if [ -f "requirements-discovery.txt" ]; then
    log "Instalando dependencias opcionales de CMDB discovery..."
    "$PIP_BIN" install --quiet -r requirements-discovery.txt || \
      warn "Algunas dependencias opcionales de discovery no se pudieron instalar (no es bloqueante)"
  else
    # Instalar solo si las vars de entorno AWS/K8s están configuradas
    if grep -qE '^AWS_ACCESS_KEY_ID=.+' .env 2>/dev/null; then
      log "AWS configurado — instalando boto3..."
      "$PIP_BIN" install --quiet boto3 || warn "No se pudo instalar boto3"
    fi
    if grep -qE '^KUBECONFIG=.+|^K8S_IN_CLUSTER=true' .env 2>/dev/null; then
      log "Kubernetes configurado — instalando kubernetes client..."
      "$PIP_BIN" install --quiet kubernetes || warn "No se pudo instalar kubernetes client"
    fi
  fi

  # ── Infraestructura Docker (Postgres + Redis) ─────────────────────────────────────────
  # Se llama antes de crear .env para que patch_env_for_docker pueda parchear
  # DATABASE_URL y REDIS_URL justo después si Docker está disponible.
  setup_docker_infra

  # Create .env if not exists
  if [ ! -f ".env" ]; then
    log "Creando archivo .env..."
    if ! cp .env.example .env 2>/dev/null; then
      PORTAL_SECRET=$($PYTHON -c "import secrets; print(secrets.token_hex(32))" 2>/dev/null || openssl rand -hex 32 2>/dev/null || echo "REPLACE_ME_$(date +%s)")
      GEN_SECRET_KEY=$($PYTHON -c "import secrets; print(secrets.token_hex(32))" 2>/dev/null || openssl rand -hex 32 2>/dev/null || echo "REPLACE_ME_$(date +%s)")
      cat > .env << ENVEOF
DATABASE_URL=sqlite:///./contecflow.db
SECRET_KEY=${GEN_SECRET_KEY}
CLIENT_PORTAL_SECRET=${PORTAL_SECRET}
ACCESS_TOKEN_EXPIRE_MINUTES=60
REFRESH_TOKEN_EXPIRE_DAYS=30
ALLOWED_ORIGINS=["http://localhost:3000","http://localhost:5173","http://localhost:8000"]
SUPERADMIN_EMAIL=admin@company.com
SUPERADMIN_PASSWORD=contecflow2024!
DEFAULT_USER_PASSWORD=contecflow2024!
ANTHROPIC_API_KEY=
CONTECFLOW_AI_MODEL=claude-haiku-4-5
ENVEOF
    fi
  fi

  # Patch existing .env: ensure required variables are present and replace placeholders.
  "$PYTHON" - <<'PY'
from pathlib import Path
import secrets

env_path = Path('.env')
if env_path.exists():
    lines = env_path.read_text(encoding='utf-8').splitlines()
else:
    lines = []


def set_var(name: str, value: str) -> None:
    for idx, line in enumerate(lines):
        if line.startswith(f'{name}='):
            lines[idx] = f'{name}={value}'
            return
    lines.append(f'{name}={value}')


def is_placeholder(value: str | None) -> bool:
    if not value:
        return True
    upper = value.upper()
    return any(upper.startswith(prefix) for prefix in ('CHANGE_ME', 'REPLACE_ME', 'TODO', 'PLACEHOLDER'))


def is_weak(value: str | None) -> bool:
    if is_placeholder(value):
        return True
    return (value or '').lower() in {'password', 'admin', 'admin123', '123456', 'contecflow2024!', 'changeme'}


def get_var(name: str) -> str:
    for line in lines:
        if line.startswith(f'{name}='):
            return line.split('=', 1)[1]
    return ''

# Auditoría 2026-08 (P0-4): estas tres eran set_var() incondicionales, así que
# CADA ejecución de setup.sh sobrescribía las credenciales configuradas en .env
# con una constante escrita en este script — incluido un .env de producción.
# Se rellenan solo si faltan o siguen siendo placeholder, que es el patrón que ya
# usaban CLIENT_PORTAL_SECRET y WEBHOOK_SECRET tres líneas más abajo.
if is_placeholder(get_var('SUPERADMIN_EMAIL')):
    set_var('SUPERADMIN_EMAIL', 'admin@company.com')
# is_weak (no is_placeholder) porque incluye explícitamente 'contecflow2024!':
# así la constante compartida por todas las instalaciones se sustituye por un
# valor aleatorio por instalación, y una contraseña real y fuerte se preserva.
# setup.sh imprime las credenciales resultantes al final, así que el onboarding
# local sigue funcionando igual.
if is_weak(get_var('SUPERADMIN_PASSWORD')):
    set_var('SUPERADMIN_PASSWORD', secrets.token_urlsafe(18) + 'Aa1!')
if is_weak(get_var('DEFAULT_USER_PASSWORD')):
    set_var('DEFAULT_USER_PASSWORD', secrets.token_urlsafe(18) + 'Aa1!')
# ENVIRONMENT gobierna el gate de operaciones destructivas (sync_demo_passwords).
# Si falta, los scripts asumen production y NO tocan credenciales; para una
# instalación local hay que declararlo explícitamente.
if not get_var('ENVIRONMENT'):
    set_var('ENVIRONMENT', 'development')
if is_placeholder(get_var('CLIENT_PORTAL_SECRET')):
    set_var('CLIENT_PORTAL_SECRET', secrets.token_hex(32))
if is_placeholder(get_var('WEBHOOK_SECRET')):
    set_var('WEBHOOK_SECRET', secrets.token_hex(32))

env_path.write_text('\n'.join(lines) + '\n', encoding='utf-8')
PY

  # Rotate SECRET_KEY when it still uses placeholders or weak defaults.
  SECRET_STATUS=$("$PYTHON" - <<'PY'
import secrets
from pathlib import Path

env_path = Path('.env')
if not env_path.exists():
    print('OK')
    raise SystemExit(0)

lines = env_path.read_text(encoding='utf-8').splitlines()
secret_indexes = [i for i, line in enumerate(lines) if line.startswith('SECRET_KEY=')]
secret_value = lines[secret_indexes[-1]][len('SECRET_KEY='):] if secret_indexes else ''

is_insecure = (
    len(secret_value) < 32
    or secret_value.upper().startswith('CHANGE_ME')
    or secret_value.upper().startswith('REPLACE_ME')
    or secret_value == 'contecflow-secret-key-change-in-production-min32chars!!'
)

if not is_insecure:
    print('OK')
    raise SystemExit(0)

new_secret = secrets.token_hex(32)
if secret_indexes:
    for idx in secret_indexes:
        lines[idx] = f'SECRET_KEY={new_secret}'
else:
    lines.append(f'SECRET_KEY={new_secret}')

env_path.write_text('\n'.join(lines) + '\n', encoding='utf-8')
print('ROTATED')
PY
)
  if [ "$SECRET_STATUS" = "ROTATED" ]; then
    warn "SECRET_KEY insegura detectada en .env — regenerada automáticamente"
  fi

  # ── Migraciones: Alembic es la ÚNICA fuente de verdad ───────────────────────
  # Auditoría 2026-08 (hallazgo 11). Antes había dos caminos:
  #   BD nueva     → Base.metadata.create_all() + `alembic stamp head`
  #   BD existente → `alembic upgrade head`
  # `stamp head` marca las revisiones como aplicadas SIN ejecutarlas, así que la
  # cadena de Alembic no se ejercitaba nunca de principio a fin. Al probarla
  # sobre una base vacía resultó que producía 374 tablas frente a las 392 de los
  # modelos: faltaban 19 (expenses, email_templates, automation_rules,
  # revenue_recognition_*, gdpr_requests, webhook_triggers…). Se cerró con la
  # revisión 089 y ahora `upgrade head` construye el esquema completo.
  #
  # Ya no se usa `app.db.migrate` (create_all + ALTER TABLE a mano con sintaxis
  # de SQLite) en ningún caso: era el segundo camino que ocultaba el hueco.
  #
  # No hay atajo por hash de modelos: `alembic upgrade head` es idempotente y
  # barato cuando no hay revisiones pendientes, y saltárselo era justo lo que
  # dejaba bases sin migrar tras un `git pull`.
  log "Aplicando migraciones con Alembic..."
  if ! "$PY_BIN" -m alembic upgrade head; then
    error "Las migraciones han fallado. La aplicación NO se arranca con un esquema a medias."
    error "Revisa el error de arriba; si la base está corrupta, restaura una copia antes de reintentar."
    exit 1
  fi
  log "Esquema al día ✓"

  # ── Comprobación / seed inicial ──────────────────────────────────────────────────────
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
    log "Esquema listo. La inicialización de datos la maneja el modo (clean/demo)."
    if [ "$USE_DOCKER" != "1" ]; then
      # Sólo para SQLite: si el fichero quedó corrupto o vacío, se rehace desde
      # cero con Alembic (antes se usaba app.db.migrate, el camino que ocultaba
      # el hueco de esquema).
      rm -f contecflow.db
      "$PY_BIN" -m alembic upgrade head
    fi
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

  # ── Gate de entorno (auditoría 2026-08, P0-4) ────────────────────────────────
  # Esta función reescribe el hash de contraseña de admin/ana.torres/luis.vega/
  # rrhh con DEFAULT_USER_PASSWORD del .env. Sin esta guarda, un ./setup.sh
  # ejecutado contra producción — algo que la vía Docker soporta — dejaba la
  # cuenta admin con una contraseña conocida y compartida.
  if ! is_safe_for_destructive_ops; then
    warn "ENVIRONMENT=$(get_environment): se OMITE la sincronización de contraseñas demo."
    warn "Reescribir credenciales solo se permite en development/test/demo."
    return 0
  fi

  DEMO_PWD=$(get_demo_password)
  if [ -z "$DEMO_PWD" ]; then
    warn "DEFAULT_USER_PASSWORD no está definida en .env: se omite la sincronización."
    return 0
  fi

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
  SYNC_RESULT=$(DEMO_PWD="$DEMO_PWD" "$PY_BIN" -c "
import os, sys
from app.db.session import SessionLocal
from app.models.user import User
from app.core.security import get_password_hash

pwd = os.environ['DEMO_PWD']
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

# ── Reset DB data and keep only admin ────────────────────────────────────────
prepare_admin_only_database() {
  section "Reseteando base de datos (solo admin)"
  cd "$SCRIPT_DIR"
  resolve_venv_bins

  if [ ! -f "$PY_BIN" ]; then
    error "Python del entorno virtual no encontrado. Ejecuta primero ./setup.sh"
    exit 1
  fi

  if ! "$PY_BIN" scripts/reset_to_admin_only.py; then
    error "No se pudo resetear la base de datos a modo admin-only"
    exit 1
  fi

  log "BD lista: solo usuario admin disponible"
}

# ── Seed demo data on demand ────────────────────────────────────────────────
prepare_demo_database() {
  section "Inicializando base de datos con datos demo"
  cd "$SCRIPT_DIR"
  resolve_venv_bins

  if [ ! -f "$PY_BIN" ]; then
    error "Python del entorno virtual no encontrado. Ejecuta primero ./setup.sh"
    exit 1
  fi

  if ! "$PY_BIN" -m app.db.seed; then
    error "No se pudieron cargar los datos demo"
    exit 1
  fi

  log "Datos demo cargados"
}

# ── Start services ────────────────────────────────────────────────────────────
start_services() {
  section "Arrancando Contecflow"
  cd "$SCRIPT_DIR"
  resolve_venv_bins
  preflight_start_checks

  # SQLite self-healing for common local crash leftovers (WAL/SHM).
  if [ -f "contecflow.db" ] && check_command sqlite3; then
    SQLITE_CHECK_OUTPUT=$(sqlite3 contecflow.db "PRAGMA quick_check;" 2>&1 || true)
    if ! echo "$SQLITE_CHECK_OUTPUT" | grep -q '^ok$'; then
      warn "SQLite quick_check falló antes del arranque: $SQLITE_CHECK_OUTPUT"
      warn "Intentando recuperación local eliminando WAL/SHM..."
      rm -f contecflow.db-wal contecflow.db-shm
      SQLITE_RECHECK_OUTPUT=$(sqlite3 contecflow.db "PRAGMA quick_check;" 2>&1 || true)
      if echo "$SQLITE_RECHECK_OUTPUT" | grep -q '^ok$'; then
        log "SQLite recuperada correctamente tras limpiar WAL/SHM"
      else
        error "SQLite sigue en estado inválido: $SQLITE_RECHECK_OUTPUT"
        error "Ejecuta: rm -f contecflow.db* && $PY_BIN -m app.db.migrate"
        exit 1
      fi
    fi
  fi

  if [ ! -f "$PY_BIN" ]; then
    error "Entorno virtual no encontrado. Ejecuta primero ./setup.sh demo o ./setup.sh clean"
    exit 1
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
  stop_background_jobs
  sleep 1

  log "Arrancando backend en puerto $BACKEND_PORT..."
  # Las tareas programadas las corre Celery beat (abajo), no la API: con los
  # dos activos cada tarea se ejecutaria dos veces y la API se niega a arrancar.
  ENABLE_APSCHEDULER=0 ENABLE_CELERY_BEAT=1 "$PY_BIN" -m uvicorn app.main:app \
    --host 0.0.0.0 \
    --port $BACKEND_PORT \
    --log-level info \
    --workers 1 \
    > /tmp/contecflow-backend.log 2>&1 &
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
      tail -20 /tmp/contecflow-backend.log
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
    tail -20 /tmp/contecflow-backend.log
    echo ""
    echo -e "${YELLOW}⚠ Posibles causas:${NC}"
    echo "   1. El puerto $BACKEND_PORT ya está en uso (ejecuta: lsof -i :$BACKEND_PORT)"
    echo "   2. Error en Python — revisa: cat /tmp/contecflow-backend.log"
    echo "   3. Falta instalar dependencias — ejecuta: cd venv && pip install -r ../requirements.txt"
    exit 1
  fi

  start_background_jobs

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
      if [ -f "frontend/validate.cjs" ]; then
        if node frontend/validate.cjs; then
          echo -e "${GREEN}✅ JSX validado correctamente${NC}"
          echo "$JSX_HASH" > "$JSX_HASH_FILE"
        else
          echo -e "${RED}❌ Errores en JSX detectados — revisa los archivos marcados${NC}"
          exit 1
        fi
      else
        warn "frontend/validate.cjs no encontrado — omitiendo validación JSX"
      fi
    else
      log "JSX sin cambios, omitiendo validación Babel"
    fi
  fi

    log "Arrancando frontend en puerto $FRONTEND_PORT..."
  cd frontend
  npm run dev -- --port $FRONTEND_PORT > /tmp/contecflow-frontend.log 2>&1 &
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
  echo "$BACKEND_PID" > /tmp/contecflow-backend.pid
  echo "$FRONTEND_PID" > /tmp/contecflow-frontend.pid

  echo ""
  echo -e "${GREEN}${BOLD}╔══════════════════════════════════════════╗${NC}"
  echo -e "${GREEN}${BOLD}║         Contecflow listo ✓                  ║${NC}"
  echo -e "${GREEN}${BOLD}╚══════════════════════════════════════════╝${NC}"
  echo ""
  echo -e "  🌐 App:      ${BOLD}http://localhost:$FRONTEND_PORT${NC}"
  echo -e "  📡 API:      http://localhost:$BACKEND_PORT/api/v1/docs"
  echo -e "  📋 Logs:     /tmp/contecflow-backend.log"
  echo -e "  ⏱  Tareas:   /tmp/contecflow-worker.log y /tmp/contecflow-beat.log"
  echo ""
  DEMO_PASSWORD=$(get_demo_password)
  echo -e "  ${BOLD}Usuarios de prueba:${NC}"
  echo -e "  admin      / ${DEMO_PASSWORD}  → Dirección"
  echo -e "  ana.torres / ${DEMO_PASSWORD}  → PM"
  echo -e "  luis.vega  / ${DEMO_PASSWORD}  → Empleado"
  echo -e "  rrhh       / ${DEMO_PASSWORD}  → RRHH"
  echo ""
  echo -e "  ${YELLOW}⚠  Contraseña por defecto mostrada arriba.${NC}"
  echo -e "  ${YELLOW}   Cámbiala en .env (DEFAULT_USER_PASSWORD) antes de usar en producción.${NC}"
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
  trap "echo ''; log 'Parando Contecflow...'; kill $BACKEND_PID $FRONTEND_PID 2>/dev/null; stop_background_jobs; exit 0" INT TERM
  wait $BACKEND_PID $FRONTEND_PID
}

# ── Background jobs (Celery worker + beat) ───────────────────────────────────
# Auditoria 2026-11: setup.sh no arrancaba Celery, y sin el no corrian 48 de
# las 52 tareas programadas: el monitor de SLA/OLA/UC, la lectura del buzon y
# la bandeja de eventos de ticket (avisos, correos, webhooks y flujos), entre
# otras. Las pruebas pasaban porque llaman a esas funciones directamente.
start_background_jobs() {
  log "Arrancando tareas en segundo plano (Celery worker y beat)..."
  "$PY_BIN" -m celery -A app.worker.celery_app worker --loglevel=info --concurrency=2 \
    > /tmp/contecflow-worker.log 2>&1 &
  echo $! > /tmp/contecflow-worker.pid
  "$PY_BIN" -m celery -A app.worker.celery_app beat --loglevel=info \
    --schedule /tmp/contecflow-celerybeat-schedule \
    > /tmp/contecflow-beat.log 2>&1 &
  echo $! > /tmp/contecflow-beat.pid
  sleep 3
  for nombre in worker beat; do
    if ! kill -0 "$(cat /tmp/contecflow-$nombre.pid)" 2>/dev/null; then
      echo -e "${YELLOW}⚠  Celery $nombre no ha arrancado (¿Redis parado?). Revisa /tmp/contecflow-$nombre.log${NC}"
      tail -5 /tmp/contecflow-$nombre.log
    fi
  done
}

stop_background_jobs() {
  for nombre in worker beat; do
    if [ -f /tmp/contecflow-$nombre.pid ]; then
      kill "$(cat /tmp/contecflow-$nombre.pid)" 2>/dev/null || true
      rm -f /tmp/contecflow-$nombre.pid
    fi
  done
}

# ── Stop services ─────────────────────────────────────────────────────────────
stop_services() {
  log "Parando Contecflow..."
  stop_background_jobs
  [ -f /tmp/contecflow-backend.pid ]  && kill $(cat /tmp/contecflow-backend.pid)  2>/dev/null || true
  [ -f /tmp/contecflow-frontend.pid ] && kill $(cat /tmp/contecflow-frontend.pid) 2>/dev/null || true
  lsof -ti:$BACKEND_PORT  | xargs kill -9 2>/dev/null || true
  lsof -ti:$FRONTEND_PORT | xargs kill -9 2>/dev/null || true
  log "Parado"

  # La infraestructura Docker (Postgres + Redis) sigue corriendo intencionalmente
  # para no perder datos entre reinicios. Para pararla manualmente:
  if detect_docker 2>/dev/null && [ -f "$SCRIPT_DIR/docker-compose.yml" ]; then
    DOCKER_RUNNING=$(docker_compose_cmd ps --quiet 2>/dev/null | wc -l | tr -d ' ')
    if [ "$DOCKER_RUNNING" -gt 0 ] 2>/dev/null; then
      echo ""
      echo -e "  ${YELLOW}ℹ  Docker (Postgres+Redis) sigue activo.${NC}"
      echo -e "     Para pararlo: ${BOLD}docker compose down${NC}"
      echo -e "     Para borrarlo todo: ${BOLD}docker compose down -v${NC}"
    fi
  fi
}

# ── Main ──────────────────────────────────────────────────────────────────────
print_banner

case "${1:-}" in
  demo)
    log "Modo: demo"
    setup_backend
    setup_frontend
    prepare_demo_database
    start_services
    ;;
  clean)
    log "Modo: clean (solo admin)"
    setup_backend
    setup_frontend
    prepare_admin_only_database
    start_services
    ;;
  start)
    log "Modo: solo arrancar"
    start_services
    ;;
  stop)
    stop_services
    ;;
  docker-stop)
    log "Parando infraestructura Docker (Postgres + Redis)..."
    if detect_docker && [ -f "$SCRIPT_DIR/docker-compose.yml" ]; then
      docker_compose_cmd down
      log "Docker detenido (datos conservados en volúmenes)"
    else
      warn "Docker no disponible o docker-compose.yml no encontrado"
    fi
    ;;
  docker-clean)
    log "Parando infraestructura Docker y borrando volúmenes..."
    if detect_docker && [ -f "$SCRIPT_DIR/docker-compose.yml" ]; then
      docker_compose_cmd down -v
      log "Docker detenido y volúmenes eliminados"
    else
      warn "Docker no disponible o docker-compose.yml no encontrado"
    fi
    ;;
  update)
    log "Modo: actualizar"
    setup_backend
    setup_frontend
    log "Actualización completada. Ejecuta ./setup.sh start para arrancar."
    ;;
  *)
    echo "Uso:"
    echo "  ./setup.sh demo          → instala y arranca con datos demo"
    echo "  ./setup.sh clean         → instala y arranca con BD vacía (solo admin)"
    echo "  ./setup.sh start         → solo arranca (BD existente)"
    echo "  ./setup.sh stop          → para la app (Docker sigue activo)"
    echo "  ./setup.sh update        → actualiza dependencias"
    echo "  ./setup.sh docker-stop   → para la infraestructura Docker"
    echo "  ./setup.sh docker-clean  → para Docker y borra todos los datos"
    exit 1
    ;;
esac
