"""Convert to Figure Parts on a slide (``flexo_talk.studio.convert``): the slide's shapes drawn as
a diagram -- as pasted from Inkscape -- made a figure on the slide, written in the deck as a
slide's figure is, in the deck's theme; what is no part of the diagram drawn over the figure; the
slide's other lines glued to it, or to the objects they were glued to, where those now are."""

from __future__ import annotations

from pathlib import Path

import pytest
from flexo.studio.figure_edit import EditError

from flexo_talk.compose import render_slide
from flexo_talk.document import deck_from_document
from flexo_talk.studio import DeckKind


def box(x: float, y: float, text: str, **more: object) -> dict:
    return {"kind": "rectangle", "at": [x, y], "size": [160, 70], "fill": "#cfe2f3", "text": text, **more}


def diagram() -> list[dict]:
    """Three boxes in a row with arrows, a highlight round two, and a free curve."""

    return [
        box(80, 200, "Reads", id="reads"),
        box(320, 200, "Align", id="align"),
        box(560, 200, "Call", id="call", fill="#fce5cd"),
        {"kind": "arrow", "from": {"shape": "reads"}, "to": {"shape": "align"}, "build": True},
        {"kind": "arrow", "from": [482, 235], "to": [558, 235]},
        {"kind": "highlight", "at": [300, 180], "size": [440, 110], "hidden": True},
        {"kind": "pen", "points": [[100, 120], [200, 90], [300, 130]]},
    ]


def deck(body: list, shapes: list, **slide: object) -> dict:
    return {
        "schema_version": 1,
        "deck": {"id": "talk", "theme": "paper"},
        "slides": [{"title": "Drawn"}, {"title": "The pipeline", "body": body, "shapes": shapes, **slide}],
    }


def test_shapes_on_a_slide_are_made_a_figure_on_it_in_place_of_its_placeholder(tmp_path: Path) -> None:
    document = deck([{"text": ""}], diagram())
    result = DeckKind().act(document, {"do": "convert", "slide": 1, "shapes": list(range(7))}, tmp_path)
    slide = result["document"]["slides"][1]
    assert result["said"] == "3 shapes and 2 lines; 2 kept as shapes"
    assert result["select"] == {"slide": 1, "region": "body", "index": 0}
    # The shapes went from the slide, and the empty text the layout had is the figure now.
    assert "shapes" not in slide and len(slide["body"]) == 1
    figure = slide["body"][0]["figure"]
    assert figure["figure"] == {"id": "diagram"}  # in the deck's theme: none of its own
    assert [node["id"] for node in figure["nodes"]] == ["reads", "align", "call"]
    assert [(edge["from"], edge["to"]) for edge in figure["edges"]] == [("reads", "align"), ("align", "call")]
    assert figure["groups"][0]["layout"]["kind"] == "row"
    # What is no part of it is drawn over the figure, attached: nothing of a slide's own kept.
    highlight, curve = figure["shapes"]
    assert highlight["around"] == ["align", "call"] and "hidden" not in highlight
    assert curve["kind"] == "pen" and "on" in curve
    # It draws, and the document is untouched.
    assert document["slides"][1]["shapes"] == diagram()
    made = deck_from_document(result["document"], tmp_path)
    assert render_slide(made, made.slides[1]).svg


def test_the_slides_other_lines_follow_the_figure_and_the_objects_after_it(tmp_path: Path) -> None:
    shapes = [
        *diagram(),
        # Not chosen: glued to a box made the figure, and to the list after where it goes.
        {"kind": "arrow", "from": [900, 500], "to": {"shape": "call", "side": "bottom"}},
        {"kind": "arrow", "from": [900, 100], "to": {"object": "body[1]"}},
        {"kind": "arrow", "from": [900, 300], "to": {"object": "body[0]"}},
    ]
    body = [{"text": "Before it."}, {"bullets": ["After it"]}]
    action = {"do": "convert", "slide": 1, "shapes": list(range(7)), "region": "body", "index": 1}
    result = DeckKind().act(deck(body, shapes), action, tmp_path)
    slide = result["document"]["slides"][1]
    assert [next(iter(block)) for block in slide["body"]] == ["text", "figure", "bullets"]
    to_call, to_list, to_text = (shape["to"] for shape in slide["shapes"])
    assert to_call["object"] == "body[1]" and to_call["side"] == "bottom" and len(to_call["at"]) == 2
    assert to_list == {"object": "body[2]"}
    assert to_text == {"object": "body[0]"}


def test_a_slide_with_no_room_for_objects_or_no_diagram_says_so(tmp_path: Path) -> None:
    with pytest.raises(EditError, match="no room for objects"):
        DeckKind().act(deck([], diagram(), layout="title"), {"do": "convert", "slide": 1, "shapes": [0]}, tmp_path)
    with pytest.raises(EditError, match="reads as a diagram"):
        DeckKind().act(deck([], diagram()), {"do": "convert", "slide": 1, "shapes": [5]}, tmp_path)
    with pytest.raises(EditError, match="Choose the shapes"):
        DeckKind().act(deck([], diagram()), {"do": "convert", "slide": 1, "shapes": [9]}, tmp_path)


def test_a_figure_made_on_a_slide_has_an_id_no_other_figure_of_the_deck_has(tmp_path: Path) -> None:
    taken = {"figure": {"figure": {"id": "diagram"}, "nodes": [{"id": "a", "label": "A"}]}}
    document = deck([taken], diagram()[:5])
    result = DeckKind().act(document, {"do": "convert", "slide": 1, "shapes": list(range(5))}, tmp_path)
    assert result["document"]["slides"][1]["body"][1]["figure"]["figure"]["id"] == "diagram-2"


def test_a_line_chosen_glued_to_what_stays_on_the_slide_ends_where_that_was(tmp_path: Path) -> None:
    shapes = [
        *diagram()[:5],
        box(80, 420, "Notes", id="notes"),
        {"kind": "arrow", "from": [600, 100], "to": {"shape": "notes"}},
    ]
    # The boxes, their lines and the pointer at the notes chosen; the notes left on the slide.
    result = DeckKind().act(deck([], shapes), {"do": "convert", "slide": 1, "shapes": [0, 1, 2, 3, 4, 6]}, tmp_path)
    slide = result["document"]["slides"][1]
    (pointer,) = slide["body"][0]["figure"]["shapes"]
    assert isinstance(pointer["to"], list) and len(pointer["to"]) == 2
    assert slide["shapes"] == [box(80, 420, "Notes", id="notes")]
    made = deck_from_document(result["document"], tmp_path)
    assert render_slide(made, made.slides[1]).svg


def test_the_agents_tool_makes_a_slides_shapes_a_figure(tmp_path: Path) -> None:
    import yaml
    from flexo.studio.agent import Tools
    from flexo.studio.workspace import Workspace

    (tmp_path / "talk.yaml").write_text(yaml.safe_dump(deck([{"text": ""}], diagram()), sort_keys=False))
    workspace = Workspace(tmp_path)
    try:
        tools = Tools(workspace, {"id": "agent", "name": "Claude"})
        said, failed = tools.call("convert_to_figure_parts", {"file": "talk.yaml", "slide": 2})
        assert not failed and said[0]["text"].startswith("3 shapes and 2 lines; 2 kept as shapes, in talk.yaml")
        slide = workspace.open("talk.yaml").document["slides"][1]
        assert "figure" in slide["body"][0] and "shapes" not in slide
        said, failed = tools.call("convert_to_figure_parts", {"file": "talk.yaml"})
        assert failed and "Say which slide" in said[0]["text"]
    finally:
        workspace.close()
