"""What is copied out of a deck in the studio: a slide's objects, shapes and figure parts cut
out of the slide drawn for the page, and Office's own shapes of them (``gvml``), as
PowerPoint's clipboard has them."""

from __future__ import annotations

import base64
import io
import re
import struct
import xml.etree.ElementTree as ET
import zipfile
import zlib
from pathlib import Path

import pytest
from flexo.copied import HELD, Copied, cut_out
from flexo.svg_resources import fonts_linked
from lxml import etree

from flexo_talk.gvml import FORMAT, gvml
from flexo_talk.studio import DeckKind

A = "http://schemas.openxmlformats.org/drawingml/2006/main"
LC = "http://schemas.openxmlformats.org/drawingml/2006/lockedCanvas"
P = "http://schemas.openxmlformats.org/presentationml/2006/main"


def _png(width: int, height: int) -> bytes:
    def chunk(kind: bytes, body: bytes) -> bytes:
        return struct.pack(">I", len(body)) + kind + body + struct.pack(">I", zlib.crc32(kind + body))

    rows = b"".join(b"\x00" + b"\x20\x60\xa0" * width for _ in range(height))
    header = struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0)
    return b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", header) + chunk(b"IDAT", zlib.compress(rows)) + chunk(b"IEND", b"")


DECK = {
    "schema_version": 1,
    "deck": {"id": "talk", "theme": "paper"},
    "slides": [
        {
            "title": "The model",
            "layout": "two-columns",
            "left": [{"text": "Words *on* the slide"}, {"image": "photo.png"}],
            "right": [
                {
                    "figure": {
                        "figure": {"id": "f"},
                        "nodes": [{"id": "a", "label": "Alpha"}, {"id": "b", "label": "Beta"}],
                        "edges": [{"from": "a", "to": "b"}],
                    }
                }
            ],
            "shapes": [{"kind": "rectangle", "at": [100, 420], "size": [120, 50], "text": "Box"}],
        }
    ],
}


@pytest.fixture(scope="module")
def slide(tmp_path_factory: pytest.TempPathFactory) -> tuple[str, Path]:
    """The slide as the studio draws it for its page: its words' fonts named, its placeholders
    faint, its photograph named by address."""

    from flexo.artwork import picture_link

    folder = tmp_path_factory.mktemp("deck")
    (folder / "photo.png").write_bytes(_png(64, 40))
    token = picture_link.set(lambda artwork: f"/api/picture?path={artwork.path.name}&v=1&token=t")
    try:
        with fonts_linked():
            for _ in range(60):
                drawing = DeckKind().draw(DECK, folder, {"focus": 0})
                if not drawing.unfinished:
                    break
    finally:
        picture_link.reset(token)
    return drawing.pages[0].svg, folder


def _view(svg: str) -> list[float]:
    return [float(value) for value in ET.fromstring(svg).get("viewBox").split()]


def test_a_slide_s_shape_object_and_figure_parts_are_cut_out_of_it(slide: tuple[str, Path]) -> None:
    svg, _ = slide
    shape = cut_out(svg, ["slide1.shapes.0"])
    # The rectangle, 120 by 50 at (100, 420), and its stroke: no more of the slide.
    x, y, width, height = _view(shape)
    assert 95 < x < 100 and 415 < y < 420 and 120 < width < 128 and 50 < height < 58
    assert "slide1.title" not in shape and "canvas.background" not in shape
    words = cut_out(svg, ["slide1.left.0"])
    assert "Words" in words and "slide1.shapes.0" not in words
    parts = cut_out(svg, ["slide1.right.0.a", "slide1.right.0.b", "slide1.right.0.edge.1.a-to-b"])
    assert "slide1.right.0.a" in parts and HELD in parts
    whole = cut_out(svg)
    assert _view(whole) == [0, 0, 960, 540] and "canvas.background" in whole


def test_a_picture_on_a_slide_is_copied_at_its_full_size(slide: tuple[str, Path]) -> None:
    from flexo.studio.copying import copied

    svg, folder = slide

    class Folder:
        def path(self, name: str) -> Path:
            return folder / name

    made = copied(Folder(), svg, ["slide1.left.1"])
    picture = re.search(r'href="data:image/png;base64,([^"]+)"', made.editable)
    assert picture and base64.b64decode(picture.group(1)) == (folder / "photo.png").read_bytes()
    assert made.pdf().startswith(b"%PDF") and b"/Subtype /Image" in made.pdf()


def _package(data: bytes) -> tuple[zipfile.ZipFile, etree._Element]:
    package = zipfile.ZipFile(io.BytesIO(data))
    return package, etree.fromstring(package.read("clipboard/drawings/drawing1.xml"))


def test_office_shapes_are_packaged_as_powerpoint_packages_them(slide: tuple[str, Path]) -> None:
    svg, _ = slide
    package, _ = _package(gvml(cut_out(svg, ["slide1.shapes.0"])))
    assert FORMAT == "com.microsoft.Art--GVML-ClipFormat"
    assert sorted(package.namelist()) == [
        "[Content_Types].xml",
        "_rels/.rels",
        "clipboard/drawings/_rels/drawing1.xml.rels",
        "clipboard/drawings/drawing1.xml",
        "clipboard/theme/theme1.xml",
    ]
    rels = package.read("_rels/.rels").decode()
    assert 'Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/drawing"' in rels
    assert 'Target="clipboard/drawings/drawing1.xml"' in rels
    types = package.read("[Content_Types].xml").decode()
    assert (
        'PartName="/clipboard/drawings/drawing1.xml" '
        'ContentType="application/vnd.openxmlformats-officedocument.drawing+xml"' in types
    )
    assert (
        'PartName="/clipboard/theme/theme1.xml" ContentType="application/vnd.openxmlformats-officedocument.theme+xml"'
        in types
    )
    theme = etree.fromstring(package.read("clipboard/theme/theme1.xml"))
    assert etree.QName(theme).localname == "clipboardTheme"
    assert [etree.QName(child).localname for child in theme] == ["themeElements", "clrMap"]
    assert 'Target="../theme/theme1.xml"' in package.read("clipboard/drawings/_rels/drawing1.xml.rels").decode()


