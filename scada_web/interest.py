"""Per-client uid interest refcounting.

Implements SR-001 through SR-004 from system-architecture.md §5:
  SR-001: refcount uid interest; ADD on 0→1, DELETE on 1→0
  SR-002: abrupt disconnect decrements that client's full interest set
  SR-003: reconcile full interest set after selector restart
  SR-004: per-client demux — don't forward samples to uninterested clients

The InterestManager is the single source of truth for "which uids are
currently active system-wide" and "which clients want which uids."
"""

from __future__ import annotations

import logging
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Callable

logger = logging.getLogger(__name__)

# Callback types for upstream actions
AddCallback = Callable[[int], None]       # uid → send ADD to selector
DeleteCallback = Callable[[int], None]    # uid → send DELETE to selector


@dataclass
class ClientInterest:
    """Tracks one client's subscribed uid set."""
    client_id: str
    uids: set[int] = field(default_factory=set)


class InterestManager:
    """Manages per-uid refcounts across all connected web clients.

    Usage:
        mgr = InterestManager(on_add=send_add, on_delete=send_delete)
        mgr.client_subscribe("client_1", uid=5)   # fires on_add(5) if 0→1
        mgr.client_subscribe("client_2", uid=5)   # refcount 2, no ADD
        mgr.client_unsubscribe("client_1", uid=5) # refcount 1, no DELETE
        mgr.client_disconnect("client_2")          # refcount 0→fires on_delete(5)
    """

    def __init__(
        self,
        on_add: AddCallback | None = None,
        on_delete: DeleteCallback | None = None,
    ):
        self._on_add = on_add
        self._on_delete = on_delete
        self._refcounts: dict[int, int] = defaultdict(int)  # uid → count
        self._clients: dict[str, ClientInterest] = {}       # client_id → interest

    def client_subscribe(self, client_id: str, uid: int) -> None:
        """Client expresses interest in a uid. ADD on 0→1 transition."""
        client = self._ensure_client(client_id)
        if uid in client.uids:
            return  # already subscribed — idempotent
        client.uids.add(uid)
        self._refcounts[uid] += 1
        if self._refcounts[uid] == 1:
            logger.info("interest_add uid=%d (first client: %s)", uid, client_id)
            if self._on_add:
                self._on_add(uid)

    def client_unsubscribe(self, client_id: str, uid: int) -> None:
        """Client drops interest in a uid. DELETE on 1→0 transition."""
        client = self._clients.get(client_id)
        if client is None or uid not in client.uids:
            return
        client.uids.discard(uid)
        self._refcounts[uid] -= 1
        if self._refcounts[uid] <= 0:
            del self._refcounts[uid]
            logger.info("interest_delete uid=%d (last client: %s)", uid, client_id)
            if self._on_delete:
                self._on_delete(uid)

    def client_disconnect(self, client_id: str) -> None:
        """Client disconnected — decrement all its uids (SR-002)."""
        client = self._clients.pop(client_id, None)
        if client is None:
            return
        for uid in list(client.uids):
            self._refcounts[uid] -= 1
            if self._refcounts[uid] <= 0:
                del self._refcounts[uid]
                logger.info("interest_delete uid=%d (disconnect: %s)", uid, client_id)
                if self._on_delete:
                    self._on_delete(uid)

    def is_interested(self, client_id: str, uid: int) -> bool:
        """SR-004: check if a specific client wants this uid (for demux)."""
        client = self._clients.get(client_id)
        return client is not None and uid in client.uids

    def active_uids(self) -> set[int]:
        """The full set of uids with refcount > 0 (for SR-003 reconciliation)."""
        return set(self._refcounts.keys())

    def reconcile(self) -> list[int]:
        """SR-003: return the full active uid set for re-sending after selector restart."""
        uids = sorted(self.active_uids())
        logger.info("interest_reconcile uids=%d", len(uids))
        return uids

    def _ensure_client(self, client_id: str) -> ClientInterest:
        if client_id not in self._clients:
            self._clients[client_id] = ClientInterest(client_id=client_id)
        return self._clients[client_id]

    @property
    def client_count(self) -> int:
        return len(self._clients)

    @property
    def active_uid_count(self) -> int:
        return len(self._refcounts)
