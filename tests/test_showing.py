"""Anything on a slide shown, highlighted, dimmed or hidden where it stands
(``flexo_talk.showing``): every object, its parts -- a list's items, a table's rows, a gallery's
pictures, numbers, code's lines -- and the slide's shapes, said with ``hide``, ``dim`` and
``highlight`` as a figure's parts are; read and written back as written, checked, drawn the
figure's way (nothing moves), and kept so in the show, the PDF and the PowerPoint."""

from __future__ import annotations

import json
import re
import shutil
import subprocess
import xml.etree.ElementTree as ET
import zipfile
from pathlib import Path

import pytest
from flexo.showing import faint
from PIL import Image as Pixels

from flexo_talk import Deck
from flexo_talk.compose import PLACEHOLDERS, render_slide
from flexo_talk.document import DeckDocumentError, deck_document, deck_from_document
from flexo_talk.export import build_deck
from flexo_talk.showing import item_paths, lookup, slide_states

SHOWN = Path(__file__).parents[1] / "src/flexo_talk/studio/static/shown.js"
PAGE = "#ffffff"


def deck_of(*slides: dict) -> dict:
    return {"schema_version": 1, "deck": {"id": "talk", "theme": "paper"}, "slides": list(slides)}


def drawn(document: dict, index: int = 0, *, editing: bool = False, base: Path | str = "."):
    deck = deck_from_document(document, base)
    token = PLACEHOLDERS.set(editing)
    try:
        rendered = render_slide(deck, deck.slides[index])
    finally:
        PLACEHOLDERS.reset(token)
    return rendered, ET.fromstring(rendered.svg)


def marks(root: ET.Element) -> dict[str, str]:
    return {item.get("id"): item.get("data-flexo-show") for item in root.iter() if item.get("data-flexo-show")}


def element(root: ET.Element, ident: str) -> ET.Element | None:
    return next((item for item in root.iter() if item.get("id") == ident), None)


def geometry(root: ET.Element) -> list[tuple]:
    """Where everything is drawn: its place and size, nothing of how it is painted."""

    keys = ("x", "y", "cx", "cy", "r", "width", "height", "d", "transform", "points")
    return [(item.get("id"), *(item.get(key) for key in keys)) for item in root.iter()]


LIST = {"bullets": ["One", ["One a", "One b"], "Two", "Three"]}
TABLE = {"table": [["Model", "Loss"], ["A", "0.31"], ["B", "0.27"]]}


# -- the document --


def test_every_object_says_how_it_is_shown_and_is_written_back_as_written(tmp_path: Path) -> None:
    Pixels.new("RGB", (8, 6), (200, 30, 30)).save(tmp_path / "cell.png")
    body = [
        {**LIST, "highlight": [2], "hide": ["1.2"]},
        {**TABLE, "dim": ["3"], "hide": ["2.2"]},
        {"text": "Words", "dim": True},
        {"image": "cell.png", "hide": True},
        {"gallery": ["cell.png", "cell.png"], "highlight": [2]},
        {"stats": [{"value": "93%", "label": "a"}, {"value": "7", "label": "b"}], "dim": [1]},
        {"code": "a = 1\nb = 2", "hide": [2]},
        {"quote": "Said", "highlight": True},
        {"math": "E = mc^2", "dim": True},
        {"callout": "Note", "hide": True, "dim": False},
    ]
    shapes = [{"kind": "star", "at": [0, 0], "size": [40, 40], "dim": True},
              {"kind": "star", "at": [50, 0], "size": [40, 40], "hidden": True},
              {"kind": "star", "at": [100, 0], "size": [40, 40], "highlight": True}]
    document = deck_of({"title": "All of it", "body": body, "shapes": shapes})
    written = deck_document(deck_from_document(document, tmp_path))
    assert written["slides"][0]["body"] == body
    assert written["slides"][0]["shapes"] == shapes


def test_a_figure_shows_its_parts_by_name_and_itself_whole() -> None:
    figure = {"figure": {"id": "p"}, "nodes": [{"id": "a", "label": "A"}, {"id": "b", "label": "B"}],
              "edges": [{"from": "a", "to": "b"}]}
    _, root = drawn(deck_of({"title": "F", "body": [{"figure": figure, "hide": True, "dim": ["a"]}]}))
    found = marks(root)
    assert found["slide1.body.0"] == "hidden"
    # Its part dimmed in it, as before: in the figure's own drawing.
    assert found["slide1.body.0.a"] == "dimmed"


