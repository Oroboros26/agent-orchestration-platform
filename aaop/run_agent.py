"""
Quick end-to-end test for Phase 3.
Runs legal-qa v1.0.0 against a sample NDA excerpt.

Usage:
    cd aaop
    python run_agent.py
"""
import asyncio
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from dotenv import load_dotenv

load_dotenv(Path(__file__).parent / ".env")

SAMPLE_NDA = """
NON-DISCLOSURE AGREEMENT

1. CONFIDENTIALITY
Both parties agree to keep all shared information strictly confidential
for a period of 5 years from the date of signing.

2. INDEMNIFICATION
Party A shall indemnify and hold harmless Party B from any and all claims,
damages, losses, and expenses without limitation or cap.

3. GOVERNING LAW
This agreement shall be governed by the laws of the State of New York.

4. TERMINATION
Either party may terminate this agreement with 30 days written notice.
"""


async def main():
    from core.orchestration.agent_runner import AgentRunner

    print("\n" + "=" * 60)
    print("  AAOP Phase 3 — End-to-End Agent Run")
    print("=" * 60)

    if not os.getenv("ANTHROPIC_API_KEY"):
        print("\n⚠  No ANTHROPIC_API_KEY found in .env")
        print("   Add your key to aaop/.env and re-run.\n")
        sys.exit(1)

    runner = AgentRunner(base_dir=str(Path(__file__).parent))

    print("\n→ Running: legal-qa v1.0.0")
    print("→ Query:   Analyze this NDA for risk\n")

    result = await runner.run(
        agent_name="legal-qa",
        version="v1.0.0",
        query="Analyze this NDA and identify all material clauses with their risk levels.",
        document_content=SAMPLE_NDA,
    )

    print(f"Run ID   : {result.run_id}")
    print(f"Status   : {result.status}")
    print(f"Duration : {result.duration_seconds}s")
    print(f"Tokens   : {result.total_tokens}")
    print(f"Cost     : ${result.total_cost:.6f}\n")

    print("Steps:")
    for s in result.steps:
        mark = "✓" if s.get("success") else "✗"
        print(
            f"  {mark} {s['step']:<12} "
            f"{s.get('total_tokens', 0):>5} tokens  "
            f"${s.get('cost', 0):.6f}  "
            f"{s.get('duration', 0)}s"
        )

    print("\nOutput:")
    if result.output_parsed:
        print(json.dumps(result.output_parsed, indent=2))
    else:
        print(result.output)

    print("\n" + "=" * 60)
    print("  Phase 3 complete — full workflow executed end-to-end")
    print("=" * 60 + "\n")


if __name__ == "__main__":
    asyncio.run(main())
