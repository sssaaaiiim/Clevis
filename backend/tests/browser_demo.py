"""Local-only scripted HTTP smoke app, using the unchanged production routes."""

import os

from app.main import create_app
from tests.scripted_browser_llm import ObservedScriptLLM, form_script
from tests.settings import IsolatedSettings

app = create_app(
    IsolatedSettings(),
    llm_factory=lambda: ObservedScriptLLM(
        actions=form_script(os.environ.get("TESTSITE_URL", "http://127.0.0.1:8765")), delay=0
    ),
)
