"""
Agent validator — runs in CI with no LLM calls.

Checks every registered agent has:
  - agent.yaml   (valid YAML, required fields present)
  - prompts.json (valid JSON, system key present)
  - CHANGELOG.md (exists)
  - golden dataset in evals/test_cases/ (if data agent)
  - mock data CSV in data/mock/ (if snowflake_semantic_view)
  - schema JSON in schemas/views/ (if snowflake_semantic_view)

Exit 0 = all checks pass.
Exit 1 = one or more agents failed — lists every problem.

Usage:
    python tools/testing/validate_agents.py
"""

import json
import sys
from pathlib import Path

import yaml

BASE_DIR = Path(__file__).resolve().parent.parent.parent

REQUIRED_AGENT_YAML_FIELDS = ["name", "version", "role", "goal", "model", "workflow"]
PASS = "✓"
FAIL = "✗"


def check_agent(agent_name: str, version: str) -> list[str]:
    errors = []
    agent_dir = BASE_DIR / "agents" / agent_name / version

    # --- agent.yaml ---
    yaml_path = agent_dir / "agent.yaml"
    if not yaml_path.exists():
        errors.append("missing agent.yaml")
        return errors  # can't check further without it

    try:
        cfg = yaml.safe_load(yaml_path.read_text())
    except yaml.YAMLError as e:
        errors.append(f"agent.yaml invalid YAML: {e}")
        return errors

    for field in REQUIRED_AGENT_YAML_FIELDS:
        if field not in cfg:
            errors.append(f"agent.yaml missing required field: '{field}'")

    if cfg.get("name") != agent_name:
        errors.append(f"agent.yaml name '{cfg.get('name')}' does not match folder '{agent_name}'")

    if cfg.get("version") != version:
        errors.append(f"agent.yaml version '{cfg.get('version')}' does not match folder '{version}'")

    # --- prompts.json ---
    prompts_path = agent_dir / "prompts.json"
    if not prompts_path.exists():
        errors.append("missing prompts.json")
    else:
        try:
            prompts = json.loads(prompts_path.read_text())
            if not prompts.get("system"):
                errors.append("prompts.json missing 'system' key or it is empty")
        except json.JSONDecodeError as e:
            errors.append(f"prompts.json invalid JSON: {e}")

    # --- CHANGELOG.md ---
    if not (agent_dir / "CHANGELOG.md").exists():
        errors.append("missing CHANGELOG.md")

    # --- data source checks ---
    ds = cfg.get("data_source", {})
    if ds.get("type") == "snowflake_semantic_view":
        view = ds.get("view")
        if not view:
            errors.append("data_source.view is missing")
        else:
            schema_path = BASE_DIR / f"schemas/views/{view}.json"
            if not schema_path.exists():
                errors.append(f"missing schemas/views/{view}.json")

            csv_path = BASE_DIR / f"data/mock/{view}.csv"
            if not csv_path.exists():
                errors.append(f"missing data/mock/{view}.csv")

        # golden dataset required for data agents
        golden_path = BASE_DIR / f"evals/test_cases/{agent_name}/golden.json"
        if not golden_path.exists():
            errors.append(f"missing evals/test_cases/{agent_name}/golden.json")
        else:
            try:
                cases = json.loads(golden_path.read_text())
                if not isinstance(cases, list) or len(cases) < 3:
                    errors.append("golden.json must be a list with at least 3 test cases")
                for case in cases:
                    for key in ("id", "question", "must_contain"):
                        if key not in case:
                            errors.append(f"golden.json case missing required key: '{key}'")
            except json.JSONDecodeError as e:
                errors.append(f"golden.json invalid JSON: {e}")

    return errors


def main() -> int:
    registry_path = BASE_DIR / "configs/registry.yaml"
    if not registry_path.exists():
        print(f"{FAIL} configs/registry.yaml not found")
        return 1

    registry = yaml.safe_load(registry_path.read_text())
    agents_cfg = registry.get("agents", {})

    if not agents_cfg:
        print(f"{FAIL} No agents found in registry.yaml")
        return 1

    all_errors: dict[str, list[str]] = {}

    for agent_name, env_cfg in agents_cfg.items():
        # collect all unique versions referenced in registry
        versions = set()
        for env in ("dev", "uat", "prod"):
            v = env_cfg.get(env)
            if v:
                versions.add(v)

        if not versions:
            # agent exists in registry but no version deployed anywhere — skip
            continue

        for version in sorted(versions):
            key = f"{agent_name}  {version}"
            errors = check_agent(agent_name, version)
            all_errors[key] = errors

    # also check any agent folder not yet in registry
    agents_dir = BASE_DIR / "agents"
    if agents_dir.exists():
        for agent_path in sorted(agents_dir.iterdir()):
            if not agent_path.is_dir():
                continue
            for ver_path in sorted(agent_path.iterdir()):
                if not ver_path.is_dir():
                    continue
                key = f"{agent_path.name}  {ver_path.name}"
                if key not in all_errors:
                    errors = check_agent(agent_path.name, ver_path.name)
                    all_errors[key] = errors

    # print results
    failed = 0
    for key, errors in sorted(all_errors.items()):
        if errors:
            print(f"{FAIL}  {key}")
            for e in errors:
                print(f"     → {e}")
            failed += 1
        else:
            print(f"{PASS}  {key}")

    print()
    total = len(all_errors)
    passed = total - failed
    print(f"  {passed}/{total} agents passed validation")

    if failed:
        print(f"\n  Fix the {failed} issue(s) above before merging.")
        return 1

    print("  All agents valid — safe to merge.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
