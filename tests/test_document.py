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


def test_a_figure_written_in_the_deck_is_read_once_for_each_version(tmp_path: Path) -> None:
    figure = {"figure": {"id": "small"}, "nodes": [{"id": "a", "label": "A"}]}
    document = {"deck": {}, "slides": [{"body": [{"figure": figure}]}]}

    def read() -> object:
        return deck_from_document(document, tmp_path).slides[0].regions["body"].blocks[0].figure

    assert read() is read()
    figure["nodes"][0]["label"] = "B"
    assert read().nodes[0].label[0].text == "B"


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


def test_a_theme_file_sets_the_slides_too(tmp_path: Path) -> None:
    from PIL import Image

    Image.new("RGB", (64, 36), "#f3ecdc").save(tmp_path / "paper.png")
    Image.new("RGB", (64, 36), "#101828").save(tmp_path / "night.png")
    (tmp_path / "notebook.yaml").write_text(
        "theme: {name: notebook-test, base: sketch, palette: ['#2b4c9b', '#c0392b']}\n"
        "slides:\n"
        "  look: margin\n"
        "  style: {header: none, body_size: 22}\n"
        "  background: paper.png\n"
        "  title_font: Caveat\n",
        encoding="utf-8",
    )
    document = {"deck": {"theme": "notebook.yaml"}, "slides": [
        {"title": "Paper"}, {"title": "Night", "background": "night.png"}]}
    deck = deck_from_document(document, tmp_path)
    assert deck.look == "margin" and deck.style.header == "none" and deck.style.body_size == 22
    assert deck.style.edge  # the look's, kept where the theme said nothing
    assert deck.title_font == "Caveat" and deck.background == str(tmp_path / "paper.png")
    # What the theme set is the theme's: the document is written back as it was.
    assert deck_document(deck)["deck"] == {"id": "talk", "theme": "notebook.yaml"}
    first, second = (render_slide(deck, slide).svg for slide in deck.slides)
    assert 'id="slide1.paper"' in first and "Caveat" in first
    # Words over a dark picture are set light, judged from the picture itself;
    # and a slide with a backdrop of its own is not covered by the paper.
    assert "#d4d0c8" in second and "#d4d0c8" not in first
    assert 'id="slide2.paper"' not in second and 'id="slide2.backdrop"' in second

    # The deck's own settings win over the theme's.
    mine = {"deck": {"theme": "notebook.yaml", "look": "band", "background": "#ffffff",
                     "style": {"body_size": 18}}, "slides": [{"title": "Mine"}]}
    deck = deck_from_document(mine, tmp_path)
    assert deck.style.header == "band" and deck.style.body_size == 18 and deck.background == "#ffffff"
    assert deck_document(deck)["deck"] == {"id": "talk", **mine["deck"]}
    assert 'id="slide1.paper"' not in render_slide(deck, deck.slides[0]).svg


def test_a_theme_file_says_where_its_slides_section_is_wrong(tmp_path: Path) -> None:
    (tmp_path / "wrong.yaml").write_text(
        "theme: {name: wrong-slides-test, base: paper}\nslides: {look: sideways}\n", encoding="utf-8"
    )
    with pytest.raises(DeckDocumentError, match="sideways"):
        deck_from_document({"deck": {"theme": "wrong.yaml"}, "slides": []}, tmp_path)


def test_a_table_alone_on_its_slide_is_centred(tmp_path: Path) -> None:
    rows = [["Model", "Active"], ["Ours", "38"]]
    alone = {"deck": {}, "slides": [{"title": "T", "body": [{"table": rows}]}]}
    beside = {"deck": {}, "slides": [{"title": "T", "body": [{"text": "Words above"}, {"table": rows}]}]}
    tables = []
    for document in (alone, beside):
        deck = deck_from_document(document, tmp_path)
        from flexo_talk.compose import render_slide as render

        (table,) = render(deck, deck.slides[0]).tables
        tables.append(table)
    style = deck.style
    body_middle = style.width / 2.0
    # Alone: across the slide and down it.
    assert abs(tables[0].x + sum(tables[0].widths) / 2.0 - body_middle) < 1.0
    assert tables[0].y > tables[1].y + 40
    # Under words, a table stands flush with them.
    assert abs(tables[1].x - style.margin) < 1.0


