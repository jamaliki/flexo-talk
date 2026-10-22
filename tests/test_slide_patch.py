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


# A start tag's attributes, as the page reads them (the drawings' values are written plainly).
# A page element, fake: its attributes by name, its style property by property, its class.
ELEMENTS = r"""
const attributes = (line) => Object.fromEntries([...line.matchAll(/\s([\w:.-]+)="([^"]*)"/g)].map((m) => [m[1], m[2]]));
const element = (given) => {
  const own = new Map(Object.entries(given).filter(([name]) => name !== "style" && name !== "class"));
  const style = new Map(P.styleOf(given.style));
  const classes = new Set((given.class || "").split(/\s+/).filter(Boolean));
  const styled = () => [...style].map(([p, v]) => `${p}: ${v}`).join("; ") || null;
  const named = () => [...classes].join(" ") || null;
  return {
    getAttribute: (name) => (name === "style" ? styled() : name === "class" ? named() : own.get(name) ?? null),
    getAttributeNode: (name) => ({ namespaceURI: null, name, value: own.get(name) }),
    setAttributeNS: (namespace, name, value) => own.set(name, value),
    removeAttribute: (name) => own.delete(name),
    style: {
      setProperty: (p, v, important) => style.set(p, important ? `${v} !important` : v),
      removeProperty: (p) => style.delete(p),
    },
    classList: { add: (name) => classes.add(name), remove: (name) => classes.delete(name) },
    seen: () => ({ ...Object.fromEntries(own), style: Object.fromEntries(style), class: [...classes] }),
  };
};
"""


def _node(script: str):
    node = shutil.which("node")
    if node is None:
        pytest.skip("Node is not installed")
    module = f"const P = await import({json.dumps(PATCH.as_uri())});\n{ELEMENTS}{script}"
    done = subprocess.run([node, "--input-type=module", "-e", module], capture_output=True, text=True, check=True)
    return json.loads(done.stdout)


def _list(tmp_path: Path, bullets: list[str]) -> str:
    document = {"deck": {"id": "patch"}, "slides": [{"title": "Uses", "body": [{"bullets": bullets}]}]}
    return DeckKind().draw(document, tmp_path, {"settle": True}).pages[0].svg


def test_a_list_typed_in_keeps_its_drawn_words_hidden_under_the_editor_as_each_key_is_drawn(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("FLEXO_TALK_CACHE", "0")
    first, last = "Therapeutic enzymes", "Enzymes useful in sustainability"
    shown = _list(tmp_path, [first, "Industrial enzymes", last])
    typed = _list(tmp_path, [first, "Industrial enzymes (drug production)", last])
    # The list's own start tag changes with its lines (its natural width, say): it is retagged,
    # while the editor has the list hidden, its words typed over it.
    seen = _node(
        f"const before = {json.dumps(shown)}.split('\\n'), after = {json.dumps(typed)}.split('\\n');\n"
        "const plan = P.patchPlan(before, after);\n"
        "const list = plan.retagged.find((tag) => tag.element.id === 'slide1.body.0');\n"
        "const was = attributes(before[list.element.start]), now = attributes(list.line);\n"
        "const live = { ...was, style: 'visibility: hidden' }, own = element(live);\n"
        "const changes = P.tagChanges(was, now, live);\n"
        "P.retag(own, element(now), changes);\n"
        "const retagged = plan.retagged.map((tag) => tag.element.id);\n"
        "console.log(JSON.stringify({ retagged, changes, own: own.seen(), now }));"
    )
    assert "slide1.body.0" in seen["retagged"]
    assert seen["changes"]["set"] and not seen["changes"]["removed"]
    # The drawn words stay hidden under the editor; what the drawing changed is made anew.
    assert seen["own"]["style"] == {"visibility": "hidden"}
    for name in seen["changes"]["set"]:
        assert seen["own"][name] == seen["now"][name]


def test_a_start_tag_made_anew_has_the_drawings_attributes_and_keeps_the_pages_own_style_and_class() -> None:
    seen = _node(
        "const was = { id: 'g', transform: 'translate(1 2)', opacity: '0.5',\n"
        "  style: 'fill: red; stroke: blue', class: 'a b' };\n"
        "const now = { id: 'g', transform: 'translate(1 2)', 'data-flexo-natural': '12',\n"
        "  style: 'fill: green; --tint: Red', class: 'b c' };\n"
        # In the page: a part sized a moment (its transform), a mark of the page's own, the words
        # typed hidden under their editor, the closed hand.
        "const live = { ...was, transform: 'scale(2)', 'data-held': '1',\n"
        "  style: 'fill: red; stroke: blue; visibility: hidden', class: 'a b grab-here' };\n"
        "const changes = P.tagChanges(was, now, live), own = element(live);\n"
        "P.retag(own, element(now), changes);\n"
        "const unchanged = P.tagChanges(was, { ...was }, { ...was });\n"
        'const styled = P.styleOf(\'fill: url("#a;b") ; font: 12px "A; B"; color: red !important;; bad\');\n'
        "console.log(JSON.stringify({ changes, own: own.seen(), unchanged, styled: Object.fromEntries(styled) }));"
    )
    assert seen["changes"] == {
        "set": ["transform", "data-flexo-natural"],
        "removed": ["opacity", "data-held"],
        "styled": ["fill", "--tint"],
        "unstyled": ["stroke"],
        "classed": ["c"],
        "unclassed": ["a"],
    }
    # Its attributes the drawing's, as a slide put in whole has them; of its style and class,
    # the drawing's changes made and the page's own kept.
    assert seen["own"] == {
        "id": "g",
        "transform": "translate(1 2)",
        "data-flexo-natural": "12",
        "style": {"fill": "green", "visibility": "hidden", "--tint": "Red"},
        "class": ["b", "grab-here", "c"],
    }
    assert all(not value for value in seen["unchanged"].values())
    assert seen["styled"] == {"fill": 'url("#a;b")', "font": '12px "A; B"', "color": "red !important"}
