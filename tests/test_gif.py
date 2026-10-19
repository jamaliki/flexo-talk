"""A GIF on a slide: a picture that plays wherever a screen shows it -- the studio, presenting,
the SVG in a browser, PowerPoint and Keynote (embedded as itself, every frame) -- sized and
cropped as any picture is, and in a PDF or a PNG the frame its ``still`` names. A deck's GIFs
travel in its bundle as they are; a logo that is a GIF holds still on every slide."""

from __future__ import annotations

import base64
import io
import re
import subprocess
import xml.etree.ElementTree as ET
import zipfile
from pathlib import Path

import pytest
from flexo import bundle as B
from flexo.animated import STILL
from flexo.drawing import read_drawing
from PIL import Image

from flexo_talk.compose import render_slide
from flexo_talk.deck import SettingError
from flexo_talk.document import DeckDocumentError, deck_from_document, read_deck
from flexo_talk.export import build_deck

COLOURS = ((200, 16, 46), (31, 119, 180), (44, 160, 44))
"""Red, blue and green: a frame each."""


def gif(width: int = 240, height: int = 160) -> bytes:
    frames = [Image.new("RGB", (width, height), colour) for colour in COLOURS]
    out = io.BytesIO()
    frames[0].save(out, "GIF", save_all=True, append_images=frames[1:], duration=400, loop=0)
    return out.getvalue()


@pytest.fixture
def folder(tmp_path: Path) -> Path:
    (tmp_path / "spin.gif").write_bytes(gif())
    return tmp_path


def deck_of(*slides: dict, **deck: object) -> dict:
    return {"schema_version": 1, "deck": {"id": "talk", "theme": "paper", **deck}, "slides": list(slides)}


def drawn(document: dict, base: Path, at: int = 0) -> ET.Element:
    deck = deck_from_document(document, base)
    return ET.fromstring(render_slide(deck, deck.slides[at]).svg)


def by_id(root: ET.Element, ident: str) -> ET.Element:
    return next(item for item in root.iter() if item.get("id") == ident)


def colour_at(png: bytes, x: float, y: float) -> tuple[int, int, int]:
    """The colour at (x, y), as fractions of the picture's width and height."""

    with Image.open(io.BytesIO(png)) as picture:
        return picture.convert("RGB").getpixel((int(picture.width * x), int(picture.height * y)))


def test_a_gif_is_drawn_as_a_picture_sized_by_its_pixels(folder: Path) -> None:
    root = drawn(deck_of({"title": "Turning", "body": [{"image": "spin.gif", "still": 2}]}), folder)
    picture = by_id(root, "slide1.body.0")
    assert picture.tag.endswith("image") and picture.get(STILL) == "2"
    original = base64.b64encode((folder / "spin.gif").read_bytes()).decode()
    assert picture.get("href") == f"data:image/gif;base64,{original}"
    # In its own proportions: 240 by 160 pixels.
    assert float(picture.get("width")) / float(picture.get("height")) == pytest.approx(1.5)
    # The first frame is the still unless it says: none is written for it.
    first = by_id(drawn(deck_of({"title": "Turning", "body": [{"image": "spin.gif"}]}), folder), "slide1.body.0")
    assert first.get(STILL) is None


def test_still_is_a_frame_counted_from_one(folder: Path) -> None:
    from flexo_talk import Deck

    for wrong in (0, -2, 1.5, "two", True):
        with pytest.raises(DeckDocumentError, match="still must be the number of one of a GIF's frames"):
            deck_from_document(deck_of({"title": "x", "body": [{"image": "spin.gif", "still": wrong}]}), folder)
    with pytest.raises(SettingError):
        Deck("talk").slide("x").body.image(folder / "spin.gif", still=0)
    deck = Deck("talk")
    deck.slide("x").body.image(folder / "spin.gif", still=12)
    assert deck.slides[0].regions["body"].blocks[0].still == 12


def test_a_gif_cropped_is_a_window_on_it_that_still_plays(folder: Path) -> None:
    """A browser shows only a GIF's first frame in a pattern, which other pictures are cropped
    with: a GIF is cropped by a window on it -- read back as the one picture, cropped."""

    root = drawn(deck_of({"title": "Cropped", "body": [
        {"image": "spin.gif", "crop": [0.25, 0, 0.5, 1], "still": 3},
    ]}), folder)
    window = by_id(root, "slide1.body.0")
    assert window.tag.endswith("}svg") and window.get("data-flexo-whole")
    assert not root.findall(".//{http://www.w3.org/2000/svg}pattern")
    inner = window.find("{http://www.w3.org/2000/svg}image")
    assert inner.get("href").startswith("data:image/gif;base64,") and inner.get(STILL) == "3"
    picture = next(item for item in read_drawing(ET.tostring(root, encoding="unicode")).walk()
                   if getattr(item, "id", None) == "slide1.body.0")
    kept = picture.clip[2] - picture.clip[0]
    assert kept == pytest.approx(picture.width / 2.0, rel=1e-3) and not picture.oval


