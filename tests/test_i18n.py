"""Translations (spec 12.2): every text of the program has a Russian version with the same placeholders."""
from __future__ import annotations

import ast
import importlib
import re
import string
import tokenize
from pathlib import Path

import pytest

from app import i18n
from app.i18n import EN, RU, Text, render, t
from app.ru import RU as CATALOG
from app.ru import RU_NOUNS

ROOT = Path(__file__).resolve().parent.parent
# Calls whose first argument is an English text to translate: t(), tr(), Text() and the settings panel helpers
CALLS = {"t", "tr", "Text", "_tr_label", "_section", "_field"}


def used_templates() -> dict[str, str]:
    """Every English text used in the program, with the place where it is used."""
    found: dict[str, str] = {}
    for path in sorted((ROOT / "app").rglob("*.py")):
        if path.name == "ru.py":
            continue
        module_name = ".".join(path.relative_to(ROOT).with_suffix("").parts)
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
            if not isinstance(node, ast.Call) or not node.args:
                continue
            func = node.func
            name = func.id if isinstance(func, ast.Name) else func.attr if isinstance(func, ast.Attribute) else None
            if name not in CALLS:
                continue
            arg = node.args[0]
            if isinstance(arg, ast.Constant) and isinstance(arg.value, str):
                value = arg.value
            elif isinstance(arg, ast.Name):  # a module constant, like the file templates
                value = getattr(importlib.import_module(module_name), arg.id, None)
                if not isinstance(value, str):
                    continue
            else:
                continue
            found.setdefault(value, f"{module_name}:{node.lineno}")
    return found


def needs_translation(template: str) -> bool:
    """Texts with words outside the placeholders; "#{num} {name}" and the like stay as they are."""
    return template == "#" or bool(re.search(r"[A-Za-z]", re.sub(r"\{[^}]*\}", "", template)))


def fields(template: str) -> dict[str, str]:
    return {name: spec for _, name, spec, _ in string.Formatter().parse(template) if name is not None}


def test_every_text_has_a_russian_translation():
    missing = {template: place for template, place in used_templates().items()
               if needs_translation(template) and template not in CATALOG}
    assert not missing, missing


def test_the_dictionary_has_no_stale_entries():
    used = used_templates()
    assert [key for key in CATALOG if key not in used] == []


@pytest.mark.parametrize("template", sorted(CATALOG))
def test_placeholders_match(template):
    english, russian = fields(template), fields(CATALOG[template])
    assert set(english) == set(russian), (template, CATALOG[template])
    for name, spec in english.items():
        if spec:
            assert spec in i18n.EN_NOUNS, (template, spec)
            assert russian[name] in RU_NOUNS, (CATALOG[template], russian[name])


def test_plurals():
    assert [render("{count:wallets}", {"count": n}, EN) for n in (1, 2, 5)] == ["1 wallet", "2 wallets", "5 wallets"]
    russian = [render("{count:wallets}", {"count": n}, RU) for n in (1, 2, 5, 11, 21, 22, 112)]
    assert russian == ["1 кошелёк", "2 кошелька", "5 кошельков", "11 кошельков", "21 кошелёк", "22 кошелька",
                       "112 кошельков"]
    genitive = [render("Send {token} from {count:wallets}?", {"token": "USDC", "count": n}, RU) for n in (1, 3, 10)]
    assert genitive == ["Отправить USDC с 1 кошелька?", "Отправить USDC с 3 кошельков?",
                        "Отправить USDC с 10 кошельков?"]


def test_text_is_rendered_in_the_language_of_the_moment():
    message = t("Skipped: {reason}", reason=t("zero balance"))
    assert str(message) == "Skipped: zero balance"
    i18n.set_language(RU)
    try:
        assert str(message) == "Пропущен: баланс 0"  # the same object, now in Russian
    finally:
        i18n.set_language(EN)
    assert message == t("Skipped: {reason}", reason=t("zero balance")) and isinstance(message, Text)


def test_context_marks_the_same_english_text_with_different_translations():
    assert render("count\x04Wallets", None, EN) == "Wallets"
    assert render("count\x04Wallets", None, RU) == "Кошельков" and render("Wallets", None, RU) == "Кошельки"


def test_code_has_no_russian_comments():
    """Comments and docstrings are in English everywhere; Russian stays only in the translation and in test data
    (spec 12.2)."""
    cyrillic = re.compile("[А-Яа-яЁё]")
    offenders = []
    for folder, pattern in ((ROOT, "*.py"), (ROOT / "app", "**/*.py"), (ROOT / "tools", "*.py"), (ROOT / "tests", "*.py")):
        for path in sorted(folder.glob(pattern)):
            relative = path.relative_to(ROOT).as_posix()
            if relative == "app/ru.py":
                continue
            source = path.read_text(encoding="utf-8")
            with open(path, encoding="utf-8") as stream:
                comments = [(token.start[0], token.string) for token in tokenize.generate_tokens(stream.readline)
                            if token.type == tokenize.COMMENT]
            docstrings = [(node.body[0].lineno, node.body[0].value.value) for node in ast.walk(ast.parse(source))
                          if isinstance(node, (ast.Module, ast.ClassDef, ast.FunctionDef))
                          and node.body and isinstance(node.body[0], ast.Expr)
                          and isinstance(node.body[0].value, ast.Constant) and isinstance(node.body[0].value.value, str)]
            offenders += [f"{relative}:{line}: {text[:60]}" for line, text in comments + docstrings
                          if cyrillic.search(text)]
    assert offenders == []
