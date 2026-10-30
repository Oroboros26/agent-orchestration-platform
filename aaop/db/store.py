"""
Interaction store — SQLite for MVP, Snowflake-ready interface.

To swap to Snowflake: implement SnowflakeInteractionStore with the same
public methods (save_interaction, save_feedback, get_all, get_stats).
"""

import sqlite3
import uuid
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Optional

DB_PATH = Path(__file__).parent.parent / "db" / "interactions.db"


@dataclass
class Interaction:
    id: str
    agent: str
    version: str
    question: str
    answer: str
    tokens: int
    cost_usd: float
    duration_seconds: float
    status: str
    created_at: str
    feedback: Optional[int] = None  # 1 = thumbs up, -1 = thumbs down, None = not rated


class InteractionStore:
    def __init__(self, db_path: Path = DB_PATH) -> None:
        self.db_path = db_path
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self) -> None:
        with self._connect() as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS interactions (
                    id            TEXT PRIMARY KEY,
                    agent         TEXT NOT NULL,
                    version       TEXT NOT NULL,
                    question      TEXT NOT NULL,
                    answer        TEXT NOT NULL,
                    tokens        INTEGER NOT NULL DEFAULT 0,
                    cost_usd      REAL NOT NULL DEFAULT 0.0,
                    duration_sec  REAL NOT NULL DEFAULT 0.0,
                    status        TEXT NOT NULL DEFAULT 'completed',
                    feedback      INTEGER,
                    created_at    TEXT NOT NULL
                )
            """)

    def save_interaction(
        self,
        agent: str,
        version: str,
        question: str,
        answer: str,
        tokens: int = 0,
        cost_usd: float = 0.0,
        duration_seconds: float = 0.0,
        status: str = "completed",
    ) -> str:
        interaction_id = str(uuid.uuid4())
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO interactions
                    (id, agent, version, question, answer, tokens, cost_usd,
                     duration_sec, status, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    interaction_id, agent, version, question, answer,
                    tokens, cost_usd, duration_seconds, status,
                    datetime.utcnow().isoformat(),
                ),
            )
        return interaction_id

    def save_feedback(self, interaction_id: str, feedback: int) -> bool:
        """feedback: 1 = thumbs up, -1 = thumbs down"""
        with self._connect() as conn:
            cur = conn.execute(
                "UPDATE interactions SET feedback = ? WHERE id = ?",
                (feedback, interaction_id),
            )
        return cur.rowcount > 0

    def get_all(self, limit: int = 200) -> list[Interaction]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT * FROM interactions ORDER BY created_at DESC LIMIT ?",
                (limit,),
            ).fetchall()
        return [self._row_to_interaction(r) for r in rows]

    def get_stats(self) -> dict:
        with self._connect() as conn:
            row = conn.execute("""
                SELECT
                    COUNT(*)                                    AS total,
                    SUM(CASE WHEN feedback = 1  THEN 1 ELSE 0 END) AS thumbs_up,
                    SUM(CASE WHEN feedback = -1 THEN 1 ELSE 0 END) AS thumbs_down,
                    SUM(CASE WHEN feedback IS NULL THEN 1 ELSE 0 END) AS unrated,
                    ROUND(SUM(cost_usd), 6)                    AS total_cost,
                    SUM(tokens)                                AS total_tokens,
                    ROUND(AVG(duration_sec), 2)                AS avg_duration
                FROM interactions
            """).fetchone()
        return dict(row)

    @staticmethod
    def _row_to_interaction(row: sqlite3.Row) -> Interaction:
        return Interaction(
            id=row["id"],
            agent=row["agent"],
            version=row["version"],
            question=row["question"],
            answer=row["answer"],
            tokens=row["tokens"],
            cost_usd=row["cost_usd"],
            duration_seconds=row["duration_sec"],
            status=row["status"],
            created_at=row["created_at"],
            feedback=row["feedback"],
        )
