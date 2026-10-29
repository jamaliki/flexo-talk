"""Code on a slide coloured by what each of its words is, in the deck's own colours.

A listing is read as the language it is in -- the one its block names (``language: rust``),
else the one it looks like -- by Pygments, and each word is painted by its kind: comments
in the theme's muted ink, keywords in its accent, strings, constants and functions in its
next colours, the rest in the listing's ink::

  - code: |
      def loss(x, y):
          return ((x - y) ** 2).mean()  # mean squared error
    language: python

The colours are the theme's tones, as words are painted in them (``[words]{accent2}``), each
kept only if its hue can be told from those before it, and each set to read on the code's
panel (``FLOOR``): so a theme of greys (print) colours only its comments, one with a single
signal colour (rams, swiss) its keywords alone. They are worked out as the slide is drawn,
never written into the deck: a change of theme or palette repaints its code, in the editor,
the PowerPoint and the PDF alike, which are all made from what is drawn.
"""

from __future__ import annotations

import math
import re
from functools import lru_cache
from typing import TYPE_CHECKING

if TYPE_CHECKING:  # pragma: no cover
    from flexo.ir.semantic import TextRun
    from flexo.style import Palette

FLOOR = 2.6
"""The least contrast a coloured word keeps against the code's panel."""

HUES = 25.0
"""How far apart (degrees) two of the theme's colours' hues are to be told apart in code."""

KINDS = ("keyword", "string", "constant", "function")
"""The kinds of words painted in the theme's colours, in the order they take them."""

LANGUAGES: dict[str, str] = {
    "python": "Python",
    "javascript": "JavaScript",
    "typescript": "TypeScript",
    "c": "C",
    "cpp": "C++",
    "rust": "Rust",
    "go": "Go",
    "julia": "Julia",
    "r": "R",
    "matlab": "MATLAB",
    "bash": "Shell",
    "sql": "SQL",
    "latex": "LaTeX",
    "json": "JSON",
    "yaml": "YAML",
    "text": "Plain Text",
}
"""The languages a listing is offered in (by its Pygments name), and what each is called. A
block may name any other Pygments knows (``language: haskell``); ``text`` colours nothing."""

# What each language a listing may be guessed to be looks like, line by line: a line that
# matches one counts for it. Python wins a tie, and a listing that looks like none.
_SIGNS: dict[str, tuple[str, ...]] = {
    "python": (
        r"^\s*(def|class)\s+\w+.*:\s*(#.*)?$", r"^\s*(import\s+\w|from\s+[\w.]+\s+import\b)", r"\bself\.",
        r"^\s*(elif|except|with)\b.*:\s*$", r"^\s*@\w", r"\b(None|True|False)\b", r"\bprint\(",
        r"^\s*for\s+\w+.*\bin\b.*:\s*$",
    ),
    "javascript": (
        r"\b(const|let|var)\s+\w+\s*=", r"=>", r"\bfunction\s*\w*\s*\(", r"\bconsole\.log\b", r"\b(undefined|null)\b",
        r"^\s*(export|import)\s.*\bfrom\s+['\"]", r"===",
    ),
    "typescript": (r"\binterface\s+\w+\s*\{", r"\btype\s+\w+\s*=", r"\w\s*:\s*(string|number|boolean)\b"),
    "cpp": (
        r"^\s*#\s*include\b", r"\bstd::", r"\bint\s+main\s*\(", r"\b(printf|cout|cin)\b",
        r"^\s*(int|float|double|char|void|auto|bool)\s+\**\w+\s*[(=;\[]", r"->\w",
    ),
    "rust": (r"\bfn\s+\w+\s*[(<]", r"\blet\s+mut\b", r"^\s*(impl|pub|use|mod)\b", r"\w+!\(", r"&mut\b", r"::\w"),
    "go": (r"^\s*package\s+\w+", r"\bfunc\s", r":=", r"\bfmt\.", r"^\s*import\s+\("),
    "julia": (r"^\s*function\s+\w+\(", r"^\s*end\s*$", r"^\s*using\s+\w", r"\.(\*|\^|/)", r"\bprintln\("),
    "r": (r"<-", r"\blibrary\(", r"\bfunction\s*\(", r"\w\$\w", r"\bc\("),
    "matlab": (
        r"^\s*%", r"^\s*function\s+(\[|\w+\s*=)", r"\b(zeros|ones|disp|fprintf|plot)\(", r";\s*(%.*)?$", r"^\s*end\s*$",
    ),
    "bash": (
        r"^\s*\$\s", r"^#!", r"^\s*(sudo|pip|conda|git|cd|ls|echo|export|uv|npm|brew|mkdir|cp|mv|rm|curl|wget)\s",
        r"\s--?[a-z][\w-]*", r"\|\s*(grep|sort|head|tail|wc|xargs)\b",
    ),
    "sql": (
        r"(?i)^\s*select\b.*", r"(?i)\bfrom\s+\w+", r"(?i)\b(where|group by|order by|insert into|create table|join)\b",
    ),
    "latex": (r"\\(begin|end)\{", r"\\(frac|section|usepackage|documentclass|textbf|cite|label)\b"),
    "json": (r'^\s*"[^"]*"\s*:', r"^\s*[\[{]\s*$"),
    "yaml": (r"^\s*[\w-]+:(\s|$)", r"^\s*-\s+\w"),
}
_COMPILED = {language: tuple(re.compile(sign) for sign in signs) for language, signs in _SIGNS.items()}


