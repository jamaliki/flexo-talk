"""A deck opened just after an update of the app: every slide shows at once, its figures as the
version before laid them out, then -- as the page settles, the slide in view first -- as this
version lays them out, the drawing sent only should it differ. An export, a fresh drawing (to
present, to copy out, for an agent) never draws what the version before kept."""

from __future__ import annotations

import copy
from dataclasses import replace
from pathlib import Path

import pytest
import yaml
from flexo import kept_versions

import flexo_talk.compose as compose
import flexo_talk.studio as studio
from flexo_talk.studio import DeckKind

OLD, NEW = "0ld0ld0ld0ld0ld0", "11e911e911e911e9"


def _deck() -> dict:
    figure = {
        "figure": {"id": "steps"},
        "nodes": [{"id": "a", "label": "Read"}, {"id": "b", "label": "Write"}],
        "edges": [{"from": "a", "to": "b"}],
    }
    other = {
        "figure": {"id": "loop"},
        "nodes": [{"id": "x", "label": "Ask"}, {"id": "y", "label": "Answer"}],
        "edges": [{"from": "x", "to": "y"}, {"from": "y", "to": "x"}],
    }
    slides = [{"layout": "title", "title": "A talk", "subtitle": "After an update"}]
    for number in range(1, 10):
        slides.append({"title": f"Slide {number}", "body": [{"bullets": [f"Point {number}"]}]})
    slides[2]["body"].append({"figure": figure})
    slides[8]["body"].append({"figure": other})
    return {"schema_version": 1, "deck": {"id": "talk"}, "slides": slides}


FIGURES = (2, 8)
"""The slides with figures on them."""


def _launched(monkeypatch: pytest.MonkeyPatch, version: str) -> DeckKind:
    """The studio started afresh on the version ``version`` of the code: nothing it held in
    memory, what it kept on disk there."""

    from flexo import draft

    monkeypatch.setattr(kept_versions, "_CODE", [version])
    for memo in (
        compose._FITS,
        compose._LAYOUTS,
        compose._SCALES,
        compose._SHOWN,
        compose._PLACES,
        compose._ASKED,
        compose._TURNS,
        compose._FINDING,
        compose._ASIDE,
        compose._PROBED,
        compose._FRAMED,
        compose._PLOTTED,
        compose._FRAME_LAYOUTS,
        draft._REMEMBERED,
    ):
        memo.clear()
    for seen in (compose._SETTLED, compose._EARLIER_SEEN, compose._FITS_USED):
        seen.clear()
    return DeckKind()


def _laid_out_otherwise(monkeypatch: pytest.MonkeyPatch) -> list:
    """This version lays its figures out otherwise than the version before (its first word
    reads otherwise): each layout it makes, counted."""

    laid: list = []
    real = compose._fit_in_box

    def otherwise(*args, **kwargs):
        laid.append(args[0].id)
        fit = real(*args, **kwargs)
        text = fit.compilation.document.text.replace(">Read<", ">Reed<").replace(">Ask<", ">Asked<")
        return replace(fit, compilation=replace(fit.compilation, document=replace(fit.compilation.document, text=text)))

    monkeypatch.setattr(compose, "_fit_in_box", otherwise)
    return laid


def _drawn(kind: DeckKind, document: dict, folder: Path, focus: int = 0, **hints):
    drawing = kind.draw(copy.deepcopy(document), folder, {"focus": focus, **hints})
    while drawing.unfinished:
        drawing = kind.draw(copy.deepcopy(document), folder, {"focus": focus, **hints})
    return drawing


def _settled(kind: DeckKind, document: dict, folder: Path, focus: int = 0):
    """The deck settled as the page settles it, a drawing at a time (each giving way to edits)."""

    for _ in range(50):
        drawing = kind.draw(copy.deepcopy(document), folder, {"focus": focus, "settle": True, "yields": True})
        if not drawing.unfinished and not drawing.info["unsettled"]:
            return drawing
    raise AssertionError("never settled")


