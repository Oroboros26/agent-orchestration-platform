"""
Compare agent and registry changes against a base ref.

Usage:
    python tools/testing/compare_catalog.py
    python tools/testing/compare_catalog.py --output artifacts/catalog-diff.md
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

import yaml

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


def _load_registry_from_git(ref: str) -> dict:
    try:
        text = _run_git("show", f"{ref}:aaop/configs/registry.yaml")
    except subprocess.CalledProcessError:
        return {}
    return yaml.safe_load(text) or {}


def build_report(base_ref: str) -> str:
    changed_files = _diff_files(base_ref)
    changed_agent_files = [path for path in changed_files if path.startswith("aaop/agents/")]
    changed_agents = sorted({Path(path).parts[2] for path in changed_agent_files if len(Path(path).parts) > 2})

    base_registry = _load_registry_from_git(base_ref).get("agents", {})
    head_registry_path = BASE_DIR / "configs/registry.yaml"
    head_registry = yaml.safe_load(head_registry_path.read_text()).get("agents", {}) if head_registry_path.exists() else {}

    added_agents = sorted(set(head_registry) - set(base_registry))
    removed_agents = sorted(set(base_registry) - set(head_registry))

    version_changes: list[str] = []
    for agent in sorted(set(base_registry) & set(head_registry)):
        base_cfg = base_registry.get(agent, {})
        head_cfg = head_registry.get(agent, {})
        env_changes = []
        for env in ("dev", "uat", "prod"):
            if base_cfg.get(env) != head_cfg.get(env):
                env_changes.append(f"{env}: `{base_cfg.get(env)}` -> `{head_cfg.get(env)}`")
        if env_changes:
            version_changes.append(f"- `{agent}`: " + ", ".join(env_changes))

    lines = [
        "# Catalog Comparison",
        "",
        f"Base ref: `{base_ref}`",
        "",
        "## Changed Agent Files",
    ]

    if changed_agent_files:
        lines.extend(f"- `{path}`" for path in changed_agent_files)
    else:
        lines.append("- None")

    lines.extend(["", "## Changed Agents"])
    if changed_agents:
        lines.extend(f"- `{agent}`" for agent in changed_agents)
    else:
        lines.append("- None")

    lines.extend(["", "## Registry Additions"])
    if added_agents:
        lines.extend(f"- `{agent}`" for agent in added_agents)
    else:
        lines.append("- None")

    lines.extend(["", "## Registry Removals"])
    if removed_agents:
        lines.extend(f"- `{agent}`" for agent in removed_agents)
    else:
        lines.append("- None")

    lines.extend(["", "## Registry Version Changes"])
    if version_changes:
        lines.extend(version_changes)
    else:
        lines.append("- None")

    return "\n".join(lines) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description="Compare AAOP catalog changes.")
    parser.add_argument("--base-ref", default="origin/main", help="Git ref to diff against")
    parser.add_argument("--output", help="Optional markdown output path")
    args = parser.parse_args()

    report = build_report(args.base_ref)
    print(report)

    if args.output:
        output_path = BASE_DIR / args.output
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(report)

    return 0


if __name__ == "__main__":
    sys.exit(main())