def guess(text: str) -> str:
    """The language a listing looks like (a name in ``LANGUAGES``): the one whose signs its
    lines show most of, Python if none."""

    scores = dict.fromkeys(_COMPILED, 0)
    for line in text.splitlines()[:200]:
        if not line.strip():
            continue
        for language, signs in _COMPILED.items():
            scores[language] += sum(1 for sign in signs if sign.search(line))
    best = max(scores, key=lambda language: scores[language])
    return best if scores[best] > scores["python"] else "python"


def lexer_name(language: str | None, text: str) -> str | None:
    """The Pygments lexer a listing is read with: the one it names, else the one it looks
    like; ``None`` for a listing coloured by nothing (``text``, or a name Pygments lacks)."""

    name = (language or "").strip().lower() or guess(text)
    if name in {"text", "plain", "none", "txt"}:
        return None
    return name if _lexer(name) is not None else None


@lru_cache(maxsize=64)
def _lexer(name: str):
    from pygments.lexers import get_lexer_by_name
    from pygments.util import ClassNotFound

    try:
        return get_lexer_by_name(name, stripnl=False, ensurenl=False)
    except ClassNotFound:
        return None


def known(language: str) -> bool:
    """Whether a listing may name ``language``: one Pygments reads, or ``text``."""

    name = language.strip().lower()
    return name in {"text", "plain", "none", "txt"} or _lexer(name) is not None


def _kind(token: object) -> str | None:
    from pygments.token import Comment, Keyword, Name, Number, Operator, String

    if token in Comment.Preproc or token in Comment.PreprocFile:
        return "keyword"
    if token in Comment:
        return "comment"
    if token in Keyword.Constant:
        return "constant"
    if token in Keyword or token in Operator.Word:
        return "keyword"
    if token in String:
        return "string"
    if token in Number or token in Name.Constant or token in Name.Builtin.Pseudo:
        return "constant"
    if token in Name.Function or token in Name.Class or token in Name.Decorator or token in Name.Builtin:
        return "function"
    return None


@lru_cache(maxsize=64)
def kinds(text: str, name: str) -> tuple[tuple[tuple[int, int, str], ...], ...]:
    """Each line of ``text``, read as the language Pygments calls ``name``: its words of a
    kind (``KINDS``, or ``comment``) as ``(start, end, kind)`` within the line, in order."""

    lexer = _lexer(name)
    lines = text.split("\n")
    if lexer is None:
        return tuple(() for _ in lines)
    starts = [0]
    for line in lines[:-1]:
        starts.append(starts[-1] + len(line) + 1)
    found: list[list[tuple[int, int, str]]] = [[] for _ in lines]
    row = 0
    for at, token, value in lexer.get_tokens_unprocessed(text):
        kind = _kind(token)
        if kind is None or not value:
            continue
        end = at + len(value)
        # (A token across lines -- a docstring -- is cut at each line's end.)
        while row + 1 < len(starts) and starts[row + 1] <= at:
            row += 1
        line, start = row, at
        while start < end and line < len(lines):
            stop = min(end, starts[line] + len(lines[line]))
            if stop > start:
                spans = found[line]
                begin, finish = start - starts[line], stop - starts[line]
                if spans and spans[-1][2] == kind and spans[-1][1] == begin:
                    spans[-1] = (spans[-1][0], finish, kind)
                else:
                    spans.append((begin, finish, kind))
            line += 1
            if line < len(starts):
                start = max(start, starts[line])
    return tuple(tuple(spans) for spans in found)


