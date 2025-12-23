# Top-Models Feature Implementation Specification

## Overview

This document describes the implementation of a "top-models" feature that displays a curated list of the best AI models for programming tasks. The feature automatically fetches models from OpenRouter's API, applies intelligent filtering, and presents them in a user-friendly format.

## Architecture

### Core Components

1. **Model Fetcher** (`model_fetcher.py`)
   - Fetches models from OpenRouter API
   - Handles HTTP requests and error management
   - Implements retry logic with exponential backoff

2. **Model Filter** (`model_filter.py`)
   - Applies filtering rules to curate the best models
   - Enforces one-model-per-provider rule
   - Excludes unwanted providers (e.g., Anthropic)

3. **Cache Manager** (`cache_manager.py`)
   - Manages local cache of model data
   - Implements cache expiry logic (default: 2 days)
   - Handles cache updates and validation

4. **Model Displayer** (`model_displayer.py`)
   - Formats and displays models in table format
   - Supports JSON output for programmatic access
   - Colorizes output for better readability

5. **CLI Handler** (`cli.py`)
   - Parses command-line arguments
   - Orchestrates the entire workflow
   - Handles flags like --json, --force-update

## Data Structures

### Model Data Structure

```python
@dataclass
class ModelInfo:
    id: str                    # e.g., "google/gemini-3-pro-preview"
    name: str                  # e.g., "Google Gemini 3 Pro Preview"
    provider: str              # e.g., "Google"
    pricing: PricingInfo
    context_window: int
    capabilities: List[str]    # ["tools", "reasoning", "vision"]
    category: str             # "programming", "vision", "reasoning"

@dataclass
class PricingInfo:
    input_per_million: float
    output_per_million: float
    average_per_million: float
```

### Cache Structure

```json
{
    "last_updated": "2025-12-20T10:30:00Z",
    "models": [
        {
            "id": "google/gemini-3-pro-preview",
            "name": "Google Gemini 3 Pro Preview",
            "provider": "Google",
            "pricing": {
                "input_per_million": 0.125,
                "output_per_million": 0.375,
                "average_per_million": 0.25
            },
            "context_window": 2000000,
            "capabilities": ["tools", "reasoning", "vision"],
            "category": "programming"
        }
    ]
}
```

## Implementation Details

### 1. Model Fetcher Implementation

```python
import requests
import time
from typing import List, Dict, Any
from dataclasses import dataclass
import logging

logger = logging.getLogger(__name__)

class ModelFetcher:
    def __init__(self, api_url: str = "https://openrouter.ai/api/v1/models"):
        self.api_url = api_url
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": "vandamme-proxy/1.0"
        })

    def fetch_models(self, max_retries: int = 3, backoff_factor: float = 1.0) -> List[Dict[str, Any]]:
        """
        Fetch models from OpenRouter API with retry logic.

        Args:
            max_retries: Maximum number of retry attempts
            backoff_factor: Backoff multiplier for exponential delay

        Returns:
            List of model dictionaries from the API

        Raises:
            ModelFetchError: If all retries fail
        """
        last_error = None

        for attempt in range(max_retries):
            try:
                response = self.session.get(self.api_url, timeout=30)
                response.raise_for_status()

                data = response.json()
                if "data" not in data:
                    raise ModelFetchError("Invalid API response format")

                logger.info(f"Successfully fetched {len(data['data'])} models")
                return data["data"]

            except (requests.RequestException, ValueError) as e:
                last_error = e
                wait_time = backoff_factor * (2 ** attempt)
                logger.warning(f"Attempt {attempt + 1} failed: {e}. Retrying in {wait_time}s...")
                time.sleep(wait_time)

        raise ModelFetchError(f"Failed to fetch models after {max_retries} attempts: {last_error}")
```

### 2. Model Filter Implementation

