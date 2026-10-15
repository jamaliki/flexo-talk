"""Shapes drawn on a slide where they are put (``Slide.shape``, a slide's ``shapes``): read and
written back as a document says them, what is wrong said where it is, drawn over (or under)
the slide's words and objects in every output, glued, built in on a click, hidden -- and in a
PowerPoint each PowerPoint's own shape."""

from __future__ import annotations

import re
import xml.etree.ElementTree as ET
from pathlib import Path

import pytest
from pptx import Presentation

from flexo_talk import Deck
from flexo_talk.compose import PLACEHOLDERS, render_slide
from flexo_talk.deck import SettingError
from flexo_talk.document import DeckDocumentError, InvalidObject, deck_document, deck_from_document, dump_document
from flexo_talk.studio import DeckKind

SVG = "{http://www.w3.org/2000/svg}"


def deck_of(*shapes: dict, body: list | None = None, **slide: object) -> dict:
    return {"schema_version": 1, "deck": {"id": "talk", "theme": "paper"},
            "slides": [{"title": "Shapes", "body": body if body is not None else [{"text": "A paragraph of words."}],
                        "shapes": list(shapes), **slide}]}


def drawn(document: dict, *, editing: bool = False) -> tuple:
    deck = deck_from_document(document, ".")
    token = PLACEHOLDERS.set(editing)
    try:
        rendered = render_slide(deck, deck.slides[0])
    finally:
        PLACEHOLDERS.reset(token)
    return rendered, ET.fromstring(rendered.svg)


def element(root: ET.Element, ident: str) -> ET.Element | None:
    return next((item for item in root.iter() if item.get("id") == ident), None)


# -- the document --


def test_shapes_are_read_and_written_back_as_written() -> None:
    shapes = [
        {"kind": "arrow", "from": [520, 300], "to": {"object": "body[0]", "side": "right"}},
        {"kind": "rounded-rectangle", "id": "note", "at": [660, 120], "size": [220, 80], "fill": "accent2-fill",
         "text": "**Binding** pocket"},
        {"kind": "arrow", "from": [770, 400], "to": {"shape": "note"}, "build": True},
        {"kind": "group", "shapes": [{"kind": "star", "at": [30, 30], "size": [50, 50]}], "hidden": True},
    ]
    document = deck_of(*shapes)
    written = deck_document(deck_from_document(document, "."))
    assert written["slides"][0]["shapes"] == shapes
    text = dump_document(written)
    # After the slide's objects, before its notes: a slide's keys as a person reads them.
    assert text.index("shapes:") > text.index("body:")


def test_a_shape_written_wrong_is_said_under_its_key() -> None:
    with pytest.raises(DeckDocumentError) as raised:
        deck_from_document(deck_of({"kind": "arrow", "from": [0, 0], "to": [1, 1], "end": "spear"}), ".")
    assert raised.value.where == "slides[0].shapes[0].end"
    with pytest.raises(DeckDocumentError) as raised:
        deck_from_document(deck_of({"kind": "ellipse", "at": [0, 0], "size": [1, 1], "build": "yes"}), ".")
    assert raised.value.where == "slides[0].shapes[0].build"


def test_in_the_studio_a_shape_written_wrong_is_left_out_and_the_rest_drawn() -> None:
    errors: list = []
    document = deck_of({"kind": "hexagon", "at": [0, 0]}, {"kind": "ellipse", "at": [10, 10], "size": [50, 50]})
    deck = deck_from_document(document, ".", errors=errors)
    assert [type(error) for error in errors] == [InvalidObject]
    assert errors[0].where == "slides[0].shapes[0].kind"
    rendered = render_slide(deck, deck.slides[0])
    root = ET.fromstring(rendered.svg)
    # Each keeps its place in the list: the second is still the second.
    assert element(root, "slide1.shapes.0") is None and element(root, "slide1.shapes.1") is not None


def test_what_a_shape_names_and_the_slide_has_not_is_said() -> None:
    errors: list = []
    deck_from_document(deck_of({"kind": "arrow", "from": [0, 0], "to": {"shape": "nothing"}},
                               {"kind": "arrow", "from": [0, 0], "to": {"object": "left[0]"}},
                               {"kind": "ellipse", "id": "a", "at": [0, 0], "size": [1, 1]},
                               {"kind": "ellipse", "id": "a", "at": [0, 0], "size": [1, 1]}), ".", errors=errors)
    said = {error.where: error.message for error in errors}
    assert "a shape called nothing" in said["slides[0].shapes[0].to"]
    assert "no such object" in said["slides[0].shapes[1].to"]
    assert "Two shapes are called a" in said["slides[0].shapes[3].id"]
    # An end with where it was kept is drawn there, its shape gone or not.
    deck_from_document(deck_of({"kind": "arrow", "from": [0, 0], "to": {"shape": "gone", "at": [5, 5]}}), ".")


