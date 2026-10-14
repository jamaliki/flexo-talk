"""An SVG picture on a slide, its words set in the deck's figure font -- the same on the slide,
in the PDF, the PNG and the PowerPoint -- or as its block says (``font``, ``texts``,
``colours``), its file never changed (``flexo.restyle``)."""

from __future__ import annotations

import re
import zipfile
from pathlib import Path

import pytest

from flexo_talk import Deck
from flexo_talk.deck import SettingError
from flexo_talk.document import DeckDocumentError, deck_document, deck_from_document

DRAWING = """\
<svg xmlns="http://www.w3.org/2000/svg" xmlns:sodipodi="http://sodipodi.sourceforge.net/DTD/sodipodi-0.dtd"
     width="300pt" height="120pt" viewBox="0 0 300 120">
  <rect id="box" x="10" y="10" width="120" height="50" style="fill:#4a90d9;stroke:#1b1b1b"/>
  <text id="title" xml:space="preserve" x="10" y="90"
    style="font-size:20px;font-family:'Helvetica Neue';font-weight:bold"><tspan sodipodi:role="line" x="10"
    y="90">Encoder</tspan></text>
  <text id="note" x="160" y="90" style="font-size:16px;font-family:'IBM Plex Mono';fill:#555555">mono</text>
</svg>
"""


def faces_in(pptx: Path) -> list[tuple[str, str]]:
    with zipfile.ZipFile(pptx) as deck:
        xml = deck.read("ppt/slides/slide1.xml").decode()
    return re.findall(r'<a:latin typeface="([^"]+)"[^>]*/>.*?<a:t>([^<]*)</a:t>', xml)


@pytest.fixture
def drawing(tmp_path: Path) -> Path:
    path = tmp_path / "drawing.svg"
    path.write_text(DRAWING, encoding="utf-8")
    return path


def test_a_drawings_words_are_in_the_decks_figure_font_on_the_slide_and_in_the_powerpoint(
    tmp_path: Path, drawing: Path
) -> None:
    deck = Deck("d", figure_font="Liberation Sans")
    assert deck.figure_family == "Liberation Sans"
    deck.slide("S").image(str(drawing))
    (rendered,) = deck.render()
    picture = rendered.svg[rendered.svg.index('id="slide1.body.0"'):]
    assert "font-family:'Liberation Sans'" in picture and "Helvetica Neue" not in picture
    built = deck.build(tmp_path / "out", formats=("pptx", "pdf"))
    faces = dict((words, face) for face, words in faces_in(built.pptx))
    assert faces["Encoder"] == faces["mono"] == "Liberation Sans"
    assert b"LiberationSans" in built.pdf.read_bytes() and b"PlexMono" not in built.pdf.read_bytes()
    assert drawing.read_text(encoding="utf-8") == DRAWING


def test_as_drawn_a_named_font_and_changed_words_reach_every_output(tmp_path: Path, drawing: Path) -> None:
    deck = Deck("d")
    deck.slide("S").image(str(drawing), font="drawn", texts=[{"id": "title", "words": "Decoder", "italic": True}],
                          colours={"#4a90d9": "#2e7d32"})
    built = deck.build(tmp_path / "out", formats=("pptx",))
    faces = dict((words, face) for face, words in faces_in(built.pptx))
    assert faces["mono"] == "IBM Plex Mono" and "Encoder" not in faces and "Decoder" in faces
    (rendered,) = deck.render()
    assert "#2e7d32" in rendered.svg and "#4a90d9" not in rendered.svg
    named = Deck("n")
    named.slide("S").image(str(drawing), font="IBM Plex Mono")
    faces = dict((words, face) for face, words in faces_in(named.build(tmp_path / "n", formats=("pptx",)).pptx))
    assert faces["Encoder"] == faces["mono"] == "IBM Plex Mono"


def test_a_drawing_drawn_as_a_picture_carries_the_faces_its_words_are_in(tmp_path: Path) -> None:
    import base64

    picture = tmp_path / "graded.svg"
    picture.write_text(
        '<svg xmlns="http://www.w3.org/2000/svg" width="200" height="60" viewBox="0 0 200 60">'
        '<defs><linearGradient id="g"><stop offset="0" stop-color="#fff"/><stop offset="1" stop-color="#eee"/>'
        '</linearGradient></defs><rect width="200" height="60" fill="url(#g)"/>'
        '<text x="10" y="45" font-size="40" font-family="Georgia" fill="#000">Words</text></svg>'
    )
    deck = Deck("p")
    deck.slide("S").image(str(picture), colours={"#eeeeee": "#ff0000"})
    (rendered,) = deck.render()
    found = re.search(r'href="data:image/svg\+xml;base64,([^"]+)"', rendered.svg)
    inner = base64.b64decode(found.group(1)).decode()
    # Its words in the deck's figure font, which it carries: a picture sees none of the page's.
    assert f"@font-face{{font-family:'{deck.figure_family}'" in inner and "Georgia" not in inner
    assert 'stop-color="#ff0000"' in inner


def test_a_documents_picture_keeps_its_font_texts_and_colours_and_says_what_does_not_read(drawing: Path) -> None:
    block = {"image": "drawing.svg", "font": "drawn", "texts": [{"id": "title", "words": "A\nB", "size": 18}],
             "colours": {"#4a90d9": "#2e7d32"}}
    document = {"schema_version": 1, "deck": {"id": "d"}, "slides": [{"title": "S", "body": [block]}]}
    deck = deck_from_document(document, drawing.parent)
    written = deck_document(deck)["slides"][0]["body"][0]
    assert written["font"] == "drawn" and written["colours"] == {"#4a90d9": "#2e7d32"}
    assert written["texts"] == [{"id": "title", "words": "A\nB", "size": 18.0}]
    wrong = {**block, "texts": [{"words": "no key"}]}
    with pytest.raises(DeckDocumentError) as caught:
        deck_from_document({**document, "slides": [{"title": "S", "body": [wrong]}]}, drawing.parent)
    assert "texts: each names its text" in str(caught.value).lower()
    with pytest.raises(SettingError):
        Deck("d").slide("S").image(str(drawing), colours={"#fff": "nothing"})
