import pytest
from pydantic import ValidationError

from tests.settings import IsolatedSettings


def test_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("BROWSER_HEADLESS", "false")
    monkeypatch.setenv("MAX_STEPS", "7")
    settings = IsolatedSettings()
    assert settings.browser_headless is False
    assert settings.max_steps == 7
    assert settings.use_fakes is True
    monkeypatch.setenv("MAX_SECONDS", "0")
    with pytest.raises(ValidationError):
        IsolatedSettings()
