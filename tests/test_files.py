"""wallets.txt and settings.txt (spec 3, 11.3, 12.2, 12.3)."""
from __future__ import annotations

from decimal import Decimal

from eth_account import Account

from app import i18n
from app import settings as settings_file
from app import wallets as wallets_file
from app.settings import Settings

KEY = "11" * 32
SENDER = Account.from_key("0x" + KEY).address
RECIPIENT = "0x4Ce896d765DF9EbE842ABAaa45Ff8CAAf4193D7E"
FIELDS = "expected 2 or 3 comma-separated fields: key,address or name,key,address"


def test_wallet_lines_are_numbered_and_checked():
    text = "\n".join([
        "﻿# a comment",
        "",
        f"Основной 1, 0x{KEY} , {RECIPIENT}",  # Cyrillic names are read as they are
        f",{KEY},{RECIPIENT.lower()}",
        f"Bad key,123,{RECIPIENT}",
        f"Typo,{KEY},{RECIPIENT[:-1]}e",
        f"Self,{KEY},{SENDER}",
    ])
    entries = wallets_file.parse(text)
    assert [entry.num for entry in entries] == [1, 2, 3, 4, 5]
    first, nameless, bad_key, typo, self_send = entries
    assert first.valid and first.name == "Основной 1" and first.sender == SENDER and first.recipient == RECIPIENT
    assert first.private_key == "0x" + KEY and first.line_no == 3
    assert nameless.valid and nameless.name == "" and nameless.title == f"{SENDER[:6]}…{SENDER[-4:]}"
    assert nameless.recipient == RECIPIENT  # a lower-case address is turned into the checksum one
    assert str(bad_key.error) == "invalid private key" and not bad_key.private_key
    assert "checksum" in str(typo.error)
    assert str(self_send.error) == "the recipient is the same as the sender"
    assert KEY not in repr(first)  # the key gets neither into repr nor into logs


def test_two_field_lines_are_nameless_wallets_and_formats_mix():
    """A "key,address" line is a wallet without a name; formats mix, the numbers go in a row (spec 11.3)."""
    other_key = "22" * 32
    text = "\n".join([
        f"0x{KEY},{RECIPIENT}",
        f"Main 1,0x{other_key},{RECIPIENT}",
        "# a comment",
        f" {other_key} , {RECIPIENT.lower()} ",
        f",{KEY},{RECIPIENT}",
        f"Name and key,{KEY}",
        f"{KEY}",
        f"Extra,{KEY},{RECIPIENT},x",
        f"{KEY},{SENDER}",
        f"{KEY},0x123",
    ])
    entries = wallets_file.parse(text)
    assert [entry.num for entry in entries] == list(range(1, 10))
    with_0x, named, without_0x, empty_name, name_and_key, one_field, four_fields, self_send, bad_address = entries
    for entry in (with_0x, without_0x, empty_name):
        assert entry.valid and entry.name == "" and entry.recipient == RECIPIENT
        assert entry.title == f"{entry.sender[:6]}…{entry.sender[-4:]}"
    assert with_0x.sender == empty_name.sender == SENDER and with_0x.private_key == "0x" + KEY
    assert without_0x.sender == Account.from_key("0x" + other_key).address and without_0x.line_no == 4
    assert named.valid and named.name == "Main 1"
    assert str(name_and_key.error) == "invalid private key"  # two fields are always key,address
    for entry in (one_field, four_fields):
        assert str(entry.error) == FIELDS
        assert entry.error.render("ru") == "нужно 2 или 3 поля через запятую: ключ,адрес или имя,ключ,адрес"
        assert not entry.valid and entry.sender is None and not entry.private_key
    assert str(self_send.error) == "the recipient is the same as the sender"
    assert str(bad_address.error).startswith("recipient address:")


def test_missing_wallets_file_is_created_in_the_current_language(tmp_path):
    path = tmp_path / "wallets.txt"
    entries, message = wallets_file.load(path)
    assert entries == [] and path.exists() and "created" in str(message)
    assert wallets_file.load(path)[0] == []  # the template has only comments
    template = path.read_text(encoding="utf-8")
    assert "name,private key,recipient address" in template and "\n# 0x<64 hex characters>,0x" in template

    i18n.set_language(i18n.RU)
    try:
        russian = tmp_path / "ru.txt"
        wallets_file.load(russian)
        text = russian.read_text(encoding="utf-8")
        assert "имя,приватный ключ,адрес получателя" in text and wallets_file.load(russian)[0] == []
    finally:
        i18n.set_language(i18n.EN)


