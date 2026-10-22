"""A deck exported again is exported as it was -- its slides as the last export drew, read and
wrote them, kept -- and comes out the same, byte for byte, as one made afresh; an edit made
between shows in the next. A figure the studio drew for its page is not laid out again to be
exported, and a bundle built again on the command line finds what was made for it before."""

from __future__ import annotations

import os
import re
import zipfile
import zlib
from pathlib import Path

import flexo
import pytest

from flexo_talk import compose
from flexo_talk import export as exporting
from flexo_talk.cli import main as talk_main
from flexo_talk.studio import DeckKind

ART = (
    '<svg xmlns="http://www.w3.org/2000/svg" width="40" height="20" viewBox="0 0 40 20"><defs>'
    '<linearGradient id="shade"><stop offset="0" stop-color="#3f7fc0"/><stop offset="1" stop-color="#f0a030"/>'
    '</linearGradient></defs><rect x="2" y="2" width="36" height="16" rx="4" fill="url(#shade)"/>'
    '<circle cx="10" cy="10" r="5" fill="#f0a030"/></svg>'
)
"""A picture drawn in SVG that slides show as a picture (a gradient: what they draw as shapes
does not have one)."""

STRUCTURE = Path(flexo.__file__).resolve().parents[2] / "tests" / "unit" / "data" / "1a7g.cif"


def _talk(folder: Path, *, molecule: bool = False) -> dict:
    """A deck with what an export carries: portraits, a link, a list that builds, a figure,
    a GIF, an SVG picture, a photograph in a figure, notes -- and a molecule, where asked."""

    from PIL import Image

    assets = folder / "assets"
    assets.mkdir(parents=True, exist_ok=True)
    Image.new("RGB", (400, 300), (200, 120, 90)).save(assets / "sam.jpeg")
    Image.new("RGB", (300, 420), (90, 140, 200)).save(assets / "ana.png")
    frames = [Image.new("RGB", (60, 40), colour) for colour in ((220, 40, 40), (40, 160, 60), (40, 60, 200))]
    frames[0].save(assets / "spin.gif", "GIF", save_all=True, append_images=frames[1:], duration=300, loop=0)
    (assets / "art.svg").write_text(ART, encoding="utf-8")
    Image.new("RGB", (80, 60), (30, 30, 30)).save(assets / "photo.png")
    flow = {"figure": {"id": "flow"}, "nodes": [{"id": "a", "label": "Purify"}, {"id": "b", "label": "Mix"}],
            "edges": [{"from": "a", "to": "b"}]}
    framed = {"figure": {"id": "framed"}, "nodes": [
        {"id": "photo", "kind": "image", "properties": {"source": "assets/photo.png"}},
        {"id": "art", "kind": "image", "properties": {"source": "assets/art.svg"}},
        {"id": "words", "label": "A photograph"}]}
    slides = [
        {"layout": "title", "title": "Kept and made again", "subtitle": "An export", "notes": "Say hello."},
        {"title": "A flow", "body": [{"bullets": ["See [Flexo](https://example.com/flexo)", "Then this"],
                                      "reveal": True}, {"figure": flow}],
         "people": [{"image": "assets/sam.jpeg", "name": "Sam"}, {"image": "assets/ana.png", "name": "Ana"}]},
        {"title": "Pictures", "body": [{"image": "assets/spin.gif"}, {"image": "assets/art.svg"}]},
        {"title": "A photograph in a figure", "body": [{"figure": framed}]},
    ]
    if molecule:
        (assets / "1a7g.cif").write_bytes(STRUCTURE.read_bytes())
        model = {"id": "model", "kind": "structure",
                 "properties": {"source": "assets/1a7g.cif", "look": "flat", "width": 120, "height": 90}}
        slides.append({"title": "A molecule", "body": [{"figure": {"figure": {"id": "molecule"}, "nodes": [model]}}]})
    return {"schema_version": 1, "deck": {"id": "kept", "theme": "paper"}, "slides": slides}


