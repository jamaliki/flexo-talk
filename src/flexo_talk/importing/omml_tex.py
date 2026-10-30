# ruff: noqa: RUF001, RUF002 -- maths symbols are the point here.
"""Office Math (OMML) read back as LaTeX: an equation PowerPoint or Word made, as Flexo's maths.

The reverse of ``flexo_talk.omml``: fractions, radicals, scripts (before a base too), big
operators with their limits, growing brackets with their separators, accents, bars, braces
and arrows over and under, limits, named functions, matrices, equation arrays, boxes and
phantoms. A letter is italic unless its run says otherwise, as in TeX; words set upright in
a run of their own (``m:nor``) are ``\\text``; a script face (``m:scr``) is
``\\mathcal``, ``\\mathbb``... Symbols are written as TeX's commands (``α`` as ``\\alpha``).
What has no TeX at all is written as the characters it shows.
"""

from __future__ import annotations

import re

from flexo.texmath import ACCENTS, BIG_OPERATORS, BINARY, GREEK, NAMED, NAMED_LIMITS, ORDINARY, RELATION
from lxml import etree

M = "http://schemas.openxmlformats.org/officeDocument/2006/math"


def _q(name: str) -> str:
    return f"{{{M}}}{name}"


def _command_table() -> dict[str, str]:
    """Each symbol TeX names, by the character it draws: the first name of each, the plain
    one preferred (``\\le`` and ``\\leq`` both draw ≤)."""

    table: dict[str, str] = {}
    for source in (GREEK, ORDINARY, BINARY, RELATION):
        for name, character in source.items():
            if not name.isalpha() or not isinstance(character, str) or len(character) != 1:
                continue
            if name.startswith("var") and character in table:
                continue
            table.setdefault(character, name)
    preferred = {"≤": "leq", "≥": "geq", "≠": "neq", "→": "rightarrow", "←": "leftarrow", "⋅": "cdot",
                 "·": "cdot", "∼": "sim", "∣": "mid", "∖": "setminus", "¬": "neg", "∧": "wedge", "∨": "vee",
                 "′": "prime"}
    table.update(preferred)
    return table


_COMMANDS = _command_table()
_BIG = {character: name for name, character in BIG_OPERATORS.items() if name not in ("intop", "smallint")}
_ACCENT = {mark: name for name, mark in ACCENTS.items() if not name.startswith("wide")}
_ACCENT.update({"ˆ": "hat", "^": "hat", "˜": "tilde", "~": "tilde", "¯": "bar", "‾": "overline",
                "→": "vec", "⃖": "overleftarrow", "˙": "dot", "¨": "ddot", "ˇ": "check",
                "´": "acute", "`": "grave", "˘": "breve"})
_FUNCTIONS = NAMED | NAMED_LIMITS
_SCRIPTS = {"script": "mathcal", "double-struck": "mathbb", "fraktur": "mathfrak", "sans-serif": "mathsf",
            "monospace": "mathtt"}
_FENCES = {"(": "(", ")": ")", "[": "[", "]": "]", "{": "\\{", "}": "\\}", "|": "|", "‖": "\\|", "⟨": "\\langle",
           "⟩": "\\rangle", "⌊": "\\lfloor", "⌋": "\\rfloor", "⌈": "\\lceil", "⌉": "\\rceil", "": ".",
           "〈": "\\langle", "〉": "\\rangle"}
_SPECIAL = {"#": "\\#", "%": "\\%", "&": "\\&", "$": "\\$", "_": "\\_", "{": "\\{", "}": "\\}", "\\": "\\backslash ",
            "~": "\\sim ", "^": "\\hat{}"}
_SPACES = {" ": "\\,", " ": "\\;", " ": "\\;", " ": "\\enspace ", " ": "\\quad ",
           " ": "\\,", " ": "\\:", " ": "\\ ", " ": "\\,", "​": ""}


def _join(parts: list[str]) -> str:
    """TeX pieces side by side, a command kept apart from a letter after it (``\\alpha x``)."""

    out = ""
    for part in parts:
        if not part:
            continue
        if re.search(r"\\[A-Za-z]+$", out) and re.match(r"[A-Za-z0-9]", part):
            out += " "
        out += part
    return out


def _group(tex: str) -> str:
    """A script's base or argument: bare where it is one symbol, braced otherwise."""

    tex = tex.strip()
    if len(tex) == 1 or re.fullmatch(r"\\[A-Za-z]+(?:\{[^{}]*\})?", tex) or (
            tex.startswith("{") and _balanced_group(tex)):
        return tex
    return f"{{{tex}}}"


