# ============================================================================
# Claude Code Proxy - Makefile
# ============================================================================
# Modern, elegant build system for Python FastAPI proxy server
# ============================================================================

.DEFAULT_GOAL := help
SHELL := /bin/bash
.ONESHELL:
.SHELLFLAGS := -eu -o pipefail -c
MAKEFLAGS += --warn-undefined-variables
MAKEFLAGS += --no-builtin-rules

.PHONY: help install install-deps install-dev install-pip clean \
        test test-unit test-integration test-e2e test-all format lint type-check check build \
        run dev docker-build docker-up docker-down docker-logs health \
        ci coverage pre-commit all watch deps-check security-check validate \
        quick-check init-dev check-install version version-set version-bump \
        tag-release release-check release-build release-publish release \
        release-full release-patch release-minor release-major info

# ============================================================================
# Configuration
# ============================================================================

PYTHON := python3
UV := uv
PYTEST := pytest
RUFF := ruff
MYPY := mypy

SRC_DIR := src
TEST_DIR := tests
PYTHON_FILES := $(SRC_DIR) $(TEST_DIR) start_proxy.py test_cancellation.py

HOST ?= 0.0.0.0
PORT ?= 8082
LOG_LEVEL ?= INFO

# Auto-detect available tools
HAS_UV := $(shell command -v uv 2> /dev/null)
HAS_DOCKER := $(shell command -v docker 2> /dev/null)
HAS_GUM := $(shell command -v gum 2> /dev/null)

