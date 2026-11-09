#!/usr/bin/env bash
# ══════════════════════════════════════════════════════════════════════════════
# Contecflow PSA — restaurar una copia de scripts/backup.sh
#
#   ./scripts/restore.sh backups/contecflow-20261109-101500 --borra-lo-que-hay
#
# Sustituye la base y los ficheros por los de la copia. Para la aplicación
# (api, worker, beat) mientras tanto y la vuelve a arrancar al terminar. Antes
# comprueba las huellas del MANIFIESTO: una copia alterada no se restaura.
#
# Es lo que se hace tras un desastre, también en producción; por eso no mira
# ENVIRONMENT, pero exige la confirmación explícita del segundo argumento.
# ══════════════════════════════════════════════════════════════════════════════
set -euo pipefail

COPIA="${1:-}"; CONFIRMA="${2:-}"
[ -n "$COPIA" ] && [ -d "$COPIA" ] || { echo "Uso: $0 <carpeta de la copia> --borra-lo-que-hay" >&2; exit 1; }
[ "$CONFIRMA" = "--borra-lo-que-hay" ] || { echo "Falta --borra-lo-que-hay: la base y los ficheros actuales se pierden." >&2; exit 1; }
COPIA="$(cd "$COPIA" && pwd)"

RAIZ="$(cd "$(dirname "$0")/.." && pwd)"
cd "$RAIZ"
if [ -f .env ]; then set -a; . ./.env; set +a; fi
S3_VOLUME="${S3_VOLUME:-contecflow_s3_data}"
: "${POSTGRES_USER:?define POSTGRES_USER}" "${POSTGRES_DB:?define POSTGRES_DB}"

echo "→ Comprobando el manifiesto…"
# Una herramienta, elegida antes: con `shasum -c || sha256sum -c` la segunda
# leía la entrada ya consumida, no comprobaba nada y daba 0 (medido).
if command -v sha256sum > /dev/null; then HUELLA="sha256sum"; else HUELLA="shasum -a 256"; fi
( cd "$COPIA" && grep -E '^[0-9a-f]{64} ' MANIFIESTO | $HUELLA -c - ) \
  || { echo "✗ Las huellas no coinciden: la copia está dañada o alterada." >&2; exit 1; }

echo "→ Parando la aplicación…"
docker compose --profile app stop api worker beat 2>/dev/null || true

echo "→ Base de datos…"
docker compose exec -T postgres pg_restore -U "$POSTGRES_USER" -d "$POSTGRES_DB" --clean --if-exists --no-owner \
  < "$COPIA/base.dump"

echo "→ Ficheros…"
docker run --rm -i -v "$S3_VOLUME":/datos alpine sh -c 'find /datos -mindepth 1 -delete && tar xzf - -C /datos' \
  < "$COPIA/ficheros.tar.gz"

echo "→ Arrancando la aplicación…"
docker compose --profile app start api worker beat 2>/dev/null || true
echo "✓ Restaurada $(basename "$COPIA") ($(grep '^alembic:' "$COPIA/MANIFIESTO"))"
