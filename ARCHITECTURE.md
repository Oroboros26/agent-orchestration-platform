# AAOP — Architecture Overview

## What We Built

A platform where business users ask questions in plain English, and AI agents answer using real business data. Engineers control every agent, every version, and every prompt — as code. New business units get an agent in minutes by creating a schema + CSV and running one command.

**Current state:** 4 agents in production, eval runner, A/B versioning, registry with environment pinning.

---

## The Big Picture

```
                          BUSINESS USERS
              ┌─────────────────────────────────────────────┐
              │  Finance team   Sales team   HR team   Legal │
              │  "Over budget?" "Top deals?" "Attrition?" "NDA risk?"
              └──────────────────────┬──────────────────────┘
                                     │  picks agent + version from sidebar
                                     ▼
┌────────────────────────────────────────────────────────────────────┐
│                        STREAMLIT UI   (ui/app.py)                  │
│                                                                     │
│  ┌──────────────────┐  ┌─────────────────┐  ┌───────────────────┐ │
│  │   Ask a Question │  │   Rate Answer   │  │ Engineer Dashboard│ │
│  │                  │  │                 │  │                   │ │
│  │  Select agent ▼  │  │  👍  Good       │  │ All interactions  │ │
│  │  finance (v1.0)  │  │  👎  Bad        │  │ Tokens / Cost     │ │
│  │  finance (v1.1)  │  │                 │  │ Satisfaction %    │ │
│  │  sales   (v1.0)  │  │  Saved to DB    │  │ Per-agent stats   │ │
│  │  hr      (v1.0)  │  │                 │  │                   │ │
│  │  legal   (v1.0)  │  │                 │  │                   │ │
│  └────────┬─────────┘  └────────┬────────┘  └───────────────────┘ │
└───────────┼─────────────────────┼──────────────────────────────────┘
            │ POST /ask           │ POST /feedback
            ▼                    ▼
┌────────────────────────────────────────────────────────────────────┐
│                     FASTAPI BACKEND  (api/app.py)                  │
│                                                                     │
│  /ask  reads agent.yaml                                            │
│    └── data_source = snowflake_semantic_view ?                     │
│              YES → mock_snowflake.query_view(view)  ← inject data  │
│              NO  → use document_content as-is                      │
│    └── AgentRunner.run(agent, version, query, data)                │
│                                                                     │
│  /feedback  → InteractionStore.save_feedback(id, 👍/👎)            │
│  /health    → liveness check                                        │
└────────────────────┬───────────────────────────────────────────────┘
                     │
                     ▼
┌────────────────────────────────────────────────────────────────────┐
│                    AGENT REGISTRY  (agents/ folder)                │
│              Controlled by configs/registry.yaml                   │
│                                                                     │
│  ┌──────────────────────────┐  ┌──────────────────────────────┐   │
│  │  finance-finance-summary │  │  sales-sales-pipeline        │   │
│  │  ├── v1.0.0/  ← dev/stg  │  │  └── v1.0.0/  ← dev/stg     │   │
│  │  └── v1.1.0/  ← dev only │  │      AUTO-GENERATED          │   │
│  │      IMPROVED PROMPT     │  │      from semantic view      │   │
│  │      3-part answer rule  │  │                              │   │
│  │      flag >10% overrun   │  └──────────────────────────────┘   │
│  └──────────────────────────┘                                      │
│                                                                     │
│  ┌──────────────────────────┐  ┌──────────────────────────────┐   │
│  │  hr-hr-headcount         │  │  legal-qa                    │   │
│  │  └── v1.0.0/  ← dev/stg  │  │  └── v1.0.0/  ← dev only    │   │
│  │      AUTO-GENERATED      │  │      HANDCRAFTED             │   │
│  │      headcount/attrition │  │      document analysis       │   │
│  └──────────────────────────┘  └──────────────────────────────┘   │
│                                                                     │
│  Versions are IMMUTABLE. New prompt = new version folder.          │
│  registry.yaml pins which version is active per environment.       │
└────────────────────┬───────────────────────────────────────────────┘
                     │  agent.yaml + prompts.json loaded into state
                     ▼
┌────────────────────────────────────────────────────────────────────┐
│              STATE MACHINE  (core/orchestration/state_machine.py)  │
│              Generic — same engine for ALL agents                  │
│                                                                     │
│  Each agent defines its OWN steps in agent.yaml.                   │
│  The machine just runs them in order.                              │
│                                                                     │
│  finance / sales / hr  (2-step workflow):                          │
│  ┌──────────┐     ┌──────────┐                                     │
│  │ analyze  │────►│  draft   │────► output                         │
│  │          │     │          │                                     │
│  │ read the │     │ write    │                                     │
│  │ data +   │     │ the      │                                     │
│  │ question │     │ answer   │                                     │
│  └──────────┘     └──────────┘                                     │
│                                                                     │
│  legal-qa  (3-step workflow):                                       │
│  ┌──────────┐     ┌──────────┐     ┌──────────┐                   │
│  │ research │────►│ analyze  │────►│  draft   │────► output        │
│  │          │     │          │     │          │                    │
│  │ read doc │     │ extract  │     │ format   │                    │
│  │ sections │     │ clauses  │     │ as JSON  │                    │
│  └──────────┘     └──────────┘     └──────────┘                   │
│                                                                     │
│  Each step:                                                         │
│    1. Build prompt from agent's prompts.json + previous output     │
│    2. BudgetGuard.check()  ← abort if cost limit hit               │
│    3. ModelRouter.route()  ← call the LLM                          │
│    4. RunTracker.log_step() ← record tokens, cost, latency         │
│    5. Pass output to next step                                      │
└────────────────────┬───────────────────────────────────────────────┘
                     │
          ┌──────────┴──────────┐
          ▼                     ▼
┌──────────────────┐   ┌─────────────────────────────────────────────┐
│   ModelRouter    │   │               LLM PROVIDERS                 │
│  (router.py)     │   │                                             │
│                  │   │  FAST tier        BALANCED tier             │
│  tier: fast   ───┼──►│  groq/            groq/                     │
│  tier: balanced──┼──►│  llama-3.1-8b     llama-3.3-70b ← primary  │
│  tier: powerful──┼──►│  (free)           (free)                    │
│                  │   │                                             │
│  tries model 1   │   │  If Groq fails → fallback:                 │
│  if fails →      │   │  claude-sonnet-4-6  (Anthropic, paid)      │
│  tries model 2   │   │  claude-opus-4-7    (Anthropic, paid)      │
│  if fails →      │   │                                             │
│  raises error    │   │  Zero code changes to switch models.        │
│                  │   │  Edit configs/models/models.yaml only.      │
└──────────────────┘   └─────────────────────────────────────────────┘
          │
          ▼
┌────────────────────────────────────────────────────────────────────┐
│                      STORAGE LAYER                                  │
│                                                                     │
│  ┌──────────────────────────────┐  ┌───────────────────────────┐  │
│  │  SQLite  (MVP)               │  │  Run Logs  (JSON files)   │  │
│  │  db/interactions.db          │  │  logs/runs/*.json         │  │
│  │                              │  │                           │  │
│  │  every interaction saved:    │  │  every step logged:       │  │
│  │  question, answer, tokens,   │  │  model used, tokens,      │  │
│  │  cost, feedback 👍👎          │  │  cost, latency, success   │  │
│  │                              │  │                           │  │
│  │  → swap to Snowflake table   │  │  → feeds dashboard        │  │
│  │    with one config change    │  │    and RLHF loop          │  │
│  └──────────────────────────────┘  └───────────────────────────┘  │
└────────────────────────────────────────────────────────────────────┘
```

