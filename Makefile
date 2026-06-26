# ══════════════════════════════════════════════════════════════════════════════
# Contecflow PSA — Makefile
# Uso: make <target>
# ══════════════════════════════════════════════════════════════════════════════

.PHONY: help install dev docs smoke health test test-fast test-coverage test-e2e \
        build build-frontend lint migrate seed clean

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
	pip install -r requirements.txt
	pip install pytest pytest-asyncio httpx coverage pytest-html
	@echo "$(YELLOW)Instalando dependencias frontend...$(RESET)"
	cd frontend && npm install
	@echo "$(GREEN)✅ Instalación completa$(RESET)"

install-e2e: ## Instala Playwright para tests E2E
	pip install playwright pytest-playwright
	playwright install chromium firefox
	@echo "$(GREEN)✅ Playwright instalado$(RESET)"

# ── Desarrollo ─────────────────────────────────────────────────────────────────
dev: ## Inicia backend y frontend en modo desarrollo
	@echo "$(CYAN)Iniciando Contecflow PSA en modo desarrollo...$(RESET)"
	@make -j2 dev-backend dev-frontend

dev-backend: ## Solo el backend
	@if [ -x .venv/bin/python ]; then \
		PY=.venv/bin/python; \
	elif [ -x venv/bin/python ]; then \
		PY=venv/bin/python; \
	else \
		PY=python3; \
	fi; \
	echo "$(CYAN)Backend con $$PY$(RESET)"; \
	$$PY -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8000

dev-frontend: ## Solo el frontend
	cd frontend && npm run dev -- --host 127.0.0.1 --port 3000

docs: ## Verifica Swagger /api/v1/docs (HTTP 200 + CSP compatible)
	@echo "$(CYAN)Verificando documentación OpenAPI...$(RESET)"
	@status=$$(curl -s -o /dev/null -w "%{http_code}" http://127.0.0.1:8000/api/v1/docs || echo "000"); \
	if [ "$$status" != "200" ]; then \
		echo "$(YELLOW)⚠ /api/v1/docs no responde (HTTP $$status). Arranca backend primero.$(RESET)"; \
		exit 1; \
	fi; \
	csp=$$(curl -i -s http://127.0.0.1:8000/api/v1/docs | awk -F': ' 'tolower($$1)=="content-security-policy"{print $$2}' | tr -d '\r'); \
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
	@curl -sf http://127.0.0.1:8000/health >/dev/null || { echo "$(YELLOW)⚠ Backend no responde en /health$(RESET)"; exit 1; }
	@status=$$(curl -s -o /dev/null -w "%{http_code}" http://127.0.0.1:8000/api/v1/docs || echo "000"); \
	if [ "$$status" != "200" ]; then \
		echo "$(YELLOW)⚠ /api/v1/docs no responde (HTTP $$status)$(RESET)"; \
		exit 1; \
	fi
	@$(PYTHON) scripts/smoke_check.py

# ── Tests ──────────────────────────────────────────────────────────────────────
test: ## Ejecuta todos los tests de API
	@echo "$(CYAN)Ejecutando tests de backend...$(RESET)"
	$(PYTHON) -m pytest tests/ -v --tb=short

test-fast: ## Tests rápidos (excluye los lentos)
	$(PYTHON) -m pytest tests/ -v --tb=short -m "not slow" --timeout=10

test-smoke: ## Solo smoke tests (sanidad básica)
	$(PYTHON) -m pytest tests/ -v --tb=short -m "smoke or auth"

test-module: ## Tests de un módulo específico: make test-module M=test_okrs
	$(PYTHON) -m pytest tests/$(M).py -v --tb=long

test-coverage: ## Tests con reporte de cobertura HTML
	@echo "$(CYAN)Ejecutando tests con cobertura...$(RESET)"
	coverage run -m pytest tests/ -v --tb=short
	coverage report
	coverage html
	@echo "$(GREEN)✅ Reporte en htmlcov/index.html$(RESET)"

quality-coverage-75: ## Puerta local de cobertura backend >= 75% (sin CI)
	@echo "$(CYAN)Validando cobertura backend >= 75%...$(RESET)"
	coverage run -m pytest tests/ -q
	coverage report --fail-under=75

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
migrate: ## Aplica las migraciones de Alembic
	alembic upgrade head

migrate-create: ## Crea una migración nueva: make migrate-create MSG="descripcion"
	alembic revision --autogenerate -m "$(MSG)"

seed: ## Carga datos de ejemplo
	$(PYTHON) scripts/seed_full_data.py

init-admin: ## Crea el usuario admin inicial
	bash init_admin.sh

# ── Limpieza ───────────────────────────────────────────────────────────────────
clean: ## Limpia archivos temporales y caches
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	find . -type f -name "*.pyc" -delete 2>/dev/null || true
	find . -name "*.db" -not -name "contecflow.db" -delete 2>/dev/null || true
	rm -rf htmlcov/ .coverage coverage.xml test-results/ dist/
	@echo "$(GREEN)✅ Limpieza completa$(RESET)"

# ── Seguridad ────────────────────────────────────────────────────────────────
pip-audit: ## Analiza dependencias Python en busca de vulnerabilidades
	pip install pip-audit
	pip-audit

# ── Rotación de claves ───────────────────────────────────────────────────────
rotate-keys: ## Recordatorio/manual para rotar claves y secretos
	@echo "Recuerda rotar periódicamente las claves y secretos de API, JWT, OAuth y webhooks."
	@echo "Actualiza los valores en .env, Azure, GitHub Secrets y otros orígenes seguros."
	@echo "Puedes usar scripts/rotate_keys.sh para automatizar la rotación si está disponible."
# ── Health check ───────────────────────────────────────────────────────────────
health: ## Verifica que el backend responde
	@curl -sf http://localhost:8000/health && \
		echo "$(GREEN)✅ Backend OK$(RESET)" || \
		echo "$(YELLOW)⚠ Backend no responde$(RESET)"

# ── Regression ───────────────────────────────────────────────────────────────
regression-backend: ## Ejecuta 3 tests de regresión backend
	$(PYTHON) -m pytest tests/test_regression_api_get_smoke.py tests/test_regression_api_operations_smoke.py tests/test_regression_invoices_created_at.py -v --tb=short

regression-e2e: ## Ejecuta 4 tests de regresion E2E
	$(PYTHON) -m pytest tests_e2e/test_e2e_sidebar_menu_smoke.py tests_e2e/test_e2e_dashboard_reporting_smoke.py tests_e2e/test_e2e_all_pages_regression.py tests_e2e/test_e2e_public_protected_regression.py -v --tb=short

regression-all: regression-backend regression-e2e ## Ejecuta toda la regresión
