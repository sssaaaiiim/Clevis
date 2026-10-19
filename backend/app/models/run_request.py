"""Request schemas for the orchestration API."""

from pydantic import BaseModel, Field


class RunRequest(BaseModel):
    url: str = Field("", description="Starting URL for the agent (optional; inferred when blank)")
    task: str = Field(..., description="High-level task description")
    max_steps: int = Field(10, ge=1, le=50, alias="max_steps", description="Maximum agent steps")
    timeout: int = Field(120, ge=10, le=600, description="Per-request timeout in seconds")
    headless: bool = Field(True, description="Run browser in headless mode")

    model_config = {"populate_by_name": True}
