"""A test-only scripted fake that binds element descriptions to the newest observed refs."""

import json
import re

from app.core.events import Action, Target
from app.fakes.fake_llm import FakeLLMClient
from app.interfaces.llm import LLMResponse, Message, T


class ObservedScriptLLM(FakeLLMClient):
    async def propose(self, messages: list[Message], schema: type[T]) -> LLMResponse[T]:
        response = await super().propose(messages, schema)
        action = response.parsed
        if isinstance(action, Action) and action.target.description:
            for ref, name in re.findall(
                r'^\[(e\d+)\] \S+ ("(?:[^"\\]|\\.)*")', messages[-1].content, re.M
            ):
                if json.loads(name) == action.target.description:
                    bound = action.model_copy(
                        update={
                            "target": Target(
                                ref=ref,
                                description=action.target.description,
                            )
                        }
                    )
                    return LLMResponse(
                        parsed=schema.model_validate(bound.model_dump()),
                        tokens_used=response.tokens_used,
                        usage=response.usage,
                    )
            raise RuntimeError("Scripted target was not observed.")
        return response


def form_script(base_url: str) -> list[Action]:
    return [
        Action(action="navigate", value=base_url + "/form.html", rationale="Open the local form."),
        Action(
            action="type",
            target=Target(description="Name"),
            value="Demo Example",
            rationale="Fill the demo name.",
        ),
        Action(
            action="type",
            target=Target(description="Email"),
            value="demo@example.test",
            rationale="Fill the demo email.",
        ),
        Action(
            action="type",
            target=Target(description="Project"),
            value="Priority",
            rationale="Choose the demo project.",
        ),
        Action(
            action="click", target=Target(description="Newsletter"), rationale="Select newsletter."
        ),
        Action(
            action="click", target=Target(description="Submit form"), rationale="Submit the demo."
        ),
        Action(
            action="done", value="The form was submitted.", rationale="The demo goal is complete."
        ),
    ]
