import logging
import time
from typing import Any, TypedDict

from langgraph.graph import END, StateGraph

from core.budget.budget_guard import BudgetGuard
from core.routing.router import ModelRouter, ModelTier

logger = logging.getLogger(__name__)

TIER_MAP = {
    "fast": ModelTier.FAST,
    "balanced": ModelTier.BALANCED,
    "powerful": ModelTier.POWERFUL,
}


class AgentState(TypedDict):
    agent_name: str
    version: str
    run_id: str
    messages: list[dict[str, str]]
    current_step: str
    context: dict[str, Any]
    iterations: int
    max_iterations: int
    model_tier: str
    temperature: float
    max_output_tokens: int
    role: str
    goal: str
    # prompts loaded from prompts.json — optional, falls back to role/goal
    system_prompt: str
    # workflow steps from agent.yaml (list of step dicts with id/description/next)
    workflow_steps: list[dict[str, Any]]
    completed_steps: list[dict[str, Any]]
    output: str


async def _llm_call(
    state: AgentState,
    router: ModelRouter,
    guard: BudgetGuard,
    system_prompt: str,
    user_prompt: str,
) -> tuple[str, dict[str, Any]]:
    tier = TIER_MAP.get(state["model_tier"], ModelTier.BALANCED)

    estimated = router.estimate_cost(
        router.fallback_chains[tier][0], 500, state["max_output_tokens"]
    )
    guard.check(estimated)

    messages = [
        {"role": "system", "content": system_prompt},
        *state["messages"],
        {"role": "user", "content": user_prompt},
    ]

    t0 = time.time()
    result = await router.route(
        messages,
        tier=tier,
        temperature=state["temperature"],
        max_tokens=state["max_output_tokens"],
    )
    duration = round(time.time() - t0, 2)

    response = result["response"]
    usage = response.usage
    actual_cost = router.estimate_cost(
        result["model_used"], usage.prompt_tokens, usage.completion_tokens
    )
    guard.record(actual_cost)

    return response.choices[0].message.content, {
        "model": result["model_used"],
        "fallback_level": result["fallback_level"],
        "input_tokens": usage.prompt_tokens,
        "output_tokens": usage.completion_tokens,
        "total_tokens": usage.prompt_tokens + usage.completion_tokens,
        "cost": actual_cost,
        "duration": duration,
    }


def _build_system_prompt(state: AgentState, step_description: str) -> str:
    """
    Use the agent's system_prompt from prompts.json if available.
    Otherwise fall back to role + goal from agent.yaml.
    """
    base = state.get("system_prompt") or f"{state['role']}\n\nGoal: {state['goal']}"
    return f"{base}\n\nCurrent task: {step_description}"


def _build_user_prompt(state: AgentState, step_id: str, previous_output: str) -> str:
    """
    Build a user prompt that includes the data context, the question,
    and any output from previous steps.
    """
    ctx = state["context"]
    query = ctx.get("query", "")
    document_content = ctx.get("document_content", "")

    parts = []
    if document_content:
        parts.append(f"Data / Context:\n{document_content}")
    if previous_output:
        parts.append(f"Previous analysis:\n{previous_output}")
    parts.append(f"Question: {query}")

    return "\n\n".join(parts)


def create_workflow(router: ModelRouter, guard: BudgetGuard) -> Any:

    async def run_step(state: AgentState, step: dict[str, Any]) -> AgentState:
        step_id = step["id"]
        step_description = step.get("description", step_id)
        logger.info(f"[{state['agent_name']}] step: {step_id}")
        t0 = time.time()

        # pass along any output from the previous step
        previous_output = state["context"].get("last_step_output", "")

        system = _build_system_prompt(state, step_description)
        user = _build_user_prompt(state, step_id, previous_output)

        try:
            content, usage = await _llm_call(state, router, guard, system, user)
            state["context"]["last_step_output"] = content
            state["context"][f"{step_id}_output"] = content
            state["context"][f"{step_id}_done"] = True
            # the last step's output is the final answer
            state["output"] = content
            success = True
        except Exception as e:
            logger.error(f"[{state['agent_name']}] step '{step_id}' failed: {e}")
            state["context"][f"{step_id}_done"] = True
            state["context"][f"{step_id}_error"] = str(e)
            usage = {"total_tokens": 0, "cost": 0.0, "duration": round(time.time() - t0, 2),
                     "input_tokens": 0, "output_tokens": 0, "model": "", "fallback_level": 0}
            success = False

        state["completed_steps"].append({"step": step_id, "success": success, **usage})
        state["iterations"] += 1
        return state

    def _get_steps(state: AgentState) -> list[dict[str, Any]]:
        """Return the workflow steps from agent.yaml, or a sensible single-step default."""
        steps = state.get("workflow_steps") or []
        if steps:
            return steps
        return [{"id": "answer", "description": "Answer the question directly and clearly.", "next": "END"}]

    def should_continue(state: AgentState) -> str:
        steps = _get_steps(state)
        for step in steps:
            if not state["context"].get(f"{step['id']}_done"):
                return str(step["id"])
        return "end"

    # Build dynamic nodes — one per possible step id found across all agents
    # We use a generic dispatcher node and route by step id.
    KNOWN_STEP_IDS = ["research", "analyze", "draft", "answer", "summarize", "format"]

    workflow = StateGraph(AgentState)

    for sid in KNOWN_STEP_IDS:
        def _node_factory(step_id: str) -> Any:
            async def node(state: AgentState) -> AgentState:
                steps = _get_steps(state)
                step = next((s for s in steps if s["id"] == step_id),
                            {"id": step_id, "description": step_id, "next": "END"})
                return await run_step(state, step)
            return node

        workflow.add_node(sid, _node_factory(sid))

    # entry node: routes to whichever step the agent.yaml defines as first
    async def entry_node(state: AgentState) -> AgentState:
        return state

    workflow.add_node("__entry__", entry_node)
    workflow.set_entry_point("__entry__")

    edge_map: dict[str, str] = {sid: sid for sid in KNOWN_STEP_IDS}
    edge_map["end"] = END
    workflow.add_conditional_edges("__entry__", should_continue, edge_map)  # type: ignore[arg-type]

    for sid in KNOWN_STEP_IDS:
        workflow.add_conditional_edges(sid, should_continue, edge_map)  # type: ignore[arg-type]

    return workflow.compile()