def test_shapes_are_made_in_python_as_written() -> None:
    deck = Deck("talk")
    with deck.slide("Python") as slide:
        slide.text("Words")
        slide.shape("arrow", from_=[100, 100], to=[200, 150], head_size=2)
        slide.shape("ring", at=[300, 200], size=[100, 60], behind=True)
    assert deck_document(deck)["slides"][0]["shapes"] == [
        {"kind": "arrow", "from": [100, 100], "to": [200, 150], "head_size": 2},
        {"kind": "ring", "at": [300, 200], "size": [100, 60], "behind": True},
    ]
    with pytest.raises(SettingError) as raised:
        deck.slides[0].shape("ellipse", at=[0, 0], size=[1, 1], locked="no")
    assert raised.value.key == "locked"


# -- drawing --


def test_shapes_are_drawn_over_the_slide_and_behind_it_under_its_words() -> None:
    rendered, root = drawn(deck_of({"kind": "ellipse", "at": [10, 10], "size": [50, 50]},
                                   {"kind": "ring", "at": [10, 10], "size": [50, 50], "behind": True}))
    content = element(root, "slide1.content")
    order = [child.get("id") for child in content]
    assert order.index("slide1.shapes-behind") < order.index("slide1.body") < order.index("slide1.shapes")
    assert element(root, "slide1.shapes.0").get("data-flexo-talk") == "shape"
    assert [layout.behind for layout in rendered.shapes] == [False, True]


def test_a_shapes_words_are_set_in_it_in_the_slides_type() -> None:
    _, root = drawn(deck_of({"kind": "rectangle", "at": [100, 100], "size": [200, 100], "text": "Encoder",
                             "fill": "ink"}))
    words = element(root, "slide1.shapes.0.text")
    assert words is not None and "Encoder" in "".join(words.itertext())
    # On a dark fill of its own, its words are the page's colour.
    from flexo_talk.document import deck_from_document as read

    deck = read(deck_of(), ".")
    assert (words.get("fill") or "").lower() == deck.palette.get("canvas").lower()


def test_an_arrow_glued_to_a_shape_and_to_an_object_is_drawn_to_them() -> None:
    document = deck_of(
        {"kind": "rectangle", "id": "box", "at": [600, 100], "size": [100, 50]},
        {"kind": "arrow", "from": [400, 400], "to": {"shape": "box", "side": "bottom"}},
        {"kind": "arrow", "from": [700, 450], "to": {"object": "body[0]", "side": "right"}},
    )
    rendered, root = drawn(document)
    ends = [float(value) for value in element(root, "slide1.shapes.1").get("data-flexo-ends").split()]
    assert ends[2:] == pytest.approx([650.0, 150.0])
    paragraph = [float(value) for value in element(root, "slide1.shapes.2").get("data-flexo-ends").split()]
    # At the paragraph's right edge, half way down it.
    words = element(root, "slide1.body.0")
    assert words is not None
    assert 150 < paragraph[2] < 500 and 100 < paragraph[3] < 220
    assert rendered.shapes[1].glue == (None, ("slide1.shapes.0", "bottom"))


def test_moving_what_a_line_is_glued_to_moves_its_end() -> None:
    first = deck_of({"kind": "ellipse", "id": "a", "at": [100, 100], "size": [50, 50]},
                    {"kind": "line", "from": [0, 0], "to": {"shape": "a", "side": "centre"}})
    second = deck_of({"kind": "ellipse", "id": "a", "at": [300, 300], "size": [50, 50]},
                     {"kind": "line", "from": [0, 0], "to": {"shape": "a", "side": "centre"}})
    ends = [[float(v) for v in element(drawn(document)[1], "slide1.shapes.1").get("data-flexo-ends").split()]
            for document in (first, second)]
    assert ends[0][2:] != ends[1][2:]
    # (At the centre, it stops at the ellipse's outline on the way to its other end.)
    assert ends[1][2] < 325 and ends[1][3] < 325


