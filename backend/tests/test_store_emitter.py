import asyncio
from datetime import datetime

import pytest

from app.core.emitter import FanoutEventEmitter
from app.core.events import EmptyData, EventType, make_event
from app.core.store import InMemoryRunStore, RunNotFound


async def test_fanout_replay_order_and_cleanup() -> None:
    store = InMemoryRunStore()
    emitter = FanoutEventEmitter(store)
    run = await store.create("test", "headless")
    event = make_event(run.runId, EventType.RUN_STOPPED, EmptyData())
    await emitter.emit(run.runId, event)
    async with emitter.subscribe(run.runId, after_seq=1) as first:
        async with emitter.subscribe(run.runId) as second:
            assert emitter.subscriber_count == 2
            assert (await second.queue.get()).seq == 1
            await asyncio.gather(*(emitter.emit(run.runId, event) for _ in range(20)))
            for seq in range(2, 22):
                a, b = await first.queue.get(), await second.queue.get()
                assert a.seq == b.seq == seq
                assert datetime.fromisoformat(a.ts.replace("Z", "+00:00")).tzinfo is not None
    assert emitter.subscriber_count == 0
    assert [e.seq for e in await store.list_events(run.runId, 18)] == [19, 20, 21]
    with pytest.raises(RuntimeError):
        async with emitter.subscribe(run.runId):
            raise RuntimeError("disconnect")
    assert emitter.subscriber_count == 0


async def test_store_copies_and_unknown_run() -> None:
    store = InMemoryRunStore()
    run = await store.create("original", "headed")
    run.goal = "changed locally"
    assert (await store.get(run.runId)).goal == "original"
    await store.update(run)
    assert (await store.get(run.runId)).goal == "changed locally"
    for operation in (store.get("missing"), store.list_events("missing")):
        with pytest.raises(RunNotFound):
            await operation
    with pytest.raises(ValueError, match="runId"):
        await store.append_event(run.runId, make_event("other", EventType.RUN_STOPPED, EmptyData()))


async def test_replay_and_live_subscription_race_has_no_gaps() -> None:
    store = InMemoryRunStore()
    emitter = FanoutEventEmitter(store)
    run = await store.create("test", "headless")
    event = make_event(run.runId, EventType.RUN_STOPPED, EmptyData())
    producer = asyncio.create_task(emitter.emit(run.runId, event))
    async with emitter.subscribe(run.runId) as sub:
        await producer
        assert (await sub.queue.get()).seq == 1
        assert sub.queue.empty()
