"""
AAOP MVP API — FastAPI backend.

Endpoints:
    POST /ask       — route a question to an agent, return the answer
    POST /feedback  — record thumbs up/down for an interaction
    GET  /health    — liveness check
"""

import logging
import os
import sys
from pathlib import Path

import yaml
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

load_dotenv(Path(__file__).parent.parent / ".env")

sys.path.insert(0, str(Path(__file__).parent.parent))

ENV = os.getenv("AAOP_ENV", "dev").lower()

from core.orchestration.agent_runner import AgentRunner
from core.registry import AgentRegistry
from db.store import InteractionStore
from tools.mock_snowflake import build_agent_context

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

BASE_DIR = Path(__file__).parent.parent
store = InteractionStore()
runner = AgentRunner(base_dir=str(BASE_DIR))
agent_registry = AgentRegistry(base_dir=BASE_DIR, env=ENV)


# ── Pydantic models ───────────────────────────────────────────────

class AskRequest(BaseModel):
    question: str = Field(..., min_length=1, max_length=2000)
    agent: str = Field(default="finance-finance-summary")
    version: str = Field(default="v1.0.0")
    document_content: str = Field(default="")


class AskResponse(BaseModel):
    interaction_id: str
    answer: str
    agent: str
    version: str
    tokens: int
    cost_usd: float
    duration_seconds: float
    status: str


class FeedbackRequest(BaseModel):
    interaction_id: str
    feedback: int = Field(..., description="1 = thumbs up, -1 = thumbs down")


class FeedbackResponse(BaseModel):
    ok: bool


# ── App ───────────────────────────────────────────────────────────

app = FastAPI(title="AAOP MVP API", version="0.5.0")


def _load_prompts(agent: str, version: str) -> dict:
    path = BASE_DIR / "agents" / agent / version / "prompts.json"
    if not path.exists():
        return {}
    import json
    return json.loads(path.read_text())


def _build_messages(question: str, agent: str, version: str, document_content: str) -> list[dict]:
    prompts = _load_prompts(agent, version)
    messages = []
    if prompts.get("system"):
        messages.append({"role": "system", "content": prompts["system"]})
    user_content = prompts.get("user", "{{question}}").replace("{{question}}", question)
    if document_content:
        user_content = f"{user_content}\n\nDocument:\n{document_content}"
    messages.append({"role": "user", "content": user_content})
    return messages


def _active_agents() -> dict[str, str]:
    """Return {agent_name: version} registered for the current environment."""
    return agent_registry.list_active_versions()


@app.get("/health")
async def health() -> dict:
    active = _active_agents()
    agents = [
        agent.model_dump(mode="json")
        for agent in agent_registry.list_agents()
    ]
    return {"status": "ok", "env": ENV, "agents": active, "agent_details": agents}


@app.post("/ask", response_model=AskResponse)
async def ask(req: AskRequest) -> AskResponse:
    # enforce environment — only serve agents active in this env
    active = _active_agents()
    if req.agent not in active:
        raise HTTPException(
            status_code=403,
            detail=f"Agent '{req.agent}' is not registered in environment '{ENV}'. "
                   f"Active agents: {list(active.keys())}"
        )
    # use the registry-pinned version for this env, not whatever the client sends
    req = req.model_copy(update={"version": active[req.agent]})

    agent_dir = BASE_DIR / "agents" / req.agent / req.version
    if not agent_dir.exists():
        raise HTTPException(status_code=404, detail=f"Agent '{req.agent}' version '{req.version}' not found")

    # auto-inject mock data for semantic view agents when no document_content provided
    document_content = req.document_content
    if not document_content:
        agent_cfg_path = agent_dir / "agent.yaml"
        if agent_cfg_path.exists():
            with open(agent_cfg_path) as f:
                agent_cfg = yaml.safe_load(f)
            data_source = agent_cfg.get("data_source", {})
            if data_source.get("type") == "snowflake_semantic_view":
                view = data_source["view"]
                document_content = build_agent_context(view, req.question)
                logger.info(f"Injected mock data for view '{view}'")

    try:
        result = await runner.run(
            agent_name=req.agent,
            version=req.version,
            query=req.question,
            document_content=document_content,
        )
    except Exception as exc:
        logger.error(f"Agent run failed: {exc}")
        raise HTTPException(status_code=500, detail=str(exc))

    answer = result.output or "(no answer returned)"
    if result.output_parsed and isinstance(result.output_parsed, dict):
        answer = result.output_parsed.get("answer") or result.output

    interaction_id = store.save_interaction(
        agent=req.agent,
        version=req.version,
        question=req.question,
        answer=answer,
        tokens=result.total_tokens,
        cost_usd=result.total_cost,
        duration_seconds=result.duration_seconds,
        status=result.status,
    )

    return AskResponse(
        interaction_id=interaction_id,
        answer=answer,
        agent=req.agent,
        version=req.version,
        tokens=result.total_tokens,
        cost_usd=result.total_cost,
        duration_seconds=result.duration_seconds,
        status=result.status,
    )


@app.post("/feedback", response_model=FeedbackResponse)
async def feedback(req: FeedbackRequest) -> FeedbackResponse:
    if req.feedback not in (1, -1):
        raise HTTPException(status_code=400, detail="feedback must be 1 or -1")
    ok = store.save_feedback(req.interaction_id, req.feedback)
    if not ok:
        raise HTTPException(status_code=404, detail="interaction_id not found")
    return FeedbackResponse(ok=True)