---

## Data Flow — One Question, Start to Finish

```
User types:  "Which department is most over budget in March 2026?"
    selects:  finance-finance-summary  v1.1.0
                │
                ▼
        Streamlit UI  →  POST /ask  {question, agent, version}
                │
                ▼
        api/app.py reads agents/finance-finance-summary/v1.1.0/agent.yaml
                │
                │  data_source.type = snowflake_semantic_view ?
                │         YES
                ▼
        mock_snowflake.query_view("finance_summary")
        reads data/mock/finance_summary.csv → formats as table
                │
                ▼
        document_content = "Data from finance_summary\n
                            MONTH  DEPT  BUDGET  ACTUALS  VARIANCE ...
                            2026-03  Engineering  120000  134500  -14500 ..."
                │
                ▼
        AgentRunner.run(agent="finance-finance-summary", version="v1.1.0", ...)
                │
                ├── loads prompts.json  →  system_prompt = "You are a senior financial analyst..."
                ├── loads agent.yaml   →  workflow_steps = [analyze, draft]
                │
                ▼
        LangGraph State Machine
                │
                ├── step: analyze
                │     system: "You are a senior financial analyst...
                │              Flag any dept > 10% over budget."
                │     user:   "[data table] \n\n Question: Which dept is most over budget?"
                │     LLM:    "Engineering is over budget by $14,500 (-12.08%) — flag: >10%"
                │
                └── step: draft
                      system: "...Current task: Write a structured answer"
                      user:   "[data table] \n\n Previous analysis: Engineering is over..."
                      LLM:    "(1) Engineering is the most over-budget department in March 2026.
                               (2) Actuals: $134,500 vs Budget: $120,000 → -$14,500 (-12.08%).
                               (3) Recommendation: Review Engineering personnel spend this quarter."
                │
                ▼
        RunTracker logs: tokens=1240, cost=$0.000731, duration=2.1s
                │
                ▼
        InteractionStore.save_interaction() → SQLite
                │
                ▼
        Streamlit displays the answer
                │
                ▼
        User clicks 👍 → POST /feedback → SQLite
```