```python
from typing import List, Dict, Set
import re

class ModelFilter:
    def __init__(self):
        # Priority list of top programming models (manually curated)
        self.top_programming_models = [
            "google/gemini-3-pro-preview",      # Priority 1
            "openai/gpt-5.1-codex",           # Priority 2
            "x-ai/grok-code-fast-1",          # Priority 3
            "anthropic/claude-sonnet-4.5",    # Skipped (Anthropic)
            "google/gemini-2.5-flash",        # Priority 4
            "meta-llama/llama-3.3-70b-instruct",
            "microsoft/phi-4-multimodal",
            "deepseek/deepseek-coder-v2",
            "cohere/command-r-plus-08-2024",
            "mistralai/mistral-large",
            "perplexity/llama-3.1-sonar-large-128k-online",
            "minimax/minimax-m2",
            "z-ai/glm-4.6",
            "qwen/qwen3-vl-235b-a22b-instruct",
        ]

        # Providers to exclude
        self.excluded_providers = {"anthropic"}

        # Track selected providers to ensure one per provider
        self.selected_providers: Set[str] = set()

    def filter_models(self, models: List[Dict[str, Any]]) -> List[ModelInfo]:
        """
        Apply filtering rules to create curated list.

        Args:
            models: Raw models from API

        Returns:
            Filtered list of ModelInfo objects
        """
        filtered_models = []

        # First, try to get models from our priority list
        for model_id in self.top_programming_models:
            model_data = self._find_model_by_id(models, model_id)
            if model_data and self._should_include_model(model_data):
                model_info = self._convert_to_model_info(model_data)
                if model_info:
                    filtered_models.append(model_info)
                    self.selected_providers.add(model_info.provider.lower())

        # If we don't have enough models, add more from the API
        if len(filtered_models) < 10:
            additional_models = self._get_additional_models(models, filtered_models)
            filtered_models.extend(additional_models)

        return filtered_models

    def _find_model_by_id(self, models: List[Dict[str, Any]], model_id: str) -> Dict[str, Any]:
        """Find a model in the list by its ID."""
        for model in models:
            if model.get("id") == model_id:
                return model
        return None

    def _should_include_model(self, model: Dict[str, Any]) -> bool:
        """Check if a model should be included based on filtering rules."""
        model_id = model.get("id", "")

        # Skip Anthropic models
        if model_id.startswith("anthropic/"):
            return False

        # Check provider exclusions
        provider = self._extract_provider(model_id)
        if provider.lower() in self.excluded_providers:
            return False

        # Ensure one model per provider (unless it's high priority)
        if provider.lower() in self.selected_providers:
            # Allow if it's in our top 3 priority models
            priority_index = self._get_priority_index(model_id)
            if priority_index > 2:  # Not in top 3
                return False

        # Check if it's a programming-capable model
        capabilities = model.get("capabilities", [])
        if not self._is_programming_model(capabilities):
            return False

        return True

    def _extract_provider(self, model_id: str) -> str:
        """Extract provider name from model ID."""
        parts = model_id.split("/")
        if len(parts) >= 2:
            return parts[0].replace("-", " ").title()
        return "Unknown"

    def _is_programming_model(self, capabilities: List[str]) -> bool:
        """Check if model is suitable for programming tasks."""
        # Look for programming-related keywords
        programming_keywords = ["coding", "programming", "code", "developer"]
        model_description = " ".join(capabilities).lower()

        # Check if description contains programming keywords
        for keyword in programming_keywords:
            if keyword in model_description:
                return True

        # Default to including models with tools capability
        return "tools" in capabilities

    def _get_priority_index(self, model_id: str) -> int:
        """Get priority index of model (lower = higher priority)."""
        try:
            return self.top_programming_models.index(model_id)
        except ValueError:
            return float('inf')
```

### 3. Cache Manager Implementation

