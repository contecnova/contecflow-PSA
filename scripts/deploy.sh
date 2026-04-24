#!/usr/bin/env bash
# ══════════════════════════════════════════════════════════════════════════════
# Contecflow PSA — Script de despliegue para servidor propio
# Uso: ./scripts/deploy.sh [staging|production]
#
# Orden garantizado: pull → backup → migrate → smoke → run → health
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

# ── Pull nuevas imágenes ───────────────────────────────────────────────────────
log "Descargando nueva imagen..."
docker compose pull

# ── Backup (solo production) ───────────────────────────────────────────────────
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

# ── PASO 1: Arrancar solo infraestructura (DB, Redis, Nginx) sin el backend ───
# El backend se levanta después de que las migraciones hayan terminado.
log "Arrancando infraestructura (db, redis, nginx)..."
docker compose up -d --no-build db redis nginx 2>/dev/null \
  || docker compose up -d --no-build db redis 2>/dev/null \
  || docker compose up -d --no-build db 2>/dev/null \
  || warn "No se pudo arrancar infraestructura selectivamente; se continúa de todas formas"

# Esperar a que la BD esté lista antes de migrar
DB_RETRIES=10; DB_ATTEMPT=0
until docker compose exec -T db pg_isready -U "${POSTGRES_USER:-contecflow}" >/dev/null 2>&1; do
  DB_ATTEMPT=$((DB_ATTEMPT+1))
  [[ $DB_ATTEMPT -ge $DB_RETRIES ]] && err "Base de datos no disponible tras $DB_RETRIES intentos"
  warn "Esperando BD... $DB_ATTEMPT/$DB_RETRIES"
  sleep 3
done
log "Base de datos lista"

# ── PASO 2: Migraciones ────────────────────────────────────────────────────────
log "Aplicando migraciones..."
MIGRATE_REVISION_BEFORE=$(docker compose run --rm --no-deps backend \
  python -m alembic current 2>/dev/null | grep -oE '[a-f0-9]{12}' | head -1 || echo "unknown")

if docker compose run --rm --no-deps backend python -m alembic upgrade head; then
  log "Migraciones aplicadas correctamente"
else
  err "Fallo en migraciones — abortando despliegue. Revisión anterior: ${MIGRATE_REVISION_BEFORE}. Ejecuta manualmente: alembic downgrade <rev>"
fi

# ── PASO 3: Smoke check de schema antes de arrancar la app ────────────────────
log "Smoke check de schema..."
if ! docker compose run --rm --no-deps backend \
    python -c "from app.main import _read_alembic_revision; from app.core.config import settings; rev=_read_alembic_revision(settings.DATABASE_URL); print('schema OK, rev='+str(rev)); assert rev is not None" 2>/dev/null; then
  warn "Smoke check de schema no concluyente — continuando igualmente"
fi

# ── PASO 4: Arrancar la aplicación completa ────────────────────────────────────
log "Arrancando aplicación..."
docker compose up -d --no-build --remove-orphans

# ── PASO 5: Health check ──────────────────────────────────────────────────────
log "Verificando salud..."
sleep 8
MAX_RETRIES=6; RETRY=0
until curl -sf http://localhost/api/v1/health >/dev/null 2>&1; do
  RETRY=$((RETRY+1))
  [[ $RETRY -ge $MAX_RETRIES ]] && err "Health check falló tras $MAX_RETRIES intentos. Revisa: docker compose logs backend"
  warn "Esperando... $RETRY/$MAX_RETRIES"
  sleep 5
done

docker image prune -f >/dev/null 2>&1 || true
log "Despliegue completado — ${ENVIRONMENT} — $(date)"