def test_python_says_it_as_a_document_does() -> None:
    deck = Deck(id="talk")
    slide = deck.slide("Python")
    slide.bullets("One", "Two", "Three").show(highlight=[2])
    slide.text("Faint").show(dim=True)
    rendered = render_slide(deck, deck.slides[0])
    assert rendered.shown == {"slide1.body.0.0": "dimmed", "slide1.body.0.2": "dimmed", "slide1.body.1": "dimmed"}
    assert deck_document(deck)["slides"][0]["body"][0]["highlight"] == [2]


@pytest.mark.parametrize(("block", "said"), [
    ({"text": "Words", "dim": [1]}, "A text is dimmed as a whole: dim: true"),
    ({**LIST, "hide": "yes"}, "hide must be true (the whole list) or a list of its items by number"),
    ({**LIST, "highlight": ["two"]}, "highlight names a list\u2019s items by number, from 1"),
    ({**LIST, "dim": [0]}, "dim names a list\u2019s items by number"),
    ({**TABLE, "hide": ["1.2.3"]}, "hide names a table\u2019s rows by number"),
    ({"code": "x", "dim": ["1.1"]}, "dim names a code\u2019s lines by number"),
    ({"figure": {"figure": {"id": "p"}, "nodes": [{"id": "a"}]}, "dim": [1]}, "figure\u2019s parts"),
])
def test_what_cannot_be_shown_so_is_said_where_it_is(block: dict, said: str) -> None:
    with pytest.raises(DeckDocumentError, match=re.escape(said)) as raised:
        deck_from_document(deck_of({"title": "Wrong", "body": [block]}), ".")
    assert raised.value.where.startswith("slides[0].body[0]")


def test_a_part_the_object_has_none_of_is_passed_over() -> None:
    rendered, root = drawn(deck_of({"title": "Gone", "body": [{**LIST, "hide": [9], "highlight": ["7.1"]}]}))
    assert rendered.shown == {} and not marks(root)


def test_a_lists_items_are_named_as_a_document_nests_them() -> None:
    assert item_paths([0, 1, 1, 0, 1, 2, 0]) == ["1", "1.1", "1.2", "2", "2.1", "2.1.1", "3"]


# -- drawn --


def test_each_object_is_hidden_dimmed_or_highlighted_where_it_stands(tmp_path: Path) -> None:
    Pixels.new("RGB", (8, 6), (200, 30, 30)).save(tmp_path / "cell.png")
    blocks = [LIST, TABLE, {"text": "Words"}, {"image": "cell.png"}, {"stats": [{"value": "9", "label": "x"}]},
              {"code": "a = 1"}, {"quote": "Said", "by": "Someone"}, {"math": "E = mc^2"}, {"callout": "Note"}]
    for index, block in enumerate(blocks):
        for key, how in (("hide", "hidden"), ("dim", "dimmed")):
            rendered, after = drawn(deck_of({"title": "One", "body": [{**block, key: True}]}), base=tmp_path,
                                    editing=True)
            _, edited = drawn(deck_of({"title": "One", "body": [block]}), base=tmp_path, editing=True)
            assert marks(after).get("slide1.body.0") == how, (index, key)
            # Nothing moves: hidden, its place is kept; faint, it is where it was.
            assert geometry(after) == geometry(edited), (index, key)
            assert rendered.shown == {"slide1.body.0": how}
            if how == "hidden":
                assert element(after, "slide1.body.0").get("visibility") == "hidden"


def test_dimmed_is_the_figures_faint_and_a_picture_see_through(tmp_path: Path) -> None:
    Pixels.new("RGB", (8, 6), (200, 30, 30)).save(tmp_path / "cell.png")
    _, root = drawn(deck_of({"title": "Faint", "body": [{"text": "Words", "dim": True},
                                                        {"image": "cell.png", "dim": True}]}), base=tmp_path)
    words = element(root, "slide1.body.0")
    assert words.get("fill") == faint("#242126", PAGE) and words.get("data-flexo-fill") is None
    assert element(root, "slide1.body.1").get("opacity") == "0.28"


def test_a_lists_item_highlighted_draws_its_others_faint_and_its_own_items_with_it() -> None:
    _, root = drawn(deck_of({"title": "List", "body": [{**LIST, "highlight": [1]}]}))
    # One (0), its two under it (1, 2) shown; Two (3) and Three (4) faint, bullet and words.
    assert marks(root) == {f"slide1.body.0.{n}{piece}": "dimmed" for n in (3, 4) for piece in ("", ".mark")}
    _, root = drawn(deck_of({"title": "List", "body": [{**LIST, "highlight": ["1.2"], "hide": [3]}]}))
    found = marks(root)
    assert "slide1.body.0.2" not in found
    assert found["slide1.body.0.0"] == found["slide1.body.0.1"] == found["slide1.body.0.3"] == "dimmed"
    assert found["slide1.body.0.4"] == "hidden"


