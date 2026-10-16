"""The Design bar's slides drawn in a design before it is chosen (``studio.previews``): a deck's
title slide in each theme for its gallery, and the slide shown in the theme, palette, fonts,
look, background or size pointed at -- each variant drawn in order, the deck itself unchanged,
one that can't be drawn said in its place, and a drawing kept while what it was drawn from is.
And what the bar works out in the page (``designs.js``), run in Node: the slide its gallery
shows, the deck's slide sizes, its backgrounds, its fonts a click away, and its variants."""

from __future__ import annotations

import copy
import json
import re
import shutil
import subprocess
from pathlib import Path

import pytest

from flexo_talk.studio import DeckKind
from flexo_talk.studio import previews as previews_module
from flexo_talk.studio.previews import designed

DECK = {
    "deck": {"id": "talk", "palette": "Tableau"},
    "slides": [
        {"title": "Methods", "body": [{"bullets": ["One", "Two"]}]},
        {"layout": "title", "title": "Enzyme design", "subtitle": "GBI Assembly 2026"},
    ],
}


def _asked(
    variants: list[object], *, slide: int = 1, document: dict | None = None, tmp: Path = Path(".")
) -> list[dict]:
    action = {"do": "previews", "slide": slide, "variants": variants}
    return DeckKind().act(copy.deepcopy(document or DECK), action, tmp)["previews"]


def _canvas(svg: str) -> str:
    return re.search(r'id="canvas\.background"[^>]*fill="([^"]+)"', svg)[1]


def test_each_variant_is_the_slide_drawn_so_in_order(tmp_path: Path) -> None:
    paper, dark, sized = _asked([{"theme": None}, {"theme": "dark"}, {"style": {"width": 720}}], tmp=tmp_path)
    assert all("<svg" in item["svg"] and item["key"] for item in (paper, dark, sized))
    assert _canvas(paper["svg"]) != _canvas(dark["svg"])
    assert 'viewBox="0 0 720 540"' in sized["svg"] and 'viewBox="0 0 960 540"' in paper["svg"]
    # (The slide asked for: its own words.)
    assert "Enzyme design" in paper["svg"] and "Methods" not in paper["svg"]


def test_the_deck_is_left_as_it_is(tmp_path: Path) -> None:
    document = copy.deepcopy(DECK)
    answer = DeckKind().act(document, {"do": "previews", "slide": 0, "variants": [{"theme": "dark"}]}, tmp_path)
    assert document == DECK and set(answer) == {"previews"}


def test_a_design_that_cant_be_drawn_is_said_in_its_place(tmp_path: Path) -> None:
    wrong, right = _asked([{"theme": "no-such-theme"}, {"theme": "swiss"}], tmp=tmp_path)
    assert "no-such-theme" in wrong["error"] and "svg" not in wrong
    assert "<svg" in right["svg"]


def test_no_such_slide_is_said_for_each_variant(tmp_path: Path) -> None:
    assert _asked([{}, {}], slide=7, tmp=tmp_path) == [{"error": "There is no such slide."}] * 2
    assert _asked([{}], slide=True, tmp=tmp_path)[0]["error"] == "There is no such slide."  # type: ignore[arg-type]


def test_a_variant_changes_the_design_alone() -> None:
    deck = {"id": "talk", "theme": "dark", "palette": "Tableau", "footer": "GBI"}
    assert designed(deck, {"theme": None, "palette": "Okabe-Ito", "footer": "else", "id": "x"}) == {
        "id": "talk",
        "palette": "Okabe-Ito",
        "footer": "GBI",
    }
    assert designed(deck, "not a variant") == deck


