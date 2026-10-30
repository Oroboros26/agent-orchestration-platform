# Changelog — finance-finance-summary

## v1.1.0 — 2026-04-24

### Changed
- Role upgraded from "data analyst" to "senior financial analyst" — more precise framing
- Goal now enforces 3-part answer structure: direct answer → numbers → recommendation
- System prompt adds explicit rules: flag >10% over budget, always quantify, compare months for trends
- Goal explicitly says: never deflect with "I don't have enough data" if the answer can be inferred

### Why this version
v1.0.0 returned plain paragraph answers. v1.1.0 enforces structured output — easier for stakeholders to scan and act on. Tested against the golden dataset before promoting to staging.

## v1.0.0 — 2026-04-24

- Initial auto-generated agent from `tools/generate_agent.py`
- Balanced tier, deterministic (temperature 0.0), 2-step workflow: analyze → draft
