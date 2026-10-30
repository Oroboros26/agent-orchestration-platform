"""
Validate that agent changes include a changelog update.

Usage:
    python tools/testing/validate_changelog.py
    python tools/testing/validate_changelog.py --base-ref origin/main
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent.parent
REPO_DIR = BASE_DIR.parent


def _run_git(*args: str) -> str:
    result = subprocess.run(
        ["git", *args],
        cwd=REPO_DIR,
        check=True,
        capture_output=True,
        text=True,
    )
    return result.stdout.strip()


def _diff_files(base_ref: str) -> list[str]:
    try:
        output = _run_git("diff", "--name-only", f"{base_ref}...HEAD")
    except subprocess.CalledProcessError:
        output = _run_git("diff", "--name-only", "HEAD~1...HEAD")
    return [line for line in output.splitlines() if line]


def _changed_agent_versions(paths: list[str]) -> dict[tuple[str, str], set[str]]:
    changed: dict[tuple[str, str], set[str]] = {}
    for path in paths:
        parts = Path(path).parts
        if len(parts) < 5 or parts[0] != "aaop" or parts[1] != "agents":
            continue
        _, _, agent, version, *_ = parts
        changed.setdefault((agent, version), set()).add(path)
    return changed


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate changelog coverage for changed agents.")
    parser.add_argument("--base-ref", default="origin/main", help="Git ref to diff against")
    args = parser.parse_args()

    changed_files = _diff_files(args.base_ref)
    changed_versions = _changed_agent_versions(changed_files)

    if not changed_versions:
        print("No changed agent versions detected.")
        return 0

    failures: list[str] = []
    for (agent, version), files in sorted(changed_versions.items()):
        changelog_rel = f"aaop/agents/{agent}/{version}/CHANGELOG.md"
        changelog_path = REPO_DIR / changelog_rel

        if changelog_rel not in files:
            failures.append(f"{agent} {version}: missing CHANGELOG.md update in this change set")
            continue

        if not changelog_path.exists():
            failures.append(f"{agent} {version}: CHANGELOG.md does not exist")
            continue

        text = changelog_path.read_text().strip()
        if version not in text:
            failures.append(f"{agent} {version}: CHANGELOG.md does not mention version '{version}'")

    if failures:
        print("Changelog validation failed:\n")
        for failure in failures:
            print(f"- {failure}")
        return 1

    print("Changelog validation passed for all changed agents.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
