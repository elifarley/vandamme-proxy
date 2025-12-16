# Multi-Provider Routing Guide

## Understanding Vandamme Proxy

Vandamme Proxy transforms Claude Code's single-provider limitation into a flexible, multi-provider gateway, including OpenAI- and Anthropic-compatible API providers.

This guide explains how it works and helps you leverage its full capabilities.

## From Single Provider to Multi-Provider Gateway

### Traditional Proxy Approach
A typical proxy acts as a simple reverse proxy:
```
Client Request → Proxy → Single API Provider
```
- All requests go to one provider
- Uses one static API key
- Limited to a single service

### Vandamme's Multi-Provider Approach
Vandamme enables intelligent routing:
```
Client Request → Vandamme → Multiple API Providers
                           ├── OpenAI
                           ├── Poe
                           ├── Azure OpenAI
                           ├── Anthropic
                           ├── Custom Endpoints
                           └── ... any OpenAI-compatible API providers (automatic translation)
                           └── ... any Anthropic-compatible API providers (request pass-through)
```

## Key Concepts

### 1. Provider Prefix Routing

Specify the provider directly in the model name, or omit to use the default provider (set in `VDM_DEFAULT_PROVIDER` env var or defaults.toml):

```python
# Format: provider:model_name
claude --model openai:gpt-4o             # Routes to OpenAI
claude --model poe:glm-4.6               # Routes to Poe
claude --model azure:gpt-4               # Routes to Azure OpenAI
claude --model gpt-4                     # Routes to the default provider (from VDM_DEFAULT_PROVIDER or defaults.toml)
```

### 2. Automatic Provider Discovery

Vandamme automatically discovers providers from environment variables:

```bash
# The presence of any {PROVIDER}_API_KEY env var creates a provider
OPENAI_API_KEY=sk-xxx          # Creates "openai" provider
POE_API_KEY=sk-xxx             # Creates "poe" provider
AZURE_API_KEY=sk-xxx           # Creates "azure" provider
CUSTOM_API_KEY=sk-xxx          # Creates "custom" provider
```

### 3. Per-Provider Configuration

Each provider can have its own complete configuration:

```bash
# Poe API Provider (with passthrough)
POE_API_KEY=!PASSTHRU

# OpenAI Provider
OPENAI_API_KEY=sk-your-openai-key
OPENAI_BASE_URL=https://some-custom-value-if-needed.openai.com/v1

# Azure OpenAI Provider
AZURE_API_KEY=sk-your-azure-key
AZURE_BASE_URL=https://your-resource.openai.azure.com
AZURE_API_VERSION=2024-02-15-preview

# Custom Provider
CUSTOM_API_KEY=sk-your-key
CUSTOM_BASE_URL=https://api.your-provider.com/anthropic
CUSTOM_API_FORMAT='anthropic' # Assumes 'openai' format by default
```

## Practical Examples

### Example: Cost-Optimized Setup

Use your own OpenAI key for most tasks, but let clients use their own Poe key:

```bash
# Proxy-managed OpenAI API key
OPENAI_API_KEY=sk-your-openai-key

# Client-provided keys for Poe (passthrough)
POE_API_KEY=!PASSTHRU
```

Usage:
```bash
# Uses your OpenAI key
claude --model openai:gpt-4o "Summarize this document"

# Uses client's Poe API key
claude --model poe:glm-4.6 "Translate this to Chinese"
```

## API Format Handling

Vandamme automatically handles different API formats:

### OpenAI Format Providers
Default format for most providers:
```bash
PROVIDER_API_KEY=sk-xxx
PROVIDER_API_FORMAT=openai  # (default, can be omitted)
```

### Anthropic Format Providers
Direct passthrough without conversion:
```bash
SOMEPROVIDER_API_KEY=sk-ant-xxx
SOMEPROVIDER_API_FORMAT=anthropic
```

