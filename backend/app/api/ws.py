from typing import cast

from fastapi import APIRouter, WebSocket

from app.core.store import RunNotFound
from app.runtime import RunService

router = APIRouter(prefix="/api/runs")


@router.websocket("/{run_id}/input")
async def websocket_stub(websocket: WebSocket, run_id: str) -> None:
    # TODO Task 5/6: authenticate the session and wire preview frames / operator input.
    await websocket.accept()
    service = cast(RunService, websocket.app.state.service)
    try:
        await service.store.get(run_id)
    except RunNotFound:
        await websocket.close(code=4404, reason="Run not found.")
        return
    await websocket.close(code=1000, reason="Transport is not implemented yet.")
