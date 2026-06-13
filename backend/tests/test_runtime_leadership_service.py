from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta
import os
import tempfile

import pytest
from sqlmodel import Session, create_engine, select

from app import main
from app.db.migrations import ensure_database_schema_current
from app.models.runtime_leadership import RuntimeLease
from app.services import runtime_leadership_service
from app.services.runtime_leadership_service import (
    RuntimeLeadershipFenceError,
    RuntimeLeadershipService,
    activate_runtime_leadership,
    deactivate_runtime_leadership,
    hold_active_runtime_leadership_fence,
)


def _engine():
    fd, raw_path = tempfile.mkstemp(suffix=".sqlite")
    os.close(fd)
    engine = create_engine(
        f"sqlite:///{raw_path}",
        connect_args={"check_same_thread": False},
    )
    ensure_database_schema_current(engine)
    return engine


def _session() -> Session:
    return Session(_engine())


def test_audit_runtime_001_live_runtime_leader_lease_blocks_duplicate_owner():
    session = _session()
    now = datetime(2026, 5, 8, 10, 0, tzinfo=UTC)

    first = RuntimeLeadershipService(session, owner_id="worker-a").acquire(
        now=now,
        ttl=timedelta(seconds=30),
    )
    duplicate = RuntimeLeadershipService(session, owner_id="worker-b").acquire(
        now=now + timedelta(seconds=5),
        ttl=timedelta(seconds=30),
    )

    assert first.acquired is True
    assert first.generation == 1
    assert duplicate.acquired is False
    assert duplicate.current_owner_id == "worker-a"
    assert duplicate.generation == 1

    leases = session.exec(select(RuntimeLease)).all()
    assert len(leases) == 1
    assert leases[0].owner_id == "worker-a"

    session.close()


def test_audit_runtime_001_lifespan_skips_autonomous_loops_without_leadership(
    monkeypatch,
):
    test_engine = _engine()
    now = datetime.now(UTC)
    with Session(test_engine) as session:
        RuntimeLeadershipService(session, owner_id="worker-a").acquire(
            now=now,
            ttl=timedelta(seconds=30),
        )

    def fail_recovery(_session):
        raise AssertionError("duplicate startup must not run runtime recovery")

    def fail_market_data_service(**_kwargs):
        raise AssertionError("duplicate startup must not construct market-data loop")

    class StreamingDisabled:
        def is_enabled(self):
            return False

    class Health:
        def heartbeat(self):
            return None

    monkeypatch.setattr(main, "engine", test_engine)
    monkeypatch.setattr(main, "initialize_database", lambda: None)
    monkeypatch.setattr(
        main, "_make_runtime_leader_owner_id", lambda: "worker-b", raising=False
    )
    monkeypatch.setattr(main, "RuntimeRecoveryService", fail_recovery)
    monkeypatch.setattr(main, "MarketDataService", fail_market_data_service)
    monkeypatch.setattr(main, "get_ig_streaming_service", lambda: StreamingDisabled())
    monkeypatch.setattr(main, "get_health_service", lambda: Health())

    async def run_lifespan() -> None:
        async with main.lifespan(None):
            await asyncio.sleep(0)

    asyncio.run(run_lifespan())


def test_audit_runtime_001_lifespan_releases_leader_lease_on_shutdown(monkeypatch):
    test_engine = _engine()
    calls = {
        "recovery": 0,
        "market_data": 0,
        "reconciliation": 0,
        "heartbeat": 0,
    }

    class Recovery:
        def __init__(self, _session):
            pass

        def recover(self):
            calls["recovery"] += 1

    class MarketData:
        def __init__(self, **_kwargs):
            calls["market_data"] += 1

        async def run(self):
            await asyncio.Event().wait()

    class Reconciliation:
        async def run(self):
            calls["reconciliation"] += 1
            await asyncio.Event().wait()

    class StreamingDisabled:
        def is_enabled(self):
            return False

    class Health:
        def heartbeat(self):
            calls["heartbeat"] += 1

    monkeypatch.setattr(main, "engine", test_engine)
    monkeypatch.setattr(main, "initialize_database", lambda: None)
    monkeypatch.setattr(main, "_make_runtime_leader_owner_id", lambda: "worker-a")
    monkeypatch.setattr(main, "RuntimeRecoveryService", Recovery)
    monkeypatch.setattr(main, "MarketDataService", MarketData)
    monkeypatch.setattr(main, "BrokerReconciliationSupervisor", Reconciliation)
    monkeypatch.setattr(main, "get_ig_streaming_service", lambda: StreamingDisabled())
    monkeypatch.setattr(main, "get_health_service", lambda: Health())

    async def run_lifespan() -> None:
        async with main.lifespan(None):
            await asyncio.sleep(0)

    asyncio.run(run_lifespan())

    with Session(test_engine) as session:
        lease = session.get(RuntimeLease, RuntimeLeadershipService.RUNTIME_LEASE_NAME)

    assert calls["recovery"] == 1
    assert calls["market_data"] == 1
    assert calls["reconciliation"] == 1
    assert calls["heartbeat"] >= 1
    assert lease is not None
    assert lease.owner_id == "worker-a"
    assert lease.released_at is not None


