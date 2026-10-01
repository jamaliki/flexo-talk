"""What a deck does with what it should not be given: each is said in words, and the
deck is still built (or refused) without a traceback, a hang, or a file out of place."""

from __future__ import annotations

import time
from pathlib import Path

import pytest

from flexo_talk import Deck
from flexo_talk.cli import main
from flexo_talk.deck import DeckStyle
from flexo_talk.document import DeckDocumentError, deck_from_document, load_document
from flexo_talk.export import file_stem


@pytest.mark.parametrize(
    ("identifier", "stem"),
    [("talk", "talk"), ("../../escaped", "escaped"), ("", "deck"), (None, "deck"), ("sub/dir", "sub-dir"),
     ("..", "deck"), (".hidden", "hidden")],
)
def test_a_deck_id_names_its_files_in_the_folder_they_are_written_to(identifier: object, stem: str) -> None:
    assert file_stem(identifier) == stem


def test_a_deck_id_cannot_write_outside_the_output_folder(tmp_path: Path) -> None:
    out = tmp_path / "a" / "b"
    deck = Deck("../../escaped")
    deck.slide("S").text("x")
    result = deck.build(out, formats=("pdf", "png"))
    assert result.pdf.parent == out and all(path.parent == out for path in result.pngs)


@pytest.mark.parametrize(
    ("changes", "said"),
    [({"width": 1e7}, r"width is 1e\+07"), ({"body_size": "big"}, "body_size is 'big'"),
     ({"margin": float("inf")}, "margin is inf"), ({"header": "fancy"}, "one of rule, band"),
     ({"numbers": "no"}, "true or false"), ({"margin": 300}, "leaves no room")],
)
def test_a_deck_style_says_what_is_wrong_with_it(changes: dict, said: str) -> None:
    with pytest.raises(ValueError, match=said):
        DeckStyle(**changes)


@pytest.mark.parametrize(
    ("make", "said"),
    [(lambda s: s.gallery([]), "at least one picture"),
     (lambda s: s.text("x", align="sideways"), "one of start, middle, end"),
     (lambda s: s.text("x", size="big"), "size is 'big'"),
     (lambda s: s.stats("93%"), r"a \(value, label\) pair"),
     (lambda s: s.bullets("a", numbered="no"), "numbered is 'no'"),
     (lambda s: s.image("x.png", width="wide"), "width is 'wide'"),
     (lambda s: s.text("x", colour="#zzzzzz"), "hex digits"),
     (lambda s: s.table(["ab", "cd"]), "a list of rows")],
)
def test_a_block_says_what_is_wrong_with_its_settings(make, said: str) -> None:
    with pytest.raises(ValueError, match=said):
        make(Deck("v").slide("S"))


def test_friendly_settings_are_taken() -> None:
    slide = Deck("v").slide("S")
    slide.text("x", align="centre").bullets(2019, 2020, ["nested", 3])
    assert slide.body.blocks[0].align == "middle"


def test_a_slides_settings_are_checked() -> None:
    for options, said in (({"split": "half"}, "split is 'half'"), ({"shade": 5}, "shade is 5"),
                          ({"layout": "columns", "widths": [0, 0]}, "width is 0"),
                          ({"background": "#zz"}, "hex digits"), ({"dark": "no"}, "dark is 'no'")):
        with pytest.raises(ValueError, match=said):
            Deck("v").slide("S", **options)


def test_emoji_are_left_out_of_the_drawing_and_said_once_a_slide(tmp_path: Path) -> None:
    deck = Deck("e", footer="Footer \N{PARTY POPPER}")
    slide = deck.slide("Love ❤️ it")
    slide.text("a️ b \N{GRINNING FACE} c").bullets("x \N{PARTY POPPER}", ["nested \N{WAVING HAND SIGN}"])
    deck.slide("T").table([["a \N{GRINNING FACE}", "b"]])
    result = deck.build(tmp_path, formats=("svg", "pdf", "pptx"))
    first = [line for line in result.diagnostics if line.startswith("slide1:")]
    assert len(first) == 1 and "\N{GRINNING FACE}" in first[0] and "\N{PARTY POPPER}" in first[0]
    assert "️" not in first[0]  # a variation selector is never "missing"


def test_a_list_of_only_nested_items_can_be_revealed_and_numbered(tmp_path: Path) -> None:
    for options in ({"reveal": True}, {"numbered": True}, {"reveal": True, "numbered": True}):
        deck = Deck("n")
        deck.slide("S").bullets(["only", "nested"], **options)
        deck.build(tmp_path, formats=("pdf", "pptx"))


def test_words_too_long_for_any_slide_are_cut_and_said_quickly(tmp_path: Path) -> None:
    deck = Deck("big")
    deck.slide("W" * 200_000).text("y " * 50_000)
    start = time.monotonic()
    result = deck.build(tmp_path, formats=("svg",))
    assert time.monotonic() - start < 30
    assert any("200,000 characters cut to 20,000" in line for line in result.diagnostics)


