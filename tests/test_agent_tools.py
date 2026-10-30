"""An agent reads a deck slide by slide from its outline, sees it as a sheet, outlined or at a build
step, is taught by a short brief and topics whose examples draw, and hears what each edit did to
the deck's slides and objects -- deletions above all -- and what to look at next."""

from __future__ import annotations

import base64
import re
import struct
import zlib
from pathlib import Path

import pytest
import yaml
from flexo.studio import agent_guides, agent_look
from flexo.studio.agent import Tools
from flexo.studio.workspace import Workspace

from flexo_talk.document import BLOCKS, SLIDE_KEYS
from flexo_talk.studio import DeckKind
from flexo_talk.studio.deck_agent import selected
from flexo_talk.studio.deck_guides import SNIPPETS

PERSON = {"id": "page-a", "name": "Ada", "kind": "person"}

DECK = """\
schema_version: 1
deck:
  id: talk
  theme: paper
slides:
- layout: title
  title: Figures that draw themselves
  author: Ada Lovelace
- title: Why another figure tool?
  body:
  - bullets:
    - Figures take hours to draw
    - Boxes drift out of line
    reveal: true
  - text: TODO a picture here
  shapes:
  - {kind: arrow, id: pointer, from: [520, 300], to: [640, 230]}
  - {kind: ring, at: [300, 220], size: [120, 80]}
- title: The model
  layout: two-columns
  left:
  - text: Write what the model *is*
  right:
  - figure:
      figure: {id: model}
      nodes: [{id: encoder, label: Encoder}, {id: decoder, label: Decoder}]
      edges: [{from: encoder, to: decoder}]
- title: Results
  body:
  - table: [[Model, Score], [Ours, '0.91']]
  notes: Say the score.
- title: Shared
  body:
  - figure: '#pipe'
figures:
  pipe:
    figure: {id: pipe}
    nodes: [{id: x, label: X}]
"""


@pytest.fixture(autouse=True)
def _sessions(tmp_path_factory: pytest.TempPathFactory, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("XDG_RUNTIME_DIR", str(tmp_path_factory.mktemp("run")))


@pytest.fixture
def deck(tmp_path: Path):
    (tmp_path / "talk.yaml").write_text(DECK, encoding="utf-8")
    workspace = Workspace(tmp_path)
    try:
        yield workspace, Tools(workspace, {"id": "agent", "name": "Claude"})
    finally:
        workspace.close()


def _texts(blocks: list[dict]) -> str:
    return "\n".join(block["text"] for block in blocks if block["type"] == "text")


def _images(blocks: list[dict]) -> list[tuple[int, int]]:
    return [
        agent_look.png_size(base64.b64decode(block["source"]["data"]))
        for block in blocks
        if block["type"] == "image"
    ]


def _png(width: int = 32, height: int = 24) -> bytes:
    rows = b"".join(b"\x00" + b"".join(bytes([x * 7 % 256, 90, 160]) for x in range(width)) for _ in range(height))

    def chunk(tag: bytes, data: bytes) -> bytes:
        return struct.pack(">I", len(data)) + tag + data + struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF)

    head = struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0)
    return b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", head) + chunk(b"IDAT", zlib.compress(rows)) + chunk(b"IEND", b"")


def _edit(tools: Tools, old: str, new: str) -> str:
    blocks, failed = tools.call("edit_document", {"file": "talk.yaml", "old": old, "new": new})
    assert not failed, blocks
    return blocks[0]["text"]


def _slide_text(tools: Tools, number: int) -> str:
    said, failed = tools.call("read_document", {"file": "talk.yaml", "slides": [number]})
    assert not failed
    return said[0]["text"].split(f"── slide {number} ──\n", 1)[1].rstrip("\n") + "\n"


# -- the outline, excerpts and the selection --


def test_the_outline_says_each_slide_in_a_line_and_what_is_selected(deck) -> None:
    workspace, tools = deck
    workspace.open("talk.yaml")
    where = {"page": 3, "label": "Slide 3 · Figure", "block": "right[0]", "part": "encoder"}
    workspace.set_presence(PERSON, "talk.yaml", where, None, "c")
    said, failed = tools.call("outline", {"file": "talk.yaml"})
    assert not failed
    assert said[0]["text"].splitlines() == [
        "talk.yaml (deck), version 1.",
        "Ada has selected slides[2].right[0] (Figure), part encoder.",
        "5 slides; theme paper.",
        "1. [title] Figures that draw themselves",
        "2. Why another figure tool? -- body: List, Text · 2 shapes · 3 build steps · 1 TODO",
        "3. [two-columns] The model -- left: Text; right: Figure (model, 2 parts)",
        "4. Results -- body: Table · notes",
        "5. Shared -- body: Figure (#pipe, 1 part)",
        "Shared figures (figures:, named '#name' from a slide): pipe (1 part).",
        "No warnings.",
    ]
    listed, _ = tools.call("list_documents", {})
    assert "selected: slides[2].right[0] (Figure), part encoder." in listed[0]["text"]