def test_audit_runtime_001_expired_runtime_leader_lease_can_be_taken_over():
    session = _session()
    now = datetime(2026, 5, 8, 10, 0, tzinfo=UTC)

    RuntimeLeadershipService(session, owner_id="worker-a").acquire(
        now=now,
        ttl=timedelta(seconds=30),
    )
    takeover = RuntimeLeadershipService(session, owner_id="worker-b").acquire(
        now=now + timedelta(seconds=31),
        ttl=timedelta(seconds=30),
    )

    assert takeover.acquired is True
    assert takeover.generation == 2

    lease = session.get(RuntimeLease, RuntimeLeadershipService.RUNTIME_LEASE_NAME)
    assert lease is not None
    assert lease.owner_id == "worker-b"
    assert lease.generation == 2
    assert lease.acquired_at == (now + timedelta(seconds=31)).replace(tzinfo=None)

    session.close()


def test_audit_runtime_002_stale_generation_cannot_renew_or_release_after_takeover():
    session = _session()
    now = datetime(2026, 5, 8, 10, 0, tzinfo=UTC)

    first = RuntimeLeadershipService(session, owner_id="worker-a").acquire(
        now=now,
        ttl=timedelta(seconds=30),
    )
    takeover = RuntimeLeadershipService(session, owner_id="worker-b").acquire(
        now=now + timedelta(seconds=31),
        ttl=timedelta(seconds=30),
    )

    assert first.generation == 1
    assert takeover.generation == 2
    assert (
        RuntimeLeadershipService(session, owner_id="worker-a").renew(
            generation=first.generation,
            now=now + timedelta(seconds=32),
        )
        is False
    )
    assert (
        RuntimeLeadershipService(session, owner_id="worker-a").release(
            generation=first.generation,
            now=now + timedelta(seconds=32),
        )
        is False
    )

    lease = session.get(RuntimeLease, RuntimeLeadershipService.RUNTIME_LEASE_NAME)
    assert lease is not None
    assert lease.owner_id == "worker-b"
    assert lease.generation == 2
    assert lease.released_at is None
    session.close()


def test_audit_runtime_002_stale_generation_fails_broker_mutation_fence(monkeypatch):
    test_engine = _engine()
    now = datetime(2026, 5, 8, 10, 0, tzinfo=UTC)
    with Session(test_engine) as session:
        first = RuntimeLeadershipService(session, owner_id="worker-a").acquire(
            now=now,
            ttl=timedelta(seconds=30),
        )
        RuntimeLeadershipService(session, owner_id="worker-b").acquire(
            now=now + timedelta(seconds=31),
            ttl=timedelta(seconds=30),
        )

    assert first.generation == 1
    monkeypatch.setattr(runtime_leadership_service, "engine", test_engine)
    activate_runtime_leadership(owner_id="worker-a", generation=first.generation)
    try:
        with pytest.raises(
            RuntimeLeadershipFenceError,
            match="leadership changed",
        ):
            with hold_active_runtime_leadership_fence():
                pass
    finally:
        deactivate_runtime_leadership(
            owner_id="worker-a",
            generation=first.generation,
        )


def test_audit_runtime_002_current_generation_holds_broker_mutation_fence(monkeypatch):
    test_engine = _engine()
    now = datetime.now(UTC)
    with Session(test_engine) as session:
        acquisition = RuntimeLeadershipService(
            session,
            owner_id="worker-a",
        ).acquire(now=now, ttl=timedelta(seconds=30))

    assert acquisition.generation == 1
    monkeypatch.setattr(runtime_leadership_service, "engine", test_engine)
    activate_runtime_leadership(
        owner_id="worker-a",
        generation=acquisition.generation,
    )
    try:
        with hold_active_runtime_leadership_fence() as active:
            assert active.owner_id == "worker-a"
            assert active.generation == acquisition.generation
    finally:
        deactivate_runtime_leadership(
            owner_id="worker-a",
            generation=acquisition.generation,
        )
