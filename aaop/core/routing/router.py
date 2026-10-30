import logging
from enum import Enum
from pathlib import Path
from typing import Any

import litellm
import yaml
from tenacity import retry, stop_after_attempt, wait_exponential

logger = logging.getLogger(__name__)


class ModelTier(Enum):
    FAST = "fast"
    BALANCED = "balanced"
    POWERFUL = "powerful"


class ModelRouter:
    def __init__(self, config_path: str = "configs/models/models.yaml"):
        self.config = self._load_config(config_path)
        self.fallback_chains: dict[ModelTier, list[str]] = {
            ModelTier.FAST: self.config["tiers"]["fast"]["models"],
            ModelTier.BALANCED: self.config["tiers"]["balanced"]["models"],
            ModelTier.POWERFUL: self.config["tiers"]["powerful"]["models"],
        }
        self.pricing: dict[str, dict[str, float]] = {}
        for tier_data in self.config["tiers"].values():
            self.pricing.update(tier_data.get("pricing", {}))

    def _load_config(self, path: str) -> dict[str, Any]:
        config_path = Path(path)
        if not config_path.is_absolute():
            config_path = Path(__file__).resolve().parents[2] / config_path

        if config_path.exists():
            with open(config_path) as f:
                result: dict[str, Any] = yaml.safe_load(f)
                return result
        # fallback defaults when config file not present
        return {
            "tiers": {
                "fast": {"models": ["claude-haiku-4-5-20251001"], "pricing": {}},
                "balanced": {"models": ["claude-sonnet-4-6"], "pricing": {}},
                "powerful": {"models": ["claude-opus-4-7"], "pricing": {}},
            }
        }

    _CHAR_MAP = str.maketrans({"—": "-", "–": "-", "’": "'", "“": '"', "”": '"'})

    @classmethod
    def _sanitize_messages(cls, messages: list[dict[str, str]]) -> list[dict[str, str]]:
        """Replace typographic chars that break the Anthropic SDK's ASCII encoding path."""
        return [
            {k: v.translate(cls._CHAR_MAP) if isinstance(v, str) else v
             for k, v in msg.items()}
            for msg in messages
        ]

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(min=1, max=10))
    async def route(
        self,
        messages: list[dict[str, str]],
        tier: ModelTier = ModelTier.BALANCED,
        **kwargs: Any,
    ) -> dict[str, Any]:
        models = self.fallback_chains[tier]
        messages = self._sanitize_messages(messages)

        for idx, model in enumerate(models):
            try:
                logger.info(f"Attempting {model} (attempt {idx + 1}/{len(models)})")
                response = await litellm.acompletion(
                    model=model, messages=messages, **kwargs
                )
                logger.info(f"Success with {model}")
                return {
                    "response": response,
                    "model_used": model,
                    "fallback_level": idx,
                }
            except Exception as e:
                logger.warning(f"{model} failed: {e}")
                if idx == len(models) - 1:
                    raise RuntimeError(f"All models in tier {tier.value} failed") from e
        raise RuntimeError(f"All models in tier {tier.value} failed")

    def estimate_cost(
        self, model: str, input_tokens: int, output_tokens: int
    ) -> float:
        rates = self.pricing.get(model, {"input_per_1m": 5.0, "output_per_1m": 15.0})
        cost = (
            input_tokens * float(rates["input_per_1m"])
            + output_tokens * float(rates["output_per_1m"])
        ) / 1_000_000
        return round(cost, 6)
