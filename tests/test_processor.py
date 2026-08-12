from pathlib import Path

import pytest

from parser_tg.config import FilterRule
from parser_tg.matcher import Matcher
from parser_tg.processor import IncomingItem, Processor
from parser_tg.state import StateStore


class FakeDelivery:
    def __init__(self) -> None:
        self.calls: list[tuple[str, ...]] = []
        self.fail = False

    async def deliver(self, item: IncomingItem, filter_ids: tuple[str, ...]) -> str:
        del item
        self.calls.append(filter_ids)
        if self.fail:
            raise RuntimeError("network")
        return "forwarded"


def item(text: str) -> IncomingItem:
    return IncomingItem("123", "Deals", "deals", "message:10", (10,), 10, text, (object(),))


@pytest.fixture
def processor(tmp_path: Path) -> tuple[Processor, StateStore, FakeDelivery]:
    state = StateStore(tmp_path / "state.sqlite3")
    delivery = FakeDelivery()
    value = Processor(Matcher((FilterRule("gpu", ("видеокарта",), 90),)), state, delivery)
    yield value, state, delivery
    state.close()


async def test_edit_can_turn_no_match_into_single_delivery(
    processor: tuple[Processor, StateStore, FakeDelivery],
) -> None:
    value, _, delivery = processor
    assert await value.process(item("мышь")) == "no_match"
    assert await value.process(item("мышь")) == "unchanged_no_match"
    assert await value.process(item("добавили видеокарту")) == "forwarded"
    assert await value.process(item("добавили ещё одну видеокарту")) == "already_forwarded"
    assert delivery.calls == [("gpu",)]


async def test_failed_delivery_can_be_retried(
    processor: tuple[Processor, StateStore, FakeDelivery],
) -> None:
    value, state, delivery = processor
    delivery.fail = True
    with pytest.raises(RuntimeError, match="network"):
        await value.process(item("видеокарта"))
    assert state.get("123", "message:10").status == "delivery_failed"  # type: ignore[union-attr]

    delivery.fail = False
    assert await value.process(item("видеокарта")) == "forwarded"
    assert len(delivery.calls) == 2
