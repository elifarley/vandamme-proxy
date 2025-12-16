# Provider-Specific Model Aliases Configuration Guide

## Overview

The provider-specific alias mechanism allows you to create flexible model aliases scoped to specific providers. Using the pattern `<PROVIDER>_ALIAS_<NAME>`, you can create case-insensitive substring matching for model selection. This feature makes it easier to work with multiple models and providers by creating memorable names and automatic matching patterns.

## Key Features

- **Case-Insensitive Matching**: `OPENAI_ALIAS_FAST` matches "fast", "FAST", "FastModel", etc.
- **Substring Matching**: Any model name containing "haiku" will match `POE_ALIAS_HAIKU`
- **Flexible Hyphen/Underscore Matching**: Aliases match model names regardless of whether they use hyphens or underscores
  - `OPENAI_ALIAS_MY_ALIAS` matches "my-alias", "my_alias", "oh-my-alias-model", and "oh-my_alias_model"
- **Provider-Scoped**: Each alias is tied to a specific provider, eliminating ambiguity
- **Target Values**: Target values cannot use provider prefixes as the provider is specified in the key itself
- **Flexible Naming**: Support any alias name, not just tier-specific ones
- **Automatic Fallbacks**: Sensible defaults for common Claude model names (haiku, sonnet, opus) when not explicitly configured

## Built-in Fallback Aliases

The proxy provides automatic fallback aliases for common Claude model names. These are used when you haven't explicitly configured an alias for a model name:

| Special Name | Poe Provider (Default) | Description |
|--------------|------------------------|-------------|
| `haiku` | `grok-4.1-fast-non-reasoning` | Fast, lightweight model |
| `sonnet` | `glm-4.6` | Balanced, versatile model |
| `opus` | `gpt-5.2` | Powerful, advanced model |

These fallbacks are automatically applied when:
- You use the special model name (e.g., "haiku", "sonnet", "opus")
- You haven't configured an explicit alias for that name
- The provider has fallback defaults configured

You can override these fallbacks by setting your own aliases:
```bash
# Override the haiku fallback
POE_ALIAS_HAIKU=my-preferred-haiku-model-in-this-provider
```

## Configuration

### 1. Environment Variables (Explicit Configuration)

Configure aliases using environment variables. These take precedence over fallback defaults.

```bash
# Provider-specific aliases
OPENAI_ALIAS_CHAT=gpt-4o
POE_ALIAS_HAIKU= grok-4.1-fast-non-reasoning
```

### 2. TOML Configuration Files (Fallback Defaults)

Configure fallback defaults using TOML files. The proxy loads configurations from multiple locations in order of priority:

#### Configuration Hierarchy (Highest to Lowest Priority)

1. **Project Overrides**: `./vandamme-config.toml`
   - Local to your project
   - Overrides all other configurations

2. **User Configuration**: `~/.config/vandamme-proxy/vandamme-config.toml`
   - User-specific settings
   - Shared across all projects

3. **Package Defaults**: `src/config/defaults.toml`
   - Built-in defaults
   - Includes default provider and fallback aliases
   - Lowest priority

#### Example TOML Configuration

```toml
# src/config/defaults.toml - Package defaults
[defaults]
# Default provider to use when not specified via environment variable
# Can be overridden by VDM_DEFAULT_PROVIDER environment variable
default-provider = "openai"

[aliases]
# Fallback aliases for special model names
# These are only used when users haven't configured the alias themselves

[poe.aliases]
haiku = "grok-4.1-fast-non-reasoning"
sonnet = "glm-4.6"
opus = "gpt-5.2"
# You can add more aliases as needed
fast = "model-1-turbo"

[openai.aliases]
haiku = "gpt-4o-mini"
fast = "gpt-4o"

[anthropic.aliases]
haiku = "claude-3-5-haiku-20241022"
chat = "claude-3-5-sonnet-20241022"
```

You can override these defaults in your own `./vandamme-config.toml` or `~/.config/vandamme-proxy/vandamme-config.toml` files.

### Tier-Based Aliases

Create tier-based aliases for consistent model selection:

```bash
# Tier-based aliases for Claude Code model selection
POE_ALIAS_HAIKU=grok-4.1-fast-non-reasoning
OPENAI_ALIAS_SONNET=gpt-4o
ANTHROPIC_ALIAS_OPUS=claude-3-opus-20240229
```

### Custom Aliases

Create aliases for specific use cases:

```bash
# Use case-specific aliases
ANTHROPIC_ALIAS_CHAT=claude-3-5-sonnet-20241022
OPENAI_ALIAS_FAST=gpt-4o-mini
OPENAI_ALIAS_SMART=o1-preview
OPENAI_ALIAS_CODE=o1-preview
OPENAI_ALIAS_EMBED=text-embedding-ada-002
```

