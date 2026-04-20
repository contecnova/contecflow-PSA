#!/bin/bash
# Actualiza la tabla de endpoints y métodos HTTP en DOCS.md a partir del OpenAPI
# Uso: ./scripts/update_endpoints_table.sh

set -e

# Arranca el servidor en background
uvicorn app.main:app --reload &
SERVER_PID=$!

# Espera a que el servidor esté listo
sleep 5

# Descarga el OpenAPI JSON
echo "Descargando OpenAPI..."
curl -s http://127.0.0.1:8000/api/v1/openapi.json > openapi.json

# Genera la tabla markdown
echo "| Endpoint | Método |" > endpoints_table.md
echo "|---|---|" >> endpoints_table.md
python3 -c "import json; d=json.load(open('openapi.json')); [print(f'| {p} | {m.upper()} |') for p,v in d['paths'].items() for m in v]" >> endpoints_table.md

# Inserta la tabla en DOCS.md (reemplaza bloque entre marcadores)
START_MARKER='### Tabla de endpoints y métodos HTTP (generada automáticamente)'
END_MARKER='### Autenticación'
awk -v start="$START_MARKER" -v end="$END_MARKER" -v table="$(cat endpoints_table.md | sed 's/\//\\\//g')" '
  BEGIN {in_block=0}
  {if ($0 ~ start) {print; in_block=1; print table; next} else if ($0 ~ end) {in_block=0}}
  if (!in_block) print
' DOCS.md > DOCS.md.tmp && mv DOCS.md.tmp DOCS.md

# Limpieza
rm -f openapi.json endpoints_table.md
kill $SERVER_PID

echo "Tabla de endpoints actualizada en DOCS.md."