def _balanced_group(tex: str) -> bool:
    depth = 0
    for index, character in enumerate(tex):
        if character == "{" and (index == 0 or tex[index - 1] != "\\"):
            depth += 1
        elif character == "}" and tex[index - 1] != "\\":
            depth -= 1
            if depth == 0 and index != len(tex) - 1:
                return False
    return depth == 0


class _Reader:
    def __init__(self) -> None:
        self.colour: str | None = None

    def children(self, node: etree._Element) -> str:
        return _join([self.node(child) for child in node if isinstance(child.tag, str)])

    def part(self, node: etree._Element | None, name: str) -> str:
        found = node.find(_q(name)) if node is not None else None
        return self.children(found) if found is not None else ""

    def prop(self, node: etree._Element, props: str, name: str, default: str | None = None) -> str | None:
        found = node.find(f"{_q(props)}/{_q(name)}")
        if found is None:
            return default
        return found.get(_q("val"), default if default is not None else "1")

    def node(self, node: etree._Element) -> str:
        tag = etree.QName(node).localname if isinstance(node.tag, str) else ""
        if etree.QName(node).namespace != M:
            if tag == "AlternateContent":
                choice = node.find("{http://schemas.openxmlformats.org/markup-compatibility/2006}Choice")
                return self.children(choice) if choice is not None else ""
            return ""
        handler = getattr(self, f"_{tag}", None)
        if handler is not None:
            return handler(node)
        return self.children(node)

    # -- runs --

    def _r(self, node: etree._Element) -> str:
        text = "".join(t.text or "" for t in node.iter(_q("t")))
        if not text:
            return ""
        props = node.find(_q("rPr"))
        normal = props is not None and props.find(_q("nor")) is not None
        found = props.find(_q("sty")) if props is not None else None
        style = found.get(_q("val")) if found is not None else None
        found = props.find(_q("scr")) if props is not None else None
        script = found.get(_q("val")) if found is not None else None
        if normal:
            body = "".join(_SPECIAL.get(character, character) for character in text)
            return f"\\text{{{body}}}" if body.strip() else "\\ "
        word = text.strip()
        if word in _FUNCTIONS and style == "p":
            return f"\\{word}"
        if style == "p" and word.isalpha() and word.isascii() and len(word) > 1:
            return f"\\mathrm{{{word}}}"
        parts = [self.character(character, style) for character in text]
        tex = _join(parts)
        if script in _SCRIPTS:
            return f"\\{_SCRIPTS[script]}{{{tex}}}"
        if style == "b":
            return f"\\mathbf{{{tex}}}"
        if style == "bi":
            return f"\\boldsymbol{{{tex}}}"
        if style == "p" and any(character.isalpha() and character.isascii() for character in text):
            return f"\\mathrm{{{tex}}}"
        return tex

    def character(self, character: str, style: str | None = None) -> str:
        if character in _SPACES:
            return _SPACES[character]
        if character == " ":
            return " "
        if character == "−":
            return "-"
        if character in "#%&$_{}\\":
            return _SPECIAL[character]
        if character == "∗":
            return "*"
        if character in _BIG:
            return f"\\{_BIG[character]}"
        if character in _COMMANDS:
            name = _COMMANDS[character]
            return f"\\{name}"
        if character in ("′", "'"):
            return "'"
        return character

    # -- structures --

    def _f(self, node: etree._Element) -> str:
        kind = self.prop(node, "fPr", "type", "bar")
        numerator, denominator = self.part(node, "num"), self.part(node, "den")
        if kind == "noBar":
            return f"{{{numerator} \\atop {denominator}}}"
        if kind == "lin":
            return f"{_group(numerator)}/{_group(denominator)}"
        return f"\\frac{{{numerator}}}{{{denominator}}}"

    def _rad(self, node: etree._Element) -> str:
        degree = self.part(node, "deg")
        hidden = self.prop(node, "radPr", "degHide") in ("1", "on", "true")
        body = self.part(node, "e")
        if degree and not hidden:
            return f"\\sqrt[{degree}]{{{body}}}"
        return f"\\sqrt{{{body}}}"

    def _sSub(self, node: etree._Element) -> str:
        return f"{_group(self.part(node, 'e')) or '{}'}_{{{self.part(node, 'sub')}}}"

    def _sSup(self, node: etree._Element) -> str:
        base, sup = self.part(node, "e"), self.part(node, "sup")
        if sup.strip() in ("'", "''", "\\prime"):
            return f"{_group(base)}{sup.replace(chr(92) + 'prime', chr(39))}"
        return f"{_group(base) or '{}'}^{{{sup}}}"

    def _sSubSup(self, node: etree._Element) -> str:
        base = _group(self.part(node, "e")) or "{}"
        return f"{base}_{{{self.part(node, 'sub')}}}^{{{self.part(node, 'sup')}}}"

    def _sPre(self, node: etree._Element) -> str:
        return f"{{}}_{{{self.part(node, 'sub')}}}^{{{self.part(node, 'sup')}}}{_group(self.part(node, 'e'))}"

    def _nary(self, node: etree._Element) -> str:
        character = self.prop(node, "naryPr", "chr", "∫") or "∫"
        operator = f"\\{_BIG[character]}" if character in _BIG else self.character(character)
        under = self.prop(node, "naryPr", "limLoc", "") == "undOvr"
        sub, sup = self.part(node, "sub"), self.part(node, "sup")
        hide_sub = self.prop(node, "naryPr", "subHide") in ("1", "on", "true")
        hide_sup = self.prop(node, "naryPr", "supHide") in ("1", "on", "true")
        limits = ""
        if sub and not hide_sub:
            limits += f"_{{{sub}}}"
        if sup and not hide_sup:
            limits += f"^{{{sup}}}"
        if under and character in "∫∬∭∮" and limits:
            operator += "\\limits"
        body = self.part(node, "e")
        return _join([operator + limits, " ", body]) if body else operator + limits

    def _d(self, node: etree._Element) -> str:
        begin = self.prop(node, "dPr", "begChr", "(")
        end = self.prop(node, "dPr", "endChr", ")")
        separator = self.prop(node, "dPr", "sepChr", "|")
        parts = [self.children(child) for child in node.findall(_q("e"))]
        inner = f" {_FENCES.get(separator or '|', separator)} ".join(parts) if len(parts) > 1 else "".join(parts)
        if len(parts) > 1 and separator == "|":
            inner = " \\middle| ".join(parts)
        left = _FENCES.get(begin if begin is not None else "(", begin or ".")
        right = _FENCES.get(end if end is not None else ")", end or ".")
        if inner.lstrip().startswith("\\begin{matrix}") and left in ("(", "[", "|", "\\{", "\\|") \
                and right in (")", "]", "|", "\\}", "\\|"):
            environment = {"(": "pmatrix", "[": "bmatrix", "|": "vmatrix", "\\{": "Bmatrix", "\\|": "Vmatrix"}[left]
            return inner.replace("\\begin{matrix}", f"\\begin{{{environment}}}").replace(
                "\\end{matrix}", f"\\end{{{environment}}}")
        if left == "\\{" and right == "." and inner.lstrip().startswith("\\begin{matrix}"):
            return inner.replace("\\begin{matrix}", "\\begin{cases}").replace("\\end{matrix}", "\\end{cases}")
        return f"\\left{left}{inner}\\right{right}"

    def _acc(self, node: etree._Element) -> str:
        mark = self.prop(node, "accPr", "chr", "̂") or "̂"
        name = _ACCENT.get(mark, "hat")
        body = self.part(node, "e")
        if name in ("hat", "tilde") and len(body.strip()) > 2:
            name = "wide" + name
        return f"\\{name}{{{body}}}"

    def _bar(self, node: etree._Element) -> str:
        top = self.prop(node, "barPr", "pos", "bot") == "top"
        return f"\\{'overline' if top else 'underline'}{{{self.part(node, 'e')}}}"

    def _groupChr(self, node: etree._Element) -> str:
        character = self.prop(node, "groupChrPr", "chr", "⏟") or "⏟"
        top = self.prop(node, "groupChrPr", "pos", "bot") == "top"
        body = self.part(node, "e")
        if character in "⏞⏟":
            return f"\\{'overbrace' if character == '⏞' else 'underbrace'}{{{body}}}"
        arrow = self.character(character)
        if body.strip().replace("\\enspace", "").strip() and arrow.startswith("\\"):
            plain = body.replace("\\enspace ", "").strip()
            command = {"\\rightarrow": "xrightarrow", "\\leftarrow": "xleftarrow"}.get(arrow)
            if command and not top:
                return f"\\{command}{{{plain}}}"
        if top:
            return f"\\overset{{{arrow}}}{{{body}}}"
        return f"\\underset{{{arrow}}}{{{body}}}"

    def _limLow(self, node: etree._Element) -> str:
        base, limit = self.part(node, "e"), self.part(node, "lim")
        name = base.strip()
        if (name.startswith("\\") and name[1:] in _FUNCTIONS) or name.startswith("\\underbrace"):
            return f"{name}_{{{limit}}}"
        if name.startswith("\\xrightarrow{") or name.startswith("\\xleftarrow{"):
            return name.replace("arrow{", f"arrow[{limit}]{{", 1)
        return f"\\underset{{{limit}}}{{{base}}}"

    def _limUpp(self, node: etree._Element) -> str:
        base, limit = self.part(node, "e"), self.part(node, "lim")
        if base.strip().startswith("\\overbrace"):
            return f"{base.strip()}^{{{limit}}}"
        return f"\\overset{{{limit}}}{{{base}}}"

    def _func(self, node: etree._Element) -> str:
        name = self.part(node, "fName").strip()
        word = re.sub(r"^\\mathrm\{(.*)\}$", r"\1", name)
        if word in _FUNCTIONS:
            name = f"\\{word}"
        elif re.fullmatch(r"[A-Za-z]+", word):
            name = f"\\operatorname{{{word}}}"
        return _join([name, " ", self.part(node, "e")])

    def _m(self, node: etree._Element) -> str:
        rows = []
        for row in node.findall(_q("mr")):
            rows.append(" & ".join(self.children(cell) for cell in row.findall(_q("e"))))
        return "\\begin{matrix}" + " \\\\ ".join(rows) + "\\end{matrix}"

    def _eqArr(self, node: etree._Element) -> str:
        lines = []
        for line in node.findall(_q("e")):
            lines.append(self.aligned(line))
        aligned = any("&" in line for line in lines)
        body = " \\\\ ".join(lines)
        return f"\\begin{{{'aligned' if aligned else 'gathered'}}}{body}\\end{{{'aligned' if aligned else 'gathered'}}}"

    def aligned(self, line: etree._Element) -> str:
        """A line of an equation array, ``&`` where a run says it is aligned at (``m:aln``)."""

        parts = []
        for child in line:
            if not isinstance(child.tag, str):
                continue
            mark = child.find(f"{_q('rPr')}/{_q('aln')}") if etree.QName(child).localname == "r" else None
            if mark is None:
                inner = child.find(f".//{_q('aln')}")
                if inner is not None and etree.QName(child).localname != "r":
                    parts.append("&")
                    parts.append(self.node(child))
                    continue
            if mark is not None:
                parts.append("&")
            parts.append(self.node(child))
        return _join(parts)

    def _box(self, node: etree._Element) -> str:
        return self.part(node, "e")

    def _borderBox(self, node: etree._Element) -> str:
        return f"\\boxed{{{self.part(node, 'e')}}}"

    def _phant(self, node: etree._Element) -> str:
        shown = self.prop(node, "phantPr", "show", "1") not in ("0", "off", "false")
        body = self.part(node, "e")
        return body if shown else f"\\phantom{{{body}}}"

    def _oMathPara(self, node: etree._Element) -> str:
        lines = [self.children(math) for math in node.findall(_q("oMath"))]
        return " \\\\ ".join(line for line in lines if line)

    def _oMath(self, node: etree._Element) -> str:
        return self.children(node)

    def _rPr(self, node: etree._Element) -> str:
        return ""

    _ctrlPr = _rPr
    _fPr = _rPr
    _radPr = _rPr
    _naryPr = _rPr
    _dPr = _rPr
    _accPr = _rPr
    _barPr = _rPr
    _groupChrPr = _rPr
    _limLowPr = _rPr
    _limUppPr = _rPr
    _funcPr = _rPr
    _mPr = _rPr
    _eqArrPr = _rPr
    _sSubPr = _rPr
    _sSupPr = _rPr
    _sSubSupPr = _rPr
    _sPrePr = _rPr
    _boxPr = _rPr
    _borderBoxPr = _rPr
    _phantPr = _rPr
    _oMathParaPr = _rPr


def omml_tex(node: etree._Element) -> str:
    """An ``m:oMath`` or ``m:oMathPara`` (or anything holding one) as TeX, on one line."""

    tex = _Reader().node(node) if etree.QName(node).namespace == M else _Reader().children(node)
    tex = re.sub(r"\s+", " ", tex).strip()
    # (Office Math spaces its own operators; TeX spaces them as it sets them.)
    return tex


def parse_omml(text: str | bytes) -> str:
    """OMML in XML text as TeX."""

    parser = etree.XMLParser(resolve_entities=False, no_network=True)
    root = etree.fromstring(text.encode("utf-8") if isinstance(text, str) else text, parser)
    return omml_tex(root)
