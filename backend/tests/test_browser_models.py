import pytest

from app.browser.safety import BrowserFailure, redact_value, validate_url
from app.interfaces.browser import Element, Observation
from tests.settings import IsolatedSettings


@pytest.mark.parametrize(
    "url", ["https://example.test?q=1", "http://localhost:8765/", "about:blank"]
)
def test_allowed_urls(url: str) -> None:
    assert validate_url(url) == url


@pytest.mark.parametrize(
    "url",
    [
        "file:///etc/passwd",
        "chrome://settings",
        "javascript:alert(1)",
        "data:text/html,hi",
        "ftp://host",
        "about:config",
        "http://",
        "https://host:bad",
        "https://host\n/path",
    ],
)
def test_blocked_urls(url: str) -> None:
    with pytest.raises(BrowserFailure) as exc:
        validate_url(url)
    assert exc.value.code == "BLOCKED_URL"


@pytest.mark.parametrize(
    "attribute",
    ["otp", "one-time-code", "auth_token", "secret", "CVV", "cvc", "credit-card", "ssn"],
)
def test_secret_redaction(attribute: str) -> None:
    assert redact_value("demo-private", "text", attribute) == "[redacted]"
    assert redact_value("", "text", attribute) == ""
    assert redact_value("demo-private", "password") == "[redacted]"
    assert redact_value("a" * 200, "text", "name") == "a" * 100


def test_compact_prompt_and_config() -> None:
    settings = IsolatedSettings()
    elements = [
        Element(ref=f"e{i}", role="textbox", name="n" * 80, tag="input", value="v" * 100)
        for i in range(settings.max_observed_elements)
    ]
    obs = Observation(
        elements=elements,
        text_excerpt="t" * settings.max_observed_text_chars,
        truncated=True,
        generation=1,
    )
    prompt = obs.to_prompt_text()
    assert len(prompt) < 40_000
    assert len(prompt.splitlines()) == len(elements) + 3
    assert '[e12] textbox "' in prompt
    assert prompt.endswith("[truncated]")
    assert settings.browser_driver == "fake"
