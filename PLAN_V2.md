# AAOP — Plan Version 2.0
# AI Agent Orchestration Platform — Enterprise Architecture

**Last updated:** 2026-04-24
**Status:** Approved for implementation
**Architect:** SAHBI Mohamed

---

## The Problem We Are Solving

Business users need access to company data insights. Today they either:
1. Ask analysts → slow, expensive human time
2. Query Snowflake directly → expensive compute, no cost control, no guardrails

**The goal:** Give users a natural language interface to their data, with full control over what they access, what it costs, and what quality the answers are.

**The core cost logic:**
```
User asks question
    → Check Snowflake knowledge base first (Cortex Search)
    → If similar answer exists (score > 0.85) → return it instantly (near zero cost)
    → If not → route to LLM based on complexity (cheap model for simple, expensive for complex)
    → Store the new answer in knowledge base for future reuse
    → Result: cost drops over time as knowledge base grows
```

---

## What Was Already Built (MVP — Phase 0)

- Agent-as-folder pattern: `agents/<name>/<version>/agent.yaml + prompts.json + CHANGELOG.md`
- Agent generator from Snowflake schema: `tools/generate_agent.py --snowflake`
- FastAPI backend: `POST /ask`, `POST /feedback`, `GET /health`
- LiteLLM model routing with fallback chains
- LangGraph multi-step workflow (research → analyze → draft)
- Registry-based DEV → UAT → PROD promotion via `configs/registry.yaml`
- GitHub Actions CI: lint + mypy + pytest + validate_agents gates
- Streamlit Cloud demo (3 environments): proved the concept, shown to stakeholders
- Budget guard: hourly spend limits per environment
- Run tracker: per-step cost/token logging

**What the MVP proved:** The agent-as-code pattern works. Deployment pipeline works. The architecture is correct. Streamlit Cloud is not the production UI.

**Current direction update (2026-04-24):**
- CI/CD planning is now standardized around **GitHub Actions**, not GitLab includes
- The target GitHub pipeline is modular and stage-based:
  `validate-changelog-format → lint → qa → build → compare-catalog → export-artifacts → generate-release-notes`
- `build-docker` is intentionally excluded from the current GitHub workflow design
- The Streamlit UI is scheduled for a visual redesign: professional light/dark theming, stronger hierarchy, and subtle motion

---

## Target Architecture

```
┌─────────────────────────────────────────────────────────┐
│                    AZURE AD (SSO)                        │
│              Handles all authentication                   │
└────────────────────────┬────────────────────────────────┘
                         │
┌────────────────────────▼────────────────────────────────┐
│           STREAMLIT IN SNOWFLAKE (UI)                    │
│   - Hosted by Snowflake, zero external infra             │
│   - Auth via Azure AD (already integrated in Snowflake)  │
│   - RBAC via Snowflake roles → agent visibility          │
│   - No white flash, no cold start, no free tier limits   │
└────────────────────────┬────────────────────────────────┘
                         │ HTTP
┌────────────────────────▼────────────────────────────────┐
│        FASTAPI — AZURE CONTAINER APPS                    │
│   - Agent orchestration (already built)                  │
│   - /ask  /feedback  /health  /admin                     │
│   - Auto-scaling, managed by Azure                       │
│   - Behind Azure AD auth middleware                      │
└──────┬──────────────────────┬──────────────────────────┘
       │                      │
┌──────▼──────┐    ┌──────────▼──────────────────────────┐
│  AZURE      │    │         SNOWFLAKE                    │
│  OPENAI     │    │  - Semantic views (real data)        │
│             │    │  - AAOP_INTERACTIONS table           │
│  gpt-4o     │    │  - AAOP_KNOWLEDGE_BASE table         │
│  gpt-4o-mini│    │  - Cortex Search (semantic lookup)   │
│  (routing   │    │  - Snowflake Tasks (batch sync)      │
│   by cost)  │    └─────────────────────────────────────┘
└─────────────┘
```

---

## Phases

---

### PHASE 1 — Real Snowflake Data
**Duration:** 2–3 sessions
**Goal:** Agents answer from real company data, not mock CSVs
**Blocking:** Everything else depends on this

**What gets built:**
- Snowflake connector in `core/data/snowflake_client.py`
- Connection pool (max 10 concurrent, reuse across requests)
- `generate_agent.py --snowflake` reads from `INFORMATION_SCHEMA` (already coded, needs credentials)
- Replace `build_agent_context()` with live Snowflake query at runtime
- `configs/environments/prod.yaml` gets Snowflake connection settings
- Start with 3 agents on real data: finance, sales, HR

**Definition of done:**
- Business user asks "Which department is over budget this month?" → answer comes from real Snowflake data
- Query cost logged per run
- No mock CSV involved

**What does NOT change:** Agent folders, registry, CI pipeline, FastAPI API surface

---

