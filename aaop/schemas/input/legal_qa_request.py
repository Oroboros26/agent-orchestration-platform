from typing import Optional

from pydantic import BaseModel, Field


class LegalQARequest(BaseModel):
    query: str = Field(max_length=10_000)
    document_content: Optional[str] = Field(default=None, max_length=100_000)
    document_id: Optional[str] = Field(
        default=None, pattern=r"^[a-zA-Z0-9_-]+$"
    )
    agent_version: str = Field(
        default="latest", pattern=r"^(v\d+\.\d+\.\d+|latest)$"
    )