def test_settings_roundtrip_and_comma_decimals(tmp_path):
    path = tmp_path / "settings.txt"
    original = Settings(network="base", token="usdc", amount_mode="range", range_min=Decimal("10"),
                        range_max=Decimal("15.5"), gas_multiplier=Decimal("1.35"), delay_min=5, delay_max=9,
                        order="random", tx_timeout=90, language="ru", theme="light")
    original.rpc["base"] = "https://example.org/rpc"
    settings_file.save(path, original)
    loaded, warnings = settings_file.load(path)
    assert warnings == [] and loaded == original

    path.write_text(path.read_text(encoding="utf-8").replace("gas_multiplier = 1.35", "gas_multiplier = 1,5"),
                    encoding="utf-8")
    assert settings_file.load(path)[0].gas_multiplier == Decimal("1.5")


def test_bad_settings_values_fall_back_to_defaults_with_warnings(tmp_path):
    path = tmp_path / "settings.txt"
    path.write_text("[main]\nnetwork = solana\ngas_multiplier = 12\ntx_timeout = 5\norder = random\n"
                    "[ui]\nlanguage = de\ntheme = light\n", encoding="utf-8")
    loaded, warnings = settings_file.load(path)
    assert loaded.network == "ethereum" and loaded.gas_multiplier == Decimal("1.2") and loaded.tx_timeout == 120
    assert loaded.order == "random" and loaded.language == "en" and loaded.theme == "light"
    assert len(warnings) == 4 and all(str(text).startswith("settings.txt: ") for text in warnings)


def test_settings_from_version_1_1_open_in_english_and_dark(tmp_path):
    """No [ui] section yet: English and the dark theme (spec 12.2, 12.3)."""
    path = tmp_path / "settings.txt"
    path.write_text("[main]\nnetwork = base\n", encoding="utf-8")
    loaded, warnings = settings_file.load(path)
    assert warnings == [] and loaded.language == "en" and loaded.theme == "dark" and loaded.network == "base"


def test_missing_settings_file_is_created_with_defaults(tmp_path):
    path = tmp_path / "settings.txt"
    loaded, warnings = settings_file.load(path)
    assert loaded == Settings() and path.exists() and len(warnings) == 1
    assert loaded.language == "en" and "[ui]" in path.read_text(encoding="utf-8")


def test_saving_language_and_theme_changes_only_the_ui_lines(tmp_path):
    """The switch saves at once, and nothing else in the file changes (spec 12.2)."""
    path = tmp_path / "settings.txt"
    text = "# my comment\n[main]\nnetwork = base\ndelay_min = 7\n\n[rpc]\nbase = https://example.org\n"
    path.write_text(text, encoding="utf-8")
    settings_file.save_ui(path, language="ru", theme="dark")
    saved = path.read_text(encoding="utf-8")
    assert saved.startswith(text) and "[ui]" in saved and "language = ru" in saved and "theme = dark" in saved
    loaded, _ = settings_file.load(path)
    assert (loaded.language, loaded.theme, loaded.network, loaded.delay_min) == ("ru", "dark", "base", 7)

    settings_file.save_ui(path, language="en", theme="light")
    again = path.read_text(encoding="utf-8")
    assert again.count("[ui]") == 1 and again.count("language =") == 1 and again.count("theme =") == 1
    assert again.startswith(text) and settings_file.load(path)[0].theme == "light"


def test_validate_names_the_field():
    settings = Settings(network="base", token="usdg", amount_mode="range", range_min=Decimal(5),
                        range_max=Decimal(1), delay_min=10, delay_max=1)
    settings.rpc["base"] = "mainnet.base.org"
    errors = [str(error) for error in settings_file.validate(settings)]
    assert any(error.startswith("Token: USDG is not among") for error in errors)
    assert any(error.startswith("Range:") for error in errors)
    assert any(error.startswith("Delay between wallets:") for error in errors)
    assert any(error.startswith("Base RPC:") for error in errors)
    assert settings_file.validate(Settings()) == []


def test_custom_token_address_must_be_valid():
    assert str(settings_file.validate(Settings(token="0x123"))[0]).startswith("Token, contract address:")
    assert settings_file.validate(Settings(token=RECIPIENT)) == []
    assert Settings(token=RECIPIENT).custom_token and not Settings(token="usdt").custom_token
