"""A deck written whole by something that read it before the owner's last save -- an agent
writing back what it read with its change, a script -- is taken in as a change from what it
read: the owner's saved edits stay, the writer's change is taken in, and the activity says
what the writer changed (flexo.studio.workspace ``Doc._made_from``)."""

from __future__ import annotations

import copy
import os
import time
from pathlib import Path

import pytest
from flexo.studio.workspace import Workspace

from flexo_talk.document import save_document

PERSON = {"id": "page-a", "name": "Ada", "kind": "person"}
AGENT = {"id": "mcp:claude-code", "name": "Claude Code", "kind": "agent"}


@pytest.fixture(autouse=True)
def _apart(tmp_path_factory: pytest.TempPathFactory, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("XDG_RUNTIME_DIR", str(tmp_path_factory.mktemp("run")))
    monkeypatch.setenv("FLEXO_ACTS", "0")


@pytest.fixture
def workspace(tmp_path: Path):
    slides = [{"layout": "title", "title": "GBI symposium 2026", "subtitle": "Kiarash Jamali"}]
    for number in range(2, 13):
        points = [f"Point {number}.{n}" for n in (1, 2, 3)]
        slides.append({"title": f"Slide {number}", "body": [{"bullets": points}]})
    deck = {"schema_version": 1, "deck": {"id": "talk", "theme": "paper"}, "slides": slides}
    save_document(deck, tmp_path / "talk.yaml")
    opened = Workspace(tmp_path)
    opened._stop.set()  # (no clock: each test takes the file in itself)
    try:
        yield opened
    finally:
        opened.close()


def _file(workspace: Workspace) -> Path:
    return workspace.root / "talk.yaml"


def _written(workspace: Workspace, text: str) -> None:
    """The deck's file written by something else, a moment later than the studio last saw it."""

    _file(workspace).write_text(text, encoding="utf-8")
    later = time.time_ns() + 2_000_000_000
    os.utime(_file(workspace), ns=(later, later))


def _saved(workspace: Workspace, change) -> None:
    doc = workspace.open("talk.yaml")
    edited = copy.deepcopy(doc.document)
    change(edited)
    doc.update(edited, doc.version, PERSON, "page-a")
    assert doc.write()


def _retitled(deck: dict) -> None:
    deck["slides"][1]["title"] = "Why it matters"


def test_a_deck_written_back_whole_from_before_the_last_save_keeps_that_save(
    workspace: Workspace,
) -> None:
    doc = workspace.open("talk.yaml")
    stale = _file(workspace).read_text(encoding="utf-8")  # what the agent read
    _saved(workspace, _retitled)  # the owner's edit, saved
    _written(workspace, stale.replace("Point 5.2", "Point 5.2, sharpened"))
    workspace.reread(doc)
    slides = doc.document["slides"]
    assert slides[1]["title"] == "Why it matters"
    assert slides[4]["body"][0]["bullets"][1] == "Point 5.2, sharpened"
    # Said as what the agent changed, on its slide: not as the owner's title taken back.
    said = [entry for entry in workspace.activity if entry["who"]["name"] == "Another app"]
    assert said and all(entry["where"]["page"] == 5 for entry in said)
    workspace.flush()
    assert "Why it matters" in _file(workspace).read_text(encoding="utf-8")
    assert "Point 5.2, sharpened" in _file(workspace).read_text(encoding="utf-8")


def test_a_slide_moved_since_a_writer_read_the_deck_stays_moved(workspace: Workspace) -> None:
    doc = workspace.open("talk.yaml")
    stale = _file(workspace).read_text(encoding="utf-8")

    def moved(deck: dict) -> None:
        deck["slides"].insert(8, deck["slides"].pop(2))

    _saved(workspace, moved)
    _written(workspace, stale.replace("Point 11.1", "Point 11.1, sharpened"))
    workspace.reread(doc)
    titles = [slide["title"] for slide in doc.document["slides"]]
    assert titles[2:9] == [f"Slide {n}" for n in (4, 5, 6, 7, 8, 9, 3)]
    assert doc.document["slides"][10]["body"][0]["bullets"][0] == "Point 11.1, sharpened"


def test_an_agent_writing_from_the_latest_is_taken_in_and_credited(workspace: Workspace) -> None:
    doc = workspace.open("talk.yaml")
    _saved(workspace, _retitled)
    workspace.set_presence(AGENT, "talk.yaml", None, "Tightening slide 2")
    latest = _file(workspace).read_text(encoding="utf-8")
    _written(workspace, latest.replace("Why it matters", "Why this matters"))
    workspace.reread(doc)
    assert doc.document["slides"][1]["title"] == "Why this matters"
    assert doc.saved == doc.version
    assert workspace.activity[-1]["who"] == AGENT
    assert workspace.activity[-1]["where"]["page"] == 2


def test_a_deck_put_back_as_it_was_is_taken_in(workspace: Workspace) -> None:
    doc = workspace.open("talk.yaml")
    first = _file(workspace).read_text(encoding="utf-8")
    _saved(workspace, _retitled)
    _written(workspace, first)  # git checkout talk.yaml
    workspace.reread(doc)
    assert doc.document["slides"][1]["title"] == "Slide 2"