### PHASE 2 — Knowledge Base + Cost Control
**Duration:** 2 sessions
**Goal:** Reuse answers, cut LLM costs over time
**Blocking:** Phase 1 must be complete

**What gets built:**

**Snowflake tables:**
```sql
CREATE TABLE AAOP.CORE.AAOP_INTERACTIONS (
    ID VARCHAR,
    AGENT_NAME VARCHAR,
    AGENT_VERSION VARCHAR,
    USER_ROLE VARCHAR,
    QUESTION VARCHAR,
    ANSWER VARCHAR,
    MODEL_USED VARCHAR,
    TOKENS_USED INTEGER,
    COST_USD FLOAT,
    FEEDBACK INTEGER,  -- 1, -1, null
    CREATED_AT TIMESTAMP
);

CREATE TABLE AAOP.CORE.AAOP_KNOWLEDGE_BASE (
    ID VARCHAR,
    AGENT_NAME VARCHAR,
    QUESTION VARCHAR,
    ANSWER VARCHAR,
    EMBEDDING VECTOR(FLOAT, 768),  -- Cortex embed
    CONFIDENCE_SCORE FLOAT,
    USE_COUNT INTEGER,
    LAST_USED TIMESTAMP,
    CREATED_AT TIMESTAMP
);
```

**3-layer retrieval in FastAPI `/ask`:**
```
1. Embed incoming question (Cortex embed_text)
2. Search AAOP_KNOWLEDGE_BASE (cosine similarity > 0.85 = cache hit)
   → Cache hit: return answer instantly, log 0 tokens used
3. Cache miss: query Snowflake semantic view for context
4. Route to Azure OpenAI based on complexity score
5. Store answer in AAOP_KNOWLEDGE_BASE for future reuse
6. Store full interaction in AAOP_INTERACTIONS
```

**Complexity routing:**
```python
# complexity_score 1-10 based on question length, keywords, domain
if complexity_score < 3:   model = "gpt-4o-mini"   # $0.15/1M tokens
elif complexity_score < 7: model = "gpt-4o"         # $2.50/1M tokens
else:                      model = "gpt-4o"          # with larger context
```

**Definition of done:**
- Second identical question costs $0.00 (served from knowledge base)
- Cache hit rate visible in engineer dashboard
- Cost per agent per day queryable from Snowflake

---

### PHASE 3 — Streamlit in Snowflake (Production UI)
**Duration:** 1–2 sessions
**Goal:** Replace Streamlit Cloud with SiS — no cold start, no white flash, auth handled
**Blocking:** Phase 1 (needs real Snowflake connection)

**What gets built:**
- Port `ui/app.py` to Streamlit in Snowflake
- SiS calls FastAPI backend on Azure Container Apps via HTTP
- Snowflake role → agent visibility mapping in registry.yaml:
  ```yaml
  finance-finance-summary:
    allowed_roles: [FINANCE_ANALYST, FINANCE_MANAGER, ADMIN]
    dev: v1.1.0
    uat: v1.0.0
    prod: v1.0.0
  ```
- Sidebar only shows agents the logged-in user's Snowflake role can access
- Interaction log writes to `AAOP_INTERACTIONS` table (Snowflake, not SQLite)

**What disappears:**
- Streamlit Cloud apps (all 3)
- SQLite `db/store.py` (replaced by Snowflake table)
- Cold start problem
- White flash problem
- Free tier limitations

**Definition of done:**
- Finance analyst logs in via Azure AD → sees only finance agents
- Supply chain manager logs in → sees only supply chain agents
- Admin logs in → sees all agents
- No mock data, no SQLite, no Streamlit Cloud

---

### PHASE 4 — FastAPI to Azure Container Apps
**Duration:** 1–2 sessions
**Goal:** Production-grade backend hosting inside Azure tenant
**Blocking:** Phase 1 (needs real config)

**What gets built:**
- `docker/Dockerfile.api` — containerize FastAPI
- `.github/workflows/deploy-dev.yml` — push to ACA dev on PR merge
- `.github/workflows/deploy-uat.yml` — push to ACA UAT on main merge
- `.github/workflows/deploy-prod.yml` — push to ACA prod on release PR merge
- Azure AD middleware on `/ask` endpoint — validates user token
- Environment config via Azure Key Vault (replaces `.env` file)
- Health check endpoint wired to ACA liveness probe

**ACA configuration:**
```
Dev:  1 replica, 0.5 vCPU, 1GB RAM, scale to 0 when idle
UAT:  1 replica, 1 vCPU, 2GB RAM
Prod: 2 replicas min, 4 replicas max, auto-scale on requests
```

**Definition of done:**
- `git push` to feature branch → ACA dev environment updated automatically
- Merge to main → ACA UAT updated automatically
- Release PR merge → ACA prod updated, Git tag created
- Zero manual deployments

---

