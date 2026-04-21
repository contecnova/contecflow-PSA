@echo off
REM Script para ejecutar pruebas automáticas de UI con Playwright en Windows
cd /d "%~dp0frontend"

REM Instalar navegadores Playwright (solo la primera vez o si hay actualización)
npx playwright install --with-deps

REM Ejecutar pruebas end-to-end
echo Ejecutando pruebas de UI...
npm run test:e2e

REM Mostrar reporte si existe
if exist playwright-report\index.html (
    echo Abriendo reporte de resultados...
    start playwright-report\index.html
) else (
    echo No se encontró el reporte de Playwright.
)

pause