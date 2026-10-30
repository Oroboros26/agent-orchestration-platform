import json
import logging
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

from core.budget.budget_guard import BudgetGuard
from core.observability.tracker import RunTracker
from core.orchestration.state_machine import AgentState, create_workflow
from core.routing.router import ModelRouter

logger = logging.getLogger(__name__)


@dataclass
class RunResult:
    run_id: str
    agent: str
    version: str
    output: str
    output_parsed: dict[str, Any] | None
    status: str
    total_tokens: int
    total_cost: float
    duration_seconds: float
    steps: list[dict[str, Any]]


class AgentRunner:
    def __init__(
        self,
        base_dir: str = ".",
        log_dir: str = "logs/runs",
        config_dir: str = "configs",
    ):
        self.base_dir = Path(base_dir)
        env = os.getenv("AAOP_ENV", "dev")
        env_config_path = self.base_dir / f"configs/environments/{env}.yaml"

        self.router = ModelRouter(
            config_path=str(self.base_dir / "configs/models/models.yaml")
        )
        self.guard = BudgetGuard(
            config_path=str(env_config_path) if env_config_path.exists() else None
        )
        self.tracker = RunTracker(log_dir=str(self.base_dir / log_dir))

    def _load_agent_config(self, agent_name: str, version: str) -> dict[str, Any]:
        path = self.base_dir / f"agents/{agent_name}/{version}/agent.yaml"
        if not path.exists():
            raise FileNotFoundError(f"Agent not found: {agent_name} {version}")
        with open(path) as f:
            result: dict[str, Any] = yaml.safe_load(f)
            return result

    async def run(
        self,
        agent_name: str,
        version: str,
        query: str,
        document_content: str = "",
        metadata: dict[str, Any] | None = None,
    ) -> RunResult:
        config = self._load_agent_config(agent_name, version)
        model_cfg = config.get("model", {})
        run_id = self.tracker.start_run(agent_name, version, metadata)

        workflow = create_workflow(self.router, self.guard)

        # load prompts.json if present
        prompts_path = self.base_dir / f"agents/{agent_name}/{version}/prompts.json"
        system_prompt = ""
        if prompts_path.exists():
            with open(prompts_path) as f:
                prompts = json.load(f)
            system_prompt = prompts.get("system", "")

        workflow_steps = config.get("workflow", {}).get("steps", [])

        initial_state = AgentState(
            agent_name=agent_name,
            version=version,
            run_id=run_id,
            messages=[],
            current_step="start",
            context={
                "query": query,
                "document_content": document_content,
            },
            iterations=0,
            max_iterations=config.get("workflow", {}).get("max_iterations", 10),
            model_tier=model_cfg.get("tier", "balanced"),
            temperature=float(model_cfg.get("temperature", 0.0)),
            max_output_tokens=int(model_cfg.get("max_output_tokens", 1000)),
            role=config.get("role", "You are a helpful AI assistant.").strip(),
            goal=config.get("goal", "Complete the task.").strip(),
            system_prompt=system_prompt,
            workflow_steps=workflow_steps,
            completed_steps=[],
            output="",
        )

        error_msg = None
        try:
            final_state = await workflow.ainvoke(initial_state)
            status = "completed"
        except Exception as e:
            logger.error(f"Workflow failed for {agent_name} {version}: {e}")
            final_state = initial_state
            final_state["output"] = "{}"
            status = "failed"
            error_msg = str(e)

        # parse output JSON if possible
        output_parsed = None
        try:
            output_parsed = json.loads(final_state["output"])
        except (json.JSONDecodeError, TypeError):
            pass

        # log each step to tracker
        for step in final_state["completed_steps"]:
            self.tracker.log_step(
                step_name=step["step"],
                input_data=step["step"],
                output_data=step.get("model", ""),
                duration=step.get("duration", 0.0),
                tokens={
                    "input": step.get("input_tokens", 0),
                    "output": step.get("output_tokens", 0),
                    "total": step.get("total_tokens", 0),
                },
                cost=step.get("cost", 0.0),
                success=step.get("success", False),
            )

        run_log = self.tracker.end_run(status=status, error=error_msg)

        return RunResult(
            run_id=run_id,
            agent=agent_name,
            version=version,
            output=final_state["output"],
            output_parsed=output_parsed,
            status=status,
            total_tokens=run_log["totals"]["total_tokens"],
            total_cost=run_log["totals"]["total_cost"],
            duration_seconds=run_log["duration_total"],
            steps=final_state["completed_steps"],
        )
