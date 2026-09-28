"""A deck document makes the deck its Python makes, says where it is wrong, and is drawn
slide by slide in the studio."""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest
import yaml

from flexo_talk import Deck
from flexo_talk.cli import main
from flexo_talk.compose import render_slide
from flexo_talk.document import (
    DeckDocumentError,
    deck_document,
    deck_from_document,
    dump_document,
    read_deck,
)
from flexo_talk.studio import DeckKind

ROOT = Path(__file__).resolve().parents[1]


def _demo() -> Deck:
    spec = importlib.util.spec_from_file_location("demo", ROOT / "examples" / "demo.py")
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.talk()


def _small() -> dict:
    return {
        "deck": {"id": "small", "look": "band", "footer": "A footer", "style": {"body_size": 22}},
        "slides": [
            {"layout": "title", "title": "A talk", "subtitle": "About things", "author": "Ada"},
            {"layout": "section", "title": "Part one"},
            {"title": "Points", "body": [{"bullets": ["One", "Two", ["under two"]], "numbered": True}],
             "notes": "Say it slowly", "footnotes": ["[1] A source"]},
            {"layout": "two-columns", "title": "Both", "split": 0.4,
             "left": [{"text": "Words with $x$", "align": "middle"}],
             "right": [{"table": [["A", "B"], ["x", 1.5]]}]},
            {"layout": "columns", "title": "Three", "widths": [2, 1, 1],
             "columns": [[{"stats": [{"value": "93%", "label": "right"}]}], [{"quote": "Q", "by": "W"}],
                         [{"callout": "C", "title": "T", "colour": "accent2"}]]},
            {"layout": "statement", "words": "One [thing]{accent}.", "by": "Me"},
            {"layout": "agenda"},
            {"layout": "blank", "body": [{"code": "x = 1\n# a comment"}]},
        ],
    }


def test_the_demo_as_a_document_draws_the_same_slides() -> None:
    deck = _demo()
    text = dump_document(deck_document(deck))
    again = deck_from_document(yaml.safe_load(text), ROOT / "examples")
    assert len(again.slides) == len(deck.slides)
    for original, copy in zip(deck.slides, again.slides, strict=True):
        assert render_slide(deck, original).svg == render_slide(again, copy).svg, original.id


def test_a_document_writes_itself_back_as_it_was_read() -> None:
    document = {"schema_version": 1, **_small()}
    deck = deck_from_document(document)
    assert deck.style.header == "band" and deck.style.body_size == 22
    assert deck_document(deck) == document


def test_words_over_several_lines_are_written_as_blocks() -> None:
    text = dump_document({"deck": {}, "slides": [{"body": [{"code": "a\nb"}]}]})
    assert "code: |-" in text


@pytest.mark.parametrize(
    ("slide", "where", "words"),
    [
        ({"layout": "sideways"}, "slides[0].layout", "unknown layout"),
        ({"title": "T", "colour": "red"}, "slides[0]", "unknown key colour"),
        ({"body": [{"table": "not rows"}]}, "slides[0].body[0] (table)", "list of rows"),
        ({"body": [{"text": "a", "bullets": ["b"]}]}, "slides[0].body[0]", "names text, bullets"),
        ({"body": [{"image": "nowhere.png"}]}, "slides[0].body[0] (image)", "no file nowhere.png"),
        ({"layout": "columns", "columns": [[], []], "widths": [1]}, "slides[0].widths", "one share"),
        ({"body": [{"callout": "c", "colour": "red"}]}, "slides[0].body[0] (callout)", "accent"),
    ],
)
def test_a_wrong_document_says_where(tmp_path: Path, slide: dict, where: str, words: str) -> None:
    with pytest.raises(DeckDocumentError) as caught:
        deck_from_document({"deck": {}, "slides": [slide]}, tmp_path)
    assert caught.value.where == where
    assert words in caught.value.message


def test_a_wrong_slide_stands_aside_when_errors_are_collected(tmp_path: Path) -> None:
    errors: list[DeckDocumentError] = []
    document = {"deck": {}, "slides": [{"title": "Fine"}, {"body": [{"table": 3}]}, {"title": "Also fine"}]}
    deck = deck_from_document(document, tmp_path, errors=errors)
    assert [slide.index for slide in deck.slides] == [1, 2, 3]
    assert deck.slides[1].layout == "blank"
    assert [error.where for error in errors] == ["slides[1].body[0] (table)"]


def test_figures_and_plots_named_by_python_are_made_when_drawn(tmp_path: Path) -> None:
    pytest.importorskip("matplotlib")
    (tmp_path / "made.py").write_text(
        "import flexo\n"
        "calls = []\n"
        "def model():\n"
        "    calls.append('figure')\n"
        "    figure = flexo.Figure('model')\n"
        "    x = figure.root.text('x', 'Input')\n"
        "    figure.root.block('f', label='Model', input=x)\n"
        "    return figure\n"
        "def curve(deck):\n"
        "    import matplotlib.pyplot as plt\n"
        "    calls.append('plot')\n"
        "    figure, axes = plt.subplots()\n"
        "    axes.plot([0, 1], [1, 0])\n"
        "    return figure\n",
        encoding="utf-8",
    )
    document = {"deck": {}, "slides": [{"layout": "two-columns", "left": [{"figure": "made.py:model"}],
                                        "right": [{"plot": "made.py:curve"}]}]}
    deck = deck_from_document(document, tmp_path)
    from flexo_talk.document import import_file

    module = import_file(tmp_path / "made.py")
    assert module.calls == []
    svg = render_slide(deck, deck.slides[0]).svg
    assert module.calls == ["figure", "plot"]
    assert "slide1.left.0" in svg and "slide1.right.0" in svg