---

## Agent Versioning & Promotion Flow

```
Engineer wants to improve the Finance agent prompt
                │
                ▼
  Create agents/finance-finance-summary/v1.1.0/
    agent.yaml    ← new role, goal, structured answer rules
    prompts.json  ← improved system prompt
    CHANGELOG.md  ← what changed and why
  (v1.0.0 folder is NEVER touched — immutable)
                │
                ▼
  Run eval runner to score both versions:
    python tools/testing/eval_runner.py \
      --compare finance-finance-summary v1.0.0 v1.1.0

  Output:
    finance-finance-summary  v1.0.0  →  PASS  72%
    finance-finance-summary  v1.1.0  →  PASS  91%
    Recommendation: promote v1.1.0 to staging
                │
                ▼
  Update configs/registry.yaml:
    finance-finance-summary:
      dev: v1.1.0       ← was v1.0.0
      staging: v1.1.0   ← was v1.0.0
      prod: null        ← promote after staging sign-off
                │
                ▼
  Business owner tests in staging, approves
                │
                ▼
  Set prod: v1.1.0 in registry.yaml
  Fast-forward merge to production branch
  Deploy (GitLab CI → Docker → AKS)
```

---

## Eval Runner — Quality Gate

```
evals/
└── test_cases/
    ├── finance-finance-summary/golden.json   ← 5 Q&A pairs with must_contain / must_not_contain
    ├── sales-sales-pipeline/golden.json      ← 5 Q&A pairs
    └── hr-hr-headcount/golden.json           ← 5 Q&A pairs

Scoring per test case:
  +1 point  each must_contain term found in the answer
  -1 point  each must_not_contain term found
  Score = hit_points / max_points  (clamped 0→1)
  Pass threshold: mean score >= 0.80

Commands:
  python tools/testing/eval_runner.py --agent finance-finance-summary --version v1.1.0
  python tools/testing/eval_runner.py --all
  python tools/testing/eval_runner.py --compare finance-finance-summary v1.0.0 v1.1.0

Output (compare mode):
  ============================================================
    COMPARISON: finance-finance-summary
    v1.0.0 vs v1.1.0
  ============================================================
    Mean score:  v1.0.0 = 72%  |  v1.1.0 = 91%  (+19%)
    Cost:        v1.0.0 = $0.0037  |  v1.1.0 = $0.0041
    Tokens:      v1.0.0 = 6240    |  v1.1.0 = 6890

    Per-case breakdown:
      fin-001:  80% → 100%  (↑+20%)
      fin-002:  60% → 80%   (↑+20%)
      ...
    Recommendation: promote v1.1.0 to staging
```

---

## How a New Business Unit Gets an Agent

```
Engineer creates a semantic view in Snowflake
              │
              ▼
Create mock schema for MVP:
  schemas/views/sales_pipeline.json
  [{"name": "MONTH", "type": "DATE", ...}, ...]
              │
              ▼
Create mock data:
  data/mock/sales_pipeline.csv
              │
              ▼
Run the generator:
  python tools/generate_agent.py --view sales_pipeline --unit sales
              │
              ▼
Register it:
  configs/registry.yaml → sales-sales-pipeline: dev: v1.0.0
              │
              ▼
Agent appears automatically in Streamlit sidebar:
  "sales-sales-pipeline (v1.0.0)"
              │
              ▼
Run evals to set the quality baseline:
  python tools/testing/eval_runner.py --agent sales-sales-pipeline --version v1.0.0
              │
              ▼
Business user asks questions → agent answers from the view data
              │
              ▼
When real Snowflake is ready:
  python tools/generate_agent.py --view sales_pipeline --unit sales --snowflake
  (same agent, real data — zero other changes)
```

---

## Agent-as-Code Structure

```
aaop/agents/
│
├── finance-finance-summary/
│   ├── v1.0.0/                  ← auto-generated, IMMUTABLE
│   │   ├── agent.yaml
│   │   ├── prompts.json
│   │   └── CHANGELOG.md
│   └── v1.1.0/                  ← hand-improved, IMMUTABLE
│       ├── agent.yaml           ← better role + structured answer goal
│       ├── prompts.json         ← rules: flag >10%, cite numbers, 3-part answer
│       └── CHANGELOG.md
│
├── sales-sales-pipeline/
│   └── v1.0.0/                  ← auto-generated
│
├── hr-hr-headcount/
│   └── v1.0.0/                  ← auto-generated
│
└── legal-qa/
    └── v1.0.0/                  ← handcrafted, 3-step workflow


agent.yaml (what controls the agent)
─────────────────────────────────────
name: finance-finance-summary
version: v1.1.0
model:
  tier: balanced          ← which model tier (resolves via models.yaml)
  temperature: 0.0        ← deterministic for data questions
workflow:
  entry: analyze          ← first step
  steps:
    - id: analyze         ← step 1: understand the question + data
      next: draft
    - id: draft           ← step 2: write the final answer
      next: END
data_source:
  type: snowflake_semantic_view
  view: finance_summary   ← tells the API which data to inject


prompts.json (what the LLM reads)
──────────────────────────────────
{
  "system": "You are a senior financial analyst for the finance team.
             You have access to 'finance_summary' with columns: MONTH, DEPARTMENT,
             BUDGET_USD, ACTUALS_USD, VARIANCE_USD, VARIANCE_PCT ...
             Rules: always quantify findings. Flag VARIANCE_PCT < -10%.
             Structure: (1) direct answer, (2) numbers, (3) recommendation.",
  "user": "{{question}}"
}
```

