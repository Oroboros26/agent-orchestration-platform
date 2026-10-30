"""
Eval runner — scores agent answers against a golden dataset.

Usage:
    python tools/testing/eval_runner.py --agent finance-finance-summary --version v1.0.0
    python tools/testing/eval_runner.py --agent finance-finance-summary --version v1.1.0
    python tools/testing/eval_runner.py --all                          # run every agent/version with a golden dataset
    python tools/testing/eval_runner.py --compare finance-finance-summary v1.0.0 v1.1.0

Scoring per test case:
    +1 point for each must_contain term found in the answer (case-insensitive)
    -1 point for each must_not_contain term found in the answer
    Score = hit_points / max_points (clamped to [0, 1])

A passing run requires mean score >= 0.8 across all test cases.
"""

import argparse
import asyncio
import json
import sys
import time
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(BASE_DIR))

from core.orchestration.agent_runner import AgentRunner
from tools.mock_snowflake import build_agent_context

PASS_THRESHOLD = 0.8


def _load_golden(agent_name: str) -> list[dict]:
    path = BASE_DIR / f"evals/test_cases/{agent_name}/golden.json"
    if not path.exists():
        return []
    return json.loads(path.read_text())


def _score_answer(answer: str, case: dict) -> tuple[float, dict]:
    answer_lower = answer.lower()

    must_contain = case.get("must_contain", [])
    must_not_contain = case.get("must_not_contain", [])

    hits = [t for t in must_contain if t.lower() in answer_lower]
    violations = [t for t in must_not_contain if t.lower() in answer_lower]

    max_points = len(must_contain) + len(must_not_contain)
    if max_points == 0:
        score = 1.0
    else:
        raw = len(hits) - len(violations)
        score = max(0.0, min(1.0, raw / max(len(must_contain), 1)))

    return score, {
        "hits": hits,
        "violations": violations,
        "missing": [t for t in must_contain if t.lower() not in answer_lower],
    }


async def run_eval(agent_name: str, version: str, runner: AgentRunner) -> dict:
    cases = _load_golden(agent_name)
    if not cases:
        return {"agent": agent_name, "version": version, "error": "no golden dataset found", "score": None}

    results = []
    for case in cases:
        question = case["question"]

        # build data context if the agent uses a semantic view
        agent_yaml_path = BASE_DIR / f"agents/{agent_name}/{version}/agent.yaml"
        document_content = ""
        if agent_yaml_path.exists():
            import yaml
            cfg = yaml.safe_load(agent_yaml_path.read_text())
            ds = cfg.get("data_source", {})
            if ds.get("type") == "snowflake_semantic_view":
                document_content = build_agent_context(ds["view"], question)

        t0 = time.time()
        try:
            result = await runner.run(
                agent_name=agent_name,
                version=version,
                query=question,
                document_content=document_content,
            )
            answer = result.output or ""
            duration = round(time.time() - t0, 2)
            score, detail = _score_answer(answer, case)
            results.append({
                "id": case["id"],
                "question": question,
                "score": score,
                "passed": score >= PASS_THRESHOLD,
                "tokens": result.total_tokens,
                "cost_usd": round(result.total_cost, 6),
                "duration": duration,
                "hits": detail["hits"],
                "violations": detail["violations"],
                "missing": detail["missing"],
                "notes": case.get("notes", ""),
                "answer_preview": answer[:200],
            })
        except Exception as e:
            results.append({
                "id": case["id"],
                "question": question,
                "score": 0.0,
                "passed": False,
                "error": str(e),
            })

    scores = [r["score"] for r in results]
    mean_score = round(sum(scores) / len(scores), 3) if scores else 0.0
    passed = sum(1 for r in results if r.get("passed"))
    total_tokens = sum(r.get("tokens", 0) for r in results)
    total_cost = round(sum(r.get("cost_usd", 0.0) for r in results), 6)

    return {
        "agent": agent_name,
        "version": version,
        "mean_score": mean_score,
        "passed": passed,
        "total": len(results),
        "overall_pass": mean_score >= PASS_THRESHOLD,
        "total_tokens": total_tokens,
        "total_cost_usd": total_cost,
        "cases": results,
    }


