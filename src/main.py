import sys

import uvicorn
from fastapi import FastAPI

from src.api.endpoints import router as api_router
from src.api.metrics import metrics_router
from src.core.config import config

app = FastAPI(title="Vandamme Proxy", version="1.0.0")

app.include_router(api_router)
app.include_router(metrics_router, prefix="/metrics", tags=["metrics"])


def main() -> None:
    if len(sys.argv) > 1 and sys.argv[1] == "--help":
        print("Vandamme Proxy v1.0.0")
        print("")
        print("Usage: python src/main.py")
        print("       or: vdm start")
        print("")
        print("Required environment variables:")
        print("  OPENAI_API_KEY - Your OpenAI API key")
        print("")
        print("Optional environment variables:")
        print("  ANTHROPIC_API_KEY - Expected API key for client validation")
        print("                      If set, clients must provide this exact API key")
        print(f"  HOST - Server host (default: 0.0.0.0)")
        print(f"  PORT - Server port (default: 8082)")
        print(f"  LOG_LEVEL - Logging level (default: WARNING)")
        print(f"  MAX_TOKENS_LIMIT - Token limit (default: 4096)")
        print(f"  MIN_TOKENS_LIMIT - Minimum token limit (default: 100)")
        print(f"  REQUEST_TIMEOUT - Request timeout in seconds (default: 90)")
        print("")
        print("")
        print("For more options, use the vdm CLI:")
        print("  vdm config show  - Show current configuration")
        print("  vdm config setup - Interactive configuration setup")
        print("  vdm health check - Check API connectivity")
        sys.exit(0)

    # Configuration summary
    print("🚀 Vandamme Proxy v1.0.0")
    print(f"✅ Configuration loaded successfully")
    print(f"   API Key : {config.api_key_hash}")
    print(f"   Base URL: {config.base_url}")
    print(f"   Max Tokens Limit: {config.max_tokens_limit}")
    print(f"   Request Timeout : {config.request_timeout}s")
    print(f"   Server: {config.host}:{config.port}")
    print(f"   Client API Key Validation: {'Enabled' if config.anthropic_api_key else 'Disabled'}")
    print("")

    # Show provider summary
    config.provider_manager.print_provider_summary()

    # Parse log level - extract just the first word to handle comments
    log_level = config.log_level.split()[0].lower()

    # Validate and set default if invalid
    valid_levels = ["debug", "info", "warning", "error", "critical"]
    if log_level not in valid_levels:
        log_level = "info"

    access_log = log_level == "debug"

    # Start server
    uvicorn.run(
        "src.main:app",
        host=config.host,
        port=config.port,
        log_level=log_level,
        access_log=access_log,
        reload=False,
    )


if __name__ == "__main__":
    main()
