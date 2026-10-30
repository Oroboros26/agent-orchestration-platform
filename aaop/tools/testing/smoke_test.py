"""
Live smoke test — one question to each data agent, prints the answer.
Requires GROQ_API_KEY in aaop/.env

Usage:
    cd aaop
    python tools/testing/smoke_test.py
"""

import asyncio
import sys
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(BASE_DIR))

from dotenv import load_dotenv

load_dotenv(BASE_DIR / ".env")

from core.orchestration.agent_runner import AgentRunner
from tools.mock_snowflake import build_agent_context

TESTS = [
    {
        "agent": "finance-finance-summary",
        "version": "v1.0.0",
        "question": "Which department is most over budget in March 2026?",
    },
    {
        "agent": "finance-finance-summary",
        "version": "v1.1.0",
        "question": "Which department is most over budget in March 2026?",
    },
    {
        "agent": "sales-sales-pipeline",
        "version": "v1.0.0",
        "question": "Who hit their quota in March 2026?",
    },
    {
        "agent": "hr-hr-headcount",
        "version": "v1.0.0",
        "question": "Which department had attrition in April 2026?",
    },
]


async def main() -> None:
    runner = AgentRunner(base_dir=str(BASE_DIR))

    for test in TESTS:
        agent = test["agent"]
        version = test["version"]
        question = test["question"]

        import yaml
        cfg_path = BASE_DIR / f"agents/{agent}/{version}/agent.yaml"
        document_content = ""
        if cfg_path.exists():
            cfg = yaml.safe_load(cfg_path.read_text())
            ds = cfg.get("data_source", {})
            if ds.get("type") == "snowflake_semantic_view":
                document_content = build_agent_context(ds["view"], question)

        print(f"\n{'─'*60}")
        print(f"  {agent}  {version}")
        print(f"  Q: {question}")
        print(f"{'─'*60}")

        try:
            result = await runner.run(
                agent_name=agent,
                version=version,
                query=question,
                document_content=document_content,
            )
            answer = result.output or "(no output)"
            print(f"  A: {answer[:500]}")
            print(f"  tokens={result.total_tokens}  cost=${result.total_cost:.4f}  "
                  f"status={result.status}  duration={result.duration_seconds:.1f}s")
        except Exception as e:
            print(f"  ERROR: {e}")

    print(f"\n{'─'*60}")
    print("  Smoke test complete")


if __name__ == "__main__":
    asyncio.run(main())
