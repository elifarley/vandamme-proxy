#!/usr/bin/env python3
"""Release management utilities for vandamme-proxy."""

import subprocess
import sys
import os
from pathlib import Path


# Colors for terminal output
class Colors:
    BOLD = "\033[1m"
    CYAN = "\033[36m"
    GREEN = "\033[32m"
    YELLOW = "\033[33m"
    RED = "\033[31m"
    RESET = "\033[0m"


def run_cmd(cmd, check=True, capture_output=False):
    """Run command with error handling."""
    try:
        if capture_output:
            return subprocess.run(cmd, shell=True, check=check,
                                 capture_output=True, text=True)
        return subprocess.run(cmd, shell=True, check=check)
    except subprocess.CalledProcessError as e:
        print(f"{Colors.RED}❌ Command failed: {cmd}{Colors.RESET}")
        if not capture_output:
            print(f"Error: {e}")
        sys.exit(1)


def get_current_version():
    """Get current version from Git (only semver tags) or package."""
    try:
        # List only semver-formatted tags, sorted by version
        result = run_cmd("git tag --list '[0-9]*.[0-9]*.[0-9]*' --sort=-version:refname", capture_output=True)
        tags = result.stdout.strip().split('\n')
        # Return first (highest) semver tag if found
        if tags and tags[0]:
            return tags[0]
        # Fall through to package version fallback
    except:
        pass
    # Fallback to package version
    try:
        result = run_cmd("uv run python -c 'from src import __version__; print(__version__)'",
                        capture_output=True)
        return result.stdout.strip()
    except:
        return "1.0.0"


def check_git_clean():
    """Check if working directory has no staged or unstaged changes."""
    result = run_cmd("git status --porcelain -uno", capture_output=True)
    if result.stdout.strip():
        print(f"{Colors.RED}❌ Working directory has uncommitted changes{Colors.RESET}")
        return False
    print(f"{Colors.GREEN}✓ Working directory clean{Colors.RESET}")
    return True


def run_tests():
    """Run quick tests."""
    print(f"{Colors.CYAN}→ Running tests...{Colors.RESET}")
    run_cmd("make test-quick")
    print(f"{Colors.GREEN}✓ Tests pass{Colors.RESET}")


def interactive_bump():
    """Interactive version bump selection."""
    current = get_current_version()
    print(f"\n{Colors.BOLD}{Colors.YELLOW}Current version: {current}{Colors.RESET}")
    print(f"\n{Colors.BOLD}{Colors.YELLOW}Choose version bump:{Colors.RESET}")
    print("  1) patch (1.0.0 → 1.0.1) - Bug fixes")
    print("  2) minor (1.0.0 → 1.1.0) - New features")
    print("  3) major (1.0.0 → 2.0.0) - Breaking changes")

    while True:
        choice = input(f"\n{Colors.CYAN}Select option [1-3]: {Colors.RESET}").strip()
        if choice == "1":
            return "patch"
        elif choice == "2":
            return "minor"
        elif choice == "3":
            return "major"
        else:
            print(f"{Colors.RED}Invalid option. Please select 1, 2, or 3{Colors.RESET}")


