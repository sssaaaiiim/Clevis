"""Per-run policy dependency. All reasons and displayed summaries are static."""

import ipaddress
from urllib.parse import urlsplit

from app.agent.policy.dataflow import DataFlowTracker
from app.agent.policy.domains import (
    Resolver,
    hostname,
    is_allowed_domain,
    is_blocked_domain,
    is_private_address,
    parse_domains,
)
from app.agent.policy.resolver import CachedResolver
from app.agent.policy.tiers import Classification, classify_action
from app.agent.state import AgentState
from app.config import Settings
from app.core.events import Action
from app.core.state import RunRecord
from app.interfaces.browser import BrowserFailure
from app.interfaces.validator import ApprovalRequest, Verdict


class PolicyValidator:
    def __init__(self, settings: Settings, resolver: Resolver | None = None) -> None:
        self.settings = settings
        self.allowed = parse_domains(settings.allowed_domains)
        self.blocked = parse_domains(settings.blocked_domains)
        self.cache = CachedResolver()
        self.resolver = resolver or self.cache
        self.approved_hosts: set[str] = set()

    async def guard_url(self, url: str, navigation: bool) -> None:
        if urlsplit(url).scheme not in {"http", "https"}:
            raise BrowserFailure("BLOCKED_URL", "Policy blocked a non-HTTP(S) request.")
        classification = await self._destination(url)
        if classification.tier == 3 or (
            navigation and classification.tier == 2 and hostname(url) not in self.approved_hosts
        ):
            raise BrowserFailure("BLOCKED_URL", "Policy blocked the browser destination.")

    def authorize_destination(self, state: AgentState, action: Action) -> None:
        if action.action == "navigate" and action.value:
            self.approved_hosts.add(hostname(action.value))
        elif state.last_observation:
            element = next(
                (e for e in state.last_observation.elements if e.ref == action.target.ref), None
            )
            if element:
                self.approved_hosts.update(
                    hostname(url) for url in (element.href, element.form_action) if url
                )

    async def _destination(self, url: str) -> Classification:
        if is_blocked_domain(url, self.blocked):
            return Classification(3, "Destination domain is blocked.")
        if self.settings.block_private_network:
            try:
                host = hostname(url)
                try:
                    ipaddress.ip_address(host)
                except ValueError:
                    if (
                        self.resolver is self.cache
                        and host
                        not in {
                            "localhost",
                            "metadata.google.internal",
                            "metadata.azure.com",
                        }
                        and not host.endswith(".localhost")
                    ):
                        await self.cache.resolve(host)
                if is_private_address(url, self.resolver):
                    return Classification(3, "SSRF: private address.")
            except (ValueError, OSError):
                return Classification(3, "Destination address could not be verified.")
        if not is_allowed_domain(url, self.allowed, self.blocked):
            return Classification(2, "Destination is outside ALLOWED_DOMAINS.")
        return Classification(0, "Allowed destination.")

    async def validate(self, run_state: RunRecord | AgentState, action: Action) -> Verdict:
        state = (
            run_state
            if isinstance(run_state, AgentState)
            else AgentState(
                run_id=run_state.runId,
                goal=run_state.goal,
            )
        )
        if state.permissions is not None:
            self.allowed = frozenset(state.permissions.allowed_domains)
            self.blocked = frozenset(state.permissions.blocked_domains)
        observation = state.last_observation
        url = observation.url if observation else "about:blank"
        classification = classify_action(
            action, observation, url, self.settings, user_goal=state.goal
        )
        if state.permissions is not None and classification.tier < 3:
            from app.agent.policy.tiers import permission_denial
            denial = permission_denial(action, observation, state.permissions)
            if denial:
                classification = Classification(3, denial)
        destination = action.value if action.action == "navigate" else None
        if observation and action.target.ref:
            element = next((e for e in observation.elements if e.ref == action.target.ref), None)
            if element and action.action == "click" and element.href:
                destination = element.href
            elif element and action.action in {"click", "type"} and element.form_action:
                destination = element.form_action
        # Blocked/current private pages cannot be used to evade destination restrictions.
        candidates = [destination] if destination else []
        if action.action not in {"done", "handoff", "navigate"} and url != "about:blank":
            candidates.append(url)
        for candidate in candidates:
            try:
                parsed = urlsplit(candidate)
                valid = parsed.scheme in {"http", "https"} and bool(parsed.hostname)
            except ValueError:
                valid = False
            check = (
                await self._destination(candidate)
                if valid
                else Classification(
                    3,
                    "Non-HTTP(S) or invalid destination.",
                )
            )
            if check.tier > classification.tier:
                classification = check
        if action.action == "type" and action.value:
            tracker = DataFlowTracker(
                state.data_flow,
                max_bytes=self.settings.max_data_flow_bytes,
                auto_allow_same_domain=self.settings.auto_allow_same_domain_data_flow,
            )
            if (
                tracker.check_type_action(hostname(url), action.value) == "FLAG"
                and classification.tier < 2
                and not (state.permissions and state.permissions.allow_cross_domain_data)
            ):
                classification = Classification(2, "Cross-domain data movement requires approval.")
        tier, reason = classification.tier, classification.reason
        display = (
            ApprovalRequest(
                action_summary=f"Approve {action.action} action: {reason}"[:300],
                risk="high" if "Payment" in reason else "medium",
                page_url=hostname(destination or url),
            )
            if tier == 2
            else None
        )
        return Verdict(
            verdict="deny" if tier == 3 else "approval" if tier == 2 else "allow",
            tier=tier,
            reason=reason,
            display=display,
        )

    async def validate_agent(self, state: AgentState, action: Action) -> Verdict:
        return await self.validate(state, action)
