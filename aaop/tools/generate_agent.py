"""
Generate an agent definition from a Snowflake semantic view schema.

Usage:
    python tools/generate_agent.py --view finance_summary --unit finance
    python tools/generate_agent.py --view finance_summary --unit finance --snowflake

Without --snowflake, reads from a local mock schema file (safe for MVP / no Snowflake creds).
With --snowflake, queries INFORMATION_SCHEMA from your connected Snowflake account.
"""

import argparse
import json
import os
import sys
from datetime import date
from pathlib import Path

import yaml
from dotenv import load_dotenv

load_dotenv(Path(__file__).parent.parent / ".env")

AGENTS_DIR = Path(__file__).parent.parent / "agents"
MOCK_SCHEMAS_DIR = Path(__file__).parent.parent / "schemas" / "views"


def load_schema_from_snowflake(view_name: str) -> list[dict]:
    try:
        import snowflake.connector
    except ImportError:
        sys.exit("snowflake-connector-python not installed. Run: pip install snowflake-connector-python")

    required = ["SNOWFLAKE_ACCOUNT", "SNOWFLAKE_USER", "SNOWFLAKE_PASSWORD",
                "SNOWFLAKE_DATABASE", "SNOWFLAKE_SCHEMA", "SNOWFLAKE_WAREHOUSE"]
    missing = [k for k in required if not os.getenv(k)]
    if missing:
        sys.exit(f"Missing env vars: {', '.join(missing)}")

    conn = snowflake.connector.connect(
        account=os.environ["SNOWFLAKE_ACCOUNT"],
        user=os.environ["SNOWFLAKE_USER"],
        password=os.environ["SNOWFLAKE_PASSWORD"],
        database=os.environ["SNOWFLAKE_DATABASE"],
        schema=os.environ["SNOWFLAKE_SCHEMA"],
        warehouse=os.environ["SNOWFLAKE_WAREHOUSE"],
    )
    cur = conn.cursor()
    cur.execute(
        """
        SELECT COLUMN_NAME, DATA_TYPE, COMMENT
        FROM INFORMATION_SCHEMA.COLUMNS
        WHERE TABLE_NAME = %s
        ORDER BY ORDINAL_POSITION
        """,
        (view_name.upper(),),
    )
    rows = cur.fetchall()
    conn.close()

    if not rows:
        sys.exit(f"View '{view_name}' not found or has no columns in INFORMATION_SCHEMA.")

    return [{"name": r[0], "type": r[1], "description": r[2] or ""} for r in rows]


def load_schema_from_mock(view_name: str) -> list[dict]:
    mock_path = MOCK_SCHEMAS_DIR / f"{view_name}.json"
    if not mock_path.exists():
        sys.exit(
            f"No mock schema found at {mock_path}.\n"
            f"Create it with columns: [{{'name': ..., 'type': ..., 'description': ...}}]"
        )
    return json.loads(mock_path.read_text())


def build_column_doc(columns: list[dict]) -> str:
    lines = []
    for col in columns:
        desc = f" — {col['description']}" if col.get("description") else ""
        lines.append(f"  - {col['name']} ({col['type']}){desc}")
    return "\n".join(lines)


def generate_agent(view_name: str, business_unit: str, columns: list[dict]) -> Path:
    agent_name = f"{business_unit}-{view_name}".lower().replace("_", "-")
    version = "v1.0.0"
    agent_dir = AGENTS_DIR / agent_name / version
    agent_dir.mkdir(parents=True, exist_ok=True)

    col_doc = build_column_doc(columns)
    col_names = [c["name"] for c in columns]

    agent_yaml = {
        "name": agent_name,
        "version": version,
        "description": (
            f"Answers business questions about the '{view_name}' semantic view "
            f"for the {business_unit} business unit."
        ),
        "model": {
            "tier": "balanced",
            "provider": "auto",
            "temperature": 0.0,
            "max_output_tokens": 1500,
            "max_prompt_tokens": 6000,
            "total_token_budget": 7500,
        },
        "role": (
            f"You are a data analyst for the {business_unit} team. "
            f"You answer questions using data from the '{view_name}' Snowflake semantic view. "
            f"Always be precise, cite column names when relevant, and say 'I don't know' "
            f"if the question cannot be answered from the available data."
        ),
        "goal": (
            f"Answer the user's business question using the columns available in '{view_name}'. "
            f"Return a clear, concise answer. If a calculation is needed, show the formula."
        ),
        "data_source": {
            "type": "snowflake_semantic_view",
            "view": view_name,
            "columns": col_names,
        },
        "workflow": {
            "entry": "analyze",
            "steps": [
                {"id": "analyze", "description": "Interpret the question against the view schema", "next": "draft"},
                {"id": "draft", "description": "Write a clear, data-grounded answer", "next": "END"},
            ],
            "max_iterations": 5,
        },
        "schemas": {
            "input": "schemas/input/business_qa_request.py",
            "output": "schemas/output/business_qa_response.py",
        },
        "metadata": {
            "author": "",
            "created": str(date.today()),
            "generated_by": "tools/generate_agent.py",
            "source_view": view_name,
            "business_unit": business_unit,
            "tags": [business_unit, view_name, "semantic-view", "auto-generated"],
        },
    }

    system_prompt = (
        f"You are a data analyst for the {business_unit} team.\n\n"
        f"You have access to the '{view_name}' semantic view with these columns:\n"
        f"{col_doc}\n\n"
        f"Answer questions based only on this data. Be precise and cite column names."
    )

    user_prompt = "{{question}}"

    prompts = {
        "system": system_prompt,
        "user": user_prompt,
    }

    changelog = (
        f"# Changelog — {agent_name}\n\n"
        f"## {version} — {date.today()}\n"
        f"- Auto-generated from Snowflake semantic view `{view_name}`\n"
        f"- Source: `tools/generate_agent.py`\n"
    )

    (agent_dir / "agent.yaml").write_text(yaml.dump(agent_yaml, default_flow_style=False, allow_unicode=True))
    (agent_dir / "prompts.json").write_text(json.dumps(prompts, indent=2))
    (agent_dir / "CHANGELOG.md").write_text(changelog)

    return agent_dir


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate an AAOP agent from a Snowflake semantic view")
    parser.add_argument("--view", required=True, help="Semantic view name (e.g. finance_summary)")
    parser.add_argument("--unit", required=True, help="Business unit name (e.g. finance)")
    parser.add_argument("--snowflake", action="store_true", help="Query live Snowflake instead of mock schema")
    args = parser.parse_args()

    print(f"\nGenerating agent for view='{args.view}' unit='{args.unit}'")

    if args.snowflake:
        print("Connecting to Snowflake...")
        columns = load_schema_from_snowflake(args.view)
    else:
        print(f"Loading mock schema from schemas/views/{args.view}.json ...")
        columns = load_schema_from_mock(args.view)

    print(f"Found {len(columns)} columns: {[c['name'] for c in columns]}")

    agent_dir = generate_agent(args.view, args.unit, columns)

    print(f"\nAgent created at: {agent_dir}")
    print("Files written:")
    for f in sorted(agent_dir.iterdir()):
        print(f"  {f.name}")
    print("\nNext steps:")
    print(f"  1. Review {agent_dir}/agent.yaml")
    print(f"  2. Review {agent_dir}/prompts.json")
    print("  3. Register it in configs/registry.yaml")


if __name__ == "__main__":
    main()
