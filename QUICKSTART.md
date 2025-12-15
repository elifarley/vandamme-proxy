# Quick Start Guide

Get up and running with Vandamme Proxy in 3 minutes.

## 🚀 Installation

### Option 1: Install from PyPI (Recommended)

```bash
# Using pip
pip install vandamme-proxy

# Or using uv (fastest)
uv pip install vandamme-proxy

# Verify installation
vdm version
```

### Option 2: Install from Source (Development)

```bash
# Clone the repository
git clone https://github.com/stellar-amenities/vandamme-proxy.git
cd vandamme-proxy

# Install with development dependencies
make install-dev

# Verify installation
vdm version
```

## ⚙️ Configuration

Vandamme Proxy uses a hierarchical configuration system. Settings from higher levels override those from lower levels:

```
Environment Variables (highest priority)
├── Local: ./vandamme-config.toml
├── User: ~/.config/vandamme-proxy/vandamme-config.toml
└── Package: src/config/defaults.toml (lowest priority)
```

The `VDM_DEFAULT_PROVIDER` environment variable overrides the default provider from `src/config/defaults.toml`.

### Interactive Setup (Easiest)

```bash
# Interactive configuration wizard
vdm config setup
```

The wizard will guide you through:
- Selecting your LLM provider(s)
- Entering API keys
- Setting default provider
- Configuring optional features

### Manual Configuration

Create a `.env` file with your provider configuration:

#### OpenAI
```bash
OPENAI_API_KEY="sk-your-openai-key"
```

#### Poe.com
```bash
POE_API_KEY="your-poe-api-key"
VDM_DEFAULT_PROVIDER="poe"  # Optional: overrides defaults.toml
```

#### Anthropic (Direct)
```bash
ANTHROPIC_API_KEY="sk-ant-your-key"
ANTHROPIC_BASE_URL="https://api.anthropic.com"
ANTHROPIC_API_FORMAT="anthropic"
VDM_DEFAULT_PROVIDER="anthropic"  # Optional: overrides defaults.toml
```

#### Azure OpenAI
```bash
AZURE_API_KEY="your-azure-key"
AZURE_BASE_URL="https://your-resource.openai.azure.com/"
AZURE_API_VERSION="2024-03-01-preview"
VDM_DEFAULT_PROVIDER="azure"  # Optional: overrides defaults.toml
```

#### Local Models (Ollama)
```bash
OLLAMA_API_KEY="dummy-key"
OLLAMA_BASE_URL="http://localhost:11434/v1"
VDM_DEFAULT_PROVIDER="ollama"  # Optional: overrides defaults.toml
```

#### Multiple Providers
```bash
# Configure multiple providers simultaneously
OPENAI_API_KEY="sk-..."
POE_API_KEY="..."
ANTHROPIC_API_KEY="sk-ant-..."
ANTHROPIC_BASE_URL="https://api.anthropic.com"
ANTHROPIC_API_FORMAT="anthropic"

# Set default provider (optional, overrides defaults.toml)
VDM_DEFAULT_PROVIDER="poe"
```

See `.env.example` for all configuration options.

## 🎯 Usage

### Start the Proxy Server

```bash
# Development mode (hot reload)
vdm server start --reload

# Production mode
vdm server start

# Custom host/port
vdm server start --host 0.0.0.0 --port 8080
```

### Use with Claude Code CLI

```bash
# Configure Claude Code to use the proxy
export ANTHROPIC_BASE_URL=http://localhost:8082

# Use Claude Code normally - it now uses your configured provider(s)
claude "Hello, world!"

# Use specific provider via model prefix
claude --model poe:gpt-4o "Quick response"
claude --model anthropic:claude-3-5-sonnet-20241022 "Use Anthropic directly"
```

### Test Your Setup

```bash
# Check proxy health
vdm health server

# Test upstream provider connectivity
vdm health upstream

# Test specific model
vdm test model claude-3-5-sonnet-20241022

# Validate configuration
vdm config validate
```

## 🎯 How It Works

Vandamme Proxy sits between Claude Code and your LLM provider:

```
Claude Code → Vandamme Proxy → LLM Provider(s)
              ↓ Converts
              ↓ Routes
              ↓ Manages
```

### Request Flow Examples

| Your Request | Provider Selection | Result |
|-------------|-------------------|---------|
| `claude-3-5-sonnet-20241022` | Uses configured default provider | Routes to default (from VDM_DEFAULT_PROVIDER or defaults.toml) |
| `poe:gpt-4o` | Uses Poe provider | Routes to Poe with `gpt-4o` model |
| `anthropic:claude-3-5-sonnet` | Uses Anthropic provider | Direct passthrough to Anthropic |
| `openai:gpt-4o` | Uses OpenAI provider | Routes to OpenAI |

## 📋 What You Need

- **Python**: 3.10 or higher
- **API Key**: At least one provider API key
- **Claude Code**: Installed and configured
- **Time**: ~3 minutes to set up

## 🔧 Default Settings

- **Server**: `http://localhost:8082`
- **Format**: Auto-detected based on provider (`openai` or `anthropic`)
- **Features**: Streaming ✓ | Function calling ✓ | Vision ✓ | Tool use ✓

## 🧪 Verify Your Setup

```bash
# 1. Check server is running
vdm health server

# 2. Test provider connectivity
vdm health upstream

# 3. Test actual message
curl -X POST http://localhost:8082/v1/messages \
  -H "Content-Type: application/json" \
  -d '{
    "model": "claude-3-5-sonnet-20241022",
    "max_tokens": 100,
    "messages": [{"role": "user", "content": "Hello!"}]
  }'

# 4. List available models
curl http://localhost:8082/v1/models
```

## 🚦 Next Steps

**Basic Usage:**
- [Provider Routing Guide](docs/provider-routing-guide.md) - Multi-provider setup
- [Model Aliases](docs/model-aliases.md) - Smart model shortcuts
- [API Key Passthrough](docs/api-key-passthrough.md) - Multi-tenant deployments

**Advanced:**
- [Makefile Workflows](docs/makefile-workflows.md) - Development best practices
- [Anthropic API Support](ANTHROPIC_API_SUPPORT.md) - Dual API format details
- [Configuration Reference](.env.example) - All environment variables

## 💡 Common Scenarios

### Using Multiple Providers

```bash
# Configure in .env
OPENAI_API_KEY="sk-..."
POE_API_KEY="..."
VDM_DEFAULT_PROVIDER="poe"

# Use different providers per request
claude --model openai:gpt-4o "Use OpenAI"
claude --model poe:gemini-flash "Use Poe"
claude "Use default (poe)"
```

### Smart Model Aliases

```bash
# Configure in .env (provider-specific)
POE_ALIAS_FAST=gpt-4o-mini
ANTHROPIC_ALIAS_SMART=claude-3-5-sonnet-20241022

# Use aliases in requests
claude --model fast "Quick response"
claude --model smart "Complex reasoning"
```

### API Key Passthrough (Multi-Tenant)

```bash
# Allow clients to use their own API keys
export OPENAI_API_KEY="!PASSTHRU"

# Clients pass their key in request headers
claude --api-key "client-api-key" "Hello"
```

---

**That's it!** 🎉 You now have a universal LLM gateway for Claude Code.

Need help? Check the [main README](README.md) or [open an issue](https://github.com/stellar-amenities/vandamme-proxy/issues).