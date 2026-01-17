# OAuth Authentication Guide

This guide explains how to use OAuth 2.0 authentication with Vandamme Proxy,
enabling you to use your ChatGPT Plus/Pro subscription instead of purchasing API keys.

## Overview

OAuth authentication allows Vandamme Proxy to authenticate with providers like
ChatGPT using your existing subscription, eliminating the need for separate API keys
and billing.

**Benefits:**
- Use your existing ChatGPT Plus/Pro subscription
- No separate API key billing required
- Automatic token refresh
- Secure token storage with proper file permissions

**Trade-offs:**
- Rate limits tied to your subscription tier
- Requires one-time browser authentication
- Not suitable for production server deployments

## Quick Start

### Step 1: Configure OAuth Provider

Set the `AUTH_MODE` environment variable for your provider:

```bash
export CHATGPT_AUTH_MODE=oauth
export CHATGPT_BASE_URL=https://api.openai.com/v1
export VDM_DEFAULT_PROVIDER=chatgpt
```

Alternatively, use the `!OAUTH` sentinel value:

```bash
export CHATGPT_API_KEY=!OAUTH
export CHATGPT_BASE_URL=https://api.openai.com/v1
```

Or configure via TOML in `~/.config/vandamme-proxy/vandamme-config.toml`:

```toml
[chatgpt]
auth-mode = "oauth"
base-url = "https://api.openai.com/v1"
```

### Step 2: Authenticate

Run the OAuth login command:

```bash
vdm oauth login chatgpt
```

This will:
1. Open a browser window for you to complete the OAuth flow
2. Wait for you to authenticate with ChatGPT
3. Store the obtained tokens securely
4. Display your account information

**Example output:**
```
[cyan]Starting OAuth flow for provider: chatgpt[/cyan]
[yellow]A browser window will open for authentication...[/yellow]

┏━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┓
┃         OAuth Login Success              ┃
├──────────────────────────────────────────┨
┃ [green]✅ Successfully authenticated![/green]  ┃
┃                                          ┃
┃ Provider: chatgpt                        ┃
┃ Account ID: user_abc123xyz               ┃
┃ Token expires at: 2026-01-17T12:34:56Z   ┃
┗━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┛
```

### Step 3: Verify Status

Check your authentication status:

```bash
vdm oauth status chatgpt
```

**Example output:**
```
┏━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━ ┓
┃             OAuth Status: chatgpt                 ┃
├─────────────────────────────────────────────────────┨
┃ Field              Value                            ┃
├─────────────────────────────────────────────────────┨
┃ Provider           chatgpt                          ┃
┃ Status             [green]✅ Authenticated[/green]  ┃
┃ Account ID         user_abc123xyz                   ┃
┃ Expires At         2026-01-17T12:34:56Z             ┃
┃ Last Refresh       2026-01-16T10:15:30Z             ┃
┃ Storage Path       /home/user/.vandamme/oauth/chatgpt/ ┃
┗━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━ ┛
```

### Step 4: Start the Proxy

```bash
vdm server start
```

### Step 5: Use with Claude Code

```bash
ANTHROPIC_BASE_URL=http://localhost:8082 claude "Hello, world!"
```

## Configuration Methods

OAuth authentication can be configured in three ways (priority order):

### 1. Environment Variable (Highest Priority)

```bash
export CHATGPT_AUTH_MODE=oauth
```

### 2. Sentinel Value

```bash
export CHATGPT_API_KEY=!OAUTH
```

### 3. TOML Configuration (Lowest Priority)

```toml
# ~/.config/vandamme-proxy/vandamme-config.toml
[chatgpt]
auth-mode = "oauth"
```

## Token Storage

OAuth tokens are stored securely on your filesystem:

**Location:** `~/.vandamme/oauth/{provider}/auth.json`

**Example:**
```
~/.vandamme/oauth/chatgpt/
└── auth.json  (mode: 0600)
```

**File permissions:** `0600` (read/write for owner only)

