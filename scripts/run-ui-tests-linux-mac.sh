#!/bin/bash
# Script para ejecutar pruebas automáticas de UI con Playwright en Linux/Mac
cd "$(dirname "$0")/../frontend"

# Instalar navegadores Playwright (solo la primera vez o si hay actualización)
npx playwright install --with-deps

# Ejecutar pruebas end-to-end
echo "Ejecutando pruebas de UI..."
npm run test:e2e

# Mostrar reporte si existe
if [ -f playwright-report/index.html ]; then
    echo "Abriendo reporte de resultados..."
    xdg-open playwright-report/index.html 2>/dev/null || open playwright-report/index.html 2>/dev/null || echo "Abre el archivo playwright-report/index.html manualmente."
else
    echo "No se encontró el reporte de Playwright."
fi
