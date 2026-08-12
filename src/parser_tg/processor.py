from __future__ import annotations

import asyncio
import hashlib
import logging
from dataclasses import dataclass
from typing import Any, Protocol

from parser_tg.matcher import Matcher
from parser_tg.state import StateStore

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class IncomingItem:
    source_id: str
    source_title: str
    source_username: str | None
    item_key: str
    message_ids: tuple[int, ...]
    link_message_id: int
    text: str
    messages: tuple[Any, ...]


class Delivery(Protocol):
    async def deliver(self, item: IncomingItem, filter_ids: tuple[str, ...]) -> str: ...


class Processor:
    def __init__(self, matcher: Matcher, state: StateStore, delivery: Delivery) -> None:
        self._matcher = matcher
        self._state = state
        self._delivery = delivery
        self._lock = asyncio.Lock()

    async def process(self, item: IncomingItem) -> str:
        content_hash = hashlib.sha256(item.text.encode("utf-8")).hexdigest()
        async with self._lock:
            previous = self._state.get(item.source_id, item.item_key)
            if previous is not None and previous.status == "forwarded":
                return "already_forwarded"
            if (
                previous is not None
                and previous.status == "no_match"
                and previous.content_hash == content_hash
            ):
                return "unchanged_no_match"

            matches = self._matcher.match(item.text)
            filter_ids = tuple(match.filter_id for match in matches)
            if not matches:
                self._state.put(item.source_id, item.item_key, content_hash, "no_match")
                logger.info(
                    "source=%s item=%s result=no_match",
                    item.source_id,
                    item.item_key,
                )
                return "no_match"

            try:
                delivery_kind = await self._delivery.deliver(item, filter_ids)
            except Exception:
                self._state.put(
                    item.source_id,
                    item.item_key,
                    content_hash,
                    "delivery_failed",
                    filter_ids,
                )
                raise
            self._state.put(
                item.source_id,
                item.item_key,
                content_hash,
                "forwarded",
                filter_ids,
                delivery_kind,
            )
            logger.info(
                "source=%s item=%s result=%s filters=%s",
                item.source_id,
                item.item_key,
                delivery_kind,
                ",".join(filter_ids),
            )
            return delivery_kind
