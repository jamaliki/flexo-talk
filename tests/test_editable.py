"""Make Editable on a slide (``flexo_talk.studio.editable``): a drawing placed as a picture made
the slide's own shapes -- one group exactly where the slide drew the picture, at the size it
was drawn -- the picture gone from its region, its build, caption and crop kept as shapes can
keep them, what was glued to it glued to the group; one picture, or every one in the deck, in
one answer (one step in the history)."""

from __future__ import annotations

import copy
import xml.etree.ElementTree as ET
from pathlib import Path

import pytest
from flexo import freeform
from flexo.studio.figure_edit import EditError

from flexo_talk.compose import EDITING, PLACEHOLDERS, STANDING_ASIDE, render_slide
from flexo_talk.document import deck_from_document
from flexo_talk.studio import DeckKind
from flexo_talk.studio.editable import drawings_in

DRAWING = """<?xml version="1.0" encoding="UTF-8"?>
<svg xmlns="http://www.w3.org/2000/svg" width="200" height="100" viewBox="0 0 200 100">
  <g id="g20">
    <rect id="rect3" x="0" y="0" width="100" height="50" fill="#4a90d9"/>
    <rect id="encoder" x="120" y="10" width="60" height="30" fill="#ffffff" stroke="#000000"/>
    <text id="text4" x="10" y="80" font-size="12" fill="#000000">Encoder</text>
  </g>
</svg>
"""


def folder(tmp_path: Path) -> Path:
    (tmp_path / "assets").mkdir()
    (tmp_path / "assets" / "module.svg").write_text(DRAWING, encoding="utf-8")
    (tmp_path / "assets" / "other.svg").write_text(DRAWING.replace("#4a90d9", "#c0392b"), encoding="utf-8")
    return tmp_path


def deck() -> dict:
    return {
        "schema_version": 1,
        "deck": {"id": "talk", "theme": "paper"},
        "slides": [
            {"title": "Words", "body": [{"text": "No drawing here"}]},
            {
                "layout": "two-columns",
                "title": "A module",
                "left": [{"bullets": ["Step one"], "build": True}],
                "right": [{"image": "assets/module.svg", "build": True, "caption": "The *module*"}],
                "shapes": [
                    {"kind": "arrow", "from": [100, 480], "to": {"object": "right[0]", "side": "left"}, "build": True},
                    {
                        "kind": "inset",
                        "of": "right[0]",
                        "region": [0.1, 0.1, 0.3, 0.3],
                        "at": [40, 300],
                        "size": [120, 90],
                    },
                ],
            },
            {
                "title": "Between words",
                "body": [{"text": "Before"}, {"image": "assets/other.svg", "crop": [0, 0, 0.5, 1]}, {"text": "After"}],
                "shapes": [{"kind": "arrow", "from": [60, 500], "to": {"object": "body[2]"}}],
            },
        ],
    }


def drawn_box(document: dict, base: Path, number: int, name: str) -> list[float]:
    """Where the slide draws the picture ``name`` while it is edited (its whole, in its points)."""

    built = deck_from_document(copy.deepcopy(document), base)
    tokens = (EDITING.set(True), PLACEHOLDERS.set(True), STANDING_ASIDE.set(True))
    try:
        svg = render_slide(built, built.slides[number]).svg
    finally:
        for variable, token in zip((EDITING, PLACEHOLDERS, STANDING_ASIDE), tokens, strict=True):
            variable.reset(token)
    found = {item.get("id"): item for item in ET.fromstring(svg).iter() if item.get("id")}
    element = found.get(f"{name}.picture", found.get(name))
    return [float(value) for value in element.get("data-flexo-whole").split()]


