
# Adapted from DeckWerk's importers/keynote/import_keynote.py (mathml_to_tex), by Vincent
# Sitzmann, under the MIT License: Copyright (c) 2026 Vincent Sitzmann. Permission is hereby
# granted, free of charge, to any person obtaining a copy of that software, to deal in it
# without restriction, provided this notice is kept; it is provided "as is", without warranty of
# any kind. Flexo's changes are under the Apache License 2.0, as the rest of it.
"""MathML -- what Keynote's equations are kept in when written in its MathML editor -- as the
LaTeX Flexo sets (``flexo.texmath``): tokens, rows, scripts, fractions, roots, accents, fences,
under- and overscripts and tables; an ``<annotation encoding="application/x-tex">`` as it is.
"""

from __future__ import annotations

import re
import unicodedata
from collections.abc import Iterable

from lxml import etree

from flexo_talk.importing.omml_tex import _COMMANDS

OPERATORS = {
    "\u27f6": r"\longrightarrow", "\u2192": r"\rightarrow", "\u2190": r"\leftarrow", "\u27f5": r"\longleftarrow",
    "\u2194": r"\leftrightarrow", "\u21d2": r"\Rightarrow", "\u27f9": r"\Longrightarrow", "\u21d0": r"\Leftarrow",
    "\u21d4": r"\Leftrightarrow", "\u21a6": r"\mapsto", "\u2264": r"\leq", "\u2265": r"\geq", "\u2260": r"\neq",
    "\u2248": r"\approx", "\u223c": r"\sim", "\u2261": r"\equiv", "\u221d": r"\propto", "\u00d7": r"\times",
    "\u00b7": r"\cdot", "\u22c5": r"\cdot", "\u2217": "*", "\u2212": "-", "\u00b1": r"\pm", "\u2213": r"\mp",
    "\u2208": r"\in", "\u2209": r"\notin", "\u2282": r"\subset", "\u2286": r"\subseteq", "\u222a": r"\cup",
    "\u2229": r"\cap", "\u2211": r"\sum", "\u220f": r"\prod", "\u222b": r"\int", "\u221e": r"\infty",
    "\u2207": r"\nabla", "\u2202": r"\partial", "\u2200": r"\forall", "\u2203": r"\exists", "\u2026": r"\ldots",
    "\u22ef": r"\cdots", "\u2223": r"\mid", "\u2225": r"\|", "\u2016": r"\|", "\u27e8": r"\langle",
    "\u27e9": r"\rangle", "{": r"\{", "}": r"\}", "\u2218": r"\circ", "\u2297": r"\otimes", "\u2295": r"\oplus",
    "\u00ac": r"\neg", "\u2227": r"\land", "\u2228": r"\lor", "\u2032": "'", "\u2033": "''",
    "\u2061": "", "\u2062": "", "\u2063": "", "\u2064": "",
}
ACCENTS = {
    "^": r"\hat", "\u02c6": r"\hat", "\u0302": r"\hat", "~": r"\tilde", "\u02dc": r"\tilde", "\u0303": r"\tilde",
    "\u00af": r"\bar", "\u203e": r"\overline", "\u0304": r"\bar", "\u2192": r"\vec", "\u20d7": r"\vec",
    "\u02d9": r"\dot", "\u0307": r"\dot", "\u00a8": r"\ddot", "\u0308": r"\ddot", "\u23de": r"\overbrace",
    "\u23df": r"\underbrace", "_": r"\underline", "\u0332": r"\underline",
}
VARIANTS = {
    "bold": r"\mathbf", "bold-italic": r"\boldsymbol", "double-struck": r"\mathbb", "script": r"\mathcal",
    "bold-script": r"\mathcal", "fraktur": r"\mathfrak", "bold-fraktur": r"\mathfrak", "sans-serif": r"\mathsf",
    "bold-sans-serif": r"\mathsf", "sans-serif-italic": r"\mathsf", "sans-serif-bold-italic": r"\mathsf",
    "monospace": r"\mathtt", "normal": r"\mathrm",
}
LETTER_STYLES = [
    ("MATHEMATICAL BOLD ITALIC", r"\boldsymbol"), ("MATHEMATICAL BOLD SCRIPT", r"\mathcal"),
    ("MATHEMATICAL BOLD FRAKTUR", r"\mathfrak"), ("MATHEMATICAL SANS-SERIF", r"\mathsf"),
    ("MATHEMATICAL DOUBLE-STRUCK", r"\mathbb"), ("MATHEMATICAL MONOSPACE", r"\mathtt"),
    ("MATHEMATICAL FRAKTUR", r"\mathfrak"), ("MATHEMATICAL SCRIPT", r"\mathcal"), ("MATHEMATICAL BOLD", r"\mathbf"),
    ("MATHEMATICAL ITALIC", ""), ("DOUBLE-STRUCK", r"\mathbb"), ("SCRIPT", r"\mathcal"), ("BLACK-LETTER", r"\mathfrak"),
]
FUNCTIONS = {"sin", "cos", "tan", "log", "ln", "exp", "max", "min", "lim", "det", "arg", "sup", "inf", "dim"}
SPECIALS = {"#": r"\#", "%": r"\%", "&": r"\&", "_": r"\_", "$": r"\$", "\\": r"\backslash ", "~": r"\sim "}