def _revalidating(drawing) -> list[int]:
    return [index for index, page in enumerate(drawing.pages) if page.extra.get("revalidating")]


def _cold(monkeypatch: pytest.MonkeyPatch, tmp_path: Path, document: dict, folder: Path):
    """The deck as this version draws it opened on a computer that never drew it before."""

    monkeypatch.setenv("FLEXO_TALK_CACHE", str(tmp_path / "cold-fits"))
    monkeypatch.setenv("FLEXO_STRUCTURE_CACHE", str(tmp_path / "cold-structures"))
    return _drawn(_launched(monkeypatch, NEW), document, folder)


def test_after_an_update_every_slide_shows_at_once_then_as_this_version_draws_it(tmp_path: Path, monkeypatch) -> None:
    document = _deck()
    before = _drawn(_launched(monkeypatch, OLD), document, tmp_path)
    assert ">Read<" in before.pages[2].svg

    kind = _launched(monkeypatch, NEW)
    laid = _laid_out_otherwise(monkeypatch)
    first = _drawn(kind, document, tmp_path, focus=8)
    # Shown at once as the version before laid each figure out: none laid out again yet.
    assert laid == []
    assert [page.svg for page in first.pages] == [page.svg for page in before.pages]
    assert _revalidating(first) == list(FIGURES)
    assert first.info["unsettled"]

    # Settled, a drawing at a time: the slide in view first, then the others.
    monkeypatch.setattr(studio, "REVALIDATING", 0.0)
    one = kind.draw(copy.deepcopy(document), tmp_path, {"focus": 8, "settle": True, "yields": True})
    assert _revalidating(one) == [2]
    assert ">Asked<" in one.pages[8].svg and ">Read<" in one.pages[2].svg
    settled = _settled(kind, document, tmp_path, focus=8)
    assert _revalidating(settled) == []
    assert ">Reed<" in settled.pages[2].svg

    # Drawn again, every slide is what this version draws of a deck it never saw, byte for byte.
    cold = _cold(monkeypatch, tmp_path, document, tmp_path)
    assert [page.svg for page in settled.pages] == [page.svg for page in cold.pages]
    assert [message.text for message in settled.messages] == [message.text for message in cold.messages]


def test_a_slide_this_version_draws_the_same_is_the_same_drawing(tmp_path: Path, monkeypatch) -> None:
    """Checked and found the same (as nearly always), a slide's drawing is the very one the page
    has: nothing is sent again, nothing moves."""

    document = _deck()
    before = _drawn(_launched(monkeypatch, OLD), document, tmp_path)
    kind = _launched(monkeypatch, NEW)
    first = _drawn(kind, document, tmp_path)
    settled = _settled(kind, document, tmp_path)
    assert _revalidating(first) == list(FIGURES) and _revalidating(settled) == []
    assert (
        [page.svg for page in settled.pages]
        == [page.svg for page in before.pages]
        == [page.svg for page in first.pages]
    )


def test_an_export_after_an_update_never_draws_what_the_version_before_kept(tmp_path: Path, monkeypatch) -> None:
    document = _deck()
    old = tmp_path / "old"
    _drawn(kind := _launched(monkeypatch, OLD), document, tmp_path)
    kind.export(copy.deepcopy(document), tmp_path, "talk", ["svg"], into=old)

    kind = _launched(monkeypatch, NEW)
    _laid_out_otherwise(monkeypatch)
    shown = _drawn(kind, document, tmp_path)
    assert _revalidating(shown) == list(FIGURES)
    exported = tmp_path / "exported"
    kind.export(copy.deepcopy(document), tmp_path, "talk", ["svg"], into=exported)

    monkeypatch.setenv("FLEXO_TALK_CACHE", str(tmp_path / "cold-fits"))
    cold = tmp_path / "cold"
    _launched(monkeypatch, NEW).export(copy.deepcopy(document), tmp_path, "talk", ["svg"], into=cold)

    def files(folder: Path) -> dict[str, bytes]:
        return {item.name: item.read_bytes() for item in sorted(folder.rglob("*.svg"))}

    assert files(exported) == files(cold)
    assert files(exported) != files(old)
    # (And the page goes on showing what it showed, still to be checked.)
    assert _revalidating(_drawn(kind, document, tmp_path)) == list(FIGURES)


