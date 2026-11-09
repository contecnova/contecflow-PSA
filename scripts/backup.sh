#!/usr/bin/env bash
# ══════════════════════════════════════════════════════════════════════════════
# Contecflow PSA — copia de seguridad: base de datos y ficheros
#
#   ./scripts/backup.sh            deja la copia en $BACKUP_DIR (por defecto ./backups)
#
# Qué copia
#   · La base: `pg_dump -Fc` desde el contenedor `postgres` (formato propio de
#     PostgreSQL: comprimido y restaurable tabla a tabla). Se comprueba con
#     `pg_restore --list` antes de darla por buena.
#   · Los ficheros (adjuntos, documentos, justificantes): el volumen S3
#     ($S3_VOLUME, por defecto contecflow_s3_data), empaquetado con tar.
#   · Un manifiesto con la huella SHA-256 de cada pieza y la revisión de Alembic.
#
# Variables (del entorno o del .env de la carpeta):
#   BACKUP_DIR   carpeta de destino                       (./backups)
#   BACKUP_KEEP  copias que se conservan; las más viejas se borran (14)
#   S3_VOLUME    volumen de los ficheros                  (contecflow_s3_data)
#   POSTGRES_USER, POSTGRES_DB  los del compose
#
# Revisión 2026-11: antes no había procedimiento de copia; `deploy.sh` hacía un
# `pg_dump` contra un servicio `db` que no existe y, si fallaba, seguía.
# ══════════════════════════════════════════════════════════════════════════════
set -euo pipefail

RAIZ="$(cd "$(dirname "$0")/.." && pwd)"
cd "$RAIZ"
if [ -f .env ]; then set -a; . ./.env; set +a; fi

BACKUP_DIR="${BACKUP_DIR:-$RAIZ/backups}"
BACKUP_KEEP="${BACKUP_KEEP:-14}"
S3_VOLUME="${S3_VOLUME:-contecflow_s3_data}"
: "${POSTGRES_USER:?define POSTGRES_USER}" "${POSTGRES_DB:?define POSTGRES_DB}"

SELLO="$(date +%Y%m%d-%H%M%S)"
DESTINO="$BACKUP_DIR/contecflow-$SELLO"
mkdir -p "$DESTINO"
fallo() { echo "✗ $1" >&2; rm -rf "$DESTINO"; exit 1; }

echo "→ Base de datos ($POSTGRES_DB)…"
docker compose exec -T postgres pg_dump -U "$POSTGRES_USER" -d "$POSTGRES_DB" -Fc > "$DESTINO/base.dump" \
  || fallo "pg_dump falló"
docker compose exec -T postgres pg_restore --list < "$DESTINO/base.dump" > /dev/null \
  || fallo "la copia de la base no se puede leer (pg_restore --list)"
REVISION="$(docker compose exec -T postgres psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -tAc 'select version_num from alembic_version' 2>/dev/null | tr '\n' ' ' || true)"

echo "→ Ficheros ($S3_VOLUME)…"
docker volume inspect "$S3_VOLUME" > /dev/null 2>&1 || fallo "no existe el volumen $S3_VOLUME"
docker run --rm -v "$S3_VOLUME":/datos:ro alpine tar czf - -C /datos . > "$DESTINO/ficheros.tar.gz" \
  || fallo "no se pudieron empaquetar los ficheros"
tar tzf "$DESTINO/ficheros.tar.gz" > /dev/null || fallo "el paquete de ficheros está dañado"

( cd "$DESTINO" && {
    echo "fecha: $SELLO"
    echo "alembic: ${REVISION:-desconocida}"
    if command -v sha256sum > /dev/null; then sha256sum base.dump ficheros.tar.gz; else shasum -a 256 base.dump ficheros.tar.gz; fi
  } > MANIFIESTO )

echo "✓ Copia en $DESTINO ($(du -sh "$DESTINO" | cut -f1))"

# Retención: se quedan las $BACKUP_KEEP más recientes.
ls -1d "$BACKUP_DIR"/contecflow-* 2>/dev/null | sort -r | tail -n +"$((BACKUP_KEEP + 1))" | while read -r vieja; do
  rm -rf "$vieja" && echo "  borrada la copia antigua $(basename "$vieja")"
done