def test_a_place_in_the_studio_is_a_path_in_the_yaml() -> None:
    document = yaml.safe_load(DECK)
    document["slides"].append({"layout": "columns", "columns": [[{"text": "a"}], [{"text": "b"}]]})
    assert selected(document, {"page": 2, "block": "body[1]"}) == "slides[1].body[1] (Text)"
    assert selected(document, {"page": 6, "block": "columns.1[0]"}) == "slides[5].columns[1][0] (Text)"
    assert selected(document, {"page": 2, "field": "title"}) == "slides[1].title"
    assert selected(document, {"page": 4}) == "slides[3] (the slide)"
    assert selected(document, {"page": 9}) is None


def test_slides_are_read_as_the_whole_text_has_them_and_edited_so(deck) -> None:
    _, tools = deck
    whole = tools.call("read_document", {"file": "talk.yaml"})[0][0]["text"]
    said, failed = tools.call("read_document", {"file": "talk.yaml", "slides": [4, 2]})
    assert not failed
    assert said[0]["text"].startswith("talk.yaml (deck), version 1: slides 4, 2 of 5, as the whole")
    four = _slide_text(tools, 4)
    assert four.startswith("- title: Results\n") and four in whole
    assert "Say the score" in four and "Why another" not in four
    changed = _edit(tools, four, four.replace("Results", "What we found"))
    assert "edited the title on slide 4" in changed


# -- look --


def test_a_slide_is_outlined_object_by_object_with_paths_and_places(deck) -> None:
    _, tools = deck
    blocks, failed = tools.call("look", {"file": "talk.yaml", "pages": [3, 2], "annotate": True})
    assert not failed
    said = _texts(blocks)
    assert re.search(r"- title: slides\[2\]\.title at \[\d+, \d+\], size \[\d+, \d+\]", said)
    assert "- left[0]: slides[2].left[0] (Text) at" in said
    assert "- right[0]: slides[2].right[0] (Figure) at" in said
    assert "- encoder: slides[2].right[0].figure.nodes[0] (block) at" in said
    assert "- shapes[0] pointer: slides[1].shapes[0] (arrow) at [" in said
    assert "- body[0]: slides[1].body[0] (List) at" in said
    assert _images(blocks) == [(960, 540), (960, 540)]


def test_a_shared_figures_parts_are_named_where_the_deck_keeps_it(deck) -> None:
    _, tools = deck
    said = _texts(tools.call("look", {"file": "talk.yaml", "pages": [5], "annotate": True})[0])
    assert "- x: figures.pipe.nodes[0] (block) at" in said


def test_a_slide_is_seen_at_a_build_step(deck) -> None:
    workspace, tools = deck
    blocks, failed = tools.call("look", {"file": "talk.yaml", "pages": [2], "step": 1})
    assert not failed and "Page 2 (Why another figure tool?), build step 1 of 3:" in _texts(blocks)
    blocks, _ = tools.call("look", {"file": "talk.yaml", "pages": [2]})
    assert "all 3 build steps shown" in _texts(blocks)
    page = workspace.drawing_of("talk.yaml").pages[1]
    first, last = DeckKind().at_step(page, 1), DeckKind().at_step(page, 3)
    assert 'id="slide2.body.0.0"' not in first and 'id="slide2.body.0.1"' not in first
    assert 'id="slide2.body.0.0"' in DeckKind().at_step(page, 2) and 'id="slide2.body.0.1"' in last


def test_a_sheet_shows_more_slides_than_a_look_in_one_picture(deck) -> None:
    _, tools = deck
    blocks, failed = tools.call("look", {"file": "talk.yaml", "sheet": True})
    assert not failed
    assert "A sheet of talk.yaml's pages 1-5, each numbered above its top left" in _texts(blocks)
    ((width, height),) = _images(blocks)
    assert width <= agent_look.SHEET_EDGE and width * height < 2 * 960 * 540


# -- what an edit did --


def test_deleting_a_slide_is_warned_of_by_its_title_and_what_it_held(deck) -> None:
    _, tools = deck
    said = _edit(tools, _slide_text(tools, 3), "")
    assert "What changed: deleted slide 3." in said
    assert "Warning -- this deleted: slide 3 “The model”, with 2 objects. If that is not" in said
    assert "Next: look at slide 3 once (look, pages: [3])." in said


def test_moving_a_slide_deletes_nothing(deck) -> None:
    _, tools = deck
    two = _slide_text(tools, 2)
    four = _slide_text(tools, 4)
    said = _edit(tools, two, "")
    said = _edit(tools, four, four + two)
    assert "Warning" not in said and "added slide 4" in said