def _letter(character: str) -> str | None:
    """TeX for one of Unicode's styled mathematical letters, else None."""

    if character == "\u210e":
        return "h"
    name = unicodedata.name(character, "")
    for prefix, command in LETTER_STYLES:
        if not name.startswith(prefix + " "):
            continue
        rest = name[len(prefix) + 1 :]
        if rest.startswith(("SMALL ", "CAPITAL ")) and len(rest.split()[-1]) == 1:
            letter = rest.split()[-1]
            plain = letter.lower() if rest.startswith("SMALL ") else letter
        elif rest.startswith("DIGIT "):
            plain = unicodedata.lookup(rest)
        else:
            greek = rest.replace("SMALL ", "SMALL LETTER ").replace("CAPITAL ", "CAPITAL LETTER ")
            try:
                plain = unicodedata.lookup(f"GREEK {greek}")
            except KeyError:
                return None
            plain = f"\\{_COMMANDS[plain]}" if plain in _COMMANDS else plain
        if command == r"\mathcal" and not plain.isupper():
            return character
        return f"{command}{{{plain}}}" if command else plain
    return None


def _join(parts: Iterable[str]) -> str:
    out = ""
    for part in parts:
        if not part:
            continue
        if re.search(r"\\[A-Za-z]+$", out) and re.match(r"[A-Za-z0-9]", part):
            out += " "
        out += part
    return out


