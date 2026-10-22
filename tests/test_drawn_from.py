"""A figure laid out for a slide is kept by what it is drawn from, files and all: a picture, a
photograph, a PDF's page, a structure or a picture drawn over the figure edited is drawn anew --
by the next build, into any folder, and by the studio while the deck is open -- with the cache
of laid-out figures left on, and nothing laid out again while they are as they were."""

from __future__ import annotations

import io
import os
import re
from pathlib import Path

import pytest

from flexo_talk import compose
from flexo_talk.document import read_deck
from flexo_talk.studio import DeckKind

SVG_NS = "http://www.w3.org/2000/svg"


def _picture(view: str = "0 0 100 50") -> str:
    return (
        f'<svg xmlns="{SVG_NS}" viewBox="{view}" width="100" height="50">'
        '<path d="M5 45 C5 -10 95 -10 95 45 Z" fill="#d7f2d8" stroke="#246c2d" stroke-width="2"/>'
        "</svg>"
    )


def _edited(path: Path, text: str | bytes) -> None:
    """``path`` written anew, its time moved on: an edit, however soon after the last."""

    before = path.stat().st_mtime_ns if path.exists() else 0
    if isinstance(text, bytes):
        path.write_bytes(text)
    else:
        path.write_text(text, encoding="utf-8")
    later = max(path.stat().st_mtime_ns, before + 1_000_000_000)
    os.utime(path, ns=(later, later))


def _deck(folder: Path, part: str) -> Path:
    """A deck of one slide showing a figure file, ``figures/cell.yaml``, whose middle part is
    ``part`` (YAML), beside a few words."""

    (folder / "figures").mkdir(exist_ok=True)
    (folder / "figures" / "cell.yaml").write_text(
        "figure: {id: cell}\n"
        "nodes:\n"
        "  - {id: before, label: Before}\n"
        f"  - {part}\n"
        "  - {id: after, label: After}\n"
        "edges:\n"
        "  - {from: before, to: middle}\n"
        "  - {from: middle, to: after}\n",
        encoding="utf-8",
    )
    deck = folder / "talk.yaml"
    deck.write_text(
        "schema_version: 1\ndeck: {id: talk}\nslides:\n- title: A cell\n  body:\n  - figure: figures/cell.yaml\n",
        encoding="utf-8",
    )
    return deck


def _built(deck: Path, into: Path) -> str:
    """The deck's first slide, built into a folder of its own."""

    result = read_deck(deck).build(into, formats=("svg",))
    return result.svgs[0].read_text(encoding="utf-8")


@pytest.fixture
def counted(monkeypatch: pytest.MonkeyPatch) -> list[int]:
    """Each figure laid out afresh, counted."""

    import flexo

    calls: list[int] = []
    real = flexo.fit_in_box

    def counting(*args, **kwargs):
        calls.append(1)
        return real(*args, **kwargs)

    monkeypatch.setattr(flexo, "fit_in_box", counting)
    return calls


def test_a_picture_edited_between_builds_is_drawn_anew(tmp_path: Path, counted: list[int]) -> None:
    picture = tmp_path / "figures" / "art.svg"
    deck = _deck(tmp_path, "{id: middle, kind: image, height: 60, properties: {source: art.svg}}")
    picture.write_text(_picture(), encoding="utf-8")
    assert 'viewBox="0 0 100 50"' in _built(deck, tmp_path / "one")
    # Its viewBox changed, the same length of file: the next build, into a new folder, draws it.
    _edited(picture, _picture("0 0 100 60"))
    second = _built(deck, tmp_path / "two")
    assert 'viewBox="0 0 100 60"' in second and 'viewBox="0 0 100 50"' not in second
    # As it was, nothing is laid out again.
    laid = len(counted)
    assert 'viewBox="0 0 100 60"' in _built(deck, tmp_path / "three")
    assert len(counted) == laid


