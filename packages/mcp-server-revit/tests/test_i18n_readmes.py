"""Structural checks for the translated READMEs in docs/i18n/.

The English README.md is canonical. Translations may change prose, but code
blocks, tool names, environment variable names, counts and the document
structure must stay in step with it.
"""

from __future__ import annotations

import re
import unicodedata
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[3]
I18N_DIR = ROOT / "docs" / "i18n"
ENGLISH = ROOT / "README.md"

# Order here is the order of the language bar (by approximate speaker count).
LANGUAGES = [
    ("English", None),
    ("简体中文", "README.zh-CN.md"),
    ("Español", "README.es.md"),
    ("हिन्दी", "README.hi.md"),
    ("العربية", "README.ar.md"),
    ("Português (BR)", "README.pt-BR.md"),
    ("Русский", "README.ru.md"),
    ("日本語", "README.ja.md"),
    ("Deutsch", "README.de.md"),
    ("Français", "README.fr.md"),
    ("Bahasa Indonesia", "README.id.md"),
    ("Türkçe", "README.tr.md"),
    ("한국어", "README.ko.md"),
    ("Tiếng Việt", "README.vi.md"),
    ("Italiano", "README.it.md"),
    ("Polski", "README.pl.md"),
    ("繁體中文", "README.zh-TW.md"),
]
TRANSLATIONS = [(label, name) for label, name in LANGUAGES if name]

FENCE_RE = re.compile(r"^```.*?^```$", re.MULTILINE | re.DOTALL)
LINK_RE = re.compile(r"\]\(([^)\s]+)\)")
ATTR_RE = re.compile(r'(?:src|srcset)="([^"]+)"')
HEADING_RE = re.compile(r"^(#{1,6}) +(.+?) *$", re.MULTILINE)
IDENT_RE = re.compile(
    r"\b(?:MCP_REVIT_[A-Z_]+|(?:revit|ifc)_[a-z_]+|plan_actions|execute_plan|rollback_plan)\b"
)


def read(path: Path) -> str:
    return path.read_text(encoding="utf-8").replace("\r\n", "\n")


def expected_bar(current: str | None, from_dir: str) -> str:
    parts = []
    for label, name in LANGUAGES:
        if label == current:
            parts.append(f"**{label}**")
        elif name is None:
            parts.append(f"[{label}]({'../../README.md' if from_dir == 'i18n' else 'README.md'})")
        else:
            prefix = "" if from_dir == "i18n" else "docs/i18n/"
            parts.append(f"[{label}]({prefix}{name})")
    return " | ".join(parts)


def github_slug(text: str) -> str:
    kept = "".join(
        c for c in text.lower() if c in "-_ " or unicodedata.category(c)[0] in "LNM"
    )
    return kept.replace(" ", "-")


def headings(text: str, level: int) -> list[str]:
    body = FENCE_RE.sub("", text)
    return [h for hashes, h in HEADING_RE.findall(body) if len(hashes) == level]


@pytest.fixture(scope="module")
def english() -> str:
    return read(ENGLISH)


def test_language_bar_in_english_readme(english: str) -> None:
    assert expected_bar("English", "root") in english.split("\n")[:12]


@pytest.mark.parametrize(("label", "name"), TRANSLATIONS)
def test_translation_exists(label: str, name: str) -> None:
    assert (I18N_DIR / name).is_file(), f"missing docs/i18n/{name} ({label})"


@pytest.mark.parametrize(("label", "name"), TRANSLATIONS)
def test_language_bar(label: str, name: str) -> None:
    lines = read(I18N_DIR / name).split("\n")[:12]
    assert expected_bar(label, "i18n") in lines


@pytest.mark.parametrize(("label", "name"), TRANSLATIONS)
def test_code_fences_identical(english: str, label: str, name: str) -> None:
    # Every fenced block (JSON, PowerShell, prompts, paths) is kept verbatim,
    # in the same order. No block is exempt.
    assert FENCE_RE.findall(read(I18N_DIR / name)) == FENCE_RE.findall(english)


@pytest.mark.parametrize(("label", "name"), TRANSLATIONS)
def test_heading_structure_matches(english: str, label: str, name: str) -> None:
    text = read(I18N_DIR / name)
    for level in (2, 3):
        assert len(headings(text, level)) == len(headings(english, level)), (
            f"h{level} count differs from README.md"
        )


@pytest.mark.parametrize(("label", "name"), TRANSLATIONS)
def test_identifiers_and_counts_preserved(english: str, label: str, name: str) -> None:
    text = read(I18N_DIR / name)
    assert set(IDENT_RE.findall(text)) == set(IDENT_RE.findall(english))
    # Tool-count table and the headline total must not drift.
    counts = re.findall(r"^\| [^|]+ \| (\d+) \|", english, re.MULTILINE)
    assert counts and re.findall(r"^\| [^|]+ \| (\d+) \|", text, re.MULTILINE) == counts
    total = re.search(r"(\d+) tools are listed", english).group(1)
    assert re.search(rf"(?<!\d){total}(?!\d)", text)


@pytest.mark.parametrize(("label", "name"), TRANSLATIONS)
def test_translation_note_links_contributing(label: str, name: str) -> None:
    head = "\n".join(read(I18N_DIR / name).split("\n")[:15])
    assert "(../../CONTRIBUTING.md)" in head
    assert "(../../README.md)" in head


@pytest.mark.parametrize(("label", "name"), TRANSLATIONS)
def test_relative_links_resolve(label: str, name: str) -> None:
    path = I18N_DIR / name
    text = read(path)
    targets = LINK_RE.findall(FENCE_RE.sub("", text)) + ATTR_RE.findall(text)
    assert targets
    for target in targets:
        if re.match(r"^(?:[a-z][a-z0-9+.-]*:|#)", target, re.IGNORECASE):
            continue
        rel = target.split("#", 1)[0]
        if not rel:
            continue
        resolved = (path.parent / rel).resolve()
        assert resolved.exists(), f"{name}: broken relative link {target}"


@pytest.mark.parametrize(("label", "name"), TRANSLATIONS)
def test_in_page_anchors_resolve(label: str, name: str) -> None:
    text = read(I18N_DIR / name)
    anchors = {github_slug(h) for level in (2, 3) for h in headings(text, level)}
    for target in LINK_RE.findall(FENCE_RE.sub("", text)):
        if target.startswith("#"):
            assert target[1:] in anchors, f"{name}: no heading for anchor {target}"


def test_arabic_is_marked_right_to_left() -> None:
    text = read(I18N_DIR / "README.ar.md")
    assert '<div dir="rtl">' in text
    assert text.count('<div dir="rtl">') + text.count("<div align=") == text.count("</div>")
