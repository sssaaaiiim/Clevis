"""Test-only UI preview demo: BROWSER_DRIVER=playwright uvicorn tests.preview_demo:app."""

import os

from app.core.events import Action
from app.fakes.fake_llm import FakeLLMClient
from app.main import create_app
from tests.settings import IsolatedSettings


def script() -> FakeLLMClient:
    base = os.environ.get("TESTSITE_URL", "http://127.0.0.1:8765")
    return FakeLLMClient(
        actions=[
            Action(
                action="navigate", value=base + "/form.html", rationale="Open the fake demo form."
            ),
            Action(
                action="wait", value="10", rationale="Keep the demo visible for preview inspection."
            ),
            Action(
                action="done", value="Preview demo complete.", rationale="The demo is complete."
            ),
        ],
        delay=0.2,
    )


app = create_app(
    IsolatedSettings(browser_driver="playwright", llm_provider="fake"), llm_factory=script
)
