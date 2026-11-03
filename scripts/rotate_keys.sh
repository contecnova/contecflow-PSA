#!/bin/bash
# Rotacion de SECRET_KEY sin perder lo cifrado.
# Uso (desde la raiz del repositorio, con la base accesible):
#   bash scripts/rotate_keys.sh
#
# Auditoria 2026-11: la version anterior cambiaba SECRET_KEY en el .env, no
# re-cifraba nada (los secretos guardados quedaban ilegibles) e imprimia la
# clave nueva en la terminal. Ahora:
#   1. copia el .env a .env.bak.<fecha> (permisos 600; contiene la clave vieja);
#   2. pone la clave nueva en SECRET_KEY y la vieja al principio de
#      SECRET_KEY_PREVIOUS (la aplicacion descifra con las dos);
#   3. re-cifra con la nueva todo lo cifrado (scripts/reencrypt_secrets.py);
#   4. no imprime ninguna clave.
# Despues: reiniciar API, worker y beat. Las sesiones abiertas caducan (los
# tokens firmados con la clave vieja dejan de valer). Cuando
# `reencrypt_secrets.py --check` diga 0, SECRET_KEY_PREVIOUS se puede vaciar.

set -euo pipefail

cd "$(dirname "$0")/.."
PY_BIN="${PY_BIN:-venv/bin/python}"

if [ ! -f .env ]; then
  echo "No hay .env en $(pwd). Rota la clave en tu gestor de secretos y ejecuta scripts/reencrypt_secrets.py." >&2
  exit 1
fi

VIEJA="$(grep -E '^SECRET_KEY=' .env | head -1 | cut -d= -f2-)"
if [ -z "$VIEJA" ]; then
  echo "El .env no tiene SECRET_KEY." >&2
  exit 1
fi
ANTERIORES="$(grep -E '^SECRET_KEY_PREVIOUS=' .env | head -1 | cut -d= -f2- || true)"
NUEVA="$(openssl rand -hex 32)"

COPIA=".env.bak.$(date +%Y%m%d%H%M%S)"
cp .env "$COPIA"
chmod 600 "$COPIA"

PREVIAS="$VIEJA${ANTERIORES:+,$ANTERIORES}"
NUEVA="$NUEVA" PREVIAS="$PREVIAS" "$PY_BIN" - <<'PY'
import os
lineas = open(".env").read().splitlines()
fuera = [l for l in lineas if not l.startswith(("SECRET_KEY=", "SECRET_KEY_PREVIOUS="))]
fuera += [f"SECRET_KEY={os.environ['NUEVA']}", f"SECRET_KEY_PREVIOUS={os.environ['PREVIAS']}"]
open(".env", "w").write("\n".join(fuera) + "\n")
PY
chmod 600 .env
echo "SECRET_KEY rotada. Copia del .env anterior en $COPIA (contiene la clave vieja: guárdala o bórrala)."

if ! "$PY_BIN" scripts/reencrypt_secrets.py; then
  echo "La re-cifra falló. La aplicación sigue pudiendo leer con SECRET_KEY_PREVIOUS; repite: $PY_BIN scripts/reencrypt_secrets.py" >&2
  exit 1
fi

cat <<'EOF'

Siguiente:
- Reinicia la API, el worker y el beat (./setup.sh stop && ./setup.sh start, o docker compose up -d).
- Si la clave vive también en un gestor de secretos o en variables del servidor, actualízala allí con el mismo valor del .env.
- Comprueba: venv/bin/python scripts/reencrypt_secrets.py --check  (debe decir «Con clave anterior: 0»).
EOF