---

## Registry — Environment Pinning

```
configs/registry.yaml

agents:
  finance-finance-summary:
    dev:     v1.1.0     ← latest version under development
    staging: v1.0.0     ← stable, validated by evals
    prod:    null       ← not yet promoted

  sales-sales-pipeline:
    dev:     v1.0.0
    staging: v1.0.0
    prod:    null

  hr-hr-headcount:
    dev:     v1.0.0
    staging: v1.0.0
    prod:    null

  legal-qa:
    dev:     v1.0.0
    staging: null
    prod:    null

Promotion checklist:
  [ ] Eval runner passes (mean score >= 0.80)
  [ ] Business owner signs off in staging
  [ ] CHANGELOG.md updated
  [ ] PR reviewed, fast-forward merge to production branch
```

---

## Upgrade Path (MVP → Production)

```
TODAY (MVP)                          PRODUCTION
───────────────────────────────      ──────────────────────────────────
Streamlit local                 →    Streamlit in Snowflake
SQLite (interactions.db)        →    Snowflake table AAOP_INTERACTIONS
Mock CSV data                   →    Real Snowflake semantic views
Manual registry update          →    GitHub Action on view schema merge
Groq free tier                  →    Groq + Anthropic + Snowflake Cortex
GitHub Actions CI               →    GitLab CI → Docker → AKS
Manual smoke test               →    Eval runner in CI gate (blocks deploy if < 0.80)


What does NOT change:
  - agent.yaml structure
  - prompts.json format
  - The versioning pattern (immutable folders)
  - The state machine
  - The ModelRouter
  - The BudgetGuard
  - The eval runner scoring logic
  - The API contract (POST /ask, POST /feedback)
  - The Streamlit screens
```

---

## File Map

```
aaop/
├── agents/                         ← every agent, every version (immutable folders)
│   ├── finance-finance-summary/
│   │   ├── v1.0.0/
│   │   └── v1.1.0/
│   ├── sales-sales-pipeline/v1.0.0/
│   ├── hr-hr-headcount/v1.0.0/
│   └── legal-qa/v1.0.0/
│
├── api/app.py                      ← FastAPI: /ask /feedback /health
├── ui/app.py                       ← Streamlit: Ask / Rate / Dashboard
│
├── core/
│   ├── orchestration/
│   │   ├── agent_runner.py         ← loads agent, runs workflow, returns RunResult
│   │   └── state_machine.py        ← generic LangGraph workflow (reads from agent.yaml)
│   ├── routing/
│   │   ├── router.py               ← litellm wrapper, model fallback chain
│   │   └── ab_router.py            ← deterministic A/B traffic split between versions
│   ├── budget/budget_guard.py      ← cost check before every LLM call
│   └── observability/tracker.py    ← per-step JSON logging
│
├── configs/
│   ├── models/models.yaml          ← model tiers, pricing (Groq primary, Anthropic fallback)
│   ├── environments/               ← spend caps per environment (dev/staging/prod)
│   └── registry.yaml              ← which version of each agent is live per environment
│
├── data/mock/                      ← CSV files standing in for Snowflake semantic views
│   ├── finance_summary.csv
│   ├── sales_pipeline.csv
│   └── hr_headcount.csv
│
├── db/store.py                     ← SQLite interaction store (Snowflake-ready interface)
├── schemas/views/                  ← JSON column definitions per semantic view
│
├── evals/
│   └── test_cases/
│       ├── finance-finance-summary/golden.json   ← 5 Q&A test cases
│       ├── sales-sales-pipeline/golden.json
│       └── hr-hr-headcount/golden.json
│
└── tools/
    ├── generate_agent.py           ← semantic view schema → agent files (the key script)
    ├── mock_snowflake.py           ← reads CSV, formats as table for prompt injection
    └── testing/
        ├── eval_runner.py          ← scores agents against golden dataset
        └── smoke_test.py           ← live end-to-end test (requires GROQ_API_KEY)
```
