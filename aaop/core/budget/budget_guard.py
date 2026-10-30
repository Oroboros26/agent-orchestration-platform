import logging
import os
import time
from collections import deque

import yaml

logger = logging.getLogger(__name__)


class BudgetExceededError(Exception):
    pass


class BudgetGuard:
    def __init__(self, config_path: str | None = None):
        self.limit = self._load_limit(config_path)
        self._window: deque[tuple[float, float]] = deque()  # (timestamp, cost)

    def _load_limit(self, config_path: str | None) -> float:
        if config_path and os.path.exists(config_path):
            with open(config_path) as f:
                data = yaml.safe_load(f)
                return float(data.get("budget_limit_usd", 10.0))
        env = os.getenv("AAOP_ENV", "dev")
        defaults = {"dev": 1.0, "staging": 5.0, "prod": 50.0}
        return defaults.get(env, 1.0)

    def _hourly_spend(self) -> float:
        now = time.time()
        cutoff = now - 3600
        while self._window and self._window[0][0] < cutoff:
            self._window.popleft()
        return sum(cost for _, cost in self._window)

    def check(self, estimated_cost: float) -> None:
        current = self._hourly_spend()
        if current + estimated_cost > self.limit:
            raise BudgetExceededError(
                f"Budget exceeded: ${current:.4f} spent + ${estimated_cost:.4f} "
                f"estimated > ${self.limit:.2f} limit"
            )

    def record(self, actual_cost: float) -> None:
        self._window.append((time.time(), actual_cost))
        logger.debug(
            f"Recorded ${actual_cost:.6f} — hourly total: ${self._hourly_spend():.4f}"
        )