**Storage format:**
```json
{
  "access_token": "eyJhbGciOiJSUzI1NiIsInR5cCI6IkpXVCJ9...",
  "refresh_token": "eyJhbGciOiJSUzI1NiIsInR5cCI6IkpXVCJ9...",
  "id_token": "eyJhbGciOiJSUzI1NiIsInR5cCI6IkpXVCJ9...",
  "account_id": "user_abc123xyz",
  "expires_at": "2026-01-17T12:34:56Z",
  "last_refresh": "2026-01-16T10:15:30Z"
}
```

## Token Management

### Automatic Refresh

Tokens are automatically refreshed when:
- The access token expires (~1 hour lifetime)
- The proxy makes a request with an expired token

Refresh failures are handled gracefully with warning logs.

### Manual Token Management

**Check token status:**
```bash
vdm oauth status chatgpt
```

**Remove stored tokens (logout):**
```bash
vdm oauth logout chatgpt
```

**Re-authenticate:**
```bash
vdm oauth logout chatgpt
vdm oauth login chatgpt
```

## Security Considerations

### Token Security

- **Storage:** Tokens stored in `~/.vandamme/oauth/{provider}/auth.json`
- **Permissions:** Files set to `0600` (owner read/write only)
- **HTTPS:** All OAuth traffic over HTTPS
- **PKCE:** Uses PKCE (Proof Key for Code Exchange) to prevent token interception

### Best Practices

1. **Check file permissions:**
   ```bash
   stat ~/.vandamme/oauth/chatgpt/auth.json
   # Should show: Access: 0600
   ```

2. **Logout when done:**
   ```bash
   vdm oauth logout chatgpt
   ```

3. **Don't share auth files:**
   The `auth.json` file contains your authentication tokens. Never share it.

4. **Use in development only:**
   OAuth is designed for personal/development use. For production, use API keys.

## Troubleshooting

### Authentication Fails

**Problem:** Browser doesn't open or authentication fails

**Solution:**
```bash
# 1. Check if browser is available
echo $BROWSER  # Should show your browser

# 2. Try manual authentication flow
# The login command will print a URL you can visit manually
vdm oauth login chatgpt
```

### Token Expired

**Problem:** Requests fail with "Not authenticated"

**Solution:**
```bash
# Check status
vdm oauth status chatgpt

# Re-authenticate if needed
vdm oauth logout chatgpt
vdm oauth login chatgpt
```

### Provider Not Found

**Problem:** Error about provider not being configured

**Solution:**
```bash
# Verify AUTH_MODE is set
echo $CHATGPT_AUTH_MODE  # Should be "oauth"

# Check provider is in defaults.toml
cat src/config/defaults.toml | grep chatgpt

# Verify base URL is set
echo $CHATGPT_BASE_URL  # Should be https://api.openai.com/v1
```

### File Permission Errors

**Problem:** Permission denied accessing auth.json

**Solution:**
```bash
# Fix file permissions
chmod 0600 ~/.vandamme/oauth/chatgpt/auth.json

# Fix directory permissions
chmod 0700 ~/.vandamme/oauth/chatgpt/
```

### Multiple Providers

**Problem:** Tokens from different providers getting mixed up

**Solution:**
Each provider has isolated storage. Verify correct paths:
```bash
# List all OAuth providers
ls -la ~/.vandamme/oauth/

# Should show separate directories per provider:
# chatgpt/
# another-provider/
```

## Architecture

