"""Entry point: python -m aaop run <agent> <version> --query '...'"""
import asyncio
import json
import sys
from pathlib import Path

# ensure aaop/ is on the path when run as a module
sys.path.insert(0, str(Path(__file__).parent))

from dotenv import load_dotenv

load_dotenv(Path(__file__).parent / ".env")

import click
from rich.console import Console
from rich.table import Table

console = Console()


@click.group()
def cli() -> None:
    """AAOP — AI Agent Orchestration Platform"""


@cli.command()
@click.argument("agent")
@click.argument("version")
@click.option("--query", "-q", required=True, help="Query to send to the agent")
@click.option("--doc", "-d", default="", help="Document content to analyze")
@click.option("--json-output", is_flag=True, help="Print raw JSON output only")
def run(agent: str, version: str, query: str, doc: str, json_output: bool) -> None:
    """Run an agent: aaop run legal-qa v1.0.0 --query '...'"""
    from core.orchestration.agent_runner import AgentRunner, RunResult

    async def _run() -> RunResult:
        runner = AgentRunner(base_dir=str(Path(__file__).parent))
        return await runner.run(
            agent_name=agent,
            version=version,
            query=query,
            document_content=doc,
        )

    result = asyncio.run(_run())

    if json_output:
        click.echo(json.dumps({
            "run_id": result.run_id,
            "status": result.status,
            "output": result.output_parsed or result.output,
            "total_tokens": result.total_tokens,
            "total_cost": result.total_cost,
            "duration": result.duration_seconds,
        }, indent=2))
        return

    # pretty output
    console.print(f"\n[bold cyan]Run: {result.agent} / {result.version} / {result.run_id}[/]")
    console.print(f"Status: [{'green' if result.status == 'completed' else 'red'}]{result.status}[/]")

    table = Table(show_header=True, header_style="bold")
    table.add_column("Step")
    table.add_column("Model")
    table.add_column("Tokens")
    table.add_column("Cost")
    table.add_column("Duration")
    table.add_column("OK")

    for s in result.steps:
        table.add_row(
            s["step"],
            s.get("model", "—")[:30],
            str(s.get("total_tokens", 0)),
            f"${s.get('cost', 0):.6f}",
            f"{s.get('duration', 0)}s",
            "✓" if s.get("success") else "✗",
        )
    console.print(table)
    console.print(f"\nTotal tokens: {result.total_tokens} | Cost: ${result.total_cost:.6f} | Duration: {result.duration_seconds}s\n")

    if result.output_parsed:
        console.print("[bold]Output:[/]")
        console.print_json(json.dumps(result.output_parsed, indent=2))
    else:
        console.print(f"[bold]Output:[/]\n{result.output}")


@cli.command()
@click.argument("agent")
def versions(agent: str) -> None:
    """List all versions of an agent."""
    base = Path(__file__).parent / "agents" / agent
    if not base.exists():
        click.echo(f"Agent '{agent}' not found.")
        return
    for v in sorted(base.iterdir()):
        if v.is_dir():
            click.echo(v.name)


if __name__ == "__main__":
    cli()
