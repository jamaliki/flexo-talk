"""A slide program's styled words as the slide markup Flexo reads (``flexo_talk.deck.inline``).

Bold is ``**words**``, italic ``*words*``, a colour ``[words]{#c0392b}`` (or a theme's,
``[words]{accent2}``), a link ``[words](https://…)``, a monospace face `` `code` ``, a
formula ``$…$``, and a raised or lowered run maths' own script: ``H$_{2}$O``,
``1$^{\\text{st}}$``. What the markup has no word for -- a run's own size or face, an
underline -- is left out; the words are kept.
"""

from __future__ import annotations

import re
from collections.abc import Callable, Sequence

from flexo_talk.importing.model import Colour, Paragraph, Run

MONOSPACE = re.compile(r"mono|courier|consolas|menlo|code|monaco|inconsolata|lucida console", re.I)


def escaped(text: str) -> str:
    """Words written so the markup reads them as they are: an asterisk, a backtick, a dollar
    and a closing bracket escaped, and a backslash before a bracket kept a backslash."""

    text = text.replace("\\(", "\\\\(").replace("\\[", "\\\\[")
    for mark in ("*", "`", "$", "]"):
        text = text.replace(mark, "\\" + mark)
    return text


def _in_text(text: str) -> str:
    """Words inside maths' ``\\text{...}``."""

    out = []
    for character in text:
        if character in "{}":
            out.append("\\" + character)
        elif character == "\\":
            out.append("\\backslash ")
        elif character in "$%&#_^~":
            out.append("\\" + character if character in "$%&#_" else " ")
        else:
            out.append(character)
    return "".join(out)


_SIGNS = re.compile(r"[0-9+\-\u2212=() .,]+")


def scripted(text: str, raised: bool) -> str:
    """A raised or lowered run as maths' script: digits and signs as they are, words upright."""

    mark = "^" if raised else "_"
    body = text.replace("\u2212", "-")
    inner = body.strip() if _SIGNS.fullmatch(body) else f"\\text{{{_in_text(text)}}}"
    return f"${mark}{{{inner}}}$" if inner else ""


def tex_inline(tex: str) -> str:
    """A formula among words: between dollars, on one line."""

    tex = " ".join(tex.replace("$", "\\$").split())
    return f"${tex}$" if tex else ""


def _same(one: Run, other: Run) -> bool:
    keys = ("bold", "italic", "baseline", "link", "font", "field", "caps")
    if one.tex is not None or other.tex is not None:
        return False
    if any(getattr(one, key) != getattr(other, key) for key in keys):
        return False
    return _hex(one.colour) == _hex(other.colour)


def _hex(colour: Colour | None) -> str | None:
    return colour.hex.lower() if colour is not None else None


def merged(runs: Sequence[Run]) -> list[Run]:
    """Runs side by side in one look made one (a slide program splits words at every edit)."""

    out: list[Run] = []
    for run in runs:
        if not run.text and run.tex is None:
            continue
        if out and _same(out[-1], run):
            last = out[-1]
            out[-1] = Run(**{**last.__dict__, "text": last.text + run.text})
        else:
            out.append(run)
    return out


def _wrapped(text: str, mark: str) -> str:
    """``text`` between ``mark``s, its spaces kept outside them (markup pairs a mark only
    with words it touches)."""

    stripped = text.strip()
    if not stripped:
        return text
    start = text[: len(text) - len(text.lstrip())]
    end = text[len(text.rstrip()) :]
    return f"{start}{mark}{stripped}{mark}{end}"


def runs_markup(
    runs: Sequence[Run],
    *,
    base_bold: bool = False,
    base_italic: bool = False,
    base_colour: str | None = None,
    colour_name: Callable[[Colour], str | None] = lambda colour: colour.hex,
    number: int | None = None,
) -> str:
    """Runs as markup, against a block's own look (``base_*``: what its words are unless
    a run says otherwise). ``colour_name`` names a colour as the markup writes it (a theme's
    colour by its role); ``number`` is written where a slide-number field is."""

    out: list[str] = []
    for run in merged(runs):
        if run.tex is not None:
            out.append(tex_inline(run.tex))
            continue
        text = run.text
        if run.field == "slide-number" and number is not None:
            text = str(number)
        if run.caps:
            text = text.upper()
        text = text.replace("\u000b", "\n").replace("\u2028", "\n")
        if not text:
            continue
        if run.baseline and text.strip():
            start, end = text[: len(text) - len(text.lstrip())], text[len(text.rstrip()) :]
            piece = start + scripted(text.strip(), run.baseline > 0) + end
        elif run.font and MONOSPACE.search(run.font) and text.strip() and "`" not in text:
            piece = _wrapped(text, "`")
        else:
            piece = escaped(text)
        bold = bool(run.bold) if run.bold is not None else base_bold
        italic = bool(run.italic) if run.italic is not None else base_italic
        if piece.strip() and not run.baseline:
            if bold and not base_bold:
                piece = _wrapped(piece, "**")
            if italic and not base_italic:
                piece = _wrapped(piece, "*")
        colour = colour_name(run.colour) if run.colour is not None else None
        if colour and colour.lower() != (base_colour or "").lower() and piece.strip() and "\n" not in piece:
            piece = _bracketed(piece, f"{{{colour}}}")
        if run.link and piece.strip() and "\n" not in piece and not re.search(r"[\s)]", run.link):
            piece = _bracketed(piece, f"({run.link})")
        out.append(piece)
    return _tidy("".join(out))


def _bracketed(piece: str, after: str) -> str:
    """Words in brackets with what follows them (a colour, a link), their spaces outside."""

    start = piece[: len(piece) - len(piece.lstrip())]
    end = piece[len(piece.rstrip()) :]
    return f"{start}[{piece.strip()}]{after}{end}"


def _tidy(markup: str) -> str:
    # Two marks of one kind meeting (bold that ends where the next bold begins) are none.
    markup = re.sub(r"(?<!\\)\*\*\*\*", "", markup)
    return markup


def paragraph_markup(paragraph: Paragraph, **options) -> str:
    """One paragraph's words as markup: a displayed formula as ``$$…$$``."""

    if paragraph.display:
        tex = " ".join(paragraph.display.replace("$", "\\$").split())
        return f"$${tex}$$"
    return runs_markup(paragraph.runs, **options).rstrip()


def plain(paragraph: Paragraph) -> str:
    """What a paragraph says, in plain words (for names and the report)."""

    return "".join(run.text if run.tex is None else run.tex for run in paragraph.runs).strip()
