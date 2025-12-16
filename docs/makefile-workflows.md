# Vandamme Proxy - Development Workflows Guide

Welcome to the Vandamme Proxy development workflows guide! This document explains how to make the most of our Makefile targets and helper scripts for efficient development, testing, and releases.

## Table of Contents

1. [Quick Start](#quick-start)
2. [Development Workflow](#development-workflow)
3. [Testing Workflow](#testing-workflow)
4. [Code Quality Workflow](#code-quality-workflow)
5. [Release Workflow](#release-workflow)
6. [Docker Workflow](#docker-workflow)
7. [Utility Commands](#utility-commands)
8. [Troubleshooting](#troubleshooting)
9. [Best Practices](#best-practices)

## Quick Start

### First-time Setup
```bash
# Initialize complete development environment (recommended)
make init-dev

# Or install in development mode only
make install-dev

# Verify installation
make check-install

# Start the development server
make dev
```

### Essential Commands
```bash
make help              # Show all available commands
make test-quick        # Run tests fast
make check            # Run code quality checks
make make              # Show project information
make version          # Show current version
```

---

## Development Workflow

### Setting Up Your Environment

#### 1. Initialize Development Environment
```bash
make init-dev
```
This command:
- Installs all dependencies including CLI tools
- Runs installation verification
- Shows next steps

#### 2. Install Dependencies Individually
```bash
# Install production dependencies
make install

# Install all dependencies (including dev tools)
make install-deps

# Install in development mode with CLI
make install-dev

# Install using pip (fallback)
make install-pip
```

#### 3. Running the Application

##### Development Server with Hot Reload
```bash
# Start development server with auto-reload
make dev

# Or with custom settings
HOST=127.0.0.1 PORT=3000 make dev
```

##### Production-like Run
```bash
# Run the proxy server
make run

# Or directly
vdm server start
```

#### 4. Health Check
```bash
# Check if server is running
make health

# Or directly
curl -s http://localhost:8082/health | python -m json.tool
```

### Daily Development Tasks

#### 1. Start Your Day
```bash
# Pull latest changes
git pull

# Install/update dependencies
make install-dev

# Check everything is working
make validate
```

#### 2. Working with the CLI
```bash
# Check CLI installation
vdm version

# Start server via CLI
vdm server start

# Test connection
vdm test connection

# List available models
vdm test models

# Check upstream health
vdm health upstream

# Validate configuration
vdm config validate
```

#### 3. Watching for Changes
```bash
# Watch for changes and auto-run tests (requires watchexec)
make watch

# Or manually:
watchexec -e py -w src -w tests -- make test-quick
```

---

## Testing Workflow

### Understanding Test Types

Our test suite uses pytest markers:
- **Unit tests**: Fast, no external dependencies (`-m unit`)
- **Integration tests**: Require running services and API keys (`-m integration`)

### Running Tests

#### Quick Test Commands
```bash
# Run all tests (unit + integration if server running)
make test

# Run only unit tests (fast)
make test-unit

# Run integration tests (requires server)
make test-integration

# Quick tests without coverage
make test-quick
```

#### Running Tests with Coverage
```bash
# Generate coverage report (unit tests only if server not running)
make coverage

# View coverage report
open htmlcov/index.html
```

#### Running Specific Tests
```bash
# Run specific test file
uv run pytest tests/unit/test_alias_manager.py

# Run specific test
uv run pytest tests/unit/test_alias_manager.py::test_alias_resolution

# Run with verbose output
uv run pytest tests -v

# Run with specific marker
uv run pytest tests -m unit -v
```

### Before Running Tests

1. **Ensure Server is Running** (for integration tests):
```bash
# Terminal 1: Start server
make dev

# Terminal 2: Run tests
make test-integration
```

2. **Set Environment Variables** (for integration tests):
```bash
# Create .env file
cat > .env << EOF
OPENAI_API_KEY=your-key-here
ANTHROPIC_API_KEY=your-key-here
EOF
```

### Test Best Practices

1. **Write Unit Tests First**: Unit tests should be fast and independent
2. **Use Test Markers**: Mark tests appropriately with `@pytest.mark.unit` or `@pytest.mark.integration`
3. **Mock External Services**: Use pytest-mock for external dependencies
4. **Test Coverage**: Aim for high coverage on critical paths

---

## Code Quality Workflow

### Code Formatting and Linting

#### Automatic Formatting
```bash
# Format code with ruff (includes type transformations)
make format
```

This command:
- Runs `ruff format` to fix formatting issues
- Runs `ruff check --fix` to auto-fix linting issues
- Attempts unsafe fixes if needed

#### Manual Linting
```bash
# Run linting checks only (no fixes)
make lint

# Run type checking only
make type-check

# Run both linting and type checking
make check
```

#### Quick Checks
```bash
# Quick check (format + lint only, skip type-check)
make quick-check
```

### Security Checks
```bash
# Run security vulnerability checks
make security-check
```

### Pre-commit Workflow
```bash
# Run everything before committing
make pre-commit
```

This is equivalent to:
```bash
make format && make check
```

### Understanding Ruff Configuration

The project uses Ruff as an all-in-one replacement for:
- **Black**: Code formatting
- **isort**: Import sorting
- **flake8**: Linting
- **pyupgrade**: Python version upgrades

Key Ruff features enabled:
- **Type transformations**: `List` → `list`, `Dict` → `dict`, `Optional` → `Union | None`
- **Import sorting**: Automatic isort-compatible sorting
- **Bug detection**: Flake8-bugbear rules
- **Simplification**: Flake8-simplify rules

---

## Release Workflow

### Understanding Version Management

The project uses **dynamic versioning** from Git tags:
- Version is derived from Git tags (no hardcoded versions)
- Format: `x.y.z` (semantic versioning without 'v' prefix)
- Automatic version generation via hatch-vcs

### Release Types

1. **Patch Release** (1.0.0 → 1.0.1): Bug fixes
2. **Minor Release** (1.0.0 → 1.1.0): New features, backward compatible
3. **Major Release** (1.0.0 → 2.0.0): Breaking changes

### Quick Releases

```bash
# Quick patch release
make release-patch

# Quick minor release
make release-minor

# Quick major release
make release-major
```

These commands:
- Validate release readiness
- Run tests
- Bump version automatically
- Create and push Git tag
- Trigger GitHub Actions for publishing

### Interactive Release

```bash
# Full interactive release workflow
make release-full
```

This guides you through:
- Version selection (patch/minor/major)
- Automatic validation
- Version bumping
- Tag creation
- Publishing trigger

### Manual Version Control

```bash
# Show current version
make version

# Set specific version
make version-set

# Bump version with type
make version-bump BUMP_TYPE=patch
make version-bump BUMP_TYPE=minor
make version-bump BUMP_TYPE=major

# Create and push tag
make tag-release
```

### Validation and Building

```bash
# Check if ready for release
make release-check

# Build distribution packages
make release-build

# Publish to PyPI manually
make release-publish
```

### Automated Publishing (Recommended)

```bash
# Create tag and trigger automated publishing
make release
```

This:
- Creates Git tag
- Pushes to origin
- Triggers GitHub Actions workflow
- Actions handles testing, building, and publishing

### Release Workflow with Scripts

You can also use the scripts directly:

```bash
# Using release script
uv run python scripts/release.py full
uv run python scripts/release.py quick patch

# Using version script
uv run python scripts/version.py bump minor
uv run python scripts/version.py get
```

### Before Releasing

1. **Check Working Directory**:
```bash
git status  # Should be clean
```

2. **Run Tests**:
```bash
make test-quick
```

3. **Check Version**:
```bash
make version
```

4. **Verify Build**:
```bash
make release-build
```

### Release Process Flow

1. Developer runs `make release-patch/minor/major`
2. Makefile validates clean state and tests
3. Version is bumped and Git tag is created/pushed
4. GitHub Actions triggers on tag push
5. Actions runs tests, builds package, publishes to PyPI
6. GitHub Release created automatically
7. Package available: `pip install vandamme-proxy==X.Y.Z`

---

## Docker Workflow

### Building and Running with Docker

```bash
# Build Docker image
make docker-build

# Start services
make docker-up

# Stop services
make docker-down

# View logs
make docker-logs

# Restart services
make docker-restart

# Clean up resources
make docker-clean
```

### Docker Compose Configuration

The project uses `docker-compose.yml` for:
- Application container
- Database (if needed)
- Reverse proxy (if needed)

---

## Utility Commands

### Project Information

```bash
# Show project information
make info

# Show project version
make version

# Show help for all commands
make help
```

### Environment Templates

```bash
# Generate .env.template
make env-template
```

### Cleanup

```bash
# Clean temporary files and caches
make clean
```

This removes:
- `__pycache__` directories
- `*.egg-info` directories
- `.pytest_cache`
- `.mypy_cache`
- `*.pyc` and `*.pyo` files
- `.coverage` file
- `build/` and `dist/` directories

### Dependency Management

```bash
# Check for outdated dependencies
make deps-check

# Validate installation
make check-install
```

---

## Troubleshooting

### Common Issues and Solutions

#### 1. UV Environment Issues
```
warning: `VIRTUAL_ENV=/path/to/env` does not match the project environment path `.venv`
```
**Solution**: Deactivate any active virtual environment before using make commands:
```bash
deactivate  # If in a venv
make install-dev
```

#### 2. Test Failures
**Integration Tests Fail**: Ensure server is running and API keys are set
```bash
# Start server
make dev

# Set API keys in .env
echo "OPENAI_API_KEY=your-key" >> .env

# Run tests
make test-integration
```

#### 3. Release Fails
**Working Directory Not Clean**:
```bash
git status
git add .
git commit -m "Ready for release"
make release-patch
```

**Version Already Published**:
```bash
# Check current version
make version

# Bump to new version
make version-bump BUMP_TYPE=patch
make release
```

#### 4. Build Issues
**Module Not Found**:
```bash
# Reinstall dependencies
make clean
make install-dev

# Or
uv sync
```

#### 5. Linting Issues
**Auto-fix doesn't work**:
```bash
# Check what issues remain
make lint

# Manually fix the reported issues
# Then run:
make format
```

#### 6. Permission Issues
**Script not executable**:
```bash
chmod +x scripts/*.py
```

### Getting Help

1. **Makefile Help**:
```bash
make help
```

2. **Script Help**:
```bash
uv run python scripts/release.py
uv run python scripts/version.py
```

3. **Verbose Output**:
```bash
# For debugging
make test-quick 2>&1 | tee test.log
```

---

## Best Practices

### Development Best Practices

1. **Always run tests before committing**:
```bash
make test-quick
```

2. **Use pre-commit hooks**:
```bash
make pre-commit
```

3. **Keep dependencies updated**:
```bash
make deps-check
```

4. **Clean before builds**:
```bash
make clean
make build
```

### Release Best Practices

1. **Tag from main branch**:
```bash
git checkout main
git pull
make release-minor
```

2. **Check changelog**:
```bash
# Review changes since last release
git log --oneline $(git describe --tags --abbrev=0)..HEAD
```

3. **Verify build locally**:
```bash
make release-build
```

4. **Test installation**:
```bash
# Test local build
pip install dist/*.whl --force-reinstall
vdm version
```

### Environment Best Practices

1. **Use `.env` for local configuration** (never commit it)
2. **Keep production secrets separate** from development
3. **Use specific Python versions**:
```bash
python3.11 -m venv .venv
source .venv/bin/activate
make install-dev
```

### Git Workflow Best Practices

1. **Feature branches**:
```bash
git checkout -b feature/new-feature
# Work on feature
make test-quick
make pre-commit
git add .
git commit -m "feat: add new feature"
git push origin feature/new-feature
```

2. **Semantic commit messages**:
- `feat:` for new features
- `fix:` for bug fixes
- `docs:` for documentation
- `refactor:` for code refactoring
- `test:` for tests
- `chore:` for maintenance

3. **Pull requests**:
   - All PRs should pass `make check`
   - Include tests for new features
   - Update documentation as needed

---

## Advanced Workflows

### Using Different Python Versions

```bash
# With uv
uv run --python 3.11 python script.py

# With pyenv
pyenv shell 3.11.0
make test-quick
```

### Custom Build Configurations

```bash
# Build with custom settings
UV_BUILD_ARGS="--no-binary" make build
```

### Parallel Testing

```bash
# Run tests in parallel
uv run pytest -n auto
```

### Profiling

```bash
# Profile test execution
uv run pytest --profile
```

---

## Conclusion

This guide covers the essential workflows for developing, testing, and releasing Vandamme Proxy. The Makefile provides a unified interface to all common operations, while the helper scripts handle complex logic behind the scenes.

Remember to:
1. **Run tests early and often**
2. **Keep code clean with `make format`**
3. **Validate before releasing with `make check`**
4. **Use the help commands when unsure**

Happy coding! 🚀
