# ruff: noqa: RUF001 -- maths symbols are the point here.
"""LaTeX maths as Office Math (OMML): equations PowerPoint edits as its own.

A formula flexo reads (``flexo.texmath.parse``) is written as the Office Math that
PowerPoint's equation editor makes: fractions, radicals, scripts, big operators with
their limits, growing brackets, accents, bars, braces, matrices and cases. PowerPoint
sets it in its maths font (Cambria Math); a slide program that does not read Office
Math shows flexo's own drawing of it instead (see ``flexo_talk.pptx``).
"""

from __future__ import annotations

from xml.sax.saxutils import escape

from flexo.texmath import (
    BIN,
    INTEGRALS,
    REL,
    Accent,
    Array,
    Arrow,
    Big,
    Boxed,
    Brace,
    Classed,
    Coloured,
    Fenced,
    Fraction,
    Group,
    HLine,
    Infix,
    Line,
    Middle,
    Mistake,
    Negated,
    NewRow,
    Operator,
    Phantom,
    Radical,
    Scripts,
    Space,
    Stack,
    StyleChange,
    Sym,
    Tab,
    Text,
    _implicit_rows,
    parse,
)

M = "http://schemas.openxmlformats.org/officeDocument/2006/math"
A = "http://schemas.openxmlformats.org/drawingml/2006/main"
A14 = "http://schemas.microsoft.com/office/drawing/2010/main"
MATHS_FONT = "Cambria Math"
"""The face PowerPoint sets its equations in: the one maths font every copy of Office has."""

_SCRIPTS = {"cal": "script", "scr": "script", "bb": "double-struck", "frak": "fraktur",
            "sf": "sans-serif", "tt": "monospace"}
_STYLES = {"rm": "p", "bf": "b", "it": "i", "bi": "bi"}
_ERROR = "C0392B"


