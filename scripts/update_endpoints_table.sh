#!/bin/bash
# Actualiza la tabla de endpoints y métodos HTTP en DOCS.md a partir del OpenAPI
# Uso: ./scripts/update_endpoints_table.sh

set -euo pipefail

cleanup() {
  rm -f openapi.json endpoints_table.md DOCS.md.tmp
  if [[ -n "${SERVER_PID:-}" ]]; then
    kill "$SERVER_PID" 2>/dev/null || true
  fi
}
trap cleanup EXIT

# Arranca el servidor en background (sin --reload para evitar procesos hijos)
uvicorn app.main:app &
SERVER_PID=$!

# Espera a que el servidor esté listo
for _ in {1..20}; do
  if curl -fsS http://127.0.0.1:8000/api/v1/openapi.json >/dev/null 2>&1; then
    break
  fi
  sleep 1
done

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
awk -v start="$START_MARKER" -v end="$END_MARKER" '
  BEGIN {in_block=0}
  {
    if ($0 ~ start) {
      print
      in_block=1
      while ((getline line < "endpoints_table.md") > 0) print line
      close("endpoints_table.md")
      next
    } else if ($0 ~ end) {
      in_block=0
    }
    if (!in_block) print
  }
' DOCS.md > DOCS.md.tmp && mv DOCS.md.tmp DOCS.md

echo "Tabla de endpoints actualizada en DOCS.md."
