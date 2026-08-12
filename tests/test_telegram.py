import os
from pathlib import Path

from telethon.errors import ChatForwardsRestrictedError

from parser_tg.processor import IncomingItem
from parser_tg.telegram import TelegramDelivery, healthcheck, message_link


class ProtectedClient:
    def __init__(self) -> None:
        self.sent_text: str | None = None

    async def forward_messages(self, recipient: object, messages: object) -> None:
        del recipient, messages
        raise ChatForwardsRestrictedError(request=None)

    async def send_message(self, recipient: object, text: str) -> None:
        del recipient
        self.sent_text = text


def test_message_links() -> None:
    assert message_link("123456", "deals", 42) == "https://t.me/deals/42"
    assert message_link("123456", None, 42) == "https://t.me/c/123456/42"


def test_healthcheck(tmp_path: Path) -> None:
    path = tmp_path / "healthy"
    assert not healthcheck(path)
    path.touch()
    assert healthcheck(path)
    os.utime(path, (1, 1))
    assert not healthcheck(path)


async def test_protected_content_falls_back_to_link() -> None:
    client = ProtectedClient()
    delivery = TelegramDelivery(client, object())  # type: ignore[arg-type]
    item = IncomingItem(
        "123456",
        "Private deals",
        None,
        "message:42",
        (42,),
        42,
        "видеокарта",
        (object(),),
    )
    assert await delivery.deliver(item, ("gpu",)) == "protected_link"
    assert client.sent_text is not None
    assert "gpu" in client.sent_text
    assert "https://t.me/c/123456/42" in client.sent_text