def _forget() -> None:
    """Everything an export keeps forgotten: the next is made afresh."""

    from flexo import drawings_kept, pdf, raster_kept

    exporting._WRITTEN.clear()
    drawings_kept._KEPT.clear()
    raster_kept._KEPT.clear()
    pdf._IMAGES.clear()


def _entries(pptx: Path) -> dict[str, bytes]:
    """A PowerPoint's parts, byte for byte -- the dates it was made aside."""

    with zipfile.ZipFile(pptx) as archive:
        parts = {name: archive.read(name) for name in archive.namelist()}
    dated = rb"<dcterms:(created|modified)[^>]*>[^<]*</dcterms:\1>"
    parts["docProps/core.xml"] = re.sub(dated, b"", parts["docProps/core.xml"])
    return parts


def _pages(pdf: Path) -> list[bytes]:
    """A PDF's pages as drawn: each content stream, inflated."""

    data = pdf.read_bytes()
    found = []
    for match in re.finditer(rb"<< /Filter /FlateDecode /Length (\d+) >>\nstream\n", data):
        body = zlib.decompress(data[match.end(): match.end() + int(match.group(1))])
        if body.startswith(b"1 0 0 -1 0 "):
            found.append(body)
    return found


def _counted(monkeypatch, owner: object, name: str) -> list[object]:
    calls: list[object] = []
    real = getattr(owner, name)

    def counting(*args, **options):
        calls.append(args[:1])
        return real(*args, **options)

    monkeypatch.setattr(owner, name, counting)
    return calls


@pytest.fixture(autouse=True)
def _afresh():
    _forget()
    yield
    _forget()


@pytest.mark.parametrize("molecule", [False, True])
def test_an_export_made_again_from_what_was_kept_is_the_export_made_afresh(
    tmp_path: Path, monkeypatch, molecule: bool
) -> None:
    if molecule and (not STRUCTURE.is_file() or pytest.importorskip("molsketch") is None):
        pytest.skip("no structure to draw")
    document = _talk(tmp_path, molecule=molecule)
    kind = DeckKind()
    first = {fmt: kind.export(document, tmp_path, "talk", [fmt], into=tmp_path / f"one-{fmt}")[0]
             for fmt in ("pptx", "pdf")}
    # Again: nothing drawn, read or written afresh -- each slide as the last export made it.
    drawn = _counted(monkeypatch, compose, "render_slide")
    written = _counted(monkeypatch, exporting, "_keep_written")
    again = {fmt: kind.export(document, tmp_path, "talk", [fmt], into=tmp_path / f"two-{fmt}")[0]
             for fmt in ("pptx", "pdf")}
    assert drawn == [] and written == []
    # And afresh, in a studio that has kept nothing.
    _forget()
    afresh = DeckKind()
    fresh = {fmt: afresh.export(document, tmp_path, "talk", [fmt], into=tmp_path / f"fresh-{fmt}")[0]
             for fmt in ("pptx", "pdf")}
    # (Drawn once for both: a PDF's slides are drawn as a PowerPoint's are.)
    assert len(drawn) == len(document["slides"])
    assert _entries(again["pptx"]) == _entries(first["pptx"]) == _entries(fresh["pptx"])
    assert _pages(again["pdf"]) == _pages(first["pdf"]) == _pages(fresh["pdf"])
    parts = _entries(fresh["pptx"])
    # What it carries is there: the GIF as itself, the SVG picture with its PNG, the portraits,
    # the link, the notes.
    media = {name.rsplit(".", 1)[-1] for name in parts if name.startswith("ppt/media/")}
    assert {"gif", "png", "svg", "jpg"} <= media
    assert any(b"https://example.com/flexo" in data for name, data in parts.items() if name.endswith(".rels"))
    assert any(b"Say hello." in data for name, data in parts.items() if name.startswith("ppt/notesSlides/"))


