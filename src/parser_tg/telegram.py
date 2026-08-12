from __future__ import annotations

import asyncio
import contextlib
import logging
import signal
from pathlib import Path
from typing import Any

from telethon import TelegramClient, events
from telethon.errors import ChatForwardsRestrictedError, FloodWaitError, ServerError

from parser_tg.config import RulesConfig, Settings
from parser_tg.matcher import Matcher
from parser_tg.processor import IncomingItem, Processor
from parser_tg.state import StateStore

logger = logging.getLogger(__name__)


def message_link(source_id: str, username: str | None, message_id: int) -> str:
    if username:
        return f"https://t.me/{username.lstrip('@')}/{message_id}"
    return f"https://t.me/c/{source_id}/{message_id}"


class TelegramDelivery:
    def __init__(self, client: TelegramClient, recipient: Any) -> None:
        self._client = client
        self._recipient = recipient

    async def deliver(self, item: IncomingItem, filter_ids: tuple[str, ...]) -> str:
        try:
            await self._with_flood_wait(
                self._client.forward_messages,
                self._recipient,
                list(item.messages),
            )
            return "forwarded"
        except ChatForwardsRestrictedError:
            link = message_link(item.source_id, item.source_username, item.link_message_id)
            filters = ", ".join(filter_ids)
            text = (
                "Найдено совпадение в канале с защищённым контентом.\n"  # noqa: RUF001
                f"Фильтры: {filters}\n"
                f"Источник: {item.source_title}\n"
                f"{link}"
            )
            await self._with_flood_wait(self._client.send_message, self._recipient, text)
            return "protected_link"

    @staticmethod
    async def _with_flood_wait(function: Any, *args: Any) -> Any:
        for attempt in range(3):
            try:
                return await function(*args)
            except FloodWaitError as exc:
                if attempt == 2 or exc.seconds > 300:
                    raise
                logger.warning("telegram flood wait: seconds=%s", exc.seconds)
                await asyncio.sleep(exc.seconds + 1)
            except (OSError, TimeoutError, ServerError):
                if attempt == 2:
                    raise
                delay = 2**attempt
                logger.warning("temporary telegram error: retry_in=%s", delay, exc_info=True)
                await asyncio.sleep(delay)
        raise RuntimeError("unreachable")


