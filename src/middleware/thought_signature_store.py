from __future__ import annotations

import asyncio
import contextlib
import logging
import time
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class ThoughtSignatureEntry:
    message_id: str
    reasoning_details: list[dict[str, Any]]
    tool_call_ids: frozenset
    timestamp: float
    conversation_id: str
    provider: str
    model: str


class ThoughtSignatureStore:
    def __init__(
        self,
        max_size: int = 1000,
        ttl_seconds: float = 3600.0,
        cleanup_interval: float = 300.0,
    ):
        self.max_size = max_size
        self.ttl_seconds = ttl_seconds
        self.cleanup_interval = cleanup_interval

        self._entries: dict[str, ThoughtSignatureEntry] = {}
        self._tool_call_index: dict[str, set[str]] = {}
        self._conversation_index: dict[str, set[str]] = {}

        self._cleanup_task: asyncio.Task | None = None
        self._lock = asyncio.Lock()

        self.logger = logging.getLogger(f"{__name__}.ThoughtSignatureStore")

    async def start(self) -> None:
        if self._cleanup_task is None:
            self._cleanup_task = asyncio.create_task(self._cleanup_loop())

    async def stop(self) -> None:
        if self._cleanup_task:
            self._cleanup_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._cleanup_task
            self._cleanup_task = None

    async def store(self, entry: ThoughtSignatureEntry) -> None:
        async with self._lock:
            if len(self._entries) >= self.max_size:
                await self._evict_oldest()

            if entry.message_id in self._entries:
                await self._remove_entry(entry.message_id)

            self._entries[entry.message_id] = entry

            for tool_call_id in entry.tool_call_ids:
                self._tool_call_index.setdefault(tool_call_id, set()).add(entry.message_id)

            self._conversation_index.setdefault(entry.conversation_id, set()).add(entry.message_id)

    async def retrieve_by_tool_calls(
        self,
        tool_call_ids: set[str],
        *,
        conversation_id: str | None = None,
    ) -> list[dict[str, Any]] | None:
        """Retrieve reasoning_details for tool_call_ids.

        Supports incremental/partial sets by using **any-match** semantics and
        choosing the **most recent** valid entry among candidates.

        If conversation_id is provided, the match is scoped to that conversation.
        """
        if not tool_call_ids:
            return None

        async with self._lock:
            candidates: set[str] = set()
            for tool_call_id in tool_call_ids:
                msg_ids = self._tool_call_index.get(tool_call_id)
                if msg_ids:
                    candidates |= msg_ids

            if not candidates:
                return None

            if conversation_id is not None:
                conv_ids = self._conversation_index.get(conversation_id)
                if not conv_ids:
                    return None
                candidates &= conv_ids
                if not candidates:
                    return None

            best: ThoughtSignatureEntry | None = None
            for message_id in candidates:
                entry = self._entries.get(message_id)
                if not entry or not self._is_entry_valid(entry):
                    continue
                if best is None or entry.timestamp > best.timestamp:
                    best = entry

            if best is None:
                return None

            return best.reasoning_details

    async def retrieve_by_conversation(self, conversation_id: str) -> list[ThoughtSignatureEntry]:
        async with self._lock:
            message_ids = self._conversation_index.get(conversation_id)
            if not message_ids:
                return []

            out: list[ThoughtSignatureEntry] = []
            for message_id in message_ids.copy():
                entry = self._entries.get(message_id)
                if entry and self._is_entry_valid(entry):
                    out.append(entry)
            return out

    async def clear_conversation(self, conversation_id: str) -> None:
        async with self._lock:
            message_ids = self._conversation_index.get(conversation_id)
            if not message_ids:
                return
            for message_id in message_ids.copy():
                await self._remove_entry(message_id)

    async def get_stats(self) -> dict[str, Any]:
        async with self._lock:
            return {
                "total_entries": len(self._entries),
                "conversations": len(self._conversation_index),
                "tool_calls": len(self._tool_call_index),
                "max_size": self.max_size,
                "ttl_seconds": self.ttl_seconds,
            }

    async def _remove_entry(self, message_id: str) -> None:
        entry = self._entries.get(message_id)
        if not entry:
            return

        del self._entries[message_id]

        for tool_call_id in entry.tool_call_ids:
            msg_ids = self._tool_call_index.get(tool_call_id)
            if msg_ids is None:
                continue
            msg_ids.discard(message_id)
            if not msg_ids:
                del self._tool_call_index[tool_call_id]

        conv_ids = self._conversation_index.get(entry.conversation_id)
        if conv_ids is not None:
            conv_ids.discard(message_id)
            if not conv_ids:
                del self._conversation_index[entry.conversation_id]

    async def _evict_oldest(self) -> None:
        if not self._entries:
            return

        sorted_entries = sorted(self._entries.items(), key=lambda x: x[1].timestamp)
        to_evict = max(1, len(sorted_entries) // 10)
        for message_id, _ in sorted_entries[:to_evict]:
            await self._remove_entry(message_id)

    def _is_entry_valid(self, entry: ThoughtSignatureEntry) -> bool:
        return (time.time() - entry.timestamp) < self.ttl_seconds

    async def _cleanup_loop(self) -> None:
        while True:
            try:
                await asyncio.sleep(self.cleanup_interval)
                await self._cleanup_expired()
            except asyncio.CancelledError:
                break
            except Exception:
                self.logger.exception("Error in cleanup loop")

    async def _cleanup_expired(self) -> None:
        async with self._lock:
            expired = [mid for mid, e in self._entries.items() if not self._is_entry_valid(e)]
            for message_id in expired:
                await self._remove_entry(message_id)
