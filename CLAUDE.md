# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Vandamme Proxy is a FastAPI-based proxy server that converts Claude API requests to OpenAI-compatible API calls. It enables Claude Code CLI to work with various LLM providers (OpenAI, Azure OpenAI, Ollama, and any OpenAI-compatible API).

## Development Commands

### Setup and Installation

```bash
# Quick start (recommended)
make init-dev

# Or step by step
make venv
make install-dev
make check-install

# Using UV directly
uv sync --extra cli

# Or using pip
pip install -r requirements.txt
```

### Running the Server

```bash
# Using the vdm CLI (recommended)
vdm server start

# Direct execution
python start_proxy.py

# Or with Docker
docker compose up -d
```

### Testing

```bash
# Run all tests
make test

# Run comprehensive integration tests
make test-integration

# Run unit tests
make test-unit

# Quick tests without coverage
make test-quick

# Test configuration and connectivity
vdm test connection
vdm test models
vdm health upstream
vdm config validate
```

### Code Quality

```bash
# Format code
make format

# Type checking
make type-check

# Run all code quality checks
make check

# Quick check (format + lint only, skip type-check)
make quick-check

# Pre-commit checks (format + all checks)
make pre-commit
```

### Common Development Tasks

```bash
# Install dependencies (production)
make install

# Install in development mode (editable)
make install-dev

# Create virtual environment
make venv

# Initialize complete development environment
make init-dev

# Verify installation
make check-install

# Run development server with hot reload
make dev

# Check proxy server health
make health

# Run full CI pipeline (install, check, test, build)
make ci

# Build distribution packages
make build

# Clean temporary files and caches
make clean

# Show all available targets
make help

# Show project version
make version

# Generate .env template file
make env-template
```

## Architecture

### Core Components

1. **Request/Response Flow**:
   - `src/api/endpoints.py` - FastAPI endpoints (`/v1/messages`, `/v1/messages/count_tokens`, `/v1/models`, `/health`, `/test-connection`)
   - `src/conversion/request_converter.py` - Converts Claude API format to OpenAI format
   - `src/conversion/response_converter.py` - Converts OpenAI responses back to Claude format
   - `src/core/client.py` - OpenAI API client with retry logic and connection pooling
   - `src/core/anthropic_client.py` - Anthropic-compatible API client for direct passthrough
   - `src/core/provider_manager.py` - Multi-provider management with format selection
   - `src/core/model_manager.py` - Model name resolution (passes through Claude model names unchanged)

2. **Dual-Mode Operation**:
   - **OpenAI Mode**: Converts Claude requests to OpenAI format, processes, converts back
   - **Anthropic Mode**: Direct passthrough for Anthropic-compatible APIs without conversion
   - Mode is automatically selected based on provider's `api_format` configuration

3. **Provider Management**:
   - Support for multiple LLM providers (OpenAI, Anthropic, Azure, custom endpoints)
   - Each provider can be configured as `api_format=openai` or `api_format=anthropic`
   - Provider selection via model prefix: `provider:model_name` (e.g., `anthropic:claude-3-sonnet`)
   - Falls back to default provider if no prefix specified

4. **Authentication & Security**:
   - **Proxy Authentication**: Optional client API key validation via `ANTHROPIC_API_KEY` environment variable
     - This controls access TO the proxy itself, not to external providers
     - If `ANTHROPIC_API_KEY` is set, clients must provide this exact key to use the proxy
     - If not set, the proxy accepts all requests (open access)
   - **Provider Authentication**: Each provider has its own API key (e.g., `OPENAI_API_KEY`, `ANTHROPIC_API_KEY` for provider)
     - These are separate from proxy authentication
     - Used to authenticate with the actual LLM providers

5. **Configuration**:
   - `src/core/config.py` - Central configuration management
   - `src/core/provider_config.py` - Per-provider configuration management
   - Environment variables loaded from `.env` file via `python-dotenv`
   - Custom headers support via `CUSTOM_HEADER_*` environment variables

6. **Data Models**:
   - `src/models/claude.py` - Pydantic models for Claude API format
   - `src/models/openai.py` - Pydantic models for OpenAI API format

### Request Conversion Details

The converter handles:
- **System messages**: Converts Claude's system parameter to OpenAI system role messages
- **User/Assistant messages**: Direct role mapping with content transformation
- **Tool use**: Converts Claude's tool_use blocks to OpenAI function calling format
- **Tool results**: Converts Claude's tool_result blocks to OpenAI tool messages
- **Images**: Converts base64-encoded images in content blocks
- **Streaming**: Full Server-Sent Events (SSE) support with cancellation handling

### Model Names

The proxy passes Claude model names through unchanged. Claude Code handles model mapping via its own environment variables:
- `ANTHROPIC_DEFAULT_HAIKU_MODEL`
- `ANTHROPIC_DEFAULT_SONNET_MODEL`
- `ANTHROPIC_DEFAULT_OPUS_MODEL`

### Custom Headers

Environment variables prefixed with `CUSTOM_HEADER_` are automatically converted to HTTP headers:
- `CUSTOM_HEADER_ACCEPT` → `ACCEPT` header
- `CUSTOM_HEADER_X_API_KEY` → `X-API-KEY` header
- Underscores in env var names become hyphens in header names

## Key Files

- `start_proxy.py` - Entry point script (legacy, use vdm CLI instead)
- `src/main.py` - FastAPI app initialization
- `src/cli/main.py` - Main CLI entry point for vdm command
- `src/cli/commands/` - CLI command implementations
- `src/api/endpoints.py` - Main API endpoints
- `src/core/config.py` - Configuration management (83 lines)
- `src/conversion/request_converter.py` - Claude→OpenAI request conversion
- `src/conversion/response_converter.py` - OpenAI→Claude response conversion

