"""settings.txt: reading, checking and writing the settings (spec 3.2, 12.2, 12.3, 13.4, 13.5)."""
from __future__ import annotations

import configparser
from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation
from pathlib import Path

from app import i18n
from app.addresses import address_error
from app.i18n import Text, t, tr
from app.networks import NETWORKS, preset_label
from app.units import plain

NATIVE = "native"
AMOUNT_MODES = ("all", "percent", "range")
ORDERS = ("sequential", "random")
THEMES = ("dark", "light")
PRESET_KEYS = frozenset(preset.key for network in NETWORKS.values() for preset in network.tokens)
MULTIPLIER_MIN, MULTIPLIER_MAX = Decimal(1), Decimal(5)
TIMEOUT_MIN, TIMEOUT_MAX = 10, 3600


def _default_rpc() -> dict[str, str]:
    return {key: network.default_rpc for key, network in NETWORKS.items()}


@dataclass
class Settings:
    network: str = "ethereum"
    token: str = NATIVE  # native, a ready-made token (usdt, usdc, usdc.e…) or an ERC-20 contract address
    amount_mode: str = "all"
    percent: Decimal = Decimal(100)
    range_min: Decimal | None = None
    range_max: Decimal | None = None
    gas_multiplier: Decimal = Decimal("1.2")
    delay_min: int = 30
    delay_max: int = 90
    order: str = "sequential"
    tx_timeout: int = 120
    rpc: dict[str, str] = field(default_factory=_default_rpc)
    language: str = i18n.DEFAULT  # English until the user picks another language (spec 12.2)
    theme: str = "dark"

    @property
    def custom_token(self) -> bool:
        return self.token != NATIVE and self.token not in PRESET_KEYS


def parse_decimal(text: str) -> Decimal:
    """A number with a dot or a comma: "1,5" and "1.5" are the same."""
    try:
        value = Decimal(text.strip().replace(",", "."))
    except InvalidOperation:
        raise ValueError(t("“{value}” is not a number", value=text)) from None
    if not value.is_finite():
        raise ValueError(t("“{value}” is not a number", value=text))
    return value


def parse_int(text: str) -> int:
    value = parse_decimal(text)
    if value != value.to_integral_value():
        raise ValueError(t("“{value}” must be a whole number", value=text))
    return int(value)


def validate(settings: Settings) -> list[Text]:
    """Errors in the settings, each with the field name as in the window. An empty list — everything is fine."""
    errors: list[Text] = []
    network = NETWORKS.get(settings.network)
    if network is None:
        errors.append(t("Network: there is no network “{value}”", value=settings.network))
    elif settings.token != NATIVE:
        if settings.token in PRESET_KEYS:
            if network.preset(settings.token) is None:
                errors.append(t("Token: {token} is not among the ready-made tokens of {network}",
                                token=preset_label(settings.token), network=network.title))
        else:
            problem = address_error(settings.token)
            if problem:
                errors.append(t("Token, contract address: {problem}", problem=problem))
    if settings.amount_mode not in AMOUNT_MODES:
        errors.append(t("Amount: unknown mode “{value}”", value=settings.amount_mode))
    elif settings.amount_mode == "percent" and not Decimal(0) < settings.percent <= Decimal(100):
        errors.append(t("Percent: must be more than 0 and at most 100"))
    elif settings.amount_mode == "range":
        if settings.range_min is None or settings.range_max is None:
            errors.append(t("Range: enter “from” and “to”"))
        elif not Decimal(0) < settings.range_min <= settings.range_max:
            errors.append(t("Range: must be 0 < “from” ≤ “to”"))
    if not MULTIPLIER_MIN <= settings.gas_multiplier <= MULTIPLIER_MAX:
        errors.append(t("Gas price multiplier: from 1.0 to 5.0"))
    if not 0 <= settings.delay_min <= settings.delay_max:
        errors.append(t("Delay between wallets: must be 0 ≤ “from” ≤ “to”"))
    if settings.order not in ORDERS:
        errors.append(t("Processing order: unknown value “{value}”", value=settings.order))
    if not TIMEOUT_MIN <= settings.tx_timeout <= TIMEOUT_MAX:
        errors.append(t("Confirmation timeout: from {low} to {high} sec", low=TIMEOUT_MIN, high=TIMEOUT_MAX))
    for key, url in settings.rpc.items():
        title = NETWORKS[key].title if key in NETWORKS else key
        if key == settings.network and not url:
            errors.append(t("{network} RPC: address not set", network=title))
        elif url and not url.lower().startswith(("http://", "https://")):
            errors.append(t("{network} RPC: the address must start with http:// or https://", network=title))
    return errors


