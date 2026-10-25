"""Ordered risk rules. Reasons are static strings and never echo untrusted content."""

import re
from dataclasses import dataclass
from urllib.parse import urlsplit

from app.agent.policy.permissions import RunPermissions
from app.browser.safety import SECRET_PATTERN
from app.config import Settings
from app.core.events import Action
from app.interfaces.browser import Observation


@dataclass(frozen=True)
class Classification:
    tier: int
    reason: str


def classify_action(
    action: Action,
    observation: Observation | None,
    current_url: str,
    settings: Settings,
    *,
    user_goal: str = "",
) -> Classification:
    elements = observation.elements if observation else []
    element = next((e for e in elements if e.ref == action.target.ref), None)
    # Control/completion actions must remain available even on a blocked page.
    if action.action in {"done", "handoff"}:
        return Classification(0, "Control action.")
    if action.action == "navigate":
        try:
            parsed = urlsplit(action.value or "")
            valid = parsed.scheme in {"http", "https"} and bool(parsed.hostname)
            _ = parsed.port
        except ValueError:
            valid = False
        if not valid:
            return Classification(3, "Non-HTTP(S) or invalid destination.")
    if element and (element.hidden or element.aria_hidden):
        return Classification(3, "Hidden target denied.")
    if (
        action.action == "type"
        and element
        and SECRET_PATTERN.search(" ".join((element.type or "", element.name)))
        and action.value
        and action.value not in user_goal
    ):
        return Classification(3, "Agent-generated credential denied; request human handoff.")
    path = urlsplit(current_url).path.lower()
    title = observation.title.lower() if observation else ""
    page = path + " " + title
    if re.search(
        r"(?:bank|financial|wire|transfer).{0,40}confirm|confirm.{0,40}(?:transfer|payment)", page
    ):
        return Classification(3, "Financial transaction confirmation denied.")
    if re.search(r"\b(payment|checkout|order)\b", page):
        return Classification(2, "Payment, checkout or order page.")
    if element:
        name = element.name.lower()
        submit = action.action in {"click", "type"} and (
            element.type in {"submit", "image"}
            or (
                element.tag == "button" and element.type is None and element.form_action is not None
            )
            or bool(re.search(r"\b(submit|send|confirm order|place order)\b", name))
        )
        if (
            settings.require_approval_for_send
            and submit
            and re.search(
                r"message|chat|compose|send",
                " ".join((name, element.form_name or "", element.form_action or "", path)),
            )
        ):
            return Classification(2, "Sending a message requires approval.")
        if settings.require_approval_for_submit and submit:
            return Classification(2, "Form submission requires approval.")
        if (
            settings.require_approval_for_download
            and action.action == "click"
            and (element.download or re.search(r"\b(download|save file)\b", name))
        ):
            return Classification(2, "Download requires approval.")
        if (
            settings.require_approval_for_upload
            and action.action in {"click", "type"}
            and (element.type == "file" or re.search(r"\b(upload|attach)\b", name))
        ):
            return Classification(2, "Upload requires approval.")
    # Enter without a ref can submit the focused form; conservatively require approval.
    if (
        settings.require_approval_for_submit
        and action.action == "type"
        and (not action.target.ref and action.value in {"Enter", "NumpadEnter"})
    ):
        return Classification(2, "Keyboard submission requires approval.")
    if action.action in {"click", "type"}:
        return Classification(1, "Ordinary page interaction.")
    return Classification(0, "Read-only action.")


def permission_denial(
    action: Action, observation: Observation | None, permissions: RunPermissions
) -> str | None:
    element = (
        next((e for e in observation.elements if e.ref == action.target.ref), None)
        if observation
        else None
    )
    if action.action not in {"click", "type"}:
        return None
    name = element.name.lower() if element else ""
    submit = (
        element is not None
        and (
            element.type in {"submit", "image"}
            or (
                element.tag == "button" and element.type is None and element.form_action is not None
            )
            or bool(re.search(r"\b(submit|send|confirm order|place order)\b", name))
        )
    ) or (
        action.action == "type"
        and not action.target.ref
        and action.value in {"Enter", "NumpadEnter"}
    )
    if submit and not permissions.allow_form_submit:
        return "Form submissions are disabled for this run."
    if (
        submit
        and not permissions.allow_send_message
        and (
            not element
            or re.search(
                r"message|chat|compose|send",
                " ".join((name, element.form_name or "", element.form_action or "")),
            )
        )
    ):
        return "Message sending is disabled for this run."
    if (
        element
        and not permissions.allow_downloads
        and (element.download or re.search(r"\b(download|save file)\b", name))
    ):
        return "Downloads are disabled for this run."
    if (
        element
        and not permissions.allow_uploads
        and (element.type == "file" or re.search(r"\b(upload|attach)\b", name))
    ):
        return "Uploads are disabled for this run."
    return None
