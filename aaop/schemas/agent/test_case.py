from typing import Any

from pydantic import BaseModel, Field


class TestCase(BaseModel):
    id: str
    agent: str
    input: dict[str, Any]
    expected_output: Any
    tags: list[str] = []
    difficulty: str = Field(default="medium", pattern=r"^(easy|medium|hard)$")