def test_slides_asked_for_fresh_are_drawn_by_this_version_at_once(tmp_path: Path, monkeypatch) -> None:
    """To present them, or to copy one out: no slide is the version before's, those not drawn
    in time still to come (pending)."""

    document = _deck()
    _drawn(_launched(monkeypatch, OLD), document, tmp_path)
    kind = _launched(monkeypatch, NEW)
    _laid_out_otherwise(monkeypatch)
    _drawn(kind, document, tmp_path)
    with monkeypatch.context() as quick:
        quick.setattr(studio, "BUDGET", 0.0)
        fresh = kind.draw(copy.deepcopy(document), tmp_path, {"focus": 0, "fresh": True})
    # (One not drawn in time is still to come, and still said to be checked: the page waits.)
    assert _revalidating(fresh) == [8]
    assert not fresh.pages[2].pending and fresh.pages[8].pending
    assert ">Reed<" in fresh.pages[2].svg
    fresh = _drawn(kind, document, tmp_path, fresh=True)
    assert _revalidating(fresh) == [] and ">Asked<" in fresh.pages[8].svg


def test_the_page_is_told_what_is_being_checked_and_an_agent_sees_this_versions_slides(
    tmp_path: Path, monkeypatch
) -> None:
    from flexo.studio.workspace import Workspace

    document = _deck()
    (tmp_path / "talk.yaml").write_text(yaml.safe_dump(document, sort_keys=False))

    def page_drawing(workspace: Workspace) -> dict:
        # (As the page asks: the slide in focus, then the others, till none is to come.)
        doc = workspace.open("talk.yaml")
        for version in range(1, 30):
            answer = workspace.draw("talk.yaml", copy.deepcopy(doc.document), version, {}, {"focus": 0})
            if not answer.get("unfinished"):
                return answer
        raise AssertionError("never drawn")

    _launched(monkeypatch, OLD)
    workspace = Workspace(tmp_path)
    try:
        page_drawing(workspace)
    finally:
        workspace.close()
    _launched(monkeypatch, NEW)
    _laid_out_otherwise(monkeypatch)
    workspace = Workspace(tmp_path)
    try:
        answer = page_drawing(workspace)
        assert [index for index, page in enumerate(answer["pages"]) if page.get("revalidating")] == list(FIGURES)
        assert ">Read<" in answer["pages"][2]["svg"]
        seen = workspace.drawing_of("talk.yaml")
        assert _revalidating(seen) == [] and ">Reed<" in seen.pages[2].svg
    finally:
        workspace.close()


def test_what_the_version_before_laid_out_is_found_only_for_the_page(tmp_path: Path, monkeypatch) -> None:
    """Kept by what it was laid out from, a figure is found again after an update -- but only
    where the page may be shown it (flexo.kept_versions.earlier), never kept in memory as this
    version's, and replaced in its file once this version lays it out."""

    _launched(monkeypatch, OLD)
    key = ("a figure", 1.0)
    compose._store_fit(key, {"svg": "<svg>old</svg>"})
    path = compose._cache_path(key)
    _launched(monkeypatch, NEW)
    assert compose._cached_fit(key) is None
    assert compose._kept_fit(key, earlier=True) == (None, False)
    with kept_versions.earlier():
        assert compose._kept_fit(key, earlier=True) == ({"svg": "<svg>old</svg>"}, True)
        assert compose._kept_fit(key) == (None, False)
    assert str(path) not in compose._FITS
    compose._store_fit(key, {"svg": "<svg>new</svg>"})
    assert compose._cached_fit(key) == {"svg": "<svg>new</svg>"}
    assert path.read_bytes().startswith(b"flexo-kept " + NEW.encode())
    assert list(path.parent.glob("*.json")) == [path]