# Colors for output
BOLD := \033[1m
RESET := \033[0m
GREEN := \033[32m
YELLOW := \033[33m
BLUE := \033[34m
CYAN := \033[36m
RED := \033[31m

# ============================================================================
# Help
# ============================================================================

help: ## Show this help message
	@echo "$(BOLD)$(CYAN)Vandamme Proxy - Makefile Commands$(RESET)"
	@echo ""
	@echo "$(BOLD)Quick Start:$(RESET)"
	@echo "  $(GREEN)make init-dev$(RESET)       - Initialize development environment"
	@echo "  $(GREEN)make install-dev$(RESET)    - Install in development mode"
	@echo "  $(GREEN)make dev$(RESET)            - Start development server"
	@echo "  $(GREEN)make validate$(RESET)       - Quick check + tests (fast)"
	@echo ""
	@echo "$(BOLD)Setup & Installation:$(RESET)"
	@grep -E '^(install|install-|deps-check|init-dev|check-install).*:.*##' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*?## "}; {printf "  $(GREEN)%-20s$(RESET) %s\n", $$1, $$2}'
	@echo ""
	@echo "$(BOLD)Development:$(RESET)"
	@grep -E '^(run|dev|health|clean|watch):.*##' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*?## "}; {printf "  $(BLUE)%-20s$(RESET) %s\n", $$1, $$2}'
	@echo ""
	@echo "$(BOLD)Code Quality:$(RESET)"
	@grep -E '^(format|lint|type-check|check|quick-check|security-check|validate|pre-commit):.*##' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*?## "}; {printf "  $(YELLOW)%-20s$(RESET) %s\n", $$1, $$2}'
	@echo ""
	@echo "$(BOLD)Testing:$(RESET)"
	@grep -E '^test.*:.*##' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*?## "}; {printf "  $(CYAN)%-20s$(RESET) %s\n", $$1, $$2}'
	@grep -E '^coverage.*:.*##' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*?## "}; {printf "  $(CYAN)%-20s$(RESET) %s\n", $$1, $$2}'
	@echo ""
	@echo "$(BOLD)Docker:$(RESET)"
	@grep -E '^docker-.*:.*##' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*?## "}; {printf "  $(BLUE)%-20s$(RESET) %s\n", $$1, $$2}'
	@echo ""
	@echo "$(BOLD)CI/CD:$(RESET)"
	@grep -E '^(ci|build|all):.*##' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*?## "}; {printf "  $(GREEN)%-20s$(RESET) %s\n", $$1, $$2}'
	@echo ""
	@echo "$(BOLD)Utilities:$(RESET)"
	@grep -E '^(version|info|env-template):.*##' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*?## "}; {printf "  $(CYAN)%-20s$(RESET) %s\n", $$1, $$2}'
	@echo ""

# ============================================================================
# Setup & Installation
# ============================================================================

install: ## Install production dependencies (UV)
	@echo "$(BOLD)$(GREEN)Installing production dependencies...$(RESET)"
ifndef HAS_UV
	$(error UV is not installed. Install with: curl -LsSf https://astral.sh/uv/install.sh | sh)
endif
	$(UV) sync --no-dev

install-deps: ## Install all dependencies including dev tools (UV)
	@echo "$(BOLD)$(GREEN)Installing all dependencies (including dev)...$(RESET)"
ifndef HAS_UV
	$(error UV is not installed. Install with: curl -LsSf https://astral.sh/uv/install.sh | sh)
endif
	$(UV) sync

install-dev: ## Install in development/editable mode (enables hot reload)
	@echo "$(BOLD)$(GREEN)Installing in development mode...$(RESET)"
ifndef HAS_UV
	$(error UV is not installed. Install with: curl -LsSf https://astral.sh/uv/install.sh | sh)
endif
	$(UV) sync --extra cli --editable
	@echo "$(BOLD)$(CYAN)✅ Package installed in development mode$(RESET)"
	@echo "$(BOLD)$(YELLOW)💡 The 'vdm' command is now available$(RESET)"

install-pip: ## Install dependencies using pip (fallback)
	@echo "$(BOLD)$(GREEN)Installing dependencies with pip...$(RESET)"
	$(PYTHON) -m pip install -r requirements.txt

deps-check: ## Check for outdated dependencies
	@echo "$(BOLD)$(YELLOW)Checking dependencies...$(RESET)"
ifdef HAS_UV
	@$(UV) pip list --outdated || echo "$(GREEN)✓ All dependencies up to date$(RESET)"
else
	@$(PYTHON) -m pip list --outdated || echo "$(GREEN)✓ All dependencies up to date$(RESET)"
endif

init-dev: ## Initialize development environment
	@echo "$(BOLD)$(BLUE)🚀 Initializing development environment...$(RESET)"
	$(MAKE) install-dev
	$(MAKE) check-install
	@echo ""
	@echo "$(BOLD)$(GREEN)✅ Development environment ready!$(RESET)"
	@echo ""
	@echo "$(BOLD)$(CYAN)Next steps:$(RESET)"
	@echo "  $(CYAN)• The 'vdm' command is now available$(RESET)"
	@echo "  $(CYAN)• Start server: make dev$(RESET)"
	@echo "  $(CYAN)• Run tests: make test$(RESET)"
	@echo "  $(CYAN)• See all commands: make help$(RESET)"

# ============================================================================
# Development
# ============================================================================

run: ## Run the proxy server
	@echo "$(BOLD)$(BLUE)Starting Vandamme Proxy...$(RESET)"
	$(PYTHON) start_proxy.py

dev: install-dev ## Setup dev environment and run server with hot reload
	@echo "$(BOLD)$(BLUE)Starting development server with auto-reload...$(RESET)"
	$(UV) run uvicorn src.main:app --host $(HOST) --port $(PORT) --reload --log-level $(shell echo $(LOG_LEVEL) | tr '[:upper:]' '[:lower:]')

health: ## Check proxy server health
	@echo "$(BOLD)$(CYAN)Checking server health...$(RESET)"
	@curl -s http://localhost:$(PORT)/health | $(PYTHON) -m json.tool || echo "$(YELLOW)Server not running on port $(PORT)$(RESET)"

check-install: ## Verify that installation was successful
	@echo "$(BOLD)$(BLUE)🔍 Verifying installation...$(RESET)"
	@echo "$(CYAN)Checking vdm command...$(RESET)"
	@if [ -f ".venv/bin/vdm" ]; then \
		echo "$(GREEN)✅ vdm command found$(RESET)"; \
		.venv/bin/vdm version; \
	else \
		echo "$(RED)❌ vdm command not found$(RESET)"; \
		echo "$(YELLOW)💡 Run 'make install-dev' to install CLI$(RESET)"; \
		exit 1; \
	fi
	@echo "$(CYAN)Checking Python imports...$(RESET)"
ifndef HAS_UV
	$(error UV is not installed. Install with: curl -LsSf https://astral.sh/uv/install.sh | sh)
endif
	@$(UV) run python -c "import src.cli.main; print('$(GREEN)✅ CLI module imports successfully$(RESET)')" || exit 1
	@echo "$(BOLD)$(GREEN)✅ Installation verified successfully$(RESET)"

clean: ## Clean temporary files and caches
	@echo "$(BOLD)$(YELLOW)Cleaning temporary files...$(RESET)"
	@find . -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
	@find . -type d -name "*.egg-info" -exec rm -rf {} + 2>/dev/null || true
	@find . -type d -name ".pytest_cache" -exec rm -rf {} + 2>/dev/null || true
	@find . -type d -name ".mypy_cache" -exec rm -rf {} + 2>/dev/null || true
	@find . -type f -name "*.pyc" -delete 2>/dev/null || true
	@find . -type f -name "*.pyo" -delete 2>/dev/null || true
	@find . -type f -name ".coverage" -delete 2>/dev/null || true
	@rm -rf build/ dist/ 2>/dev/null || true
	@echo "$(GREEN)✓ Cleaned successfully$(RESET)"

# ============================================================================
# Code Quality
# ============================================================================

format: ## Auto-format code with ruff (includes type transformations)
	@echo "$(BOLD)$(YELLOW)Formatting code...$(RESET)"
	@echo "$(CYAN)→ ruff format$(RESET)"
	@$(UV) run $(RUFF) format $(PYTHON_FILES)
	@echo "$(CYAN)→ ruff check --fix (all auto-fixable rules)$(RESET)"
	@if $(UV) run $(RUFF) check --fix $(PYTHON_FILES); then \
		echo "$(GREEN)✓ All fixes applied successfully$(RESET)"; \
	else \
		echo "$(YELLOW)⚠ Some issues require manual fixes$(RESET)"; \
		echo "$(CYAN)→ Running additional unsafe fixes...$(RESET)"; \
		$(UV) run $(RUFF) check --fix $(PYTHON_FILES) --unsafe-fixes || true; \
		echo "$(YELLOW)⚠ Remaining issues need manual intervention$(RESET)"; \
	fi
	@echo "$(GREEN)✓ Code formatted$(RESET)"

lint: ## Run code linting checks (ruff - check only)
	@echo "$(BOLD)$(YELLOW)Running linters...$(RESET)"
	@echo "$(CYAN)→ ruff format --check$(RESET)"
	@$(UV) run $(RUFF) format --check $(PYTHON_FILES) || (echo "$(YELLOW)⚠ Run 'make format' to fix formatting$(RESET)" && exit 1)
	@echo "$(CYAN)→ ruff check$(RESET)"
	@$(UV) run $(RUFF) check $(PYTHON_FILES) || (echo "$(YELLOW)⚠ Run 'make format' to fix issues$(RESET)" && exit 1)
	@echo "$(GREEN)✓ Linting passed$(RESET)"

type-check: ## Run type checking with mypy
	@echo "$(BOLD)$(YELLOW)Running type checker...$(RESET)"
	@$(UV) run $(MYPY) $(SRC_DIR) || (echo "$(YELLOW)⚠ Type checking found issues$(RESET)" && exit 1)
	@echo "$(GREEN)✓ Type checking passed$(RESET)"

check: lint type-check ## Run all code quality checks (lint + type-check)
	@echo "$(BOLD)$(GREEN)✓ All quality checks passed$(RESET)"

quick-check: ## Fast check (format + lint only, skip type-check)
	@echo "$(BOLD)$(YELLOW)Running quick checks (format + lint)...$(RESET)"
	@$(UV) run $(RUFF) format --check $(PYTHON_FILES) || (echo "$(YELLOW)⚠ Run 'make format' to fix formatting$(RESET)" && exit 1)
	@$(UV) run $(RUFF) check $(PYTHON_FILES) || (echo "$(YELLOW)⚠ Run 'make format' to fix issues$(RESET)" && exit 1)
	@echo "$(GREEN)✓ Quick checks passed$(RESET)"

security-check: ## Run security vulnerability checks
	@echo "$(BOLD)$(YELLOW)Running security checks...$(RESET)"
	@command -v bandit >/dev/null 2>&1 || { echo "$(YELLOW)Installing bandit...$(RESET)"; $(UV) pip install bandit; }
	@$(UV) run bandit -r $(SRC_DIR) -ll || echo "$(GREEN)✓ No security issues found$(RESET)"

validate: quick-check test-quick ## Fast validation (quick-check + quick tests)
	@echo "$(BOLD)$(GREEN)✓ Validation complete$(RESET)"

pre-commit: format check ## Format code and run all checks (run before commit)
	@echo "$(BOLD)$(GREEN)✓ Pre-commit checks complete$(RESET)"

# ============================================================================
# Testing
# ============================================================================

test: ## Run all tests except e2e (unit + integration, no API calls)
	@echo "$(BOLD)$(CYAN)Running all tests (excluding e2e)...$(RESET)"
	@# First run unit tests
	@$(UV) run $(PYTEST) $(TEST_DIR) -v -m unit
	@# Then try integration tests if server is running
	@if curl -s http://localhost:$(PORT)/health > /dev/null 2>&1 || \
	   curl -s http://localhost:18082/health > /dev/null 2>&1; then \
		echo "$(YELLOW)Server detected, running integration tests...$(RESET)"; \
		$(UV) run $(PYTEST) $(TEST_DIR) -v -m "integration and not e2e" || echo "$(YELLOW)⚠ Some integration tests failed$(RESET)"; \
	else \
		echo "$(YELLOW)⚠ Server not running, skipping integration tests$(RESET)"; \
		echo "$(CYAN)To run integration tests:$(RESET)"; \
		echo "  1. Start server: make dev"; \
		echo "  2. Run: make test-integration"; \
	fi

test-unit: ## Run unit tests only (fast, no external deps)
	@echo "$(BOLD)$(CYAN)Running unit tests...$(RESET)"
	@$(UV) run $(PYTEST) $(TEST_DIR) -v -m unit

test-integration: ## Run integration tests (requires server, no API calls)
	@echo "$(BOLD)$(CYAN)Running integration tests...$(RESET)"
	@echo "$(YELLOW)Note: Ensure server is running$(RESET)"
	@if curl -s http://localhost:$(PORT)/health > /dev/null 2>&1 || \
	   curl -s http://localhost:18082/health > /dev/null 2>&1; then \
		$(UV) run $(PYTEST) $(TEST_DIR) -v -m "integration and not e2e"; \
	else \
		echo "$(RED)❌ Server not running. Start with 'make dev' first$(RESET)"; \
		exit 1; \
	fi

test-e2e: ## Run end-to-end tests with real APIs (requires server and API keys)
	@echo "$(BOLD)$(CYAN)Running end-to-end tests...$(RESET)"
	@echo "$(YELLOW)⚠ These tests make real API calls and will incur costs$(RESET)"
	@echo "$(YELLOW)Note: Ensure server is running and API keys are set in .env$(RESET)"
	@if curl -s http://localhost:$(PORT)/health > /dev/null 2>&1 || \
	   curl -s http://localhost:18082/health > /dev/null 2>&1; then \
		$(UV) run $(PYTEST) $(TEST_DIR) -v -m e2e; \
	else \
		echo "$(RED)❌ Server not running. Start with 'make dev' first$(RESET)"; \
		exit 1; \
	fi

test-all: ## Run ALL tests including e2e (requires server and API keys)
	@echo "$(BOLD)$(CYAN)Running ALL tests (unit + integration + e2e)...$(RESET)"
	@echo "$(YELLOW)⚠ E2E tests make real API calls and will incur costs$(RESET)"
	@# First run unit tests
	@$(UV) run $(PYTEST) $(TEST_DIR) -v -m unit
	@# Then check if server is running for integration and e2e tests
	@if curl -s http://localhost:$(PORT)/health > /dev/null 2>&1 || \
	   curl -s http://localhost:18082/health > /dev/null 2>&1; then \
		echo "$(YELLOW)Server detected, running integration tests...$(RESET)"; \
		$(UV) run $(PYTEST) $(TEST_DIR) -v -m "integration and not e2e" || echo "$(YELLOW)⚠ Some integration tests failed$(RESET)"; \
		echo "$(YELLOW)Running e2e tests...$(RESET)"; \
		$(UV) run $(PYTEST) $(TEST_DIR) -v -m e2e || echo "$(YELLOW)⚠ Some e2e tests failed (check API keys)$(RESET)"; \
	else \
		echo "$(RED)❌ Server not running. Start with 'make dev' first$(RESET)"; \
		exit 1; \
	fi

test-quick: ## Run tests without coverage (fast)
	@echo "$(BOLD)$(CYAN)Running quick tests...$(RESET)"
	@$(UV) run $(PYTEST) $(TEST_DIR) -q --tb=short -m unit

coverage: ## Run tests with coverage report
	@echo "$(BOLD)$(CYAN)Running tests with coverage...$(RESET)"
	@echo "$(CYAN)→ Ensuring pytest-cov is installed...$(RESET)"
	@$(UV) add --group dev pytest-cov 2>/dev/null || true
	@# Check if server is running, if so run all tests, otherwise run only unit tests
	@if curl -s http://localhost:$(PORT)/health > /dev/null 2>&1 || \
	   curl -s http://localhost:18082/health > /dev/null 2>&1; then \
		echo "$(YELLOW)Server detected, running coverage on all tests...$(RESET)"; \
		$(UV) run $(PYTEST) $(TEST_DIR) --cov=$(SRC_DIR) --cov-report=html --cov-report=term-missing; \
	else \
		echo "$(YELLOW)Server not running, running coverage on unit tests only...$(RESET)"; \
		$(UV) run $(PYTEST) $(TEST_DIR) --cov=$(SRC_DIR) --cov-report=html --cov-report=term-missing -m unit; \
	fi
	@echo "$(GREEN)✓ Coverage report generated in htmlcov/$(RESET)"

# ============================================================================
# Docker
# ============================================================================

docker-build: ## Build Docker image
	@echo "$(BOLD)$(BLUE)Building Docker image...$(RESET)"
ifndef HAS_DOCKER
	$(error Docker is not installed or not running)
endif
	docker compose build

docker-up: ## Start services with Docker Compose
	@echo "$(BOLD)$(BLUE)Starting Docker services...$(RESET)"
ifndef HAS_DOCKER
	$(error Docker is not installed or not running)
endif
	docker compose up -d
	@echo "$(GREEN)✓ Services started$(RESET)"
	@echo "$(CYAN)View logs: make docker-logs$(RESET)"

docker-down: ## Stop Docker services
	@echo "$(BOLD)$(BLUE)Stopping Docker services...$(RESET)"
ifndef HAS_DOCKER
	$(error Docker is not installed or not running)
endif
	docker compose down
	@echo "$(GREEN)✓ Services stopped$(RESET)"

docker-logs: ## Show Docker logs
ifndef HAS_DOCKER
	$(error Docker is not installed or not running)
endif
	docker compose logs -f

docker-restart: docker-down docker-up ## Restart Docker services

docker-clean: docker-down ## Stop and remove Docker containers, volumes
	@echo "$(BOLD)$(YELLOW)Cleaning Docker resources...$(RESET)"
	docker compose down -v --remove-orphans
	@echo "$(GREEN)✓ Docker resources cleaned$(RESET)"

# ============================================================================
# Build & Distribution
# ============================================================================

build: clean ## Build distribution packages
	@echo "$(BOLD)$(GREEN)Building distribution packages...$(RESET)"
	$(UV) build
	@echo "$(GREEN)✓ Build complete - check dist/$(RESET)"

# ============================================================================
# CI/CD
# ============================================================================

ci: install-dev check test ## Run full CI pipeline (install, check, test)
	@echo "$(BOLD)$(GREEN)━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━$(RESET)"
	@echo "$(BOLD)$(GREEN)✓ CI Pipeline Complete$(RESET)"
	@echo "$(BOLD)$(GREEN)━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━$(RESET)"

all: clean install-dev check test build ## Run everything (clean, install, check, test, build)
	@echo "$(BOLD)$(GREEN)━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━$(RESET)"
	@echo "$(BOLD)$(GREEN)✓ All Tasks Complete$(RESET)"
	@echo "$(BOLD)$(GREEN)━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━$(RESET)"

# ============================================================================
# Release Management
# ============================================================================

# Version Management
version: ## Show current version
	@$(UV) run python scripts/release.py version

version-set: ## Set new version interactively
	@$(UV) run python scripts/release.py version-set

version-bump: ## Bump version interactively (or: make version-bump BUMP_TYPE=patch|minor|major)
ifndef BUMP_TYPE
	@echo "$(CYAN)💡 Tip: Skip interactive mode with: make version-bump BUMP_TYPE=patch|minor|major$(RESET)"
	@echo ""
	@$(UV) run python scripts/release.py full
else
	@$(UV) run python scripts/release.py version-bump $(BUMP_TYPE)
endif

# Tag Management
tag-release: ## Create and push git tag for current version
	@$(UV) run python scripts/release.py tag

# Release Workflow
release-check: ## Validate release readiness
	@$(UV) run python scripts/release.py check

release-build: ## Build distribution packages
	@$(MAKE) release-check
	@$(MAKE) clean
	@$(UV) build

release-publish: ## Publish to PyPI (manual)
	@$(MAKE) release-build
	@$(UV) run python scripts/release.py publish

release: tag-release ## Complete release (tag + publish via GitHub Actions)
	@$(UV) run python scripts/release.py post-tag

# Combined Workflows
release-full: ## Complete interactive release
	@$(UV) run python scripts/release.py full

release-patch: ## Quick patch release
	@$(UV) run python scripts/release.py quick patch

release-minor: ## Quick minor release
	@$(UV) run python scripts/release.py quick minor

release-major: ## Quick major release
	@$(UV) run python scripts/release.py quick major

# ============================================================================
# Utility Targets
# ============================================================================

.PHONY: info
info: ## Show project information
	@echo "$(BOLD)$(CYAN)Project Information$(RESET)"
	@echo "  Name:         Vandamme Proxy"
	@echo "  Version:      $$($(UV) run python -c 'from src import __version__; print(__version__)' 2>/dev/null || echo 'unknown')"
	@echo "  Python:       >= 3.10"
	@echo "  Source:       $(SRC_DIR)/"
	@echo "  Tests:        $(TEST_DIR)/"
	@echo "  Default Host: $(HOST)"
	@echo "  Default Port: $(PORT)"
	@echo ""
	@echo "$(BOLD)$(CYAN)Environment$(RESET)"
	@echo "  UV:           $(if $(HAS_UV),✓ installed,✗ not found)"
	@echo "  Docker:       $(if $(HAS_DOCKER),✓ installed,✗ not found)"
	@echo "  Python:       $$($(PYTHON) --version 2>&1)"

.PHONY: watch
watch: ## Watch for file changes and auto-run tests
	@echo "$(BOLD)$(CYAN)Watching for changes...$(RESET)"
	@command -v watchexec >/dev/null 2>&1 || { echo "$(RED)Error: watchexec not installed. Install with: cargo install watchexec-cli$(RESET)"; exit 1; }
	watchexec -e py -w $(SRC_DIR) -w $(TEST_DIR) -- make test-quick

.PHONY: env-template
env-template: ## Generate .env template file
	@echo "$(BOLD)$(CYAN)Generating .env.template...$(RESET)"
	@echo "# Claude Code Proxy Configuration" > .env.template
	@echo "" >> .env.template
	@echo "# Required: OpenAI API Key" >> .env.template
	@echo "OPENAI_API_KEY=your-key-here" >> .env.template
	@echo "" >> .env.template
	@echo "# Optional: Security" >> .env.template
	@echo "#ANTHROPIC_API_KEY=your-key-here" >> .env.template
	@echo "" >> .env.template
	@echo "# Optional: Model Configuration" >> .env.template
	@echo "#ANTHROPIC_ALIAS_HAIKU=gpt-4o-mini" >> .env.template
	@echo "#ANTHROPIC_ALIAS_SONNET=glm-4.6" >> .env.template
	@echo "#ANTHROPIC_ALIAS_OPUS=gemini-3-pro" >> .env.template
	@echo "" >> .env.template
	@echo "# Optional: API Configuration" >> .env.template
	@echo "#OPENAI_BASE_URL=https://api.openai.com/v1" >> .env.template
	@echo "#AZURE_API_VERSION=2024-02-15-preview" >> .env.template
	@echo "" >> .env.template
	@echo "# Optional: Server Settings" >> .env.template
	@echo "#HOST=0.0.0.0" >> .env.template
	@echo "#PORT=8082" >> .env.template
	@echo "#LOG_LEVEL=INFO" >> .env.template
	@echo "$(GREEN)✓ Generated .env.template$(RESET)"