def test_a_tables_row_or_cell_and_its_header_kept_among_highlights() -> None:
    _, root = drawn(deck_of({"title": "Table", "body": [{**TABLE, "hide": [2]}]}))
    hidden = {ident for ident, how in marks(root).items() if how == "hidden"}
    assert hidden == {"slide1.body.0.1.0", "slide1.body.0.1.1"}
    _, root = drawn(deck_of({"title": "Table", "body": [{**TABLE, "highlight": [3]}]}))
    # The header row stays as it is; the other row is faint.
    assert set(marks(root)) == {"slide1.body.0.1.0", "slide1.body.0.1.1"}
    _, root = drawn(deck_of({"title": "Table", "body": [{**TABLE, "dim": ["2.2"]}]}))
    assert marks(root) == {"slide1.body.0.1.1": "dimmed"}


def test_gallery_pictures_numbers_and_lines_of_code_by_number(tmp_path: Path) -> None:
    Pixels.new("RGB", (8, 6), (200, 30, 30)).save(tmp_path / "cell.png")
    body = [{"gallery": [{"picture": "cell.png", "caption": "One"}, "cell.png"], "hide": [1]},
            {"stats": [{"value": "9", "label": "x"}, {"value": "8", "label": "y"}], "highlight": [2]},
            {"code": "a = 1\nb = 2\nc = 3", "dim": [2]}]
    _, root = drawn(deck_of({"title": "Parts", "body": body}), base=tmp_path)
    found = marks(root)
    assert found["slide1.body.0.0"] == found["slide1.body.0.0.caption"] == "hidden"
    assert found["slide1.body.1.0"] == found["slide1.body.1.0.label"] == "dimmed" and "slide1.body.1.1" not in found
    assert found["slide1.body.2.1"] == "dimmed" and "slide1.body.2.0" not in found


def test_a_line_of_code_wrapped_is_shown_as_its_line_is() -> None:
    long = "value = " + " + ".join(f"term_{n}" for n in range(40))
    _, root = drawn(deck_of({"title": "Code", "body": [{"code": f"a = 1\n{long}", "hide": [2], "width": 300}]}),
                    editing=True)
    hidden = [ident for ident, how in marks(root).items() if how == "hidden"]
    assert len(hidden) > 1 and "slide1.body.0.0" not in hidden
    # (For an editor, each wrapped piece says the line it is of.)
    assert {element(root, ident).get("data-flexo-of") for ident in hidden} - {None} == {"1"}


def test_an_object_highlighted_draws_the_slides_others_faint_but_not_its_title() -> None:
    body = [{"text": "This", "highlight": True}, {"text": "That"}, {"text": "Gone", "hide": True}]
    shapes = [{"kind": "star", "at": [0, 0], "size": [40, 40]},
              {"kind": "star", "at": [50, 0], "size": [40, 40], "highlight": True}]
    rendered, root = drawn(deck_of({"title": "Look", "body": body, "shapes": shapes}))
    assert rendered.shown == {"slide1.body.1": "dimmed", "slide1.body.2": "hidden", "slide1.shapes.0": "dimmed"}
    assert "slide1.title" not in marks(root)


def test_a_shape_is_shown_as_any_object_is() -> None:
    shapes = [{"kind": "star", "at": [0, 0], "size": [40, 40], "dim": True},
              {"kind": "star", "at": [50, 0], "size": [40, 40], "hide": True, "build": True}]
    rendered, root = drawn(deck_of({"title": "Shapes", "body": [], "shapes": shapes}), editing=True)
    assert marks(root) == {"slide1.shapes.0": "dimmed", "slide1.shapes.1": "hidden"}
    # Hidden, it builds in on no click; exported, it is not written at all.
    assert rendered.steps == 1
    rendered, _ = drawn(deck_of({"title": "Shapes", "body": [], "shapes": shapes}))
    assert [layout.id for layout in rendered.shapes] == ["slide1.shapes.0"]


