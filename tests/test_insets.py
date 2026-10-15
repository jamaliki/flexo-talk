"""Zoom insets on a slide (``flexo.insets``) and pictures masked by shapes (``flexo.masks``):
read and written back as a document says them, drawn in the slide's SVG, and in its PDF, its
PNG and its PowerPoint -- a cropped picture and PowerPoint's own shapes there."""

from __future__ import annotations

import re
import xml.etree.ElementTree as ET
import zipfile
from pathlib import Path

import pytest

from flexo_talk.compose import render_slide
from flexo_talk.document import DeckDocumentError, deck_document, deck_from_document
from flexo_talk.export import build_deck

SVG = "{http://www.w3.org/2000/svg}"
FIGURE = """figure: {id: pipe}
nodes:
- {id: encoder, label: Encoder}
- {id: decoder, label: Decoder}
edges:
- {from: encoder, to: decoder}
"""


@pytest.fixture
def folder(tmp_path: Path) -> Path:
    from PIL import Image, ImageDraw

    picture = Image.new("RGB", (400, 300), (10, 20, 40))
    ImageDraw.Draw(picture).rectangle((200, 100, 260, 160), fill=(240, 80, 80))
    picture.save(tmp_path / "cells.png")
    (tmp_path / "pipe.yaml").write_text(FIGURE)
    return tmp_path


def deck(*slides: dict) -> dict:
    return {"schema_version": 1, "deck": {"id": "talk", "theme": "paper"}, "slides": list(slides)}


INSET = {"kind": "inset", "of": "left[0]", "region": [0.5, 0.25, 0.25, 0.25], "at": [520, 140], "size": [300, 225],
         "text": "b", "connector_dash": "dashed"}
MICROGRAPH = {"title": "Cells", "layout": "two-columns", "left": [{"image": "cells.png"}], "right": [{"text": "Words"}],
              "shapes": [INSET]}


def element(root: ET.Element, ident: str) -> ET.Element | None:
    return next((item for item in root.iter() if item.get("id") == ident), None)


def test_an_inset_is_read_and_written_back_as_written(folder: Path) -> None:
    written = deck_document(deck_from_document(deck(MICROGRAPH), folder))
    assert written["slides"][0]["shapes"] == [INSET]


def test_an_inset_shows_its_region_of_the_picture_magnified(folder: Path) -> None:
    made = deck_from_document(deck(MICROGRAPH), folder)
    rendered = render_slide(made, made.slides[0])
    root = ET.fromstring(rendered.svg)
    picture = element(root, "slide1.left.0")
    x, y, w, h = (float(value) for value in picture.get("data-flexo-box").split())
    inset = element(root, "slide1.shapes.0")
    assert inset.get("data-flexo-shape") == "inset" and inset.get("data-flexo-of") == "left[0]"
    region = [float(value) for value in inset.get("data-flexo-region").split()]
    assert region == pytest.approx([x + 0.5 * w, y + 0.25 * h, 0.25 * w, 0.25 * h], abs=0.01)
    used = inset.find(f".//{SVG}use")
    assert used.get("href") == "#slide1.left.0"
    # Magnified to fill the box: the region's corner lands on the box's.
    a, _, _, d, e, f = (float(value) for value in re.findall(r"[-\d.]+", used.get("transform")))
    assert a == pytest.approx(300 / (0.25 * w), rel=1e-3) and a == d
    assert (a * region[0] + e, a * region[1] + f) == pytest.approx((520, 140), abs=0.05)
    # Its frame, its two lines, its view clipped to the box, its outline and its label.
    for piece in ("frame", "connectors", "view", "border", "text"):
        assert element(root, f"slide1.shapes.0.{piece}") is not None, piece
    assert not rendered.diagnostics


def test_an_inset_of_a_figure_shows_its_vectors(folder: Path) -> None:
    slide = {"title": "Pipeline", "body": [{"figure": "pipe.yaml"}],
             "shapes": [{"kind": "inset", "of": "body[0]", "at": [600, 300], "size": [240, 160]}]}
    made = deck_from_document(deck(slide), folder)
    root = ET.fromstring(render_slide(made, made.slides[0]).svg)
    figure = element(root, "slide1.body.0")
    assert figure.get("data-flexo-box") and figure.get("data-flexo-talk") == "figure"
    assert element(root, "slide1.shapes.0").find(f".//{SVG}use").get("href") == "#slide1.body.0"


