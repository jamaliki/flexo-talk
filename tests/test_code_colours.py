"""Code on a slide coloured by its words' kinds in the deck's own colours
(``flexo_talk.codecolours``): read as the language it names or looks like, painted by the
theme -- comments muted, keywords in the accent, strings, constants and functions in its next
colours, each made to read on the code's panel -- in the slide, the PowerPoint and the PDF,
and never written into the deck."""

from __future__ import annotations

import re
import zipfile
from pathlib import Path

import pytest
import yaml

from flexo_talk import Deck
from flexo_talk.codecolours import FLOOR, coloured, guess, kinds, paints
from flexo_talk.deck import SettingError

LISTING = '''
import numpy as np

def loss(x, y=2):
    """Mean squared error."""
    # the difference, squared
    return np.mean((x - y) ** 2)  # mean
'''


def _spans(svg: str, identifier: str) -> list[tuple[str, str | None]]:
    """The words of a drawn line of code, each piece and the colour it is painted in."""

    found = re.search(rf'<text id="{re.escape(identifier)}"[^>]*>(.*?)</text>', svg, re.S)
    assert found is not None
    piece = r'<tspan(?: x="[^"]*")?(?: fill="(#[0-9a-f]{6})")?><tspan[^>]*>([^<]*)</tspan></tspan>'
    pieces = re.findall(piece, found.group(1))
    return [(words, fill or None) for fill, words in pieces]


def test_words_are_coloured_by_their_kinds_in_the_themes_colours(tmp_path: Path) -> None:
    from flexo.colour import contrast

    deck = Deck("code", theme="paper")
    with deck.slide("Code") as slide:
        slide.code(LISTING)
    svg = deck.build(tmp_path, formats=("svg",)).svgs[0].read_text()
    panel = re.search(r'id="slide1\.body\.0\.panel"[^>]*fill="(#[0-9a-f]{6})"', svg).group(1)
    first = dict(_spans(svg, "slide1.body.0.0"))
    second = _spans(svg, "slide1.body.0.2")
    # Keywords in the accent (the theme's first tone, as its words are painted), the function's
    # name, a number: each in a colour of its own, each reading on the panel.
    keyword, name, number = first["import"], dict(second)["loss"], dict(second)["2"]
    assert keyword == deck.palette.get("tone-1-stroke")
    assert len({keyword, name, number}) == 3
    assert all(contrast(colour, panel) >= FLOOR - 0.01 for colour in (keyword, name, number))
    # The rest in the listing's ink; a comment at a line's end in the muted ink.
    assert first[" numpy "] is None
    last = dict(_spans(svg, "slide1.body.0.5"))
    assert last["# mean"] is not None and last["return"] == keyword
    # A line that is a comment alone is muted as a whole, as ever: one run, the line's paint.
    whole = re.search(r'<text id="slide1\.body\.0\.4"[^>]*fill="(#[0-9a-f]{6})"', svg)
    assert whole is not None and whole.group(1) == last["# mean"]
    assert _spans(svg, "slide1.body.0.4") == [("    # the difference, squared", None)]


def test_a_listing_named_plain_text_is_coloured_by_nothing(tmp_path: Path) -> None:
    deck = Deck("plain")
    with deck.slide("Code") as slide:
        slide.code("def f(x):\n    return x + 1", language="text")
    svg = deck.build(tmp_path, formats=("svg",)).svgs[0].read_text()
    assert "def f(x):" in svg


def test_a_language_named_is_one_pygments_reads_and_is_all_that_is_written() -> None:
    deck = Deck("named")
    with deck.slide("Code") as slide:
        slide.code("fn main() {}", language="Rust")
        with pytest.raises(SettingError, match="language"):
            slide.code("x", language="klingon")
    # What the deck keeps of it: its words and its language, no colour.
    assert deck.slides[0].regions["body"].sources == [{"code": "fn main() {}", "language": "rust"}]


def test_the_language_a_listing_looks_like() -> None:
    assert guess("import torch\n\ndef f(x):\n    return x") == "python"
    assert guess("fn main() {\n    let mut x = 1;\n    println!(\"{}\", x);\n}") == "rust"
    assert guess("$ pip install flexo\n$ uv run flexo studio --port 8080") == "bash"
    assert guess("const x = [1, 2].map((n) => n * 2);\nconsole.log(x);") == "javascript"
    assert guess("#include <vector>\nint main() {\n    std::vector<int> v;\n}") == "cpp"
    assert guess("SELECT name FROM cells WHERE count > 3;") == "sql"
    # Nothing it looks like: Python.
    assert guess("x = 1") == "python"