```python
import json
import os
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional, List

class CacheManager:
    def __init__(self, cache_dir: str = "~/.cache/vandamme-proxy"):
        self.cache_dir = Path(cache_dir).expanduser()
        self.cache_file = self.cache_dir / "recommended-models.json"
        self.cache_max_age_days = 2

        # Ensure cache directory exists
        self.cache_dir.mkdir(parents=True, exist_ok=True)

    def get_cached_models(self) -> Optional[List[ModelInfo]]:
        """
        Get cached models if they exist and are not stale.

        Returns:
            List of ModelInfo objects if cache is valid, None otherwise
        """
        if not self.cache_file.exists():
            return None

        try:
            with open(self.cache_file, 'r') as f:
                cache_data = json.load(f)

            # Check if cache is stale
            last_updated = datetime.fromisoformat(cache_data.get("last_updated", ""))
            if datetime.now() - last_updated > timedelta(days=self.cache_max_age_days):
                logger.info("Cache is stale")
                return None

            # Convert to ModelInfo objects
            models = []
            for model_data in cache_data.get("models", []):
                model_info = self._dict_to_model_info(model_data)
                if model_info:
                    models.append(model_info)

            logger.info(f"Loaded {len(models)} models from cache")
            return models

        except (json.JSONDecodeError, KeyError, ValueError) as e:
            logger.error(f"Error reading cache: {e}")
            return None

    def update_cache(self, models: List[ModelInfo]) -> None:
        """
        Update cache with new model data.

        Args:
            models: List of ModelInfo objects to cache
        """
        cache_data = {
            "last_updated": datetime.now().isoformat(),
            "models": [self._model_info_to_dict(model) for model in models]
        }

        try:
            # Write to temporary file first, then rename for atomicity
            temp_file = self.cache_file.with_suffix(".tmp")
            with open(temp_file, 'w') as f:
                json.dump(cache_data, f, indent=2)

            temp_file.rename(self.cache_file)
            logger.info(f"Updated cache with {len(models)} models")

        except Exception as e:
            logger.error(f"Error updating cache: {e}")
            raise CacheError(f"Failed to update cache: {e}")

    def is_cache_stale(self) -> bool:
        """Check if cache is stale or doesn't exist."""
        if not self.cache_file.exists():
            return True

        try:
            with open(self.cache_file, 'r') as f:
                cache_data = json.load(f)

            last_updated = datetime.fromisoformat(cache_data.get("last_updated", ""))
            return datetime.now() - last_updated > timedelta(days=self.cache_max_age_days)

        except Exception:
            return True

    def _model_info_to_dict(self, model: ModelInfo) -> Dict[str, Any]:
        """Convert ModelInfo to dictionary."""
        return {
            "id": model.id,
            "name": model.name,
            "provider": model.provider,
            "pricing": {
                "input_per_million": model.pricing.input_per_million,
                "output_per_million": model.pricing.output_per_million,
                "average_per_million": model.pricing.average_per_million
            },
            "context_window": model.context_window,
            "capabilities": model.capabilities,
            "category": model.category
        }

    def _dict_to_model_info(self, data: Dict[str, Any]) -> Optional[ModelInfo]:
        """Convert dictionary to ModelInfo."""
        try:
            pricing_data = data.get("pricing", {})
            pricing = PricingInfo(
                input_per_million=pricing_data.get("input_per_million", 0),
                output_per_million=pricing_data.get("output_per_million", 0),
                average_per_million=pricing_data.get("average_per_million", 0)
            )

            return ModelInfo(
                id=data["id"],
                name=data["name"],
                provider=data["provider"],
                pricing=pricing,
                context_window=data.get("context_window", 0),
                capabilities=data.get("capabilities", []),
                category=data.get("category", "unknown")
            )
        except (KeyError, TypeError) as e:
            logger.warning(f"Error converting model data: {e}")
            return None
```

### 4. Model Displayer Implementation

