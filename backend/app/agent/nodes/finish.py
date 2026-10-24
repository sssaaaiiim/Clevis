from typing import Any

from app.agent.context import current_context, sanitized_graph_error
from app.agent.state import AgentState
from app.core.state import TERMINAL_STATES, RunStatus


async def finish_node(state: AgentState) -> dict[str, Any]:
    try:
        return await _finish(state)
    except Exception as exc:
        raise sanitized_graph_error(exc, current_context.get()) from None


async def _finish(state: AgentState) -> dict[str, Any]:
    context = current_context.get()
    run = await context.store.get(state.run_id)
    if run.status in TERMINAL_STATES:
        state.status = run.status.value
        return context.sync(state)
    if state.error:
        await context.machine.transition(RunStatus.FAILED, error=state.error)
        state.status = "failed"
    elif state.status == "stopped":
        await context.machine.transition(RunStatus.STOPPED)
    else:
        await context.execution.checkpoint()
        if state.turn_epoch != context.machine.resume_count:
            state.result = None
            state.reroute = True
            return context.sync(state)
        async with context.machine.control_lock:
            if (await context.store.get(state.run_id)).status != RunStatus.RUNNING:
                state.reroute = True
                return context.sync(state)
            if context.preview is not None:
                await context.execution.call(context.preview.stop_stream)
            await context.execution.call(context.driver.close)
            context.closed = True
            await context.execution.finish(state.result or "Task finished.")
            state.status = "finished"
    return context.sync(state)
