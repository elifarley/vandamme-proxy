"""Elegant YAML formatting utilities for running totals responses."""

from datetime import datetime
from typing import Any, Dict, List, Optional

import yaml  # type: ignore


def format_running_totals_yaml(
    data: Dict[str, Any], filters: Optional[Dict[str, str]] = None
) -> str:
    """Format running totals data as pretty YAML with comments and metadata.

    Args:
        data: Hierarchical running totals data
        filters: Applied filters for documentation

    Returns:
        Formatted YAML string
    """
    # Create the YAML structure with metadata
    yaml_data = {
        "# Running Totals Report": None,
        f"# Generated: {datetime.now().isoformat()}Z": None,
    }

    # Add filter information if provided
    if filters:
        filter_parts = []
        if filters.get("provider"):
            filter_parts.append(f"provider={filters['provider']}")
        if filters.get("model"):
            filter_parts.append(f"model={filters['model']}")

        if filter_parts:
            yaml_data["# Filter: " + " & ".join(filter_parts)] = None

    # Add empty line for separation
    yaml_data["#"] = None

    # Add the actual data
    yaml_data.update(data)

    # Configure YAML for pretty output
    class PrettyYamlDumper(yaml.SafeDumper):
        """Custom YAML dumper for pretty formatting."""

        def write_line_break(self, data: Any = None) -> None:
            # Ensure blank lines between top-level sections
            super().write_line_break(data)
            if len(self.indents) == 1:
                super().write_line_break()

    # Format with 2-space indentation and pretty flow
    yaml_str = yaml.dump(
        yaml_data,
        Dumper=PrettyYamlDumper,
        default_flow_style=False,
        indent=2,
        sort_keys=False,
        allow_unicode=True,
        width=100,
    )

    # Clean up the output - remove null values for comments
    lines = []
    for line in yaml_str.split("\n"):
        # Skip lines that are just "null:" (from our comment structure)
        if line.strip() == "null:":
            continue
        # Clean up comment lines
        if line.strip().startswith("'#"):
            line = line.replace("'#", "#")
            if line.endswith(": null"):
                line = line[:-6]
        lines.append(line)

    return "\n".join(lines)


def create_hierarchical_structure(
    summary_data: Dict[str, Any], provider_data: Dict[str, Any]
) -> Dict[str, Any]:
    """Create hierarchical YAML structure from summary and provider data.

    Args:
        summary_data: Overall summary statistics
        provider_data: Provider-specific data with models

    Returns:
        Hierarchical dictionary suitable for YAML formatting
    """
    structure = {
        "# Summary Statistics": None,
        "summary": {
            "total_requests": summary_data.get("total_requests", 0),
            "total_errors": summary_data.get("total_errors", 0),
            "total_input_tokens": summary_data.get("total_input_tokens", 0),
            "total_output_tokens": summary_data.get("total_output_tokens", 0),
            "total_cache_read_tokens": summary_data.get("total_cache_read_tokens", 0),
            "total_cache_creation_tokens": summary_data.get("total_cache_creation_tokens", 0),
            "total_tool_uses": summary_data.get("total_tool_uses", 0),
            "total_tool_results": summary_data.get("total_tool_results", 0),
            "total_tool_calls": summary_data.get("total_tool_calls", 0),
            "active_requests": summary_data.get("active_requests", 0),
            "average_duration_ms": summary_data.get("average_duration_ms", 0),
        },
        "#": None,  # Empty line separator
    }

    # Add provider breakdown
    if provider_data:
        structure["# Provider Breakdown"] = None
        providers_dict: Dict[str, Any] = {}

        for provider_name, provider_info in sorted(provider_data.items()):
            # Provider header comment
            providers_dict[f"# {provider_name.title()} Provider"] = None

            # Provider stats
            provider_stats = {
                "total_requests": provider_info.get("total_requests", 0),
                "total_errors": provider_info.get("total_errors", 0),
                "total_input_tokens": provider_info.get("total_input_tokens", 0),
                "total_output_tokens": provider_info.get("total_output_tokens", 0),
                "average_duration_ms": provider_info.get("average_duration_ms", 0),
            }

            # Add cache info if present
            if provider_info.get("total_cache_read_tokens", 0) > 0:
                provider_stats["total_cache_read_tokens"] = provider_info["total_cache_read_tokens"]
            if provider_info.get("total_cache_creation_tokens", 0) > 0:
                provider_stats["total_cache_creation_tokens"] = provider_info[
                    "total_cache_creation_tokens"
                ]

            # Add tool info if present
            if provider_info.get("total_tool_uses", 0) > 0:
                provider_stats["total_tool_uses"] = provider_info["total_tool_uses"]
            if provider_info.get("total_tool_results", 0) > 0:
                provider_stats["total_tool_results"] = provider_info["total_tool_results"]
            if provider_info.get("total_tool_calls", 0) > 0:
                provider_stats["total_tool_calls"] = provider_info["total_tool_calls"]

            structure["providers"][provider_name] = provider_stats

            # Add models if present
            if "models" in provider_info and provider_info["models"]:
                provider_stats_dict: Dict[str, Any] = provider_stats
                provider_stats_dict["# Models"] = None
                models_dict: Dict[str, Any] = {}

                for model_name, model_info in sorted(provider_info["models"].items()):
                    model_stats = {
                        "total_requests": model_info.get("total_requests", 0),
                        "average_duration_ms": model_info.get("average_duration_ms", 0),
                    }

                    # Add errors if present
                    if model_info.get("total_errors", 0) > 0:
                        model_stats["total_errors"] = model_info["total_errors"]

                    models_dict[model_name] = model_stats

                provider_stats_dict["models"] = models_dict

        structure["providers"] = providers_dict

    return structure