class _Writer:
    def __init__(self, size: float, colour: str | None, resolve) -> None:
        self.size = size
        self.colour = colour
        self.resolve = resolve

    # -- runs --

    def run(self, text: str, *, style: str | None = None, script: str | None = None, normal: bool = False,
            italic: bool | None = None, colour: str | None = None) -> str:
        if not text:
            return ""
        props = ""
        if normal:
            props = "<m:nor/>"
        else:
            if script:
                props += f'<m:scr m:val="{script}"/>'
            if style:
                props += f'<m:sty m:val="{style}"/>'
        if italic is None:
            italic = style in {"i", "bi"} or (style is None and not normal and not script
                                              and any(ch.isalpha() and (ch.isascii() or ch.islower()) for ch in text))
        bold = style in {"b", "bi"}
        fill = colour or self.colour
        paint = f'<a:solidFill><a:srgbClr val="{fill}"/></a:solidFill>' if fill else ""
        space = ' xml:space="preserve"' if text != text.strip() else ""
        return (
            f"<m:r>{f'<m:rPr>{props}</m:rPr>' if props else ''}"
            f'<a:rPr lang="en-GB" sz="{round(self.size * 100)}" b="{int(bold)}" i="{int(italic)}" dirty="0">'
            f'{paint}<a:latin typeface="{MATHS_FONT}"/><a:cs typeface="{MATHS_FONT}"/></a:rPr>'
            f"<m:t{space}>{escape(text)}</m:t></m:r>"
        )

    # -- lists of atoms --

    def items(self, items: list) -> str:
        out: list[str] = []
        index = 0
        while index < len(items):
            item = items[index]
            index += 1
            operator = item.base if isinstance(item, Scripts) else item
            if isinstance(operator, Operator) and operator.symbol:
                # A big operator takes what follows it, up to a relation or sign, as its
                # body; a named one (log, max) as its argument, so it is spaced as one.
                body: list = []
                while index < len(items) and not _ends_body(items[index]):
                    body.append(items[index])
                    index += 1
                if not operator.named:
                    out.append(self.nary(operator, item if isinstance(item, Scripts) else None, body))
                elif body:
                    out.append(f"<m:func><m:fName>{self.atom(item)}</m:fName><m:e>{self.items(body)}</m:e></m:func>")
                else:
                    out.append(self.atom(item))
                continue
            out.append(self.atom(item))
        return "".join(out)

    def nary(self, operator: Operator, scripts: Scripts | None, body: list) -> str:
        limits = operator.limits
        if limits is None:
            limits = operator.symbol not in INTEGRALS
        sub = scripts.sub if scripts else None
        sup = scripts.sup if scripts else None
        props = (f'<m:chr m:val="{escape(operator.symbol)}"/>'
                 f'<m:limLoc m:val="{"undOvr" if limits else "subSup"}"/>'
                 f"{'' if sub else '<m:subHide m:val=\"1\"/>'}{'' if sup else '<m:supHide m:val=\"1\"/>'}")
        # With nothing after it, an empty body would show as an empty slot: a zero-width one.
        inside = self.items(body) if body else self.run("\u200b", style="p", italic=False)
        return (f"<m:nary><m:naryPr>{props}</m:naryPr><m:sub>{self.items(sub or [])}</m:sub>"
                f"<m:sup>{self.items(sup or [])}</m:sup><m:e>{inside}</m:e></m:nary>")

    # -- atoms --

    def atom(self, item: object) -> str:
        if isinstance(item, Sym):
            return self.sym(item)
        if isinstance(item, Text):
            return self.run(item.words, normal=True, italic=item.font == "it")
        if isinstance(item, Group | Classed):
            return self.items(item.items if isinstance(item, Group) else item.body)
        if isinstance(item, Scripts):
            return self.scripts(item)
        if isinstance(item, Operator):
            return self.operator(item)
        if isinstance(item, Fraction):
            fraction = (f"<m:f>{'' if item.rule else '<m:fPr><m:type m:val=\"noBar\"/></m:fPr>'}"
                        f"<m:num>{self.items(item.numerator)}</m:num>"
                        f"<m:den>{self.items(item.denominator)}</m:den></m:f>")
            return self.fenced(item.left, [fraction], item.right) if item.left or item.right else fraction
        if isinstance(item, Radical):
            degree = self.items(item.degree) if item.degree else ""
            hide = "" if degree else '<m:radPr><m:degHide m:val="1"/></m:radPr>'
            return f"<m:rad>{hide}<m:deg>{degree}</m:deg><m:e>{self.items(item.body)}</m:e></m:rad>"
        if isinstance(item, Fenced):
            parts: list[list] = [[]]
            separators: list[str] = []
            for thing in item.body:
                if isinstance(thing, Middle):
                    separators.append(thing.delimiter)
                    parts.append([])
                else:
                    parts[-1].append(thing)
            return self.fenced(item.left, [self.items(part) for part in parts], item.right,
                               separator=separators[0] if separators else None)
        if isinstance(item, Middle | Big):
            return self.run(item.delimiter, style="p", italic=False)
        if isinstance(item, Accent):
            return (f'<m:acc><m:accPr><m:chr m:val="{escape(item.mark)}"/></m:accPr>'
                    f"<m:e>{self.items(item.body)}</m:e></m:acc>")
        if isinstance(item, Line):
            return (f'<m:bar><m:barPr><m:pos m:val="{"top" if item.over else "bot"}"/></m:barPr>'
                    f"<m:e>{self.items(item.body)}</m:e></m:bar>")
        if isinstance(item, Brace):
            char, pos = ("⏞", "top") if item.over else ("⏟", "bot")
            brace = (f'<m:groupChr><m:groupChrPr><m:chr m:val="{char}"/><m:pos m:val="{pos}"/>'
                     f'<m:vertJc m:val="{"bot" if item.over else "top"}"/></m:groupChrPr>'
                     f"<m:e>{self.items(item.body)}</m:e></m:groupChr>")
            if not item.label:
                return brace
            tag = "limUpp" if item.over else "limLow"
            return f"<m:{tag}><m:e>{brace}</m:e><m:lim>{self.items(item.label)}</m:lim></m:{tag}>"
        if isinstance(item, Arrow):
            if item.body is not None:
                pos = "bot" if item.below else "top"
                return (f'<m:groupChr><m:groupChrPr><m:chr m:val="{escape(item.char)}"/><m:pos m:val="{pos}"/>'
                        f"</m:groupChrPr><m:e>{self.items(item.body)}</m:e></m:groupChr>")
            room = self.run("\u2002", style="p", italic=False)
            words = f"{room}{self.items(item.over or [])}{room}"
            # The arrow under its words, and on the line (its words raised above it).
            arrow = (f'<m:groupChr><m:groupChrPr><m:chr m:val="{escape(item.char)}"/><m:pos m:val="bot"/>'
                     f'<m:vertJc m:val="bot"/></m:groupChrPr><m:e>{words}</m:e></m:groupChr>')
            if item.under:
                arrow = f"<m:limLow><m:e>{arrow}</m:e><m:lim>{self.items(item.under)}</m:lim></m:limLow>"
            # PowerPoint spaces it as a character, not as the relation it is: a thick space each side.
            thick = self.run("\u2005", style="p", italic=False)
            return f"{thick}{arrow}{thick}"
        if isinstance(item, Stack):
            base = self.items(item.base)
            if item.over is not None:
                base = f"<m:limUpp><m:e>{base}</m:e><m:lim>{self.items(item.over)}</m:lim></m:limUpp>"
            if item.under is not None:
                base = f"<m:limLow><m:e>{base}</m:e><m:lim>{self.items(item.under)}</m:lim></m:limLow>"
            return base
        if isinstance(item, Array):
            return self.array(item)
        if isinstance(item, Space):
            return self.run(_space(item.em), style="p", italic=False) if item.em > 0 else ""
        if isinstance(item, Coloured):
            before = self.colour
            self.colour = self.resolve(item.colour) or before
            try:
                return self.items(item.body)
            finally:
                self.colour = before
        if isinstance(item, Phantom):
            return (f'<m:phant><m:phantPr><m:show m:val="0"/></m:phantPr>'
                    f"<m:e>{self.items(item.body)}</m:e></m:phant>")
        if isinstance(item, Boxed):
            return f"<m:borderBox><m:e>{self.items(item.body)}</m:e></m:borderBox>"
        if isinstance(item, Negated):
            return self.atom(item.body) if item.body is not None else ""
        if isinstance(item, Mistake):
            return self.run(item.words, normal=True, italic=False, colour=_ERROR)
        if isinstance(item, StyleChange | Tab | NewRow | HLine | Infix):
            return ""
        return ""

    def sym(self, item: Sym) -> str:
        if item.font in _SCRIPTS:
            return self.run(item.char, style="p", script=_SCRIPTS[item.font], italic=False)
        if item.font in _STYLES:
            return self.run(item.char, style=_STYLES[item.font])
        if item.kind in {BIN, REL} or not item.char.isalpha():
            return self.run(item.char, style="p", italic=False)
        return self.run(item.char)

    def operator(self, item: Operator) -> str:
        if not item.symbol:
            return ""
        return self.run(item.symbol, style="p", italic=False)

    def scripts(self, item: Scripts) -> str:
        base = item.base
        if isinstance(base, Operator) and base.named and base.limits is not False and item.sub and not item.sup:
            # lim_{n→∞}: its limit under it, as PowerPoint's own lim is.
            return (f"<m:limLow><m:e>{self.operator(base)}</m:e>"
                    f"<m:lim>{self.items(item.sub)}</m:lim></m:limLow>")
        body = self.atom(base) if base is not None else ""
        if item.sup is not None and item.sub is not None:
            return (f"<m:sSubSup><m:e>{body}</m:e><m:sub>{self.items(item.sub)}</m:sub>"
                    f"<m:sup>{self.items(item.sup)}</m:sup></m:sSubSup>")
        if item.sub is not None:
            return f"<m:sSub><m:e>{body}</m:e><m:sub>{self.items(item.sub)}</m:sub></m:sSub>"
        return f"<m:sSup><m:e>{body}</m:e><m:sup>{self.items(item.sup or [])}</m:sup></m:sSup>"

    def fenced(self, left: str, parts: list[str], right: str, *, separator: str | None = None) -> str:
        props = (f'<m:begChr m:val="{escape(left)}"/>'
                 f"{f'<m:sepChr m:val=\"{escape(separator)}\"/>' if separator else ''}"
                 f'<m:endChr m:val="{escape(right)}"/>')
        return f"<m:d><m:dPr>{props}</m:dPr>{''.join(f'<m:e>{part}</m:e>' for part in parts)}</m:d>"

    def array(self, item: Array) -> str:
        rows = item.rows or [[[]]]
        if item.kind in {"aligned", "gathered"}:
            # PowerPoint's own equation array: a line each, aligned where each pair meets.
            lines = []
            for row in rows:
                line = ""
                for column, content in enumerate(row):
                    written = self.items([Group([]), *content] if column % 2 == 1 else content)
                    if column % 2 == 1 and item.kind == "aligned":
                        written = _aligned(written)
                    line += written
                lines.append(f"<m:e>{line}</m:e>")
            return f"<m:eqArr>{''.join(lines)}</m:eqArr>"
        count = max(len(row) for row in rows)
        columns = (item.columns or "c").replace(" ", "")
        justify = []
        for column in range(count):
            if item.kind == "aligned":
                align = "r" if column % 2 == 0 else "l"
            else:
                align = columns[column] if column < len(columns) else columns[-1]
            justify.append({"l": "left", "r": "right"}.get(align, "center"))
        mcs = "".join(f'<m:mc><m:mcPr><m:count m:val="1"/><m:mcJc m:val="{jc}"/></m:mcPr></m:mc>'
                      for jc in justify)
        spacing = '<m:cGp m:val="0"/>' if item.kind == "aligned" else ""
        body = ""
        for row in rows:
            cells = []
            for column in range(count):
                content = row[column] if column < len(row) else []
                if item.kind == "aligned" and column % 2 == 1:
                    content = [Group([]), *content]
                cells.append(f"<m:e>{self.items(content)}</m:e>")
            body += f"<m:mr>{''.join(cells)}</m:mr>"
        matrix = f"<m:m><m:mPr>{spacing}<m:mcs>{mcs}</m:mcs></m:mPr>{body}</m:m>"
        if item.left or item.right:
            return self.fenced(item.left, [matrix], item.right)
        return matrix


