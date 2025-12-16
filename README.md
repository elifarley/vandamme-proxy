# Vandamme Proxy

**The LLM Gateway for Multi-Provider AI Development**

[![ci](https://github.com/CedarVerse/vandamme-proxy/actions/workflows/ci.yml/badge.svg)](https://github.com/CedarVerse/vandamme-proxy/actions/workflows/ci.yml)
[![PyPI version](https://img.shields.io/pypi/v/vandamme-proxy.svg)](https://pypi.org/project/vandamme-proxy/)
[![PyPI downloads](https://img.shields.io/pypi/dm/vandamme-proxy.svg)](https://pypi.org/project/vandamme-proxy/)
[![Python versions](https://img.shields.io/pypi/pyversions/vandamme-proxy.svg)](https://pypi.org/project/vandamme-proxy/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Code style: black](https://img.shields.io/badge/code%20style-black-000000.svg)](https://github.com/psf/black)

> **Transform Claude Code (or any Anthropic API client) into a multi-provider client for OpenAI, Anthropic, Poe, Azure, Gemini, and other compatible APIs.**

---

## 🚀 Why Vandamme Proxy?

### For Claude Code Users
Route requests to any LLM provider with simple model prefixes

```shell
# Install and setup in seconds
pip install vandamme-proxy
# Export your API key
vdm server start

```

```shell
`# Use with Claude Code CLI
export ANTHROPIC_BASE_URL=http://localhost:8082
claude --model openai:gpt-4o "Analyze this code"
claude --model poe:gemini-flash "Quick question"
claude --model fast "Fast response"  # Smart alias
```

### For LLM Gateway Users
A lightweight, production-ready proxy with enterprise features:
- **🔌 Zero-Configuration Discovery** - Providers auto-configured from environment variables
- **🔄 Dual API Format Support** - Native OpenAI conversion + Anthropic passthrough
- **🏷️ Smart Model Aliases** - Case-insensitive substring matching for cleaner workflows
- **🔐 Secure API Key Passthrough** - Multi-tenant deployments with `!PASSTHRU` sentinel
- **⛓️ Extensible Middleware** - Chain-of-responsibility pattern for custom logic
- **📊 Built-in Observability** - Metrics, health checks, and structured logging

---

## ✨ Features at a Glance

### 🌐 Provider Support
- **Major Providers**: OpenAI, Anthropic, Poe, Azure OpenAI, etc
- **Custom Endpoints**: Any OpenAI/Anthropic-compatible API
- **Auto-Discovery**: Configure via `{PROVIDER}_API_KEY` environment variables
- **Mixed Formats**: Run OpenAI conversion and Anthropic passthrough simultaneously

### 🎯 Intelligent Routing
- **Provider Prefix Routing**: `provider:model` syntax
- **Smart Model Aliases**: Substring matching with priority ordering
- **Dynamic Provider Selection**: Switch providers per-request without configuration changes

### 🔒 Security & Multi-Tenancy
- **API Key Passthrough**: Set `{PROVIDER}_API_KEY=!PASSTHRU` to enable client-provided keys
- **Mixed Authentication**: Static keys + passthrough simultaneously per-provider
- **Isolated Configuration**: Per-provider settings, custom headers, API versions

### 🛠️ Developer Experience
- **Handy CLI (`vdm`)**: Server management, health checks, configuration validation
- Streaming support, metrics endpoints
- **Extensible Architecture**: Built-in middleware for Google Gemini thought signatures
- Hot reload support during development

---

## 🏗️ Architecture Overview

```
┌──────────────────────────────────────────────────────┐
│            Your AI Application                       │
│      (Claude Code CLI, Custom Clients)               │
└──────────────────────┬───────────────────────────────┘
                       │
                       ▼
       ┌───────────────────────────────────┐
       │    Vandamme Proxy Gateway         │
       │    http://localhost:8082          │
       │                                   │
       │  ┌─────────────────────────────┐ │
       │  │  Smart Alias Engine         │ │
       │  │  "fast" → "poe:gemini-flash"│ │
       │  └─────────────────────────────┘ │
       │                                   │
       │  ┌─────────────────────────────┐ │
       │  │  Dynamic Provider Router    │ │
       │  │  Dual Format Handler        │ │
       │  └─────────────────────────────┘ │
       └───────────────┬───────────────────┘
                       │
       ┌───────────────┼────────────┬─────────────┐
       │               │            │             │
       ▼               ▼            ▼             ▼
   ┌────────┐     ┌─────────┐  ┌────────┐   ┌─────────┐
   │ OpenAI │     │Anthropic│  │  Poe   │   │  Azure  │
   │        │     │ Format: │  │(!PASS  │   │ Gemini  │
   │ Static │     │Anthropic│  │ THRU)  │   │ Custom  │
   │  Key   │     │         │  │        │   │         │
   └────────┘     └─────────┘  └────────┘   └─────────┘
```

**Request Flow:**
1. Anthropic Client sends request to Vandamme Proxy
2. Smart alias resolution (if applicable)
3. Provider routing based on model prefix
4. Format selection (OpenAI conversion vs Anthropic passthrough)
5. Response transformation and middleware processing

---

## 🚀 Quick Start

### 1️⃣ Installation

```bash
# Using uv (fastest)
uv pip install vandamme-proxy

# Or using pip
pip install vandamme-proxy

# Verify installation
vdm version
```

### 2️⃣ Configure Providers

```bash
# Interactive setup (recommended for new users)
vdm config setup

# Or create .env file manually
cat > .env << 'EOF'
# Provider API Keys
OPENAI_API_KEY=sk-your-openai-key
POE_API_KEY=!PASSTHRU  # Client provides key per-request
ANTHROPIC_API_KEY=sk-ant-your-key
ANTHROPIC_API_FORMAT=anthropic  # Direct passthrough (no conversion)

# Smart Aliases (provider-specific)
POE_ALIAS_FAST=gemini-flash
ANTHROPIC_ALIAS_CHAT=claude-3-5-sonnet-20241022
OPENAI_ALIAS_CODE=gpt-4o

# Default Provider (when no prefix specified)
# Overrides the default-provider from src/config/defaults.toml
VDM_DEFAULT_PROVIDER=openai
EOF
```

### 3️⃣ Start Server

```bash
# Development mode (with hot reload)
vdm server start --reload

# Production mode
vdm server start --host 0.0.0.0 --port 8082
```

### 4️⃣ Use with Claude Code CLI

```bash
# Point Claude Code to proxy
export ANTHROPIC_BASE_URL=http://localhost:8082

# Use provider routing
claude --model openai:gpt-4o "Analyze this code"
claude --model poe:gemini-flash "Quick question"

# Use smart aliases
claude --model fast "Fast response needed"
claude --model chat "Deep conversation"

# For passthrough providers (!PASSTHRU), provide your API key
ANTHROPIC_API_KEY=your-poe-key claude --model poe:gemini-flash "..."
```

### 5️⃣ Verify Your Setup

```bash
# Check server health
vdm health server

# Test upstream provider connectivity
vdm health upstream

# Show current configuration
vdm config show

# View active model aliases
curl http://localhost:8082/v1/aliases
```

**🎉 You're all set!** Now using multiple LLM providers through a single, elegant interface.

---

## ⚙️ Configuration System

Vandamme Proxy uses a hierarchical configuration system. Settings from higher levels override those from lower levels:

```
Environment Variables (highest priority)
├── Local: ./vandamme-config.toml
├── User: ~/.config/vandamme-proxy/vandamme-config.toml
└── Package: src/config/defaults.toml (lowest priority)
```

### Default Provider

The default provider is determined in this order:
1. `VDM_DEFAULT_PROVIDER` environment variable (if set)
2. `default-provider` from your local `./vandamme-config.toml`
3. `default-provider` from your user config `~/.config/vandamme-proxy/vandamme-config.toml`
4. `default-provider` from `src/config/defaults.toml` (defaults to "openai")

### Package Defaults

The `src/config/defaults.toml` file provides built-in defaults:
- Default provider: "openai"
- Fallback model aliases for providers like Poe

You can override any of these settings using environment variables or your own TOML configuration files.

---

## 📖 Core Concepts

### Provider Prefix Routing

Route requests by prefixing model names with the provider identifier:

```bash
# Format: provider:model_name
claude --model openai:gpt-4o         # Routes to OpenAI
claude --model poe:gemini-flash      # Routes to Poe
claude --model anthropic:claude-3    # Routes to Anthropic
claude --model gpt-4o                # Routes to VDM_DEFAULT_PROVIDER
```

**Providers are auto-discovered from environment variables:**
- `OPENAI_API_KEY` → creates "openai" provider
- `POE_API_KEY` → creates "poe" provider
- `CUSTOM_API_KEY` → creates "custom" provider

**[📚 Complete Routing Guide →](docs/provider-routing-guide.md)**

---

### Smart Model Aliases

Create memorable shortcuts with powerful substring matching:

```bash
# .env configuration
POE_ALIAS_FAST=gemini-flash
POE_ALIAS_HAIKU=gpt-4o-mini
ANTHROPIC_ALIAS_CHAT=claude-3-5-sonnet-20241022
```

**Intelligent Matching Rules:**
- **Case-Insensitive:** `fast`, `Fast`, `FAST` all match
- **Substring Matching:** `my-fast-model` matches `FAST` alias
- **Hyphen/Underscore:** `my-alias` and `my_alias` both match `MY_ALIAS`
- **Provider-Scoped:** Each alias is tied to a specific provider
- **Priority Order:** Exact match → Longest substring → Provider order → Alphabetical

**[📚 Model Aliases Guide →](docs/model-aliases.md)**

- **Automatic Fallbacks**: Default mappings for `haiku`, `sonnet`, `opus`
- **Project Overrides**: Local configuration files
- **User Preferences**: System-wide defaults

**[📚 Fallback Aliases →](docs/fallback-aliases.md)**

---

### Dual API Format Support

**OpenAI Format (default):**
```bash
PROVIDER_API_FORMAT=openai  # Requests converted to/from OpenAI format
```

**Anthropic Format (passthrough):**
```bash
PROVIDER_API_FORMAT=anthropic  # Zero conversion overhead, direct passthrough
```

**Mix formats in a single instance:**
```bash
OPENAI_API_FORMAT=openai         # Conversion mode
ANTHROPIC_API_FORMAT=anthropic   # Passthrough mode
BEDROCK_API_FORMAT=anthropic     # AWS Bedrock passthrough
```

This enables using Claude natively on AWS Bedrock, Google Vertex AI, or any Anthropic-compatible endpoint without conversion overhead.

**[📚 Anthropic API Support Guide →](ANTHROPIC_API_SUPPORT.md)**

---

### Secure API Key Passthrough

Enable client-provided API keys with the `!PASSTHRU` sentinel:

```bash
# Proxy stores and uses a static API key
OPENAI_API_KEY=sk-your-static-key

# Client provides their own key per-request
POE_API_KEY=!PASSTHRU
```

**Use Cases:**
- **Multi-Tenant Deployments** - Each client uses their own API keys
- **Cost Distribution** - Clients pay for their own API usage
- **Client Autonomy** - Users maintain control of their credentials
- **Gradual Migration** - Move providers to passthrough one at a time

**[📚 API Key Passthrough Guide →](docs/api-key-passthrough.md)**

---

## 🆚 Vandamme Proxy vs Alternatives

VanDamme Proxy is designed around a specific problem space:
acting as a multi-provider LLM gateway that is natively compatible with Claude Code and Anthropic’s SSE protocol, while still supporting OpenAI-style APIs and other providers.

Most alternatives solve adjacent but different problems. The comparisons below are scoped specifically to Claude Code compatibility and protocol behavior, not general LLM usage.

| Feature | Vandamme Proxy | LiteLLM | OpenRouter |
|---------|---------------|---------|------------|
| **Provider Routing** | ✅ Prefix-based (`provider:model`) | ✅ Config-based | ✅ Unified namespace |
| **Smart Aliases** | ✅ Substring matching + priorities | ❌ Exact match only | ❌ Not supported |
| **Dual API Formats** | ✅ OpenAI + Anthropic native | ✅ OpenAI only | ✅ OpenAI only |
| **API Key Passthrough** | ✅ `!PASSTHRU` sentinel | ⚠️ Limited support | ✅ Native support |
| **Mixed Auth Modes** | ✅ Static + Passthrough per-provider | ❌ Global only | ❌ Global only |
| **Middleware System** | ✅ Chain-of-responsibility | ⚠️ Limited hooks | ❌ Not extensible |
| **Claude Code Integration** | ✅ Zero-config | ⚠️ Manual setup | ⚠️ Manual setup |
| **Self-Hosted** | ✅ Full control | ✅ Full control | ❌ Cloud service only |
| **vdm CLI** | ✅ Integrated tooling | ❌ Not provided | ❌ Not provided |

### When to Choose Vandamme Proxy

**Choose Vandamme if you:**
- Use Claude Code CLI and want seamless multi-provider support
- Need flexible per-provider API key passthrough for multi-tenant scenarios
- Want smart model aliases with substring matching
- Require Anthropic-format native passthrough (AWS Bedrock, Google Vertex AI)
- Prefer lightweight design with minimal dependencies
- Want extensible middleware for custom request/response logic

**Choose LiteLLM if you:**
- Need enterprise-grade load balancing and automatic failover
- Require extensive logging and observability integrations
- Want managed caching layers and retry strategies

**Choose OpenRouter if you:**
- Prefer a managed cloud service over self-hosting
- Want access to exclusive model partnerships and providers
- Don't require self-hosted infrastructure

---

## 📚 Documentation

### 🚀 Getting Started
- [**Quick Start Guide**](QUICKSTART.md) - Get running in 5 minutes
- [**Architecture Overview**](CLAUDE.md) - Deep dive into design decisions
- [**Development Workflows**](docs/makefile-workflows.md) - Makefile targets and best practices

### 🌐 Feature Guides
- [**Multi-Provider Routing**](docs/provider-routing-guide.md) - Complete routing and configuration guide
- [**Smart Model Aliases**](docs/model-aliases.md) - Alias configuration and matching rules
- [**Fallback Model Aliases**](docs/fallback-aliases.md) - Automatic defaults for special model names
- [**API Key Passthrough**](docs/api-key-passthrough.md) - Security and multi-tenancy patterns
- [**Anthropic API Support**](ANTHROPIC_API_SUPPORT.md) - Dual-format operation details

### 📖 Reference
#### API Endpoints
- `POST /v1/messages` - Chat completions
- `POST /v1/messages/count_tokens` - Token counting
- `GET /v1/models` - List available models
- `GET /v1/aliases` - View active model aliases
- `GET /health` - Health check with provider status
- `GET /metrics/running-totals` - Usage metrics

#### CLI Commands
- `vdm server start` - Start the proxy server
- `vdm config setup` - Interactive configuration
- `vdm health server` - Check server health
- `vdm health upstream` - Test provider connectivity
- `vdm test connection` - Validate API access
- `vdm test models` - List available models

---

## 🛠️ Development

### Setup Development Environment

```bash
# Clone the repository
git clone https://github.com/CedarVerse/vandamme-proxy.git
cd vandamme-proxy

# Initialize development environment (recommended)
make init-dev

# Or install dependencies manually
make install-dev
make check-install
```

### Daily Development Workflow

```bash
# Start development server with hot reload
make dev

# Run tests (excluding e2e by default)
make test

# Run code quality checks
make check

# Format code
make format

# Quick validation (format + lint + quick tests)
make validate
```

### Testing Strategy

The project follows a three-tier testing pyramid:

1. **Unit Tests** (~90%): Fast, mocked tests using RESPX for HTTP-layer mocking
2. **Integration Tests** (~10%): Require running server, no external API calls
3. **E2E Tests** (<5%): Real API calls for critical validation (requires API keys)

```bash
# Run specific test suites
make test-unit          # Unit tests only (fastest)
make test-integration   # Integration tests (requires server)
make test-e2e          # E2E tests (requires API keys, incurs costs)
make test-all          # All tests including E2E
```

### Contributing

We welcome contributions! Please see our development guide for details:

- [**Development Workflows**](docs/makefile-workflows.md) - Makefile targets and best practices
- [**Architecture Overview**](CLAUDE.md) - Design decisions and code structure
- [**Code Style Guide**](docs/makefile-workflows.md#code-quality) - Formatting and linting standards

---

## 🔧 Advanced Configuration

### Environment Variables

#### Required (at least one provider)
```bash
OPENAI_API_KEY=sk-your-openai-key
ANTHROPIC_API_KEY=sk-ant-your-key
POE_API_KEY=your-poe-key
# Any {PROVIDER}_API_KEY creates a provider
```

#### Default Provider
```bash
# Default provider for models without provider prefixes
# Overrides the default-provider from src/config/defaults.toml
# If not set, uses value from defaults.toml (defaults to "openai")
VDM_DEFAULT_PROVIDER=openai
```

#### Provider Configuration
```bash
# API Format: "openai" (default) or "anthropic"
ANTHROPIC_API_FORMAT=anthropic

# Base URL (optional, has sensible defaults)
OPENAI_BASE_URL=https://api.openai.com/v1
AZURE_BASE_URL=https://your-resource.openai.azure.com

# API Version (for Azure)
AZURE_API_VERSION=2024-02-15-preview
```

#### Server Settings
```bash
HOST=0.0.0.0                    # Server host
PORT=8082                       # Server port
LOG_LEVEL=INFO                  # Logging level
MAX_TOKENS_LIMIT=4096           # Maximum tokens
REQUEST_TIMEOUT=90              # Request timeout in seconds
MAX_RETRIES=2                   # Retry attempts
```

#### Middleware Configuration
```bash
# Google Gemini thought signatures
GEMINI_THOUGHT_SIGNATURES_ENABLED=true
THOUGHT_SIGNATURE_CACHE_TTL=3600
THOUGHT_SIGNATURE_MAX_CACHE_SIZE=10000
```

#### Custom Headers
```bash
# Automatically converted to HTTP headers
CUSTOM_HEADER_ACCEPT=application/json
CUSTOM_HEADER_X_API_KEY=your-key
```

### Production Deployment

#### Docker Deployment
```bash
# Build and start with Docker Compose
docker compose up -d

# View logs
docker compose logs -f

# Stop services
docker compose down
```

#### Systemd Service
```bash
# Create systemd service file
sudo tee /etc/systemd/system/vandamme-proxy.service > /dev/null <<EOF
[Unit]
Description=Vandamme Proxy
After=network.target

[Service]
Type=simple
User=vandamme
WorkingDirectory=/opt/vandamme-proxy
Environment=HOST=0.0.0.0
Environment=PORT=8082
ExecStart=/opt/vandamme-proxy/.venv/bin/vdm server start
Restart=always

[Install]
WantedBy=multi-user.target
EOF

# Enable and start service
sudo systemctl enable vandamme-proxy
sudo systemctl start vandamme-proxy
```

---

## 📄 License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

---

## 🤝 Community

- **🐛 Issues:** [Report bugs and request features](https://github.com/CedarVerse/vandamme-proxy/issues)
- **💬 Discussions:** [Join community discussions](https://github.com/CedarVerse/vandamme-proxy/discussions)
- **📖 Repository:** [GitHub](https://github.com/CedarVerse/vandamme-proxy)

---

## 🌟 Acknowledgments

Built with ❤️ for the AI development community. Inspired by the need for seamless multi-provider integration in modern AI workflows.

---

**Keywords:** LLM gateway, API proxy, Claude Code, OpenAI, Anthropic, multi-provider, AI proxy, LLM router, API gateway, large language model, AI development, prompt engineering, model routing, API management