def _print_report(report: dict) -> None:
    agent = report["agent"]
    version = report["version"]

    if "error" in report:
        print(f"\n[{agent} {version}] ERROR: {report['error']}")
        return

    status = "PASS" if report["overall_pass"] else "FAIL"
    print(f"\n{'='*60}")
    print(f"  {agent}  {version}  →  {status}")
    print(f"  Score: {report['mean_score']:.0%}  |  "
          f"{report['passed']}/{report['total']} cases passed  |  "
          f"{report['total_tokens']} tokens  |  ${report['total_cost_usd']:.4f}")
    print(f"{'='*60}")

    for case in report["cases"]:
        icon = "✓" if case.get("passed") else "✗"
        score_str = f"{case['score']:.0%}" if isinstance(case.get("score"), float) else "ERR"
        print(f"  {icon} [{case['id']}] {score_str}  {case['question'][:60]}")
        if case.get("missing"):
            print(f"       missing: {case['missing']}")
        if case.get("violations"):
            print(f"       violations: {case['violations']}")
        if case.get("error"):
            print(f"       error: {case['error']}")


def _print_comparison(report_a: dict, report_b: dict) -> None:
    print(f"\n{'='*60}")
    print(f"  COMPARISON: {report_a['agent']}")
    print(f"  {report_a['version']} vs {report_b['version']}")
    print(f"{'='*60}")

    score_a = report_a.get("mean_score", 0)
    score_b = report_b.get("mean_score", 0)
    delta = score_b - score_a
    direction = "+" if delta >= 0 else ""

    print(f"\n  Mean score:  {report_a['version']} = {score_a:.0%}  |  "
          f"{report_b['version']} = {score_b:.0%}  ({direction}{delta:.0%})")
    print(f"  Cost:        {report_a['version']} = ${report_a.get('total_cost_usd', 0):.4f}  |  "
          f"{report_b['version']} = ${report_b.get('total_cost_usd', 0):.4f}")
    print(f"  Tokens:      {report_a['version']} = {report_a.get('total_tokens', 0)}  |  "
          f"{report_b['version']} = {report_b.get('total_tokens', 0)}")

    cases_a = {c["id"]: c for c in report_a.get("cases", [])}
    cases_b = {c["id"]: c for c in report_b.get("cases", [])}

    print("\n  Per-case breakdown:")
    for cid in sorted(set(list(cases_a.keys()) + list(cases_b.keys()))):
        ca = cases_a.get(cid, {})
        cb = cases_b.get(cid, {})
        sa = ca.get("score", 0)
        sb = cb.get("score", 0)
        d = sb - sa
        arrow = "→" if d == 0 else ("↑" if d > 0 else "↓")
        print(f"    {cid}:  {sa:.0%} {arrow} {sb:.0%}  ({'+' if d >= 0 else ''}{d:.0%})")

    winner = report_b["version"] if score_b >= score_a else report_a["version"]
    print(f"\n  Recommendation: promote {winner} to staging\n")


async def main() -> None:
    parser = argparse.ArgumentParser(description="AAOP Eval Runner")
    parser.add_argument("--agent", help="Agent name (e.g. finance-finance-summary)")
    parser.add_argument("--version", default="v1.0.0", help="Agent version")
    parser.add_argument("--all", action="store_true", help="Run all agents with a golden dataset")
    parser.add_argument("--compare", nargs=3, metavar=("AGENT", "VERSION_A", "VERSION_B"),
                        help="Compare two versions of the same agent")

    args = parser.parse_args()

    runner = AgentRunner(base_dir=str(BASE_DIR))

    if args.compare:
        agent_name, ver_a, ver_b = args.compare
        print(f"Comparing {agent_name}: {ver_a} vs {ver_b} ...")
        report_a, report_b = await asyncio.gather(
            run_eval(agent_name, ver_a, runner),
            run_eval(agent_name, ver_b, runner),
        )
        _print_report(report_a)
        _print_report(report_b)
        _print_comparison(report_a, report_b)

    elif args.all:
        evals_dir = BASE_DIR / "evals/test_cases"
        agent_names = [p.name for p in evals_dir.iterdir() if p.is_dir()]
        reports = []
        for agent_name in sorted(agent_names):
            agents_dir = BASE_DIR / "agents" / agent_name
            if not agents_dir.exists():
                continue
            versions = sorted(v.name for v in agents_dir.iterdir() if v.is_dir())
            if not versions:
                continue
            version = versions[-1]  # latest
            print(f"Running {agent_name} {version} ...")
            report = await run_eval(agent_name, version, runner)
            reports.append(report)
            _print_report(report)

        # summary table
        print(f"\n{'='*60}")
        print("  SUMMARY")
        print(f"{'='*60}")
        for r in reports:
            status = "PASS" if r.get("overall_pass") else "FAIL"
            score = f"{r['mean_score']:.0%}" if r.get("mean_score") is not None else "N/A"
            print(f"  {status}  {r['agent']}  {r['version']}  {score}")

    elif args.agent:
        report = await run_eval(args.agent, args.version, runner)
        _print_report(report)
        sys.exit(0 if report.get("overall_pass") else 1)

    else:
        parser.print_help()


if __name__ == "__main__":
    asyncio.run(main())
