from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore", case_sensitive=False)

    frontend_origin: str = "http://localhost:5173"
    browser_headless: bool = True
    browser_driver: Literal["fake", "playwright"] = "fake"
    viewport_width: int = Field(default=1280, ge=320)
    viewport_height: int = Field(default=720, ge=200)
    device_scale_factor: float = Field(default=1, gt=0, allow_inf_nan=False)
    nav_timeout_ms: int = Field(default=20_000, ge=1)
    action_timeout_ms: int = Field(default=8_000, ge=1)
    max_observed_elements: int = Field(default=150, ge=1)
    max_observed_text_chars: int = Field(default=3000, ge=1)
    slow_mo_ms: float = Field(default=0, ge=0, allow_inf_nan=False)
    max_steps: int = Field(default=30, ge=1)
    max_seconds: float = Field(default=300, gt=0)
    max_tokens: int = Field(default=200_000, ge=1)
    use_fakes: bool = True
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"] = "INFO"