def test_an_edit_between_exports_shows_in_the_next_and_the_rest_is_as_it_was(tmp_path: Path) -> None:
    document = _talk(tmp_path)
    kind = DeckKind()
    (before,) = kind.export(document, tmp_path, "talk", ["pptx"], into=tmp_path / "one")
    document["slides"][1]["title"] = "A flow, renamed"
    # A file a slide shows changed on disk, its document as it was.
    art = tmp_path / "assets" / "art.svg"
    art.write_text(ART.replace('stop-color="#3f7fc0"', 'stop-color="#c03f3f"'), encoding="utf-8")
    stamp = art.stat().st_mtime_ns + 2_000_000_000
    os.utime(art, ns=(stamp, stamp))
    (after,) = kind.export(document, tmp_path, "talk", ["pptx"], into=tmp_path / "two")
    one, two = _entries(before), _entries(after)
    assert b"A flow, renamed" in two["ppt/slides/slide2.xml"] and b"A flow, renamed" not in one["ppt/slides/slide2.xml"]
    svgs = [name for name in two if name.startswith("ppt/media/") and name.endswith(".svg")]
    assert svgs and all(one[name] != two[name] for name in svgs)
    for name in ("ppt/slides/slide1.xml", "ppt/slides/slide4.xml"):
        assert one[name] == two[name]
    # (And as one made afresh has it.)
    _forget()
    (fresh,) = DeckKind().export(document, tmp_path, "talk", ["pptx"], into=tmp_path / "fresh")
    assert _entries(fresh) == two


def test_a_figure_drawn_for_the_studio_s_page_is_not_laid_out_again_to_be_exported(
    tmp_path: Path, monkeypatch
) -> None:
    from flexo.artwork import picture_link
    from flexo.svg_resources import fonts_linked

    document = _talk(tmp_path)
    kind = DeckKind()
    # Drawn as the studio draws for its page: photographs named by an address of its own.
    token = picture_link.set(lambda art: f"/api/picture?path={art.path.name}")
    try:
        with fonts_linked():
            for _ in range(20):
                drawing = kind.draw(document, tmp_path, {"settle": True})
                if not any(page.pending for page in drawing.pages):
                    break
    finally:
        picture_link.reset(token)
    assert any("/api/picture?" in page.svg for page in drawing.pages)
    fits = _counted(monkeypatch, flexo, "fit_in_box")
    (pptx,) = kind.export(document, tmp_path, "talk", ["pptx"], into=tmp_path / "out")
    # The flow, with no photograph, is found as it was drawn for the page; the figure with a
    # photograph is laid out for the export, carrying the photograph itself.
    assert len(fits) == 1
    rendered = [item.svg for item in kind._exports.values()]
    assert rendered and not any("/api/picture?" in svg for svg in rendered)
    _forget()
    kind._exports.clear()
    (fresh,) = DeckKind().export(document, tmp_path, "talk", ["pptx"], into=tmp_path / "fresh")
    assert _entries(pptx) == _entries(fresh)


def test_a_bundle_built_again_finds_what_was_laid_out_for_it_before(tmp_path: Path, monkeypatch) -> None:
    from flexo import bundle

    folder = tmp_path / "talk"
    folder.mkdir()
    document = _talk(folder)
    from flexo_talk.document import dump_document

    (folder / "talk.yaml").write_text(dump_document(document), encoding="utf-8")
    made = bundle.pack(folder / "talk.yaml", tmp_path / "talk.flexo")
    out = tmp_path / "build"
    assert talk_main(["build", str(made.path), "-o", str(out), "--formats", "pptx,pdf"]) == 0
    first = _entries(out / "kept.pptx")
    compose._PROBED.clear()
    fits = _counted(monkeypatch, flexo, "fit_in_box")
    assert talk_main(["build", str(made.path), "-o", str(out), "--formats", "pptx,pdf"]) == 0
    assert fits == []
    assert _entries(out / "kept.pptx") == first
    # Unpacked where it was the first time, and taken away once built.
    builds = Path(os.environ["FLEXO_TALK_CACHE"]) / "builds"
    assert [item.suffix for item in builds.iterdir()] == [".lock"]