def test_words_dimmed_by_their_markup_are_their_own_colour_faint() -> None:
    _, root = drawn(deck_of({"title": "Words", "body": [{"text": "Plain [faint]{dim} plain", "colour": "accent"},
                                                       {"bullets": ["An [item]{dim}"]}]}))
    spans = [item for item in root.iter() if item.get("data-flexo-show") == "dimmed"]
    accent = element(root, "slide1.body.0").get("fill")
    assert [span.text for span in spans] == ["faint", "item"]
    assert spans[0].get("fill") == faint(accent, PAGE)
    assert spans[1].get("fill") == faint("#242126", PAGE)


# -- built in, presented, exported --


def test_hidden_builds_in_on_no_click_and_a_list_revealed_skips_its_hidden_item() -> None:
    body = [{"text": "One", "build": True, "hide": True}, {"text": "Two", "build": True},
            {"bullets": ["A", "B", "C"], "reveal": True, "hide": [2]}]
    rendered, _ = drawn(deck_of({"title": "Builds", "body": body}))
    assert rendered.builds == [(2, "slide1.body.1")]
    # Two, then the list's A and C: a click each.
    assert rendered.steps == 4
    gone = ET.fromstring(rendered.at_step(4))
    assert element(gone, "slide1.body.0").get("visibility") == "hidden"
    assert element(gone, "slide1.body.2.1").get("visibility") == "hidden"


def test_a_figure_that_builds_in_appears_before_its_parts_do() -> None:
    figure = {"figure": {"id": "p"}, "nodes": [{"id": n, "label": n.upper()} for n in "abc"],
              "edges": [{"from": "a", "to": "b"}, {"from": "b", "to": "c"}]}
    body = [{"text": "First", "build": True}, {"figure": figure, "build": True, "stages": [["b"], ["c"]]}]
    rendered, root = drawn(deck_of({"title": "Stages", "body": body}))
    assert rendered.builds == [(2, "slide1.body.0"), (3, "slide1.body.1"), (4, "slide1.body.1.click.1"),
                               (5, "slide1.body.1.click.2")]
    assert element(root, "slide1.body.1").get("data-flexo-step") == "3"
    assert element(root, "slide1.body.1.b").get("data-flexo-step") == "4"
    # So too placed where it says, out of its place's flow.
    placed = [{"text": "First", "build": True},
              {"figure": figure, "build": True, "stages": [["b"]], "at": [500, 100], "width": 200}]
    rendered, root = drawn(deck_of({"title": "Stages", "body": placed}))
    assert rendered.builds == [(2, "slide1.body.0"), (3, "slide1.body.1"), (4, "slide1.body.1.click.1")]
    # Hidden, neither it nor its parts take a click.
    rendered, _ = drawn(deck_of({"title": "Stages", "body": [{**body[1], "hide": True}]}))
    assert rendered.steps == 1 and rendered.builds == []


def test_the_pdf_and_the_powerpoint_keep_them(tmp_path: Path) -> None:
    Pixels.new("RGB", (8, 6), (200, 30, 30)).save(tmp_path / "cell.png")
    body = [{**LIST, "dim": [1], "hide": [3]}, {**TABLE, "hide": [2]}, {"image": "cell.png", "dim": True},
            {"text": "Gone", "hide": True}, {"bullets": ["Away"], "hide": True}]
    shapes = [{"kind": "rectangle", "at": [600, 300], "size": [80, 40], "fill": "#2266aa", "dim": True},
              {"kind": "rectangle", "at": [700, 300], "size": [80, 40], "hidden": True}]
    deck = deck_from_document(deck_of({"title": "Exported", "body": body, "shapes": shapes}), tmp_path)
    made = build_deck(deck, tmp_path / "out", ("pptx", "pdf"))
    xml = zipfile.ZipFile(made.pptx).read("ppt/slides/slide1.xml").decode()
    page = PAGE.lstrip("#").upper()
    # The list: item One and its items faint, item Three's words see-through, its room kept.
    listed = next(shape for shape in re.findall(r"<p:sp>.*?</p:sp>", xml, re.DOTALL) if "One a" in shape)
    paragraphs = re.findall(r"<a:p>.*?</a:p>", listed, re.DOTALL)
    assert len(paragraphs) == 5
    faint_ink = faint("#242126", PAGE).lstrip("#").upper()
    assert f'val="{faint_ink}"' in paragraphs[0] and "<a:alpha" not in paragraphs[0]
    assert f'<a:srgbClr val="{page}"><a:alpha val="0"/>' in paragraphs[4]
    assert 'val="242126"' in paragraphs[3]
    # The table's second row see-through, the others as they are.
    rows = re.findall(r"<a:tr .*?</a:tr>", xml, re.DOTALL)
    assert [('<a:alpha val="0"/>' in row) for row in rows] == [False, True, False]
    # The picture see-through, the shape faint; what is hidden whole is not there at all.
    assert 'alphaModFix amt="28000"' in xml
    assert f'val="{faint("#2266aa", PAGE).lstrip("#").upper()}"' in xml and 'val="2266AA"' not in xml
    assert "Gone" not in xml and "Away" not in xml and 'name="slide1.shapes.1"' not in xml
    # The PDF: nothing hidden in its words.
    text = made.pdf.read_bytes().decode("latin-1")
    assert "/ca 0.28" in text


