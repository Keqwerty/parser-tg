from pathlib import Path

from parser_tg.state import StateStore


def test_state_round_trip_and_update(tmp_path: Path) -> None:
    store = StateStore(tmp_path / "state.sqlite3")
    try:
        assert store.get("1", "message:2") is None
        store.put("1", "message:2", "old", "no_match")
        assert store.get("1", "message:2").status == "no_match"  # type: ignore[union-attr]
        store.put("1", "message:2", "new", "forwarded", ("gpu",), "forwarded")
        state = store.get("1", "message:2")
        assert state is not None
        assert state.content_hash == "new"
        assert state.filters == ("gpu",)
        assert state.delivery == "forwarded"
    finally:
        store.close()
