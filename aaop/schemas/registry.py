from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field

EnvironmentName = Literal["dev", "uat", "prod"]


class AgentHealth(BaseModel):
    healthy: bool = True
    enabled: bool = True
    reason: str = ""
    current_tasks: int = 0
    max_concurrent_tasks: int = 1


class AgentRegistryEntry(BaseModel):
    description: str = ""
    business_unit: str = ""
    source_view: str = ""
    dev: str | None = None
    uat: str | None = None
    prod: str | None = None


class RegisteredAgent(BaseModel):
    name: str
    version: str
    description: str = ""
    business_unit: str = ""
    source_view: str = ""
    capabilities: list[str] = Field(default_factory=list)
    tags: list[str] = Field(default_factory=list)
    path: Path
    model_tier: str = "balanced"
    provider: str = "auto"
    health: AgentHealth = Field(default_factory=AgentHealth)

    model_config = {"arbitrary_types_allowed": True}


class StepResult(BaseModel):
    step: str
    success: bool
    model: str = ""
    fallback_level: int = 0
    input_tokens: int = 0
    output_tokens: int = 0
    total_tokens: int = 0
    cost: float = 0.0
    duration: float = 0.0
    error: str | None = None


class RunSummary(BaseModel):
    run_id: str
    agent: str
    version: str
    status: str
    total_tokens: int = 0
    total_cost: float = 0.0
    duration_seconds: float = 0.0
    steps: list[StepResult] = Field(default_factory=list)
