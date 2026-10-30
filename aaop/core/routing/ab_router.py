import hashlib
import logging

logger = logging.getLogger(__name__)


class ABRouter:
    def __init__(self, agent: str, v1: str, v2: str, split: float = 0.5):
        self.agent = agent
        self.v1 = v1
        self.v2 = v2
        self.split = split

    def route(self, request_id: str) -> str:
        """Deterministic split — same request_id always gets same version."""
        digest = int(hashlib.md5(request_id.encode()).hexdigest(), 16)
        bucket = (digest % 100) / 100.0
        version = self.v1 if bucket < self.split else self.v2
        logger.debug(f"AB route: {request_id} → {version} (bucket={bucket:.2f})")
        return version
