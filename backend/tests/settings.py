from pydantic_settings import SettingsConfigDict

from app.config import Settings


class IsolatedSettings(Settings):
    """Read explicit values and process env without loading a developer's private .env."""

    model_config = SettingsConfigDict(env_file=None)
