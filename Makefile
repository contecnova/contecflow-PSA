# ══════════════════════════════════════════════════════════════════════════════
# Contecflow PSA — Makefile
# Uso: make <target>
# ══════════════════════════════════════════════════════════════════════════════

.PHONY: help install install-e2e dev dev-backend dev-frontend docs smoke health \
        test test-serial test-fast test-smoke test-module test-coverage test-e2e \
        quality-coverage-75 quality-types-75 quality-p3 build build-frontend \
        migrate migrate-create seed seed-full init-admin backup restore clean \
        pip-audit audit audit-fast audit-info rotate-keys \
        regression-backend regression-e2e regression-all

# ── Puertos (23-11-2026: estaban fijos) — make dev BACKEND_PORT=8010 ─────────
BACKEND_PORT  ?= 8000
FRONTEND_PORT ?= 3000

# ── Python interpreter — prefers venv, falls back to python3 ─────────────────
PYTHON := $(shell \
  if [ -x .venv/bin/python ]; then echo .venv/bin/python; \
  elif [ -x venv/bin/python ]; then echo venv/bin/python; \
  else command -v python3 2>/dev/null || echo python3; fi)

# ── Colores ────────────────────────────────────────────────────────────────────
GREEN  := \033[0;32m
YELLOW := \033[1;33m
CYAN   := \033[0;36m
RESET  := \033[0m

help: ## Muestra esta ayuda
	@echo ""
	@echo "$(CYAN)Contecflow PSA — comandos disponibles:$(RESET)"
	@echo ""
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | \
		awk 'BEGIN {FS = ":.*?## "}; {printf "  $(GREEN)%-20s$(RESET) %s\n", $$1, $$2}'
	@echo ""

# ── Instalación ────────────────────────────────────────────────────────────────
install: ## Instala todas las dependencias (backend + frontend)
	@echo "$(YELLOW)Instalando dependencias Python...$(RESET)"
	$(PYTHON) -m pip install -r requirements.txt
	@echo "$(YELLOW)Instalando dependencias frontend...$(RESET)"
	cd frontend && npm install
	@echo "$(GREEN)✅ Instalación completa$(RESET)"

install-e2e: ## Instala los navegadores de Playwright para tests E2E
	$(PYTHON) -m playwright install chromium firefox
	@echo "$(GREEN)✅ Playwright instalado$(RESET)"

# ── Desarrollo ─────────────────────────────────────────────────────────────────
dev: ## Inicia backend y frontend en modo desarrollo
	@echo "$(CYAN)Iniciando Contecflow PSA en modo desarrollo...$(RESET)"
	@$(MAKE) -j2 dev-backend dev-frontend

dev-backend: ## Solo el backend
	@if [ -x .venv/bin/python ]; then \
		PY=.venv/bin/python; \
	elif [ -x venv/bin/python ]; then \
		PY=venv/bin/python; \
	else \
		PY=python3; \
	fi; \
	echo "$(CYAN)Backend con $$PY$(RESET)"; \
	$$PY -m uvicorn app.main:app --reload --host 127.0.0.1 --port $(BACKEND_PORT)

dev-frontend: ## Solo el frontend
	cd frontend && API_URL=http://localhost:$(BACKEND_PORT) npm run dev -- --host 127.0.0.1 --port $(FRONTEND_PORT)

docs: ## Verifica Swagger /api/v1/docs (HTTP 200 + CSP compatible)
	@echo "$(CYAN)Verificando documentación OpenAPI...$(RESET)"
	@status=$$(curl -s -o /dev/null -w "%{http_code}" http://127.0.0.1:$(BACKEND_PORT)/api/v1/docs || echo "000"); \
	if [ "$$status" != "200" ]; then \
		echo "$(YELLOW)⚠ /api/v1/docs no responde (HTTP $$status). Arranca backend primero.$(RESET)"; \
		exit 1; \
	fi; \
	csp=$$(curl -i -s http://127.0.0.1:$(BACKEND_PORT)/api/v1/docs | awk -F': ' 'tolower($$1)=="content-security-policy"{print $$2}' | tr -d '\r'); \
	echo "$(GREEN)✅ /api/v1/docs responde 200$(RESET)"; \
	if echo "$$csp" | grep -qi "cdn.jsdelivr.net"; then \
		echo "$(GREEN)✅ CSP docs permite assets de Swagger$(RESET)"; \
	else \
		echo "$(YELLOW)⚠ CSP docs no incluye cdn.jsdelivr.net (puede causar pantalla en blanco)$(RESET)"; \
		echo "CSP actual: $$csp"; \
		exit 1; \
	fi

smoke: ## Verificación integral: health + docs + login + ticket sin cliente
	@echo "$(CYAN)Ejecutando smoke integral...$(RESET)"
	@curl -sf http://127.0.0.1:$(BACKEND_PORT)/health >/dev/null || { echo "$(YELLOW)⚠ Backend no responde en /health$(RESET)"; exit 1; }
	@status=$$(curl -s -o /dev/null -w "%{http_code}" http://127.0.0.1:$(BACKEND_PORT)/api/v1/docs || echo "000"); \
	if [ "$$status" != "200" ]; then \
		echo "$(YELLOW)⚠ /api/v1/docs no responde (HTTP $$status)$(RESET)"; \
		exit 1; \
	fi
	@$(PYTHON) scripts/smoke_check.py

# ── Tests ──────────────────────────────────────────────────────────────────────
test: ## Ejecuta todos los tests de API (en paralelo con xdist)
	@echo "$(CYAN)Ejecutando tests de backend...$(RESET)"
	$(PYTHON) -m pytest tests/ -n auto --tb=short

test-serial: ## Igual que test, pero en un solo proceso (para depurar)
	$(PYTHON) -m pytest tests/ -v --tb=short

test-fast: ## Tests rápidos (excluye los lentos; en paralelo)
	$(PYTHON) -m pytest tests/ -n auto --tb=short -m "not slow"

test-smoke: ## Solo smoke tests (sanidad básica)
	$(PYTHON) -m pytest tests/ -v --tb=short -m "smoke or auth"

test-module: ## Tests de un módulo específico: make test-module M=test_okrs
	$(PYTHON) -m pytest tests/$(M).py -v --tb=long

test-coverage: ## Tests con reporte de cobertura HTML
	@echo "$(CYAN)Ejecutando tests con cobertura...$(RESET)"
	$(PYTHON) -m coverage run -m pytest tests/ -v --tb=short
	$(PYTHON) -m coverage report
	$(PYTHON) -m coverage html
	@echo "$(GREEN)✅ Reporte en htmlcov/index.html$(RESET)"

quality-coverage-75: ## Puerta local de cobertura backend >= 75% (sin CI)
	@echo "$(CYAN)Validando cobertura backend >= 75%...$(RESET)"
	$(PYTHON) -m coverage run -m pytest tests/ -q
	$(PYTHON) -m coverage report --fail-under=75

quality-types-75: ## Puerta local de type coverage frontend >= 75% (sin CI)
	@echo "$(CYAN)Validando type coverage frontend >= 75%...$(RESET)"
	cd frontend && npm run type:coverage

quality-p3: ## Quality gate local P3 (coverage + type coverage + a11y report)
	@echo "$(CYAN)Ejecutando quality gate local P3...$(RESET)"
	$(MAKE) quality-coverage-75
	cd frontend && npm run quality:p3
	@echo "$(GREEN)✅ Quality gate local P3 OK$(RESET)"

test-e2e: ## Tests E2E con Playwright
	@echo "$(CYAN)Ejecutando tests E2E...$(RESET)"
	$(PYTHON) -m pytest tests_e2e/ -v --tb=short --headed

# ── Build ──────────────────────────────────────────────────────────────────────
build: build-frontend ## Build completo (frontend)
	@echo "$(GREEN)✅ Build completo$(RESET)"

build-frontend: ## Build del frontend (Vite)
	@echo "$(CYAN)Building frontend...$(RESET)"
	cd frontend && npm run build
	@echo "$(GREEN)✅ Frontend build OK$(RESET)"

# ── Base de datos ──────────────────────────────────────────────────────────────
# Igual que setup.sh/setup.bat: scripts/migrar.py (copia previa si hay
# revisiones destructivas) y comprobación del esquema real.
migrate: ## Aplica las migraciones (con copia previa si hay destructivas)
	$(PYTHON) scripts/migrar.py
	$(PYTHON) scripts/comprobar_esquema.py

migrate-create: ## Crea una migración nueva: make migrate-create MSG="descripcion"
	$(PYTHON) -m alembic revision --autogenerate -m "$(MSG)"

seed: ## Carga los datos demo (lo mismo que setup demo; solo development/test)
	$(PYTHON) -m app.db.seed

seed-full: ## Datos masivos 2025-2027 sobre la demo (solo development/test)
	$(PYTHON) scripts/seed_full_data.py

# 23-11-2026: llamaba a un init_admin.sh que no existía.
init-admin: ## Crea o restablece el admin con SUPERADMIN_EMAIL/PASSWORD del .env (no borra nada)
	$(PYTHON) scripts/reset_to_admin_only.py --solo-admin

backup: ## Copia local: base (SQLite o PostgreSQL) + uploads/ en backups/
	$(PYTHON) scripts/copia_local.py backup

restore: ## Restaura una copia local: make restore COPIA=backups/contecflow-local-...
	@test -n "$(COPIA)" || { echo "Uso: make restore COPIA=backups/contecflow-local-..."; exit 1; }
	$(PYTHON) scripts/copia_local.py restore "$(COPIA)"

# ── Limpieza ───────────────────────────────────────────────────────────────────
clean: ## Limpia archivos temporales y caches
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	find . -type f -name "*.pyc" -delete 2>/dev/null || true
	rm -rf htmlcov/ .coverage coverage.xml test-results/ dist/ .pytest_cache/
	@echo "$(GREEN)✅ Limpieza completa$(RESET)"

# ── Seguridad ────────────────────────────────────────────────────────────────
pip-audit: ## Analiza dependencias Python en busca de vulnerabilidades
	$(PYTHON) -m pip install pip-audit
	$(PYTHON) -m pip_audit -r requirements.txt

# ── Auditoría local completa ─────────────────────────────────────────────────
# Envoltorios finos sobre scripts/ci_local.sh, que es la ÚNICA implementación.
# Este proyecto no usa CI/CD por decisión de diseño, así que ese script es donde
# están reunidos todos los gates. Ojo: `make` no está disponible en todas las
# máquinas del equipo (p. ej. Windows sin GNU Make); ahí hay que invocar el
# script directamente con bash.
audit: ## Pasa todos los gates de calidad en local (bloqueantes + informativos)
	@bash scripts/ci_local.sh

audit-fast: ## Igual que audit pero sin pytest ni informativos (~2 min)
	@bash scripts/ci_local.sh --fast

audit-info: ## Solo los gates informativos (deuda conocida, no bloquean)
	@bash scripts/ci_local.sh --info

# ── Rotación de claves ───────────────────────────────────────────────────────
rotate-keys: ## Rota SECRET_KEY y re-cifra lo guardado (scripts/rotate_keys.sh)
	PY_BIN=$(PYTHON) bash scripts/rotate_keys.sh
# ── Health check ───────────────────────────────────────────────────────────────
health: ## Verifica que el backend responde
	@curl -sf http://localhost:$(BACKEND_PORT)/health && \
		echo "$(GREEN)✅ Backend OK$(RESET)" || \
		echo "$(YELLOW)⚠ Backend no responde$(RESET)"

# ── Regression ───────────────────────────────────────────────────────────────
regression-backend: ## Ejecuta 3 tests de regresión backend
	$(PYTHON) -m pytest tests/test_regression_api_get_smoke.py tests/test_regression_api_operations_smoke.py tests/test_regression_invoices_created_at.py -v --tb=short

regression-e2e: ## Ejecuta 4 tests de regresion E2E
	$(PYTHON) -m pytest tests_e2e/test_e2e_sidebar_menu_smoke.py tests_e2e/test_e2e_dashboard_reporting_smoke.py tests_e2e/test_e2e_all_pages_regression.py tests_e2e/test_e2e_public_protected_regression.py -v --tb=short

regression-all: regression-backend regression-e2e ## Ejecuta toda la regresión