@pytest.mark.parametrize(
    ("name", "text", "said"),
    [("dup.yaml", "deck: {id: a}\ndeck: {id: b}\nslides: []\n", "'deck' is written twice"),
     ("tab.yaml", "deck:\n\tid: a\nslides: []\n", "a tab"),
     ("bad.json", '{"deck": {"id": "a"},, }', "line 1, column"),
     ("python.yaml", "deck: !!python/object/apply:os.system ['true']\nslides: []\n", "constructor"),
     ("half.json", '{"deck": {"id": "\\ud800"}, "slides": []}', "broken character"),
     ("bomb.yaml", "a: &a [x,x,x,x,x,x,x,x,x,x]\nb: &b [*a,*a,*a,*a,*a,*a,*a,*a,*a,*a]\n"
      "c: &c [*b,*b,*b,*b,*b,*b,*b,*b,*b,*b]\nd: &d [*c,*c,*c,*c,*c,*c,*c,*c,*c,*c]\n"
      "e: &e [*d,*d,*d,*d,*d,*d,*d,*d,*d,*d]\nf: &f [*e,*e,*e,*e,*e,*e,*e,*e,*e,*e]\n"
      "g: [*f,*f,*f,*f,*f,*f,*f,*f,*f,*f]\n", "more parts")],
)
def test_a_document_file_that_cannot_be_read_says_why(tmp_path: Path, name: str, text: str, said: str) -> None:
    path = tmp_path / name
    path.write_text(text, encoding="utf-8")
    with pytest.raises(DeckDocumentError, match=said):
        load_document(path)


def test_a_document_is_read_as_yaml_1_2_reads_it(tmp_path: Path) -> None:
    path = tmp_path / "deck.yaml"
    path.write_text(
        "deck: {id: a, style: {width: 1.2e3}}\nslides:\n- title: yes\n  body: [{text: 012}, {text: 2026-10-01}]\n"
    )
    document = load_document(path)
    assert document["slides"][0]["title"] == "yes"
    assert document["slides"][0]["body"] == [{"text": 12}, {"text": "2026-10-01"}]
    assert document["deck"]["style"]["width"] == 1200.0
    (tmp_path / "bom.json").write_bytes(b'\xef\xbb\xbf{"deck": {}, "slides": []}')
    assert load_document(tmp_path / "bom.json") == {"deck": {}, "slides": []}


def test_a_document_says_where_a_setting_is_wrong(tmp_path: Path) -> None:
    def said(document: dict) -> str:
        with pytest.raises(DeckDocumentError) as caught:
            deck_from_document(document, tmp_path).render()
        return str(caught.value)

    assert said({"deck": {"style": {"width": "wide"}}, "slides": []}).startswith("deck.style: width is 'wide'")
    assert said({"slides": [{"shade": "dark"}]}).startswith("slides[0]: shade is 'dark'")
    assert said({"slides": [{"footnotes": {"a": 1}}]}).startswith("slides[0].footnotes:")
    assert said({"slides": [{"body": [{"text": "x", "align": "sideways"}]}]}).startswith("slides[0].body[0] (text)")
    built = deck_from_document({"deck": {"footer": None, "id": None}, "slides": [{"title": "x"}]}, tmp_path)
    assert built.id == "talk" and built.footer == ""


def test_the_command_line_says_every_failure_in_words(tmp_path: Path, capsys: pytest.CaptureFixture) -> None:
    (tmp_path / "boom.py").write_text("from flexo_talk import Deck\n\ndef talk():\n    return 1 / 0\n")
    (tmp_path / "fig.yaml").write_text("deck: {id: x}\nslides:\n- body: [{figure: figs.py:nosuch}]\n")
    (tmp_path / "figs.py").write_text("def other():\n    pass\n")
    assert main(["build", str(tmp_path / "boom.py"), "-o", str(tmp_path / "out")]) == 1
    error = capsys.readouterr().err
    assert "boom.py, line 4, in talk: ZeroDivisionError: division by zero" in error and "Traceback" not in error
    assert main(["build", str(tmp_path / "fig.yaml"), "-o", str(tmp_path / "out")]) == 1
    assert "slides[0].body[0] (figure): figs.py has no function nosuch" in capsys.readouterr().err
    with pytest.raises(SystemExit, match="no such file"):
        main(["build", str(tmp_path / "missing.yaml")])


@pytest.mark.parametrize("theme", ["paper", "dark", "swiss", "bauhaus", "print", "archive", "rams", "midcentury"])
def test_every_theme_gives_a_plot_six_colours_told_apart(theme: str) -> None:
    from flexo.colour import hue_distance

    colours = Deck("t", theme=theme).plot_style()["axes.prop_cycle"].by_key()["color"]
    assert len(colours) == 6 and len(set(colours)) == 6
    assert all(hue_distance(a, b) > 0.03 for index, a in enumerate(colours) for b in colours[index + 1:])


def test_a_plot_and_a_code_panel_on_a_dark_slide_of_a_light_deck_take_the_slides_paints(tmp_path: Path) -> None:
    import matplotlib.pyplot as plt

    deck = Deck("bg")
    with deck.plotting():
        figure, axes = plt.subplots()
        axes.bar([1, 2], [3, 4], yerr=[0.5, 0.5])
        axes.set_title("Words")
    slide = deck.slide("Dark", background="#1b2a41")
    slide.plot(figure)
    deck.slide("Code", background="#1b2a41").code("x = 1")
    first, second = deck.render()
    ink = deck.palette.get("ink").lower()
    assert ink not in first.svg.lower() and "#000000" not in first.svg  # words light, error bars too
    panel = deck.palette.get("tone-1-fill").lower()
    assert panel not in second.svg.lower()
