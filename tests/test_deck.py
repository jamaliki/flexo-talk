"""A deck builds, and its PowerPoint keeps every word, list, figure, and note."""

from __future__ import annotations

import importlib.util
import re
import zipfile
from pathlib import Path

import pytest

from flexo_talk import Deck
from flexo_talk.deck import inline

ROOT = Path(__file__).resolve().parents[1]


def _demo() -> Deck:
    spec = importlib.util.spec_from_file_location("demo", ROOT / "examples" / "demo.py")
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.talk()


def _slides(path: Path) -> list[str]:
    archive = zipfile.ZipFile(path)
    names = sorted(
        (n for n in archive.namelist() if re.fullmatch(r"ppt/slides/slide\d+\.xml", n)),
        key=lambda n: int(re.search(r"(\d+)", n).group(1)),  # type: ignore[union-attr]
    )
    return [archive.read(name).decode() for name in names]


def test_the_demo_builds_every_format(tmp_path: Path) -> None:
    result = _demo().build(tmp_path)
    assert result.pptx is not None and result.pptx.exists()
    assert len(result.svgs) == len(result.pngs) == 5
    assert not result.diagnostics, result.summary()
    assert result.pdf is not None
    pdf = result.pdf.read_bytes()
    assert pdf.count(b"/Type /Page ") == 5 and b"/FontFile2" in pdf


def test_every_word_on_a_slide_is_live_text_in_the_pptx(tmp_path: Path) -> None:
    deck = _demo()
    result = deck.build(tmp_path, formats=("pptx",))
    slides = _slides(result.pptx)  # type: ignore[arg-type]
    assert len(slides) == 5
    text = "".join(re.findall(r"<a:t>([^<]*)</a:t>", slides[1]))
    for words in ("Why another figure tool?", "boxes drift out of line", "flexo-talk · a demo"):
        assert words.replace("·", "·") in text
    # The list is one box of bulleted paragraphs, the second level a level in.
    assert slides[1].count("<a:buChar") == 5 and 'lvl="1"' in slides[1]
    # The figure is native shapes: a rounded box per component, a freeform per line.
    assert slides[4].count('prst="roundRect"') >= 5 and "<a:cubicBezTo>" in slides[4]
    # Dashes are presets every slide program draws; scripts are written larger
    # than drawn, since slide programs shrink raised runs.
    assert '<a:prstDash val="dash"/>' in slides[4] and "custDash" not in slides[4]
    assert re.search(r'sz="\d+" i="1" baseline="', slides[4]) or 'baseline="' in slides[4]
    notes = [n for n in zipfile.ZipFile(result.pptx).namelist() if "notesSlide" in n]  # type: ignore[arg-type]
    assert notes, "the speaker notes are kept"


def test_slide_text_takes_emphasis_and_math() -> None:
    runs = inline("A *model* is **not** $x^2$")
    assert [(r.text, r.italic, r.weight) for r in runs][:4] == [
        ("A ", False, 400),
        ("model", True, 400),
        (" is ", False, 400),
        ("not", False, 700),
    ]
    assert any(r.baseline_shift == "super" for r in runs)


def test_a_deck_takes_any_flexo_theme_and_checks_its_layouts() -> None:
    for theme in ("tikz", "sketch", "dark"):
        with Deck("t", theme=theme) as deck, deck.slide("Hello") as slide:
            slide.bullets("one", "two")
        assert deck.render()[0].svg.startswith("<?xml")
    with pytest.raises(ValueError, match="layouts are"), Deck("t") as deck:
        deck.slide("x", layout="three-columns")  # type: ignore[arg-type]


def test_a_matplotlib_plot_is_native_shapes_and_text(tmp_path: Path) -> None:
    matplotlib = pytest.importorskip("matplotlib")
    matplotlib.use("svg")
    import matplotlib.pyplot as plt

    deck = Deck("plots", theme="dark")
    with deck.plotting():
        figure, axes = plt.subplots()
        axes.plot([0, 1, 2], [2, 1, 1.5], label="loss")
        axes.set_ylabel(r"Loss $\theta$")
        axes.imshow([[0, 1], [1, 0]], extent=(0, 2, 1, 2))
    with deck.slide("A plot") as slide:
        slide.plot(figure)
    result = deck.build(tmp_path, formats=("pptx", "pdf"))
    slide = _slides(result.pptx)[0]  # type: ignore[arg-type]
    # Tick labels are live text in the deck's font.
    assert 'typeface="Figtree"' in slide and ">0.00<" in slide
    # Lines are freeforms; the image is a picture, flipped as matplotlib stores it.
    assert "<a:custGeom>" in slide and "<p:pic>" in slide and 'flipV="1"' in slide
    # Words with maths in them are set by flexo, as on a slide, and drawn as outlines.
    assert ">Loss" not in slide and "STIX" not in slide


