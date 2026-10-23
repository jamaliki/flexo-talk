"""Words typed over a figure on a slide, wrapping onto another line, leave it less room: it is
laid out again from what was compiled for it (flexo.boxfit.kept), not compiled again -- and
drawn as compiling it again draws it."""

from __future__ import annotations

import contextlib
import copy
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
    """Drawn as before anything was kept: every figure compiled."""

    with monkeypatch.context() as patch:
        patch.setattr(compose, "_kept_compiled", lambda spec: contextlib.nullcontext())
        yield


def test_words_typed_over_a_figure_draw_it_without_compiling_it_again(tmp_path: Path, monkeypatch) -> None:
    """A line of words added over a figure as they are typed leaves it less room: it is laid out
    again, in the layout it has, from what was compiled -- and drawn as compiling it again draws
    it."""

    import flexo.boxfit as boxfit

    kind = DeckKind()
    document = _deck(tmp_path)
    _drawn(kind, document, tmp_path)
    compiled: list[object] = []
    real = boxfit.compile_figure

    def counted(*args, **kwargs):
        compiled.append(args)
        return real(*args, **kwargs)

    monkeypatch.setattr(boxfit, "compile_figure", counted)
    laid: list[object] = []
    fitted = compose._fit_in_box
    monkeypatch.setattr(compose, "_fit_in_box", lambda *args, **options: laid.append(args) or fitted(*args, **options))
    typed = copy.deepcopy(document)
    drawn = []
    for words in (
        " that goes on and on, at length, past the end of its line, onto another line",
        " and on again, at more length still, past the end of the second line, onto a third",
        " and on to a fourth line of words, which takes yet more of the room over the figure",
    ):
        typed["slides"][1]["body"][0]["bullets"][0] += words
        drawn.append((copy.deepcopy(typed), _drawn(kind, typed, tmp_path)))
    # (Laid out again for each room it is given: compiled for the first, at most, and found
    # compiled for the rest.)
    assert len({args[2] for args in laid}) >= 2
    assert len(compiled) <= 1
    for document_then, pages in drawn:
        with _nothing_kept(monkeypatch):
            assert _drawn(DeckKind(), document_then, tmp_path) == pages
