#!/bin/bash
# test_and_report.sh - Ejecuta tests, genera cobertura y actualiza el reporte resultado.html

set -e
cd "$(dirname "$0")/.."

# Ejecutar tests backend y generar cobertura
pytest --maxfail=0 --tb=short --cov=. --cov-report=term --cov-report=html

# Ejecutar tests unitarios frontend
if [ -d "frontend" ]; then
  cd frontend
  npm install > /dev/null 2>&1
  npm run test || true
  cd ..
fi

# Guardar salidas de tests
pytest --maxfail=0 --tb=short --cov=. --cov-report=term --cov-report=html > backend_test_output.txt || true
if [ -d "frontend" ]; then
  cd frontend
  npm run test > frontend_test_output.txt || true
  npx playwright test --reporter=list,html > playwright_test_output.txt || true
  cd ..
fi

# Resumen automático en resultado.html
DATE=$(date '+%d/%m/%Y %H:%M')
BACKEND_FAILS=$(grep -E 'FAILED|ERROR' backend_test_output.txt | wc -l | xargs)
FRONTEND_FAILS=$(grep -E 'FAIL|Error:' frontend/frontend_test_output.txt | wc -l | xargs)
E2E_FAILS=$(grep -E 'FAIL|Error:' frontend/playwright_test_output.txt | wc -l | xargs)

sed -i '' \
  -e "/<section class=\"block\">/a\\\n<h2>Resumen automático de tests ($DATE)</h2>\\\n<ul>\\\n  <li>Backend: $BACKEND_FAILS fallos/errores</li>\\\n  <li>Frontend: $FRONTEND_FAILS fallos/errores</li>\\\n  <li>E2E: $E2E_FAILS fallos/errores</li>\\\n</ul>" \
  resultado.html

# Mensaje final
echo "\nTests y reporte ejecutados. Consulta resultado.html y htmlcov/index.html."