def test_an_overfull_slide_is_set_smaller_and_reported(tmp_path: Path) -> None:
    deck = Deck("full")
    with deck.slide("Too much") as slide:
        slide.bullets(*(["a long sentence that goes on and on across the whole slide width"] * 12))
    result = deck.build(tmp_path, formats=("svg",))
    assert any("to fit" in message for message in result.diagnostics)


def test_a_png_picture_is_embedded(tmp_path: Path) -> None:
    import struct
    import zlib

    def chunk(tag: bytes, payload: bytes) -> bytes:
        return struct.pack(">I", len(payload)) + tag + payload + struct.pack(">I", zlib.crc32(tag + payload))

    rows = b"".join(b"\x00" + bytes([30, 120, 200] * 4) for _ in range(3))
    source = tmp_path / "p.png"
    source.write_bytes(
        b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", 4, 3, 8, 2, 0, 0, 0))
        + chunk(b"IDAT", zlib.compress(rows)) + chunk(b"IEND", b"")
    )
    deck = Deck("pictures")
    with deck.slide("A picture") as slide:
        slide.image(source)
    result = deck.build(tmp_path, formats=("pptx",))
    assert "<p:pic>" in _slides(result.pptx)[0]  # type: ignore[arg-type]
    assert any(name.startswith("ppt/media/") for name in zipfile.ZipFile(result.pptx).namelist())  # type: ignore[arg-type]


def test_a_table_is_a_native_table_ruled_as_in_a_paper(tmp_path: Path) -> None:
    deck = Deck("tables")
    with deck.slide("Results", layout="two-columns", split=0.6) as slide:
        slide.left.table([["Model", "Top-1"], ["ViT", "**81.8**"], ["Ours ($\\lambda$)", "81.2"]])
        slide.right.bullets("Numbers are set flush right")
    result = deck.build(tmp_path, formats=("pptx", "svg"))
    slide = _slides(result.pptx)[0]  # type: ignore[arg-type]
    assert "<a:tbl>" in slide and slide.count("<a:tr ") == 3 and slide.count("<a:gridCol ") == 2
    # Booktabs: a rule above, one under the header, one below; nothing else.
    assert slide.count("<a:lnT w=\"13970\"") + slide.count("<a:lnB w=\"13970\"") >= 2
    # Italic Greek the words' face lacks is the maths font's (TeX's) letter.
    assert 'algn="r"' in slide and "\U0001d706" in slide
    # The drawn copy of the table is not also in the PowerPoint.
    assert slide.count(">Model<") == 1


def test_titles_words_and_figures_each_take_their_own_family(tmp_path: Path) -> None:
    from flexo_talk import DeckStyle

    deck = Deck(
        "type", font="IBM Plex Sans", title_font="Latin Modern Roman", figure_font="Figtree",
        style=DeckStyle(title_align="middle", title_role="tone-1-stroke"),
    )
    with deck.slide("A title", layout="two-columns") as slide:
        slide.left.bullets("Words and `code`")
        with slide.right.figure() as figure:
            figure.block("b", label="Block")
    result = deck.build(tmp_path, formats=("pptx", "svg"))
    svg = result.svgs[0].read_text()
    assert 'font-family="Latin Modern Roman"' in svg and 'text-anchor="middle"' in svg
    assert 'font-family="Figtree"' in svg
    slide = _slides(result.pptx)[0]  # type: ignore[arg-type]
    assert 'typeface="LM Roman 10"' in slide and 'typeface="IBM Plex Sans"' in slide


def test_a_tall_figure_is_laid_out_for_a_wide_slide(tmp_path: Path) -> None:
    deck = Deck("tall")
    with deck.slide("A stack", layout="figure") as slide, slide.figure() as figure, figure.column(
        "layers", reverse=True
    ) as layers:
        previous = layers.text("x", "$x$")
        for index in range(6):
            previous = layers.block(f"b{index}", label=f"Layer {index}", input=previous)
    result = deck.build(tmp_path, formats=("svg",))
    assert any("laid out turned" in note for note in result.notes)
    assert not any("too small" in message for message in result.diagnostics)