### Provider-Specific Aliases

Create aliases for the same use case across different providers:

```bash
# Fast models from different providers
OPENAI_ALIAS_FAST=gpt-4o-mini
ANTHROPIC_FAST=claude-3-5-haiku-20241022
POE_FAST=grok-4.1-fast-non-reasoning
```

## How It Works

### Alias Resolution Algorithm

1. **Load Aliases**: Read all `<PROVIDER>_ALIAS_*` environment variables at startup
2. **Validate Providers**: Ensure each provider exists in the configuration
3. **Normalize**: Store alias names in lowercase for case-insensitive matching
4. **Match**: Find aliases across all providers where the alias name is a substring of the requested model
5. **Prioritize**: Select the best match based on priority rules
6. **Resolve**: Return the provider-prefixed target value

### Priority Order

When multiple aliases match a model name:

1. **Exact Match First**: If an alias exactly matches the model name, it's chosen immediately
   - Underscores in aliases are converted to hyphens for exact matching
2. **Longest Substring**: Among substring matches, the longest alias name wins
3. **Provider Order**: If multiple aliases have the same length, sort by provider name alphabetically
4. **Alphabetical Order**: Then sort by alias name alphabetically

### Examples

```bash
# Configuration
ANTHROPIC_ALIAS_CHAT=claude-3-5-sonnet-20241022
OPENAI_ALIAS_FAST=gpt-4o-mini
POE_ALIAS_HAIKU=grok-4.1-fast-non-reasoning
```

**Resolution Examples**:

- `"chat"` → `anthropic:claude-3-5-sonnet-20241022` (exact match)
- `"ChatModel"` → `anthropic:claude-3-5-sonnet-20241022` (case-insensitive)
- `"my-haiku-model"` → `poe:grok-4.1-fast-non-reasoning` (substring match)
- `"Super-Fast-Response"` → `openai:gpt-4o-mini` (substring match)
- `"chathaiiku"` → `anthropic:claude-3-5-sonnet-20241022` (longest match wins)
- `"my-alias"` → `openai:gpt-4o` (from `OPENAI_ALIAS_MY_ALIAS`, underscore to hyphen)
- `"oh-my-alias-is-great"` → `openai:gpt-4o` (from `OPENAI_ALIAS_MY_ALIAS`, substring match with normalization)

## API Usage

### List All Aliases

```bash
# List all configured aliases
curl http://localhost:8082/v1/aliases
```

**Response**:
```json
{
  "object": "list",
  "aliases": {
    "poe": {
      "haiku": "grok-4.1-fast-non-reasoning",
      "fast": "gpt-4o-mini"
    },
    "openai": {
      "chat": "gpt-4o",
      "smart": "o1-preview"
    },
    "anthropic": {
      "code": "claude-3-5-sonnet-20241022"
    }
  },
  "total": 5
}
```

### Using Aliases in Requests

```bash
# Direct alias match
curl -X POST http://localhost:8082/v1/messages \
  -H "Content-Type: application/json" \
  -d '{
    "model": "haiku",
    "max_tokens": 100,
    "messages": [{"role": "user", "content": "Hello"}]
  }'

# Substring match
curl -X POST http://localhost:8082/v1/messages \
  -H "Content-Type: application/json" \
  -d '{
    "model": "my-custom-haiku-model",
    "max_tokens": 100,
    "messages": [{"role": "user", "content": "Hello"}]
  }'
```

### Claude Code Integration

Use aliases with Claude Code CLI:

```bash
# Set up proxy
export ANTHROPIC_BASE_URL=http://localhost:8082

# Use alias directly
claude --model haiku "Quick response needed"

# Use substring matching
claude --model any-Haiku-model-will-do "Process this quickly"
```

## Environment Variable Rules

### Naming Convention

- **Prefix**: All aliases must follow pattern `<PROVIDER>_ALIAS_`
- **Case**: Variable names are case-sensitive but aliases are stored in lowercase
- **Characters**: Use letters, numbers, and underscores in alias names
- **Conversion**: Underscores in variable names become part of the alias name but also match hyphens

### Value Format

```bash
# Plain model name (provider is specified in the variable prefix)
OPENAI_ALIAS_FAST=gpt-4o-mini

# Model names with special characters
CUSTOM_PROVIDER_ALIAS_SPECIAL=model-v1.2.3
```

### Validation Rules

1. **No Empty Values**: Empty or whitespace-only values are skipped
2. **No Circular References**: An alias cannot reference itself
3. **Format Validation**: Values must match valid model name patterns
4. **Automatic Logging**: Invalid configurations are logged with warnings

## Best Practices

### Naming Conventions