def test_a_drawing_is_kept_while_what_it_was_drawn_from_is(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    drawn: list[int] = []
    real = previews_module._draw

    def counted(*args: object, **kwargs: object) -> dict:
        drawn.append(1)
        return real(*args, **kwargs)

    monkeypatch.setattr(previews_module, "_draw", counted)
    monkeypatch.setattr(previews_module, "_kept", type(previews_module._kept)())
    first = _asked([{"theme": "rams"}], tmp=tmp_path)
    assert _asked([{"theme": "rams"}], tmp=tmp_path) == first and len(drawn) == 1
    # Its slide's words changed, it is drawn again; another slide's, not.
    other = copy.deepcopy(DECK)
    other["slides"][0]["title"] = "Results"
    _asked([{"theme": "rams"}], document=other, tmp=tmp_path)
    assert len(drawn) == 1
    other["slides"][1]["title"] = "Enzymes, designed"
    _asked([{"theme": "rams"}], document=other, tmp=tmp_path)
    assert len(drawn) == 2


# -- what the page works out (designs.js), in Node --

SCRIPT = Path(__file__).parents[1] / "src" / "flexo_talk" / "studio" / "static" / "designs.js"


def _node(code: str) -> object:
    node = shutil.which("node")
    if node is None:
        pytest.skip("Node is not installed")
    program = (
        f"import * as D from {json.dumps(SCRIPT.as_uri())};\n"
        f"console.log(JSON.stringify(await (async () => {{ {code} }})()));"
    )
    done = subprocess.run([node, "--input-type=module", "-e", program], capture_output=True, text=True, check=True)
    return json.loads(done.stdout.strip().splitlines()[-1])


def test_the_gallery_shows_the_title_slide_else_the_first() -> None:
    assert _node("""return [
      D.gallerySlide([{ title: "a" }, { layout: "section" }, { layout: "title" }]),
      D.gallerySlide([{ title: "a" }, { layout: "title", skip: true }]),
      D.gallerySlide([]), D.gallerySlide(undefined)];""") == [2, 0, -1, -1]


def test_a_slide_size_is_named_and_written_as_the_deck_writes_it() -> None:
    assert _node("""return [
      D.slideSize({}), D.slideSize({ style: { width: 720 } }), D.slideSize({ style: { width: 1000, height: 500 } }),
      D.sized({ style: { title_size: 32 } }, "4:3"), D.sized({ style: { width: 720 } }, "16:9"),
      D.sized({}, { width: 99999, height: 10 }), D.sized({ id: "t" }, "nonsense")];""") == [
        {"width": 960, "height": 540, "value": "16:9", "ratio": 960 / 540},
        {"width": 720, "height": 540, "value": "4:3", "ratio": 720 / 540},
        {"width": 1000, "height": 500, "value": "custom", "ratio": 2},
        {"style": {"title_size": 32, "width": 720}},
        {},
        {"style": {"width": 4032, "height": 72}},
        {"id": "t"},
    ]


def test_a_variant_is_put_over_the_deck_and_marked_once_it_is_in_use() -> None:
    assert _node("""const deck = { theme: "dark", palette: "Tableau", footer: "GBI" };
      const made = D.applyVariant({ ...deck }, { theme: null, palette: "Okabe-Ito", footer: "else" });
      return [made, D.withVariant(deck, { theme: "swiss" }), D.hasVariant(made, { palette: "Okabe-Ito", theme: null }),
        D.hasVariant(deck, { theme: null }), D.keyOf({ a: 1 }, 2) === D.keyOf({ a: 1 }, 2),
        D.keyOf({ a: 1 }) === D.keyOf({ a: 2 })];""") == [
        {"palette": "Okabe-Ito", "footer": "GBI"},
        {"theme": "swiss", "palette": "Tableau", "footer": "GBI"},
        True,
        False,
        True,
        False,
    ]


def test_a_background_is_the_themes_none_a_colour_or_a_picture() -> None:
    assert _node("""return [{}, { background: true }, { background: false }, { background: "#ABCDEF" },
      { background: "paper.png" }].map((deck) => D.backgroundOf(deck))
      .concat([D.BACKGROUNDS.every(([colour]) => /^#[0-9a-f]{6}$/.test(colour))]);""") == [
        {"kind": "theme", "value": None},
        {"kind": "theme", "value": None},
        {"kind": "none", "value": False},
        {"kind": "colour", "value": "#abcdef"},
        {"kind": "picture", "value": "paper.png"},
        True,
    ]


def test_the_fonts_a_click_away_are_the_themes_then_pairs_then_one_face_this_mac_has() -> None:
    choices = _node("""return D.fontChoices(["Georgia", "helvetica neue", "Futura", "Optima"],
      ["Optima", "Nowhere Sans"]);""")
    assert [choice["value"] for choice in choices] == ["", "Georgia / Helvetica Neue", "Optima"]
    assert choices[0]["variant"] == {"font": None, "title_font": None, "figure_font": None}
    assert choices[1]["variant"] == {"font": "Helvetica Neue", "title_font": "Georgia", "figure_font": None}