def test_a_code_listing_is_set_in_monospace(tmp_path: Path) -> None:
    deck = Deck("code")
    with deck.slide("Code") as slide:
        slide.code("""
            def f(x):
                # a comment
                return x + 1
        """)
    svg = deck.build(tmp_path, formats=("svg",)).svgs[0].read_text()
    assert "def f(x):" in svg and 'xml:space="preserve"' in svg
    assert 'data-flexo-fill="muted-ink"' in svg


def test_a_list_in_another_script_names_a_face_that_has_it(tmp_path: Path) -> None:
    from flexo.fonts import family_covering

    if family_covering("한국어") is None:
        pytest.skip("no installed font has Hangul")
    deck = Deck("scripts")
    with deck.slide("Scripts") as slide:
        slide.bullets("한국어 문장도 됩니다", "See https://github.com/jamaliki/flexo-talk/blob/main/src/flexo_talk/compose.py")
    result = deck.build(tmp_path, formats=("pptx", "svg"))
    slide = _slides(result.pptx)[0]  # type: ignore[arg-type]
    run = re.search(r'<a:r>(?:(?!</a:r>).)*한국어(?:(?!</a:r>).)*</a:r>', slide)
    assert run is not None and 'typeface="Figtree"' not in run.group(0)


def test_a_numbered_list_is_numbered_natively(tmp_path: Path) -> None:
    deck = Deck("numbers")
    with deck.slide("Steps") as slide:
        slide.bullets("First", ["a detail"], "Second", numbered=True)
    result = deck.build(tmp_path, formats=("pptx", "svg"))
    slide = _slides(result.pptx)[0]  # type: ignore[arg-type]
    assert slide.count('<a:buAutoNum type="arabicPeriod"/>') == 2 and slide.count("<a:buChar") == 1
    svg = result.svgs[0].read_text()
    assert ">1.<" in svg and ">2.<" in svg


def test_a_revealed_list_builds_click_by_click(tmp_path: Path) -> None:
    deck = Deck("reveal")
    with deck.slide("Steps") as slide:
        slide.bullets("First", ["under the first"], "Second", "Third", reveal=True)
    with deck.slide("Plain") as slide:
        slide.bullets("No steps")
    result = deck.build(tmp_path, formats=("pptx", "pdf"))
    slide = _slides(result.pptx)[0]  # type: ignore[arg-type]
    assert slide.count('nodeType="clickEffect"') == 3 and '<p:pRg st="0" end="1"/>' in slide
    # Title alone, then one item at a time: four pages, and one for the plain slide.
    assert result.pdf is not None and result.pdf.read_bytes().count(b"/Type /Page ") == 5
    handout = deck.build(tmp_path / "handout", formats=("pdf",), handout=True)
    assert handout.pdf is not None and handout.pdf.read_bytes().count(b"/Type /Page ") == 2


def test_footnotes_sit_above_the_footer_and_shorten_the_body(tmp_path: Path) -> None:
    deck = Deck("notes", footer="Footer")
    with deck.slide("Cited") as slide:
        slide.bullets(*(["a line of text that takes its room"] * 14))
        slide.footnote("[1] A reference.")
    result = deck.build(tmp_path, formats=("svg",))
    svg = result.svgs[0].read_text()
    assert "[1] A reference." in svg
    assert any("fit" in message for message in result.diagnostics)


def test_links_are_native_hyperlinks_in_the_pptx(tmp_path: Path) -> None:
    deck = Deck("links")
    with deck.slide("Links") as slide:
        slide.bullets("Code: [the repository](https://github.com/jamaliki/flexo)")
        slide.footnote("[1] [*A paper*](https://arxiv.org/abs/1706.03762)")
    result = deck.build(tmp_path, formats=("pptx", "pdf"))
    archive = zipfile.ZipFile(result.pptx)  # type: ignore[arg-type]
    relations = archive.read("ppt/slides/_rels/slide1.xml.rels").decode()
    assert "https://github.com/jamaliki/flexo" in relations and "https://arxiv.org/abs/1706.03762" in relations
    assert archive.read("ppt/slides/slide1.xml").decode().count("<a:hlinkClick") == 2
    assert result.pdf is not None and result.pdf.read_bytes().count(b"/Subtype /Link") == 2


