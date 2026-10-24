from typing import Literal

from pydantic_settings import SettingsConfigDict

from app.config import Settings


class IsolatedSettings(Settings):
    """Read explicit values and process env without loading a developer's private .env."""

    model_config = SettingsConfigDict(env_file=None)
    # Unit/API fixtures explicitly select the independent fake/Playwright path.
    agent_driver: Literal["playwright", "pinchtab"] = "playwright"
