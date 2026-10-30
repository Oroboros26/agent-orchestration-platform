import json
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

logger = logging.getLogger(__name__)


@dataclass
class AgentVersion:
    name: str
    major: int
    minor: int
    patch: int
    config: dict[str, Any]
    prompts: dict[str, str]
    tools: list[str]
    changelog: str
    description: str = ""
    tags: list[str] = field(default_factory=list)

    @property
    def version_string(self) -> str:
        return f"v{self.major}.{self.minor}.{self.patch}"

    @property
    def path(self) -> Path:
        return Path(f"agents/{self.name}/{self.version_string}")

    def save(self, base_dir: str = ".") -> None:
        target = Path(base_dir) / self.path
        target.mkdir(parents=True, exist_ok=True)

        with open(target / "agent.yaml", "w") as f:
            yaml.dump(
                {
                    "name": self.name,
                    "version": self.version_string,
                    "description": self.description,
                    "config": self.config,
                    "tools": self.tools,
                    "tags": self.tags,
                },
                f,
                default_flow_style=False,
            )

        with open(target / "prompts.json", "w") as f:
            json.dump(self.prompts, f, indent=2)

        with open(target / "CHANGELOG.md", "w") as f:
            f.write(self.changelog)

        logger.info(f"Saved {self.name} {self.version_string} → {target}")

    @classmethod
    def load(cls, name: str, version: str, base_dir: str = ".") -> "AgentVersion":
        path = Path(base_dir) / f"agents/{name}/{version}"

        with open(path / "agent.yaml") as f:
            data = yaml.safe_load(f)

        with open(path / "prompts.json") as f:
            prompts = json.load(f)

        with open(path / "CHANGELOG.md") as f:
            changelog = f.read()

        major, minor, patch = map(int, version.strip("v").split("."))

        return cls(
            name=data["name"],
            major=major,
            minor=minor,
            patch=patch,
            config=data["config"],
            prompts=prompts,
            tools=data.get("tools", []),
            changelog=changelog,
            description=data.get("description", ""),
            tags=data.get("tags", []),
        )

    def bump_patch(self, changelog_entry: str = "Patch update") -> "AgentVersion":
        import copy
        new = copy.deepcopy(self)
        new.patch += 1
        new.changelog = (
            f"## {new.version_string}\n- {changelog_entry}\n\n{self.changelog}"
        )
        return new

    def bump_minor(self, changelog_entry: str = "Minor update") -> "AgentVersion":
        import copy
        new = copy.deepcopy(self)
        new.minor += 1
        new.patch = 0
        new.changelog = (
            f"## {new.version_string}\n- {changelog_entry}\n\n{self.changelog}"
        )
        return new
