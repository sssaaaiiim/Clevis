import asyncio
import json
from typing import Any
from uuid import uuid4

import pytest
from httpx import ASGITransport, AsyncClient

from app.core.events import Action, Plan, PlanStep, Target
from app.fakes.fake_driver import FakeBrowserDriver
from app.fakes.fake_llm import FakeLLMClient
from app.interfaces.browser import Element, Observation
from app.main import create_app
from tests.settings import PolicySettings


class ApprovalDriver(FakeBrowserDriver):
    async def observe(self) -> Observation:
        return Observation(
            elements=[
                Element(
                    ref="e1",
                    name="Submit",
                    role="button",
                    tag="button",
                    type="submit",
                )
            ]
        )


def application(timeout: float = 300, *, twice: bool = False) -> Any:
    click = Action(action="click", target=Target(ref="e1"), rationale="Submit the demo.")
    return create_app(
        PolicySettings(approval_timeout_s=timeout),
        driver_factory=lambda: ApprovalDriver(delay=0),
        llm_factory=lambda: FakeLLMClient(
            actions=[click] * (2 if twice else 1)
            + [
                Action(
                    action="done",
                    value="Demo complete",
                    rationale="Complete.",
                )
            ],
            plan=Plan(steps=[PlanStep(id=1, text="Complete the demo")]),
            delay=0,
        ),
    )


async def pending(app: Any, run_id: str) -> str:
    async with asyncio.timeout(3):
        while True:
            record = await app.state.service.store.get(run_id)
            if record.status == "paused":
                events = await app.state.service.store.list_events(run_id)
                requests = [e for e in events if e.type == "approval.required"]
                if requests:
                    return str(requests[-1].data.approval_id)
            await asyncio.sleep(0.005)


@pytest.mark.parametrize("decision", ["approve", "deny"])
async def test_authenticated_approval_and_denial(
    decision: str, caplog: pytest.LogCaptureFixture
) -> None:
    app = application()
    async with app.router.lifespan_context(app):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            created = (
                await client.post("/api/runs", json={"goal": "Demo", "mode": "headless"})
            ).json()
            run_id, token = created["runId"], created["approvalToken"]
            assert token not in {created["previewToken"], created["controlToken"]}
            task = app.state.service.tasks[run_id]
            approval_id = await pending(app, run_id)
            body = {"approval_id": approval_id}
            if decision == "deny":
                body["reason"] = "PRIVATE-REASON-CANARY"
            response = await client.post(
                f"/api/runs/{run_id}/{decision}",
                json=body,
                headers={"Authorization": f"Bearer {token}"},
            )
            assert response.status_code == 200
            assert response.json()["status"] == ("approved" if decision == "approve" else "denied")
            await asyncio.wait_for(task, 3)
            record = await app.state.service.store.get(run_id)
            assert record.status == "finished" and record.result == "Demo complete"
            events = await app.state.service.store.list_events(run_id)
            resumed = next(e for e in events if e.type == "run.resumed")
            assert resumed.data.reason == ("approved" if decision == "approve" else "denied")
            assert token not in caplog.text and "PRIVATE-REASON-CANARY" not in caplog.text
            assert token not in json.dumps([e.model_dump() for e in events])


async def test_wrong_token_stale_id_duplicate_and_unknown() -> None:
    app = application()
    async with app.router.lifespan_context(app):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            created = (
                await client.post("/api/runs", json={"goal": "Demo", "mode": "headless"})
            ).json()
            run_id, token = created["runId"], created["approvalToken"]
            approval_id = await pending(app, run_id)
            url, body = f"/api/runs/{run_id}/approve", {"approval_id": approval_id}
            assert (await client.post(url, json=body)).status_code == 401
            assert (
                await client.post(url, json=body, headers={"Authorization": "Bearer wrong"})
            ).status_code == 401
            headers = {"Authorization": f"Bearer {token}"}
            assert (
                await client.post(url, json={"approval_id": str(uuid4())}, headers=headers)
            ).status_code == 422
            assert (
                await client.post("/api/runs/unknown/approve", json=body, headers=headers)
            ).status_code == 404
            assert (await client.post(url, json=body, headers=headers)).status_code == 200
            assert (await client.post(url, json=body, headers=headers)).status_code == 409