```python
import json
from typing import List
from tabulate import tabulate
import colorama
from colorama import Fore, Style

# Initialize colorama
colorama.init()

class ModelDisplayer:
    def __init__(self):
        self.color_map = {
            "tools": Fore.GREEN,
            "reasoning": Fore.BLUE,
            "vision": Fore.MAGENTA,
        }

    def display_table(self, models: List[ModelInfo]) -> None:
        """
        Display models in a formatted table.

        Args:
            models: List of ModelInfo objects to display
        """
        if not models:
            print(f"{Fore.YELLOW}No models available{Style.RESET_ALL}")
            return

        # Prepare table data
        headers = ["Model", "Provider", "Input/M", "Output/M", "Avg/M", "Context", "Capabilities"]
        rows = []

        for model in models:
            capabilities_str = self._format_capabilities(model.capabilities)
            row = [
                model.name,
                model.provider,
                f"${model.pricing.input_per_million:.3f}",
                f"${model.pricing.output_per_million:.3f}",
                f"${model.pricing.average_per_million:.3f}",
                self._format_context_size(model.context_window),
                capabilities_str
            ]
            rows.append(row)

        # Print table
        print(f"\n{Fore.CYAN}Top Models for Programming{Style.RESET_ALL}")
        print("=" * 80)
        print(tabulate(rows, headers=headers, tablefmt="grid"))
        print(f"\n{Fore.DIM}Showing {len(models)} models{Style.RESET_ALL}")

    def display_json(self, models: List[ModelInfo]) -> None:
        """
        Display models in JSON format.

        Args:
            models: List of ModelInfo objects to display
        """
        models_data = []
        for model in models:
            model_dict = {
                "id": model.id,
                "name": model.name,
                "provider": model.provider,
                "pricing": {
                    "input_per_million": model.pricing.input_per_million,
                    "output_per_million": model.pricing.output_per_million,
                    "average_per_million": model.pricing.average_per_million
                },
                "context_window": model.context_window,
                "capabilities": model.capabilities,
                "category": model.category
            }
            models_data.append(model_dict)

        json_output = {
            "last_updated": datetime.now().isoformat(),
            "models": models_data
        }

        print(json.dumps(json_output, indent=2))

    def _format_capabilities(self, capabilities: List[str]) -> str:
        """Format capabilities with colors."""
        if not capabilities:
            return ""

        colored_caps = []
        for cap in capabilities:
            color = self.color_map.get(cap, "")
            if color:
                colored_caps.append(f"{color}{cap}{Style.RESET_ALL}")
            else:
                colored_caps.append(cap)

        return ", ".join(colored_caps)

    def _format_context_size(self, context_window: int) -> str:
        """Format context window size with appropriate unit."""
        if context_window >= 1000000:
            return f"{context_window // 1000000}M"
        elif context_window >= 1000:
            return f"{context_window // 1000}K"
        else:
            return str(context_window)
```

### 5. CLI Handler Implementation

```python
import argparse
import sys
import logging
from typing import Optional

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

class CLIHandler:
    def __init__(self):
        self.fetcher = ModelFetcher()
        self.filter = ModelFilter()
        self.cache_manager = CacheManager()
        self.displayer = ModelDisplayer()

    def handle_top_models_command(self, args: argparse.Namespace) -> None:
        """
        Handle the --top-models command.

        Args:
            args: Parsed command line arguments
        """
        try:
            models = self._get_models(
                force_update=args.force_update,
                use_cache=not args.force_update
            )

            if args.json:
                self.displayer.display_json(models)
            else:
                self.displayer.display_table(models)

        except Exception as e:
            logger.error(f"Error fetching top models: {e}")
            sys.exit(1)

    def _get_models(self, force_update: bool = False, use_cache: bool = True) -> List[ModelInfo]:
        """
        Get models, using cache if available and not force updating.

        Args:
            force_update: Force refresh from API
            use_cache: Whether to use cached data

        Returns:
            List of ModelInfo objects
        """
        # Try to get from cache first (unless force update)
        if use_cache and not force_update:
            cached_models = self.cache_manager.get_cached_models()
            if cached_models:
                return cached_models

        # Fetch from API
        logger.info("Fetching models from OpenRouter API...")
        raw_models = self.fetcher.fetch_models()

        # Filter models
        logger.info("Filtering models...")
        filtered_models = self.filter.filter_models(raw_models)

        # Update cache
        self.cache_manager.update_cache(filtered_models)

        return filtered_models

def setup_argument_parser() -> argparse.ArgumentParser:
    """Set up command line argument parser."""
    parser = argparse.ArgumentParser(
        description="Vandamme Proxy - AI Model Proxy Service",
        formatter_class=argparse.RawDescriptionHelpFormatter
    )

    # Top models command
    parser.add_argument(
        "--top-models",
        action="store_true",
        help="Show top recommended models for programming"
    )

    parser.add_argument(
        "--json",
        action="store_true",
        help="Output in JSON format (use with --top-models)"
    )

    parser.add_argument(
        "--force-update",
        action="store_true",
        help="Force update model cache (use with --top-models)"
    )

    return parser

def main():
    """Main entry point."""
    parser = setup_argument_parser()
    args = parser.parse_args()

    if args.top_models:
        cli_handler = CLIHandler()
        cli_handler.handle_top_models_command(args)
    else:
        parser.print_help()

if __name__ == "__main__":
    main()
```

