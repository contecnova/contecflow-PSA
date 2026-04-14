#!/bin/bash
# ─────────────────────────────────────────────────
#  Clarive v21 — Arranque limpio (borra caché Vite)
# ─────────────────────────────────────────────────
set -e
DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$DIR"

echo "🧹 Borrando caché de Vite..."
rm -rf frontend/node_modules/.vite

echo "▶ Arrancando Clarive..."
exec ./setup.sh