def test_the_command_line_builds_and_converts(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    target = tmp_path / "demo.yaml"
    assert main(["convert", str(ROOT / "examples" / "demo.py"), "-o", str(target)]) == 0
    assert read_deck(target).id == "demo"
    assert main(["build", str(target), "-o", str(tmp_path / "out"), "--formats", "svg"]) == 0
    assert len(list((tmp_path / "out").glob("demo-*.svg"))) == 5
    assert "ok" in capsys.readouterr().out


def test_the_studio_draws_the_slide_in_focus_first(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    import flexo_talk.studio as studio

    kind = DeckKind()
    document = {"schema_version": 1, **_small()}
    monkeypatch.setattr(studio, "BUDGET", 0.0)
    first = kind.draw(document, tmp_path, {"focus": 4})
    drawn = [page.id for page in first.pages if not page.pending]
    assert drawn == ["slide5"] and first.unfinished
    while (drawing := kind.draw(document, tmp_path, {"focus": 4})).unfinished:
        pass
    assert all(page.svg for page in drawing.pages)
    assert drawing.info["palette"]["accent"].startswith("#")
    # Nothing changed: nothing is drawn again, and every page is the same.
    again = kind.draw(document, tmp_path, {"focus": 0})
    assert [page.svg for page in again.pages] == [page.svg for page in drawing.pages]


def test_the_studio_reports_a_wrong_slide_on_its_page(tmp_path: Path) -> None:
    kind = DeckKind()
    document = {"deck": {}, "slides": [{"title": "Fine"}, {"body": [{"stats": []}]}]}
    drawing = kind.draw(document, tmp_path, {})
    assert [page.extra["error"] for page in drawing.pages] == [False, True]
    (message,) = [message for message in drawing.messages if message.severity == "error"]
    assert message.page == "slide2" and message.where == "slides[1].body[0] (stats)"


def test_the_studio_catalog_offers_every_look_layout_and_block() -> None:
    catalog = DeckKind().catalog()
    assert {look["name"] for look in catalog["looks"]} == {"classic", "band", "editorial", "keynote", "margin"}
    assert "two-columns" in catalog["slide_keys"] and "split" in catalog["slide_keys"]["two-columns"]
    header = next(field for field in catalog["style"] if field["name"] == "header")
    assert header["kind"] == "choice" and header["choices"] == ["rule", "band", "line", "none"]


def test_the_studio_names_what_a_change_did_slide_by_slide() -> None:
    kind = DeckKind()
    before = {"deck": {"look": "classic"}, "slides": [
        {"title": "A", "body": [{"text": "long enough words to be recognised"}]}, {"title": "B"}, {"title": "C"}]}
    after = {"deck": {"look": "band"}, "slides": [
        {"title": "A!", "body": [{"text": "long enough words to be recognised"}]}, {"title": "New"}, {"title": "B"}]}
    notes = kind.describe(before, after)
    assert [note["text"] for note in notes] == [
        "changed the look", "edited slide 1: the title", "added slide 2 (New)", "removed slide 3",
    ]
    assert notes[1]["where"] == {"page": 1, "label": "Slide 1"}


def test_an_agent_gets_a_guide_and_a_quick_check() -> None:
    kind = DeckKind()
    guide = kind.guide()
    assert "two-columns" in guide and "bullets" in guide and "Look at each slide" in guide
    assert kind.check({"deck": {}, "slides": [{"body": [{"table": 1}]}]}, ROOT) == [
        "slides[0].body[0] (table): a table is a list of rows, each a list of cells"
    ]
    document = {"schema_version": 1, **_small()}
    assert kind.parse(kind.dump(document)) == document


def test_the_theme_editor_shows_a_theme_on_slides_and_on_a_deck(tmp_path: Path) -> None:
    from flexo_talk.studio import SlideSamples

    samples = SlideSamples().pages("paper", tmp_path, {})
    assert len(samples) == 5 and "<svg" in samples[1][2]()
    (tmp_path / "talk.yaml").write_text(dump_document({"schema_version": 1, **_small()}), encoding="utf-8")
    own = SlideSamples().pages("tikz", tmp_path, {"deck": "talk.yaml"})
    assert [label for _, label, _ in own][:2] == ["A talk", "Part one"]


def test_a_deck_redraws_when_its_theme_file_changes(tmp_path: Path) -> None:
    import time

    theme = tmp_path / "lab.yaml"
    theme.write_text("theme: {name: lab-deck, base: paper, palette: ['#1d4e89']}\n", encoding="utf-8")
    stats = {"stats": [{"value": "9", "label": "x"}]}
    document = {"deck": {"theme": "lab.yaml"}, "slides": [{"title": "A", "body": [stats]}]}
    kind = DeckKind()
    first = kind.draw(document, tmp_path, {})
    time.sleep(0.01)
    theme.write_text("theme: {name: lab-deck, base: paper, palette: ['#8b1e3f']}\n", encoding="utf-8")
    second = kind.draw(document, tmp_path, {})
    assert first.pages[0].svg != second.pages[0].svg
    assert theme.resolve() in second.files
