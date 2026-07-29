"""Per-client uid interest refcounting and global selector separation.

Implements SR-001 through SR-004 from system-architecture.md §5:
  SR-001: refcount uid interest; ADD on 0→1, DELETE on 1→0
  SR-002: abrupt disconnect decrements that client's full interest set
  SR-003: reconcile the full interest set after a selector restart —
    `reconcile()` below computes the replay set; server.py's
    `_on_publication_matched` calls it when the ValueRequest writer's match
    count rises from 0 (on_publication_matched, since that topic is VOLATILE
    and an earlier write would be discarded), sending PERIOD before the ADD
    burst so no tag is briefly at the wrong rate
  SR-004: per-client demux — don't forward samples to uninterested clients


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
AddCallback = Callable[[int], None]        # uid → send ADD
DeleteCallback = Callable[[int], None]     # uid → send DELETE
PeriodCallback = Callable[[int], None]     # min_separation_ms → send PERIOD


def _require_positive_separation(min_separation_ms: int) -> None:
    # Must be > 0. PERIOD with period_ms == 0 means "restore the selector's own
    # default" on the ValueRequest contract (dds/idl/PlcValue.idl), so 0 here
    # would make a command send something other than what it appears to. This
    # is the canonical statement of the rule — config.py, server.py, and
    # config.yaml each re-validate it at their own layer but should point here
    # rather than restate it.
    if min_separation_ms <= 0:
        raise ValueError("min_separation_ms must be > 0")


@dataclass
class ClientInterest:
    """Tracks one client's subscribed uid set."""
    client_id: str
    uids: set[int] = field(default_factory=set)


class InterestManager:
    """Manages per-uid refcounts across all connected web clients.

    Usage:
        mgr = InterestManager(on_add=send_add, on_delete=send_delete, on_period=send_period)
        mgr.client_subscribe("client_1", uid=5)   # fires ADD(5)
        mgr.set_min_separation(100)               # fires PERIOD(100) once
        mgr.client_unsubscribe("client_1", uid=5) # fires DELETE
    """

    def __init__(
        self,
        on_add: AddCallback | None = None,
        on_delete: DeleteCallback | None = None,
        on_period: PeriodCallback | None = None,
        min_separation_ms: int = 250,
    ):
        _require_positive_separation(min_separation_ms)
        self._on_add = on_add
        self._on_delete = on_delete
        self._on_period = on_period
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
                self._on_add(uid)

    def set_min_separation(self, min_separation_ms: int) -> None:
        """Update the global selector minimum separation (fires PERIOD once)."""
        _require_positive_separation(min_separation_ms)
        if min_separation_ms == self._min_separation_ms:
            return
        self._min_separation_ms = min_separation_ms
        logger.info("interest_min_separation_update period_ms=%d active_uids=%d",
                    min_separation_ms, len(self._refcounts))
        if self._on_period:
            self._on_period(min_separation_ms)

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
        """SR-003: active uids and periods, for replay after a selector restart.

        Called from server.py's `_on_publication_matched` when the
        ValueRequest writer's match count rises from 0. The caller sends a
        PERIOD command before replaying these as ADDs.
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