def test_a_deck_of_gifs_plays_in_powerpoint_and_shows_its_stills_on_paper(folder: Path, tmp_path: Path) -> None:
    document = deck_of(
        {"title": "Turning", "layout": "two-columns", "left": [
            {"image": "spin.gif", "still": 2},
            {"image": "spin.gif", "crop": [0.25, 0, 0.5, 1], "mask": "circle"},
        ], "right": [
            {"image": "spin.gif", "crop": [0, 0.25, 1, 0.5], "still": 3},
            {"gallery": ["spin.gif", "spin.gif"], "crop": "circle", "height": 60},
        ]},
    )
    deck = deck_from_document(document, folder)
    out = build_deck(deck, tmp_path / "out", ("pptx", "pdf", "png", "svg"))
    original = (folder / "spin.gif").read_bytes()
    # PowerPoint: the GIF itself, once, every frame, as image/gif, for each picture of it.
    with zipfile.ZipFile(out.pptx) as archive:
        media = [name for name in archive.namelist() if name.startswith("ppt/media/")]
        assert media == ["ppt/media/image1.gif"] and archive.read(media[0]) == original
        assert 'Extension="gif" ContentType="image/gif"' in archive.read("[Content_Types].xml").decode()
        rels = archive.read("ppt/slides/_rels/slide1.xml.rels").decode()
        slide = archive.read("ppt/slides/slide1.xml").decode()
    target = re.search(r'Id="(rId\d+)"[^>]*Target="\.\./media/image1\.gif"', rels)
    pictures = re.findall(r"<p:pic>.*?</p:pic>", slide)
    assert target and len(pictures) == 5
    assert all(f'r:embed="{target.group(1)}"' in picture for picture in pictures)
    # Each where the slide draws it, cropped natively: the middle half across, kept round;
    # the middle half down; the gallery's made round.
    crops = [re.search(r"<a:srcRect[^>]*>", picture) for picture in pictures]
    assert crops[0] is None and 'l="25000"' in crops[1].group(0) and 'r="25000"' in crops[1].group(0)
    assert 't="25000"' in crops[2].group(0) and 'b="25000"' in crops[2].group(0)
    assert [('prst="ellipse"' in picture) for picture in pictures] == [False, True, False, True, True]
    # The SVG carries the GIF, every frame, to play.
    assert base64.b64encode(original).decode() in out.svgs[0].read_text(encoding="utf-8")
    # The PNG and the PDF: the frame each names -- blue, the first (red), green.
    png = out.pngs[0].read_bytes()
    shown = {colour_at(png, *where) for where in ((0.25, 0.42), (0.25, 0.75), (0.75, 0.38))}
    assert shown == set(COLOURS)
    page = _pdf_page(out.pdf, tmp_path)
    if page is not None:
        assert {colour_at(page, *where) for where in ((0.25, 0.42), (0.25, 0.75), (0.75, 0.38))} == set(COLOURS)


def _pdf_page(pdf: Path, tmp_path: Path) -> bytes | None:
    import shutil

    if shutil.which("pdftoppm") is None:
        return None
    subprocess.run(["pdftoppm", "-r", "50", "-png", "-singlefile", str(pdf), str(tmp_path / "page")], check=True)
    return (tmp_path / "page.png").read_bytes()


def test_a_gif_logo_holds_still_on_every_slide(folder: Path, tmp_path: Path) -> None:
    document = deck_of({"title": "One", "body": [{"text": "Words"}]}, logos=["spin.gif"], logos_on="every")
    logo = by_id(drawn(document, folder), "slide1.logo0")
    href = logo.get("href")
    assert href.startswith("data:image/png;base64,")
    assert colour_at(base64.b64decode(href.split(",", 1)[1]), 0.5, 0.5) == COLOURS[0]


def test_a_gif_travels_in_its_deck_bundle_as_it_is(folder: Path, tmp_path: Path) -> None:
    (folder / "talk.yaml").write_text(
        "deck: {id: turning}\nslides:\n- title: Turning\n  body:\n  - image: spin.gif\n    still: 2\n", encoding="utf-8"
    )
    made = B.pack(folder / "talk.yaml", tmp_path / "turning.flexo")
    with zipfile.ZipFile(made.path) as archive:
        stored = [info for info in archive.infolist() if info.filename.endswith("spin.gif")]
        assert len(stored) == 1 and archive.read(stored[0]) == (folder / "spin.gif").read_bytes()
    out = tmp_path / "out"
    B.unpack(made.path, out)
    unpacked = next(out.rglob("spin.gif"))
    assert unpacked.read_bytes() == (folder / "spin.gif").read_bytes()
    assert read_deck(next(out.rglob("talk.yaml"))).slides[0].regions["body"].blocks[0].still == 2


def test_a_figures_gif_drawn_for_the_studio_first_still_goes_into_the_powerpoint(folder: Path, tmp_path: Path) -> None:
    """A figure's photographs are named by address while the studio draws its page, and carried
    in an export: a figure drawn for the page, its layout kept, must not be exported so. (The
    owner's slide 22 lost its GIF, and slide 46 its pictures, in the app's PowerPoint.)"""

    from flexo.artwork import picture_link

    document = deck_of({"title": "Cycle", "body": [{"figure": {"figure": {"id": "cycle"}, "nodes": [
        {"id": "label", "label": "Motif"},
        {"id": "motif", "kind": "image", "height": 80, "properties": {"source": "spin.gif", "still": 1}},
    ], "edges": [{"from": "label", "to": "motif"}]}}]})
    deck = deck_from_document(document, folder)
    token = picture_link.set(lambda artwork: f"/api/picture?path={artwork.path.name}")
    try:
        page = render_slide(deck, deck.slides[0]).svg
    finally:
        picture_link.reset(token)
    assert "/api/picture?path=spin.gif" in page
    out = build_deck(deck_from_document(document, folder), tmp_path / "out", ("pptx",))
    with zipfile.ZipFile(out.pptx) as archive:
        assert "ppt/media/image1.gif" in archive.namelist()
        assert archive.read("ppt/media/image1.gif") == (folder / "spin.gif").read_bytes()
