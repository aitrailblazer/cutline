from unittest.mock import AsyncMock, Mock

import pytest
from google.api_core.exceptions import AlreadyExists

from app.actions import (
    ActionBoundaryError,
    FirestoreActionRecordStore,
    MemoryActionRecordStore,
    action_fingerprint,
    action_store_from_environment,
    execute_recovery_action,
)


@pytest.mark.asyncio
async def test_memory_action_store_success_replay_and_conflict():
    store = MemoryActionRecordStore()
    payload = {
        "run_id": "run-12345678",
        "approval_id": "approval-12345678",
        "idempotency_key": "key-12345678",
        "plan_version": "sq42-recovery-v1",
    }
    first = await execute_recovery_action(store, **payload)
    replay = await execute_recovery_action(store, **payload)
    assert first["executor_mode"] == "CLOUD_RUN"
    assert first["transition"]["concurrency_after"] == 1
    assert first["replayed"] is False
    assert replay["replayed"] is True
    with pytest.raises(ActionBoundaryError, match="IDEMPOTENCY_KEY_REUSE"):
        await execute_recovery_action(
            store, **{**payload, "approval_id": "approval-different"}
        )


@pytest.mark.asyncio
async def test_action_rejects_unknown_plan():
    with pytest.raises(ActionBoundaryError, match="PLAN_NOT_ALLOWLISTED"):
        await execute_recovery_action(
            MemoryActionRecordStore(),
            run_id="run-12345678",
            approval_id="approval-12345678",
            idempotency_key="key-12345678",
            plan_version="unknown",
        )


@pytest.mark.asyncio
async def test_firestore_action_store_create_replay_and_conflict():
    document = Mock()
    document.create = AsyncMock()
    document.get = AsyncMock()
    collection = Mock()
    collection.document.return_value = document
    client = Mock()
    client.collection.return_value = collection
    store = FirestoreActionRecordStore(client=client)
    record = {"executor_mode": "CLOUD_RUN"}
    created, replayed = await store.create_or_get("key", "fingerprint", record)
    assert created["fingerprint"] == "fingerprint"
    assert replayed is False

    document.create.side_effect = AlreadyExists("exists")
    snapshot = Mock()
    snapshot.to_dict.return_value = created
    document.get.return_value = snapshot
    existing, replayed = await store.create_or_get("key", "fingerprint", record)
    assert existing == created
    assert replayed is True

    snapshot.to_dict.return_value = None
    with pytest.raises(ActionBoundaryError, match="IDEMPOTENCY_KEY_REUSE"):
        await store.create_or_get("key", "different", record)


def test_action_store_factory_and_fingerprint(monkeypatch):
    monkeypatch.setenv("CUTLINE_MODE", "local")
    assert isinstance(action_store_from_environment(), MemoryActionRecordStore)
    assert action_fingerprint({"b": "2", "a": "1"}) == action_fingerprint(
        {"a": "1", "b": "2"}
    )

    sentinel = object()
    monkeypatch.setenv("CUTLINE_MODE", "live")
    monkeypatch.setenv("GOOGLE_CLOUD_PROJECT", "project")
    monkeypatch.setattr(
        "app.actions.FirestoreActionRecordStore",
        lambda project: (sentinel, project),
    )
    assert action_store_from_environment() == (sentinel, "project")