def test_an_inset_of_nothing_is_its_box_and_says_so(folder: Path) -> None:
    slide = {"title": "Words", "body": [{"text": "Just words"}],
             "shapes": [{"kind": "inset", "of": "body[3]", "at": [600, 300], "size": [240, 160]}]}
    made = deck_from_document(deck(slide), folder)
    rendered = render_slide(made, made.slides[0])
    inset = element(ET.fromstring(rendered.svg), "slide1.shapes.0")
    assert inset.find(f".//{SVG}use") is None and inset.find(f".//{SVG}path") is not None
    assert any("zoom inset of body[3] shows nothing" in said for said in rendered.diagnostics)


def test_an_inset_is_in_every_export(folder: Path) -> None:
    pipeline = {"title": "Pipeline", "body": [{"figure": "pipe.yaml"}],
                "shapes": [{"kind": "inset", "of": "body[0]", "region": [0.1, 0.2, 0.3, 0.5], "at": [600, 300],
                            "size": [240, 160]}]}
    made = deck_from_document(deck(MICROGRAPH, pipeline), folder)
    out = build_deck(made, folder / "out", ("png", "pdf", "pptx"))
    assert out.pdf.read_bytes().startswith(b"%PDF") and len(out.pngs) == 2
    from flexo.drawing import Group, read_drawing

    # The PNG's (and the PDF's) drawing: the view read back, clipped to the box.
    drawing = read_drawing(made.render()[0].svg)

    def views(group: Group) -> list[Group]:
        found = []
        for item in group.items:
            if isinstance(item, Group):
                found += [item] if item.data.get("data-flexo-inset") == "view" else views(item)
        return found

    (view,) = views(drawing.root)
    assert view.clip == pytest.approx((520, 140, 820, 365), abs=0.01)
    with zipfile.ZipFile(out.pptx) as package:
        first = package.read("ppt/slides/slide1.xml").decode()
        second = package.read("ppt/slides/slide2.xml").decode()
        media = package.namelist()
    # A photograph magnified: the picture itself, cropped natively to the region; the rest
    # PowerPoint's own shapes, grouped, named as the studio names it.
    assert 'name="Zoom Inset' in first
    crops = re.findall(r'<a:srcRect l="(\d+)" t="(\d+)" r="(\d+)" b="(\d+)"/>', first)
    assert ("50000", "25000", "25000", "50000") in crops
    assert first.count("<p:cxnSp") + first.count("<a:prstGeom prst=\"line\"") >= 2 or first.count("<p:sp>") >= 4
    # A figure magnified: a picture of its vectors (an SVG, with a PNG for those that draw none).
    assert "svgBlip" in second and any(name.endswith(".svg") for name in media)


def test_a_picture_is_masked_by_a_shape(folder: Path) -> None:
    masked = {"image": "cells.png", "crop": [0.25, 0, 0.5, 1], "mask": {"kind": "star", "tips": 6}}
    slide = {"title": "Masked", "body": [masked]}
    made = deck_from_document(deck(slide), folder)
    # Written back as it was read.
    assert deck_document(made)["slides"][0]["body"][0] == masked
    root = ET.fromstring(render_slide(made, made.slides[0]).svg)
    picture = element(root, "slide1.body.0")
    assert picture.tag == f"{SVG}path" and picture.get("fill") == "url(#slide1.body.0.crop)"
    assert picture.get("data-flexo-whole") and picture.get("data-flexo-box")
    out = build_deck(made, folder / "out", ("pdf", "pptx", "png"))
    assert out.pdf.read_bytes().startswith(b"%PDF")
    with zipfile.ZipFile(out.pptx) as package:
        xml = package.read("ppt/slides/slide1.xml").decode()
    # PowerPoint's picture in that shape: a freeform of its outline, cropped natively.
    picture_xml = xml[xml.index("<p:pic"):xml.index("</p:pic>")]
    assert "<a:custGeom>" in picture_xml and "<a:srcRect" in picture_xml


@pytest.mark.parametrize(("mask", "said"), [
    ("oval", "mask must be circle, or a closed shape"),
    ({"kind": "arrow", "from": [0, 0], "to": [1, 1]}, "masked by a closed shape"),
    ({"kind": "star", "tips": 99}, "tips"),
])
def test_a_mask_written_wrong_says_what_a_mask_is(folder: Path, mask: object, said: str) -> None:
    document = deck({"title": "A", "body": [{"image": "cells.png", "mask": mask}]})
    with pytest.raises(DeckDocumentError, match=said):
        deck_from_document(document, folder)