# -- the studio's, run in Node --


def _node(code: str) -> object:
    node = shutil.which("node")
    if node is None:
        pytest.skip("Node is not installed")
    script = f"const S = await import({json.dumps(SHOWN.as_uri())});\n{code}"
    done = subprocess.run(["node", "--input-type=module", "-e", script], capture_output=True, text=True, check=True)
    return json.loads(done.stdout)


def test_the_studio_reads_and_writes_them_as_the_deck_does() -> None:
    made = _node("""
      const list = { bullets: ["One", ["One a", "", "One b"], "Two"], highlight: [2], dim: true };
      const parts = S.partsOf(list).map((part) => [part.name, part.label, part.drawn]);
      const whole = S.wholeOf(list);
      S.setPart(list, ["1.2"], "hidden");
      S.setPart(list, ["2"], "dimmed");
      const after = structuredClone(list);
      S.setWhole(list, "shown");
      const shape = S.setWhole({ kind: "star", hidden: true }, "highlighted", { shape: true });
      const slide = { body: [{ text: "x", hide: true },
        { figure: { figure: { id: "f", dim: ["a"] } }, highlight: ["b"] }], shapes: [{ kind: "star", hidden: true }] };
      const apart = S.anyApart(slide), count = S.showAll(slide);
      console.log(JSON.stringify({ parts, whole, after, list, shape, apart, count, slide,
        table: S.partsOf({ table: [["A", "B"], ["1", "2"]] }).map((part) => [part.name, part.label, part.header]),
        code: S.partsOf({ code: "\\n\\na\\n\\nb\\n" }).map((part) => part.label),
        at: [S.partAt({ bullets: ["One", ["One a"], "Two"] }, "2.mark"),
          S.partAt({ table: [["A"], ["B"]] }, "1.0.cell"), S.partAt({ code: "a\\nb" }, "3", "1")],
        name: S.partName({ table: [] }, "3") }));
    """)
    # Its items as the slide draws them: an empty one is none, and takes no number.
    assert made["parts"] == [["1", "One", 0], ["1.1", "One a", 1], ["1.2", "One b", 2], ["2", "Two", 3]]
    assert made["whole"] == "dimmed"
    assert made["after"] == {"bullets": ["One", ["One a", "", "One b"], "Two"], "dim": [2], "hide": ["1.2"]}
    assert made["list"] == {"bullets": ["One", ["One a", "", "One b"], "Two"], "dim": [2], "hide": ["1.2"]}
    # A shape's hidden, as decks said it before, gone with the way it is said now.
    assert made["shape"] == {"kind": "star", "highlight": True}
    assert made["apart"] is True and made["count"] == 4
    assert made["slide"] == {"body": [{"text": "x"}, {"figure": {"figure": {"id": "f"}}}], "shapes": [{"kind": "star"}]}
    assert made["table"] == [["1", "A · B", True], ["2", "1 · 2", False]]
    assert made["code"] == ["a", "", "b"]
    assert made["at"] == ["2", "2", "2"]
    assert made["name"] == "Table Row 3"


def test_what_is_drawn_under_an_object_is_shown_as_it_is() -> None:
    states = {"slide1.body.0": "dimmed", "slide1.body.0.3": "hidden"}
    assert lookup(states, "slide1.body.0.caption") == "dimmed"
    assert lookup(states, "slide1.body.0.3.mark") == "hidden"
    assert lookup(states, "slide1.body.10") is None


def test_a_slides_states_name_what_they_are_drawn_as() -> None:
    deck = deck_from_document(deck_of({"title": "S", "body": [{**LIST, "dim": True, "hide": [2]}]}), ".")
    assert slide_states(deck.slides[0]) == {"slide1.body.0": "dimmed", "slide1.body.0.3": "hidden"}
