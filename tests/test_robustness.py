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
    [({"width": 1e7}, r"width must be between 72 and 4032, not 1e\+07\."),
     ({"body_size": "big"}, "body_size must be a number from 1 to 400, not 'big'"),
     ({"margin": float("inf")}, "margin must be a number from 0 to 2016, not inf"),
     ({"header": "fancy"}, "one of rule, band"), ({"numbers": "no"}, "true or false, not 'no'"),
     ({"margin": 300}, "leaves no room")],
)
def test_a_deck_style_says_what_is_wrong_with_it(changes: dict, said: str) -> None:
    with pytest.raises(ValueError, match=said):
        DeckStyle(**changes)


@pytest.mark.parametrize(
    ("make", "said"),
    [(lambda s: s.gallery([]), "at least one picture"),
     (lambda s: s.text("x", align="sideways"), "one of start, middle, end"),
     (lambda s: s.text("x", size="big"), r"size must be a number, such as 20 \(points\), not 'big'"),
     (lambda s: s.stats("93%"), r"a \(value, label\) pair"),
     (lambda s: s.bullets("a", numbered="no"), "numbered must be true or false, not 'no'"),
     (lambda s: s.image("x.png", width="wide"), r"width must be a number, such as 300 \(points\), not 'wide'"),
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
    for options, said in (({"split": "half"}, "split must be a number, such as 0.5 .*, not 'half'"),
                          ({"shade": 5}, "shade must be between 0 and 1, not 5"),
                          ({"layout": "columns", "widths": [0, 0]}, "column width must be between 0.01 and 100, not 0"),
                          ({"background": "#zz"}, "hex digits"),
                          ({"dark": "no"}, "dark must be true or false, not 'no'")):
        with pytest.raises(ValueError, match=said):
            Deck("v").slide("S", **options)


def test_emoji_are_left_out_of_the_drawing_and_said_once_a_slide(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # As on a machine with no font that has them: GNU Unifont, where installed, has
    # outlines for every emoji.
    monkeypatch.setattr("flexo.fonts.family_covering", lambda characters: None)
    monkeypatch.setattr("flexo.text.family_covering", lambda characters: None)
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
    assert any("Text shortened from 200,000 to 20,000 characters" in line for line in result.diagnostics)


@pytest.mark.parametrize(
    ("name", "text", "said"),
    [("dup.yaml", "deck: {id: a}\ndeck: {id: b}\nslides: []\n", "duplicate key 'deck'"),
     ("tab.yaml", "deck:\n\tid: a\nslides: []\n", "a tab"),
     ("bad.json", '{"deck": {"id": "a"},, }', "line 1, column"),
     ("python.yaml", "deck: !!python/object/apply:os.system ['true']\nslides: []\n", "constructor"),
     ("half.json", '{"deck": {"id": "\\ud800"}, "slides": []}', "invalid character"),
     ("bomb.yaml", "a: &a [x,x,x,x,x,x,x,x,x,x]\nb: &b [*a,*a,*a,*a,*a,*a,*a,*a,*a,*a]\n"
      "c: &c [*b,*b,*b,*b,*b,*b,*b,*b,*b,*b]\nd: &d [*c,*c,*c,*c,*c,*c,*c,*c,*c,*c]\n"
      "e: &e [*d,*d,*d,*d,*d,*d,*d,*d,*d,*d]\nf: &f [*e,*e,*e,*e,*e,*e,*e,*e,*e,*e]\n"
      "g: [*f,*f,*f,*f,*f,*f,*f,*f,*f,*f]\n", "more than 2,000,000 items")],
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

    assert said({"deck": {"style": {"width": "wide"}}, "slides": []}) == (
        "deck.style.width: width must be a number from 72 to 4032, not 'wide'."
    )
    assert said({"slides": [{"shade": "dark"}]}) == (
        "slides[0].shade: shade must be a number, such as 0.4 (how much a picture is darkened), not 'dark'."
    )
    assert said({"slides": [{"footnotes": {"a": 1}}]}).startswith("slides[0].footnotes:")
    assert said({"slides": [{"body": [{"text": "x", "align": "sideways"}]}]}).startswith("slides[0].body[0] (text)")
    built = deck_from_document({"deck": {"footer": None, "id": None}, "slides": [{"title": "x"}]}, tmp_path)
    assert built.id == "talk" and built.footer == ""


@pytest.mark.parametrize(
    ("document", "said"),
    [
        ({"deck": {"palette": 123}}, "deck.palette: palette must be a palette name or a list of #rrggbb colours, "
         "not 123."),
        ({"deck": {"palette": "nosuch"}}, 'deck.palette: Unknown palette "nosuch"'),
        ({"deck": {"font": 123}}, "deck.font: font must be a font family name, such as IBM Plex Sans, not 123."),
        ({"deck": {"look": ["band"]}}, "deck.look: look must be one of classic, band, editorial, keynote, margin, "
         "not ['band']."),
        ({"deck": {"sketch": "very"}}, "deck.sketch: sketch must be true (for a hand-drawn look) or a mapping of "
         "roughness, passes, fill, paper and seed, not 'very'."),
        ({"deck": {"conventions": "straight"}}, "deck.conventions: conventions must be a mapping of flexo "
         "conventions, such as {lines: straight}, not 'straight'."),
        ({"deck": {"conventions": {"nosuch": 1}}}, "deck.conventions: unknown convention nosuch"),
        ({"deck": {"background": 5}}, "deck.background: background must be true (the theme's page colour), "
         "false, a #rrggbb colour or a picture file, not 5."),
        ({"deck": {"background": "#zzzzzz"}}, "deck.background: background must be a colour written as #rgb or "
         "#rrggbb in hex digits, not '#zzzzzz'."),
        ({"deck": {"footer": ["a"]}}, "deck.footer: footer must be text, not ['a']."),
        ({"deck": {"style": {"title_role": "accent"}}}, "deck.style.title_role: title_role must be a palette role "
         "(such as ink, muted-ink or tone-1-stroke), not 'accent'."),
        ({"slides": [{"title": True}]}, "slides[0].title: title must be text, not yes/no (true)."),
        ({"slides": [{"layout": "two-columns", "split": "half"}]}, "slides[0].split: split must be a number, "
         "such as 0.5 (the left column's share of the width), not 'half'."),
        ({"slides": [{"background": 5}]}, "slides[0].background: background must be a #rrggbb colour or a "
         "picture file, not 5."),
        ({"slides": [{"footnotes": [True]}]}, "slides[0].footnotes: footnotes must be text or a list of text."),
        ({"slides": [{"body": [{"text": "a", "colour": "red"}]}]}, "(text): colour must be accent (accent2, …), "
         "muted, ink or a #rrggbb colour, not 'red'."),
        ({"slides": [{"body": [{"text": True}]}]}, "(text): A text block must contain text, not yes/no (true)."),
        ({"slides": [{"body": [{"table": [[{"a": 1}, [1, 2]]]}]}]}, "(table): A table cell must be text, "
         "not {'a': 1}."),
        ({"slides": [{"body": [{"table": [["a"]], "align": "zzz"}]}]}, "(table): align must be a letter for each "
         "column (l, c or r) or a list of start, middle and end, not 'zzz'."),
        ({"slides": [{"body": [{"stats": [{"value": 1, "label": ["a"]}]}]}]}, "(stats): A stat's label must be "
         "text, not ['a']."),
        ({"slides": [{"body": [{"stats": [[1, {"a": 1}]]}]}]}, "(stats): A stat's label must be text, "
         "not {'a': 1}."),
        ({"slides": [{"body": [{"callout": "c", "colour": "accent12"}]}]}, "(callout): A callout's colour must be "
         "an accent (accent, accent2, …), not 'accent12'."),
    ],
)
def test_a_wrong_value_in_a_document_is_said_at_its_key_not_drawn(tmp_path: Path, document: dict, said: str) -> None:
    with pytest.raises(DeckDocumentError) as caught:
        deck_from_document({"deck": {}, "slides": [], **document}, tmp_path)
    assert said in str(caught.value)


def test_a_caption_is_words_not_what_python_writes_for_a_list(tmp_path: Path) -> None:
    from PIL import Image

    Image.new("RGB", (8, 8)).save(tmp_path / "p.png")
    gallery = {"gallery": [{"picture": "p.png", "caption": ["a"]}]}
    with pytest.raises(DeckDocumentError, match=r"\(gallery\): A caption must be text, not \['a'\]"):
        deck_from_document({"deck": {}, "slides": [{"body": [gallery]}]}, tmp_path)


def test_the_studio_says_a_deck_setting_wrong_at_the_deck_not_on_its_first_slide(tmp_path: Path) -> None:
    from flexo_talk.studio import DeckKind

    for deck in ({"sketch": "very"}, {"palette": "nosuch"}, {"style": {"title_role": "nosuch"}}):
        drawing = DeckKind().draw({"deck": deck, "slides": [{"title": "a"}, {"title": "b"}]}, tmp_path)
        (message,) = [message for message in drawing.messages if message.severity == "error"]
        assert message.where.startswith("deck.") and not message.page


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


def test_a_slides_text_light_or_dark_is_as_asked_and_its_accents_show_on_its_colour() -> None:
    from flexo.colour import contrast, is_dark

    from flexo_talk.compose import _slide_palette

    deck = Deck("g")
    # Auto: light words on the theme's mid blue (a slide of its accent), as Keynote sets them;
    # dark on a yellow.
    slide = deck.slide("T", background="accent")
    accent, auto = slide.backdrop, _slide_palette(deck, slide)
    assert not is_dark(auto.get("ink"))
    assert is_dark(_slide_palette(deck, deck.slide("Y", background="#f2d03b")).get("ink"))
    # Light or Dark asked is what is drawn, however the colour would have it.
    asked = _slide_palette(deck, deck.slide("D", background="accent", dark=False))
    assert is_dark(asked.get("ink"))
    assert not is_dark(_slide_palette(deck, deck.slide("L", background="#f0f0f0", dark=True)).get("ink"))
    assert is_dark(_slide_palette(deck, deck.slide("N", background="#1b2a41", dark=False)).get("ink"))
    # The accent (the title's rule, accented words) on a slide of that accent is still seen.
    assert contrast(deck.palette.get("tone-1-stroke"), accent) < 2.0
    assert all(contrast(palette.get("tone-1-stroke"), accent) >= 3.0 for palette in (auto, asked))


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
    assert any("Darken the picture by" in line for line in faint.render()[0].diagnostics)


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
    assert any("is too wide to fit, even at the smallest size" in line for line in second.diagnostics)


def test_a_long_code_line_is_set_smaller_then_wrapped_and_said() -> None:
    from flexo_talk.compose import _Canvas, _code_lines

    deck = Deck("c")
    long = "result = some_function_with_a_long_name(argument_one, argument_two, keyword=value) " * 2
    slide = deck.slide("Code")
    slide.code(f"def f():\n    {long}\n    return result")
    (rendered,) = deck.render()
    assert any("of code wrapped to fit the slide" in line for line in rendered.diagnostics)
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
    assert not any("Text does not fit" in line for line in slide.diagnostics)


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


def test_a_displayed_equation_in_python_words_is_centred_as_in_a_document() -> None:
    slide = Deck("m").slide("D")
    slide.text(r"$$E = mc^2$$")
    (block,) = slide.body.blocks
    assert type(block).__name__ == "_Math" and block.align == "middle"


def test_emphasis_pairs_as_markdown_pairs_it() -> None:
    from flexo_talk.deck import inline

    def styled(words: str) -> list[tuple[str, bool, int]]:
        return [(run.text, run.italic, run.weight) for run in inline(words)]

    assert "".join(text for text, _, _ in styled("2 * 3 * 4")) == "2 * 3 * 4"
    assert styled(r"a \*literal\* b") == [("a *literal* b", False, 400)]
    assert styled("***both***") == [("both", True, 700)]
    assert styled("*a* b") == [("a", True, 400), (" b", False, 400)]


def test_a_footer_takes_markup_and_a_right_to_left_one_stands_at_the_right() -> None:
    import re

    deck = Deck("f", footer="**Lab** meeting")
    deck.slide("S").text("x")
    (slide,) = deck.render()
    assert 'font-weight="700"' in re.search(r'id="slide1\.footer".*?</text>', slide.svg, re.S).group(0)
    persian = Deck("fa", footer="سمینار گروه")
    persian.slide("S").text("x")
    (slide,) = persian.render()
    footer = re.search(r'id="slide1\.footer"[^>]*x="([\d.]+)"[^>]*text-anchor="end"', slide.svg)
    assert footer and float(footer.group(1)) > persian.style.width / 2


def test_a_tab_in_words_is_a_space(tmp_path: Path) -> None:
    deck = Deck("t")
    deck.slide("S").text("a\tb").bullets("c\td")
    (slide,) = deck.render()
    assert "\t" not in slide.svg


def test_a_right_to_left_quote_is_written_to_powerpoint_as_it_reads(tmp_path: Path) -> None:
    import re
    import zipfile

    deck = Deck("q")
    slide = deck.slide("آمار")
    slide.quote("سخن بزرگان با **تأکید** در میانه", by="حافظ")
    xml = zipfile.ZipFile(deck.build(tmp_path, formats=("pptx",)).pptx).read("ppt/slides/slide1.xml").decode()
    words = re.search(r'name="Text “سخن.*?</p:sp>', xml, re.S).group(0)
    assert 'rtl="1"' in words
    assert "".join(re.findall(r"<a:t>([^<]*)</a:t>", words)) == "سخن بزرگان با تأکید در میانه"
    date = "\u06f1\u06f5 مهر \u06f1\u06f4\u06f0\u06f5"
    title = deck.title("T", author="بیمارستان شریعتی", date=date)
    assert "\u2013" in "".join(run.text for run in title.byline_runs)  # a dot would read as a zero


def test_right_to_left_slides_set_their_furniture_from_the_right() -> None:
    import re

    deck = Deck("fa", look="editorial")
    deck.title("عنوان ارائه", subtitle="زیرعنوان")
    deck.agenda("فهرست")
    deck.section("بخش اول")
    deck.slide("آمار").stats(("۹۳٪", "دقت"))
    deck.slide("فهرست").bullets("مورد اول", "GPT-4 در این مورد", "مورد سوم")
    title, agenda, _section, stats, listing = deck.render()
    middle = deck.style.width / 2

    def x_of(svg: str, element: str) -> float:
        found = re.search(rf'id="{re.escape(element)}"[^>]*\bx="([\d.]+)"', svg)
        assert found, element
        return float(found.group(1))

    assert x_of(title.svg, "slide1.bar") > middle
    assert x_of(agenda.svg, "slide2.agenda0.number") > middle
    assert x_of(stats.svg, "slide4.body.0.0") > middle  # the figure over its label, at the right
    assert listing.svg.count('text-anchor="end"') >= 3  # every item, the English-led one too


def test_title_section_and_statement_slides_fit_their_words_or_say_so() -> None:
    import re

    long = "A very long sentence that goes on and on " * 8
    deck = Deck("o")
    deck.title(long, subtitle=long[:200], author="Me")
    deck.section(long)
    deck.statement(long, by="Someone")
    for slide in deck.render():
        ys = [float(y) for y in re.findall(r'<text [^>]*\by="([\d.-]+)"', slide.svg)]
        assert min(ys) > 0 and max(ys) < deck.style.height, slide.slide.layout
        assert any("to fit" in line for line in slide.diagnostics)


def test_a_plot_keeps_a_background_chosen_for_it_and_clears_the_default() -> None:
    import matplotlib.pyplot as plt

    from flexo_talk.compose import plot_svg

    figure, axes = plt.subplots()
    axes.plot([0, 1], [0, 1])
    axes.set_facecolor("#e5e5e5")
    inset = axes.inset_axes([0.5, 0.5, 0.4, 0.4])
    inset.plot([0, 1], [1, 0])
    svg = plot_svg(figure, 300.0, 200.0, "Figtree", "p")
    assert "#e5e5e5" in svg.lower() and "#ffffff" in svg.lower()  # the panel, and the inset's white
    plain, axes = plt.subplots()
    axes.plot([0, 1], [0, 1])
    assert "#ffffff" not in plot_svg(plain, 300.0, 200.0, "Figtree", "q").lower()


@pytest.mark.parametrize(
    ("svg", "shapes"),
    [
        ('<rect width="10" height="10" fill="#c00"/>', True),
        ('<style>.a{fill:red}</style><rect class="a" width="10" height="10"/>', False),
        ('<style>*{stroke-linejoin:round}</style><rect width="10" height="10"/>', True),
        ('<defs><symbol id="s"><circle r="3"/></symbol></defs><use href="#s"/>', False),
        ('<g opacity="0.5"><rect width="4" height="4"/><rect x="2" width="4" height="4"/></g>', False),
        ('<text transform="scale(-1,1)" x="-20" y="10">mirrored</text>', False),
        ('<rect width="10" height="10" fill="currentColor"/>', False),
    ],
)
def test_an_svg_file_is_placed_as_shapes_only_when_it_draws_as_its_viewers_do(svg: str, shapes: bool) -> None:
    from flexo_talk.compose import _drawable

    markup = f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 40 20">{svg}</svg>'
    assert _drawable(markup) is shapes


def test_an_svg_placed_as_a_picture_keeps_its_text_in_the_png(tmp_path: Path) -> None:
    from PIL import Image

    picture = tmp_path / "words.svg"
    picture.write_text(
        '<svg xmlns="http://www.w3.org/2000/svg" width="200" height="60" viewBox="0 0 200 60">'
        '<defs><linearGradient id="g"><stop offset="0" stop-color="#fff"/><stop offset="1" stop-color="#fff"/>'
        '</linearGradient></defs><rect width="200" height="60" fill="url(#g)"/>'
        '<text x="10" y="45" font-size="40" font-family="Figtree" fill="#000">Words</text></svg>'
    )
    deck = Deck("p")
    deck.slide("S").image(str(picture))
    (png,) = deck.build(tmp_path / "out", formats=("png",)).pngs
    image = Image.open(png).convert("L")
    assert image.getextrema()[0] < 60  # the black words are drawn


def test_two_revealed_lists_reveal_one_after_the_other_as_in_powerpoint() -> None:
    deck = Deck("r")
    slide = deck.slide("Two", layout="two-columns")
    slide.left.bullets("a", "b", reveal=True)
    slide.right.bullets("c", "d", reveal=True)
    (rendered,) = deck.render()
    assert rendered.steps == 5  # the slide, then a, b, c, d: a click each


def test_small_things_are_left_out_or_said() -> None:
    import re

    with pytest.raises(ValueError, match="Unknown theme \u201cnight\u201d"):
        Deck("t", theme="night")
    with pytest.raises(ValueError, match=r"theme must name a theme .* not 123"):
        Deck("t", theme=123)
    deck = Deck("s")
    slide = deck.slide("   ")
    slide.bullets("a", "", "  ", "b").code("\n\n").table([["a", "b", "c"], ["d"]])
    (rendered,) = deck.render()
    assert slide.title_runs == () and 'id="slide1.rule"' not in rendered.svg
    assert len(re.findall(r'id="slide1\.body\.0"', rendered.svg)) == 1 and len(slide.body.blocks[0].items) == 2
    assert 'data-flexo-talk="code"' not in rendered.svg
    assert any("different numbers of cells" in line for line in rendered.diagnostics)
    assert len(rendered.diagnostics) == len(set(rendered.diagnostics))


def test_the_powerpoint_names_faces_in_english_and_tags_runs_by_script() -> None:
    from flexo.fonts import family_faces, select_face

    from flexo_talk.pptx import _lang, _legacy_family

    faces = family_faces("Geeza Pro")
    if faces:  # a Mac font: named in Persian, Hindi and Arabic only, on Windows
        face = select_face(faces, 400, False)
        assert _legacy_family(face.source, face.index) == "Geeza Pro"
    tags = [_lang(text) for text in ("hello", "گفتگو", "日本語のテキスト", "한국어")]
    assert tags == ["en-GB", "fa-IR", "ja-JP", "ko-KR"]


def test_a_list_far_longer_than_any_slide_is_cut_and_said_quickly() -> None:
    deck = Deck("l")
    deck.slide("Huge").bullets(*[f"item {index}" for index in range(5000)])
    start = time.monotonic()
    (slide,) = deck.render()
    assert time.monotonic() - start < 30
    assert any("List shortened from 5,000 to 300 items" in line for line in slide.diagnostics)


def test_convert_names_files_beside_the_document_and_makes_its_folder(tmp_path: Path) -> None:
    import json

    from PIL import Image

    from flexo_talk.document import read_deck

    source = tmp_path / "talk"
    source.mkdir()
    Image.new("RGB", (16, 16), "#336699").save(source / "photo.png")
    (source / "lab.yaml").write_text("theme:\n  name: lab\n  base: paper\n")
    (source / "deck.py").write_text(
        "from pathlib import Path\n"
        "from flexo_talk import Deck\n"
        "HERE = Path(__file__).resolve().parent\n"
        "def talk():\n"
        "    deck = Deck('lab', theme=str(HERE / 'lab.yaml'))\n"
        "    slide = deck.slide('S', background=str(HERE / 'photo.png'), shade=0.5)\n"
        "    with slide.figure() as figure:\n"
        "        figure.image('p', HERE / 'photo.png', label='P')\n"
        "    return deck\n"
    )
    target = tmp_path / "out" / "new" / "deck.json"
    assert main(["convert", str(source / "deck.py"), "-o", str(target)]) == 0
    text = target.read_text()
    assert str(tmp_path) not in text  # nothing named by where it happens to be
    document = json.loads(text)
    assert document["deck"]["theme"] == "../../talk/lab.yaml"
    assert document["slides"][0]["background"] == "../../talk/photo.png"
    assert read_deck(target).render()[0].diagnostics == []


def test_a_date_is_written_as_a_document_writes_one() -> None:
    import datetime
    import json

    from flexo_talk.document import deck_document, dump_document
    from flexo_talk.studio import DeckKind

    deck = Deck("d")
    title = deck.title("T", author="Ada", date=datetime.date(2026, 10, 1))
    assert "".join(run.text for run in title.byline_runs) == "Ada · 2026-10-01"
    document = deck_document(deck)
    document["slides"][0]["notes"] = datetime.date(2026, 10, 2)  # as yaml.safe_load gives one
    written = json.loads(dump_document(document, format="json"))["slides"][0]
    assert (written["date"], written["notes"]) == ("2026-10-01", "2026-10-02")
    assert DeckKind().parse("title: yes\ndate: 2026-10-01\n") == {"title": "yes", "date": "2026-10-01"}


def test_an_author_of_several_lines_has_the_date_on_a_line_of_its_own() -> None:
    # Not after the author's last line (a place under a name), as one byline line would.
    deck = Deck("d")
    one = deck.title("T", author="Ada Lovelace", date="2026")
    several = deck.title("T", author="Ada Lovelace\nUniversity College London", date="2026")
    assert "".join(run.text for run in one.byline_runs) == "Ada Lovelace · 2026"
    assert "".join(run.text for run in several.byline_runs) == "Ada Lovelace\nUniversity College London\n2026"


def test_a_document_nested_past_any_deck_is_refused_in_words(tmp_path: Path) -> None:
    deep: list = ["x"]
    for _ in range(3000):
        deep = ["x", deep]
    with pytest.raises(DeckDocumentError, match="more than 100 levels deep"):
        deck_from_document({"deck": {}, "slides": [{"body": [{"bullets": deep}]}]}, tmp_path)
    path = tmp_path / "deep.yaml"
    path.write_text("slides:\n- body:\n  - bullets: " + "[x, " * 3000 + "x" + "]" * 3000 + "\n")
    with pytest.raises(DeckDocumentError, match="levels deep"):
        load_document(path)
    with pytest.raises(ValueError, match="nested more than 100 levels"):
        Deck("d").slide("S").bullets(*deep[:2])


def test_a_plot_that_never_returns_is_stopped_on_the_command_line(
    tmp_path: Path, capsys: pytest.CaptureFixture, monkeypatch: pytest.MonkeyPatch
) -> None:
    import signal

    import flexo_talk.document as document

    monkeypatch.setattr(document, "CODE_TIMEOUT", 1.0)
    (tmp_path / "plots.py").write_text("def loops():\n    while True:\n        pass\n")
    (tmp_path / "deck.yaml").write_text("deck: {id: x}\nslides:\n- body: [{plot: plots.py:loops}]\n")
    start = time.monotonic()
    assert main(["build", str(tmp_path / "deck.yaml"), "-o", str(tmp_path / "out"), "--formats", "svg"]) == 1
    assert time.monotonic() - start < 30
    assert "slides[0].body[0] (plot): plots.py:loops took longer than 1 second and was stopped." in (
        capsys.readouterr().err
    )
    (tmp_path / "plots.py").write_text("def loops():\n    return None\n")
    assert main(["build", str(tmp_path / "deck.yaml"), "-o", str(tmp_path / "out"), "--formats", "svg"]) == 1
    assert "plots.py:loops did not return a matplotlib figure" in capsys.readouterr().err
    assert signal.getitimer(signal.ITIMER_REAL)[0] == 0  # nothing left to ring later


def test_callouts_opening_columns_side_by_side_stand_as_one_row_of_panels() -> None:
    import re

    deck = Deck("c")
    slide = deck.slide("Three", layout="columns")
    slide.columns[0].callout("A long point that takes several lines to say in a narrow column.", title="One")
    slide.columns[0].text("Words under the first.")
    slide.columns[1].callout("Short.", title="Two")
    slide.columns[2].callout("Middling, a line or two.", title="Three")
    (rendered,) = deck.render()
    heights = [float(re.search(rf'id="slide1\.column{index}\.0\.panel"[^>]*height="([\d.]+)"', rendered.svg).group(1))
               for index in (1, 2, 3)]
    assert len(set(heights)) == 1
    alone = Deck("a")
    alone.slide("One").callout("Short.")
    (single,) = alone.render()
    natural = float(re.search(r'id="slide1\.body\.0\.panel"[^>]*height="([\d.]+)"', single.svg).group(1))
    assert natural < heights[0]


def test_a_figure_slide_s_figure_grows_to_fill_it_and_a_lone_picture_sits_with_its_title() -> None:
    import flexo

    from flexo_talk.compose import OPTICAL

    def strip() -> flexo.Figure:
        figure = flexo.Figure("strip")
        a = figure.root.block("a", label="Sensor")
        b = figure.root.block("b", label="Hub", input=a)
        figure.root.block("c", label="Cloud", input=b)
        return figure

    content, figured = Deck("f"), Deck("f")
    content.slide("Content").add(strip())
    figured.slide("Figure", layout="figure").add(strip())
    (small,), (large,) = content.render(), figured.render()

    def scale(svg: str) -> float:
        import re

        return float(re.search(r'id="slide1\.body\.0"[^>]*transform="[^"]*scale\(([\d.]+)', svg).group(1))

    assert scale(large.svg) > scale(small.svg) * 1.2  # words up to the title's size, not the body's
    for align, share in (("auto", OPTICAL), ("middle", 0.5)):
        deck = Deck("t")
        deck.slide("T", align=align).table([["a", "b"], ["1", "2"]])
        (slide,) = deck.render()
        (table,) = slide.tables
        top = table.y - _body_top(slide.svg)
        below = deck.style.height - deck.style.margin - deck.style.small_size - (table.y + sum(table.heights))
        assert abs(top / (top + below) - share) < 0.03, align


def _body_top(svg: str) -> float:
    import re

    rule = re.search(r'id="slide1\.rule"[^>]*\by="([\d.]+)"[^>]*height="([\d.]+)"', svg)
    return float(rule.group(1)) + float(rule.group(2)) + Deck("x").style.title_gap


def test_slide_files_are_numbered_as_wide_as_the_count_needs(tmp_path: Path) -> None:
    deck = Deck("big")
    for index in range(100):
        deck.slide(f"Slide {index + 1}")
    names = [path.name for path in deck.build(tmp_path, formats=("svg",)).svgs]
    assert names[0] == "big-001.svg" and names[-1] == "big-100.svg" and names == sorted(names)
    small = Deck("small")
    small.slide("One")
    assert [path.name for path in small.build(tmp_path, formats=("svg",)).svgs] == ["small-01.svg"]


@pytest.mark.parametrize("theme", ["print", "swiss", "bauhaus", "paper"])
def test_a_link_is_told_from_the_words_in_every_theme(theme: str) -> None:
    import re

    from flexo.colour import contrast

    from flexo_talk.pptx import _ink_of

    deck = Deck("l", theme=theme)
    slide = deck.slide("Links")
    slide.text("Read [the paper](https://example.org) first.").bullets("See [the code](https://example.org)")
    (rendered,) = deck.render()
    palette = deck.palette
    ink, page = palette.get("ink"), palette.get("canvas")
    fills = re.findall(r'<a href="https://example.org"><tspan[^>]*fill="(#[0-9a-fA-F]{6})"', rendered.svg)
    assert fills and all(fill.lower() != ink.lower() and contrast(fill, page) >= 4.5 for fill in fills)
    if theme == "paper":
        assert all(fill.lower() == palette.get("tone-1-stroke").lower() for fill in fills)  # the accent, as before
    (listed,) = rendered.lists
    link = next(run for _, runs, _ in listed.items for run in runs if run.link)
    assert _ink_of(link, palette, ink).lower() != ink.lower()  # the PowerPoint's list too


@pytest.mark.parametrize("theme", ["print", "paper", "dark"])
def test_a_link_on_a_band_reads_as_words_must(theme: str) -> None:
    import re

    from flexo.colour import contrast

    from flexo_talk.deck import accent_field

    deck = Deck("l", theme=theme, look="band")
    deck.title("Thank you", subtitle="Questions welcome: [me](mailto:me@example.org)")
    (rendered,) = deck.render()
    fills = re.findall(r'<a href="mailto:me@example.org"><tspan[^>]*fill="(#[0-9a-fA-F]{6})"', rendered.svg)
    assert fills and all(contrast(fill, accent_field(deck.palette)) >= 4.5 for fill in fills)


def test_a_table_that_fits_breaks_none_of_its_words() -> None:
    import re

    deck = Deck("t", look="band")
    slide = deck.slide("Links", layout="two-columns")
    slide.left.bullets("A bullet")
    slide.right.table([["Source", "Where"], ["Code", "GitHub"]])
    (rendered,) = deck.render()
    assert "Source" in re.findall(r">([^<>]+)</tspan>", rendered.svg)  # not Sourc, then e


@pytest.mark.parametrize(("theme", "background"), [("dark", None), ("paper", None), ("dark", "#f4f1ea")])
def test_words_on_a_plots_cells_read_on_them_and_coloured_words_keep_their_colour(
    theme: str, background: str | None
) -> None:
    import re

    import matplotlib.pyplot as plt
    from flexo.colour import contrast

    deck = Deck("cells", theme=theme)
    with deck.plotting():
        figure, (image, mesh) = plt.subplots(1, 2)
        image.imshow([[0.0, 1.0]], cmap="Blues")  # a pale cell, then a deep one
        mesh.pcolormesh([[0.0, 1.0]], cmap="Blues")
        for axes, at in ((image, 0.0), (mesh, 0.5)):
            axes.text(at, at, "pale", ha="center")
            axes.text(at + 1, at, "deep", ha="center")
            axes.text(at + 1, at, "mine", color="#ff0000")
    deck.slide("Cells", background=background).plot(figure)
    (slide,) = deck.render()

    def fills(words: str) -> list[str]:
        return re.findall(rf"fill: (#[0-9a-f]{{6}})[^>]*>{words}<", slide.svg)

    assert len(fills("pale")) == 2 and all(contrast(fill, "#f7fbff") >= 4.5 for fill in fills("pale"))
    assert len(fills("deep")) == 2 and all(contrast(fill, "#08306b") >= 4.5 for fill in fills("deep"))
    assert fills("mine") == ["#ff0000", "#ff0000"]


def test_a_plot_of_very_many_marks_draws_them_as_one_picture_in_the_slides_paints(tmp_path: Path) -> None:
    import base64
    import io
    import re
    import zipfile

    import matplotlib.pyplot as plt
    import numpy as np
    from PIL import Image

    deck = Deck("dense", theme="dark")
    with deck.plotting():
        figure, (many, chosen) = plt.subplots(1, 2)
        many.scatter(*np.random.default_rng(0).normal(size=(2, 100_000)), s=1, color="black")
        chosen.scatter([0, 1], [0, 1], rasterized=True)  # the author's own choice, not said
    deck.slide("Dense").plot(figure)
    start = time.monotonic()
    result = deck.build(tmp_path, formats=("png", "pdf", "pptx", "svg"))
    assert time.monotonic() - start < 15  # 100,000 shapes took half a minute
    assert [line for line in result.diagnostics if "rasterized=True" in line] == [
        "slide1: The 100,000 marks in the plot are drawn as an image, not as shapes. "
        "To choose this yourself, plot them with rasterized=True."
    ]
    svg = result.svgs[0].read_text()
    assert len(svg) < 2_000_000 and svg.count("<path") < 200
    pictures = [np.asarray(Image.open(io.BytesIO(base64.b64decode(data))).convert("RGBA"))
                for data in re.findall(r"data:image/png;base64,([A-Za-z0-9+/=\s]+)", svg)]
    marks = max(pictures, key=lambda pixels: int((pixels[..., 3] > 128).sum()))
    # Black on a dark slide is the slide's ink, in a picture as in shapes.
    assert marks[marks[..., 3] > 128][:, :3].mean() > 200
    with zipfile.ZipFile(result.pptx) as pptx:  # type: ignore[arg-type]
        slide = pptx.read("ppt/slides/slide1.xml").decode()
    assert slide.count("<p:sp>") < 200 and "<p:pic>" in slide


@pytest.mark.parametrize("kind", ["pcolormesh", "contourf"])
def test_a_mesh_shows_no_hairlines_of_the_slide_between_its_cells_in_the_png(kind: str, tmp_path: Path) -> None:
    import matplotlib.pyplot as plt
    import numpy as np
    from matplotlib.colors import ListedColormap
    from PIL import Image

    deck = Deck("mesh", theme="dark")
    with deck.plotting():
        figure, axes = plt.subplots()
        x, y = np.meshgrid(np.linspace(0, 1, 13), np.linspace(0, 1, 13))
        # Every cell (every level) one colour: anything else inside is the slide showing through.
        getattr(axes, kind)(x, y, np.sin(6 * x) * np.cos(5 * y), cmap=ListedColormap(["#21918c"]))
    deck.slide("Mesh").plot(figure)
    (png,) = deck.build(tmp_path, formats=("png",)).pngs
    pixels = np.asarray(Image.open(png).convert("RGB"), dtype=int)
    away = np.abs(pixels - np.array([0x21, 0x91, 0x8C])).max(axis=2)
    rows, columns = np.nonzero(away < 8)
    inside = away[rows.min() + 6 : rows.max() - 6, columns.min() + 6 : columns.max() - 6]
    assert inside.max() < 16  # a seam lets the slide through by 30 or more


def test_a_plots_words_that_ask_for_monospace_or_serif_are_set_in_the_decks_faces_for_them() -> None:
    import re

    import matplotlib.pyplot as plt

    from flexo_talk.compose import plot_faces, plot_svg

    figure, axes = plt.subplots()
    axes.text(0.1, 0.8, "code", family="monospace")
    axes.text(0.1, 0.6, "typed", family="Courier New")
    axes.text(0.1, 0.4, "roman", family="serif")
    axes.text(0.1, 0.2, "plain", family="Comic Sans MS")
    svg = plot_svg(figure, 300.0, 200.0, "Figtree", "f", faces=plot_faces(Deck("faces").layout_style.typography))
    set_in = {words: family for family, words in re.findall(r"font-family: '([^']+)'[^>]*>(\w+)<", svg)}
    assert set_in == {"code": "IBM Plex Mono", "typed": "IBM Plex Mono", "roman": "Latin Modern Roman",
                      "plain": "Figtree"}


def test_a_plots_words_longer_than_it_are_fitted_to_it_and_said() -> None:
    import io
    import re

    import matplotlib.pyplot as plt
    import numpy as np
    from flexo.export import rasterise
    from PIL import Image

    from flexo_talk.compose import plot_svg

    figure, axes = plt.subplots()
    axes.plot([0, 1], [0, 1])
    axes.set_ylabel("a score with a very long axis label that keeps going and going and going")
    axes.set_title("https://example.org/a/very/long/path/to/the/data/that/was/plotted/here.csv")
    said: list[tuple[str, str]] = []
    svg = plot_svg(figure, 300.0, 200.0, "Figtree", "w", said=said)
    assert [line for _, line in said] == [
        "Text “a score with a very long axis label that keeps going and go…” in the plot is too long, "
        "so it was wrapped. Try shortening it.",
        "Text “https://example.org/a/very/long/path/to/the/data/that/was/p…” in the plot is too long, "
        "so it was reduced in size and truncated. Try shortening it.",
    ]
    # Drawn on a page a hundred points larger all round, nothing is outside the plot's own box.
    wider = re.sub(r'width="[^"]+" height="[^"]+" viewBox="[^"]+"',
                   'width="500pt" height="400pt" viewBox="-100 -100 500 400"', svg, count=1)
    alpha = np.asarray(Image.open(io.BytesIO(rasterise(wider, dpi=72))).convert("RGBA"))[..., 3].copy()
    alpha[99:301, 99:401] = 0
    assert alpha.max() == 0


def test_black_words_in_a_plot_read_on_a_dark_slide_as_black_lines_do() -> None:
    import re

    import matplotlib.pyplot as plt

    deck = Deck("dark", theme="dark")
    with deck.plotting():
        figure, axes = plt.subplots()
        axes.plot([0, 1], [0, 1], color="k")
        axes.text(0.5, 0.2, "black words", color="k")
    deck.slide("Black").plot(figure)
    (slide,) = deck.render()
    ink = deck.palette.get("ink").lower()
    words = re.search(r"<text[^>]*>(?:(?!</text>).)*black words", slide.svg, re.DOTALL)
    assert words is not None and ink in words.group(0).lower()


def test_the_command_line_build_leaves_out_a_skipped_slide(tmp_path: Path) -> None:
    # As the studio's export and the show leave it out (Keynote's Skip Slide).
    (tmp_path / "talk.yaml").write_text(
        "schema_version: 1\ndeck: {id: skips}\nslides:\n"
        "- {title: One}\n- {title: Two, skip: true}\n- {title: Three}\n",
        encoding="utf-8",
    )
    out = tmp_path / "out"
    assert main(["build", str(tmp_path / "talk.yaml"), "--formats", "svg", "-o", str(out)]) == 0
    # Numbered as they are shown, as the numbers drawn on them are: no gap where one was skipped.
    assert sorted(path.name for path in out.glob("*.svg")) == ["skips-01.svg", "skips-02.svg"]
    assert "Three" in (out / "skips-02.svg").read_text(encoding="utf-8")
