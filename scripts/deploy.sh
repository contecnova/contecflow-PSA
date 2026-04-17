#!/usr/bin/env bash
# ══════════════════════════════════════════════════════════════════════════════
# Contecflow PSA — Script de despliegue para servidor propio
# Uso: ./scripts/deploy.sh [staging|production]
#
# Variables de entorno requeridas (o en .env del directorio de despliegue):
#   GHCR_TOKEN       — GitHub personal access token (read:packages)
#   GHCR_USER        — GitHub username / org
#   BACKEND_IMAGE    — ghcr.io/<org>/contecflow-backend:latest
#   FRONTEND_IMAGE   — ghcr.io/<org>/contecflow-frontend:latest
# ══════════════════════════════════════════════════════════════════════════════
set -euo pipefail

ENVIRONMENT=${1:-staging}
DEPLOY_DIR="/opt/contecflow"
LOG_FILE="/var/log/contecflow-deploy.log"

RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'; NC='\033[0m'
log()  { echo -e "${GREEN}[$(date '+%H:%M:%S')] ✅ $1${NC}" | tee -a "$LOG_FILE" 2>/dev/null || echo "✅ $1"; }
warn() { echo -e "${YELLOW}[$(date '+%H:%M:%S')] ⚠  $1${NC}" | tee -a "$LOG_FILE" 2>/dev/null || echo "⚠  $1"; }
err()  { echo -e "${RED}[$(date '+%H:%M:%S')] ✗  $1${NC}"; exit 1; }

log "Iniciando despliegue Contecflow PSA → ${ENVIRONMENT}"

command -v docker  >/dev/null || err "Docker no instalado"
docker compose version >/dev/null 2>&1 || err "Docker Compose no instalado"
[[ -d "$DEPLOY_DIR" ]]      || err "Directorio $DEPLOY_DIR no existe. Crea /opt/contecflow y configura .env"
[[ -f "$DEPLOY_DIR/.env" ]] || err "Archivo .env no encontrado en $DEPLOY_DIR"
cd "$DEPLOY_DIR"

# ── Login to GitHub Container Registry ────────────────────────────────────────
if [[ -n "${GHCR_TOKEN:-}" && -n "${GHCR_USER:-}" ]]; then
  log "Autenticando en ghcr.io..."
  echo "$GHCR_TOKEN" | docker login ghcr.io -u "$GHCR_USER" --password-stdin
else
  warn "GHCR_TOKEN / GHCR_USER no definidos — se omite login al registry (se usará build local)"
fi

if [[ "$ENVIRONMENT" == "production" ]]; then
  warn "Haciendo backup de base de datos..."
  mkdir -p backups
  BACKUP_FILE="backup_$(date +%Y%m%d_%H%M%S).sql"
  docker compose exec -T db pg_dump \
    -U "${POSTGRES_USER:-contecflow}" "${POSTGRES_DB:-contecflow}" \
    > "backups/$BACKUP_FILE" 2>/dev/null \
    && log "Backup: backups/$BACKUP_FILE" \
    || warn "Backup omitido (BD puede no estar corriendo)"
fi

log "Descargando nueva imagen..."
docker compose pull

log "Desplegando servicios..."
docker compose up -d --no-build --remove-orphans

log "Aplicando migraciones..."
docker compose exec -T backend alembic upgrade head

log "Verificando salud..."
sleep 8
MAX_RETRIES=6; RETRY=0
until curl -sf http://localhost/api/v1/health >/dev/null 2>&1; do
  RETRY=$((RETRY+1))
  [[ $RETRY -ge $MAX_RETRIES ]] && err "Health check falló tras $MAX_RETRIES intentos"
  warn "Esperando... $RETRY/$MAX_RETRIES"
  sleep 5
done

docker image prune -f >/dev/null 2>&1 || true
log "Despliegue completado — ${ENVIRONMENT} — $(date)"
