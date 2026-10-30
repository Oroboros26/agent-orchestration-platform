## What does this PR do?

<!-- One sentence: what changed and why -->

## Type of change

- [ ] New agent / data source
- [ ] Agent prompt improvement (new version)
- [ ] Core engine change (router, state machine, budget guard, etc.)
- [ ] Tooling / infrastructure
- [ ] Bug fix

---

## Checklist — New agent or data source

- [ ] `schemas/views/<view>.json` created
- [ ] `data/mock/<view>.csv` created with realistic data (min 20 rows, 2 months)
- [ ] `python tools/generate_agent.py --view <view> --unit <unit>` run
- [ ] `agents/<name>/v1.0.0/` folder contains `agent.yaml`, `prompts.json`, `CHANGELOG.md`
- [ ] `evals/test_cases/<agent-name>/golden.json` written (min 5 cases)
- [ ] `configs/registry.yaml` updated — agent added with `dev: v1.0.0`
- [ ] `python tools/testing/validate_agents.py` passes locally
- [ ] `python tools/testing/eval_runner.py --agent <name> --version v1.0.0` run and score noted below

**Eval score:** _____ / 5 cases, mean score: _____%

## Checklist — Agent prompt improvement (new version)

- [ ] New version folder created (e.g. `v1.1.0/`) — old version NOT edited
- [ ] `CHANGELOG.md` explains what changed and why
- [ ] `python tools/testing/eval_runner.py --compare <agent> <old> <new>` run
- [ ] New version scores higher or equal on golden dataset

**Comparison result:** v_____ = _____% → v_____ = _____%

## Checklist — Core engine change

- [ ] `pytest tests/unit/ -v` passes
- [ ] `mypy core/` passes
- [ ] `python tools/testing/validate_agents.py` passes
- [ ] Existing agent behaviour unchanged (run smoke test if GROQ_API_KEY available)

---

## Notes for reviewer

<!-- Anything non-obvious: trade-offs made, things not covered, follow-up needed -->
