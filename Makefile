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
MAKEFLAGS += --no-print-directory

.PHONY: help dev-env-init dev-deps-sync run dev health clean watch doctor check-install sanitize format lint typecheck security-check validate test test-unit test-integration test-e2e test-all test-quick coverage check check-quick ci build all pre-commit docker-build docker-up docker-down docker-logs docker-restart docker-clean build-cli clean-binaries version version-set version-bump tag-release release-check release-build release-publish release release-full release-patch release-minor release-major info env-template deps-check

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

# Nuitka Configuration
NUITKA := uv run python -m nuitka
BUILD_DIR := dist/nuitka

# Auto-detect available tools
HAS_UV := $(shell command -v uv 2> /dev/null)
HAS_DOCKER := $(shell command -v docker 2> /dev/null)
HAS_GUM := $(shell command -v gum 2> /dev/null)

# Terminal detection
TERM_COLOR := $(shell tput colors 2>/dev/null)
ifeq ($(TERM_COLOR),0)
    # No color support
    BOLD :=
    RESET :=
    GREEN :=
    YELLOW :=
    BLUE :=
    CYAN :=
    RED :=
else
    # Use ANSI codes with printf for better compatibility
    BOLD := \033[1m
    RESET := \033[0m
    GREEN := \033[32m
    YELLOW := \033[33m
    BLUE := \033[34m
    CYAN := \033[36m
    RED := \033[31m
endif

# ============================================================================
# Help
# ============================================================================

help: ## Show this help message
	@printf "$(BOLD)$(CYAN)Vandamme Proxy - Makefile Commands$(RESET)\n"
	@printf "\n"
	@printf "$(BOLD)Quick Start:$(RESET)\n"
	@printf "  $(GREEN)make dev-env-init$(RESET)  - Initialize development environment\n"
	@printf "  $(GREEN)make dev-deps-sync$(RESET) - Install dependencies and CLI\n"
	@printf "  $(GREEN)make dev$(RESET)            - Start development server\n"
	@printf "  $(GREEN)make check-quick$(RESET)    - Fast validation (static + unit tests)\n"
	@printf "  $(GREEN)make doctor$(RESET)         - Environment health check\n"
	@printf "\n"
	@printf "$(BOLD)Environment Setup (dev-* prefix = mutations):$(RESET)\n"
	@grep -E '^(dev-|check-install).*:.*##' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*?## "}; {printf "  $(GREEN)%-20s$(RESET) %s\n", $$1, $$2}'
	@printf "\n"
	@printf "$(BOLD)Code Quality (sanitize = static checks only):$(RESET)\n"
	@grep -E '^(sanitize|format|lint|typecheck|security-check).*:.*##' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*?## "}; {printf "  $(YELLOW)%-20s$(RESET) %s\n", $$1, $$2}'
	@printf "\n"
	@printf "$(BOLD)Merge Gates:$(RESET)\n"
	@grep -E '^(check-?|validate|pre-commit).*:.*##' $(MAKEFILE_LIST) | grep -v 'check-install' | awk 'BEGIN {FS = ":.*?## "}; {printf "  $(GREEN)%-20s$(RESET) %s\n", $$1, $$2}'
	@printf "\n"
	@printf "$(BOLD)Testing:$(RESET)\n"
	@grep -E '^test.*:.*##' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*?## "}; {printf "  $(CYAN)%-20s$(RESET) %s\n", $$1, $$2}'
	@grep -E '^coverage.*:.*##' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*?## "}; {printf "  $(CYAN)%-20s$(RESET) %s\n", $$1, $$2}'
	@printf "\n"
	@printf "$(BOLD)Development:$(RESET)\n"
	@grep -E '^(run|dev|health|clean|watch|doctor):.*##' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*?## "}; {printf "  $(BLUE)%-20s$(RESET) %s\n", $$1, $$2}'
	@printf "\n"
	@printf "$(BOLD)Docker:$(RESET)\n"
	@grep -E '^docker-.*:.*##' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*?## "}; {printf "  $(BLUE)%-20s$(RESET) %s\n", $$1, $$2}'
	@printf "\n"
	@printf "$(BOLD)Binary Builds:$(RESET)\n"
	@grep -E '^(build-.*|clean-binaries):.*##' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*?## "}; {printf "  $(GREEN)%-20s$(RESET) %s\n", $$1, $$2}'
	@printf "\n"
	@printf "$(BOLD)CI/CD:$(RESET)\n"
	@grep -E '^(ci|build|all).*:.*##' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*?## "}; {printf "  $(GREEN)%-20s$(RESET) %s\n", $$1, $$2}'
	@printf "\n"
	@printf "$(BOLD)Release Management:$(RESET)\n"
	@grep -E '^(version|tag-|release-).*:.*##' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*?## "}; {printf "  $(CYAN)%-20s$(RESET) %s\n", $$1, $$2}'
	@printf "\n"
	@printf "$(BOLD)Utilities:$(RESET)\n"
	@grep -E '^(info|env-template|deps-check):.*##' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*?## "}; {printf "  $(CYAN)%-20s$(RESET) %s\n", $$1, $$2}'
	@printf "\n"

# ============================================================================
# Environment Setup (dev-* prefix = mutations)
# ============================================================================

dev-env-init: ## Initialize development environment (create .venv only)
	@printf "$(BOLD)$(BLUE)🚀 Initializing development environment...$(RESET)\n"
	@printf "$(CYAN)→ Creating virtual environment...$(RESET)\n"
	@test -d .venv || $(UV) venv
	@printf "$(BOLD)$(GREEN)✅ .venv created$(RESET)\n"
	@printf "\n"
	@printf "$(BOLD)$(CYAN)Next steps:$(RESET)\n"
	@printf "  $(CYAN)• Run: make dev-deps-sync$(RESET)\n"

dev-deps-sync: ## Reconcile dependencies (uv sync with dev tools)
	@printf "$(BOLD)$(GREEN)Syncing dependencies...$(RESET)\n"
	@test -d .venv || (printf "$(RED)❌ .venv not found$(RESET)\n" && printf "$(CYAN)ℹ️ Run: make dev-env-init$(RESET)\n" && exit 1)
ifndef HAS_UV
	$(error UV is not installed. Install with: curl -LsSf https://astral.sh/uv/install.sh | sh)
endif
	$(UV) sync --extra cli --editable
	@printf "$(CYAN)→ Verifying installation...$(RESET)\n"
	$(MAKE) check-install
	@printf "$(BOLD)$(CYAN)✅ Dependencies synced, CLI installed$(RESET)\n"

# ============================================================================
# Development
# ============================================================================

run: ## Run the proxy server
	@printf "$(BOLD)$(BLUE)Starting Vandamme Proxy...$(RESET)\n"
	$(PYTHON) start_proxy.py

dev: dev-deps-sync ## Sync deps and run server with hot reload
	@printf "$(BOLD)$(BLUE)Starting development server with auto-reload...$(RESET)\n"
	$(UV) run uvicorn src.main:app --host $(HOST) --port $(PORT) --reload --log-level $(shell echo $(LOG_LEVEL) | tr '[:upper:]' '[:lower:]')

health: ## Check proxy server health
	@printf "$(BOLD)$(CYAN)Checking server health...$(RESET)\n"
	@curl -s http://localhost:$(PORT)/health | $(PYTHON) -m json.tool || printf "$(YELLOW)Server not running on port $(PORT)$(RESET)\n"

check-install: ## Verify that installation was successful
	@printf "$(BOLD)$(BLUE)🔍 Verifying installation...$(RESET)\n"
	@printf "$(CYAN)Checking vdm command...$(RESET)\n"
	@if [ -f ".venv/bin/vdm" ]; then \
		printf "$(GREEN)✅ vdm command found$(RESET)\n"; \
		.venv/bin/vdm version; \
	else \
		printf "$(RED)❌ vdm command not found$(RESET)\n"; \
		printf "$(YELLOW)💡 Run 'make dev-env-init' to install CLI$(RESET)\n"; \
		exit 1; \
	fi
	@printf "$(CYAN)Checking Python imports...$(RESET)\n"
ifndef HAS_UV
	$(error UV is not installed. Install with: curl -LsSf https://astral.sh/uv/install.sh | sh)
endif
	@$(UV) run python -c "import src.cli.main; print('$(GREEN)✅ CLI module imports successfully$(RESET)')" || exit 1
	@printf "$(BOLD)$(GREEN)✅ Installation verified successfully$(RESET)\n"

doctor: ## Run environment health check (read-only, fast)
	@printf "$(BOLD)$(CYAN)🩺 Doctor - Environment Health Check$(RESET)\n"
	@printf "\n"
	@printf "$(BOLD)$(YELLOW)System Information:$(RESET)\n"
	@printf "  OS:           $$(uname -s)\n"
	@printf "  Architecture: $$(uname -m)\n"
	@printf "  Kernel:       $$(uname -r)\n"
	@printf "\n"
	@printf "$(BOLD)$(YELLOW)Tool Availability:$(RESET)\n"
	@command -v uv >/dev/null 2>&1 && printf "  UV:           $(GREEN)✓ installed$(RESET)\n" || printf "  UV:           $(RED)✗ not found$(RESET)\n"
	@command -v python3 >/dev/null 2>&1 && printf "  Python 3:     $(GREEN)✓ installed$$($(PYTHON) --version 2>&1)$(RESET)\n" || printf "  Python 3:     $(RED)✗ not found$(RESET)\n"
	@command -v docker >/dev/null 2>&1 && printf "  Docker:       $(GREEN)✓ installed$(RESET)\n" || printf "  Docker:       $(YELLOW)⚠ not found$(RESET)\n"
	@command -v git >/dev/null 2>&1 && printf "  Git:          $(GREEN)✓ installed$$(git --version 2>&1)$(RESET)\n" || printf "  Git:          $(RED)✗ not found$(RESET)\n"
	@printf "\n"
	@printf "$(BOLD)$(GREEN)✓ Environment check complete$(RESET)\n"

clean: ## Clean temporary files and caches
	@printf "$(BOLD)$(YELLOW)Cleaning temporary files...$(RESET)\n"
	@find . -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
	@find . -type d -name "*.egg-info" -exec rm -rf {} + 2>/dev/null || true
	@find . -type d -name ".pytest_cache" -exec rm -rf {} + 2>/dev/null || true
	@find . -type d -name ".mypy_cache" -exec rm -rf {} + 2>/dev/null || true
	@find . -type f -name "*.pyc" -delete 2>/dev/null || true
	@find . -type f -name "*.pyo" -delete 2>/dev/null || true
	@find . -type f -name ".coverage" -delete 2>/dev/null || true
	@rm -rf build/ dist/ 2>/dev/null || true
	@$(MAKE) clean-binaries
	@printf "$(GREEN)✓ Cleaned successfully$(RESET)\n"

# ============================================================================
# Code Quality
# ============================================================================

format: ## Auto-format code with ruff (includes type transformations)
	@printf "$(BOLD)$(YELLOW)Formatting code...$(RESET)\n"
	@printf "$(CYAN)→ ruff format$(RESET)\n"
	@$(UV) run $(RUFF) format $(PYTHON_FILES)
	@printf "$(CYAN)→ ruff check --fix (all auto-fixable rules)$(RESET)\n"
	@if $(UV) run $(RUFF) check --fix $(PYTHON_FILES); then \
		printf "$(GREEN)✓ All fixes applied successfully$(RESET)\n"; \
	else \
		printf "$(YELLOW)⚠ Some issues require manual fixes$(RESET)\n"; \
		printf "$(CYAN)→ Running additional unsafe fixes...$(RESET)\n"; \
		$(UV) run $(RUFF) check --fix $(PYTHON_FILES) --unsafe-fixes || true; \
		printf "$(YELLOW)⚠ Remaining issues need manual intervention$(RESET)\n"; \
	fi
	@printf "$(GREEN)✓ Code formatted$(RESET)\n"

lint: ## Run code linting checks (ruff - check only)
	@printf "$(BOLD)$(YELLOW)Running linters...$(RESET)\n"
	@printf "$(CYAN)→ ruff format --check$(RESET)\n"
	@$(UV) run $(RUFF) format --check $(PYTHON_FILES) || (printf "$(YELLOW)⚠ Run 'make format' to fix formatting$(RESET)\n" && exit 1)
	@printf "$(CYAN)→ ruff check$(RESET)\n"
	@$(UV) run $(RUFF) check $(PYTHON_FILES) || (printf "$(YELLOW)⚠ Run 'make format' to fix issues$(RESET)\n" && exit 1)
	@printf "$(GREEN)✓ Linting passed$(RESET)\n"

typecheck: ## Run type checking with mypy
	@printf "$(BOLD)$(YELLOW)Running type checker...$(RESET)\n"
	@$(UV) run $(MYPY) $(SRC_DIR) || (printf "$(YELLOW)⚠ Type checking found issues$(RESET)\n" && exit 1)
	@printf "$(GREEN)✓ Type checking passed$(RESET)\n"

sanitize: ## Run all static checks (format + lint + typecheck, NO tests)
	@printf "$(BOLD)$(YELLOW)Running sanitize...$(RESET)\n"
	@$(MAKE) format
	@$(MAKE) lint
	@$(MAKE) typecheck
	@printf "$(BOLD)$(GREEN)✓ Sanitize complete - all static checks passed$(RESET)\n"

check: ## Merge safety gate (sanitize + test-unit)
	@printf "$(BOLD)$(CYAN)Running merge gate...$(RESET)\n"
	@$(MAKE) sanitize
	@$(MAKE) test-unit
	@printf "$(BOLD)$(GREEN)✓ Merge gate passed$(RESET)\n"

check-quick: ## Fast local validation (sanitize + test-quick)
	@printf "$(BOLD)$(CYAN)Running quick validation...$(RESET)\n"
	@$(MAKE) sanitize
	@$(MAKE) test-quick
	@printf "$(BOLD)$(GREEN)✓ Quick validation passed$(RESET)\n"

security-check: ## Run security vulnerability checks
	@printf "$(BOLD)$(YELLOW)Running security checks...$(RESET)\n"
	@command -v bandit >/dev/null 2>&1 || { printf "$(YELLOW)Installing bandit...$(RESET)\n"; $(UV) pip install bandit; }
	@$(UV) run bandit -r $(SRC_DIR) -ll || printf "$(GREEN)✓ No security issues found$(RESET)\n"

validate: sanitize test coverage ## Full release validation (static + tests + coverage)
	@printf "$(BOLD)$(GREEN)✓ Validation complete - ready to ship$(RESET)\n"

# Pre-commit hook target - customize as needed for your project
# Default: runs fast checks (sanitize + quick tests)
# Alternatives: use 'sanitize' (faster), 'check' (slower), or add custom steps
pre-commit: sanitize test ## Run pre-commit hooks (customizable)
	@printf "$(BOLD)$(GREEN)✓ Pre-commit checks complete$(RESET)\n"

# ============================================================================
# Testing
# ============================================================================

test: ## Run all tests except e2e (unit + integration, no API calls)
	@printf "$(BOLD)$(CYAN)Running all tests (excluding e2e)...$(RESET)\n"
	@# First run unit tests
	@$(UV) run $(PYTEST) $(TEST_DIR)/unit -v
	@# Then try integration tests if server is running
	@if curl -s http://localhost:$(PORT)/health > /dev/null 2>&1 || \
	   curl -s http://localhost:18082/health > /dev/null 2>&1; then \
		printf "$(YELLOW)Server detected, running integration tests...$(RESET)\n"; \
		$(UV) run $(PYTEST) $(TEST_DIR)/integration -v || printf "$(YELLOW)⚠ Some integration tests failed$(RESET)\n"; \
	else \
		printf "$(YELLOW)⚠ Server not running, skipping integration tests$(RESET)\n"; \
		printf "$(CYAN)To run integration tests:$(RESET)\n"; \
		printf "  1. Start server: make dev\n"; \
		printf "  2. Run: make test-integration\n"; \
	fi

test-unit: ## Run unit tests only (fast, no external deps)
	@printf "$(BOLD)$(CYAN)Running unit tests...$(RESET)\n"
	@$(UV) run $(PYTEST) $(TEST_DIR)/unit -v

test-integration: ## Run integration tests (requires server, no API calls)
	@printf "$(BOLD)$(CYAN)Running integration tests...$(RESET)\n"
	@printf "$(YELLOW)Note: Ensure server is running$(RESET)\n"
	@if curl -s http://localhost:$(PORT)/health > /dev/null 2>&1 || \
	   curl -s http://localhost:18082/health > /dev/null 2>&1; then \
		$(UV) run $(PYTEST) $(TEST_DIR) -v -m "integration and not e2e"; \
	else \
		printf "$(RED)❌ Server not running. Start with 'make dev' first$(RESET)\n"; \
		exit 1; \
	fi

test-e2e: ## Run end-to-end tests with real APIs (requires server and API keys)
	@printf "$(BOLD)$(CYAN)Running end-to-end tests...$(RESET)\n"
	@printf "$(YELLOW)⚠ These tests make real API calls and will incur costs$(RESET)\n"
	@printf "$(YELLOW)Note: Ensure server is running and API keys are set in .env$(RESET)\n"
	@if curl -s http://localhost:$(PORT)/health > /dev/null 2>&1 || \
	   curl -s http://localhost:18082/health > /dev/null 2>&1; then \
		$(UV) run $(PYTEST) $(TEST_DIR) -v -m e2e; \
	else \
		printf "$(RED)❌ Server not running. Start with 'make dev' first$(RESET)\n"; \
		exit 1; \
	fi

test-all: ## Run ALL tests including e2e (requires server and API keys)
	@printf "$(BOLD)$(CYAN)Running ALL tests (unit + integration + e2e)...$(RESET)\n"
	@printf "$(YELLOW)⚠ E2E tests make real API calls and will incur costs$(RESET)\n"
	@# First run unit tests
	@$(UV) run $(PYTEST) $(TEST_DIR) -v -m unit
	@# Then check if server is running for integration and e2e tests
	@if curl -s http://localhost:$(PORT)/health > /dev/null 2>&1 || \
	   curl -s http://localhost:18082/health > /dev/null 2>&1; then \
		printf "$(YELLOW)Server detected, running integration tests...$(RESET)\n"; \
		$(UV) run $(PYTEST) $(TEST_DIR) -v -m "integration and not e2e" || printf "$(YELLOW)⚠ Some integration tests failed$(RESET)\n"; \
		printf "$(YELLOW)Running e2e tests...$(RESET)\n"; \
		$(UV) run $(PYTEST) $(TEST_DIR) -v -m e2e || printf "$(YELLOW)⚠ Some e2e tests failed (check API keys)$(RESET)\n"; \
	else \
		printf "$(RED)❌ Server not running. Start with 'make dev' first$(RESET)\n"; \
		exit 1; \
	fi

test-quick: ## Run tests without coverage (fast)
	@printf "$(BOLD)$(CYAN)Running quick tests...$(RESET)\n"
	@$(UV) run $(PYTEST) $(TEST_DIR) -q --tb=short -m unit

coverage: ## Run tests with coverage report
	@printf "$(BOLD)$(CYAN)Running tests with coverage...$(RESET)\n"
	@printf "$(CYAN)→ Ensuring pytest-cov is installed...$(RESET)\n"
	@$(UV) add --group dev pytest-cov 2>/dev/null || true
	@# Check if server is running, if so run all tests, otherwise run only unit tests
	@if curl -s http://localhost:$(PORT)/health > /dev/null 2>&1 || \
	   curl -s http://localhost:18082/health > /dev/null 2>&1; then \
		printf "$(YELLOW)Server detected, running coverage on all tests...$(RESET)\n"; \
		$(UV) run $(PYTEST) $(TEST_DIR) --cov=$(SRC_DIR) --cov-report=html --cov-report=term-missing; \
	else \
		printf "$(YELLOW)Server not running, running coverage on unit tests only...$(RESET)\n"; \
		$(UV) run $(PYTEST) $(TEST_DIR) --cov=$(SRC_DIR) --cov-report=html --cov-report=term-missing -m unit; \
	fi
	@printf "$(GREEN)✓ Coverage report generated in htmlcov/$(RESET)\n"

# ============================================================================
# Binary Builds (Nuitka)
# ============================================================================

build-cli: ## Build CLI binary for current platform
	@printf "$(BOLD)$(GREEN)Building CLI binary...$(RESET)\n"
	@# Ensure _version.py exists from hatch-vcs
	@$(UV) build --wheel 2>/dev/null || true
	@# Detect platform
	@UNAME_S="$$(uname -s)"; \
	UNAME_M="$$(uname -m)"; \
	if [ "$${UNAME_S}" = "Darwin" ]; then \
		PLATFORM="darwin"; \
	elif [ "$${UNAME_S}" = "Linux" ]; then \
		PLATFORM="linux"; \
	else \
		PLATFORM="unknown"; \
	fi; \
	BINARY_EXT=""; \
	if [ "$${UNAME_S}" = "Darwin" ] && [ "$${UNAME_M}" = "arm64" ]; then \
		BINARY_NAME="vdm-$${PLATFORM}-aarch64$${BINARY_EXT}"; \
	elif [ "$${UNAME_S}" = "Darwin" ] && [ "$${UNAME_M}" = "x86_64" ]; then \
		BINARY_NAME="vdm-$${PLATFORM}-x86_64$${BINARY_EXT}"; \
	elif [ "$${UNAME_S}" = "Linux" ]; then \
		BINARY_NAME="vdm-$${PLATFORM}-$${UNAME_M}$${BINARY_EXT}"; \
	else \
		BINARY_NAME="vdm$${BINARY_EXT}"; \
	fi; \
	printf "$(CYAN)Platform: $${PLATFORM} $${UNAME_M}$(RESET)\n"; \
	$(NUITKA) --onefile --standalone \
		--enable-plugin=anti-bloat \
		--nofollow-import-to=tests \
		--nofollow-import-to=src.dashboard \
		--assume-yes-for-downloads \
		--output-dir=$(BUILD_DIR) \
		--output-filename=$${BINARY_NAME} \
		--include-data-files=src/config/*.toml=src/config/ \
		src/cli/main.py
	@printf "$(GREEN)✓ CLI binary built: $(BUILD_DIR)/$$(ls $(BUILD_DIR)/vdm*)$(RESET)\n"

clean-binaries: ## Clean Nuitka build artifacts
	@printf "$(BOLD)$(YELLOW)Cleaning Nuitka artifacts...$(RESET)\n"
	@rm -rf $(BUILD_DIR) 2>/dev/null || true
	@find . -type d -name "*.build" -exec rm -rf {} + 2>/dev/null || true
	@find . -type d -name "*.dist" -exec rm -rf {} + 2>/dev/null || true
	@find . -name "*.onefile-build" -exec rm -rf {} + 2>/dev/null || true
	@printf "$(GREEN)✓ Binary artifacts cleaned$(RESET)\n"

# ============================================================================
# Docker
# ============================================================================

docker-build: ## Build Docker image
	@printf "$(BOLD)$(BLUE)Building Docker image...$(RESET)\n"
ifndef HAS_DOCKER
	$(error Docker is not installed or not running)
endif
	docker compose build

docker-up: ## Start services with Docker Compose
	@printf "$(BOLD)$(BLUE)Starting Docker services...$(RESET)\n"
ifndef HAS_DOCKER
	$(error Docker is not installed or not running)
endif
	docker compose up -d
	@printf "$(GREEN)✓ Services started$(RESET)\n"
	@printf "$(CYAN)View logs: make docker-logs$(RESET)\n"

docker-down: ## Stop Docker services
	@printf "$(BOLD)$(BLUE)Stopping Docker services...$(RESET)\n"
ifndef HAS_DOCKER
	$(error Docker is not installed or not running)
endif
	docker compose down
	@printf "$(GREEN)✓ Services stopped$(RESET)\n"

docker-logs: ## Show Docker logs
ifndef HAS_DOCKER
	$(error Docker is not installed or not running)
endif
	docker compose logs -f

docker-restart: docker-down docker-up ## Restart Docker services

docker-clean: docker-down ## Stop and remove Docker containers, volumes
	@printf "$(BOLD)$(YELLOW)Cleaning Docker resources...$(RESET)\n"
	docker compose down -v --remove-orphans
	@printf "$(GREEN)✓ Docker resources cleaned$(RESET)\n"

# ============================================================================
# Build & Distribution
# ============================================================================

build: clean ## Build distribution packages
	@printf "$(BOLD)$(GREEN)Building distribution packages...$(RESET)\n"
	$(UV) build
	@printf "$(GREEN)✓ Build complete - check dist/$(RESET)\n"

# ============================================================================
# CI/CD
# ============================================================================

ci: dev-deps-sync sanitize test ## Run full CI pipeline (setup, sanitize, test)
	@printf "$(BOLD)$(GREEN)━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━$(RESET)\n"
	@printf "$(BOLD)$(GREEN)✓ CI Pipeline Complete$(RESET)\n"
	@printf "$(BOLD)$(GREEN)━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━$(RESET)\n"

all: clean dev-deps-sync sanitize test build ## Run everything (clean, setup, sanitize, test, build)
	@printf "$(BOLD)$(GREEN)━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━$(RESET)\n"
	@printf "$(BOLD)$(GREEN)✓ All Tasks Complete$(RESET)\n"
	@printf "$(BOLD)$(GREEN)━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━$(RESET)\n"

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
	@printf "$(CYAN)💡 Tip: Skip interactive mode with: make version-bump BUMP_TYPE=patch|minor|major$(RESET)\n"
	@printf "\n"
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
	@printf "$(BOLD)$(CYAN)Project Information$(RESET)\n"
	@printf "  Name:         Vandamme Proxy\n"
	@printf "  Version:      $$($(UV) run python -c 'from src import __version__; print(__version__)' 2>/dev/null || echo 'unknown')\n"
	@printf "  Python:       >= 3.10\n"
	@printf "  Source:       $(SRC_DIR)/\n"
	@printf "  Tests:        $(TEST_DIR)/\n"
	@printf "  Default Host: $(HOST)\n"
	@printf "  Default Port: $(PORT)\n"
	@printf "\n"
	@printf "$(BOLD)$(CYAN)Environment$(RESET)\n"
	@printf "  UV:           $(if $(HAS_UV),✓ installed,✗ not found)\n"
	@printf "  Docker:       $(if $(HAS_DOCKER),✓ installed,✗ not found)\n"
	@printf "  Python:       $$($(PYTHON) --version 2>&1)\n"

.PHONY: watch
watch: ## Watch for file changes and auto-run tests
	@printf "$(BOLD)$(CYAN)Watching for changes...$(RESET)\n"
	@command -v watchexec >/dev/null 2>&1 || { printf "$(RED)Error: watchexec not installed. Install with: cargo install watchexec-cli$(RESET)\n"; exit 1; }
	watchexec -e py -w $(SRC_DIR) -w $(TEST_DIR) -- make test-quick

.PHONY: env-template
env-template: ## Generate .env template file
	@printf "$(BOLD)$(CYAN)Generating .env.template...$(RESET)\n"
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
	@printf "$(GREEN)✓ Generated .env.template$(RESET)\n"

deps-check: ## Check for outdated dependencies
	@printf "$(BOLD)$(YELLOW)Checking dependencies...$(RESET)\n"
ifdef HAS_UV
	@$(UV) pip list --outdated || printf "$(GREEN)✓ All dependencies up to date$(RESET)\n"
else
	@$(PYTHON) -m pip list --outdated || printf "$(GREEN)✓ All dependencies up to date$(RESET)\n"
endif