def test_a_shape_that_builds_appears_after_the_objects_that_do() -> None:
    document = deck_of({"kind": "arrow", "from": [0, 0], "to": [10, 10], "build": True},
                       {"kind": "arrow", "from": [0, 0], "to": [20, 20]},
                       {"kind": "ellipse", "at": [0, 0], "size": [10, 10], "build": True},
                       body=[{"text": "Words", "build": True}])
    rendered, root = drawn(document)
    assert rendered.steps == 4
    assert rendered.builds == [(2, "slide1.body.0"), (3, "slide1.shapes.0"), (4, "slide1.shapes.2")]
    assert element(root, "slide1.shapes.1").get("data-flexo-step") is None
    shown = ET.fromstring(rendered.at_step(2))
    assert element(shown, "slide1.shapes.0") is None and element(shown, "slide1.shapes.1") is not None


def test_a_hidden_shape_is_faint_while_edited_and_never_shown() -> None:
    document = deck_of({"kind": "star", "at": [0, 0], "size": [50, 50], "hidden": True})
    _, editing = drawn(document, editing=True)
    shape = element(editing, "slide1.shapes.0")
    assert shape is not None and shape.get("data-flexo-placeholder") == "Hidden"
    rendered, shown = drawn(document)
    assert element(shown, "slide1.shapes.0") is None and not rendered.shapes


def test_shapes_are_scaled_with_a_slide_of_another_size() -> None:
    document = deck_of({"kind": "ellipse", "at": [0, 0], "size": [480, 270]})
    document["deck"]["style"] = {"width": 1920, "height": 1080}
    _, root = drawn(document)
    assert element(root, "slide1.shapes").get("transform") == "scale(2)"


# -- the outputs --


SHAPES = (
    {"kind": "rounded-rectangle", "id": "note", "at": [600, 100], "size": [200, 80], "corner": 20,
     "text": "Pocket", "shadow": True, "rotate": 10},
    {"kind": "arrow", "from": [400, 450], "to": {"shape": "note", "side": "bottom"}, "build": True},
    {"kind": "ellipse", "at": [100, 300], "size": [120, 80], "behind": True},
    {"kind": "star", "at": [300, 300], "size": [80, 80], "ratio": 0.5},
    {"kind": "polygon", "at": [420, 300], "size": [80, 80], "sides": 7},
    {"kind": "bubble", "at": [600, 300], "size": [160, 70], "tail": [560, 420], "text": "Hi"},
    {"kind": "brace", "from": [880, 100], "to": [880, 400], "text": "Three"},
    {"kind": "curved-arrow", "from": [100, 480], "to": [300, 470], "bend": 0.4},
    {"kind": "dimension", "from": [500, 500], "to": [650, 500], "text": "3.1 Å"},
    {"kind": "arrow-right", "at": [700, 460], "size": [120, 60], "shaft": 0.4},
    {"kind": "text", "at": [40, 400], "width": 200, "text": "A note"},
    {"kind": "group", "shapes": [{"kind": "cross", "at": [10, 10], "size": [20, 20]},
                                 {"kind": "check", "at": [40, 10], "size": [20, 20]}]},
)


def test_shapes_are_in_the_pdf_png_and_svg(tmp_path: Path) -> None:
    written = DeckKind().export(deck_of(*SHAPES), tmp_path, "talk", ["svg", "pdf", "png"], into=tmp_path / "out")
    svg = next(path for path in written if path.suffix == ".svg").read_text()
    assert svg.count('data-flexo-talk="shape"') >= len(SHAPES)
    assert next(path for path in written if path.suffix == ".pdf").stat().st_size > 1000


