import os
from pathlib import Path
from typing import Any

import yaml

from schemas.registry import (
    AgentHealth,
    AgentRegistryEntry,
    EnvironmentName,
    RegisteredAgent,
)

ENVIRONMENTS: tuple[EnvironmentName, ...] = ("dev", "uat", "prod")
REQUIRED_AGENT_FILES = ("agent.yaml", "prompts.json", "CHANGELOG.md")


class AgentRegistry:
    """Environment-aware registry for versioned AAOP agents."""

    def __init__(
        self,
        base_dir: str | Path = ".",
        env: EnvironmentName | None = None,
        registry_path: str | Path | None = None,
    ) -> None:
        self.base_dir = Path(base_dir)
        raw_env = env if env is not None else (os.getenv("AAOP_ENV") or "dev")
        self.env = self._normalize_env(raw_env)
        self.registry_path = (
            Path(registry_path)
            if registry_path is not None
            else self.base_dir / "configs" / "registry.yaml"
        )
        self._entries = self._load_entries()

    def _normalize_env(self, env: str) -> EnvironmentName:
        normalized = env.lower()
        if normalized == "staging":
            normalized = "uat"
        if normalized not in ENVIRONMENTS:
            raise ValueError(f"Unsupported AAOP environment: {env}")
        return normalized

    def _load_entries(self) -> dict[str, AgentRegistryEntry]:
        if not self.registry_path.exists():
            return {}

        with self.registry_path.open(encoding="utf-8") as registry_file:
            raw = yaml.safe_load(registry_file) or {}

        entries = raw.get("agents") or {}
        return {
            name: AgentRegistryEntry.model_validate(entry or {})
            for name, entry in entries.items()
        }

    def list_entries(self) -> dict[str, AgentRegistryEntry]:
        return dict(self._entries)

    def resolve_version(
        self,
        agent_name: str,
        env: EnvironmentName | str | None = None,
    ) -> str:
        target_env = self._normalize_env(env or self.env)
        entry = self._entries.get(agent_name)
        if entry is None:
            raise KeyError(f"Agent '{agent_name}' is not in the registry")

        version = self._entry_version(entry, target_env)
        if version:
            return version

        if target_env == "uat" and entry.dev:
            return entry.dev

        raise KeyError(
            f"Agent '{agent_name}' has no active version for environment '{target_env}'"
        )

    def list_active_versions(
        self,
        env: EnvironmentName | str | None = None,
    ) -> dict[str, str]:
        active: dict[str, str] = {}
        for agent_name in self._entries:
            try:
                active[agent_name] = self.resolve_version(agent_name, env)
            except KeyError:
                continue
        return active

    def get_agent(
        self,
        agent_name: str,
        env: EnvironmentName | str | None = None,
    ) -> RegisteredAgent:
        version = self.resolve_version(agent_name, env)
        return self.load_agent(agent_name, version)

    def list_agents(
        self,
        env: EnvironmentName | str | None = None,
    ) -> list[RegisteredAgent]:
        return [
            self.load_agent(agent_name, version)
            for agent_name, version in self.list_active_versions(env).items()
        ]

    def find_by_capability(
        self,
        capability: str,
        env: EnvironmentName | str | None = None,
    ) -> list[RegisteredAgent]:
        wanted = self._normalize_capability(capability)
        return [
            agent
            for agent in self.list_agents(env)
            if wanted in agent.capabilities
        ]

    def load_agent(self, agent_name: str, version: str) -> RegisteredAgent:
        agent_dir = self.base_dir / "agents" / agent_name / version
        config_path = agent_dir / "agent.yaml"

        missing = [
            filename
            for filename in REQUIRED_AGENT_FILES
            if not (agent_dir / filename).is_file()
        ]
        if missing:
            return self._unhealthy_agent(
                agent_name=agent_name,
                version=version,
                agent_dir=agent_dir,
                reason=f"Missing required files: {', '.join(missing)}",
            )

        with config_path.open(encoding="utf-8") as config_file:
            config = yaml.safe_load(config_file) or {}

        entry = self._entries.get(agent_name)
        metadata = config.get("metadata") or {}
        data_source = config.get("data_source") or {}
        model = config.get("model") or {}

        business_unit = (
            str(metadata.get("business_unit") or "")
            or (entry.business_unit if entry else "")
        )
        source_view = (
            str(data_source.get("view") or metadata.get("source_view") or "")
            or (entry.source_view if entry else "")
        )

        return RegisteredAgent(
            name=str(config.get("name") or agent_name),
            version=str(config.get("version") or version),
            description=str(config.get("description") or (entry.description if entry else "")),
            business_unit=business_unit,
            source_view=source_view,
            capabilities=self._extract_capabilities(config, business_unit, source_view),
            tags=[str(tag) for tag in metadata.get("tags", [])],
            path=agent_dir,
            model_tier=str(model.get("tier") or "balanced"),
            provider=str(model.get("provider") or "auto"),
            health=AgentHealth(),
        )

    def _unhealthy_agent(
        self,
        agent_name: str,
        version: str,
        agent_dir: Path,
        reason: str,
    ) -> RegisteredAgent:
        entry = self._entries.get(agent_name)
        return RegisteredAgent(
            name=agent_name,
            version=version,
            description=entry.description if entry else "",
            business_unit=entry.business_unit if entry else "",
            source_view=entry.source_view if entry else "",
            path=agent_dir,
            health=AgentHealth(healthy=False, enabled=False, reason=reason),
        )

    def _extract_capabilities(
        self,
        config: dict[str, Any],
        business_unit: str,
        source_view: str,
    ) -> list[str]:
        values: list[str] = []
        metadata = config.get("metadata") or {}
        data_source = config.get("data_source") or {}

        for key in ("capabilities", "tools"):
            values.extend(str(item) for item in config.get(key, []) or [])

        values.extend(str(item) for item in metadata.get("capabilities", []) or [])
        values.extend(str(item) for item in metadata.get("tags", []) or [])

        for value in (business_unit, source_view, data_source.get("type")):
            if value:
                values.append(str(value))

        workflow = config.get("workflow") or {}
        for step in workflow.get("steps", []) or []:
            step_id = step.get("id")
            if step_id:
                values.append(str(step_id))

        normalized = {self._normalize_capability(value) for value in values if value}
        return sorted(normalized)

    @staticmethod
    def _normalize_capability(value: str) -> str:
        return value.strip().lower().replace(" ", "-").replace("_", "-")

    @staticmethod
    def _entry_version(
        entry: AgentRegistryEntry,
        env: EnvironmentName,
    ) -> str | None:
        if env == "dev":
            return entry.dev
        if env == "uat":
            return entry.uat
        return entry.prod
