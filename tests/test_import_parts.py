"""The parts of a deck's import: Keynote's Snappy and protobuf read (and written) by hand
(``iwa``), Office Math read back as TeX -- every formula Flexo writes as Office Math comes back
as the same formula (``omml_tex``) -- MathML as TeX (``mathml_tex``), a slide program's words
as slide markup (``markup``), and a list's levels as Flexo's nested lists."""

from __future__ import annotations

import pytest

from flexo_talk.importing import iwa
from flexo_talk.importing.keynote import family_of
from flexo_talk.importing.markup import escaped, runs_markup
from flexo_talk.importing.mathml_tex import equation_tex, mathml_tex
from flexo_talk.importing.model import Colour, Run
from flexo_talk.importing.omml_tex import parse_omml
from flexo_talk.importing.writing import _nested


def test_snappy_reads_what_it_writes_and_a_stream_that_copies_back() -> None:
    data = bytes(range(256)) * 300
    assert iwa.unsnappy(iwa.snappy(data)) == data
    # "abcd" then a copy of 8 bytes from 4 back (overlapping): abcdabcdabcd.
    stream = bytes([12, 3 << 2]) + b"abcd" + bytes([((8 - 4) << 2) | 1, 4])
    assert iwa.unsnappy(stream) == b"abcdabcdabcd"
    with pytest.raises(iwa.Damaged):
        iwa.unsnappy(bytes([20, 3 << 2]) + b"abcd")


def test_protobuf_fields_are_read_by_number_as_written() -> None:
    written = (iwa.Builder().int(1, 7).float(2, 1.5).text(3, "words").message(4, iwa.Builder().int(1, 99))
               .packed(5, [1, 2, 300]).reference(6, 1234).bool(7, True).int(8, -3))
    message = iwa.Message(bytes(written))
    assert message.int(1) == 7 and message.float(2) == 1.5 and message.text(3) == "words"
    assert message.message(4).int(1) == 99 and message.ints(5) == [1, 2, 300]
    assert message.reference(6) == 1234 and message.bool(7) and message.int(8) == -3
    assert message.int(42, 5) == 5 and not message.has(42)


def test_archives_are_read_back_by_their_ids_and_types() -> None:
    stream = iwa.write_archives([(10, 5, bytes(iwa.Builder().text(10, "a"))), (11, 2001, b"")])
    found = {archive.ident: archive for archive in iwa.archives(stream)}
    assert found[10].type == 5 and found[10].message.text(10) == "a" and found[11].type == 2001


FORMULAS = [
    r"\frac{a+b}{2}",
    r"x^2 + y_i^2",
    r"\sum_{i=1}^{N} \log p_\theta(y_i \mid x_i)",
    r"\sqrt{d_k}",
    r"\sqrt[3]{x}",
    r"\left( \frac{a}{b} \right)",
    r"\hat{x} + \bar{y} + \vec{v}",
    r"\int_0^\infty e^{-x} dx",
    r"\begin{pmatrix} a & b \\ c & d \end{pmatrix}",
    r"f(x) = \begin{cases} 1 & x > 0 \\ 0 & \text{otherwise} \end{cases}",
    r"\alpha \beta \gamma \leq \infty",
    r"\lim_{n \to \infty} a_n",
    r"\overbrace{a+b}^{n}",
    r"x \xrightarrow{k} y",
    r"\mathbb{E}[x] \approx \mathbf{W} x",
    r"\begin{aligned} a &= b + c \\ d &= e \end{aligned}",
    r"\mathcal{L}(q) = \mathcal{L}_{\text{geometry}}(q)",
]


@pytest.mark.parametrize("formula", FORMULAS)
def test_office_math_flexo_writes_comes_back_as_the_same_formula(formula: str) -> None:
    from flexo.texmath import linear

    from flexo_talk.omml import omml

    back = parse_omml(omml(formula, size=20, display=True))
    assert linear(back) == linear(formula)


def test_office_math_of_powerpoints_own_reads() -> None:
    m = "http://schemas.openxmlformats.org/officeDocument/2006/math"
    nary = (f'<m:oMath xmlns:m="{m}"><m:nary><m:naryPr><m:chr m:val="\u2211"/></m:naryPr><m:sub><m:r><m:t>i</m:t>'
            f'</m:r></m:sub><m:sup><m:r><m:t>n</m:t></m:r></m:sup><m:e><m:r><m:t>x</m:t></m:r></m:e></m:nary>'
            f'</m:oMath>')
    assert parse_omml(nary) == r"\sum_{i}^{n} x"
    fenced = (f'<m:oMath xmlns:m="{m}"><m:d><m:dPr><m:begChr m:val="["/><m:endChr m:val="]"/></m:dPr><m:e>'
              f'<m:r><m:t>0,1</m:t></m:r></m:e></m:d></m:oMath>')
    assert parse_omml(fenced) == r"\left[0,1\right]"


def test_mathml_becomes_tex() -> None:
    assert mathml_tex('<math><mfrac><mi>a</mi><mn>2</mn></mfrac></math>') == r"\frac{a}{2}"
    assert mathml_tex('<math><msup><mi>e</mi><mrow><mo>-</mo><mi>x</mi></mrow></msup></math>') == "e^{-x}"
    assert mathml_tex('<math><mi mathvariant="bold">W</mi><mo>\u2264</mo><mi>\u03b1</mi></math>') \
        == r"\mathbf{W}\leq\alpha"
    assert equation_tex("<math><mblink/></math>") is None
    assert equation_tex(r"\dot\mathbf{x} % a comment") == r"\dot{\mathbf{x}}"


def test_words_become_slide_markup_with_their_look_where_it_differs() -> None:
    runs = [Run("Bold", bold=True), Run(" and "), Run("italic ", italic=True), Run("red", colour=Colour("#c00000")),
            Run(" H"), Run("2", baseline=-0.25), Run("O "), Run("", tex=r"\alpha"), Run(" costs $5*2")]
    assert runs_markup(runs) == r"**Bold** and *italic* [red]{#c00000} H$_{2}$O $\alpha$ costs \$5\*2"
    assert runs_markup([Run("code", font="Courier New"), Run(" st", baseline=0.3)]) == "`code` $^{\\text{st}}$"
    assert escaped(r"[1] \(x\)") == r"[1\] \\(x\)"


def test_levels_become_nested_lists_an_empty_item_standing_for_a_missing_one() -> None:
    assert _nested([(0, "a"), (1, "b"), (1, "c"), (0, "d")]) == ["a", ["b", "c"], "d"]
    assert _nested([(0, "a"), (2, "deep"), (0, "b")]) == ["a", ["", ["deep"]], "b"]
    assert _nested([(1, "under"), (1, "also")]) == ["under", "also"]


def test_keynotes_faces_are_named_by_their_families() -> None:
    assert family_of("HelveticaNeue-Bold") == ("Helvetica Neue", True, False)
    assert family_of("TimesNewRomanPSMT") == ("Times New Roman", False, False)
    assert family_of("Avenir-BookOblique") == ("Avenir", False, True)