def test_shapes_are_powerpoints_own_with_their_words(tmp_path: Path) -> None:
    written = DeckKind().export(deck_of(*SHAPES), tmp_path, "talk", ["pptx"], into=tmp_path / "out")
    slide = Presentation(str(written[0])).slides[0]
    xml = ET.tostring(slide._element).decode()
    presets = set(re.findall(r'prst="(\w+)"', xml))
    assert {"roundRect", "ellipse", "star5", "wedgeRoundRectCallout", "leftBrace", "rightArrow",
            "straightConnector1"} <= presets
    names = {shape.name for shape in slide.shapes}
    assert "Rounded Rectangle “Pocket”" in names and "Speech Bubble “Hi”" in names and "Text Box “A note”" in names
    assert "Label “3.1 Å”" in names and "Label “Three”" in names and "Group" in names
    # A heptagon, which PowerPoint has no preset of, is a freeform of its outline.
    heptagon = next(shape for shape in slide.shapes if shape.name == "Polygon")
    assert heptagon._element.find(".//{http://schemas.openxmlformats.org/drawingml/2006/main}custGeom") is not None
    # Its turn and its corner, as PowerPoint's own.
    note = next(shape for shape in slide.shapes if shape.name.startswith("Rounded Rectangle"))
    assert note.rotation == pytest.approx(10.0)
    assert 'name="adj" fmla="val 25000"' in ET.tostring(note._element).decode()
    assert "outerShdw" in ET.tostring(note._element).decode()


def test_a_glued_arrow_is_a_connector_joined_to_its_shape(tmp_path: Path) -> None:
    written = DeckKind().export(deck_of(*SHAPES), tmp_path, "talk", ["pptx"], into=tmp_path / "out")
    slide = Presentation(str(written[0])).slides[0]
    note = next(shape for shape in slide.shapes if shape.name.startswith("Rounded Rectangle"))
    arrow = next(shape for shape in slide.shapes if shape.name == "Arrow")
    joined = arrow._element.find(".//{http://schemas.openxmlformats.org/drawingml/2006/main}endCxn")
    assert joined is not None and joined.get("id") == str(note.shape_id) and joined.get("idx") == "2"
    assert 'tailEnd type="triangle"' in ET.tostring(arrow._element).decode()


def test_a_shape_that_builds_is_a_click_in_the_powerpoint(tmp_path: Path) -> None:
    written = DeckKind().export(deck_of(*SHAPES), tmp_path, "talk", ["pptx"], into=tmp_path / "out")
    slide = Presentation(str(written[0])).slides[0]
    arrow = next(shape for shape in slide.shapes if shape.name == "Arrow")
    timing = ET.tostring(slide._element).decode()
    assert f'spid="{arrow.shape_id}"' in timing


def test_shapes_behind_are_under_the_slides_words_and_those_over_it_on_top(tmp_path: Path) -> None:
    written = DeckKind().export(deck_of(*SHAPES), tmp_path, "talk", ["pptx"], into=tmp_path / "out")
    names = [shape.name for shape in Presentation(str(written[0])).slides[0].shapes]
    words = next(index for index, name in enumerate(names) if name.startswith("Text “A paragraph"))
    assert names.index("Oval") < words < names.index("Group")


# -- the studio --


def test_the_studio_offers_every_kind_and_says_how_to_write_them() -> None:
    kind = DeckKind()
    shapes = kind.catalog()["shapes"]
    offered = [name for section in shapes["sections"] for name in section["kinds"]]
    from flexo.freeform import KINDS

    assert sorted(offered) == sorted(KINDS)
    assert shapes["frame"] == 960 and "build" in shapes["slide_keys"]
    guide = kind.guide()
    assert "Shapes (a slide's shapes" in guide and "curved-arrow: bend, lean" in guide
    assert "{shape: note, side: left}" in guide


def test_a_change_of_shapes_is_said_by_what_it_did() -> None:
    kind = DeckKind()
    before = deck_of({"kind": "ellipse", "at": [0, 0], "size": [10, 10]})
    after = deck_of({"kind": "ellipse", "at": [0, 0], "size": [10, 10]},
                    {"kind": "arrow", "from": [0, 0], "to": [5, 5]})
    assert kind.describe(before, after)[0]["text"] == "added an arrow to slide 1"
    assert kind.describe(after, before)[0]["text"] == "deleted an arrow from slide 1"


def test_drawing_a_slide_for_the_studio_draws_its_shapes_and_their_frames(tmp_path: Path) -> None:
    kind = DeckKind()
    document = deck_of({"kind": "text", "at": [100, 100]},
                       {"kind": "star", "at": [0, 0], "size": [50, 50], "hidden": True},
                       {"kind": "rectangle", "at": [200, 200], "size": [100, 50], "rotate": 30})
    page = kind.draw(document, tmp_path).pages[0]
    root = ET.fromstring(page.svg)
    # A box of words not yet written shows its placeholder while edited; its measured box is said.
    words = element(root, "slide1.shapes.0.text")
    assert words is not None and words.get("data-flexo-placeholder") == "Text"
    assert element(root, "slide1.shapes.0").get("data-flexo-box")
    assert element(root, "slide1.shapes.1").get("data-flexo-placeholder") == "Hidden"
    assert element(root, "slide1.shapes.2").get("data-flexo-turn") == "30"
    # Presented, the hidden shape is left out as any placeholder is, the slide not drawn again.
    assert "data-flexo-presented" not in page.svg


