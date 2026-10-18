"""Pictures side by side with words under them -- a caption each, or a figure's names set under
its drawings -- end on one line, so the words under them are on one line too; and a slide's
footnotes are set small in its bottom margin, beside its number, taking no room from its body
where the margin has room for them."""

from __future__ import annotations

import re
import xml.etree.ElementTree as ET
from pathlib import Path

from flexo_talk.compose import render_slide
from flexo_talk.document import deck_from_document

LONG = "A caption long enough to run on to a second line under its picture, and on, and on."


def _picture(folder: Path, name: str, size: tuple[int, int]) -> str:
    from PIL import Image

    Image.new("RGB", size, (91, 141, 239)).save(folder / name)
    return name


def _svg(slide: dict, folder: Path, **deck: object) -> str:
    made = deck_from_document({"deck": {"id": "aligned", **deck}, "slides": [slide]}, folder)
    return render_slide(made, made.slides[0]).svg


def _down(root: ET.Element, node: ET.Element) -> float:
    """How far the groups ``node`` is in were moved down (a column lowered or centred)."""

    parents = {child: parent for parent in root.iter() for child in parent}
    down = 0.0
    while node in parents:
        node = parents[node]
        moved = re.fullmatch(r"translate\(0 ([-\d.]+)\)", node.get("transform") or "")
        down += float(moved.group(1)) if moved else 0.0
    return down


def _box(svg: str, identifier: str) -> tuple[float, float]:
    """Where an object is drawn on the slide, down it: its top and its bottom."""

    root = ET.fromstring(svg)
    node = next(item for item in root.iter() if item.get("id") == identifier)
    _, y, _, height = map(float, node.get("data-flexo-box", "").split())
    return y + _down(root, node), y + height + _down(root, node)


def _top(svg: str, identifier: str) -> float:
    """Where words are set on the slide, down it: their first line's."""

    root = ET.fromstring(svg)
    node = next(item for item in root.iter() if item.get("id") == identifier)
    line = node if node.get("y") else next(item for item in node.iter() if item.get("y"))
    return float(line.get("y")) + _down(root, node)


def _two(left: dict, right: dict) -> dict:
    return {"title": "Side by side", "layout": "two-columns", "left": [left], "right": [right]}


def test_captions_of_pictures_side_by_side_are_on_one_line(tmp_path: Path) -> None:
    wide, square = _picture(tmp_path, "wide.png", (400, 200)), _picture(tmp_path, "square.png", (300, 300))
    svg = _svg(_two({"image": wide, "caption": "Wide"}, {"image": square, "caption": "Square"}), tmp_path)
    left, right = _box(svg, "slide1.left.0.picture"), _box(svg, "slide1.right.0.picture")
    # Of other proportions, the pictures end on one line, the shorter lowered to it ...
    assert abs(left[1] - right[1]) < 0.5 and left[0] > right[0] + 20
    # ... and their captions are on one line under them.
    assert abs(_top(svg, "slide1.left.0.caption") - _top(svg, "slide1.right.0.caption")) < 0.5


def test_a_longer_caption_beside_a_short_one_still_starts_on_its_line(tmp_path: Path) -> None:
    wide, square = _picture(tmp_path, "wide.png", (400, 200)), _picture(tmp_path, "square.png", (300, 300))
    svg = _svg(_two({"image": wide, "caption": LONG}, {"image": square, "caption": "Square"}), tmp_path)
    left, right = _box(svg, "slide1.left.0.picture"), _box(svg, "slide1.right.0.picture")
    assert abs(left[1] - right[1]) < 0.5
    assert abs(_top(svg, "slide1.left.0.caption") - _top(svg, "slide1.right.0.caption")) < 0.5
    # The pictures are sized for the taller caption: it stays above the slide's number.
    assert _top(svg, "slide1.left.0.caption") < _top(svg, "slide1.number")


def test_pictures_without_captions_beside_each_other_still_share_a_top(tmp_path: Path) -> None:
    wide, square = _picture(tmp_path, "wide.png", (400, 200)), _picture(tmp_path, "square.png", (300, 300))
    svg = _svg(_two({"image": wide}, {"image": square, "caption": "Square"}), tmp_path)
    # Only one with words under it: nothing to line up, the pictures start level, as before.
    assert abs(_box(svg, "slide1.left.0")[0] - _box(svg, "slide1.right.0.picture")[0]) < 0.5


def _figure(folder: Path, name: str, picture: str, side: str) -> str:
    (folder / "figures").mkdir(exist_ok=True)
    (folder / "figures" / f"{name}.yaml").write_text(
        f"figure: {{id: {name}}}\nnodes:\n  - {{id: drawn, kind: image, label: {name.title()},"
        f" properties: {{source: {picture}, title_side: {side}}}}}\n",
        encoding="utf-8",
    )
    return f"figures/{name}.yaml"


