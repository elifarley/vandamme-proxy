#!/usr/bin/env python3
"""Version management utilities for vandamme-proxy."""

import re
import subprocess
import sys
from pathlib import Path
from typing import Tuple


def get_current_version() -> str:
    """Get current version from Git (only semver tags)."""
    try:
        # List only semver-formatted tags, sorted by version
        result = subprocess.run(
            ["git", "tag", "--list", "[0-9]*.[0-9]*.[0-9]*", "--sort=-version:refname"],
            capture_output=True,
            text=True,
            check=True
        )
        tags = result.stdout.strip().split('\n')
        # Return first (highest) semver tag, or default if none found
        return tags[0] if tags and tags[0] else "1.0.0"
    except subprocess.CalledProcessError:
        return "1.0.0"  # Initial version


def parse_version(version: str) -> Tuple[int, int, int]:
    """Parse version string into tuple."""
    match = re.match(r'^(\d+)\.(\d+)\.(\d+)$', version)
    if not match:
        raise ValueError(f"Invalid version format: {version}")
    return tuple(map(int, match.groups()))


def bump_version(version: str, bump_type: str) -> str:
    """Bump version by specified type."""
    major, minor, patch = parse_version(version)

    if bump_type == "patch":
        patch += 1
    elif bump_type == "minor":
        minor += 1
        patch = 0
    elif bump_type == "major":
        major += 1
        minor = 0
        patch = 0
    else:
        raise ValueError(f"Invalid bump type: {bump_type}")

    return f"{major}.{minor}.{patch}"


def set_version(version: str) -> None:
    """Set new version - creates a tag."""
    # Validate version format
    parse_version(version)

    # Create tag
    subprocess.run(
        ["git", "tag", "-a", version, "-m", f"Release {version}"],
        check=True
    )
    print(f"Created tag: {version}")


def main():
    """Main entry point."""
    if len(sys.argv) < 2:
        print("Usage: python version.py <command> [args]")
        print("Commands:")
        print("  get           - Get current version")
        print("  set X.Y.Z     - Set version (creates tag)")
        print("  bump <type>   - Bump version (patch/minor/major)")
        sys.exit(1)

    command = sys.argv[1]

    if command == "get":
        print(get_current_version())
    elif command == "set":
        if len(sys.argv) != 3:
            print("Error: set requires version argument")
            sys.exit(1)
        set_version(sys.argv[2])
    elif command == "bump":
        if len(sys.argv) != 3:
            print("Error: bump requires type argument (patch/minor/major)")
            sys.exit(1)
        current = get_current_version()
        new = bump_version(current, sys.argv[2])
        print(f"Bumping {current} → {new}")
        set_version(new)
    else:
        print(f"Unknown command: {command}")
        sys.exit(1)


if __name__ == "__main__":
    main()