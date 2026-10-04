"""Interface languages: English (the default) and Russian (spec 12.2).

Texts are written in English right in the code and double as keys of the Russian dictionary in app/ru.py.
Logic modules return Text objects instead of ready strings: a Text is rendered in the current language every
time it is shown, so after a language switch the window shows statuses and log lines again in the new language.

Placeholders use str.format syntax. A placeholder with a noun spec, like {count:wallets}, becomes a number with
the noun in the right plural form: "1 wallet", "2 wallets". Russian has three forms (one, few, many) and its
templates may use another grammatical case of the noun, so its nouns live in app/ru.py next to the translations.
"""
from __future__ import annotations

import string
from collections.abc import Mapping
from typing import Any

EN, RU = "en", "ru"
LANGUAGES = (EN, RU)
DEFAULT = EN

_language = DEFAULT

# English noun forms for plurals: (one, many)
EN_NOUNS: dict[str, tuple[str, ...]] = {
    "wallets": ("wallet", "wallets"),
    "entries": ("entry", "entries"),
}


def language() -> str:
    return _language


def set_language(code: str) -> None:
    global _language
    if code not in LANGUAGES:
        raise ValueError(f"unknown language: {code}")
    _language = code


def plural(code: str, count: int, forms: tuple[str, ...]) -> str:
    count = abs(int(count))
    if code == EN:
        return forms[0] if count == 1 else forms[1]
    count %= 100
    if 11 <= count <= 14:
        return forms[2]
    count %= 10
    if count == 1:
        return forms[0]
    if 2 <= count <= 4:
        return forms[1]
    return forms[2]


class _Formatter(string.Formatter):
    def __init__(self, code: str) -> None:
        super().__init__()
        self.code = code

    def format_field(self, value: Any, format_spec: str) -> str:
        forms = nouns(self.code).get(format_spec)
        if forms is not None:
            return f"{value} {plural(self.code, value, forms)}"
        return format(value, format_spec)


def catalog(code: str) -> Mapping[str, str]:
    if code == RU:
        from app.ru import RU as translations  # imported here: the dictionary is only needed in Russian

        return translations
    return {}


def nouns(code: str) -> Mapping[str, tuple[str, ...]]:
    if code == RU:
        from app.ru import RU_NOUNS

        return RU_NOUNS
    return EN_NOUNS


CONTEXT = "\x04"  # "context\x04text": the same English text with different translations, as in gettext


def render(template: str, params: Mapping[str, Any] | None = None, code: str | None = None) -> str:
    """The template in the given language (by default the current one) with parameters filled in."""
    code = code or _language
    text = catalog(code).get(template)
    if text is None:
        text = template.split(CONTEXT, 1)[-1]
    values = {key: value.render(code) if isinstance(value, Text) else value for key, value in (params or {}).items()}
    return _Formatter(code).vformat(text, (), values) if values else text


class Text:
    """A message for the user. It is rendered in the current language each time it is shown."""

    __slots__ = ("template", "params")

    def __init__(self, template: str, **params: Any) -> None:
        self.template = template
        self.params = params

    def render(self, code: str | None = None) -> str:
        return render(self.template, self.params, code)

    def __str__(self) -> str:
        return self.render()

    def __format__(self, format_spec: str) -> str:
        return format(str(self), format_spec)

    def __repr__(self) -> str:
        return f"Text({self.template!r}, {self.params!r})"

    def __eq__(self, other: object) -> bool:
        if isinstance(other, Text):
            return self.template == other.template and self.params == other.params
        return NotImplemented

    def __hash__(self) -> int:
        return hash((self.template, tuple(sorted((k, str(v)) for k, v in self.params.items()))))


def t(template: str, **params: Any) -> Text:
    """A message that stays translatable: for statuses, the log and anything shown later."""
    return Text(template, **params)


def tr(template: str, **params: Any) -> str:
    """The message right away in the current language: for widgets that are retranslated on a switch."""
    return render(template, params)


def show(value: Text | str | None) -> str:
    """Text, plain string or nothing — as a string in the current language."""
    return "" if value is None else str(value)
