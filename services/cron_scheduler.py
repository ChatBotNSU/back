"""
Background cron scheduler — fires flows whose start_node is a `cron_trigger`.

Runs as a long-lived asyncio task started from the FastAPI lifespan. Every
`tick_seconds` it walks all known flows, finds those whose entry node is a
cron_trigger, and starts a fresh Session via `engine.runner.start_flow` when
the cron expression's next scheduled time has passed since the last fire.

Last-fire timestamps are stored in `flow.metadata['__cron_last_fired__']` so
restarts don't replay missed windows infinitely (they replay at most once).
"""
from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone
from typing import Any

from engine.loader import make_flow_loader
from engine.runner import start_flow
from models.flow import Flow
from models.node import NodeType
from models.session import Session

logger = logging.getLogger(__name__)


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _cron_nodes(flow: Flow) -> list:
    """All cron_trigger nodes in `flow` — they are independent entry points,
    not just start_node candidates."""
    return [n for n in flow.nodes.values() if n.type == NodeType.CRON_TRIGGER]


def _is_due(cron_expr: str, last_fired_iso: str | None, now: datetime) -> bool:
    """A cron is due when the most recent scheduled tick has passed since the
    last recorded fire. On first-ever evaluation we just record the boundary
    and don't backfill."""
    from croniter import croniter  # type: ignore

    if not croniter.is_valid(cron_expr):
        return False

    if not last_fired_iso:
        # First time we see this flow — don't backfire, just plant a marker
        # at the *previous* scheduled tick so we fire at the next one.
        return False

    try:
        last_fired = datetime.fromisoformat(last_fired_iso)
    except ValueError:
        return False

    # Next scheduled run after last_fired; if that's already in the past, it's due.
    it = croniter(cron_expr, last_fired)
    next_fire: datetime = it.get_next(datetime)
    return next_fire <= now


class CronScheduler:
    def __init__(
        self,
        flow_store: Any,
        session_store: Any,
        tick_seconds: float = 30.0,
    ) -> None:
        self.flow_store = flow_store
        self.session_store = session_store
        self.tick_seconds = tick_seconds
        self._task: asyncio.Task | None = None
        self._stop = asyncio.Event()

    def start(self) -> None:
        if self._task is not None:
            return
        self._stop.clear()
        self._task = asyncio.create_task(self._run(), name="cron-scheduler")
        logger.info("Cron scheduler started (tick=%ss)", self.tick_seconds)

    async def stop(self) -> None:
        self._stop.set()
        if self._task is not None:
            await asyncio.wait([self._task], timeout=5)
            self._task = None

    async def _run(self) -> None:
        # Small startup delay so the API has time to settle before we hammer
        # the store on first tick.
        try:
            await asyncio.wait_for(self._stop.wait(), timeout=5)
            return
        except asyncio.TimeoutError:
            pass

        while not self._stop.is_set():
            try:
                await self._tick()
            except Exception:  # noqa: BLE001
                logger.exception("Cron scheduler tick failed")
            try:
                await asyncio.wait_for(self._stop.wait(), timeout=self.tick_seconds)
            except asyncio.TimeoutError:
                continue

    async def _tick(self) -> None:
        flows = await self.flow_store.list_all(limit=1000)
        now = _now()
        loader = make_flow_loader(self.flow_store)

        for flow in flows:
            cron_nodes = _cron_nodes(flow)
            if not cron_nodes:
                continue

            # Per-node last-fired markers — multiple cron nodes in one flow can
            # tick on independent schedules without stepping on each other.
            markers: dict[str, str] = flow.metadata.get("__cron_last_fired__", {}) or {}
            if isinstance(markers, str):
                # Legacy format (single timestamp for the whole flow) — migrate
                # by treating it as the marker for every cron node currently in
                # the flow.
                markers = {n.id: markers for n in cron_nodes}
            dirty = False

            for node in cron_nodes:
                cron_expr = str(node.config.get("cron", "")).strip()
                if not cron_expr:
                    continue
                last = markers.get(node.id)
                if not _is_due(cron_expr, last, now):
                    if not last:
                        markers[node.id] = now.isoformat()
                        dirty = True
                    continue
                await self._fire(flow, node.id, loader)
                markers[node.id] = now.isoformat()
                dirty = True

            if dirty:
                flow.metadata["__cron_last_fired__"] = markers
                await self.flow_store.save(flow)

    async def _fire(self, flow: Flow, entry_node: str, loader: Any) -> None:
        logger.info("Firing cron flow %s entry %s", flow.id, entry_node)
        session = Session(
            flow_id=flow.id,
            workspace_id=flow.workspace_id,
            project_id=flow.project_id,
        )
        # Preload variables that user-facing sessions have left behind, so a
        # nightly job can read e.g. {currency} set during a /usd command.
        shared = flow.metadata.get("__shared_vars__") or {}
        if isinstance(shared, dict):
            session.variables.update(shared)
        session.variables.update({
            "channel": "cron",
            "fired_at": _now().isoformat(),
            "__session_key__": f"cron:{flow.id}:{entry_node}:{int(_now().timestamp())}",
        })
        try:
            session = await start_flow(session, flow, flow_loader=loader, entry_node=entry_node)
        except Exception:  # noqa: BLE001
            logger.exception("Cron flow %s crashed", flow.id)
            return
        try:
            await self.session_store.save(session)
        except Exception:  # noqa: BLE001
            logger.exception("Cron flow %s: failed to persist session", flow.id)