def test_a_line_is_joined_to_a_shape_written_after_it(tmp_path: Path) -> None:
    document = deck_of({"kind": "arrow", "from": [100, 100], "to": {"shape": "later", "side": "left"}},
                       {"kind": "ellipse", "id": "later", "at": [300, 50], "size": [100, 100]})
    written = DeckKind().export(document, tmp_path, "talk", ["pptx"], into=tmp_path / "out")
    slide = Presentation(str(written[0])).slides[0]
    oval = next(shape for shape in slide.shapes if shape.name == "Oval")
    arrow = next(shape for shape in slide.shapes if shape.name == "Arrow")
    joined = arrow._element.find(".//{http://schemas.openxmlformats.org/drawingml/2006/main}endCxn")
    # An oval's left is its third site, as PowerPoint numbers them.
    assert joined is not None and (joined.get("id"), joined.get("idx")) == (str(oval.shape_id), "2")


# -- a figure's own shapes, on its slide --


FIGURE = {
    "figure": {"id": "pipeline"},
    "nodes": [{"id": "encoder", "label": "Encoder"}, {"id": "decoder", "label": "Decoder"}],
    "edges": [{"from": "encoder", "to": "decoder"}],
    "shapes": [{"kind": "ring", "id": "ring", "around": ["decoder"]},
               {"kind": "arrow", "from": [-30, -20], "to": {"part": "encoder", "side": "top"}, "text": "in"}],
}


def test_a_figures_own_shapes_are_drawn_with_it_on_its_slide() -> None:
    _, root = drawn(deck_of(body=[{"figure": FIGURE}]))
    figure = next(item for item in root.iter() if item.get("data-flexo-talk") == "figure")
    drawn_over = [item for item in figure.iter() if item.get("data-flexo-shape")]
    assert {item.get("data-flexo-shape") for item in drawn_over} == {"ring", "arrow"}
    # (Its words too, in the figure's drawing.)
    assert any("".join(item.itertext()).strip() == "in" for item in figure.iter(f"{SVG}text"))


def test_a_figure_with_shapes_is_in_every_output(tmp_path: Path) -> None:
    written = DeckKind().export(deck_of(body=[{"figure": FIGURE}]), tmp_path, "talk", ["svg", "pdf", "pptx"],
                                into=tmp_path / "out")
    svg = next(path for path in written if path.suffix == ".svg").read_text()
    assert 'data-flexo-shape="ring"' in svg
    assert next(path for path in written if path.suffix == ".pdf").stat().st_size > 1000
    slide = Presentation(str(next(path for path in written if path.suffix == ".pptx"))).slides[0]

    def names(shapes) -> list[str]:
        return [name for shape in shapes
                for name in (shape.name, *(names(shape.shapes) if shape.shape_type == 6 else ()))]

    # The figure is drawn in the PowerPoint as its own shapes: the ring and the arrow among
    # them, each named for its kind (and words), as the studio names it.
    found = names(slide.shapes)
    assert "Highlight Ring" in found and "Arrow “in”" in found and "Arrowhead" in found


def test_a_figures_shapes_build_in_with_the_parts_they_are_on() -> None:
    from flexo.serialization import parse_figure

    from flexo_talk.compose import part_steps

    note = {"kind": "text", "id": "note", "at": [0, 0], "text": "late"}
    spec = parse_figure({**FIGURE, "shapes": [*FIGURE["shapes"], note]})
    steps = part_steps(spec, [["encoder"], ["decoder"], ["note"]])
    # The ring with the decoder it goes round, the arrow with the encoder it points at, the
    # note on the click that names it.
    assert (steps["ring"], steps["shapes.1"], steps["note"]) == (2, 1, 3)
    _, root = drawn(deck_of(body=[{"figure": {**FIGURE}, "stages": [["encoder"], ["decoder"]]}]))
    ring = next(item for item in root.iter() if item.get("data-flexo-shape") == "ring")
    assert ring.get("data-flexo-step") is not None
