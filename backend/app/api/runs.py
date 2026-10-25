import secrets
from collections.abc import AsyncIterator
from typing import Annotated, cast

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request
from pydantic import UUID4, Field, field_validator
from sse_starlette import EventSourceResponse, ServerSentEvent

from app.agent.policy.permissions import RunPermissions, resolve_permissions
from app.core.events import TERMINAL_EVENTS, Mode, Model
from app.core.state import RunRecord
from app.runtime import RunService, StaleApproval

router = APIRouter(prefix="/api/runs")


def get_service(request: Request) -> RunService:
    return cast(RunService, request.app.state.service)


Service = Annotated[RunService, Depends(get_service)]


class CreateRun(Model):
    permissions: RunPermissions | None = None
    goal: str = Field(min_length=1, max_length=2000)
    mode: Mode

    @field_validator("goal", mode="before")
    @classmethod
    def trim_goal(cls, value: object) -> object:
        return value.strip() if isinstance(value, str) else value


class CreatedRun(Model):
    runId: str
    previewToken: str = Field(repr=False)
    controlToken: str = Field(repr=False)
    approvalToken: str = Field(repr=False)


@router.post("", status_code=201)
async def create_run(body: CreateRun, service: Service) -> CreatedRun:
    try:
        permissions = resolve_permissions(body.permissions, service.settings)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from None
    run = await service.create(body.goal, body.mode, permissions=permissions)
    return CreatedRun(
        runId=run.runId,
        previewToken=service.preview_tokens[run.runId],
        controlToken=service.control_tokens[run.runId],
        approvalToken=service.approval_tokens[run.runId],
    )


class ApprovalDecision(Model):
    approval_id: UUID4


class DenialDecision(ApprovalDecision):
    reason: str = Field(default="", max_length=200)


async def authorize_approval(run_id: str, service: RunService, authorization: str | None) -> None:
    await service.store.get(run_id)
    scheme, _, token = (authorization or "").partition(" ")
    expected = service.approval_tokens.get(run_id, "")
    if (
        scheme.lower() != "bearer"
        or not expected
        or not secrets.compare_digest(token.encode(), expected.encode())
    ):
        raise HTTPException(status_code=401, detail="Approval authorization required.")


@router.post("/{run_id}/approve")
async def approve(
    run_id: str,
    body: ApprovalDecision,
    service: Service,
    authorization: Annotated[str | None, Header()] = None,
) -> dict[str, str]:
    await authorize_approval(run_id, service, authorization)
    try:
        await service.decide_approval(run_id, str(body.approval_id), "approved")
    except StaleApproval:
        raise HTTPException(status_code=422, detail="Approval request has expired.") from None
    return {"status": "approved"}


@router.post("/{run_id}/deny")
async def deny(
    run_id: str,
    body: DenialDecision,
    service: Service,
    authorization: Annotated[str | None, Header()] = None,
) -> dict[str, str]:
    await authorize_approval(run_id, service, authorization)
    try:
        await service.decide_approval(run_id, str(body.approval_id), "denied", body.reason)
    except StaleApproval:
        raise HTTPException(status_code=422, detail="Approval request has expired.") from None
    return {"status": "denied"}


@router.get("/{run_id}")
async def get_run(run_id: str, service: Service) -> RunRecord:
    return await service.store.get(run_id)


@router.post("/{run_id}/stop")
async def stop_run(run_id: str, service: Service) -> RunRecord:
    return await service.stop(run_id)


@router.post("/{run_id}/takeover")
async def takeover(run_id: str, service: Service) -> RunRecord:
    return await service.takeover(run_id)


@router.post("/{run_id}/resume")
async def resume(run_id: str, service: Service) -> RunRecord:
    return await service.resume(run_id)


@router.get("/{run_id}/events", response_class=EventSourceResponse)
async def events(
    run_id: str,
    service: Service,
    after: Annotated[int | None, Query(ge=0)] = None,
    last_event_id: Annotated[str | None, Header(alias="Last-Event-ID")] = None,
) -> EventSourceResponse:
    await service.store.get(run_id)
    # An explicit query cursor wins over the reconnect header.
    try:
        cursor = after if after is not None else int(last_event_id or "0")
        if cursor < 0:
            raise ValueError
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid event cursor.") from None

    async def stream() -> AsyncIterator[ServerSentEvent]:
        async with service.emitter.subscribe(run_id, cursor) as subscription:
            while True:
                if subscription.terminal and subscription.queue.empty():
                    return
                event = await subscription.queue.get()
                if event.seq > cursor:
                    yield ServerSentEvent(
                        id=str(event.seq),
                        event=event.type,
                        data=event.model_dump_json(),
                    )
                if event.type in TERMINAL_EVENTS:
                    return

    return EventSourceResponse(
        stream(),
        ping=15,
        sep="\n",
        send_timeout=5,
        ping_message_factory=lambda: ServerSentEvent(comment="keep-alive"),
    )