def _aligned(written: str) -> str:
    """Office Math whose first run is its line's alignment point (``m:aln``)."""

    at = written.find("<m:r>")
    if at < 0:
        return written
    after = at + len("<m:r>")
    if written.startswith("<m:rPr>", after):
        return written[:after] + "<m:rPr><m:aln/>" + written[after + len("<m:rPr>"):]
    return written[:after] + "<m:rPr><m:aln/></m:rPr>" + written[after:]


def _ends_body(item: object) -> bool:
    """Whether ``item`` ends a big operator's body: a relation, a sign between terms."""

    return (isinstance(item, Sym) and item.kind in {REL, BIN}) or isinstance(item, Tab | NewRow)


def _space(em: float) -> str:
    if em >= 1.0:
        return " " * round(em)
    if em >= 0.5:
        return " "
    if em >= 5 / 18:
        return " "
    if em >= 4 / 18:
        return " "
    return " "


def omml(source: str, *, size: float, colour: str | None = None, display: bool = False,
         align: str = "middle", resolve=lambda colour: None) -> str:
    """``source`` as Office Math, in PowerPoint's ``a14:m`` wrapper: a line of its own
    (``display``, aligned as ``align`` says) or a formula within words.

    ``colour`` is the words' colour (``rrggbb``); ``resolve`` turns a colour the
    formula names (``\\color{accent}``) into one.
    """

    display = display or source.lstrip().startswith("\\displaystyle")
    items, _ = parse(source)
    items = _implicit_rows(items, display)
    body = _Writer(size, colour, resolve).items(items)
    maths = f"<m:oMath>{body}</m:oMath>"
    if display:
        jc = {"start": "left", "end": "right"}.get(align, "centerGroup")
        maths = f'<m:oMathPara><m:oMathParaPr><m:jc m:val="{jc}"/></m:oMathParaPr>{maths}</m:oMathPara>'
    return f'<a14:m xmlns:a14="{A14}" xmlns:m="{M}" xmlns:a="{A}">{maths}</a14:m>'
