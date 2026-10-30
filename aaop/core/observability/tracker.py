import json
import logging
import time
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


class RunTracker:
    def __init__(self, log_dir: str = "logs/runs"):
        self.log_dir = Path(log_dir)
        self.log_dir.mkdir(parents=True, exist_ok=True)
        self.current_run: dict[str, Any] | None = None

    def start_run(
        self, agent_name: str, version: str, metadata: dict[str, Any] | None = None
    ) -> str:
        run_id = str(uuid.uuid4())[:8]
        self.current_run = {
            "run_id": run_id,
            "agent": agent_name,
            "version": version,
            "start_time": time.time(),
            "steps": [],
            "metadata": metadata or {},
            "status": "running",
        }
        logger.info(f"Run started: {agent_name} {version} [{run_id}]")
        return run_id

    def log_step(
        self,
        step_name: str,
        input_data: Any,
        output_data: Any,
        duration: float,
        tokens: dict[str, int],
        cost: float,
        success: bool,
    ) -> None:
        if not self.current_run:
            raise RuntimeError("No active run — call start_run() first")

        self.current_run["steps"].append(
            {
                "name": step_name,
                "timestamp": datetime.now().isoformat(),
                "duration_seconds": round(duration, 2),
                "tokens": tokens,
                "cost_usd": round(cost, 6),
                "success": success,
                "input_preview": str(input_data)[:200],
                "output_preview": str(output_data)[:200],
            }
        )

    def end_run(self, status: str = "completed", error: str | None = None) -> dict[str, Any]:
        if not self.current_run:
            raise RuntimeError("No active run")

        self.current_run["end_time"] = time.time()
        self.current_run["duration_total"] = round(
            self.current_run["end_time"] - self.current_run["start_time"], 2
        )
        self.current_run["status"] = status
        if error:
            self.current_run["error"] = error

        steps = self.current_run["steps"]
        self.current_run["totals"] = {
            "total_tokens": sum(s["tokens"].get("total", 0) for s in steps),
            "total_cost": round(sum(s["cost_usd"] for s in steps), 6),
            "success_rate": (
                round(sum(1 for s in steps if s["success"]) / len(steps), 2)
                if steps
                else 0.0
            ),
        }

        filename = (
            f"{self.current_run['agent']}_"
            f"{self.current_run['run_id']}_"
            f"{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        )
        filepath = self.log_dir / filename
        with open(filepath, "w") as f:
            json.dump(self.current_run, f, indent=2)

        logger.info(
            f"Run saved: {filepath} | "
            f"cost=${self.current_run['totals']['total_cost']} | "
            f"status={status}"
        )
        run = self.current_run
        self.current_run = None
        return run
