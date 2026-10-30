# Contributing to AAOP

This document describes the full development cycle for this platform — from branching to production deploy. It applies to everyone adding a new data source, improving an agent prompt, or changing the core engine.

---

## Branches

| Branch       | Environment | Deploy method          |
|-------------|-------------|------------------------|
| `main`       | Staging (UAT) | Auto on merge to main  |
| `production` | Production    | Manual, fast-forward only, no squash |

Feature branches are always cut from `main` and merged back into `main` via PR.

---

## Scenario 1 — Adding a new data source + agent

This is the most common task. A new semantic view exists in Snowflake (or is planned) and you need to build an agent for it.

### Step 1 — Branch

```bash
git checkout main
git pull origin main
git checkout -b feature/add-<unit>-agent
```

### Step 2 — Create the mock schema

```bash
# Create schemas/views/<view>.json
# Each entry: {"name": "COLUMN_NAME", "type": "VARCHAR", "description": "..."}
```

Minimum 8 columns. Match the real Snowflake view schema as closely as possible — this becomes the agent's knowledge of what data it has access to.

### Step 3 — Create mock data

```bash
# Create data/mock/<view>.csv
# Minimum: 20 rows, 2 months of data, realistic values
```

The mock data must be representative enough that the agent can answer real business questions. If the data is too sparse or uniform, the agent will give wrong answers in evals.

### Step 4 — Generate the agent

```bash
cd aaop
python tools/generate_agent.py --view <view> --unit <unit>
```

This creates `agents/<unit>-<view>/v1.0.0/` with `agent.yaml`, `prompts.json`, and `CHANGELOG.md`. Review the generated files — the system prompt is auto-built from the schema but you can improve it.

### Step 5 — Write the golden dataset

```bash
# Create evals/test_cases/<agent-name>/golden.json
# Minimum 5 test cases. Each case needs:
#   - "id": unique string
#   - "question": realistic business question
#   - "must_contain": list of strings the answer MUST include
#   - "must_not_contain": list of strings the answer must NOT include
#   - "notes": why this test case matters
```

Write these before running the agent. Think like the business user — what questions would Finance / Sales / HR actually ask?

### Step 6 — Register the agent

```yaml
# configs/registry.yaml — add:
<unit>-<view>:
  description: <one line>
  business_unit: <unit>
  source_view: <view>
  dev: v1.0.0
  staging: null   # promote after PR review
  prod: null
```

### Step 7 — Validate locally

```bash
python tools/testing/validate_agents.py
```

This must pass before you open a PR. It checks every required file exists and is valid.

### Step 8 — Run the eval (local, optional live)

```bash
# Dry structure check (always):
python tools/testing/validate_agents.py

# Live scoring (requires GROQ_API_KEY in .env):
python tools/testing/eval_runner.py --agent <agent-name> --version v1.0.0
```

Note the score. If it's below 80%, improve the prompts before opening the PR.

### Step 9 — Push and open a PR

```bash
git add schemas/views/<view>.json
git add data/mock/<view>.csv
git add agents/<unit>-<view>/
git add evals/test_cases/<unit>-<view>/
git add configs/registry.yaml
git commit -m "feat: add <unit>-<view> agent v1.0.0"
git push origin feature/add-<unit>-agent
```

Open a PR → `main`. Fill in the PR template. CI runs automatically:
- Gate 1: ruff + mypy + pytest
- Gate 2: `validate_agents.py` — blocks merge if any agent has missing files

### Step 10 — After review, merge to main (staging)

Squash merge is fine for feature branches into main.

Business owner tests the new agent in the staging UI. When they approve:

```yaml
# configs/registry.yaml — update:
staging: v1.0.0
```

### Step 11 — Promote to production

```yaml
# configs/registry.yaml — update:
prod: v1.0.0
```

Open a PR → `production`. This must be a fast-forward merge (no squash, no rebase that rewrites commits). After approval, deploy is manual.

---

## Scenario 2 — Improving an agent prompt

When an agent's answers are not good enough — wrong structure, missing numbers, hallucinating — you improve the prompt by creating a **new version**. The old version is never edited.

### Steps

```bash
git checkout -b feat/improve-<agent>-prompt

# Create agents/<agent>/v1.1.0/ (copy v1.0.0 as a starting point)
cp -r agents/<agent>/v1.0.0 agents/<agent>/v1.1.0

# Edit agents/<agent>/v1.1.0/agent.yaml  — improve role, goal, rules
# Edit agents/<agent>/v1.1.0/prompts.json — improve system prompt
# Edit agents/<agent>/v1.1.0/CHANGELOG.md — explain what changed and why

# Compare versions (requires GROQ_API_KEY):
python tools/testing/eval_runner.py --compare <agent> v1.0.0 v1.1.0
```

The comparison output gives a clear recommendation. Include the score diff in the PR.

---

## Scenario 3 — Changing the core engine

Changes to `core/` (state machine, router, budget guard, tracker) affect every agent.

```bash
git checkout -b fix/<description>

# Make the change
# Run full test suite:
pytest tests/unit/ -v
mypy core/
python tools/testing/validate_agents.py

# If GROQ_API_KEY available — run smoke test to confirm no regression:
python tools/testing/smoke_test.py
```

All three must pass before opening a PR. Note the smoke test output in the PR description.

---

## CI gates (run automatically on every PR)

| Gate | What it checks | Blocks merge? |
|------|---------------|---------------|
| ruff | Code style | Yes |
| mypy | Type correctness on `core/` | Yes |
| pytest | Unit tests in `tests/unit/` | Yes |
| validate_agents | All agent files exist and are valid, golden datasets present | Yes |

Live LLM calls (eval_runner, smoke_test) are **not** run in CI — they require a real API key and cost money. Run them locally before opening the PR.

---

## Hard rules (never break these)

- **Never edit an existing version folder.** `v1.0.0` is immutable the moment it is merged. Improvements always go in `v1.1.0`, `v2.0.0`, etc.
- **Never hardcode API keys, model names, or secrets** anywhere in code.
- **Never squash merge into `production`** — fast-forward only.
- **Never push directly to `main` or `production`** — always via PR.
- **Never use `print()` in `core/`** — use `logging`.

---

## Version semantics

| Change | Version bump |
|--------|-------------|
| Prompt wording, temperature | Patch: v1.0.**1** |
| New workflow step, new tool | Minor: v1.**1**.0 |
| Breaking input/output schema | Major: **v2**.0.0 |