def test_a_persian_list_is_set_right_to_left(tmp_path: Path) -> None:
    deck = Deck("fa")
    with deck.slide("سلام دنیا") as slide:
        slide.bullets("این یک جمله است", "English و فارسی")
    result = deck.build(tmp_path, formats=("pptx", "svg"))
    slide = _slides(result.pptx)[0]  # type: ignore[arg-type]
    # The title and the Persian item read right to left; the item starting in English does not.
    assert slide.count('rtl="1"') == 2 and 'algn="r"' in slide
    svg = result.svgs[0].read_text()
    assert 'text-anchor="end"' in svg


def test_an_acknowledgement_slide_has_columns_colours_and_a_gallery(tmp_path: Path) -> None:
    pytest.importorskip("PIL")
    from PIL import Image

    photo = tmp_path / "face.jpg"
    Image.new("RGB", (300, 400), (200, 150, 120)).save(photo)
    deck = Deck("thanks")
    with deck.slide("Thanks", layout="columns", widths=(2, 1, 1)) as slide:
        first, second, third = slide.columns
        first.text("**Lab** [— PI]{muted}", colour="accent")
        second.bullets("[Emmy]{accent2}", "[Bob]{#c0392b}")
        third.gallery([(photo, "**Ada**\\nPI")], crop="circle")
    result = deck.build(tmp_path, formats=("pptx", "svg"))
    svg = result.svgs[0].read_text()
    assert 'data-flexo-talk="gallery"' in svg and "data:image/png;base64" in svg
    slide = _slides(result.pptx)[0]  # type: ignore[arg-type]
    assert "C0392B" in slide and "<p:pic>" in slide and ">Ada<" in slide


