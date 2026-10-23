"""A figure found laid out on disk -- a deck just opened -- is laid out ahead once its slide is in
focus and the studio is quiet (flexo_talk.warming): the first words typed over it that wrap find
it compiled. Nothing of it is seen until then, and the slide is drawn as ever."""

from __future__ import annotations

import contextlib
import copy
from pathlib import Path

from flexo import draft

from flexo_talk import compose, warming
from flexo_talk.studio import DeckKind


def _deck(name: str) -> dict:
    nodes = [{"id": "a", "label": "Read"}, {"id": "b", "label": "Write it down"}, {"id": "c", "label": "Check"}]
    figure = {"figure": {"id": "steps"}, "nodes": nodes, "edges": [{"from": "a", "to": "b"}, {"from": "b", "to": "c"}]}
    slides = [{"title": "A talk", "layout": "title"},
              {"title": "Typed over a figure",
               "body": [{"bullets": ["A point", "Another"]}, {"figure": figure, "turn": False}]}]
    return {"schema_version": 1, "deck": {"id": name}, "slides": slides}


def _drawn(kind: DeckKind, document: dict, folder: Path, focus: int = 1) -> list[str]:
    drawing = kind.draw(document, folder, {"focus": focus})
    while drawing.unfinished:
        drawing = kind.draw(document, folder, {"focus": focus})
    return [page.svg for page in drawing.pages]


def test_a_figure_found_on_disk_is_laid_out_ahead_of_words_typed_over_it(tmp_path: Path, monkeypatch) -> None:
    import flexo.boxfit as boxfit

    document = _deck("ahead")
    _drawn(DeckKind(), document, tmp_path)  # (laid out, and kept on disk)
    compose.written()
    # Opened again: what was compiled is in no memory, its layout on disk alone.
    compose._FITS.clear()
    compose._COMPILED.compiled.clear()
    compose._COMPILED.measured.clear()
    compose._WISHES.clear()
    kind = DeckKind()
    compiled: list[object] = []
    real = boxfit.compile_figure

    def counted(*args, **kwargs):
        compiled.append(args)
        return real(*args, **kwargs)

    monkeypatch.setattr(boxfit, "compile_figure", counted)
    _drawn(kind, document, tmp_path)
    assert compiled == [] and kind._focused == "slide2"
    remembered = list(draft._REMEMBERED.items())
    warming._lay_out(kind, "slide2")
    assert len(compiled) == 1
    assert list(draft._REMEMBERED.items()) == remembered  # (nothing of it seen yet)
    assert compose.wishes("slide2") == []
    typed = copy.deepcopy(document)
    typed["slides"][1]["body"][0]["bullets"][0] += " that goes on and on, at length, past the end of its line, on"
    after = _drawn(kind, typed, tmp_path)
    assert len(compiled) == 1
    with monkeypatch.context() as patch:
        patch.setattr(compose, "_kept_compiled", lambda spec: contextlib.nullcontext())
        assert _drawn(DeckKind(), copy.deepcopy(typed), tmp_path) == after


def test_a_figure_laid_out_ahead_gives_way_to_a_drawing(tmp_path: Path, monkeypatch) -> None:
    import flexo.boxfit as boxfit

    document = _deck("given-way")
    _drawn(DeckKind(), document, tmp_path)
    compose.written()
    compose._FITS.clear()
    compose._WISHES.clear()
    kind = DeckKind()
    _drawn(kind, document, tmp_path)
    assert compose.wishes("slide2")
    compiled: list[object] = []
    monkeypatch.setattr(boxfit, "compile_figure", lambda *args, **kwargs: compiled.append(args))
    kind._drawing += 1  # (a drawing under way)
    try:
        warming._lay_out(kind, "slide2")
    finally:
        kind._drawing -= 1
    assert compiled == []
    assert compose.wishes("slide2")  # (wished for still)


def test_a_figure_edited_on_its_slide_has_its_words_read_ahead_of_the_next_edit(tmp_path: Path) -> None:
    from flexo.studio.figure_edit import _READ_AHEAD, inline_words, read_ahead

    document = _deck("edited")
    kind = DeckKind()
    at = {"slide": 1, "region": "body", "index": 1}
    edit = {"do": "update", "targets": [{"type": "node", "id": "a"}], "values": {"label": "Read again"}}
    answer = kind.act(document, {"do": "figure", "at": at, "edit": edit}, tmp_path)
    figure = answer["document"]["slides"][1]["body"][1]["figure"]
    assert [inline_words(figure)] == warming._WORDS
    read_ahead(warming._WORDS.pop())
    assert inline_words(figure) in _READ_AHEAD
    again = {"do": "update", "targets": [{"type": "node", "id": "b"}], "values": {"label": "Write"}}
    kind.act(answer["document"], {"do": "figure", "at": at, "edit": again}, tmp_path)
    assert inline_words(figure) not in _READ_AHEAD  # (taken by the edit)
