from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore", case_sensitive=False)

    frontend_origin: str = "http://localhost:5173"
    browser_headless: bool = True
    max_steps: int = Field(default=30, ge=1)
    max_seconds: float = Field(default=300, gt=0)
    max_tokens: int = Field(default=200_000, ge=1)
    use_fakes: bool = True
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"] = "INFO"
