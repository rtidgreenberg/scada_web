"""Per-client uid interest refcounting and global selector separation.

Implements SR-001, SR-002 and SR-004 from system-architecture.md §5:
  SR-001: refcount uid interest; ADD on 0→1, DELETE on 1→0
  SR-002: abrupt disconnect decrements that client's full interest set
  SR-004: per-client demux — don't forward samples to uninterested clients

SR-003 (reconcile the full interest set after a selector restart) is NOT
implemented. `reconcile()` below computes the replay set but has no caller:
nothing detects a selector restart. Its symptom is a permanently blank display
(system-architecture.md §5, SR-003). Two things are needed and neither exists
yet — a trigger (on_publication_matched on the ValueRequest writer, since that
topic is VOLATILE and an earlier write would be discarded), and a PERIOD replay
that server.py's _last_period_ms currently suppresses. Treat reconcile() as
scaffolding until both land.


The InterestManager is the single source of truth for "which uids are
currently active system-wide", "which clients want which uids", and the current
global minimum separation used by selector ADD commands.
"""

from __future__ import annotations

import logging
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Callable

logger = logging.getLogger(__name__)

# Callback types for upstream actions
AddCallback = Callable[[int, int], None]  # uid, min_separation_ms → send ADD
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
        mgr.client_subscribe("client_1", uid=5)   # fires ADD(5, current period)
        mgr.set_min_separation(100)               # fires ADD(5, 100)
        mgr.client_unsubscribe("client_1", uid=5) # fires DELETE
    """

    def __init__(
        self,
        on_add: AddCallback | None = None,
        on_delete: DeleteCallback | None = None,
        min_separation_ms: int = 250,
    ):
        if min_separation_ms <= 0:
            # 0 is not "no rate limit": the selector reads PERIOD 0 as "restore
            # your configured default" (dds/idl/PlcValue.idl). Web clients
            # cannot request the full field rate, so 0 never leaves here.
            raise ValueError("min_separation_ms must be > 0")
        self._on_add = on_add
        self._on_delete = on_delete
        self._min_separation_ms = min_separation_ms
        self._refcounts: dict[int, int] = defaultdict(int)  # uid → count
        self._clients: dict[str, ClientInterest] = {}       # client_id → interest

    def client_subscribe(self, client_id: str, uid: int) -> None:
        """Client expresses interest in a uid. ADD on 0→1 transition."""
        client = self._ensure_client(client_id)
        if uid in client.uids:
            return
        client.uids.add(uid)
        self._refcounts[uid] += 1
        if self._refcounts[uid] == 1:
            logger.info("interest_add uid=%d client=%s", uid, client_id)
            if self._on_add:
                self._on_add(uid, self._min_separation_ms)

    def set_min_separation(self, min_separation_ms: int) -> None:
        """Update the global selector minimum separation for all active uids."""
        if min_separation_ms <= 0:
            # 0 is not "no rate limit": the selector reads PERIOD 0 as "restore
            # your configured default" (dds/idl/PlcValue.idl). Web clients
            # cannot request the full field rate, so 0 never leaves here.
            raise ValueError("min_separation_ms must be > 0")
        if min_separation_ms == self._min_separation_ms:
            return
        self._min_separation_ms = min_separation_ms
        logger.info("interest_min_separation_update period_ms=%d active_uids=%d",
                    min_separation_ms, len(self._refcounts))
        if self._on_add:
            for uid in sorted(self._refcounts):
                self._on_add(uid, min_separation_ms)

    def client_unsubscribe(self, client_id: str, uid: int) -> None:
        """Client drops interest in a uid. DELETE on 1→0 transition."""
        client = self._clients.get(client_id)
        if client is None or uid not in client.uids:
            return
        client.uids.remove(uid)
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

    @property
    def min_separation_ms(self) -> int:
        """Current global selector minimum separation."""
        return self._min_separation_ms

    def active_periods(self) -> dict[int, int]:
        """Active uids mapped to the current global minimum separation."""
        return {uid: self._min_separation_ms for uid in self.active_uids()}

    def reconcile(self) -> dict[int, int]:
        """SR-003 scaffolding: active uids and periods for a selector restart.

        No caller — see the module docstring. Wiring this up is not sufficient on
        its own to satisfy SR-003.
        """
        periods = dict(sorted(self.active_periods().items()))
        logger.info("interest_reconcile uids=%d", len(periods))
        return periods

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