TEMPLATE = """\
# ===== ETH Sender: settings =====
# The file can be edited in Notepad or in the program.
# The Apply button rewrites it entirely.

[main]
# Network: ethereum | arbitrum | robinhood | optimism | bsc | base | avalanche
network = {network}
# Token: native (ETH/BNB/AVAX) | usdt | usdc | ERC-20 contract address
# Also: usdg (robinhood) | usdt0 (optimism) | usdc.e (arbitrum, optimism, avalanche) | usdbc (base) | usdt.e (avalanche)
token = {token}
# Amount: all (whole balance) | percent (percent of the balance) | range (random amount from a range)
amount_mode = {amount_mode}
percent = {percent}
range_min = {range_min}
range_max = {range_max}
# Gas price multiplier, one for all networks: from 1.0 to 5.0
gas_multiplier = {gas_multiplier}
# Delay between wallets, sec: random from delay_min to delay_max
delay_min = {delay_min}
delay_max = {delay_max}
# Order: sequential (as in the file) | random
order = {order}
# How long to wait for a transaction to get into a block, sec: from 10 to 3600
tx_timeout = {tx_timeout}

[rpc]
{rpc}

[ui]
# Interface language: en | ru
language = {language}
# Theme: dark | light
theme = {theme}
"""

UI_LANGUAGE_COMMENT = "# Interface language: en | ru"
UI_THEME_COMMENT = "# Theme: dark | light"


def _write(path: Path, text: str) -> None:
    temp = path.with_name(path.name + ".tmp")
    temp.write_text(text, encoding="utf-8")
    temp.replace(path)  # write to a temporary file first: if something fails, the old file stays intact


def save(path: Path, settings: Settings) -> None:
    """Rewrites the whole file, with the standard comments in the current language."""
    _write(path, tr(
        TEMPLATE,
        network=settings.network,
        token=settings.token,
        amount_mode=settings.amount_mode,
        percent=plain(settings.percent),
        range_min=plain(settings.range_min) if settings.range_min is not None else "",
        range_max=plain(settings.range_max) if settings.range_max is not None else "",
        gas_multiplier=plain(settings.gas_multiplier),
        delay_min=settings.delay_min,
        delay_max=settings.delay_max,
        order=settings.order,
        tx_timeout=settings.tx_timeout,
        rpc="\n".join(f"{key} = {settings.rpc.get(key, '')}" for key in NETWORKS),
        language=settings.language,
        theme=settings.theme,
    ))


def save_ui(path: Path, *, language: str, theme: str) -> None:
    """Language and theme are saved right away, without Apply (spec 12.2, 12.3). Only the [ui] lines change:
    the other values stay as they were saved, and unsaved edits in the panel do not get into the file."""
    if not path.exists():
        save(path, Settings(language=language, theme=theme))
        return
    values = {"language": language, "theme": theme}
    lines = path.read_text(encoding="utf-8-sig").splitlines()
    out: list[str] = []
    section: str | None = None
    seen_ui = False
    written: set[str] = set()

    def add_missing() -> None:
        out.extend(f"{key} = {value}" for key, value in values.items() if key not in written)
        written.update(values)

    for line in lines:
        stripped = line.strip()
        if stripped.startswith("[") and stripped.endswith("]"):
            if section == "ui":
                add_missing()
            section = stripped[1:-1].strip().lower()
            seen_ui = seen_ui or section == "ui"
            out.append(line)
            continue
        if section == "ui" and "=" in stripped and not stripped.startswith(("#", ";")):
            key = stripped.split("=", 1)[0].strip().lower()
            if key in values:
                if key not in written:
                    out.append(f"{key} = {values[key]}")
                    written.add(key)
                continue
        out.append(line)
    if section == "ui":
        add_missing()
    if not seen_ui:
        out += ["", "[ui]", tr(UI_LANGUAGE_COMMENT), f"language = {language}", tr(UI_THEME_COMMENT),
                f"theme = {theme}"]
    _write(path, "\n".join(out) + "\n")


