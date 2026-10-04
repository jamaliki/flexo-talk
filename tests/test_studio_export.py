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
        "Slide 3 · Figure: \u201cSpike\u201d is drawn as a plain box: it can\u2019t be drawn as it is."
    ]
    # Its slide as exported (and presented) shows no words of what is wrong.
    svgs = kind.export(deck, tmp_path, "talk", ["svg"], into=tmp_path / "svg")
    last = sorted(path for path in svgs if path.suffix == ".svg")[-1].read_text()
    assert "can\u2019t be drawn" not in last and "length" not in last and "The spike" in last