```bash
# Use descriptive, memorable names
OPENAI_ALIAS_FAST=gpt-4o-mini
OPENAI_ALIAS_SMART=o1-preview
ANTHROPIC_ALIAS_CHAT=claude-3-5-sonnet-20241022

# Use consistent patterns across providers
OPENAI_ALIAS_FAST=gpt-4o-mini
ANTHROPIC_ALIAS_FAST=claude-3-5-haiku-20241022
POE_ALIAS_FAST=grok-4.1-fast-non-reasoning
```

### Organize by Use Case

```bash
# Development aliases
OPENAI_ALIAS_DEV_FAST=gpt-4o-mini
ANTHROPIC_ALIAS_DEV_SMART=o1-preview

# Production aliases
ANTHROPIC_ALIAS_PROD_CHAT=claude-3-5-sonnet-20241022
OPENAI_ALIAS_PROD_ANALYTICS=o1-preview

# Testing aliases
POE_ALIAS_TEST_MOCK=gpt-4o-mini
```

### Documentation

Document your aliases for team members:

```bash
# Team-specific aliases - see docs/model-aliases.md
# To use these aliases in Claude Code,
# run `/model team-chat` or `/model team-code`
ANTHROPIC_ALIAS_TEAM_CHAT=claude-3-5-sonnet-20241022
OPENAI_ALIAS_TEAM_CODE=o1-preview
```

## Troubleshooting

### Common Issues

#### Alias Not Matching

```bash
# Check if alias is loaded
curl http://localhost:8082/v1/aliases

# Verify model name contains the alias substring
# Example: "haiku" matches "my-haiku-model" but not "haikumodel"
```

#### Circular Reference

```bash
# Error: Circular alias reference detected
POE_ALIAS_WRONG=wrong  # Invalid
```

### Debug Logging

Enable debug logging to see alias resolution:

```bash
export LOG_LEVEL=DEBUG
vdm server start
```

**Sample Debug Output**:
```
DEBUG: Resolved model alias 'my-haiku-model' -> 'poe:gpt-4o-mini' (matched alias 'haiku')
```

### Validation Commands

```bash
# Check loaded aliases
curl http://localhost:8082/v1/aliases

# Test alias resolution
curl -X POST http://localhost:8082/v1/messages \
  -H "Content-Type: application/json" \
  -d '{"model": "test-alias-name", "max_tokens": 1, "messages": [{"role": "user", "content": "test"}]}'
```

## Benefits of Provider-Specific Aliases

1. **Clear Provider Association**: Each alias is explicitly tied to a provider
2. **Simplified Configuration**: No need to repeat provider in target values
3. **Better Organization**: Provider-scoped aliases are easier to manage
4. **Validation**: System validates that providers exist before loading aliases

## Security Considerations

### Access Control

- **Admin Only**: Only administrators can configure aliases via environment variables
- **Runtime Protection**: Aliases cannot be modified at runtime
- **No User Input**: Alias values are not influenced by user requests

### Provider Authentication

- **Existing Security**: Provider API keys are still required and validated
- **No Bypass**: Aliases don't bypass any authentication mechanisms
- **Header Preservation**: Custom headers are still applied to resolved models

## Performance

### Impact

- **Minimal Overhead**: Alias resolution is O(n) where n is the number of aliases
- **Cached at Startup**: Aliases are loaded once and cached in memory
- **No Network Calls**: Resolution happens entirely in-memory
- **Typical Usage**: With < 100 aliases, the performance impact is negligible

### Optimization

- **Order Matters**: Place more specific aliases before general ones
- **Avoid Overlaps**: Minimize overlapping alias names for predictable behavior
- **Regular Cleanup**: Remove unused aliases to maintain clarity

## Reference

### API Endpoints

#### GET /v1/aliases

List all configured model aliases.

**Response Format**:
```json
{
  "object": "list",
  "data": [
    {
      "alias": "string",
      "target": "string",
      "provider": "string",
      "model": "string"
    }
  ]
}
```

### Environment Variables

| Variable | Format | Example | Description |
|----------|--------|---------|-------------|
| `<PROVIDER>_ALIAS_<NAME>` | `<TARGET_MODEL>` | `OPENAI_ALIAS_FAST=gpt-4o-mini` | Create a provider-scoped model alias |

### Error Codes

| Error | Description | Solution                                         |
|-------|-------------|--------------------------------------------------|
| 401 | Invalid API key | Check `PROXY_API_KEY` configuration              |
| 404 | Provider not found | Configure the provider with `{PROVIDER}_API_KEY` |
| 500 | Internal server error | Check server logs for alias resolution errors    |

### Supported Characters

**Alias Names**:
- Letters: a-z, A-Z
- Numbers: 0-9
- Underscore: _

**Target Values**:
- Letters, numbers, hyphens, slashes, dots, colons
- Provider prefix format: `provider:model`
- Plain model format: `model-name`
