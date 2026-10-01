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


def test_words_read_on_every_backdrop_and_panel() -> None:
    from flexo.colour import contrast

    from flexo_talk.compose import _code_paints, _slide_palette

    for colour in ("#888888", "#6b6b6b", "#1b2a41", "#f0f0f0"):
        deck = Deck("g")
        palette = _slide_palette(deck, deck.slide("T", background=colour))
        assert contrast(palette.get("muted-ink"), colour) >= 4.5, colour
    for theme in ("swiss", "bauhaus", "midcentury", "paper", "dark"):
        panel, _, ink, muted = _code_paints(Deck("c", theme=theme).palette)
        assert contrast(ink, panel) >= 7.0 and contrast(muted, panel) >= 4.5, theme


def test_an_accent_word_in_a_band_title_is_lifted_off_the_band() -> None:
    import re

    from flexo.colour import contrast

    from flexo_talk.deck import accent_field

    deck = Deck("b", look="band")
    deck.slide("Title with [accent words]{accent}").text("x")
    (slide,) = deck.render()
    field = accent_field(deck.palette)
    title = re.search(r'id="slide1\.title".*?</text>', slide.svg, re.S).group(0)
    fills = set(re.findall(r'fill="(#[0-9a-fA-F]{6})"', title))
    assert fills and all(contrast(fill, field) >= 3.0 for fill in fills)


def test_light_words_over_a_shaded_picture_and_a_word_when_they_will_not_read(tmp_path: Path) -> None:
    from PIL import Image

    bright = tmp_path / "bright.png"  # a dark street under a bright sky
    picture = Image.new("RGB", (64, 64), "#f2f2f2")
    picture.paste((30, 30, 30), (0, 32, 64, 64))
    picture.save(bright)
    shaded = Deck("p")
    shaded.title("Over a photograph", background=str(bright), shade=0.5)
    (slide,) = shaded.render()
    assert slide.diagnostics == [] and "#f7f5f0" in slide.svg  # light words, and they read
    faint = Deck("p")
    faint.title("Over a photograph", background=str(bright), shade=0.2)
    assert any("a shade of" in line for line in faint.render()[0].diagnostics)


def test_a_wide_table_wraps_its_cells_to_stay_on_the_slide(tmp_path: Path) -> None:
    deck = Deck("t")
    deck.slide("Long cells").table([
        ["Method", "Notes", "Score"],
        ["Ours", "A long description of the method that goes on and on " * 3, "0.93"],
    ])
    deck.slide("Wide").table([[f"Column {i}" for i in range(14)], [f"value {i * 1234}" for i in range(14)]])
    first, second = deck.render()
    (table,) = first.tables
    assert sum(table.widths) <= deck.style.width - 2 * deck.style.margin + 0.5
    assert table.heights[1] > table.heights[0] * 1.5  # the long cell wrapped
    assert first.diagnostics == []
    assert sum(second.tables[0].widths) <= deck.style.width - 2 * deck.style.margin + 0.5
    assert any("too wide for its place" in line for line in second.diagnostics)


def test_a_long_code_line_is_set_smaller_then_wrapped_and_said() -> None:
    from flexo_talk.compose import _Canvas, _code_lines

    deck = Deck("c")
    long = "result = some_function_with_a_long_name(argument_one, argument_two, keyword=value) " * 2
    slide = deck.slide("Code")
    slide.code(f"def f():\n    {long}\n    return result")
    (rendered,) = deck.render()
    assert any("too long for the slide, wrapped" in line for line in rendered.diagnostics)
    canvas = _Canvas(deck, slide)
    _, lines = _code_lines(canvas, slide.body.blocks[0], 400.0)
    assert len(lines) > 3 and all(line.startswith("        ") for line, _ in lines[2:-1])


def test_a_gallery_fits_the_height_of_its_place(tmp_path: Path) -> None:
    import re

    from PIL import Image

    pictures = []
    for index in range(4):
        path = tmp_path / f"p{index}.png"
        Image.new("RGB", (400, 400), "#3366aa").save(path)
        pictures.append((str(path), f"Person {index}"))
    deck = Deck("g")
    deck.slide("People").gallery(pictures, columns=2, crop="circle")
    (slide,) = deck.render()
    placed = re.findall(r'<image[^>]* y="([\d.]+)"[^>]* height="([\d.]+)"', slide.svg)
    bottoms = [float(y) + float(h) for y, h in placed]
    assert bottoms and max(bottoms) <= deck.style.height - deck.style.margin + 1
    assert not any("words do not fit" in line for line in slide.diagnostics)


def test_a_phone_photograph_stands_upright_and_cmyk_reads(tmp_path: Path) -> None:
    import base64
    import io

    from flexo.artwork import load_artwork
    from PIL import Image

    turned = tmp_path / "turned.jpg"
    exif = Image.Exif()
    exif[0x0112] = 6
    Image.new("RGB", (300, 200), "#cc0000").save(turned, exif=exif)
    art = load_artwork("p", str(turned))
    assert (art.width, art.height) == (200 * 0.75, 300 * 0.75)
    upright = Image.open(io.BytesIO(base64.b64decode(art.data_uri.split(",", 1)[1])))
    assert upright.size == (200, 300)
    cmyk = tmp_path / "cmyk.jpg"
    Image.new("CMYK", (40, 40), (0, 255, 255, 0)).save(cmyk)
    shown = Image.open(io.BytesIO(base64.b64decode(load_artwork("c", str(cmyk)).data_uri.split(",", 1)[1])))
    assert shown.mode == "RGB"
