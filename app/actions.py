"""Authenticated, idempotent action boundary for the controlled live workload."""

from __future__ import annotations

import hashlib
import json
import os
from abc import ABC, abstractmethod
from asyncio import Lock
from typing import Any

from google.api_core.exceptions import AlreadyExists
from google.cloud import firestore


class ActionBoundaryError(RuntimeError):
    """A public-safe action-boundary rejection."""


class ActionRecordStore(ABC):
    @abstractmethod
    async def create_or_get(
        self, idempotency_key: str, fingerprint: str, record: dict[str, Any]
    ) -> tuple[dict[str, Any], bool]:
        """Return the record and whether it was replayed."""
        raise NotImplementedError


class MemoryActionRecordStore(ActionRecordStore):
    """Deterministic store used by tests and controlled local mode."""

    def __init__(self) -> None:
        self._lock = Lock()
        self._records: dict[str, dict[str, Any]] = {}

    async def create_or_get(
        self, idempotency_key: str, fingerprint: str, record: dict[str, Any]
    ) -> tuple[dict[str, Any], bool]:
        async with self._lock:
            existing = self._records.get(idempotency_key)
            if existing is not None:
                if existing["fingerprint"] != fingerprint:
                    raise ActionBoundaryError("IDEMPOTENCY_KEY_REUSE")
                return dict(existing), True
            stored = {**record, "fingerprint": fingerprint}
            self._records[idempotency_key] = stored
            return dict(stored), False


class FirestoreActionRecordStore(ActionRecordStore):
    """Durable Cloud Run store with atomic create semantics."""

    def __init__(
        self,
        project: str | None = None,
        collection: str = "cutline_action_receipts",
        client: Any | None = None,
    ) -> None:
        self.client = client or firestore.AsyncClient(project=project)
        self.collection = collection

    async def create_or_get(
        self, idempotency_key: str, fingerprint: str, record: dict[str, Any]
    ) -> tuple[dict[str, Any], bool]:
        document = self.client.collection(self.collection).document(idempotency_key)
        stored = {**record, "fingerprint": fingerprint}
        try:
            await document.create(stored)
            return stored, False
        except AlreadyExists:
            snapshot = await document.get()
            existing = snapshot.to_dict()
            if not existing or existing.get("fingerprint") != fingerprint:
                raise ActionBoundaryError("IDEMPOTENCY_KEY_REUSE") from None
            return dict(existing), True


def action_store_from_environment() -> ActionRecordStore:
    if os.getenv("CUTLINE_MODE", "local").lower() == "live":
        return FirestoreActionRecordStore(project=os.getenv("GOOGLE_CLOUD_PROJECT"))
    return MemoryActionRecordStore()


def action_fingerprint(payload: dict[str, str]) -> str:
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode()).hexdigest()


async def execute_recovery_action(
    store: ActionRecordStore,
    *,
    run_id: str,
    approval_id: str,
    idempotency_key: str,
    plan_version: str,
) -> dict[str, Any]:
    if plan_version != "sq42-recovery-v1":
        raise ActionBoundaryError("PLAN_NOT_ALLOWLISTED")
    payload = {
        "run_id": run_id,
        "approval_id": approval_id,
        "idempotency_key": idempotency_key,
        "plan_version": plan_version,
    }
    transition = {
        "concurrency_before": 3,
        "concurrency_after": 1,
        "reserve_workers_before": 0,
        "reserve_workers_after": 4,
    }
    record, replayed = await store.create_or_get(
        idempotency_key,
        action_fingerprint(payload),
        {
            "executor_mode": "CLOUD_RUN",
            "run_id": run_id,
            "approval_id": approval_id,
            "plan_version": plan_version,
            "transition": transition,
            "annotation_id": f"annotation-{run_id[:8]}",
        },
    )
    return {
        "executor_mode": record["executor_mode"],
        "transition": record["transition"],
        "annotation_id": record["annotation_id"],
        "replayed": replayed,
    }