## Environment Variables

Required (at least one provider):
- `OPENAI_API_KEY` - API key for OpenAI provider
- `{PROVIDER}_API_KEY` - API key for any configured provider (e.g., `ANTHROPIC_API_KEY`, `AZURE_API_KEY`)

Provider Configuration:
- `{PROVIDER}_API_FORMAT` - API format: "openai" (default) or "anthropic"
- `{PROVIDER}_BASE_URL` - Base URL for the provider
- `DEFAULT_PROVIDER` - Default provider to use (defaults to "openai")

Examples:
```bash
# OpenAI provider (default format)
OPENAI_API_KEY=sk-...

# Anthropic provider (direct passthrough)
ANTHROPIC_API_KEY=sk-ant-...
ANTHROPIC_BASE_URL=https://api.anthropic.com
ANTHROPIC_API_FORMAT=anthropic

# AWS Bedrock (Anthropic-compatible)
BEDROCK_API_KEY=...
BEDROCK_BASE_URL=https://bedrock-runtime.us-east-1.amazonaws.com
BEDROCK_API_FORMAT=anthropic

# Azure OpenAI
AZURE_API_KEY=...
AZURE_BASE_URL=https://your-resource.openai.azure.com
AZURE_API_FORMAT=openai
AZURE_API_VERSION=2024-02-15-preview
```

Security (Proxy Authentication):
- `ANTHROPIC_API_KEY` - Optional proxy authentication key
  - If set, clients must provide this exact key to access the proxy
  - This is NOT related to any external provider's API key
  - This controls access TO the proxy, not access to provider APIs
  - Example: Set this to require a specific API key from Claude Code CLI users


API Configuration:
- `OPENAI_BASE_URL` - API base URL (default: https://api.openai.com/v1)
- `AZURE_API_VERSION` - For Azure OpenAI deployments

Server Settings:
- `HOST` - Server host (default: 0.0.0.0)
- `PORT` - Server port (default: 8082)
- `LOG_LEVEL` - Logging level (default: INFO)

Performance:
- `MAX_TOKENS_LIMIT` - Maximum tokens (default: 4096)
- `MIN_TOKENS_LIMIT` - Minimum tokens (default: 100)
- `REQUEST_TIMEOUT` - Request timeout in seconds (default: 90)
- `MAX_RETRIES` - Retry attempts (default: 2)

## Common Tasks

### Testing with Claude Code CLI

```bash
# Start proxy
python start_proxy.py

# Use Claude Code with proxy (if ANTHROPIC_API_KEY not set in proxy)
ANTHROPIC_BASE_URL=http://localhost:8082 ANTHROPIC_API_KEY="any-value" claude

# Use Claude Code with proxy (if ANTHROPIC_API_KEY is set in proxy)
ANTHROPIC_BASE_URL=http://localhost:8082 ANTHROPIC_API_KEY="exact-matching-key" claude
```

### Using Anthropic-Compatible Providers

#### Direct Anthropic API
```bash
# Configure for direct Anthropic API access
ANTHROPIC_API_KEY=sk-ant-...
ANTHROPIC_BASE_URL=https://api.anthropic.com
ANTHROPIC_API_FORMAT=anthropic
DEFAULT_PROVIDER=anthropic
```

#### AWS Bedrock
```bash
# Configure for AWS Bedrock with Claude models
BEDROCK_API_KEY=your-aws-key
BEDROCK_BASE_URL=https://bedrock-runtime.us-east-1.amazonaws.com
BEDROCK_API_FORMAT=anthropic
DEFAULT_PROVIDER=bedrock

# Use with specific model
ANTHROPIC_BASE_URL=http://localhost:8082 claude --model bedrock:anthropic.claude-3-sonnet-20240229-v1:0
```

#### Google Vertex AI
```bash
# Configure for Google Vertex AI (Anthropic models)
VERTEX_API_KEY=your-vertex-key
VERTEX_BASE_URL=https://generativelanguage.googleapis.com/v1beta
VERTEX_API_FORMAT=anthropic
DEFAULT_PROVIDER=vertex
```

#### Provider Selection in Requests

You can specify which provider to use per request:

1. **Default Provider**: Uses the configured `DEFAULT_PROVIDER`
   ```bash
   # Uses default provider
   claude --model claude-3-5-sonnet-20241022
   ```

2. **Provider Prefix**: Specify provider in model name
   ```bash
   # Use specific provider
   claude --model anthropic:claude-3-5-sonnet-20241022
   claude --model openai:gpt-4o
   claude --model bedrock:anthropic.claude-3-sonnet-20240229-v1:0
   ```

3. **Environment Override**: Override default provider temporarily
   ```bash
   # Temporarily use different provider
   DEFAULT_PROVIDER=anthropic claude
   ```

### Testing Endpoints

```bash
# Health check
curl http://localhost:8082/health

# Test OpenAI connectivity
curl http://localhost:8082/test-connection

# Test message endpoint
curl -X POST http://localhost:8082/v1/messages \
  -H "Content-Type: application/json" \
  -H "x-api-key: your-key" \
  -d '{
    "model": "claude-3-5-sonnet-20241022",
    "max_tokens": 100,
    "messages": [{"role": "user", "content": "Hello!"}]
  }'
```

### Debugging

- Set `LOG_LEVEL=DEBUG` to see detailed request/response conversions
- Check `src/core/logging.py` for logging configuration
- Request/response conversion is logged in `request_converter.py:88`

## Important Notes

- The proxy uses async/await throughout for high concurrency
- Connection pooling is managed by the OpenAI client
- Streaming responses support client disconnection/cancellation
- Token counting endpoint uses character-based estimation (4 chars ≈ 1 token)
- Error responses are classified and converted to Claude API format