def _deck_with_figures() -> dict:
    figure = {
        "figure": {"id": "inline"},
        "nodes": [{"id": "x", "kind": "text", "label": "x"}, {"id": "m", "label": "Model"}],
        "edges": [{"from": "x", "to": "m"}],
    }
    return {
        "schema_version": 1,
        "deck": {"id": "talk"},
        "slides": [
            {"title": "Here", "layout": "two-columns", "left": [{"text": "Words"}], "right": [{"figure": figure}]},
            {"title": "A file", "layout": "figure", "body": [{"figure": "model.yaml"}]},
            {"title": "Python", "body": [{"figure": "figures.py:model"}]},
        ],
    }


def test_a_figure_written_in_the_deck_is_edited_where_it_is_written(tmp_path: Path) -> None:
    kind = DeckKind()
    document = _deck_with_figures()
    at = {"slide": 0, "region": "right", "index": 0}
    read = kind.act(document, {"do": "figure", "at": at, "edit": {"do": "read"}}, tmp_path)
    assert [node["id"] for node in read["model"]["nodes"]] == ["x", "m"] and read["document"] == document
    edit = {"do": "add", "kind": "mlp", "after": "m", "source": "m"}
    made = kind.act(document, {"do": "figure", "at": at, "edit": edit}, tmp_path)
    assert made["select"] == ["mlp"]
    figure = made["document"]["slides"][0]["right"][0]["figure"]
    assert {"from": "m", "to": "mlp"} in figure["edges"] and len(figure["nodes"]) == 3
    assert len(document["slides"][0]["right"][0]["figure"]["nodes"]) == 2  # the one given is left alone
    deck = deck_from_document({**made["document"], "slides": made["document"]["slides"][:1]}, tmp_path)
    assert render_slide(deck, deck.slides[0]).svg


def test_a_figure_file_on_a_slide_is_edited_in_its_file(tmp_path: Path) -> None:
    from flexo.studio.figure_kind import NEW_FIGURE

    (tmp_path / "model.yaml").write_text(NEW_FIGURE, encoding="utf-8")
    kind = DeckKind()
    document = _deck_with_figures()
    at = {"slide": 1, "region": "body", "index": 0}
    kind.act(document, {"do": "figure", "at": at, "edit": {"do": "read"}}, tmp_path)
    assert (tmp_path / "model.yaml").read_text() == NEW_FIGURE  # reading writes nothing
    rename = {"do": "rename", "id": "encoder", "to": "backbone"}
    result = kind.act(document, {"do": "figure", "at": at, "edit": rename}, tmp_path)
    assert result["file"] == "model.yaml" and result["document"] is document
    text = (tmp_path / "model.yaml").read_text()
    assert text.startswith("# A flexo figure") and "id: backbone" in text and "to: backbone" in text


def test_a_figure_made_in_python_or_gone_is_not_edited_on_its_slide(tmp_path: Path) -> None:
    from flexo.studio.figure_edit import EditError

    kind = DeckKind()
    document = _deck_with_figures()
    def read(slide: int, region: str, index: int) -> None:
        at = {"slide": slide, "region": region, "index": index}
        kind.act(document, {"do": "figure", "at": at, "edit": {"do": "read"}}, tmp_path)

    with pytest.raises(EditError, match="Python file"):
        read(2, "body", 0)
    with pytest.raises(EditError, match="gone"):
        read(0, "right", 5)


def test_the_studio_offers_the_figure_editor_for_figures_on_slides() -> None:
    parts = DeckKind().catalog()["figure_editor"]["parts"]
    assert {"block", "protein", "plasmid", "attention"} <= set(parts)


def test_a_picture_in_a_figure_written_in_the_deck_is_found_beside_the_deck(tmp_path: Path) -> None:
    (tmp_path / "logo.svg").write_text(
        '<svg xmlns="http://www.w3.org/2000/svg" width="20" height="20"><circle cx="10" cy="10" r="8"/></svg>'
    )
    figure = {"figure": {"id": "pic"}, "nodes": [{"id": "logo", "kind": "image", "properties": {"source": "logo.svg"}}]}
    document = {"schema_version": 1, "deck": {"id": "t"}, "slides": [{"title": "Logo", "body": [{"figure": figure}]}]}
    deck = deck_from_document(document, tmp_path)
    assert render_slide(deck, deck.slides[0]).svg
