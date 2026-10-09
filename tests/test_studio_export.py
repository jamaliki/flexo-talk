"""The studio's exports of a deck, as Keynote's Export To makes them: a PDF with a
page per slide (each stage of its builds only when asked), and an image of each slide
in a folder of the deck's name, made aside for the page to hand over; the CLI's build/
is as it was."""

from __future__ import annotations

from pathlib import Path

from flexo_talk.studio import DeckKind

DECK = {
    "schema_version": 1,
    "deck": {"id": "My Talk", "theme": "paper"},
    "slides": [
        {"layout": "title", "title": "A talk"},
        {"title": "Three things", "body": [{"bullets": ["One", "Two", "Three"], "reveal": True}]},
    ],
}


def _pages(pdf: Path) -> int:
    return pdf.read_bytes().count(b"/Type /Page ")


def test_the_pdf_has_a_page_per_slide_showing_it_whole(tmp_path: Path) -> None:
    written = DeckKind().export(DECK, tmp_path, "talk", ["pdf"], into=tmp_path / "out")
    assert [path.name for path in written] == ["My Talk.pdf"]
    assert _pages(written[0]) == 2


def test_each_stage_of_builds_is_a_page_when_asked(tmp_path: Path) -> None:
    written = DeckKind().export(DECK, tmp_path, "talk", ["pdf"], into=tmp_path / "out", steps=True)
    # The title slide, then the list's slide bare and with each of its three items.
    assert _pages(written[0]) == 1 + 4


def test_images_made_aside_are_a_folder_of_the_deck_s_name(tmp_path: Path) -> None:
    written = DeckKind().export(DECK, tmp_path, "talk", ["png", "svg"], into=tmp_path / "out")
    assert sorted(path.relative_to(tmp_path / "out").as_posix() for path in written) == [
        "My Talk/slide-01.png", "My Talk/slide-01.svg", "My Talk/slide-02.png", "My Talk/slide-02.svg",
    ]
    assert not (tmp_path / "build").exists()


def test_build_is_written_beside_the_deck_as_before(tmp_path: Path) -> None:
    written = DeckKind().export(DECK, tmp_path, "talk", ["pdf", "png"])
    assert sorted(path.relative_to(tmp_path).as_posix() for path in written) == [
        "build/My Talk-01.png", "build/My Talk-02.png", "build/My Talk.pdf",
    ]


def test_a_figure_that_cannot_be_drawn_is_an_empty_box_and_the_export_says_so(tmp_path: Path) -> None:
    protein = {"id": "p", "kind": "protein", "label": "Spike", "properties": {}}
    deck = {**DECK, "slides": [
        *DECK["slides"], {"title": "The spike", "body": [{"figure": {"figure": {"id": "f"}, "nodes": [protein]}}]},
    ]}
    kind = DeckKind()
    (pdf,) = kind.export(deck, tmp_path, "talk", ["pdf"], into=tmp_path / "out")
    assert _pages(pdf) == 3
    # (Its other shapes drawn, the one it can't draw a plain box of its words.)
    assert kind.export_notes == [
        "Slide 3 · Figure: \u201cSpike\u201d is drawn as a plain box: a protein needs its length in residues."
    ]
    # Its slide as exported (and presented) shows no words of what is wrong.
    svgs = kind.export(deck, tmp_path, "talk", ["svg"], into=tmp_path / "svg")
    last = sorted(path for path in svgs if path.suffix == ".svg")[-1].read_text()
    assert "can\u2019t be drawn" not in last and "length" not in last and "The spike" in last


def test_a_slide_of_a_layout_there_is_none_of_is_drawn_and_exported_as_content(tmp_path: Path) -> None:
    quote = {"layout": "quote", "title": "Why it matters",
             "body": [{"quote": "The queue lets the customer stop waiting."}]}
    deck = {**DECK, "slides": [*DECK["slides"], quote]}
    kind = DeckKind()
    drawing = kind.draw(deck, tmp_path)
    while drawing.unfinished:
        drawing = kind.draw(deck, tmp_path)
    page = drawing.pages[-1]
    # Its objects drawn as on a Content slide, not a blank slide with a warning sign.
    assert "The queue lets the customer" in page.svg and "Why it matters" in page.svg
    said = [message for message in drawing.messages if message.where == f"slides[{len(deck['slides']) - 1}].layout"]
    assert [(message.text, message.severity) for message in said] == [
        ("\u201cquote\u201d isn\u2019t a layout: drawn as Content. Choose one from Layout.", "warning")]
    # Exported the same, and said so.
    (pdf,) = kind.export(deck, tmp_path, "talk", ["pdf"], into=tmp_path / "out")
    assert _pages(pdf) == len(deck["slides"])
    number = len(deck["slides"])
    assert kind.export_notes == [f"Slide {number}: \u201cquote\u201d isn\u2019t a layout: drawn as Content."]