### Mixed Format Support
Different providers can use different formats simultaneously:
```bash
# OpenAI format (default)
OPENAI_API_KEY=sk-xxx

# Anthropic format
BEDROCK_API_KEY=sk-aws-xxx
BEDROCK_API_FORMAT=anthropic
```

## Advanced Features

### 1. Default Provider

Set a default provider for models without prefixes:
```bash
# Optional: overrides defaults.toml
VDM_DEFAULT_PROVIDER=openai
```

Now `claude --model gpt-4` (without the provider prefix) routes to OpenAI automatically.
If `VDM_DEFAULT_PROVIDER` is not set, it uses the `default-provider` from `src/config/defaults.toml` (defaults to "openai").

### 2. API Key Passthrough

Allow clients to use their own API keys:
```bash
PROVIDER_API_KEY=!PASSTHRU
```

### 3. Custom Headers

Add provider-specific headers:
```bash
OPENAI_CUSTOM_HEADER_ORG_ID=org-your-org
POE_CUSTOM_HEADER_X_MODEL_VERSION=v2
```

### 4. Thought Signature Middleware

Special handling for Google Gemini's thought signatures:
```bash
GEMINI_THOUGHT_SIGNATURES_ENABLED=true # That's the default
```

## Migration from Single-Provider Proxies

If you're coming from a proxy that only supports OpenAI:

### Before (Single Provider)
```bash
# Only one target
OPENAI_API_KEY=sk-xxx
OPENAI_BASE_URL=https://api.openai.com/v1

# Client requests always go to OpenAI
curl -X POST http://proxy:8082/v1/messages \
  -H "x-api-key: sk-xxx" \
  -d '{"model": "gpt-4", "messages": [...]}'
```

### After (Multi-Provider with Vandamme)
```bash
# Multiple providers
OPENAI_API_KEY=sk-xxx
POE_API_KEY=!PASSTHRU
AMAZON_API_KEY=sk-ant-xxx
AMAZON_API_FORMAT=anthropic

# Route to different providers
curl -X POST http://proxy:8082/v1/messages \
  -H "x-api-key: poe-key" \
  -d '{"model": "poe:glm-4.6", "messages": [...]}'

curl -X POST http://proxy:8082/v1/messages \
  -H "x-api-key: amazon-key" \
  -d '{"model": "amazon:claude-3-sonnet", "messages": [...]}'
```

## Best Practices

### 1. Security
- Use `!PASSTHRU` for client-managed keys
- Keep sensitive keys out of version control
- Use environment variables or secret management

### 2. Performance
- Enable provider caching for frequently used providers
- Consider regional providers for latency
- Use connection pooling

### 3. Monitoring
- Check provider health status
- Monitor API key usage per provider
- Track request routing patterns

### 4. Documentation
- Document your provider configurations
- Maintain a mapping of models to providers
- Share provider prefix conventions with your team

## Troubleshooting

### Provider Not Found
```
Error: Provider 'xyz' not configured
```
**Solution**: Ensure `{XYZ}_API_KEY` is set in environment variables.

### API Key Invalid
```
Error: Invalid API key for provider 'openai'
```
**Solution**: Verify the correct API key format for each provider.

### Wrong Provider Selected
```
Request went to wrong provider
```
**Solution**: Check model name format - should be `provider:model`.

## Next Steps

1. **Explore Providers**: List available providers with `vdm providers list`
2. **Test Routing**: Try different provider prefixes
3. **Configure Monitoring**: Set up provider-specific metrics
4. **Document Setup**: Create your provider mapping documentation

## Conclusion

Vandamme Proxy transforms Claude Code from a single-provider tool into a flexible, multi-provider gateway. This enables:

- **Cost Optimization**: Use the right provider for each task
- **Redundancy**: Multiple providers for reliability
- **Flexibility**: Mix and match providers as needed
- **Control**: Fine-grained routing and configuration

Start simple with one or two providers, then expand as needed. The provider prefix system makes it intuitive to route requests exactly where you want them.
