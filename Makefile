# ══════════════════════════════════════════════════════════════════════════════
# Contecflow PSA — Makefile
# Uso: make <target>
# ══════════════════════════════════════════════════════════════════════════════

.PHONY: help install dev docs smoke health test test-fast test-coverage test-e2e \
        build build-frontend lint docker-build docker-up docker-down \
        migrate seed clean

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
	@python3 scripts/smoke_check.py

# ── Tests ──────────────────────────────────────────────────────────────────────
test: ## Ejecuta todos los tests de API
	@echo "$(CYAN)Ejecutando tests de backend...$(RESET)"
	python -m pytest tests/ -v --tb=short

test-fast: ## Tests rápidos (excluye los lentos)
	python -m pytest tests/ -v --tb=short -m "not slow" --timeout=10

test-smoke: ## Solo smoke tests (sanidad básica)
	python -m pytest tests/ -v --tb=short -m "smoke or auth"

test-module: ## Tests de un módulo específico: make test-module M=test_okrs
	python -m pytest tests/$(M).py -v --tb=long

test-coverage: ## Tests con reporte de cobertura HTML
	@echo "$(CYAN)Ejecutando tests con cobertura...$(RESET)"
	coverage run -m pytest tests/ -v --tb=short
	coverage report
	coverage html
	@echo "$(GREEN)✅ Reporte en htmlcov/index.html$(RESET)"

test-ci: ## Tests en modo CI (sin colores, con JUnit XML)
	python -m pytest tests/ \
		--tb=short \
		--junit-xml=test-results/junit.xml \
		-p no:warnings \
		-q
	coverage run -m pytest tests/ -q
	coverage xml -o test-results/coverage.xml

test-e2e: ## Tests E2E con Playwright
	@echo "$(CYAN)Ejecutando tests E2E...$(RESET)"
	python -m pytest tests_e2e/ -v --tb=short --headed

test-e2e-ci: ## Tests E2E en modo CI (headless)
	python -m pytest tests_e2e/ -v --tb=short

# ── Build ──────────────────────────────────────────────────────────────────────
build: build-frontend ## Build completo (frontend)
	@echo "$(GREEN)✅ Build completo$(RESET)"

build-frontend: ## Build del frontend (Vite)
	@echo "$(CYAN)Building frontend...$(RESET)"
	cd frontend && npm run build
	@echo "$(GREEN)✅ Frontend build OK$(RESET)"

# ── Docker ─────────────────────────────────────────────────────────────────────
docker-build: ## Construye las imágenes Docker
	docker compose build

docker-up: ## Levanta todos los servicios
	docker compose up -d
	@echo "$(GREEN)✅ Contecflow corriendo en http://localhost$(RESET)"

docker-down: ## Para todos los servicios
	docker compose down

docker-logs: ## Muestra logs de todos los servicios
	docker compose logs -f

docker-test: ## Ejecuta los tests dentro del contenedor
	docker compose run --rm backend python -m pytest tests/ -v --tb=short

# ── Base de datos ──────────────────────────────────────────────────────────────
migrate: ## Aplica las migraciones de Alembic
	alembic upgrade head

migrate-create: ## Crea una migración nueva: make migrate-create MSG="descripcion"
	alembic revision --autogenerate -m "$(MSG)"

seed: ## Carga datos de ejemplo
	python scripts/seed_data.py

init-admin: ## Crea el usuario admin inicial
	bash init_admin.sh

# ── Limpieza ───────────────────────────────────────────────────────────────────
clean: ## Limpia archivos temporales y caches
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	find . -type f -name "*.pyc" -delete 2>/dev/null || true
	find . -name "*.db" -not -name "contecflow.db" -delete 2>/dev/null || true
	rm -rf htmlcov/ .coverage coverage.xml test-results/ dist/
	@echo "$(GREEN)✅ Limpieza completa$(RESET)"

# ── Health check ───────────────────────────────────────────────────────────────
health: ## Verifica que el backend responde
	@curl -sf http://localhost:8000/health && \
		echo "$(GREEN)✅ Backend OK$(RESET)" || \
		echo "$(YELLOW)⚠ Backend no responde$(RESET)"