def test_each_theme_colours_code_as_it_paints_words() -> None:
    from flexo.colour import chroma, contrast
    from flexo.themes import THEMES, resolve_palette, with_tone_roles

    for name in THEMES:
        palette = with_tone_roles(resolve_palette(name))
        panel = palette.get("tone-1-fill")
        made = paints(palette, panel, palette.get("muted-ink"))
        assert made["comment"] == palette.get("muted-ink")
        for kind in ("keyword", "string", "constant", "function"):
            if kind in made:
                assert contrast(made[kind], panel) >= FLOOR - 0.01, (name, kind)
    # A theme told apart by lightness alone colours nothing but its comments; one with a
    # single signal colour, its keywords alone.
    assert set(paints(with_tone_roles(resolve_palette("print")), "#ffffff", "#555555")) == {"comment"}
    swiss = paints(with_tone_roles(resolve_palette("swiss")), "#f0f0f0", "#666666")
    assert set(swiss) == {"keyword", "comment"} and chroma(swiss["keyword"]) > 0.1
    assert len(paints(with_tone_roles(resolve_palette("paper")), "#ffffff", "#666666")) == 5


def test_a_wrapped_line_keeps_each_word_in_its_colour() -> None:
    from flexo.themes import resolve_palette, with_tone_roles

    palette = with_tone_roles(resolve_palette("paper"))
    source = ['x = "a long string" + compute(1, 2)']
    # Wrapped after the string: its rest indented four spaces under it.
    drawn = [('x = "a long string" ', False, 0), ('    + compute(1, 2)', False, 0)]
    made = coloured(source, "python", drawn, palette, "#ffffff", "#666666")
    first, rest = made
    assert "".join(run.text for run in first) == drawn[0][0]
    assert "".join(run.text for run in rest) == drawn[1][0]
    string = next(run for run in first if run.text.startswith('"'))
    assert string.text == '"a long string"' and string.color
    numbers = [run for run in rest if run.text.strip() in {"1", "2"}]
    assert numbers and all(run.color for run in numbers)
    # (The indent added before its rest is the listing's, in its ink.)
    assert rest[0].text.startswith("    ") and not rest[0].color


def test_a_string_across_lines_is_coloured_on_each() -> None:
    lines = kinds('s = """one\ntwo"""\nx = 3', "python")
    assert lines[0][-1][2] == "string" and lines[1][0] == (0, 6, "string")
    assert lines[2][-1] == (4, 5, "constant")


def test_the_powerpoint_and_the_pdf_have_the_colours(tmp_path: Path) -> None:
    deck = Deck("exports", theme="paper")
    with deck.slide("Code") as slide:
        slide.code(LISTING)
    result = deck.build(tmp_path, formats=("pptx", "pdf"))
    with zipfile.ZipFile(result.pptx) as archive:
        xml = archive.read("ppt/slides/slide1.xml").decode()
    keyword = deck.palette.get("tone-1-stroke").lstrip("#").upper()
    run = re.search(r"<a:r>(?:(?!</a:r>).)*<a:t>import</a:t></a:r>", xml)
    assert run is not None and f'val="{keyword}"' in run.group(0)
    # Its words in one text box, as a listing is, several colours in it.
    assert len(set(re.findall(r'<a:srgbClr val="(\w+)"/></a:solidFill><a:latin typeface="IBM Plex Mono"', xml))) >= 4
    import pypdfium2 as pdfium

    page = pdfium.PdfDocument(str(result.pdf))[0]
    assert "return np.mean" in page.get_textpage().get_text_range()


def test_a_deck_document_names_a_listings_language(tmp_path: Path) -> None:
    from flexo_talk.document import read_deck

    source = tmp_path / "talk.yaml"
    source.write_text(yaml.safe_dump({"schema_version": 1, "deck": {"id": "t"}, "slides": [
        {"title": "Code", "body": [{"code": "SELECT 1", "language": "sql"}, {"code": "x", "language": "text"}]}]}))
    deck = read_deck(source)
    assert [block.language for block in deck.slides[0].regions["body"].blocks] == ["sql", "text"]
