"""HTTP endpoints for the web task orchestrator."""

from collections.abc import AsyncGenerator
import os

import httpx
from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import StreamingResponse
from starlette.responses import Response

from app.config import PINCHTAB_BASE
from app.models.run_request import RunRequest
from app.services.agent import agent_loop

router = APIRouter()


@router.get("/api/screenshot")
async def screenshot(tab_id: str = Query(min_length=1, max_length=128)) -> Response:
    """Proxy a full-resolution PNG screenshot for the active PinchTab tab."""
    headers = {}
    pinchtab_token = os.getenv("PINCHTAB_TOKEN")
    if pinchtab_token:
        headers["Authorization"] = f"Bearer {pinchtab_token}"

    try:
        async with httpx.AsyncClient(base_url=PINCHTAB_BASE, headers=headers, timeout=15) as client:
            result = await client.get(
                "/screenshot",
                params={"tabId": tab_id, "format": "png", "scale": "1", "raw": "true"},
            )
            result.raise_for_status()
    except httpx.HTTPStatusError as exc:
        raise HTTPException(
            status_code=502,
            detail=f"PinchTab screenshot failed with HTTP {exc.response.status_code}.",
        ) from exc
    except httpx.RequestError as exc:
        raise HTTPException(status_code=502, detail="Could not connect to PinchTab for a screenshot.") from exc

    content_type = result.headers.get("content-type", "image/png").split(";", 1)[0].lower()
    if content_type not in {"image/png", "image/jpeg", "image/webp"}:
        raise HTTPException(status_code=502, detail="PinchTab returned an unsupported screenshot format.")
    return Response(
        content=result.content,
        media_type=content_type,
        headers={"Cache-Control": "no-store"},
    )


@router.get("/api/health")
async def health() -> dict[str, bool]:
    """Liveness probe."""
    return {"ok": True}


@router.post("/api/run")
async def run(request: RunRequest) -> StreamingResponse:
    """Run the browser agent and stream NDJSON progress events."""

    async def event_stream() -> AsyncGenerator[str, None]:
        async for chunk in agent_loop(
            task=request.task,
            url=request.url,
            max_steps=request.max_steps,
            headless=request.headless,
            timeout=request.timeout,
        ):
            yield chunk

    return StreamingResponse(
        event_stream(),
        media_type="application/x-ndjson",
        headers={"X-Accel-Buffering": "no"},
    )
