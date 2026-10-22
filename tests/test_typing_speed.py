"""Typing on a slide reads and draws that slide alone, and asks the disk about the deck's files
once: what the studio does at each keystroke."""

from __future__ import annotations

import copy
import os
from pathlib import Path

import pytest

import flexo_talk.compose as compose
import flexo_talk.document as document_module
import flexo_talk.studio as studio
from flexo_talk.studio import DeckKind

PNG = bytes.fromhex(
    "89504e470d0a1a0a0000000d4948445200000001000000010806000000"
    "1f15c4890000000d49444154789c6360000002000154a24f5d0000000049454e44ae426082"
)


def _deck(folder: Path) -> dict:
    (folder / "assets").mkdir(exist_ok=True)
    (folder / "assets" / "dot.png").write_bytes(PNG)
    figure = {"figure": {"id": "steps"}, "nodes": [{"id": "a", "label": "Read"}, {"id": "b", "label": "Write"}],
              "edges": [{"from": "a", "to": "b"}]}
    slides = [{"layout": "title", "title": "A talk", "subtitle": "Typed in"}]
    for number in range(1, 12):
        slides.append({"title": f"Slide {number}", "body": [{"bullets": [f"Point {number}", "Another point"]}]})
    slides[4]["body"].append({"figure": figure})
    slides[7]["body"].append({"image": "assets/dot.png"})
    return {"schema_version": 1, "deck": {"id": "talk"}, "slides": slides}


def _drawn(kind: DeckKind, document: dict, folder: Path, focus: int = 0):
    drawing = kind.draw(document, folder, {"focus": focus})
    while drawing.unfinished:
        drawing = kind.draw(document, folder, {"focus": focus})
    return drawing


def _counting(monkeypatch: pytest.MonkeyPatch, owner: object, name: str) -> list:
    calls: list = []
    original = getattr(owner, name)

    def counted(*args, **kwargs):
        calls.append(args)
        return original(*args, **kwargs)

    monkeypatch.setattr(owner, name, counted)
    return calls


def test_a_word_typed_on_a_slide_reads_and_draws_that_slide_alone(tmp_path: Path, monkeypatch) -> None:
    kind = DeckKind()
    document = _deck(tmp_path)
    _drawn(kind, document, tmp_path)
    read = _counting(monkeypatch, document_module, "add_slide")
    drawn = _counting(monkeypatch, compose, "render_slide")
    typed = copy.deepcopy(document)
    typed["slides"][5]["body"][0]["bullets"][0] += " more"
    after = _drawn(kind, typed, tmp_path, focus=5)
    assert [args[3] for args in read] == ["slides[5]"]
    assert [args[1].id for args in drawn] == ["slide6"]
    # Every slide as a studio that never saw the deck before draws it.
    fresh = _drawn(DeckKind(), copy.deepcopy(typed), tmp_path, focus=5)
    assert [page.svg for page in after.pages] == [page.svg for page in fresh.pages]
    assert [message.text for message in after.messages] == [message.text for message in fresh.messages]


def test_a_drawing_with_nothing_changed_asks_the_disk_where_no_file_is(tmp_path: Path, monkeypatch) -> None:
    kind = DeckKind()
    document = _deck(tmp_path)
    _drawn(kind, document, tmp_path)
    resolved = _counting(monkeypatch, Path, "resolve")
    looked = _counting(monkeypatch, os, "stat")
    _drawn(kind, copy.deepcopy(document), tmp_path)
    # (The deck's own folder, once: no file a slide names.)
    assert {args[0] for args in resolved} <= {tmp_path}
    # The picture and the figure's folder are each asked once, not once for each slide.
    assert len({str(args[0]) for args in looked}) == len(looked)


def test_a_slide_taken_as_it_was_read_follows_its_files(tmp_path: Path) -> None:
    kind = DeckKind()
    document = _deck(tmp_path)
    before = _drawn(kind, document, tmp_path)
    picture = tmp_path / "assets" / "dot.png"
    picture.rename(tmp_path / "aside.png")
    gone = _drawn(kind, copy.deepcopy(document), tmp_path)
    said = [message.text for message in gone.messages if message.severity == "error"]
    assert any("dot.png" in text for text in said)
    assert gone.pages[7].svg != before.pages[7].svg
    (tmp_path / "aside.png").rename(picture)
    back = _drawn(kind, copy.deepcopy(document), tmp_path)
    assert not [message for message in back.messages if message.severity == "error"]
    assert back.pages[7].svg == before.pages[7].svg


def test_an_edit_to_a_slide_that_keeps_its_title_is_described_without_comparing_slides(monkeypatch) -> None:
    def never(*args):
        raise AssertionError("compared")

    monkeypatch.setattr(studio, "_likeness", never)
    shapes = [{"kind": "rectangle", "at": [10 * n, 10], "size": [5, 5]} for n in range(400)]
    before = {"slides": [{"title": "Shapes", "shapes": shapes}, {"title": "After"}]}
    after = copy.deepcopy(before)
    after["slides"][0]["shapes"][3]["at"] = [31, 12]
    notes = DeckKind().describe(before, after)
    assert [note["where"]["page"] for note in notes] == [1]
    moved = DeckKind().follow(before, after)
    assert moved({"page": 1, "label": "Slide 1"}) == {"page": 1, "label": "Slide 1"}
