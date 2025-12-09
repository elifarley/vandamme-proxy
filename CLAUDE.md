# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Vandamme Proxy is a FastAPI-based proxy server that converts Claude API requests to OpenAI-compatible API calls. It enables Claude Code CLI to work with various LLM providers (OpenAI, Azure OpenAI, Ollama, and any OpenAI-compatible API).

## Development Commands

### Setup and Installation

```bash
# Using UV (recommended)
uv sync --extra cli

# Or using pip
pip install -r requirements.txt
```

### Running the Server

```bash
# Using the vdm CLI (recommended)
vdm start

# Direct execution
python start_proxy.py

# Or with Docker
docker compose up -d
```

### Testing

```bash
# Run comprehensive integration tests
python src/test_claude_to_openai.py

# Test configuration and connectivity
vdm test connection
vdm test models
vdm health upstream
vdm config validate

# Run unit tests (if available)
pytest tests/
```

### Code Quality

```bash
# Format code
uv run black src/
uv run isort src/

# Type checking
uv run mypy src/
```

## Architecture

### Core Components

1. **Request/Response Flow**:
   - `src/api/endpoints.py` - FastAPI endpoints (`/v1/messages`, `/v1/messages/count_tokens`, `/health`, `/test-connection`)
   - `src/conversion/request_converter.py` - Converts Claude API format to OpenAI format
   - `src/conversion/response_converter.py` - Converts OpenAI responses back to Claude format
   - `src/core/client.py` - OpenAI API client with retry logic and connection pooling
   - `src/core/model_manager.py` - Model mapping (haiku→SMALL_MODEL, sonnet→MIDDLE_MODEL, opus→BIG_MODEL)

2. **Authentication & Security**:
   - Optional client API key validation via `ANTHROPIC_API_KEY` environment variable
   - If `ANTHROPIC_API_KEY` is set in the proxy, clients must provide matching key
   - If not set, any client API key is accepted

3. **Configuration**:
   - `src/core/config.py` - Central configuration management
   - Environment variables loaded from `.env` file via `python-dotenv`
   - Custom headers support via `CUSTOM_HEADER_*` environment variables

4. **Data Models**:
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

### Model Mapping

Default mappings (configurable via environment variables):
- Models with "haiku" → `SMALL_MODEL` (default: gpt-4o-mini)
- Models with "sonnet" → `MIDDLE_MODEL` (default: same as BIG_MODEL)
- Models with "opus" → `BIG_MODEL` (default: gpt-4o)

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

Required:
- `OPENAI_API_KEY` - API key for target provider

Security:
- `ANTHROPIC_API_KEY` - If set, clients must provide this exact key

Model Configuration:
- `BIG_MODEL` - For opus requests (default: gpt-4o)
- `MIDDLE_MODEL` - For sonnet requests (default: value of BIG_MODEL)
- `SMALL_MODEL` - For haiku requests (default: gpt-4o-mini)

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
