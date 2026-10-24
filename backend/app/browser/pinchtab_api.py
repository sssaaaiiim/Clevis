"""All PinchTab 0.15.2 HTTP paths and wire fields live here. No raw errors/payload logging."""

from dataclasses import dataclass, field
from typing import Any
from urllib.parse import urlsplit
from uuid import uuid4

import httpx

from app.config import Settings
from app.core.events import Action
from app.interfaces.browser import BrowserFailure

PINCHTAB_MIN_VERSION = "0.15.2"
PINCHTAB_TESTED_VERSION = "0.15.2"


def loopback_origin(value: str) -> str:
    try:
        parsed = urlsplit(value)
        if (
            parsed.scheme == "http"
            and parsed.hostname in {"127.0.0.1", "::1"}
            and not parsed.username
            and not parsed.password
            and not parsed.query
            and not parsed.fragment
            and parsed.path in {"", "/"}
            and parsed.port
        ):
            return value.rstrip("/")
    except ValueError:
        pass
    raise BrowserFailure("BROWSER_ERROR", "PinchTab requires a bare literal-loopback HTTP URL.")


@dataclass(repr=False)
class PinchNode:
    ref: str
    role: str
    name: str


@dataclass(repr=False)
class PinchSnapshot:
    nodes: list[PinchNode] = field(default_factory=list)


def parse_snapshot(payload: Any) -> PinchSnapshot:
    try:
        return PinchSnapshot(
            [
                PinchNode(str(n["ref"]), str(n["role"]), str(n.get("name", ""))[:80])
                for n in payload["nodes"]
                if n.get("ref") and not n.get("hidden")
            ]
        )
    except (KeyError, TypeError, ValueError):
        raise BrowserFailure("BROWSER_ERROR", "Unsupported PinchTab snapshot response.") from None


def error_code(response: httpx.Response) -> str:
    try:
        payload = response.json()
        if payload.get("code") == "navigation_changed":
            # v0.15.2 can report 409 after a link begins navigating. Re-observe;
            # never replay the click automatically or treat this as an auth failure.
            return "STALE_REF"
        # Inspect internally only: upstream error strings may embed refs/URLs/typed values.
        marker = str(payload.get("code", "")) + " " + str(payload.get("error", ""))
        if any(
            value in marker.lower()
            for value in ("stale", "not found", "no snapshot", "unknown ref")
        ):
            return "STALE_REF"
    except (ValueError, AttributeError):
        pass
    return "BROWSER_ERROR"


