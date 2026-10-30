from typing import List, Literal

from pydantic import BaseModel, Field


class Clause(BaseModel):
    clause_type: str
    risk_level: Literal["low", "medium", "high"]
    summary: str = Field(max_length=2_000)
    missing: bool = False


class LegalQAResponse(BaseModel):
    agent: str
    version: str
    clauses: List[Clause]
    overall_risk: Literal["low", "medium", "high"]
    missing_standard_clauses: List[str] = []
    confidence: float = Field(ge=0.0, le=1.0)
    run_id: str
