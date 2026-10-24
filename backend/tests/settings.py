from typing import Literal

from pydantic_settings import SettingsConfigDict

from app.config import Settings


class IsolatedSettings(Settings):
    """Read explicit values and process env without loading a developer's private .env."""

    model_config = SettingsConfigDict(env_file=None)
    # Unit/API fixtures explicitly select the independent fake/Playwright path.
    agent_driver: Literal["playwright", "pinchtab"] = "playwright"
    # Legacy end-to-end fixtures intentionally exercise the loopback demo site and
    # automated forms. These are test-only defaults, never production Settings.
    block_private_network: bool = False
    require_approval_for_submit: bool = False
    require_approval_for_send: bool = False


class PolicySettings(IsolatedSettings):
    """Policy tests retain the secure production defaults, with injected DNS."""

    block_private_network: bool = True
    require_approval_for_submit: bool = True
    require_approval_for_send: bool = True