def _choice(options: tuple[str, ...] | frozenset[str] | dict):
    def convert(raw: str) -> str:
        value = raw.lower()
        if value not in options:
            raise ValueError(t("allowed: {values}", values=", ".join(options)))
        return value

    return convert


def _number(low: Decimal | int, high: Decimal | int, *, integer: bool = False, low_inclusive: bool = True):
    def convert(raw: str):
        value = parse_int(raw) if integer else parse_decimal(raw)
        if value > high or value < low or (not low_inclusive and value == low):
            raise ValueError(t("must be {sign} {low} and ≤ {high}", sign="≥" if low_inclusive else ">",
                               low=low, high=high))
        return value

    return convert


def _token(raw: str) -> str:
    value = raw.lower()
    if value == NATIVE or value in PRESET_KEYS:
        return value
    problem = address_error(raw)
    if problem:
        raise ValueError(problem)
    return raw


def load(path: Path) -> tuple[Settings, list[Text]]:
    """Settings from the file and warnings. Invalid values are replaced with the defaults."""
    if not path.exists():
        settings = Settings()
        save(path, settings)
        return settings, [t("{file} not found: created with the default settings", file=path.name)]
    parser = configparser.ConfigParser(
        interpolation=None, comment_prefixes=("#", ";"), inline_comment_prefixes=None, strict=False)
    try:
        parser.read_string(path.read_text(encoding="utf-8-sig"))
    except (OSError, UnicodeDecodeError, configparser.Error) as exc:
        return Settings(), [t("{file} could not be read ({error}), using the default settings", file=path.name,
                              error=str(exc))]

    settings, warnings = Settings(), []

    def read(section: str, key: str, convert, *, allow_empty: bool = False) -> None:
        raw = parser[section].get(key) if parser.has_section(section) else None
        if raw is None:
            return
        raw = raw.strip()
        if not raw:
            if allow_empty:
                setattr(settings, key, None)
            return
        try:
            setattr(settings, key, convert(raw))
        except ValueError as exc:
            warnings.append(t("{file}: {key} = {value}: {problem}; using the default value", file=path.name, key=key,
                              value=raw, problem=exc.args[0]))

    read("main", "network", _choice(NETWORKS))
    read("main", "token", _token)
    read("main", "amount_mode", _choice(AMOUNT_MODES))
    read("main", "percent", _number(Decimal(0), Decimal(100), low_inclusive=False))
    read("main", "range_min", _number(Decimal(0), Decimal(10) ** 30, low_inclusive=False), allow_empty=True)
    read("main", "range_max", _number(Decimal(0), Decimal(10) ** 30, low_inclusive=False), allow_empty=True)
    read("main", "gas_multiplier", _number(MULTIPLIER_MIN, MULTIPLIER_MAX))
    read("main", "delay_min", _number(0, 86400, integer=True))
    read("main", "delay_max", _number(0, 86400, integer=True))
    read("main", "order", _choice(ORDERS))
    read("main", "tx_timeout", _number(TIMEOUT_MIN, TIMEOUT_MAX, integer=True))
    read("ui", "language", _choice(i18n.LANGUAGES))
    read("ui", "theme", _choice(THEMES))
    if parser.has_section("rpc"):
        for key in NETWORKS:
            url = parser["rpc"].get(key, "").strip()
            if url:
                settings.rpc[key] = url
    warnings.extend(t("{file}: {error}", file=path.name, error=error) for error in validate(settings))
    return settings, warnings