def test_figures_named_under_their_drawings_side_by_side_end_on_one_line(tmp_path: Path) -> None:
    (tmp_path / "figures").mkdir()
    _picture(tmp_path / "figures", "wide.png", (400, 200))
    _picture(tmp_path / "figures", "tall.png", (200, 300))
    left, right = _figure(tmp_path, "wide", "wide.png", "bottom"), _figure(tmp_path, "tall", "tall.png", "bottom")
    svg = _svg(_two({"figure": left}, {"figure": right}), tmp_path)
    one, other = _box(svg, "slide1.left.0"), _box(svg, "slide1.right.0")
    # Each fitted to its column, their names under them are on one line all the same.
    assert abs(one[1] - other[1]) < 0.5 and one[0] > other[0] + 20
    # Named over their drawings, they share a top, as figures side by side always have.
    left, right = _figure(tmp_path, "wide", "wide.png", "top"), _figure(tmp_path, "tall", "tall.png", "top")
    svg = _svg(_two({"figure": left}, {"figure": right}), tmp_path)
    assert abs(_box(svg, "slide1.left.0")[0] - _box(svg, "slide1.right.0")[0]) < 0.5


def _noted(folder: Path, notes: list[str], **deck: object) -> str:
    wide = _picture(folder, "wide.png", (400, 200))
    slide = {"title": "Noted", "body": [{"image": wide}]}
    return _svg({**slide, "footnotes": notes} if notes else slide, folder, **deck)


def test_footnotes_are_set_in_the_bottom_margin_beside_the_number(tmp_path: Path) -> None:
    plain = _noted(tmp_path, [])
    noted = _noted(tmp_path, ["A source.", "Another source."])
    # The body's picture is as large as on the slide without them: they take none of its room.
    assert _box(noted, "slide1.body.0") == _box(plain, "slide1.body.0")
    picture = _box(noted, "slide1.body.0")[1]
    first, second = _top(noted, "slide1.footnote0"), _top(noted, "slide1.footnote1")
    # The first on the number's line, the next under it, all under the body.
    assert abs(first - _top(noted, "slide1.number")) < 0.5 and second > first > picture
    assert second < 540.0
    sized = re.search(r'id="slide1\.footnote0"[^>]*font-size="([\d.]+)', noted)
    number = re.search(r'id="slide1\.number"[^>]*font-size="([\d.]+)', noted)
    assert sized and number and sized.group(1) == number.group(1)


def test_footnotes_stand_over_the_decks_footer_and_the_body_ends_above_them(tmp_path: Path) -> None:
    plain = _noted(tmp_path, [], footer="Lab meeting")
    noted = _noted(tmp_path, ["A source."], footer="Lab meeting")
    note = _top(noted, "slide1.footnote0")
    assert note < _top(noted, "slide1.footer")
    assert _box(noted, "slide1.body.0")[1] < note
    assert _box(noted, "slide1.body.0")[1] < _box(plain, "slide1.body.0")[1]


def test_footnotes_too_many_for_the_margin_take_what_they_need_from_the_body(tmp_path: Path) -> None:
    plain = _noted(tmp_path, [])
    noted = _noted(tmp_path, [f"Source {n}." for n in range(6)])
    assert _box(noted, "slide1.body.0")[1] < _top(noted, "slide1.footnote0")
    assert _box(noted, "slide1.body.0")[1] < _box(plain, "slide1.body.0")[1]
    # The last stays on the slide, clear of its edge.
    assert _top(noted, "slide1.footnote5") < 540.0 - 16.0


def test_captions_of_pictures_in_a_row_are_on_one_line(tmp_path: Path) -> None:
    wide, square = _picture(tmp_path, "wide.png", (400, 200)), _picture(tmp_path, "square.png", (300, 300))
    slide = {
        "title": "Rows",
        "layout": "two-columns",
        "rows": ["", ""],
        "left": [{"text": "One"}, {"image": wide, "caption": LONG}],
        "right": [{"text": "Other"}, {"image": square, "caption": "Square"}],
    }
    svg = _svg(slide, tmp_path)
    left, right = _box(svg, "slide1.left.1.picture"), _box(svg, "slide1.right.1.picture")
    assert abs(left[1] - right[1]) < 0.5 and left[0] > right[0] + 20
    assert abs(_top(svg, "slide1.left.1.caption") - _top(svg, "slide1.right.1.caption")) < 0.5
    # How far it was moved down its row, for the studio: where it would stand were it not.
    assert re.search(r'<g data-flexo-down="[\d.]+" transform="translate\(0 [\d.]+\)">\s*<g id="slide1\.left\.1"', svg)