def main():
    """Main entry point."""
    if len(sys.argv) < 2:
        print("Usage: python release.py <command> [args]")
        print("Commands:")
        print("  version           - Show current version")
        print("  version-set       - Set new version interactively")
        print("  version-bump      - Bump version (patch/minor/major)")
        print("  tag               - Create and push git tag")
        print("  check             - Validate release readiness")
        print("  publish           - Build and publish to PyPI")
        print("  post-tag          - Post-tag actions")
        print("  full              - Complete interactive release")
        print("  quick <type>      - Quick release (patch/minor/major)")
        sys.exit(1)

    command = sys.argv[1]

    if command == "version":
        version = get_current_version()
        print(f"{Colors.BOLD}{Colors.CYAN}Current version: {Colors.RESET}{version}")

    elif command == "version-set":
        version = input(f"{Colors.CYAN}Enter new version (x.y.z): {Colors.RESET}").strip()
        run_cmd(f'git tag -a {version} -m "Release {version}"')
        run_cmd(f'git push origin {version}')
        print(f"{Colors.GREEN}✓ Tag {version} created and pushed{Colors.RESET}")

    elif command == "version-bump":
        if len(sys.argv) < 3:
            print(f"{Colors.RED}Error: version-bump requires type argument{Colors.RESET}")
            sys.exit(1)
        bump_type = sys.argv[2]
        run_cmd(f'uv run python scripts/version.py bump {bump_type}')

    elif command == "tag":
        version = get_current_version()
        run_cmd(f'git tag -a {version} -m "Release {version}"')
        run_cmd(f'git push origin {version}')
        print(f"{Colors.GREEN}✓ Tag {version} pushed successfully{Colors.RESET}")

    elif command == "push-tag":
        version = get_current_version()
        run_cmd(f'git push origin {version}')
        print(f"{Colors.GREEN}✓ Tag {version} pushed successfully{Colors.RESET}")

    elif command == "check":
        print(f"{Colors.BOLD}{Colors.CYAN}Checking release readiness...{Colors.RESET}")
        if not check_git_clean():
            sys.exit(1)
        run_tests()
        version = get_current_version()
        print(f"{Colors.GREEN}✓ Ready to release {version}{Colors.RESET}")

    elif command == "publish":
        print(f"{Colors.BOLD}{Colors.GREEN}Publishing to PyPI...{Colors.RESET}")
        token = os.getenv("PYPI_API_TOKEN")
        if token:
            run_cmd(f'uv publish --token {token} dist/*')
        else:
            run_cmd('uv publish dist/*')
        print(f"{Colors.BOLD}{Colors.GREEN}✓ Published to PyPI{Colors.RESET}")

    elif command == "post-tag":
        print(f"{Colors.BOLD}{Colors.GREEN}✅ Release initiated!{Colors.RESET}")
        print(f"{Colors.CYAN}→ Tag created, GitHub Actions will publish automatically{Colors.RESET}")
        print(f"{Colors.CYAN}→ Track progress at: https://github.com/elifarley/vandamme-proxy/actions{Colors.RESET}")

    elif command == "full":
        # Full interactive version bump (tests should be run separately)
        if not check_git_clean():
            sys.exit(1)
        # Removed run_tests() - developers run tests before bumping versions
        bump_type = interactive_bump()

        print(f"\n{Colors.CYAN}Bumping version ({bump_type})...{Colors.RESET}")
        run_cmd(f'uv run python scripts/version.py bump {bump_type}')

        print(f"\n{Colors.CYAN}Pushing tag to remote...{Colors.RESET}")
        run_cmd('uv run python scripts/release.py push-tag')

        print(f"\n{Colors.BOLD}{Colors.GREEN}✅ Version bumped and tagged!{Colors.RESET}")
        print(f"{Colors.CYAN}→ Run 'make release-check' to validate before release{Colors.RESET}")
        print(f"{Colors.CYAN}→ Monitor GitHub Actions: https://github.com/elifarley/vandamme-proxy/actions{Colors.RESET}")

    elif command == "quick":
        if len(sys.argv) < 3:
            print(f"{Colors.RED}Error: quick requires type argument (patch/minor/major){Colors.RESET}")
            sys.exit(1)
        bump_type = sys.argv[2]

        run_cmd('uv run python scripts/release.py check')
        run_cmd(f'uv run python scripts/version.py bump {bump_type}')
        run_cmd('uv run python scripts/release.py push-tag')
        run_cmd('uv run python scripts/release.py post-tag')

    else:
        print(f"{Colors.RED}Unknown command: {command}{Colors.RESET}")
        sys.exit(1)


if __name__ == "__main__":
    main()