class TelegramService:
    def __init__(self, settings: Settings, rules: RulesConfig) -> None:
        self._settings = settings
        self._rules = rules
        self._client = TelegramClient(
            str(settings.session_path),
            settings.api_id,
            settings.api_hash,
            auto_reconnect=True,
            sequential_updates=False,
        )
        self._processor: Processor | None = None
        self._state: StateStore | None = None

    async def run(self) -> None:
        self._prepare_paths()
        await self._client.connect()
        heartbeat: asyncio.Task[None] | None = None
        try:
            if not await self._client.is_user_authorized():
                raise RuntimeError(
                    "Telegram session is not authorized; run `parser-tg login` interactively first"
                )

            recipient = await self._client.get_input_entity(self._settings.recipient)
            sources = []
            for configured_source in self._rules.sources:
                entity = await self._client.get_entity(configured_source)
                if not getattr(entity, "broadcast", False):
                    raise RuntimeError(
                        f"configured source is not a broadcast channel: {configured_source}"
                    )
                sources.append(entity)
                logger.info(
                    "source_resolved id=%s username=%s title=%s",
                    entity.id,
                    getattr(entity, "username", None),
                    getattr(entity, "title", ""),
                )

            self._state = StateStore(self._settings.state_path)
            delivery = TelegramDelivery(self._client, recipient)
            self._processor = Processor(Matcher(self._rules.filters), self._state, delivery)
            self._client.add_event_handler(self._on_album, events.Album(chats=sources))
            self._client.add_event_handler(self._on_new_message, events.NewMessage(chats=sources))
            self._client.add_event_handler(
                self._on_edited_message, events.MessageEdited(chats=sources)
            )

            self._install_signal_handlers()
            heartbeat = asyncio.create_task(self._heartbeat(), name="health-heartbeat")
            logger.info("service_started sources=%s", len(sources))
            await self._client.run_until_disconnected()
        finally:
            if heartbeat is not None:
                heartbeat.cancel()
                with contextlib.suppress(asyncio.CancelledError):
                    await heartbeat
            if self._client.is_connected():
                await self._client.disconnect()
            if self._state is not None:
                self._state.close()
            logger.info("service_stopped")

    async def _on_new_message(self, event: events.NewMessage.Event) -> None:
        if event.message.grouped_id is not None:
            return
        await self._process_messages((event.message,), edited=False)

    async def _on_album(self, event: events.Album.Event) -> None:
        await self._process_messages(tuple(event.messages), edited=False)

    async def _on_edited_message(self, event: events.MessageEdited.Event) -> None:
        message = event.message
        if message.grouped_id is None:
            await self._process_messages((message,), edited=True)
            return
        messages = await self._load_album(message)
        await self._process_messages(messages, edited=True)

    async def _load_album(self, edited_message: Any) -> tuple[Any, ...]:
        lower = max(1, edited_message.id - 9)
        ids = list(range(lower, edited_message.id + 10))
        candidates = await self._client.get_messages(edited_message.peer_id, ids=ids)
        messages = tuple(
            message
            for message in candidates
            if message is not None and message.grouped_id == edited_message.grouped_id
        )
        return tuple(sorted(messages or (edited_message,), key=lambda value: value.id))

    async def _process_messages(self, messages: tuple[Any, ...], *, edited: bool) -> None:
        assert self._processor is not None
        if not messages:
            return
        try:
            first = messages[0]
            chat = await first.get_chat()
            grouped_id = first.grouped_id
            item_key = f"album:{grouped_id}" if grouped_id is not None else f"message:{first.id}"
            texts = tuple(
                message.raw_text.strip() for message in messages if message.raw_text.strip()
            )
            text = "\n".join(dict.fromkeys(texts))
            item = IncomingItem(
                source_id=str(chat.id),
                source_title=(
                    getattr(chat, "title", None) or getattr(chat, "username", None) or str(chat.id)
                ),
                source_username=getattr(chat, "username", None),
                item_key=item_key,
                message_ids=tuple(message.id for message in messages),
                link_message_id=first.id,
                text=text,
                messages=messages,
            )
            result = await self._processor.process(item)
            logger.debug("event_processed item=%s edited=%s result=%s", item_key, edited, result)
        except Exception:
            logger.exception(
                "event_processing_failed message_ids=%s edited=%s",
                ",".join(str(message.id) for message in messages),
                edited,
            )

    async def _heartbeat(self) -> None:
        while True:
            self._settings.health_path.touch()
            await asyncio.sleep(30)

    def _prepare_paths(self) -> None:
        for path in (
            self._settings.session_path,
            self._settings.state_path,
            self._settings.health_path,
        ):
            path.parent.mkdir(parents=True, exist_ok=True)
        for private_path in (self._settings.session_path, self._settings.state_path):
            if private_path.exists():
                private_path.chmod(0o600)

    def _install_signal_handlers(self) -> None:
        loop = asyncio.get_running_loop()
        for received_signal in (signal.SIGTERM, signal.SIGINT):
            with contextlib.suppress(NotImplementedError):
                loop.add_signal_handler(
                    received_signal,
                    lambda: asyncio.create_task(self._client.disconnect()),
                )


async def login(settings: Settings) -> None:
    settings.session_path.parent.mkdir(parents=True, exist_ok=True)
    client = TelegramClient(str(settings.session_path), settings.api_id, settings.api_hash)
    try:
        await client.start()
        identity = await client.get_me()
        logger.info("session_authorized user_id=%s username=%s", identity.id, identity.username)
    finally:
        await client.disconnect()
        if settings.session_path.exists():
            settings.session_path.chmod(0o600)


def healthcheck(path: Path, *, max_age_seconds: float = 120.0) -> bool:
    try:
        age = __import__("time").time() - path.stat().st_mtime
    except OSError:
        return False
    return 0 <= age <= max_age_seconds
