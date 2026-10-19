"""ReAct-style web task agent using OpenRouter and PinchTab."""

import asyncio
import json
import logging
import os
from collections.abc import AsyncGenerator
from typing import Any
from urllib.parse import quote_plus

import anyio
import httpx

from app.config import PINCHTAB_BASE
from app.services.openrouter import OpenRouterClient
from app.services.token_telemetry import compare_layout_sizes
from app.utils.ndjson import ndjson

logger = logging.getLogger(__name__)


async def agent_loop(
    task: str,
    url: str,
    max_steps: int,
    headless: bool,
    timeout: int,
) -> AsyncGenerator[str, None]:
    """Run the browser agent and yield NDJSON progress events."""
    openrouter_api_key = os.getenv("OPENROUTER_API_KEY")
    if not openrouter_api_key:
        yield ndjson({
            "event": "result",
            "status": "error",
            "message": "OPENROUTER_API_KEY is not set.",
        })
        return

    instance_id: str | None = None
    usage: dict[str, int] = {"tokens": 0}
    http_timeout = httpx.Timeout(timeout=float(timeout))

    pinchtab_headers: dict[str, str] = {}
    pinchtab_token = os.getenv("PINCHTAB_TOKEN")
    if pinchtab_token:
        pinchtab_headers["Authorization"] = f"Bearer {pinchtab_token}"

    async with (
        httpx.AsyncClient(
            base_url=PINCHTAB_BASE,
            headers=pinchtab_headers,
            timeout=http_timeout,
        ) as client,
        OpenRouterClient(openrouter_api_key, http_timeout) as llm,
    ):
        try:
            yield ndjson({"event": "status", "status": "Planning"})

            mode = "headless" if headless else "headed"
            try:
                resp = await client.post("/instances/start", json={"mode": mode})
                resp.raise_for_status()
                instance_data = resp.json()
                instance_id = instance_data.get("id") or instance_data.get("instanceId")
                yield ndjson({
                    "event": "log",
                    "actor": "System",
                    "msg": f"Browser instance started (id={instance_id}, mode={mode}).",
                })
            except httpx.ConnectError:
                yield ndjson({
                    "event": "result",
                    "status": "error",
                    "message": "Cannot connect to PinchTab. Make sure `pinchtab server` is running on port 9867.",
                })
                return
            except httpx.HTTPStatusError as exc:
                yield ndjson({
                    "event": "result",
                    "status": "error",
                    "message": f"PinchTab /instances/start failed: {exc.response.status_code} {exc.response.text}",
                })
                return

            url = url.strip()
            if not url:
                url = f"https://www.google.com/search?q={quote_plus(task)}"
                yield ndjson({
                    "event": "log",
                    "actor": "Planner",
                    "msg": "No URL given. Searching the web for the requested destination.",
                })
            elif not url.startswith(("http://", "https://")):
                url = f"https://{url}"
            yield ndjson({"event": "target", "url": url})

            yield ndjson({"event": "status", "status": "Running"})
            tab_id: str | None = None
            try:
                nav_resp = await client.post("/navigate", json={"url": url})
                nav_resp.raise_for_status()
                tab_id = nav_resp.json().get("tabId")
                if isinstance(tab_id, str) and tab_id:
                    yield ndjson({"event": "browser_tab", "tab_id": tab_id})
                yield ndjson({"event": "log", "actor": "Navigator", "msg": f"Navigated to {url}."})
            except httpx.HTTPStatusError as exc:
                yield ndjson({
                    "event": "result",
                    "status": "error",
                    "message": f"Navigation failed: {exc.response.status_code} {exc.response.text}",
                })
                return

            yield ndjson({"event": "status", "status": "Planning"})
            planning_prompt = (
                f"You are a web task planner. Given a task and starting URL, produce a JSON array "
                f"of up to {max_steps} step labels (strings) that an agent should follow to complete the task.\n"
                "If the task is to open or go to a named website and the starting URL is a search results page, "
                "identify the matching official website from the results and navigate to it. Do not guess its URL.\n"
                "Respond ONLY with a JSON array of strings. No markdown. No extra keys.\n"
                'Example: ["Load the page", "Find the search bar", "Type the query", "Submit search", "Extract results"]'
            )
            step_labels = await llm.complete_json(
                f"{planning_prompt}\n\nTask: {task}\nStarting URL: {url}",
                fallback=[f"Complete the task: {task}"],
                usage=usage,
            )
            yield ndjson({"event": "usage", "tokens": usage["tokens"]})
            if not isinstance(step_labels, list) or len(step_labels) == 0:
                step_labels = [f"Complete the task: {task}"]

            step_labels = step_labels[:max_steps]
            plan_steps = [{"id": i + 1, "label": label} for i, label in enumerate(step_labels)]
            yield ndjson({
                "event": "log",
                "actor": "Planner",
                "msg": f"Decomposed task into {len(plan_steps)} step(s).",
            })
            yield ndjson({"event": "plan", "steps": plan_steps})

            action_system_prompt = (
                "You are a browser automation agent. You are given a task step and the current page's "
                "interactive elements as a compact accessibility tree.\n"
                "When selecting a website from search results, prefer the official site that matches the requested name. "
                "Use its actual result link; do not guess or invent a URL.\n"
                "Respond ONLY with a JSON object (no markdown) with one of these shapes:\n"
                '- { "action": "click", "ref": "e5" }\n'
                '- { "action": "type", "ref": "e5", "text": "hello" }\n'
                '- { "action": "fill", "ref": "e5", "text": "hello" }\n'
                '- { "action": "navigate", "url": "https://example.com" }\n'
                '- { "action": "done", "reason": "task complete" }\n'
            )
            last_snapshot: str = ""
            tab_params = {"tabId": tab_id} if isinstance(tab_id, str) and tab_id else {}

            for step_index, step in enumerate(plan_steps):
                yield ndjson({"event": "step", "index": step_index})
                yield ndjson({
                    "event": "log",
                    "actor": "Navigator",
                    "msg": f"Starting step {step_index + 1}: {step['label']}",
                })

                snapshot_layout: Any = last_snapshot
                try:
                    snap_resp = await client.get(
                        "/snapshot",
                        params={**tab_params, "filter": "interactive", "format": "compact"},
                    )
                    snap_resp.raise_for_status()
                    try:
                        snapshot_layout = snap_resp.json()
                    except ValueError:
                        snapshot_layout = snap_resp.text.strip()
                    last_snapshot = json.dumps(snapshot_layout, ensure_ascii=False, separators=(",", ":"))
                    yield ndjson({"event": "log", "actor": "Navigator", "msg": "Page snapshot captured."})
                except (httpx.HTTPStatusError, httpx.RequestError) as exc:
                    yield ndjson({
                        "event": "log",
                        "actor": "Navigator",
                        "msg": f"Snapshot failed ({exc}); continuing with last known state.",
                    })

                try:
                    html_resp = await client.get("/html", params=tab_params)
                    html_resp.raise_for_status()
                    html_data = html_resp.json()
                    raw_html = html_data.get("html") if isinstance(html_data, dict) else None
                    if not isinstance(raw_html, str):
                        raise ValueError("PinchTab /html response did not contain an HTML string.")
                    yield ndjson({
                        "event": "layout_comparison",
                        **compare_layout_sizes(raw_html, snapshot_layout),
                    })
                except Exception:
                    logger.warning("Unable to compare HTML and snapshot layout telemetry.", exc_info=True)

                action_prompt = (
                    f"{action_system_prompt}\n\n"
                    f"Overall task: {task}\n"
                    f"Current step ({step_index + 1}/{len(plan_steps)}): {step['label']}\n\n"
                    f"Page interactive elements (accessibility tree):\n{last_snapshot}"
                )
                action: dict[str, Any] = await llm.complete_json(
                    action_prompt,
                    fallback={"action": "done", "reason": "could not determine action"},
                    usage=usage,
                )
                yield ndjson({"event": "usage", "tokens": usage["tokens"]})
                if not isinstance(action, dict):
                    yield ndjson({
                        "event": "log",
                        "actor": "Navigator",
                        "msg": "Invalid action response from OpenRouter. Skipping step.",
                    })
                    continue

                action_type: str = action.get("action", "")
                yield ndjson({
                    "event": "log",
                    "actor": "Navigator",
                    "msg": f"Decided action: {json.dumps(action)}",
                })

                if action_type in ("click", "type", "fill", "navigate"):
                    yield ndjson({
                        "event": "action",
                        "kind": action_type,
                        "ref": action.get("ref"),
                        "text": action.get("text"),
                        "url": action.get("url"),
                    })

                if action_type == "done":
                    reason = action.get("reason", "no reason given")
                    yield ndjson({
                        "event": "log",
                        "actor": "Navigator",
                        "msg": f"Agent signalled completion: {reason}",
                    })
                    break
                elif action_type == "navigate":
                    nav_url = action.get("url", "")
                    try:
                        response = await client.post("/navigate", json={"url": nav_url})
                        response.raise_for_status()
                        yield ndjson({"event": "log", "actor": "Navigator", "msg": f"Navigated to {nav_url}."})
                    except httpx.HTTPStatusError as exc:
                        yield ndjson({
                            "event": "log",
                            "actor": "Navigator",
                            "msg": f"Navigation to {nav_url} failed: {exc.response.status_code}.",
                        })
                elif action_type in ("click", "type", "fill"):
                    payload: dict[str, Any] = {"kind": action_type, "ref": action.get("ref", "")}
                    if action_type in ("type", "fill"):
                        payload["text"] = action.get("text", "")
                    try:
                        response = await client.post("/action", json=payload)
                        response.raise_for_status()
                        yield ndjson({
                            "event": "log",
                            "actor": "Navigator",
                            "msg": f"Action '{action_type}' on ref '{payload.get('ref')}' succeeded.",
                        })
                    except httpx.HTTPStatusError as exc:
                        try:
                            error_data = exc.response.json()
                        except ValueError:
                            error_data = {}
                        details = error_data.get("details", {}) if isinstance(error_data, dict) else {}
                        if (
                            exc.response.status_code == 409
                            and isinstance(error_data, dict)
                            and error_data.get("code") == "navigation_changed"
                        ):
                            navigated_url = details.get("url") if isinstance(details, dict) else None
                            if navigated_url:
                                yield ndjson({"event": "target", "url": navigated_url})
                                message = f"Action '{action_type}' navigated to {navigated_url}."
                            else:
                                message = (
                                    f"Action '{action_type}' changed the page; continuing on the new page."
                                )
                            yield ndjson({"event": "log", "actor": "Navigator", "msg": message})
                        else:
                            yield ndjson({
                                "event": "log",
                                "actor": "Navigator",
                                "msg": (
                                    f"Action '{action_type}' failed: {exc.response.status_code} "
                                    f"{exc.response.text}."
                                ),
                            })
                else:
                    yield ndjson({
                        "event": "log",
                        "actor": "Navigator",
                        "msg": f"Unknown action type '{action_type}'. Skipping.",
                    })

                await asyncio.sleep(0.5)

            yield ndjson({"event": "status", "status": "Validating"})
            try:
                snap_resp = await client.get(
                    "/snapshot",
                    params={**tab_params, "filter": "interactive", "format": "compact"},
                )
                snap_resp.raise_for_status()
                try:
                    validation_layout = snap_resp.json()
                except ValueError:
                    validation_layout = snap_resp.text.strip()
                validation_snapshot = json.dumps(
                    validation_layout,
                    ensure_ascii=False,
                    separators=(",", ":"),
                )
            except Exception:
                validation_snapshot = last_snapshot

            validation_prompt = (
                "You are a task validator. Given the original task and the current page state, "
                "determine if the task has been completed successfully.\n"
                'Respond ONLY with a JSON object: { "completed": true|false, "summary": "one sentence" }'
                f"\n\nTask: {task}\n\nFinal page state:\n{validation_snapshot}"
            )
            validation: dict[str, Any] = await llm.complete_json(
                validation_prompt,
                fallback={"completed": False, "summary": "Could not validate task completion."},
                usage=usage,
            )
            yield ndjson({"event": "usage", "tokens": usage["tokens"]})
            if not isinstance(validation, dict):
                validation = {"completed": False, "summary": "Validation response was invalid."}
            completed: bool = bool(validation.get("completed", False))
            summary: str = validation.get("summary", "Task execution finished.")

            yield ndjson({"event": "status", "status": "Completed" if completed else "Failed"})
            yield ndjson({
                "event": "result",
                "status": "success" if completed else "error",
                "message": summary,
            })

        except asyncio.CancelledError:
            raise
        except Exception as exc:  # noqa: BLE001
            logger.exception("Unexpected agent orchestration error.")
            yield ndjson({"event": "result", "status": "error", "message": f"Unexpected error: {exc}"})
        finally:
            if instance_id:
                with anyio.CancelScope(shield=True):
                    try:
                        await client.post(f"/instances/{instance_id}/stop")
                    except Exception:
                        logger.warning("Unable to stop PinchTab instance %s.", instance_id, exc_info=True)