def test_a_photograph_replaced_between_builds_is_drawn_anew(tmp_path: Path) -> None:
    image = pytest.importorskip("PIL.Image")

    def photograph(width: int, height: int) -> bytes:
        out = io.BytesIO()
        image.new("RGB", (width, height), (200, 90, 40)).save(out, "PNG")
        return out.getvalue()

    def drawn(svg: str) -> float:
        found = re.search(r'<image [^>]*width="([\d.]+)" height="([\d.]+)"', svg)
        assert found is not None
        return float(found.group(1)) / float(found.group(2))

    photo = tmp_path / "figures" / "photo.png"
    deck = _deck(tmp_path, "{id: middle, kind: image, height: 60, properties: {source: photo.png}}")
    photo.write_bytes(photograph(80, 40))
    assert drawn(_built(deck, tmp_path / "one")) == pytest.approx(2.0, rel=0.01)
    _edited(photo, photograph(40, 80))
    assert drawn(_built(deck, tmp_path / "two")) == pytest.approx(0.5, rel=0.01)


def _chain(turned: bool) -> str:
    """A few residues of a chain, as a PDB file: along x, or along y."""

    lines = []
    for index, name in enumerate(("ALA", "GLY", "SER", "LEU", "VAL", "ALA", "GLY", "SER")):
        places = (("N", (0.0, 0.0)), ("CA", (1.2, 0.8)), ("C", (2.4, 0.0)), ("O", (2.4, -1.2)))
        for atom, (dx, dy) in places:
            along, aside = 3.6 * index + dx, dy
            x, y = (aside, along) if turned else (along, aside)
            lines.append(
                f"ATOM  {len(lines) + 1:5d}  {atom:<3} {name} A{index + 1:4d}    "
                f"{x:8.3f}{y:8.3f}{0.0:8.3f}  1.00 10.00           {atom[0]}  "
            )
    return "\n".join([*lines, "END", ""])


def test_a_structure_saved_again_between_builds_is_drawn_anew(tmp_path: Path) -> None:
    pytest.importorskip("molsketch")
    structure = tmp_path / "figures" / "chain.pdb"
    deck = _deck(tmp_path, "{id: middle, kind: structure, properties: {source: chain.pdb, look: flat}}")
    structure.write_text(_chain(turned=False), encoding="utf-8")
    first = _built(deck, tmp_path / "one")
    _edited(structure, _chain(turned=True))
    second = _built(deck, tmp_path / "two")
    # (The same file named, the drawing of it another: its molecule's paths are not those drawn first.)
    paths = re.compile(r'<path [^>]*d="([^"]+)"')
    assert set(paths.findall(first)) != set(paths.findall(second))
    assert _built(deck, tmp_path / "three") == second


def test_what_a_figure_is_drawn_from_is_what_is_in_its_files_read_once(tmp_path: Path, monkeypatch) -> None:
    """Each file by its name and what is in it -- read once, then asked of the disk while the disk
    says it is the same file, unchanged -- never by where it is or when it was saved."""

    from flexo import kept_versions
    from flexo.ir.semantic import FigureSpec, FreeShape, NodeSpec

    files = {name: tmp_path / name for name in ("art.svg", "page.pdf", "model.cif", "map.mrc", "ss.pdb", "over.png")}
    for file in files.values():
        file.write_bytes(file.name.encode() * 10)
    nodes = (
        NodeSpec("art", "image", properties=(("source", str(files["art.svg"])),)),
        NodeSpec("page", "image", properties=(("source", f"{files['page.pdf']}#2"),)),
        NodeSpec(
            "model",
            "structure",
            properties=(
                ("source", str(files["model.cif"])),
                ("density", str(files["map.mrc"])),
                ("ss_from", str(files["ss.pdb"])),
            ),
        ),
        NodeSpec("fetched", "structure", properties=(("source", "1BK0"), ("density", "auto"))),
        NodeSpec("chart", "plot", properties=(("source", str(tmp_path / "plots.py")),)),
    )
    over = FreeShape.of({"kind": "picture", "at": [0, 0], "size": [10, 10], "source": str(files["over.png"])})
    spec = FigureSpec("parts", nodes=nodes, shapes=(over,))
    read: list[str] = []
    real = open

    def opened(name, *args, **kwargs):
        if str(name).startswith(str(tmp_path)):
            read.append(Path(name).name)
        return real(name, *args, **kwargs)

    monkeypatch.setattr("builtins.open", opened)
    kept_versions._CONTENTS.clear()
    known = compose._drawn_from(spec)
    assert [entry[0] for entry in known] == [
        str(files["art.svg"]),
        f"{files['page.pdf']}#2",
        str(files["model.cif"]),
        str(files["map.mrc"]),
        str(files["ss.pdb"]),
        "1BK0",
        "auto",
        str(files["over.png"]),
    ]
    assert sorted(read) == sorted(files)
    # Asked again, asked of the disk: nothing read.
    read.clear()
    assert compose._drawn_from(spec) == known and read == []
    # A file by its own name and what is in it; a PDF's page by its file's; an ID by its name.
    assert ("1BK0", "1BK0") in known and ("auto", "auto") in known
    assert str(tmp_path) not in repr(known) and "page.pdf#2 " in repr(known)
    for file in files.values():
        # Saved again as it was: the same. Changed: another.
        _edited(file, file.read_bytes())
        assert compose._drawn_from(spec) == known, file.name
        _edited(file, b"y" * 11)
        assert compose._drawn_from(spec) != known, file.name
        known = compose._drawn_from(spec)


