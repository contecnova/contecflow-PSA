#!/usr/bin/env bash
# ══════════════════════════════════════════════════════════════════════════════
# Contecflow PSA — desplegar o actualizar en un servidor propio
#
#   ./scripts/deploy.sh
#
# Orden: imágenes → copia de seguridad → migraciones → aplicación → salud.
#
#   1. Imágenes: si CONTECFLOW_APP_IMAGE / CONTECFLOW_WEB_IMAGE apuntan a un
#      registro (llevan «/»), se descargan; si no, se construyen aquí.
#   2. Copia: `scripts/backup.sh` (base + ficheros). Si la base ya está en
#      marcha y la copia falla, NO se sigue.
#   3. Migraciones: el servicio `migrate` del compose (Alembic + RLS). La API,
#      el worker y beat dependen de que termine bien: con una migración rota
#      la aplicación no arranca a medias.
#   4. `docker compose --profile app up -d`, comprobando que `migrate` sale con 0.
#   5. Salud: `GET /health` a través de nginx (`WEB_PORT`).
#
# Variables (del entorno o del .env de la carpeta): las del compose, más
#   GHCR_USER / GHCR_TOKEN   para entrar en ghcr.io si las imágenes están allí
#   DEPLOY_DIR               carpeta del despliegue (por defecto, la del repo)
#
# Revisión 2026-11: el anterior apuntaba a servicios `db`, `backend` y `nginx`
# que no existen en este compose, y si la copia fallaba seguía igualmente.
# ══════════════════════════════════════════════════════════════════════════════
set -euo pipefail

DEPLOY_DIR="${DEPLOY_DIR:-$(cd "$(dirname "$0")/.." && pwd)}"
cd "$DEPLOY_DIR"
[ -f .env ] || { echo "✗ Falta .env en $DEPLOY_DIR" >&2; exit 1; }
set -a; . ./.env; set +a

paso() { echo "[$(date '+%H:%M:%S')] → $1"; }
fallo() { echo "[$(date '+%H:%M:%S')] ✗ $1" >&2; exit 1; }

command -v docker > /dev/null || fallo "Docker no está instalado"
docker compose version > /dev/null 2>&1 || fallo "Falta Docker Compose v2"

# Los volúmenes de datos son externos (no los borra un `down -v`): se crean si faltan.
docker volume create contecflow_postgres_data > /dev/null
docker volume create contecflow_s3_data > /dev/null

# ── 1. Imágenes ───────────────────────────────────────────────────────────────
if [[ "${CONTECFLOW_APP_IMAGE:-}" == */* || "${CONTECFLOW_WEB_IMAGE:-}" == */* ]]; then
  if [ -n "${GHCR_TOKEN:-}" ] && [ -n "${GHCR_USER:-}" ]; then
    echo "$GHCR_TOKEN" | docker login ghcr.io -u "$GHCR_USER" --password-stdin > /dev/null
  fi
  paso "Descargando imágenes"
  docker compose --profile app pull api web
else
  paso "Construyendo imágenes"
  docker compose --profile app build api web
fi

# ── 2. Copia de seguridad ─────────────────────────────────────────────────────
if docker compose ps --status running --services 2>/dev/null | grep -qx postgres; then
  paso "Copia de seguridad"
  ./scripts/backup.sh || fallo "La copia falló: no se despliega sin copia"
else
  paso "La base no está en marcha: primera instalación, sin copia previa"
fi

# ── 3 y 4. Migraciones y aplicación ───────────────────────────────────────────
paso "Migraciones y arranque"
docker compose --profile app up -d --remove-orphans \
  || fallo "No arrancó. Mira: docker compose logs migrate api"
# `migrate` es de una sola pasada: se espera a que termine y se mira cómo.
for intento in $(seq 1 120); do
  ESTADO="$(docker compose ps -a migrate --format '{{.State}} {{.ExitCode}}' 2>/dev/null)"
  [[ "$ESTADO" == exited* ]] && break
  sleep 2
done
[[ "$ESTADO" == "exited 0" ]] || fallo "Las migraciones no terminaron bien ($ESTADO). Mira: docker compose logs migrate"

# ── 5. Salud ──────────────────────────────────────────────────────────────────
WEB="${WEB_PORT:-127.0.0.1:8080}"
[[ "$WEB" == *:* ]] || WEB="127.0.0.1:$WEB"
paso "Comprobando http://$WEB/health"
for intento in 1 2 3 4 5 6; do
  if curl -sf "http://$WEB/health" > /dev/null; then
    docker image prune -f > /dev/null 2>&1 || true
    echo "[$(date '+%H:%M:%S')] ✓ Desplegado ($(docker compose exec -T postgres psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -tAc 'select version_num from alembic_version' 2>/dev/null | tr -d ' \r'))"
    exit 0
  fi
  sleep 5
done
fallo "La aplicación no contesta en /health. Mira: docker compose logs api web"