def test_a_figure_laid_out_once_is_reused(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    import flexo

    monkeypatch.setenv("FLEXO_TALK_CACHE", str(tmp_path / "cache"))
    calls = []
    real = flexo.fit_in_box

    def counting(*args, **kwargs):
        calls.append(1)
        return real(*args, **kwargs)

    monkeypatch.setattr(flexo, "fit_in_box", counting)
    for _ in range(2):
        deck = Deck("cached")
        with deck.slide("A figure") as slide, slide.figure() as figure:
            figure.block("b", label="Block", input=figure.text("x", "$x$"))
        deck.render()
    assert len(calls) == 1 and list((tmp_path / "cache" / "fits").glob("*.json"))


def test_a_persian_table_reads_from_the_right(tmp_path: Path) -> None:
    deck = Deck("fa-table")
    with deck.slide("Table") as slide:
        slide.table([["مدل", "دقت"], ["الف", "81.2"]])
    result = deck.build(tmp_path, formats=("pptx", "svg"))
    slide = _slides(result.pptx)[0]  # type: ignore[arg-type]
    header = re.search(r"<a:tr .*?</a:tr>", slide)
    assert header is not None
    cells = re.findall(r"<a:t>([^<]*)</a:t>", header.group(0))
    assert cells == ["دقت", "مدل"]  # the first column is written last


def test_a_slide_takes_its_own_background(tmp_path: Path) -> None:
    pytest.importorskip("PIL")
    from PIL import Image

    photo = tmp_path / "wide.jpg"
    Image.new("RGB", (1600, 600), (40, 80, 120)).save(photo)
    deck = Deck("backgrounds")
    deck.title("On a photograph", background=photo, shade=0.5)
    with deck.slide("On a colour", background="#1b2a41") as slide:
        slide.bullets("Light words, lighter accents")
    result = deck.build(tmp_path, formats=("pptx", "svg", "pdf"))
    first, second = _slides(result.pptx)  # type: ignore[arg-type]
    # The photograph is cropped to the slide natively, not stretched.
    assert "<a:srcRect" in first and "<p:pic>" in first
    assert "1B2A41" in second
    assert 'fill="#f7f5f0"' in result.svgs[1].read_text()
    # The native list on a dark slide is set in the slide's light ink, not the page's.
    assert "F7F5F0" in second


def _texts(svg: str, pattern: str) -> list[tuple[float, float]]:
    """The ``(x, y)`` of every text element whose id matches ``pattern``."""

    import xml.etree.ElementTree as ET

    found = []
    for item in ET.fromstring(svg).iter():
        if item.tag.endswith("text") and re.search(pattern, item.get("id", "")):
            found.append((float(item.get("x", 0)), float(item.get("y", 0))))
    return found


@pytest.mark.parametrize("look", ["classic", "band", "editorial", "keynote", "margin"])
def test_every_look_builds_every_kind_of_slide(tmp_path: Path, look: str) -> None:
    deck = Deck("looks", look=look)
    deck.title("A talk", subtitle="In one look", author="Ada")
    deck.agenda()
    deck.section("First part", subtitle="Why")
    deck.statement("One claim, [large]{accent}.", by="someone")
    with deck.slide("Numbers") as slide:
        slide.stats(("93%", "accuracy"), ("4x", "faster"))
        slide.callout("The *key* point.", title="Idea", colour="accent2")
    with deck.slide("Words") as slide:
        slide.quote("A thing worth saying.", by="a reader")
    deck.section("Second part")
    result = deck.build(tmp_path, formats=("pptx", "svg"))
    assert not result.diagnostics, result.summary()
    agenda = result.svgs[1].read_text()
    assert "First part" in agenda and "Second part" in agenda and ">02<" in agenda
    slides = _slides(result.pptx)  # type: ignore[arg-type]
    assert ">93%<" in slides[4] and ">Idea<" in slides[4]
    assert "“" in slides[5] and "a reader" in slides[5]


def test_a_filled_section_takes_the_accent_and_light_words(tmp_path: Path) -> None:
    deck = Deck("fill", look="band")
    deck.section("A part")
    with deck.slide("After it") as slide:
        slide.bullets("An item")
    result = deck.build(tmp_path, formats=("pptx", "svg"))
    section, _ = _slides(result.pptx)  # type: ignore[arg-type]
    accent = deck.palette.get("tone-1-stroke").lstrip("#").upper()
    assert re.search(rf'<p:bg>.*?<a:srgbClr val="{accent}"/>', section, re.S)
    assert "F7F5F0" in section  # its words set light
    # The content slide's title sits on a band of the accent across the top.
    assert 'id="slide2.band"' in result.svgs[1].read_text()


def test_words_start_at_the_top_and_a_shorter_picture_is_centred_against_them(tmp_path: Path) -> None:
    def tall(figure) -> None:
        previous = figure.block("a", label="A")
        for name in "bcdef":
            previous = figure.block(name, label=name.upper(), input=previous)

    deck = Deck("aligned")
    with deck.slide("Beside a taller picture", layout="two-columns") as slide:
        slide.left.bullets("One", "Two")
        with slide.right.figure(turn=False) as figure:
            tall(figure)
    with deck.slide("Beside a shorter picture", layout="two-columns") as slide:
        slide.left.bullets(*(f"Point {index}" for index in range(8)))
        with slide.right.figure() as figure:
            figure.block("a", label="A")
    with deck.slide("Middle", layout="two-columns", align="middle") as slide:
        slide.left.bullets("One", "Two")
        with slide.right.figure(turn=False) as figure:
            tall(figure)
    result = deck.build(tmp_path, formats=("pptx", "svg"))
    taller, shorter, middle = (path.read_text() for path in result.svgs)

    def moved(svg: str, region: str) -> bool:
        return 'transform="translate(0' in svg.split(f'id="{region}"')[1][:80]

    # The words start where the body starts, whatever is beside them.
    assert not moved(taller, "slide1.left") and not moved(shorter, "slide2.left")
    assert moved(shorter, "slide2.right") and moved(middle, "slide3.left")
    # The native list moves with its region: its box starts lower on the middle slide.
    first, _, third = _slides(result.pptx)  # type: ignore[arg-type]
    box = r'name="slide\d\.left\.0".*?<a:off x="\d+" y="(\d+)"'
    offsets = [int(re.search(box, s, re.S).group(1)) for s in (first, third)]  # type: ignore[union-attr]
    assert offsets[1] > offsets[0]


def test_a_single_column_gallery_is_flush_with_the_words(tmp_path: Path) -> None:
    pytest.importorskip("PIL")
    from PIL import Image

    logo = tmp_path / "logo.png"
    Image.new("RGB", (200, 80), (30, 90, 160)).save(logo)
    deck = Deck("logos")
    with deck.slide("Funding") as slide:
        slide.text("**Funded by**")
        slide.gallery([logo, logo], columns=1, height=30)
    result = deck.build(tmp_path, formats=("svg",))
    svg = result.svgs[0].read_text()
    xs = {float(x) for x in re.findall(r'<image id="slide1\.body\.1\.\d" x="([\d.]+)"', svg)}
    assert xs == {deck.style.margin}


def test_a_look_is_a_style_preset() -> None:
    from flexo_talk import DeckStyle

    assert DeckStyle.look("band").header == "band"
    assert Deck(look="editorial").style.sections == "number"
    assert DeckStyle.look("keynote", body_size=24).body_size == 24
    with pytest.raises(ValueError, match="looks are"):
        Deck(look="fancy")
    with pytest.raises(ValueError, match="callout"):
        Deck().slide("x").callout("words", colour="red")


def _word_sizes(svg: str) -> dict[str, set[float]]:
    """The sizes words are drawn at, by the region they are in."""

    from flexo.drawing import Text, read_drawing

    sizes: dict[str, set[float]] = {}
    for item in read_drawing(svg).walk():
        if isinstance(item, Text) and item.id and item.id.count(".") > 2:
            region = ".".join(item.id.split(".")[:2])
            sizes.setdefault(region, set()).update(round(run.size, 2) for line in item.lines for run in line.runs)
    return sizes


def test_figures_side_by_side_set_their_words_at_one_size(tmp_path: Path) -> None:
    deck = Deck("shared")
    with deck.slide("Two figures", layout="two-columns") as slide:
        with slide.left.figure() as figure:
            a = figure.block("a", label="Short")
            figure.block("b", label="Pair", input=a)
        with slide.right.figure() as figure:
            previous = figure.text("x", "$x$")
            for index in range(6):
                previous = figure.block(f"b{index}", label=f"Layer {index}", input=previous)
    result = deck.build(tmp_path, formats=("svg",))
    sizes = _word_sizes(result.svgs[0].read_text())
    # The short pair alone would be set at the body size; beside the tall stack it matches it.
    assert sizes["slide1.left"] == sizes["slide1.right"]
    assert max(sizes["slide1.left"]) < deck.style.body_size


def test_a_column_of_numbers_with_gaps_is_still_set_flush_right() -> None:
    deck = Deck("gaps")
    with deck.slide("Results") as slide:
        slide.table([["", "Ours", "Theirs"], ["ImageNet", "88.55", "88.4"], ["CIFAR-100", "94.55", "\N{EN DASH}"]])
    (table,) = slide.body.blocks
    assert table.align == ("start", "end", "end")


def test_a_callout_fills_its_panel_line_by_line(tmp_path: Path) -> None:
    from flexo.drawing import Text, read_drawing

    words = "DeiT trained ViTs on ImageNet alone, with strong augmentation and distillation from a CNN teacher."
    deck = Deck("panel")
    with deck.slide("Next", layout="two-columns") as slide:
        slide.left.bullets("One")
        slide.right.callout(words, title="What came next")
    result = deck.build(tmp_path, formats=("svg",))
    (text,) = [
        item for item in read_drawing(result.svgs[0].read_text()).walk()
        if isinstance(item, Text) and item.id == "slide1.right.0.words"
    ]
    first = "".join(run.text for run in text.lines[0].runs)
    # Greedy: the first line takes all it can, as a paragraph does; balanced lines leave the panel ragged.
    assert len(first) > len(words) / len(text.lines) + 5


def test_an_equation_is_displayed_on_its_own_line_and_fits_its_place(tmp_path: Path) -> None:
    from flexo_talk.document import deck_document, deck_from_document

    long = r" + ".join(rf"\frac{{a_{i}}}{{b_{i}}}" for i in range(40))
    document = {"deck": {"id": "maths"}, "slides": [
        {"title": "Loss", "body": [
            {"text": "We minimise"},
            {"math": r"\mathcal{L} = -\frac{1}{N}\sum_{i=1}^{N} \log p(y_i \mid x_i)"},
            {"text": r"$$\begin{pmatrix} a & b \\ c & d \end{pmatrix}$$"},
            {"math": long},
        ]},
    ]}
    deck = deck_from_document(document, tmp_path)
    kinds = [type(block).__name__ for block in deck.slides[0].regions["body"].blocks]
    assert kinds == ["_Words", "_Math", "_Math", "_Math"]
    # The document keeps what was written.
    assert deck_document(deck)["slides"][0]["body"][2] == {"text": r"$$\begin{pmatrix} a & b \\ c & d \end{pmatrix}$$"}
    result = deck.build(tmp_path / "out", formats=("svg", "pptx"))
    assert not result.diagnostics, result.summary()
    svg = result.svgs[0].read_text()
    groups = re.findall(r'<g [^>]*data-flexo-math="[^"]*"[^>]*>', svg)
    assert len(groups) == 3 and all('data-flexo-talk="math"' in group for group in groups)
    # The long one is set smaller to fit the slide, not run off it.
    from flexo.drawing import read_drawing

    def formulas(group):
        for item in group.items:
            if hasattr(item, "items"):
                if "data-flexo-math" in item.data:
                    yield item
                else:
                    yield from formulas(item)

    def shapes(group):
        for item in group.items:
            yield from shapes(item) if hasattr(item, "items") else [item]

    last = list(formulas(read_drawing(svg).root))[-1]
    right = max(item.x + item.width for item in shapes(last))
    assert right <= deck.style.width - deck.style.margin + 1.0
    slide = _slides(result.pptx)[0]
    assert slide.count("<a:custGeom>") > 50  # formulas are native shapes, glyph by glyph


def test_maths_in_a_list_leaves_room_in_the_native_words_and_is_drawn_over_it(tmp_path: Path) -> None:
    deck = Deck("maths")
    deck.slide("Rates").bullets(
        r"The rate $k = A e^{-E_a/RT}$ rises with temperature",
        r"A plain one: $x_t$",
    )
    deck.slide("Table").table([["what", "value"], ["half", r"$\frac{1}{2}$"]])
    result = deck.build(tmp_path, formats=("pptx",))
    listing, table = _slides(result.pptx)
    # One space, spaced out to the formula's width, keeps its place in the words...
    gaps = re.findall(r'<a:rPr [^>]*spc="(\d+)"[^>]*>.*?</a:rPr><a:t> </a:t>', listing)
    assert len(gaps) == 1 and int(gaps[0]) > 1000
    assert "rises with temperature" in listing and "<a:t>t</a:t>" in listing
    # ...and the formula is drawn as shapes where it was set.
    assert listing.count("<a:custGeom>") > 5
    assert re.search(r'spc="\d+"', table) and table.count("<a:custGeom>") >= 2


def test_maths_that_cannot_be_read_is_reported_on_its_slide(tmp_path: Path) -> None:
    deck = Deck("broken")
    deck.slide("Oops").text(r"Here: $\frac{1}{2} + \foo{x}$").math(r"\sqrt{x")
    result = deck.build(tmp_path, formats=("svg",))
    said = " ".join(result.diagnostics)
    assert r"\foo is not a maths command flexo knows" in said
    assert "a { is not closed" in said and "slide1" in said
    assert "Traceback" not in said and "Error" not in said


def test_prices_are_prices_and_escaped_dollars_are_dollars() -> None:
    runs = inline(r"It costs $5 and $10, a sample is \$20, and $x^2$ is maths.")
    assert "".join(run.text for run in runs if not run.italic).startswith("It costs $5 and $10, a sample is $20")
    assert [run.text for run in runs if run.italic] == ["x"]


def test_a_plot_sets_its_maths_as_a_slide_does_and_says_what_it_cannot_read() -> None:
    pytest.importorskip("matplotlib")
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    from flexo_talk.compose import plot_svg

    # Maths matplotlib cannot set at all: a matrix, \le, a fraction in a legend.
    figure, axes = plt.subplots()
    axes.plot([0, 1], [0, 1], label=r"$\beta = \frac{1}{2}$")
    axes.set_title(r"$\begin{pmatrix} a & b \\ c & d \end{pmatrix}$ and $x \le y$")
    axes.set_ylabel(r"$\frac{1}{$")
    axes.legend()
    said: list[tuple[str, str]] = []
    svg = plot_svg(figure, 300.0, 200.0, "Figtree", "p", maths="Fira Math", said=said)
    assert said == [(r"$\frac{1}{$", "a { is not closed")]
    assert "STIX" not in svg and "<path" in svg