def test_shapes_found_wanting_as_they_are_drawn_are_plain_boxes_each_said(tmp_path: Path) -> None:
    nodes = [
        {"id": "p", "kind": "plasmid", "label": "pUC19", "properties": {"length": -5}},
        {"id": "t", "kind": "tree", "label": "Tree", "properties": {"newick": "((A,B"}},
        {"id": "q", "label": "Next"},
    ]
    bad = {"title": "Bad", "body": [{"figure": {"figure": {"id": "f"}, "nodes": nodes}}]}
    deck = {**DECK, "slides": [*DECK["slides"], bad]}
    kind = DeckKind()
    drawing = kind.draw(deck, tmp_path)
    while drawing.unfinished:
        drawing = kind.draw(deck, tmp_path)
    # The rest of the figure is drawn; each shape that can't be is said where it is, to be chosen.
    assert "Next" in drawing.pages[-1].svg and 'data-flexo-talk="invalid"' not in drawing.pages[-1].svg
    assert {message.where for message in drawing.messages if "can\u2019t be drawn yet" in message.text} == {
        "slides[2] f#p:length", "slides[2] f#t:newick"}
    kind.export(deck, tmp_path, "talk", ["pdf"], into=tmp_path / "out")
    assert kind.export_notes == [
        "Slide 3 \u00b7 Figure: \u201cpUC19\u201d is drawn as a plain box: a plasmid of -5 bp is too short to draw."
        " \u201cTree\u201d is drawn as a plain box: the tree's Newick does not read: a ( is never closed."
    ]


def test_a_skipped_slide_is_kept_but_neither_exported_nor_counted_among_the_sections(tmp_path: Path) -> None:
    import pytest

    from flexo_talk.document import DeckDocumentError, deck_from_document

    deck = {**DECK, "slides": [
        {"layout": "agenda"},
        {"layout": "section", "title": "Skipped part", "skip": True},
        {"layout": "section", "title": "Shown part"},
        {"title": "Last", "body": [{"text": "Words"}]},
    ]}
    kind = DeckKind()
    # Drawn to be edited, as Keynote's slide navigator shows a slide skipped.
    drawing = kind.draw(deck, tmp_path, {"settle": True})
    while drawing.unfinished:
        drawing = kind.draw(deck, tmp_path, {"settle": True})
    agenda, skipped, *_ = (page.svg for page in drawing.pages)
    assert "Skipped part" in skipped
    # The agenda lists the sections presented, numbered as they are.
    assert "Shown part" in agenda and "Skipped part" not in agenda
    (pdf,) = kind.export(deck, tmp_path, "talk", ["pdf"], into=tmp_path / "out")
    assert _pages(pdf) == 3
    with pytest.raises(DeckDocumentError, match="skip must be true or false"):
        deck_from_document({**DECK, "slides": [{"title": "T", "skip": "yes"}]}, tmp_path)


def _numbers(svgs: list[str]) -> list[str | None]:
    import re

    found = (re.search(r'id="slide\d+\.number"[^>]*><tspan[^>]*>(\d+)<', svg) for svg in svgs)
    return [match and match[1] for match in found]


def test_the_slides_after_one_skipped_are_numbered_as_they_are_shown(tmp_path: Path) -> None:
    # As Keynote numbers them: the show counts the slides it shows, and the numbers drawn on
    # them, the PDF's and the PowerPoint's agree with it -- no gap where one was skipped.
    deck = {**DECK, "slides": [
        {"title": "One", "body": [{"text": "a"}]},
        {"title": "Two", "skip": True, "body": [{"text": "b"}]},
        {"title": "Three", "body": [{"text": "c"}]},
    ]}
    kind = DeckKind()

    def drawn(document: dict) -> list[str]:
        drawing = kind.draw(document, tmp_path, {"settle": True})
        while drawing.unfinished:
            drawing = kind.draw(document, tmp_path, {"settle": True})
        return [page.svg for page in drawing.pages]

    # The slide skipped has none; the one after it is the second shown.
    assert _numbers(drawn(deck)) == ["1", None, "2"]
    # Shown again, the slides after it are drawn again with their numbers.
    shown = {**deck, "slides": [{key: value for key, value in slide.items() if key != "skip"} for slide in deck["slides"]]}
    assert _numbers(drawn(shown)) == ["1", "2", "3"]
    svgs = sorted(kind.export(deck, tmp_path, "talk", ["svg"], into=tmp_path / "out"))
    assert [path.name for path in svgs] == ["slide-01.svg", "slide-02.svg"]
    assert _numbers([path.read_text(encoding="utf-8") for path in svgs]) == ["1", "2"]
