import os
from datetime import UTC, datetime, timedelta
from pathlib import Path
from types import SimpleNamespace

from telethon.errors import ChatForwardsRestrictedError
from telethon.tl.types import User

from parser_tg.processor import IncomingItem
from parser_tg.telegram import (
    TelegramDelivery,
    healthcheck,
    message_link,
    messages_are_recent,
    safe_display_text,
    validate_recipient,
)


class ProtectedClient:
    def __init__(self) -> None:
        self.sent_text: str | None = None
        self.sent_parse_mode: object = "not-set"

    async def forward_messages(self, recipient: object, messages: object) -> None:
        del recipient, messages
        raise ChatForwardsRestrictedError(request=None)

    async def send_message(
        self,
        recipient: object,
        text: str,
        *,
        parse_mode: object = "not-set",
    ) -> None:
        del recipient
        self.sent_text = text
        self.sent_parse_mode = parse_mode


def test_message_links() -> None:
    assert message_link("123456", "deals", 42) == "https://t.me/deals/42"
    assert message_link("123456", None, 42) == "https://t.me/c/123456/42"


def test_untrusted_display_text_removes_control_characters() -> None:
    assert safe_display_text("Trusted\n\u202eevil") == "Trusted evil"


def test_recipient_must_be_expected_non_bot_user() -> None:
    assert validate_recipient(User(123), 123).id == 123

    for entity in (User(123, bot=True), User(123, deleted=True), User(456), object()):
        try:
            validate_recipient(entity, 123)
        except RuntimeError:
            pass
        else:
            raise AssertionError(f"accepted unsafe recipient: {entity!r}")


def test_healthcheck(tmp_path: Path) -> None:
    path = tmp_path / "healthy"
    assert not healthcheck(path)
    path.touch()
    assert healthcheck(path)
    os.utime(path, (1, 1))
    assert not healthcheck(path)


def test_message_age_uses_original_publication_date() -> None:
    now = datetime(2026, 8, 14, 12, tzinfo=UTC)
    recent = SimpleNamespace(date=now - timedelta(days=29))
    boundary = SimpleNamespace(date=now - timedelta(days=30))
    old_edited_today = SimpleNamespace(
        date=now - timedelta(days=31),
        edit_date=now,
    )

    max_age = timedelta(days=30)
    assert messages_are_recent((recent,), max_age, now=now)
    assert messages_are_recent((boundary,), max_age, now=now)
    assert not messages_are_recent((old_edited_today,), max_age, now=now)
    assert not messages_are_recent((SimpleNamespace(),), max_age, now=now)


async def test_protected_content_falls_back_to_link() -> None:
    client = ProtectedClient()
    delivery = TelegramDelivery(client, object())  # type: ignore[arg-type]
    item = IncomingItem(
        "123456",
        "[Private deals](https://phishing.invalid)",
        None,
        "message:42",
        (42,),
        42,
        "видеокарта",
        (object(),),
    )
    assert await delivery.deliver(item, ("gpu",)) == "protected_link"
    assert client.sent_text is not None
    assert client.sent_parse_mode is None
    assert "[Private deals](https://phishing.invalid)" in client.sent_text
    assert "gpu" in client.sent_text
    assert "https://t.me/c/123456/42" in client.sent_text
