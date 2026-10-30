from pathlib import Path

import pytest

from core.registry import AgentRegistry


def _write_agent(base: Path, name: str, version: str, *, changelog: bool = True) -> None:
    agent_dir = base / "agents" / name / version
    agent_dir.mkdir(parents=True)
    (agent_dir / "agent.yaml").write_text(
        f"""
name: {name}
version: {version}
description: Test agent
model:
  tier: fast
  provider: auto
tools:
  - document_retrieval
workflow:
  steps:
    - id: analyze
      description: Analyze input
metadata:
  business_unit: finance
  tags: [finance, variance_summary]
data_source:
  type: snowflake_semantic_view
  view: finance_summary
""",
        encoding="utf-8",
    )
    (agent_dir / "prompts.json").write_text('{"system": "test"}', encoding="utf-8")
    if changelog:
        (agent_dir / "CHANGELOG.md").write_text("## test\n", encoding="utf-8")


def _write_registry(base: Path) -> None:
    config_dir = base / "configs"
    config_dir.mkdir()
    (config_dir / "registry.yaml").write_text(
        """
agents:
  finance-agent:
    description: Finance test agent
    business_unit: finance
    source_view: finance_summary
    dev: v1.0.0
    uat: null
    prod: null
  broken-agent:
    description: Broken test agent
    business_unit: ops
    source_view: ops_incidents
    dev: v1.0.0
    uat: null
    prod: null
""",
        encoding="utf-8",
    )


@pytest.fixture
def registry_base(tmp_path):
    _write_registry(tmp_path)
    _write_agent(tmp_path, "finance-agent", "v1.0.0")
    _write_agent(tmp_path, "broken-agent", "v1.0.0", changelog=False)
    return tmp_path


def test_resolves_dev_and_uat_fallback(registry_base):
    registry = AgentRegistry(base_dir=registry_base, env="dev")

    assert registry.resolve_version("finance-agent") == "v1.0.0"
    assert registry.resolve_version("finance-agent", env="uat") == "v1.0.0"


def test_prod_does_not_fallback_to_dev(registry_base):
    registry = AgentRegistry(base_dir=registry_base, env="prod")

    with pytest.raises(KeyError, match="no active version"):
        registry.resolve_version("finance-agent")


def test_loads_capabilities_from_agent_metadata(registry_base):
    registry = AgentRegistry(base_dir=registry_base)

    agent = registry.get_agent("finance-agent")

    assert agent.name == "finance-agent"
    assert agent.version == "v1.0.0"
    assert agent.health.healthy is True
    assert agent.model_tier == "fast"
    assert "finance" in agent.capabilities
    assert "finance-summary" in agent.capabilities
    assert "document-retrieval" in agent.capabilities
    assert "variance-summary" in agent.capabilities


def test_find_by_capability(registry_base):
    registry = AgentRegistry(base_dir=registry_base)

    matches = registry.find_by_capability("variance_summary")

    assert [agent.name for agent in matches] == ["finance-agent"]


def test_missing_required_files_returns_unhealthy_agent(registry_base):
    registry = AgentRegistry(base_dir=registry_base)

    agent = registry.get_agent("broken-agent")

    assert agent.health.healthy is False
    assert "CHANGELOG.md" in agent.health.reason
