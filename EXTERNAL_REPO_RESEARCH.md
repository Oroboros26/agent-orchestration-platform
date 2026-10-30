# External Repo Research

Research branch: `research-upstream-comparison`

Cloned repositories:

- `external-research/dev-pro-agents`
  - Source: `https://github.com/BjornMelin/dev-pro-agents.git`
- `external-research/agents`
  - Source: `https://github.com/expectbugs/agents.git`

This note captures ideas worth borrowing for AAOP. It is not a recommendation to merge either codebase wholesale.

## Executive Summary

AAOP is already more platform-oriented than both references: it has versioned agents, model-tier routing, fallback chains, budget enforcement, run tracking, API/UI entrypoints, and eval/planning docs.

The strongest ideas to borrow are:

1. Add a real agent registry abstraction with capability indexing and health/load metadata.
2. Promote AAOP's ad hoc run state into stricter Pydantic models for run requests, step results, agent metadata, and agent reports.
3. Add LangGraph state reducers for append/update fields such as step outputs, task queues, and messages.
4. Add optional persistence for workflow checkpoints and cross-run memory, but keep it behind interfaces so Redis/Qdrant/Neo4j are not required for the local demo path.
5. Add developer-facing trace tests that inspect graph state transitions, not only final outputs.

## Repo 1: dev-pro-agents

Best fit for AAOP: typed platform internals and agent management.

Notable patterns:

- `src/core/agent_registry.py` keeps a registry of agent instances and indexes capabilities for fast routing.
- `src/core/orchestrator.py` builds LangGraph nodes dynamically from registered agents.
- `src/schemas/unified_models.py` uses Pydantic v2 models, enums, computed fields, and validators for task delegation and agent reports.
- `src/repositories/` and `src/services/` separate persistence from business logic.
- `src/config/agents.yaml` and `src/config/orchestrator.yaml` separate agent and orchestrator configuration.
- `tests/test_unified_models.py` directly tests enum coverage, field constraints, computed fields, and LLM JSON extraction.

What to borrow:

- A lightweight `AgentRegistry` for AAOP that loads versioned agent metadata from `aaop/configs/registry.yaml` and `aaop/agents/*/*/agent.yaml`.
- Capability tags in agent config, such as `capabilities: ["finance_analysis", "variance_summary"]`.
- Health/load metadata for agents exposed in UI and API.
- Pydantic models for agent run state and step reports.
- Tests around schema validation and routing selection.

What to avoid:

- Hardcoding specific agents in the orchestrator. AAOP should keep versioned folders as the source of truth.
- Tying the registry to concrete in-process agent objects too early. AAOP may route to local agents, APIs, batch jobs, or future remote runtimes.
- Pulling in SQLModel until there is a clear persistence boundary that needs relational querying.

## Repo 2: expectbugs/agents

Best fit for AAOP: workflow state, persistence, memory, and research tooling.

Notable patterns:

- `src/orchestrator.py` defines a LangGraph `MultiAgentState` that inherits from `MessagesState`.
- `task_queue_reducer` prevents task queue overwrites by merging task updates by ID.
- `BaseAgent` has async initialization, cleanup, Redis state save/load, and async context manager support.
- `MultiAgentOrchestrator` compiles a graph with one orchestrator node and dynamic agent nodes.
- `InputValidator` sanitizes request text and validates thread IDs.
- `src/memory_bridge.py` stores workflow results in a memory system with metadata and supports retrieval by query.
- `tests/test_task_queue_deep_trace.py` traces graph state across the workflow rather than only checking a final response.

What to borrow:

- LangGraph reducers for mutable state fields such as `completed_steps`, `messages`, `task_queue`, and `agent_states`.
- Thread IDs for resumable workflows and trace correlation.
- Optional checkpoint persistence behind a local-default interface.
- A memory abstraction that can later use vector/graph stores, but starts with AAOP's existing logs.
- Trace-style tests for workflow execution and state persistence.

What to avoid:

- Making Redis, Qdrant, Neo4j, Perplexica, or local LLM services mandatory for core AAOP.
- Broad HTML escaping of all user input before LLM calls. It is useful for web rendering but can distort prompts; AAOP should validate by field and escape only at output/rendering boundaries.
- Hardcoded external paths such as `/home/user/buddy`.

## AAOP Fit Analysis

Current AAOP strengths:

- `aaop/core/routing/router.py` already handles model tiers, fallback chains, and cost estimates.
- `aaop/core/budget/budget_guard.py` gives AAOP a production guardrail missing from many agent demos.
- `aaop/core/orchestration/state_machine.py` already uses LangGraph for versioned agent workflows.
- `aaop/core/orchestration/agent_runner.py` ties together config, prompts, routing, budget, and observability.
- `aaop/configs/registry.yaml` already defines active versions by environment.
- `aaop/agents/*/v*/agent.yaml` already gives agents a stable versioned packaging format.

Main gaps these repos expose:

- No first-class capability registry yet.
- Workflow state is a `TypedDict`; important state contracts are not validated with Pydantic.
- LangGraph state fields are mostly overwritten rather than intentionally reduced/merged.
- The runner creates a workflow per run and does not expose graph checkpointing or thread IDs.
- Tests focus on lower-level units; there is little graph transition tracing.
- Persistent memory is not modeled yet, even as an optional adapter.

## Recommended Implementation Order

1. Registry and metadata
   - Add `aaop/core/registry.py`.
   - Load `aaop/configs/registry.yaml`.
   - Resolve environment versions.
   - Read each `agent.yaml`.
   - Expose capabilities, business unit, source view, version, and health fields.

2. Typed run models
   - Add `aaop/schemas/run.py`.
   - Model `RunRequest`, `StepResult`, `RunSummary`, and `AgentHealth`.
   - Keep model scope narrow so it does not disrupt existing UI/API code.

3. State reducers and trace tests
   - Update LangGraph state for append/update semantics where AAOP currently mutates lists and dicts.
   - Add tests that prove multi-step workflows preserve completed steps, last outputs, costs, and errors.

4. Optional checkpoint adapter
   - Start with in-memory checkpointing or file-backed logs.
   - Keep Redis as an optional future backend.

5. Optional memory adapter
   - Begin by querying AAOP run logs and eval logs.
   - Later add vector/graph memory only if cross-run retrieval becomes a real product requirement.

## Candidate Tickets

- Add capability metadata to agent.yaml files and expose it in the dashboard.
- Implement `AgentRegistry` with environment-aware version resolution.
- Add Pydantic run/step schemas and validate `AgentRunner.run` inputs/outputs.
- Add LangGraph reducer tests for completed steps and workflow context.
- Add thread ID support for `AgentRunner.run`.
- Add a local run-history retriever that can provide previous run context to agents.
- Add graph trace output to logs for debugging failed workflows.