def test_a_picture_is_made_its_shapes_where_the_slide_drew_it(tmp_path: Path) -> None:
    base = folder(tmp_path)
    document = deck()
    kept = copy.deepcopy(document)
    x, y, width, height = drawn_box(document, base, 1, "slide2.right.0")
    result = DeckKind().act(document, {"do": "editable", "at": {"slide": 1, "region": "right", "index": 0}}, base)
    assert document == kept  # (the deck asked of is as it was: the answer is the deck to be)
    slide = result["document"]["slides"][1]
    # The picture gone from its column; the other column as it was.
    assert slide["right"] == [] and slide["left"] == kept["slides"][1]["left"]
    group = slide["shapes"][0]
    assert group["kind"] == "group" and group["id"] == "module"
    # Its drawing exactly where the picture was drawn, at the size it was drawn (a 960-wide
    # slide: the shapes' units are its points).
    blue = next(
        shape
        for shape in group["shapes"]
        if shape.get("fill") not in (None, "paper", "none") and shape["kind"] == "rectangle"
    )
    assert blue["at"] == pytest.approx([x, y], abs=0.05)
    assert blue["size"] == pytest.approx([width / 2, height / 2], abs=0.05)
    # Built in on a click: the group builds, the first of the slide's shapes that do (said: the
    # list before it no longer builds later than it did).
    assert group["build"] is True and slide["shapes"][1]["build"] is True
    # Its caption, a box of words under it, a size smaller, centred.
    caption = group["shapes"][-1]
    assert caption["kind"] == "text" and caption["text"] == "The *module*" and caption["align"] == "middle"
    assert caption["at"][1] >= y + height
    # A line glued to the picture glued to the group; its zoom inset taken away, and said.
    arrow = slide["shapes"][1]
    assert arrow["to"] == {"shape": "module", "side": "left"}
    assert not any(shape.get("kind") == "inset" for shape in slide["shapes"])
    assert "A zoom inset of it is taken away" in result["said"]
    assert result["said"].startswith("Made editable: 3 shapes, where the picture was")
    assert result["select"] == {"slide": 1, "shape": 0}
    # The drawing's file stays.
    assert (base / "assets" / "module.svg").is_file()
    # The slide draws.
    deck_from_document(result["document"], base)


def test_a_crop_and_the_objects_after_it_follow(tmp_path: Path) -> None:
    base = folder(tmp_path)
    result = DeckKind().act(deck(), {"do": "editable", "at": {"slide": 2, "region": "body", "index": 1}}, base)
    slide = result["document"]["slides"][2]
    # The body closes up after it; a line glued to the object after it, to it where it is now.
    assert slide["body"] == [{"text": "Before"}, {"text": "After"}]
    assert slide["shapes"][1]["to"] == {"object": "body[1]"}
    # Only its left half was shown: the box on its right, which the crop hid, is left out.
    group = slide["shapes"][0]
    assert not any(shape.get("id") == "encoder" for shape in group["shapes"])
    assert "1 shape its crop hid is left out" in result["said"]
    assert "build" not in group


def test_every_drawing_in_the_deck_at_once(tmp_path: Path) -> None:
    base = folder(tmp_path)
    document = deck()
    assert drawings_in(document) == [(1, "right", 0), (2, "body", 1)]
    result = DeckKind().act(document, {"do": "editable", "all": True}, base)
    slides = result["document"]["slides"]
    assert drawings_in(result["document"]) == []
    assert [shape["id"] for shape in (slides[1]["shapes"][0], slides[2]["shapes"][0])] == ["module", "other"]
    assert result["made"] == 2 and result["said"].startswith("2 drawings on 2 slides made editable")
    assert slides[0] == document["slides"][0]
    with pytest.raises(EditError, match="No slide has a drawing"):
        DeckKind().act(result["document"], {"do": "editable", "all": True}, base)


def test_only_a_drawings_picture_is_made_editable(tmp_path: Path) -> None:
    base = folder(tmp_path)
    with pytest.raises(EditError, match="not a drawing"):
        DeckKind().act(deck(), {"do": "editable", "at": {"slide": 0, "region": "body", "index": 0}}, base)
    gone = deck()
    (base / "assets" / "other.svg").unlink()
    with pytest.raises(EditError, match=r"other\.svg on slide 3"):
        DeckKind().act(gone, {"do": "editable", "at": {"slide": 2, "region": "body", "index": 1}}, base)


def test_the_group_is_where_the_picture_was_drawn_on_a_slide_of_another_size(tmp_path: Path) -> None:
    base = folder(tmp_path)
    document = deck()
    document["deck"]["style"] = {"width": 1280, "height": 720}
    x, _, width, _ = drawn_box(document, base, 1, "slide2.right.0")
    built = deck_from_document(copy.deepcopy(document), base)
    k = built.style.width / 960.0
    result = DeckKind().act(document, {"do": "editable", "at": {"slide": 1, "region": "right", "index": 0}}, base)
    group = result["document"]["slides"][1]["shapes"][0]
    blue = next(shape for shape in group["shapes"] if shape["kind"] == "rectangle")
    # (Its page, 200 pixels across, as wide as the picture was drawn: the box, half of it.)
    assert blue["at"][0] == pytest.approx(x / k, abs=0.05)
    assert blue["size"][0] == pytest.approx(width / k / 2, abs=0.05)
    left, _, right, _ = freeform.bounds({**group, "shapes": group["shapes"][:-1]})
    assert left == pytest.approx(x / k, abs=0.6) and right == pytest.approx((x + width * 0.9) / k, abs=1.0)