async def test_denial_then_new_request_rejects_old_id() -> None:
    app = application(twice=True)
    async with app.router.lifespan_context(app):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            created = (
                await client.post("/api/runs", json={"goal": "Demo", "mode": "headless"})
            ).json()
            run_id = created["runId"]
            headers = {"Authorization": f"Bearer {created['approvalToken']}"}
            old_id = await pending(app, run_id)
            assert (
                await client.post(
                    f"/api/runs/{run_id}/deny", json={"approval_id": old_id}, headers=headers
                )
            ).status_code == 200
            async with asyncio.timeout(3):
                while True:
                    new_id = await pending(app, run_id)
                    if new_id != old_id:
                        break
                    await asyncio.sleep(0.005)
            assert (
                await client.post(
                    f"/api/runs/{run_id}/approve", json={"approval_id": old_id}, headers=headers
                )
            ).status_code == 422
            assert (
                await client.post(
                    f"/api/runs/{run_id}/approve", json={"approval_id": new_id}, headers=headers
                )
            ).status_code == 200


@pytest.mark.parametrize("wait_s", [0.05, 1])
async def test_approval_timeout_fails_cleanly_and_stop_works(wait_s: float) -> None:
    app = application(timeout=wait_s)
    async with app.router.lifespan_context(app):
        run = await app.state.service.create("Demo", "headless")
        await asyncio.gather(*app.state.service.tasks.values())
        record = await app.state.service.store.get(run.runId)
        assert record.status == "failed" and record.error == "Approval timed out"
    app = application(timeout=0)
    async with app.router.lifespan_context(app):
        run = await app.state.service.create("Demo", "headless")
        await pending(app, run.runId)
        await asyncio.wait_for(app.state.service.stop(run.runId), 2)
        assert (await app.state.service.store.get(run.runId)).status == "stopped"


async def test_multi_subgoal_revision_and_authenticated_approval_timeline() -> None:
    from tests.test_outcome_graph import ScriptVerifier

    verifier = ScriptVerifier([True, False, True, True])
    click = Action(action="click", target=Target(ref="e1"), rationale="Submit demo.")
    finish = Action(action="done", value="All demo parts completed", rationale="Complete part.")
    app = create_app(
        PolicySettings(),
        driver_factory=lambda: ApprovalDriver(delay=0),
        llm_factory=lambda: FakeLLMClient(
            actions=[finish, finish, finish, click, finish],
            plan=Plan(steps=[PlanStep(id=i, text=f"Demo part {i}") for i in range(1, 4)]),
            delay=0,
        ),
        outcome_llm_factory=lambda: verifier,
    )
    async with app.router.lifespan_context(app):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            created = (
                await client.post(
                    "/api/runs", json={"goal": "Complete three parts", "mode": "headless"}
                )
            ).json()
            run_id = created["runId"]
            task = app.state.service.tasks[run_id]
            approval_id = await pending(app, run_id)
            answer = await client.post(
                f"/api/runs/{run_id}/approve",
                json={"approval_id": approval_id},
                headers={"Authorization": f"Bearer {created['approvalToken']}"},
            )
            assert answer.status_code == 200
            await asyncio.wait_for(task, 3)
            record = await app.state.service.store.get(run_id)
            assert record.status == "finished" and record.result == "All demo parts completed"
            events = await app.state.service.store.list_events(run_id)
            assert [e.seq for e in events] == list(range(1, len(events) + 1))
            assert sum(e.type == "step.proposed" and e.data.action == "revise" for e in events) == 1
            assert sum(e.type == "approval.required" for e in events) == 1
            assert verifier.calls == 4
            timeline = [e.type for e in events]
            assert (
                timeline.index("approval.required")
                < timeline.index("run.paused")
                < timeline.index("run.resumed")
                < timeline.index("run.finished")
            )
