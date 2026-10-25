from app.core.emitter import FanoutEventEmitter
from app.core.state import RunStateMachine, RunStatus
from app.core.store import InMemoryRunStore


async def test_labeled_credentials_are_not_in_started_event() -> None:
    store = InMemoryRunStore()
    emitter = FanoutEventEmitter(store)
    fake_password = "fake-demo-password-canary"
    run = await store.create("Local login: password=" + fake_password, "headless")
    machine = RunStateMachine(run.runId, store, emitter)
    await machine.transition(RunStatus.PLANNING)
    events = await store.list_events(run.runId)
    assert events[0].type == "run.started"
    assert fake_password not in events[0].model_dump_json()
    assert "[redacted]" in events[0].data.goal
