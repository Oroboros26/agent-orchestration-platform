#!/usr/bin/env python3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from core.registry import AgentRegistry

ENV_KEYS = ("dev", "uat", "prod")


def check_version(registry, agent_name, env_name):
    try:
        agent = registry.get_agent(agent_name, env=env_name)
    except KeyError:
        return True

    if agent.health.healthy:
        print(f"✓ {agent_name} {env_name} -> {agent.version}")
        return True

    print(
        f"✗ {agent_name} {env_name} -> {agent.version}: "
        f"{agent.health.reason}"
    )
    return False


def check_pinned_version(registry, agent_name, env_name, version):
    agent = registry.load_agent(agent_name, str(version))
    if agent.health.healthy:
        print(f"✓ {agent_name} {env_name} -> {version}")
        return True

    print(f"✗ {agent_name} {env_name} -> {version}: {agent.health.reason}")
    return False


def main():
    aaop_root = Path(__file__).resolve().parents[2]
    registry = AgentRegistry(base_dir=aaop_root)
    checked = 0
    ok = True

    for agent_name, entry in registry.list_entries().items():
        for env_name in ENV_KEYS:
            version = getattr(entry, env_name)
            if version is None:
                if env_name == "uat":
                    ok = check_version(registry, agent_name, env_name) and ok
                continue
            checked += 1
            ok = check_pinned_version(registry, agent_name, env_name, version) and ok

    if checked == 0:
        print("No pinned registry versions to check.")

    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
