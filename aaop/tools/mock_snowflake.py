"""
Mock Snowflake query layer for MVP.

Usage (in code):
    from tools.mock_snowflake import query_view
    context = query_view("finance_summary", filters={"MONTH": "2026-03-01"})

Usage (CLI — preview what the agent will see):
    python tools/mock_snowflake.py --view finance_summary
    python tools/mock_snowflake.py --view finance_summary --month 2026-03-01 --dept Engineering

When real Snowflake is available, replace query_view() with a real connector call.
The rest of the code (api, agent) stays the same.
"""

import argparse
import csv
from pathlib import Path

MOCK_DATA_DIR = Path(__file__).parent.parent / "data" / "mock"
MAX_ROWS = 50  # keep prompt size reasonable


def query_view(
    view_name: str,
    filters: dict[str, str] | None = None,
    max_rows: int = MAX_ROWS,
) -> str:
    """
    Returns a plain-text table of the view's mock data, ready to paste into a prompt.
    filters: optional column=value pairs to narrow the rows (e.g. {"MONTH": "2026-03-01"}).
    """
    csv_path = MOCK_DATA_DIR / f"{view_name}.csv"
    if not csv_path.exists():
        return f"[No mock data found for view '{view_name}'. Create data/mock/{view_name}.csv]"

    with open(csv_path, newline="") as f:
        reader = csv.DictReader(f)
        rows = list(reader)

    if filters:
        for col, val in filters.items():
            rows = [r for r in rows if r.get(col, "").lower() == val.lower()]

    if not rows:
        return f"[No rows match the given filters in '{view_name}']"

    rows = rows[:max_rows]
    headers = list(rows[0].keys())

    col_widths = {h: max(len(h), max(len(r[h]) for r in rows)) for h in headers}

    header_line = "  ".join(h.ljust(col_widths[h]) for h in headers)
    sep_line = "  ".join("-" * col_widths[h] for h in headers)
    data_lines = [
        "  ".join(row[h].ljust(col_widths[h]) for h in headers)
        for row in rows
    ]

    total = len(rows)
    note = f"[Showing {total} row{'s' if total != 1 else ''} from mock view '{view_name}']"
    return "\n".join([note, header_line, sep_line] + data_lines)


def build_agent_context(view_name: str, question: str, filters: dict[str, str] | None = None) -> str:
    """
    Returns the full document_content string to inject into the agent's prompt.
    This is what goes into the `document_content` field of POST /ask.
    """
    data = query_view(view_name, filters)
    return f"## Data from {view_name}\n\n{data}\n\n## Question\n{question}"


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Preview mock Snowflake view data")
    parser.add_argument("--view", required=True, help="View name (e.g. finance_summary)")
    parser.add_argument("--month", help="Filter by MONTH column (e.g. 2026-03-01)")
    parser.add_argument("--dept", help="Filter by DEPARTMENT column")
    parser.add_argument("--category", help="Filter by CATEGORY column")
    args = parser.parse_args()

    filters: dict[str, str] = {}
    if args.month:
        filters["MONTH"] = args.month
    if args.dept:
        filters["DEPARTMENT"] = args.dept
    if args.category:
        filters["CATEGORY"] = args.category

    print(query_view(args.view, filters or None))
