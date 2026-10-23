"""A figure with molecules placed on a slide reads its molecules' shapes once, however often it is
drawn again -- edited, laid out for another place -- and the slide writes them out once however
often it is written (flexo.sealed): drawn the same, to the letter, as read whole and written
element by element."""

from __future__ import annotations

import contextlib
import copy
import xml.etree.ElementTree as ET
from pathlib import Path

import flexo
import pytest

from flexo_talk import compose
from flexo_talk.studio import DeckKind

STRUCTURE = Path(flexo.__file__).resolve().parents[2] / "tests" / "unit" / "data" / "1a7g.cif"


def _deck(folder: Path, *, molecule: bool = False) -> dict:
    nodes = [{"id": "a", "label": "Read"}, {"id": "b", "label": "Write it down"}, {"id": "c", "label": "Check"}]
    if molecule:
        (folder / "assets").mkdir(exist_ok=True)
        (folder / "assets" / "1a7g.cif").write_bytes(STRUCTURE.read_bytes())
        nodes.append({"id": "model", "kind": "structure",
                      "properties": {"source": "assets/1a7g.cif", "look": "flat", "width": 120, "height": 90}})
    figure = {"figure": {"id": "steps"}, "nodes": nodes,
              "edges": [{"from": "a", "to": "b"}, {"from": "b", "to": "c"}]}
    slides = [
        {"title": "A talk", "layout": "title"},
        # (Kept the way it is written: a figure turned to fit is drawn as a draft while it is
        # changed, from the drawing before -- never kept.)
        {"title": "Typed over a figure",
         "body": [{"bullets": ["A point", "Another"]}, {"figure": figure, "turn": False}]},
    ]
    return {"schema_version": 1, "deck": {"id": "sooner"}, "slides": slides}


def _drawn(kind: DeckKind, document: dict, folder: Path, focus: int = 1) -> list[str]:
    drawing = kind.draw(document, folder, {"focus": focus})
    while drawing.unfinished:
        drawing = kind.draw(document, folder, {"focus": focus})
    return [page.svg for page in drawing.pages]


@contextlib.contextmanager
def _nothing_kept(monkeypatch: pytest.MonkeyPatch):
    """Drawn as before anything was kept: every figure compiled, every drawing read whole and
    written element by element."""

    with monkeypatch.context() as patch:
        patch.setattr(compose, "_kept_compiled", lambda spec: contextlib.nullcontext())
        patch.setattr(compose, "_with_molecules", lambda words, prefix: None)
        patch.setattr("flexo.sealed.sealed_in", lambda root: [])
        yield


def test_a_figure_with_a_molecule_is_drawn_on_its_slide_as_read_whole(tmp_path: Path, monkeypatch) -> None:
    """A slide with a molecule in its figure, the molecule's shapes read once and written out
    once, is the slide drawn reading the figure whole and writing it element by element --
    edited, and typed over."""

    if not STRUCTURE.is_file():
        pytest.skip("no structure to draw")
    pytest.importorskip("molsketch")
    kind = DeckKind()
    document = _deck(tmp_path, molecule=True)
    before = _drawn(kind, document, tmp_path)
    with _nothing_kept(monkeypatch):
        assert _drawn(DeckKind(), copy.deepcopy(document), tmp_path) == before
    edited = copy.deepcopy(document)
    edited["slides"][1]["body"][1]["figure"]["nodes"][0]["label"] = "Read it again"
    edited["slides"][1]["body"][0]["bullets"][1] += ", typed over at length so that it needs a second line"
    after = _drawn(kind, edited, tmp_path)
    assert after != before
    with _nothing_kept(monkeypatch):
        assert _drawn(DeckKind(), copy.deepcopy(edited), tmp_path) == after


def _prefixed_whole(svg: str, identifier: str) -> tuple[str, dict[str, str]]:
    """A figure prefixed for its place as it was: read whole, every element gone through."""

    import re

    source = ET.fromstring(re.sub(r"<!DOCTYPE[^>]*>", "", svg, count=1))
    for item in source.iter():
        compose._prefix_ids(item, f"{identifier}.")
    return ET.tostring(source, encoding="unicode"), {}


def test_a_figure_placed_on_a_slide_reads_its_molecules_once(monkeypatch) -> None:
    if not STRUCTURE.is_file():
        pytest.skip("no structure to draw")
    pytest.importorskip("molsketch")
    from flexo.compiler import compile_figure
    from flexo.drawn_spans import spans

    def figure(words: str) -> str:
        with flexo.Figure("placed") as made:
            row = made.root.row("row", gap=24)
            row.block("before", label=words)
            row.structure("model", STRUCTURE, look="flat", width=200, height=120)
        return compile_figure(made.spec).document.text

    read: list[str] = []
    real = ET.fromstring
    monkeypatch.setattr(ET, "fromstring", lambda text, *args: read.append(text) or real(text, *args))
    for words in ("First", "Second"):
        svg = figure(words)
        read.clear()
        placed, universal = compose._prefixed(svg, "slide2.body.1")
        made = list(read)
        assert ET.tostring(placed, encoding="unicode") == _prefixed_whole(svg, "slide2.body.1")[0]
        assert universal == {}
        # (Its words read without the molecule's shapes; the molecule's read the first time alone.)
        (shapes,) = [span for span in spans(svg) if span.inside < span.end]
        assert len(made[-1]) == len(svg) - (shapes.end - shapes.inside)
        if words == "First":
            assert len(made) == 2 and svg[shapes.inside:shapes.end] in made[0]
        else:
            assert len(made) == 1