def test_a_deck_unpacked_afresh_elsewhere_finds_its_figures_laid_out(tmp_path: Path, monkeypatch) -> None:
    """A bundle opened again where it is unpacked afresh -- a copy of it, the deck opened on
    another computer -- has its files elsewhere, saved as they were unpacked: its figures are
    found as they were laid out, by what their files hold, and drawn byte for byte alike."""

    import shutil

    import flexo
    from flexo import bundle
    from flexo.studio.bundles import opened

    from flexo_talk.document import load_document

    monkeypatch.setenv("FLEXO_BUNDLES", str(tmp_path / "bundles"))
    folder = tmp_path / "made"
    folder.mkdir()
    deck = _deck(folder, "{id: middle, kind: image, height: 60, properties: {source: art.svg}}")
    (folder / "figures" / "art.svg").write_text(_picture(), encoding="utf-8")
    names = {name: folder / name for name in ("talk.yaml", "figures/cell.yaml", "figures/art.svg")}
    bundle.write(tmp_path / "talk.flexo", names, bundle.manifest(deck.name, "deck", files=len(names)))
    shutil.copyfile(tmp_path / "talk.flexo", tmp_path / "talk (1).flexo")
    laid: list[int] = []
    real = flexo.fit_in_box

    def counted(*args, **kwargs):
        laid.append(1)
        return real(*args, **kwargs)

    monkeypatch.setattr(flexo, "fit_in_box", counted)

    def drawn(path: Path) -> list[str]:
        root = opened(path).root
        compose._FITS.clear()  # (each a studio started afresh)
        document = load_document(root / "talk.yaml")
        kind = DeckKind()
        drawing = kind.draw(document, root, {"focus": 0})
        while drawing.unfinished:
            drawing = kind.draw(document, root, {"focus": 0})
        return [page.svg for page in drawing.pages]

    first = drawn(tmp_path / "talk.flexo")
    assert laid
    laid.clear()
    copy = drawn(tmp_path / "talk (1).flexo")
    assert opened(tmp_path / "talk (1).flexo").root != opened(tmp_path / "talk.flexo").root
    assert laid == []
    assert copy == first