### PHASE 5 — CI/CD Auto-Promotion Pipeline
**Duration:** 1 session
**Goal:** The workflow you described — merge to main auto-promotes to UAT, weekly release to PROD
**Blocking:** Phase 4 (needs ACA deployment)

**GitHub Actions structure:**
```
.github/workflows/
  ci.yml
  reusable-validate-changelog.yml
  reusable-lint.yml
  reusable-qa.yml
  reusable-build.yml
  reusable-compare-catalog.yml
  reusable-export-artifacts.yml
  reusable-generate-release-notes.yml
```

**Pipeline stages:**
```
validate-changelog-format
lint
qa
build
compare-catalog
export-artifacts
generate-release-notes
```

`build-docker` is intentionally not part of this pipeline plan.

**The weekly release workflow:**
```
Monday–Friday:
  Developer → feature branch → PR → CI green → reviewer approves → merge to main
  → Automatic: ACA UAT updated, agents visible in UAT Streamlit

Friday (or any day chosen):
  Release manager → opens Release PR from main
  → Auto-generated release notes list all changes since last release
  → 2 reviewers approve
  → Merge → ACA prod updated → Git tag created → PROD agents visible
```

**Definition of done:**
- Zero manual deployment steps
- Audit trail: every prod change has a PR, a reviewer, a tag
- Release notes generated automatically from commit messages

---

### PHASE 6 — RBAC + Audit
**Duration:** 1–2 sessions
**Goal:** Full role-based access, complete audit trail
**Blocking:** Phase 3 (needs SiS) and Phase 4 (needs Azure AD middleware)

**What gets built:**
- `allowed_roles` field in `registry.yaml` per agent
- FastAPI middleware: extract Azure AD user role → check against agent's `allowed_roles`
- 403 response if unauthorized: "Your role does not have access to this agent"
- `AAOP_AUDIT_LOG` Snowflake table: who accessed what, when, from which IP
- Snowflake Task: nightly sync of Azure AD roles → Snowflake user table

**Definition of done:**
- Unauthorized user sees no agents they cannot access — not even their names
- Audit log queryable by security team from Snowflake
- Role changes in Azure AD propagate within 24 hours

---

## What We Are NOT Building

| Item | Reason |
|------|--------|
| LangFlow | Nobody needs a visual workflow builder. Agents are code. |
| Custom vector DB (Pinecone, Qdrant) | Snowflake Cortex Search does the same job, zero new infrastructure |
| Kubernetes | Azure Container Apps is managed K8s. We don't operate it. |
| Airflow | Snowflake Tasks replace it for data sync jobs |
| Custom auth system | Azure AD + Snowflake roles handle everything |
| Redis | Snowflake knowledge base replaces the cache layer |
| Prometheus + Grafana | Snowflake has built-in query monitoring. Add later if needed. |

---

## Success Metrics

| Metric | Target | How measured |
|--------|--------|--------------|
| Cache hit rate | > 50% after 30 days | `AAOP_KNOWLEDGE_BASE` use_count / total queries |
| Avg cost per query | < $0.01 | `AAOP_INTERACTIONS.COST_USD` average |
| Avg latency (cache hit) | < 500ms | Logged per interaction |
| Avg latency (LLM call) | < 5s | Logged per interaction |
| DEV → UAT deploy time | < 5 min | GitHub Actions run time |
| DEV → PROD cycle | < 1 week | Release PR cadence |
| Zero unauthorized access | 100% | AAOP_AUDIT_LOG violations = 0 |

---

## What Is Kept From MVP (Nothing Gets Thrown Away)

| MVP Component | Status in V2 |
|---------------|-------------|
| `agents/` folder structure | Unchanged |
| `configs/registry.yaml` | Extended with `allowed_roles` |
| `tools/generate_agent.py` | Unchanged, `--snowflake` flag now works |
| `tools/testing/validate_agents.py` | Unchanged |
| `tools/testing/eval_runner.py` | Unchanged |
| `api/app.py` (FastAPI) | Extended, Dockerized |
| `core/` (router, budget, tracker) | Unchanged |
| GitHub Actions CI | Extended with deploy workflows |
| DEV → UAT → PROD registry pattern | Unchanged |

---

## Phase Dependency Map

```
Phase 1 (Snowflake data)
    ↓
Phase 2 (Knowledge base)    Phase 3 (SiS UI)    Phase 4 (ACA deploy)
                                    ↓                    ↓
                            Phase 5 (CI/CD auto-promotion)
                                    ↓
                            Phase 6 (RBAC + Audit)
```

Phase 2, 3, and 4 can be worked in parallel once Phase 1 is done.

---

## Open Questions (Need Answers Before Phase 3)

1. Which Snowflake account and database will AAOP use?
2. What is the Azure Container Apps resource group and subscription?
3. Which Azure AD app registration will be used for auth?
4. What Snowflake roles exist today that map to business units?
5. Is Azure OpenAI already provisioned, or does it need to be requested?
