from pathlib import Path

import pytest

from parser_tg.config import load_rules
from parser_tg.matcher import Matcher

RULES_PATH = Path(__file__).parents[1] / "config" / "rules.yaml"
MATCHER = Matcher(load_rules(RULES_PATH).filters)


@pytest.mark.parametrize(
    "text, expected",
    [
        ("Клавиатура ATK RS7", ("keyboards_brands",)),
        ("Мышь ATK X1", ("mice_brands",)),
        ("DDR4 Kingston 2x8 GB", ("ram_ddr4_kits",)),
        ("DDR4 Kingston 1x16 GB", ()),
        ("DDR5 Kingston 32 GB", ()),
        ("DDR5 Patriot 32 GB", ("ram_ddr5_brands",)),
        ("Блок питания 1stPlayer NGDP 1000W", ("psu_1stplayer",)),
        ("Блок питания 1stPlayer DK 600W", ()),
        ("Смартфон Xiaomi 15", ("smartphones_xiaomi_without_note_poco",)),
        ("Смартфон Xiaomi Redmi Note 14", ()),
        ("SSD NVMe на QLC памяти", ()),
        ("Видеокарта RTX 3060 Ti", ()),
        ("Видеокарта RTX 4070 Ti", ("gpu_except_old_series",)),
        ("Видеокарта Radeon RX 6600 XT", ()),
        ("Видеокарта Radeon RX 7600 XT", ("gpu_except_old_series",)),
        ("Наушники KZ EDX Pro", ()),
        ("Наушники KZ EDX Pro X", ("headphones_models",)),
        ("Realme Buds Air 7", ("headphones_models",)),
        ("Realme Buds Air 7 Pro", ()),
        ("Наушники Fiio FT3 32 Ом", ()),
        ("Наушники Fiio FT3 350 Ом", ("headphones_fiio_ft3_350ohm",)),
        ("OLED монитор ASUS 27", ("monitors_oled_any",)),
        ("Планшет OPPO Pad 4", ("tablets_brands",)),
        ("Наушники OPPO Enco Air5 Pro", ("headphones_models",)),
    ],
)
def test_catalog_rules(text: str, expected: tuple[str, ...]) -> None:
    assert tuple(match.filter_id for match in MATCHER.match(text)) == expected
