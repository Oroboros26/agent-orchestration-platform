from core.routing.router import ModelRouter, ModelTier


def test_estimate_cost_known_model():
    router = ModelRouter(config_path="configs/models/models.yaml")
    cost = router.estimate_cost("claude-sonnet-4-6", input_tokens=1000, output_tokens=500)
    # 1000 * 3.0/1M + 500 * 15.0/1M = 0.003 + 0.0075 = 0.0105
    assert abs(cost - 0.0105) < 0.0001


def test_estimate_cost_unknown_model_uses_default():
    router = ModelRouter(config_path="configs/models/models.yaml")
    cost = router.estimate_cost("unknown-model", input_tokens=1_000_000, output_tokens=0)
    assert cost == 5.0  # default input rate


def test_fallback_chains_loaded():
    router = ModelRouter(config_path="configs/models/models.yaml")
    assert ModelTier.BALANCED in router.fallback_chains
    assert len(router.fallback_chains[ModelTier.BALANCED]) > 0