GVML_ORDER = {
    "sp": ["nvSpPr", "spPr", "txSp", "style"],
    "cxnSp": ["nvCxnSpPr", "spPr", "style"],
    "pic": ["nvPicPr", "blipFill", "spPr", "style"],
}


def _in_order(element: etree._Element) -> None:
    """Each shape holds what DrawingML's canvas has a shape hold, in its order."""

    kind = etree.QName(element).localname
    names = [etree.QName(child).localname for child in element]
    if kind == "grpSp":
        assert names[:2] == ["nvGrpSpPr", "grpSpPr"], names
        for child in list(element)[2:]:
            _in_order(child)
        return
    order = GVML_ORDER[kind]
    assert names == [name for name in order if name in names], names
    assert set(names) <= set(order)


def test_a_slide_s_objects_are_office_shapes_in_the_locked_canvas(slide: tuple[str, Path]) -> None:
    svg, folder = slide
    photo = "data:image/png;base64," + base64.b64encode((folder / "photo.png").read_bytes()).decode()
    drawn = cut_out(
        svg, ["slide1.shapes.0", "slide1.left.0", "slide1.left.1", "slide1.right.0"], picture=lambda href: photo
    )
    package, root = _package(gvml(drawn))
    assert etree.QName(root).localname == "graphic" and etree.QName(root).namespace == A
    data = root.find(f"{{{A}}}graphicData")
    assert data.get("uri") == LC
    canvas = data.find(f"{{{LC}}}lockedCanvas")
    assert [etree.QName(child).localname for child in canvas][:2] == ["nvGrpSpPr", "grpSpPr"]
    # The canvas is the copy's size, in EMU.
    width, height = _view(drawn)[2:]
    extent = canvas.find(f"{{{A}}}grpSpPr/{{{A}}}xfrm/{{{A}}}ext")
    assert int(extent.get("cx")) == round(width * 12700) and int(extent.get("cy")) == round(height * 12700)
    # Nothing of a slide's own (PresentationML) is in it.
    assert not [item for item in root.iter() if etree.QName(item).namespace == P]
    for shape in list(canvas)[2:]:
        _in_order(shape)
    # Words are a shape's own text, as PowerPoint copies them: in a txSp, its box the shape's.
    spoken = [shape for shape in root.iter(f"{{{A}}}sp") if shape.find(f"{{{A}}}txSp") is not None]
    assert spoken and all(shape.find(f"{{{A}}}txSp/{{{A}}}useSpRect") is not None for shape in spoken)
    words = "".join(text.text or "" for text in root.iter(f"{{{A}}}t"))
    assert "Box" in words and "Alpha" in words and "Beta" in words and "slide" in words
    # The figure's line is a connector joined to its two shapes; the figure a group.
    joined = root.find(f".//{{{A}}}cxnSp/{{{A}}}nvCxnSpPr/{{{A}}}cNvCxnSpPr")
    assert joined is not None and joined.find(f"{{{A}}}stCxn") is not None and joined.find(f"{{{A}}}endCxn") is not None
    ids = {int(item.get("id")) for item in root.iter(f"{{{A}}}cNvPr")}
    assert {int(joined.find(f"{{{A}}}stCxn").get("id")), int(joined.find(f"{{{A}}}endCxn").get("id"))} <= ids
    assert len(ids) == len(list(root.iter(f"{{{A}}}cNvPr")))
    # The photograph is a picture of the package, related from the drawing.
    blip = root.find(f".//{{{A}}}pic/{{{A}}}blipFill/{{{A}}}blip")
    embed = blip.get("{http://schemas.openxmlformats.org/officeDocument/2006/relationships}embed")
    rels = package.read("clipboard/drawings/_rels/drawing1.xml.rels").decode()
    target = re.search(rf'Id="{embed}" Type="[^"]+/image" Target="\.\./media/([^"]+)"', rels)
    assert target and package.read(f"clipboard/media/{target.group(1)}").startswith(b"\x89PNG")
    assert 'Extension="png" ContentType="image/png"' in package.read("[Content_Types].xml").decode()


def test_what_only_held_the_copy_is_no_group_pasted(slide: tuple[str, Path]) -> None:
    """A slide's region round the object copied, and a figure round its parts copied, are not
    groups of their own in the paste: the shapes are pasted as they were chosen."""

    svg, _ = slide
    _, root = _package(gvml(cut_out(svg, ["slide1.right.0.a", "slide1.right.0.b"])))
    canvas = root.find(f".//{{{LC}}}lockedCanvas")
    top = [etree.QName(child).localname for child in canvas][2:]
    # Alpha and Beta, each a group of its box and words -- not inside the figure's group.
    assert top == ["grpSp", "grpSp"]
    whole = gvml(cut_out(svg, ["slide1.right.0"]))
    _, root = _package(whole)
    assert [etree.QName(child).localname for child in root.find(f".//{{{LC}}}lockedCanvas")][2:] == ["grpSp"]


def test_a_copy_s_office_shapes_are_made_from_its_drawing(slide: tuple[str, Path]) -> None:
    svg, _ = slide
    copied = Copied(cut_out(svg, ["slide1.shapes.0"]))
    assert gvml(copied.drawing) == gvml(copied.editable)
