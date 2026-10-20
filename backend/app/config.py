from typing import Literal

from pydantic import Field, SecretStr
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

    llm_provider: Literal["fake", "openrouter"] = "fake"
    openrouter_api_key: SecretStr = Field(default=SecretStr(""), repr=False)
    openrouter_base_url: str = "https://openrouter.ai/api/v1"
    llm_model_primary: str = ""
    llm_model_fallback: str = ""
    llm_temperature: float = Field(default=0.2, ge=0, le=2)
    llm_max_output_tokens: int = Field(default=800, ge=1)
    llm_request_timeout_s: float = Field(default=60, gt=0, allow_inf_nan=False)
    llm_max_retries: int = Field(default=2, ge=0, le=10)
    max_cost_usd: float = Field(default=0.50, ge=0, allow_inf_nan=False)
    max_history_steps_in_prompt: int = Field(default=8, ge=1)

    screencast_format: Literal["jpeg", "png"] = "jpeg"
    screencast_quality: int = Field(default=85, ge=1, le=100)
    screencast_max_fps: float = Field(default=15, gt=0, le=120, allow_inf_nan=False)
    screencast_every_nth_frame: int = Field(default=1, ge=1)
    screencast_fallback_fps: float = Field(default=2, gt=0, le=30, allow_inf_nan=False)
    preview_idle_resend_s: float = Field(default=1, gt=0, allow_inf_nan=False)
    preview_client_queue: int = Field(default=2, ge=1, le=10)
    preview_auth_timeout_s: float = Field(default=5, gt=0, allow_inf_nan=False)
    preview_retain_after_end_s: float = Field(default=30, ge=0, allow_inf_nan=False)

    takeover_max_seconds: float = Field(default=600, gt=0, allow_inf_nan=False)
    input_max_messages_per_second: int = Field(default=200, ge=1)
    input_max_text_length: int = Field(default=2000, ge=1, le=2000)
    input_max_message_bytes: int = Field(default=8192, ge=128)
    input_idle_timeout_s: float = Field(default=120, gt=0, allow_inf_nan=False)
    max_handoffs: int = Field(default=3, ge=0)

    def validate_llm(self) -> None:
        if self.llm_provider == "openrouter" and (
            not self.openrouter_api_key.get_secret_value().strip()
            or not self.llm_model_primary.strip()
        ):
            raise RuntimeError(
                "LLM_PROVIDER=openrouter requires OPENROUTER_API_KEY and LLM_MODEL_PRIMARY."
            )