def _hue(colour: str) -> float:
    from flexo.colour import to_oklab

    _, a, b = to_oklab(colour)
    return math.degrees(math.atan2(b, a)) % 360.0


def _apart(first: str, second: str) -> bool:
    """Whether two colours' hues can be told apart (``HUES`` degrees or more)."""

    turn = abs(_hue(first) - _hue(second)) % 360.0
    return min(turn, 360.0 - turn) >= HUES


def paints(palette: Palette, panel: str, muted: str) -> dict[str, str]:
    """The colour each kind of word is painted in on a code panel of ``panel``: ``comment``
    the muted ink (``muted``, read on the panel already), and keywords, strings, constants
    and functions the theme's tones in turn -- each one's hue (its words' colour, else its
    fill's, for a theme whose words are all ink) kept only if it can be told from those
    before it -- each made to read on the panel. A kind left without one is the ink."""

    from flexo.colour import chroma, with_contrast

    hues: list[str] = []
    for index in range(1, 9):
        stroke, fill = palette.get(f"tone-{index}-stroke"), palette.get(f"tone-{index}-fill")
        colour = stroke if chroma(stroke) >= 0.03 else fill if chroma(fill) >= 0.03 else None
        if colour is None or not all(_apart(colour, other) for other in hues):
            continue
        hues.append(colour)
    made = {kind: with_contrast(colour, panel, FLOOR) for kind, colour in zip(KINDS, hues, strict=False)}
    made["comment"] = muted
    return made


def runs_of(
    body: str, spans: tuple[tuple[int, int, str], ...], offset: int, colours: dict[str, str]
) -> list[tuple[str, str | None]]:
    """``body``, the words of a source line from ``offset`` on, as runs each kind of word
    in its colour: ``(text, colour or None)`` pairs, in order, neighbours of one colour one run."""

    out: list[tuple[str, str | None]] = []
    start, end = offset, offset + len(body)
    at = start
    for begin, finish, kind in spans:
        if finish <= start or begin >= end:
            continue
        begin, finish = max(begin, start), min(finish, end)
        if begin > at:
            out.append((body[at - start : begin - start], None))
        out.append((body[begin - start : finish - start], colours.get(kind)))
        at = finish
    if at < end:
        out.append((body[at - start :], None))
    merged: list[tuple[str, str | None]] = []
    for text, colour in out:
        if merged and merged[-1][1] == colour:
            merged[-1] = (merged[-1][0] + text, colour)
        elif text:
            merged.append((text, colour))
    return merged


def coloured(
    source: list[str], language: str | None, drawn: list[tuple[str, bool, int]], palette: Palette, panel: str,
    muted: str,
) -> list[tuple[TextRun, ...] | None] | None:
    """A listing's lines as drawn (``drawn``: each line's words, whether it is a comment, and
    the line of ``source`` it is of -- a line too long wrapped, its rest indented under it,
    as flexo_talk.compose sets it) as code runs coloured by kind -- a line that is a comment
    alone ``None``, muted as a whole as the listing mutes one; ``None`` where it is coloured
    by nothing (``language: text``)."""

    from flexo.ir.semantic import TextRun

    name = lexer_name(language, "\n".join(source))
    if name is None:
        return None
    spans = kinds("\n".join(source), name)
    colours = paints(palette, panel, muted)
    made: list[tuple[TextRun, ...] | None] = []
    # (Where each source line's next piece starts in it.)
    taken: dict[int, int] = {}
    for text, _, line in drawn:
        offset = taken.get(line)
        if offset is None:
            lead, offset = 0, 0
        else:
            own = source[line] if line < len(source) else ""
            lead = min(len(text), len(own) - len(own.lstrip()) + 4)
        body = text[lead:]
        taken[line] = offset + len(body)
        runs = [(text[:lead], None)] if lead else []
        runs += runs_of(body, spans[line] if line < len(spans) else (), offset, colours)
        # (A line that is a comment alone is the listing's to mute, as a comment line is.)
        if all(colour == colours["comment"] or not piece.strip() for piece, colour in runs):
            made.append(None)
            continue
        made.append(tuple(TextRun(piece, code=True, color=colour or "") for piece, colour in runs if piece))
    return made