def test_a_picture_edited_while_its_deck_is_open_is_drawn_again(tmp_path: Path) -> None:
    picture = tmp_path / "figures" / "art.svg"
    _deck(tmp_path, "{id: middle, kind: image, height: 60, properties: {source: art.svg}}")
    picture.write_text(_picture(), encoding="utf-8")
    document = {
        "deck": {"id": "open"},
        "slides": [{"title": "A cell", "body": [{"figure": "figures/cell.yaml"}]}],
    }
    kind = DeckKind()
    drawing = kind.draw(document, tmp_path, {"settle": True})
    assert 'viewBox="0 0 100 50"' in drawing.pages[0].svg
    # The picture is watched (the studio draws the deck again when it changes) ...
    assert picture.resolve() in {Path(file).resolve() for file in drawing.files}
    # ... and drawn as it is now, the deck's words as they were.
    _edited(picture, _picture("0 0 100 60"))
    again = kind.draw(document, tmp_path, {"settle": True})
    assert 'viewBox="0 0 100 60"' in again.pages[0].svg


def test_a_picture_in_a_figure_written_in_the_deck_is_watched_too(tmp_path: Path) -> None:
    picture = tmp_path / "art.svg"
    picture.write_text(_picture(), encoding="utf-8")
    figure = {
        "figure": {"id": "inline"},
        "nodes": [{"id": "middle", "kind": "image", "height": 60, "properties": {"source": "art.svg"}}],
        "shapes": [{"kind": "picture", "at": [0, 0], "size": [20, 20], "source": "over.svg"}],
    }
    document = {"deck": {"id": "inline"}, "slides": [{"title": "Inline", "body": [{"figure": figure}]}]}
    kind = DeckKind()
    drawing = kind.draw(document, tmp_path, {"settle": True})
    watched = {Path(file).resolve() for file in drawing.files}
    # (One not there yet is watched for: put there, the slide is drawn with it.)
    assert picture.resolve() in watched and (tmp_path / "over.svg").resolve() in watched
    _edited(picture, _picture("0 0 100 60"))
    assert 'viewBox="0 0 100 60"' in kind.draw(document, tmp_path, {"settle": True}).pages[0].svg


def test_a_frame_s_figures_are_kept_by_their_pictures_too(tmp_path: Path) -> None:
    picture = tmp_path / "figures" / "art.svg"
    _deck(tmp_path, "{id: middle, kind: image, height: 60, properties: {source: art.svg}}")
    picture.write_text(_picture(), encoding="utf-8")
    (tmp_path / "figures" / "other.yaml").write_text(
        "figure: {id: other}\nnodes:\n  - {id: before, label: Before}\n  - {id: middle, label: Middle}\n"
        "  - {id: after, label: After}\nedges:\n  - {from: before, to: middle}\n  - {from: middle, to: after}\n",
        encoding="utf-8",
    )
    deck = tmp_path / "talk.yaml"
    deck.write_text(
        "schema_version: 1\ndeck: {id: framed}\nslides:\n"
        "- title: Other\n  body:\n  - {figure: figures/other.yaml, frame: cell}\n"
        "- title: A cell\n  body:\n  - {figure: figures/cell.yaml, frame: cell}\n",
        encoding="utf-8",
    )
    first = read_deck(deck).build(tmp_path / "one", formats=("svg",)).svgs[1].read_text(encoding="utf-8")
    assert 'viewBox="0 0 100 50"' in first
    _edited(picture, _picture("0 0 100 60"))
    second = read_deck(deck).build(tmp_path / "two", formats=("svg",)).svgs[1].read_text(encoding="utf-8")
    assert 'viewBox="0 0 100 60"' in second


def test_a_picture_put_there_after_a_figure_in_the_deck_names_it_is_drawn(tmp_path: Path) -> None:
    figure = {
        "figure": {"id": "inline"},
        "nodes": [{"id": "middle", "kind": "image", "height": 60, "properties": {"source": "art.svg"}}],
    }
    document = {"deck": {"id": "later"}, "slides": [{"title": "Inline", "body": [{"figure": figure}]}]}
    kind = DeckKind()
    missing = kind.draw(document, tmp_path, {"settle": True})
    assert any("artwork file" in message.text for message in missing.messages)
    (tmp_path / "art.svg").write_text(_picture(), encoding="utf-8")
    found = kind.draw(document, tmp_path, {"settle": True})
    assert 'viewBox="0 0 100 50"' in found.pages[0].svg
    assert not any("artwork file" in message.text for message in found.messages)