class PinchtabAPI:
    def __init__(
        self, settings: Settings, transport: httpx.AsyncBaseTransport | None = None
    ) -> None:
        token = settings.pinchtab_token.get_secret_value()
        if not token:
            raise BrowserFailure(
                "BROWSER_ERROR", "Set PINCHTAB_TOKEN to the local PinchTab server token."
            )
        self.bridge_url: str | None = None
        self.request_timeout = settings.pinchtab_timeout_s
        self.navigation_timeout = max(self.request_timeout, settings.nav_timeout_ms / 1000 + 2)
        self.action_timeout = max(self.request_timeout, settings.action_timeout_ms / 1000 + 2)
        self.client = httpx.AsyncClient(
            base_url=loopback_origin(settings.pinchtab_url),
            headers={"Authorization": "Bearer " + token},
            timeout=settings.pinchtab_timeout_s,
            trust_env=False,
            follow_redirects=False,
            transport=transport,
        )

    async def request(self, method: str, path: str, body: dict[str, Any] | None = None) -> Any:
        try:
            destination = (
                self.bridge_url + path if self.bridge_url and path.startswith("/tabs/") else path
            )
            timeout = self.request_timeout
            if path.endswith("/navigate"):
                timeout = self.navigation_timeout
            elif path.endswith("/action"):
                timeout = self.action_timeout
            response = await self.client.request(method, destination, json=body, timeout=timeout)
            if response.status_code >= 400:
                code = error_code(response)
                raise BrowserFailure(
                    "STALE_REF" if code == "STALE_REF" else "BROWSER_ERROR",
                    "PinchTab reference is stale."
                    if code == "STALE_REF"
                    else "PinchTab request failed; check PINCHTAB_TOKEN and the local service.",
                )
            return response.json()
        except httpx.TimeoutException:
            raise BrowserFailure(
                "TIMEOUT", "PinchTab operation timed out; the browser or destination page is slow."
            ) from None
        except httpx.ConnectError:
            raise BrowserFailure(
                "BROWSER_ERROR", "Start local PinchTab 0.15.2 and check PINCHTAB_URL."
            ) from None
        except httpx.HTTPError:
            raise BrowserFailure(
                "BROWSER_ERROR", "PinchTab connection interrupted during the browser operation."
            ) from None
        except ValueError:
            raise BrowserFailure(
                "BROWSER_ERROR", "PinchTab returned an invalid response; check its tested version."
            ) from None

    async def health(self, run_id: str = "unassigned") -> None:
        health = await self.request("GET", "/health")
        version = str(health.get("version", "unknown"))
        if version != PINCHTAB_TESTED_VERSION:
            raise BrowserFailure(
                "BROWSER_ERROR",
                "Install PinchTab " + PINCHTAB_TESTED_VERSION + "; version mismatch.",
            )
        # Health alone can be public; instances must require the configured bearer token.
        await self.request("GET", "/instances")
        try:
            response = await self.client.get("/instances", headers={"Authorization": ""})
        except httpx.HTTPError:
            raise BrowserFailure(
                "BROWSER_ERROR", "Start local PinchTab 0.15.2 and check PINCHTAB_URL."
            ) from None
        if response.status_code not in {401, 403}:
            raise BrowserFailure(
                "BROWSER_ERROR", "Enable PinchTab token authentication before starting the API."
            )

    async def attach(self, port: int) -> str:
        data = await self.request(
            "POST",
            "/instances/attach",
            {
                "name": "clevis-" + uuid4().hex,
                "cdpUrl": f"http://127.0.0.1:{port}",
                "provider": "chrome",
            },
        )
        try:
            if not data.get("attached"):
                raise ValueError
            self.bridge_url = loopback_origin(str(data["url"]))
            return str(data["id"])
        except (KeyError, AttributeError, ValueError):
            raise BrowserFailure(
                "BROWSER_ERROR", "PinchTab did not attach the owned browser."
            ) from None

    async def tab(self, instance: str, target: str, url: str) -> str:
        if self.bridge_url is not None:
            # v0.15.2 ids.Manager.TabIDFromCDPTarget returns the target ID unchanged.
            return target
        tabs = await self.request("GET", f"/instances/{instance}/tabs?fresh=1")
        matches = [t for t in tabs if t.get("id") == target]
        if not matches:
            matches = [t for t in tabs if t.get("url") == url]
        if len(matches) != 1:
            raise BrowserFailure("BROWSER_ERROR", "PinchTab cannot uniquely map the active tab.")
        return str(matches[0]["id"])

    async def snapshot(self, tab: str) -> PinchSnapshot:
        return parse_snapshot(await self.request("GET", f"/tabs/{tab}/snapshot?filter=interactive"))

    async def action(
        self, tab: str, kind: str, ref: str | None = None, text: str | None = None, **fields: Any
    ) -> None:
        body: dict[str, Any] = {"kind": kind, **fields}
        if ref is not None:
            body["ref"] = ref
        if text is not None:
            body["text"] = text
        await self.request("POST", f"/tabs/{tab}/action", body)

    async def navigate(self, tab: str, url: str) -> None:
        await self.request("POST", f"/tabs/{tab}/navigate", {"url": url})

    async def handoff(self, tab: str, paused: bool) -> None:
        await self.request(
            "POST",
            f"/tabs/{tab}/" + ("handoff" if paused else "resume"),
            {"reason": "operator"} if paused else {"status": "completed"},
        )

    async def stop(self, instance: str) -> None:
        await self.request("POST", f"/instances/{instance}/stop")

    async def close(self) -> None:
        await self.client.aclose()


async def execute(
    api: PinchtabAPI, tab: str, action: "Action", ref: str | None, tag: str, viewport_height: int
) -> None:
    if action.action == "click":
        await api.action(tab, "click", ref)
    elif action.action == "type":
        if ref is None:
            if action.value not in {
                "Enter",
                "Tab",
                "Escape",
                "Backspace",
                "Delete",
                "ArrowUp",
                "ArrowDown",
                "ArrowLeft",
                "ArrowRight",
                "Home",
                "End",
                "PageUp",
                "PageDown",
                "Space",
            }:
                raise BrowserFailure(
                    "INVALID_ACTION", "A type action needs a current reference or key."
                )
            await api.action(tab, "press", key=action.value)
        elif tag == "select":
            await api.action(tab, "select", ref, value=action.value or "")
        else:
            await api.action(tab, "fill", ref, action.value or "")
    elif action.action == "scroll":
        direction = action.value or "down"
        if direction not in {"up", "down", "top", "bottom"}:
            raise BrowserFailure("INVALID_ACTION", "Unknown scroll direction.")
        pixels = {
            "up": -int(viewport_height * 0.8),
            "down": int(viewport_height * 0.8),
            "top": -10_000_000,
            "bottom": 10_000_000,
        }[direction]
        await api.action(tab, "scroll", scrollY=pixels)
    else:
        raise BrowserFailure("INVALID_ACTION", "Unsupported PinchTab action.")
