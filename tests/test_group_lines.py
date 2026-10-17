"""A line to a group on a slide (``flexo.group_ends``): drawn as the figure draws it, turned
with the figure to fit its place, and built in with the last of what the group holds."""

from __future__ import annotations

from pathlib import Path

import pytest

FIGURE = {
    "figure": {"id": "in-and-out"},
    "groups": [
        {"id": "root", "role": "canvas", "layout": {"kind": "row", "gap": 30, "align": "center"},
         "children": ["ins", "cell", "outs"]},
        {"id": "ins", "role": "layout", "layout": {"kind": "row", "gap": 6}, "children": ["a", "plus", "b"]},
        {"id": "outs", "role": "layout", "layout": {"kind": "row", "gap": 6}, "children": ["x", "y"]},
    ],
    "nodes": [
        {"id": "a", "label": "ACV tripeptide"}, {"id": "plus", "kind": "text", "label": "+"},
        {"id": "b", "label": "Oxygen"}, {"id": "cell", "label": "Penicillium", "height": 50},
        {"id": "x", "label": "Isopenicillin N"}, {"id": "y", "label": "Water"},
    ],
    "edges": [{"from": "ins", "to": "cell"}, {"from": "cell", "to": "outs"}],
}


@pytest.mark.parametrize("turn", [True, False])
def test_a_figure_with_lines_to_groups_is_drawn_on_a_slide_turned_or_kept_as_written(
    tmp_path: Path, monkeypatch, turn: bool
) -> None:
    """Laid out for a tall place, the figure turns (rows become columns): its lines to the
    groups are routed in the turned figure, as they are in the one kept as written."""

    from flexo_talk import compose
    from flexo_talk.studio import DeckKind

    monkeypatch.setenv("FLEXO_TALK_CACHE", "0")
    name = f"grouped-{turn}"
    slide = {"title": "In and out", "layout": "two-columns",
             "left": [{"bullets": ["Everything going in", "The cell", "Everything coming out"]}],
             "right": [{"figure": FIGURE, "turn": turn}]}
    document = {"deck": {"id": name}, "slides": [slide]}
    drawing = DeckKind().draw(document, tmp_path, {"settle": True})
    assert not [message.text for message in drawing.messages if message.severity == "error"]
    svg = drawing.pages[0].svg
    # (Its parts' ids are the figure's, after the place it has on the slide.)
    assert '.edge.1.ins-to-cell"' in svg and '.edge.2.cell-to-outs"' in svg
    layout = compose._LAYOUTS[next(key for key in compose._LAYOUTS if key[0] == name)]
    assert layout.startswith("turned") == turn


def test_a_line_to_a_group_builds_in_with_the_last_of_what_the_group_holds() -> None:
    from flexo.serialization import parse_figure

    from flexo_talk.compose import part_steps

    steps = part_steps(parse_figure(FIGURE), [["a"], ["cell"], ["plus", "b"]])
    # In with "b", the last of the substrates; out with the cell, its products never built in.
    assert (steps["edge.1.ins-to-cell"], steps["edge.2.cell-to-outs"]) == (3, 2)
    # A group named on a click of its own: the line comes with it.
    steps = part_steps(parse_figure(FIGURE), [["cell"], ["outs"]])
    assert steps["edge.2.cell-to-outs"] == 2
