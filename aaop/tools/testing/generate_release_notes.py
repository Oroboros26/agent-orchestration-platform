"""
Generate release notes from git history and changed agent versions.

Usage:
    python tools/testing/generate_release_notes.py
    python tools/testing/generate_release_notes.py --output artifacts/release-notes.md
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


def _git_log(base_ref: str) -> list[str]:
    try:
        output = _run_git("log", "--pretty=format:- %s", f"{base_ref}...HEAD")
    except subprocess.CalledProcessError:
        output = _run_git("log", "--pretty=format:- %s", "-5")
    return [line for line in output.splitlines() if line]


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate release notes markdown.")
    parser.add_argument("--base-ref", default="origin/main", help="Git ref to diff against")
    parser.add_argument("--output", help="Optional output path")
    args = parser.parse_args()

    changed_files = _diff_files(args.base_ref)
    changed_versions = sorted(
        {
            f"{parts[2]} {parts[3]}"
            for path in changed_files
            for parts in [Path(path).parts]
            if len(parts) >= 5 and parts[0] == "aaop" and parts[1] == "agents"
        }
    )

    commits = _git_log(args.base_ref)

    lines = [
        "# Release Notes",
        "",
        "## Agent Versions",
    ]

    if changed_versions:
        lines.extend(f"- `{item}`" for item in changed_versions)
    else:
        lines.append("- No agent version changes detected")

    lines.extend(["", "## Commits"])
    if commits:
        lines.extend(commits)
    else:
        lines.append("- No commits detected")

    text = "\n".join(lines) + "\n"
    print(text)

    if args.output:
        output_path = BASE_DIR / args.output
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(text)

    return 0


if __name__ == "__main__":
    sys.exit(main())