def mathml_tex(source: str) -> str:
    """TeX for MathML, or ``ValueError`` naming what has none."""

    try:
        root = etree.fromstring(source.encode("utf-8"), etree.XMLParser(resolve_entities=False, no_network=True))
    except etree.XMLSyntaxError as error:
        raise ValueError(f"does not parse ({error})") from None

    def tag(node: etree._Element) -> str:
        return etree.QName(node).localname if isinstance(node.tag, str) else ""

    def colour_of(node: etree._Element) -> str | None:
        value = (node.get("mathcolor") or "").strip().lower()
        return None if value in ("", "#000000", "#000", "black") else value

    def token(node: etree._Element, operator: bool) -> str:
        parts = []
        for character in (node.text or "").strip():
            if operator and character in OPERATORS:
                parts.append(OPERATORS[character])
            elif character in SPECIALS:
                parts.append(SPECIALS[character])
            elif not character.isascii() and (letter := _letter(character)) is not None:
                parts.append(letter)
            elif character in OPERATORS and OPERATORS[character].startswith("\\"):
                parts.append(OPERATORS[character])
            elif character in _COMMANDS:
                parts.append(f"\\{_COMMANDS[character]}")
            else:
                parts.append(character)
        return _join(parts)

    def group(tex: str) -> str:
        if len(tex) == 1 or re.fullmatch(r"\\[A-Za-z]+", tex) or re.fullmatch(r"\\[A-Za-z]+\{[^{}]*\}", tex):
            return tex
        return f"{{{tex}}}"

    def kids(node: etree._Element) -> list[etree._Element]:
        return [item for item in node if isinstance(item.tag, str)]

    def fence(node: etree._Element) -> str:
        character = (node.text or "").strip()
        return {"{": r"\{", "}": r"\}", "\u27e8": r"\langle ", "\u27e9": r"\rangle ", "\u2016": r"\| "}.get(
            character, character)

    def row(nodes: list[etree._Element]) -> str:
        if (len(nodes) >= 2 and tag(nodes[0]) == "mo" and tag(nodes[-1]) == "mo"
                and (nodes[0].text or "").strip() in "([{|\u2016\u27e8"
                and (nodes[-1].text or "").strip() in ")]}|\u2016\u27e9"
                and (nodes[0].text or "").strip() and (nodes[-1].text or "").strip()
                and "false" not in (nodes[0].get("stretchy"), nodes[-1].get("stretchy"))):
            inner = _join(convert(item) for item in nodes[1:-1])
            return _join([r"\left" + fence(nodes[0]), inner, r"\right" + fence(nodes[-1])])
        return _join(convert(item) for item in nodes)

    def need(node: etree._Element, count: int) -> list[etree._Element]:
        found = kids(node)
        if len(found) != count:
            raise ValueError(f"<{tag(node)}> with {len(found)} children")
        return found

    def fence_character(character: str) -> str:
        return {"": ".", "{": r"\{", "}": r"\}", "\u27e8": r"\langle", "\u27e9": r"\rangle"}.get(character, character)

    def convert(node: etree._Element) -> str:
        name = tag(node)
        if name in ("mi", "mn", "mo", "mtext", "ms"):
            if name in ("mtext", "ms"):
                body = "".join(SPECIALS.get(c, c) for c in (node.text or "")).replace("{", r"\{").replace("}", r"\}")
                tex = rf"\text{{{body}}}" if body.strip() else r"\ "
            else:
                tex = token(node, operator=name == "mo")
                variant = node.get("mathvariant")
                text = (node.text or "").strip()
                if name == "mi" and len(text) > 1 and text.isascii() and text.isalpha() and variant in (None, "normal"):
                    tex = f"\\{text}" if text in FUNCTIONS else rf"\mathrm{{{text}}}"
                elif (variant in VARIANTS and tex and not tex.startswith("\\")
                      and not (variant == "normal" and name != "mi")):
                    tex = f"{VARIANTS[variant]}{{{tex}}}"
        elif name in ("math", "mrow", "mstyle", "mpadded", "merror"):
            tex = row(kids(node))
        elif name == "semantics":
            for item in kids(node)[1:]:
                if tag(item) == "annotation" and (item.get("encoding") or "").lower() in (
                        "application/x-tex", "tex", "latex"):
                    return (item.text or "").strip()
            found = kids(node)
            if not found:
                raise ValueError("<semantics> without content")
            tex = convert(found[0])
        elif name == "mphantom":
            tex = rf"\phantom{{{row(kids(node))}}}"
        elif name == "mspace":
            tex = r"\;"
        elif name == "msub":
            base, sub = need(node, 2)
            tex = f"{group(convert(base))}_{{{convert(sub)}}}"
        elif name == "msup":
            base, sup = need(node, 2)
            tex = f"{group(convert(base))}^{{{convert(sup)}}}"
        elif name == "msubsup":
            base, sub, sup = need(node, 3)
            tex = f"{group(convert(base))}_{{{convert(sub)}}}^{{{convert(sup)}}}"
        elif name == "mfrac":
            top, bottom = need(node, 2)
            tex = rf"\frac{{{convert(top)}}}{{{convert(bottom)}}}"
        elif name == "msqrt":
            tex = rf"\sqrt{{{row(kids(node))}}}"
        elif name == "mroot":
            base, index = need(node, 2)
            tex = rf"\sqrt[{convert(index)}]{{{convert(base)}}}"
        elif name in ("mover", "munder"):
            base, mark = need(node, 2)
            symbol = (mark.text or "").strip() if tag(mark) == "mo" else ""
            accent = ACCENTS.get(symbol)
            under = name == "munder"
            if accent and (accent in (r"\underbrace", r"\underline")) == under:
                tex = f"{accent}{{{convert(base)}}}"
            elif under:
                tex = rf"\underset{{{convert(mark)}}}{{{convert(base)}}}"
            else:
                tex = rf"\overset{{{convert(mark)}}}{{{convert(base)}}}"
        elif name == "munderover":
            base, below, above = need(node, 3)
            core = convert(base)
            if core in (r"\sum", r"\prod", r"\int", r"\lim", r"\bigcup", r"\bigcap"):
                tex = f"{core}_{{{convert(below)}}}^{{{convert(above)}}}"
            else:
                tex = rf"\underset{{{convert(below)}}}{{\overset{{{convert(above)}}}{{{core}}}}}"
        elif name == "mfenced":
            opening, closing = node.get("open", "("), node.get("close", ")")
            separator = (node.get("separators", ",").strip() or ",")[0]
            inner = f"{separator} ".join(convert(item) for item in kids(node))
            tex = rf"\left{fence_character(opening)}{inner}\right{fence_character(closing)}"
        elif name == "mtable":
            rows = []
            for line in kids(node):
                if tag(line) != "mtr":
                    raise ValueError(f"<{tag(line)}> in a table")
                rows.append(" & ".join(row(kids(cell)) for cell in kids(line)))
            tex = r"\begin{matrix} " + r" \\ ".join(rows) + r" \end{matrix}"
        else:
            raise ValueError(f"<{name}>")
        colour = colour_of(node)
        if colour and colour != uniform:
            tex = rf"\textcolor{{{colour}}}{{{tex}}}"
        return tex

    tokens = [node for node in root.iter() if tag(node) in ("mi", "mn", "mo", "mtext", "ms")]
    colours = {colour_of(node) for node in tokens}
    uniform = colours.pop() if len(colours) == 1 else None
    tex = convert(root)
    return rf"\textcolor{{{uniform}}}{{{tex}}}" if uniform else tex


_UNBRACED = re.compile(
    r"(\\(?:dot|ddot|hat|widehat|bar|vec|tilde|widetilde|check|breve|acute|grave|overline|underline|mathbf|"
    r"mathrm|mathit|mathcal|mathbb|mathsf|mathtt|mathfrak|boldsymbol))\s*(\\[A-Za-z]+\s*\{[^{}]*\})")


def equation_tex(source: str) -> str | None:
    """The TeX of an equation Keynote kept (LaTeX, or MathML), on one line; ``None`` where
    its MathML has no TeX."""

    text = source.strip()
    if text.startswith("<"):
        try:
            text = mathml_tex(text)
        except ValueError:
            return None
    else:
        text = re.sub(r"(?<!\\)%[^\n]*", "", text)
    text = " ".join(text.split())
    while True:
        braced = _UNBRACED.sub(r"\1{\2}", text)
        if braced == text:
            break
        text = braced
    return text or None