## Dependencies

Add these dependencies to your `requirements.txt`:

```
requests>=2.31.0
tabulate>=0.9.0
colorama>=0.4.6
```

## Installation and Usage

### 1. Install Dependencies

```bash
pip install -r requirements.txt
```

### 2. Command Line Usage

```bash
# Show top models in table format
python cli.py --top-models

# Show top models in JSON format
python cli.py --top-models --json

# Force update cache
python cli.py --top-models --force-update

# JSON output with force update
python cli.py --top-models --json --force-update
```

### 3. Programmatic Usage

```python
from cli import CLIHandler

# Create handler
handler = CLIHandler()

# Get top models
models = handler._get_models(force_update=True)

# Display in table format
handler.displayer.display_table(models)

# Or get JSON
import json
models_data = [handler.cache_manager._model_info_to_dict(m) for m in models]
print(json.dumps(models_data, indent=2))
```

## Configuration

### Environment Variables

- `OPENROUTER_API_URL`: Custom OpenRouter API URL (default: https://openrouter.ai/api/v1/models)
- `CACHE_MAX_AGE_DAYS`: Cache expiry in days (default: 2)
- `CACHE_DIR`: Custom cache directory (default: ~/.cache/vandamme-proxy)

### Customization

To customize the filtering rules or model priorities:

1. Modify the `top_programming_models` list in `ModelFilter`
2. Adjust `excluded_providers` set for provider exclusions
3. Update `is_programming_model` method for different filtering criteria

## Error Handling

The implementation includes comprehensive error handling:

1. **Network Errors**: Automatic retry with exponential backoff
2. **Cache Errors**: Fallback to API fetch if cache is corrupted
3. **API Errors**: Graceful degradation with informative error messages
4. **Validation Errors**: Skip malformed model entries with warnings

## Testing

### Unit Tests Structure

```python
# tests/test_model_fetcher.py
def test_fetch_models_success()
def test_fetch_models_retry()
def test_fetch_models_failure()

# tests/test_model_filter.py
def test_filter_models_priority()
def test_one_model_per_provider()
def test_excluded_providers()

# tests/test_cache_manager.py
def test_cache_write_read()
def test_cache_expiry()
def test_cache_stale_check()

# tests/test_model_displayer.py
def test_display_table_format()
def test_display_json_format()
```

### Integration Test

```python
# tests/test_integration.py
def test_full_workflow():
    """Test the complete top-models workflow."""
    handler = CLIHandler()
    models = handler._get_models(force_update=True)
    assert len(models) > 0
    assert all(isinstance(m, ModelInfo) for m in models)
```

## Performance Considerations

1. **Caching**: Models are cached locally to avoid repeated API calls
2. **Lazy Loading**: Models are only fetched when explicitly requested
3. **Async Option**: For high-performance scenarios, consider using `aiohttp` for async requests
4. **Memory**: The model list is small (<50 models), so memory usage is minimal

## Security Considerations

1. **No Authentication**: OpenRouter's models endpoint doesn't require API keys
2. **Cache Validation**: Cache files are validated before use
3. **Timeout Handling**: API requests have configurable timeouts
4. **User-Agent**: Requests include proper User-Agent identification

## Future Enhancements

1. **Custom Filtering**: Allow users to specify filtering criteria
2. **Model Categories**: Support multiple categories (e.g., vision, reasoning)
3. **Performance Metrics**: Track model performance statistics
4. **Model Comparison**: Side-by-side model comparison feature
5. **Subscription Updates**: Push notifications for new top models

## Maintenance

The curated model list should be reviewed periodically (monthly) to ensure it remains relevant. Update the `top_programming_models` list in `ModelFilter` based on:

1. OpenRouter's weekly rankings
2. User feedback and usage patterns
3. New model releases
4. Provider reliability and performance

This implementation provides a robust, self-sufficient solution for displaying top AI models optimized for programming tasks, with automatic updates, intelligent filtering, and flexible output formats.