def test_an_object_deleted_or_taken_to_another_slide(deck) -> None:
    _, tools = deck
    said = _edit(tools, "  - text: TODO a picture here\n", "")
    assert "Warning -- this deleted: the text on slide 2 (body)." in said
    # Moved to another slide, nothing is deleted.
    said = _edit(tools, "  - table:", "  - text: TODO a picture here\n  - table:")
    assert "Warning" not in said
    said = _edit(tools, "  - kind: ring\n", "  - kind: ring\n    hide: true\n")
    assert "Warning" not in said


def test_shapes_figure_parts_and_shared_figures_deleted_are_named(deck) -> None:
    _, tools = deck
    three = _slide_text(tools, 3)
    said = _edit(tools, three, three.replace("      - id: decoder\n        label: Decoder\n", "").replace(
        "      edges:\n      - from: encoder\n        to: decoder\n", ""))
    assert "the part decoder of the figure on slide 3" in said
    two = _slide_text(tools, 2)
    ring = two[two.index("  - kind: ring"):]
    said = _edit(tools, ring, "")
    assert "Warning -- this deleted: 1 shape of slide 2." in said
    said = _edit(tools, _slide_text(tools, 5), "")
    assert "the shared figure pipe" not in said
    whole = tools.call("read_document", {"file": "talk.yaml"})[0][0]["text"]
    said = _edit(tools, whole[whole.index("figures:"):], "")
    assert "the shared figure pipe" in said


# -- guides --


def test_the_deck_brief_is_short_and_made_from_the_live_tools_and_keys(deck) -> None:
    _, tools = deck
    opened, failed = tools.call("open_document", {"file": "talk.yaml"})
    assert not failed
    brief = opened[0]["text"]
    assert brief == DeckKind().brief() and brief.startswith("A flexo-talk deck")
    lines = brief.splitlines()
    assert len(lines) <= 95 and max(len(line) for line in lines) <= 100
    flat = " ".join(brief.split())
    assert f"Layouts: {', '.join(SLIDE_KEYS)}." in flat and f"Objects: {', '.join(BLOCKS)}." in flat
    for tool in ("outline", "read_document", "edit_document", "write_document", "look", "guide", "status"):
        assert re.search(rf"\b{tool}\b", brief)
    for word in ("slides: [n, ...]", "sheet: true", "annotate: true", "step: n", "Flexo bug", "one question"):
        assert word in brief
    for topic in DeckKind().topics():
        assert f"  {topic}: " in brief


def test_the_deck_guide_is_cut_into_topics_and_nothing_of_it_is_lost() -> None:
    kind = DeckKind()
    topics = kind.topics()
    words = sorted(re.sub(r"\s", "", "".join(topic.text for topic in topics.values())))
    assert words == sorted(re.sub(r"\s", "", kind.guide()))
    # All but the Python API's line has a topic of its own.
    assert topics[agent_guides.MORE].text.startswith("``read_deck`` makes a ``Deck``")
    assert "Layouts and their keys:" in topics["layouts"].text and "set in rows" in topics["layouts"].text
    assert topics["insets"].text.startswith("A zoom inset is a shape too")
    assert re.match(r"A\s+picture\s+\(``image``\)\s+may be cropped", topics["pictures"].text)
    assert "The kinds: lines from one point to another" in topics["shapes"].text
    assert topics["people"].text.startswith("people: portraits")


def test_a_topic_is_given_with_its_examples(deck) -> None:
    _, tools = deck
    said, failed = tools.call("guide", {"topic": "insets"})
    assert not failed
    assert said[0]["text"].startswith("Deck: insets -- Part of a picture, figure or plot shown magnified.")
    assert "# part of a picture, magnified\n- title: A closer look" in said[0]["text"]


def test_every_deck_example_draws_without_a_warning_in_one_deck(tmp_path: Path) -> None:
    slides, figures, alone = [], {}, []
    for snippets in SNIPPETS.values():
        for snippet in snippets:
            for name, content in snippet.files.items():
                (tmp_path / name).parent.mkdir(parents=True, exist_ok=True)
                (tmp_path / name).write_bytes(_png() if content == b"png" else content)
            data = yaml.safe_load(snippet.yaml)
            if isinstance(data, list):
                slides += data
            elif "deck" in data:
                alone.append(data)
            else:
                slides += data["slides"]
                figures |= data.get("figures") or {}
    reference = {"schema_version": 1, "deck": {"id": "reference"}, "slides": slides, "figures": figures}
    names = []
    for index, document in enumerate((reference, *alone)):
        names.append(f"reference{index}.yaml")
        (tmp_path / names[-1]).write_text(yaml.safe_dump(document, sort_keys=False), encoding="utf-8")
    workspace = Workspace(tmp_path)
    try:
        for name, document in zip(names, (reference, *alone), strict=True):
            drawing = workspace.drawing_of(name)
            assert len(drawing.pages) == len(document["slides"])
            assert [(m.page, m.text) for m in drawing.messages if m.severity in ("error", "warning")] == []
    finally:
        workspace.close()