```
┌─────────────────────────────────────────────────────────────────────┐
│                         VANDAMME PROXY                              │
├─────────────────────────────────────────────────────────────────────┤
│                                                                     │
│  CLI Commands                                                       │
│  ┌──────────┐                                                        │
│  │ vdm oauth │──► login/status/logout                               │
│  └──────────┘                                                        │
│       │                                                             │
│       ▼                                                             │
│  ┌──────────────────────────────────────────────────────────────┐  │
│  │                    Token Storage                               │  │
│  │  ~/.vandamme/oauth/{provider}/auth.json                      │  │
│  └──────────────────────────────────────────────────────────────┘  │
│       │                                                             │
│       ▼                                                             │
│  ┌──────────────────────────────────────────────────────────────┐  │
│  │                    TokenManager                                │  │
│  │  - get_access_token()                                         │  │
│  │  - Automatic refresh on expiry                                │  │
│  └──────────────────────────────────────────────────────────────┘  │
│       │                                                             │
│       ▼                                                             │
│  ┌──────────────────────────────────────────────────────────────┐  │
│  │              OAuthClientMixin                                  │  │
│  │  - _get_oauth_token()                                         │  │
│  │  - _inject_oauth_headers()                                    │  │
│  └──────────────────────────────────────────────────────────────┘  │
│       │                                                             │
│       ▼                                                             │
│  ┌──────────────────────────────────────────────────────────────┐  │
│  │         OpenAIClient / AnthropicClient                        │  │
│  │  Requests include: Authorization: Bearer <token>             │  │
│  └──────────────────────────────────────────────────────────────┘  │
│                                                                     │
└─────────────────────────────────────────────────────────────────────┘
```

## OAuth vs API Key Authentication

| Feature | OAuth | API Key |
|---------|-------|---------|
| **Billing** | ChatGPT subscription | Per-usage API billing |
| **Setup** | Browser auth flow (one-time) | Copy/paste key |
| **Token refresh** | Automatic | N/A (keys don't expire) |
| **Rate limits** | Subscription tier | API tier |
| **Use case** | Personal/development | Production |
| **Cost** | Included in subscription | Pay-per-usage |
| **Security** | OAuth 2.0 + PKCE | API key in env |
| **Multi-key** | Not supported | Yes (round-robin) |

## Advanced Topics

### Custom Provider Configuration

To add OAuth for a custom provider:

1. Add to `~/.config/vandamme-proxy/vandamme-config.toml`:
   ```toml
   [my-provider]
   auth-mode = "oauth"
   base-url = "https://api.example.com/v1"
   api-format = "openai"
   ```

2. Authenticate:
   ```bash
   vdm oauth login my-provider
   ```

### Programmatic Usage

The `TokenManager` can be used programmatically:

```python
from src.core.oauth import TokenManager, FileSystemAuthStorage
from pathlib import Path

# Create storage
storage_path = Path.home() / ".vandamme" / "oauth" / "chatgpt"
storage = FileSystemAuthStorage(base_path=storage_path)

# Create token manager
token_mgr = TokenManager(storage=storage, raise_on_refresh_failure=False)

# Get access token
access_token, account_id = token_mgr.get_access_token()
```

### Debug Mode

Enable debug logging to see OAuth operations:

```bash
LOG_LEVEL=DEBUG vdm server start
```

Debug logs show:
- Token retrieval
- Refresh attempts
- Header injection
- Authentication failures

## Reference

### CLI Commands

**`vdm oauth login <provider>`**
- Opens browser for OAuth authentication
- Stores tokens in `~/.vandamme/oauth/{provider}/`
- Requires: Provider configured with `AUTH_MODE=oauth`

**`vdm oauth status <provider>`**
- Shows current authentication status
- Displays token expiry and account ID
- Returns exit code 1 if not authenticated

**`vdm oauth logout <provider>`**
- Removes stored tokens
- Deletes `~/.vandamme/oauth/{provider}/auth.json`

### Environment Variables

- `{PROVIDER}_AUTH_MODE` - Set to "oauth" for OAuth authentication
- `{PROVIDER}_API_KEY` - Set to "!OAUTH" as alternative to AUTH_MODE
- `{PROVIDER}_BASE_URL` - Base URL for the provider

### Files

- `~/.vandamme/oauth/{provider}/auth.json` - Stored tokens
- `~/.config/vandamme-proxy/vandamme-config.toml` - Provider configuration
- `src/config/defaults.toml` - Built-in provider defaults

## Support

For issues or questions:
1. Check token status: `vdm oauth status <provider>`
2. Check logs: `LOG_LEVEL=DEBUG vdm server start`
3. Verify configuration: `vdm config validate`
4. Re-authenticate: `vdm oauth logout <provider>` && `vdm oauth login <provider>`
