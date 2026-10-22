"""A slide drawn again is patched where it changed (``studio/static/slidepatch.js``): the runs of
elements its change touched, read anew from the drawing that came, make that drawing from the
one shown -- line for line -- whatever the change: words, a part moved among the others, one
added or taken away. Run in Node."""

from __future__ import annotations

import copy
import json
import shutil
import subprocess
from pathlib import Path

import pytest

from flexo_talk.studio import DeckKind

PATCH = Path(__file__).parents[1] / "src/flexo_talk/studio/static/slidepatch.js"

# Each plan made the drawing that came from the one shown, its lines as the plan puts them in.
REBUILT = """
const rebuilt = (before, after, plan) => {
  const lines = [...before], edits = [];
  for (const range of plan.ranges) {
    edits.push({ from: range.from, to: range.to, lines: after.slice(range.start, range.end + 1) });
  }
  for (const tag of plan.retagged) edits.push({ from: tag.element.start, to: tag.element.start, lines: [tag.line] });
  edits.sort((one, other) => other.from - one.from);
  for (const edit of edits) lines.splice(edit.from, edit.to - edit.from + 1, ...edit.lines);
  return lines;
};
"""


def _plans(pairs: list[tuple[str, str]]) -> list[dict]:
    node = shutil.which("node")
    if node is None:
        pytest.skip("Node is not installed")
    script = (
        f"const P = await import({json.dumps(PATCH.as_uri())});\n{REBUILT}"
        f"const pairs = {json.dumps(pairs)};\n"
        "console.log(JSON.stringify(pairs.map(([a, b]) => {\n"
        "  const before = a.split('\\n'), after = b.split('\\n'), plan = P.patchPlan(before, after);\n"
        "  if (!plan) return null;\n"
        "  return { same: rebuilt(before, after, plan).join('\\n') === b,\n"
        "    read: plan.ranges.map((range) => range.kids.map((kid) => kid.id || kid.tag)),\n"
        "    put: plan.ranges.map((range) => after.slice(range.start, range.end + 1).join('\\n')),\n"
        "    retagged: plan.retagged.map((tag) => tag.element.id) };\n"
        "})));"
    )
    done = subprocess.run([node, "--input-type=module", "-e", script], capture_output=True, text=True, check=True)
    return json.loads(done.stdout)


def _deck(tmp_path: Path, figure: dict) -> str:
    document = {"deck": {"id": "patch"}, "slides": [{"title": "Steps", "body": [{"figure": figure}]}]}
    return DeckKind().draw(document, tmp_path, {"settle": True}).pages[0].svg


def test_a_slide_drawn_again_is_made_from_the_one_shown_by_the_elements_its_change_touched(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("FLEXO_TALK_CACHE", "0")
    nodes = [
        {"id": "read", "label": "Read"},
        {"id": "align", "label": "Align"},
        {"id": "call", "label": "Call variants"},
        {"id": "note", "kind": "text", "label": "Then"},
    ]
    figure = {
        "figure": {"id": "pipeline"},
        "nodes": nodes,
        "groups": [{"id": "root", "layout": {"kind": "row"}, "children": ["read", "align", "call", "note"]}],
        "edges": [{"from": "read", "to": "align"}, {"from": "align", "to": "call"}],
    }
    shown = _deck(tmp_path, figure)
    worded = copy.deepcopy(figure)
    worded["nodes"][1]["label"] = "Align reads to the genome"
    moved = copy.deepcopy(figure)
    moved["groups"][0]["children"] = ["read", "align", "note", "call"]
    added = copy.deepcopy(figure)
    added["nodes"].append({"id": "filter", "label": "Filter"})
    added["groups"][0]["children"].append("filter")
    taken = copy.deepcopy(figure)
    taken["nodes"] = [node for node in nodes if node["id"] != "note"]
    taken["groups"][0]["children"] = ["read", "align", "call"]
    pairs = [(shown, _deck(tmp_path, changed)) for changed in (worded, moved, added, taken)]
    plans = _plans(pairs)
    assert all(plan is not None and plan["same"] for plan in plans), plans
    # Words changed: the part, and what moved for it -- never the slide, nor the figure, whole.
    read = [id for ids in plans[0]["read"] for id in ids]
    assert "slide1.body.0.align" in read and not {"slide1", "slide1.body", "slide1.body.0"} & set(read)


def test_a_change_the_drawing_shown_cannot_be_patched_with_is_put_in_whole() -> None:
    head = '<?xml version="1.0" encoding="UTF-8"?>\n<svg id="s" viewBox="0 0 10 10">\n'
    group = (
        '  <g id="a">\n    <rect id="a.r" width="1" />\n  </g>\n  <g id="b">\n    <rect id="b.r" width="2" />\n  </g>\n'
    )
    shown = f"{head}{group}</svg>"
    # Its start tag alone changed: the element's attributes, what it holds kept.
    retagged = shown.replace('<g id="a">', '<g id="a" opacity="0.5">')
    # Two parts swapped, a "</g>" alike in both: the run widened to whole elements.
    swapped = (
        f'{head}  <g id="b">\n    <rect id="b.r" width="2" />\n  </g>\n'
        '  <g id="a">\n    <rect id="a.r" width="1" />\n  </g>\n</svg>'
    )
    # A part inside another put in, at its end.
    grown = shown.replace(
        '    <rect id="b.r" width="2" />\n', '    <rect id="b.r" width="2" />\n    <circle id="b.c" r="1" />\n'
    )
    # The drawing's own element changed: no part of it holds that.
    resized = shown.replace('viewBox="0 0 10 10"', 'viewBox="0 0 20 10"')
    plans = _plans([(shown, retagged), (shown, swapped), (shown, grown), (shown, resized)])
    assert plans[0] == {"same": True, "read": [], "put": [], "retagged": ["a"]}
    assert plans[1]["same"] and plans[1]["read"] == [["a", "b"]]
    assert plans[2]["same"] and plans[2]["put"] == ['    <circle id="b.c" r="1" />']
    assert plans[3] is None
