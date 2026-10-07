"""A slide deck written the way a flexo figure is: a ``with`` block, one theme.

```python
from flexo_talk import Deck

with Deck("results", theme="paper") as deck:
    deck.title("Figures that draw themselves", subtitle="Group meeting")
    with deck.slide("Why") as slide:
        slide.bullets("Figures take hours", "They break when the model changes")
    with deck.slide("The model", layout="two-columns") as slide:
        slide.left.bullets("An encoder", "A head")
        with slide.right.figure() as figure:
            x = figure.root.text("x", "$x$")
            figure.root.block("encoder", label="Encoder", input=x)
deck.build("build")                      # talk.pptx, talk.pdf, and an SVG and PNG per slide
```

Every slide is set in the deck's theme -- any flexo theme or theme file, with
its palette, font, conventions, and hand -- so titles, bullets, and figures
share one typeface and one set of colours. A figure on a slide is compiled at
the width of its place, at a size where its words read at the deck's figure
size, and scaled to fit; it is the same flexo figure a paper would print.
"""

from __future__ import annotations

import re
from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field, fields, replace
from pathlib import Path
from typing import Literal

import flexo
from flexo.ir.semantic import FigureSpec, TextRun
from flexo.markup import math_spans, parse_label
from flexo.style import LayoutStyle, Palette, TypographyStyle
from flexo.themes import resolve_palette, resolve_style, with_tone_roles
from flexo.units import pt

type Layout = Literal[
    "content", "two-columns", "columns", "figure", "title", "section", "statement", "agenda", "blank"
]
LAYOUTS: tuple[str, ...] = (
    "content", "two-columns", "columns", "figure", "title", "section", "statement", "agenda", "blank"
)


class SettingError(ValueError):
    """A setting that cannot be what it was given. ``key`` names the setting, so a deck
    document can say where it is wrong (``slides[2].split``, ``deck.palette``)."""

    def __init__(self, key: str, message: str) -> None:
        super().__init__(message)
        self.key = key


@dataclass(frozen=True, slots=True)
class DeckStyle:
    """The proportions of a deck's slides; the look comes from the flexo theme.

    Sizes are in points on a 16:9 slide of 960 by 540 points (13.33 by 7.5 in).
    """

    width: float = 960.0
    height: float = 540.0
    margin: float = 48.0
    title_size: float = 30.0
    subtitle_size: float = 18.0
    body_size: float = 20.0
    small_size: float = 14.0
    figure_size: float = 13.0
    """The size a figure's words are set at on a slide: figures are scaled so."""
    line_height: float = 1.25
    paragraph_gap: float = 0.55
    """Space between two bullets, as a fraction of the body size."""
    indent: float = 26.0
    """How far each bullet level steps in."""
    column_gap: float = 36.0
    block_gap: float = 18.0
    """Space between two blocks placed one under the other in a region."""
    title_gap: float = 32.0
    """Space between a slide's title and its body."""
    header: Literal["rule", "band", "line", "none"] = "rule"
    """What marks a slide's title: a short accent rule under it, a band of the
    accent colour behind it, a hairline across the slide under it, or nothing."""
    opening: Literal["centred", "left", "band"] = "centred"
    """The title slide: centred, flush left beside an accent bar, or on an accent band."""
    sections: Literal["rule", "fill", "number"] = "rule"
    """Section slides: a rule over the title, the whole slide in the accent colour
    (with the section's number), or the section's number set large in the accent."""
    edge: bool = False
    """A thin accent bar down the left edge of every slide but the opening."""
    align: Literal["auto", "top", "middle"] = "auto"
    """Where a slide's content sits in its body, top to bottom: ``auto`` keeps
    words at the top, sets pictures standing alone a little above the middle of the
    room they have (where the eye takes its middle to be), and centres a column of
    pictures against a taller column of words beside it (a taller column of pictures
    starts level with the words); ``top`` sets everything at the top; ``middle``
    centres the whole content in the body."""
    numbers: bool = True
    """A slide number in the bottom-right corner."""
    title_weight: int | None = None
    """The weight of slide titles; the theme's title weight when unset."""
    title_align: Literal["start", "middle"] = "start"
    """Slide titles flush left, or centred (with their rule)."""
    title_role: str = "ink"
    """The palette role that paints slide titles: ``ink``, or ``tone-1-stroke`` for the accent."""

    def __post_init__(self) -> None:
        # Proportions come from documents and the studio as well as Python: each is
        # checked here, and said in words, before a slide is drawn at that size.
        import math

        for name, (low, high) in _STYLE_NUMBERS.items():
            value = getattr(self, name)
            if isinstance(value, bool) or not isinstance(value, int | float) or not math.isfinite(value):
                raise SettingError(
                    name, f"{name} must be a number from {_said(low)} to {_said(high)}, not {value!r}."
                )
            if not low <= value <= high:
                raise SettingError(
                    name, f"{name} must be between {_said(low)} and {_said(high)}, not {_said(value)}."
                )
        if self.margin * 2 >= min(self.width, self.height):
            raise SettingError("margin", f"A margin of {_said(self.margin)} leaves no room on a "
                                         f"{_said(self.width)} \u00d7 {_said(self.height)} slide.")
        for name, allowed in _STYLE_CHOICES.items():
            if getattr(self, name) not in allowed:
                raise SettingError(
                    name, f"{name} must be one of {', '.join(allowed)}, not {getattr(self, name)!r}."
                )
        for name in ("edge", "numbers"):
            if not isinstance(getattr(self, name), bool):
                raise SettingError(name, f"{name} must be true or false, not {getattr(self, name)!r}.")
        weight = self.title_weight
        if weight is not None and (isinstance(weight, bool) or not isinstance(weight, int) or not 1 <= weight <= 1000):
            raise SettingError("title_weight", "title_weight must be a font weight from 100 to 900 (such as 700), "
                                               f"not {weight!r}.")
        if not isinstance(self.title_role, str) or self.title_role not in _roles():
            # A role no palette has would paint every title black.
            raise SettingError("title_role", "title_role must be a palette role (such as ink, muted-ink or "
                                             f"tone-1-stroke), not {self.title_role!r}.")

    @classmethod
    def look(cls, name: str, **changes: object) -> DeckStyle:
        """A named look (see ``LOOKS``), with any field changed: ``DeckStyle.look("band", body_size=22)``."""

        if name not in LOOKS:
            raise ValueError(f"Unknown look \u201c{name}\u201d. Available looks: {', '.join(LOOKS)}.")
        return cls(**{**LOOKS[name], **changes})  # type: ignore[arg-type]


OKABE_ITO = ("#E69F00", "#56B4E9", "#009E73", "#D55E00", "#0072B2", "#CC79A7")
"""Hues told apart by every eye (Okabe and Ito's), for a plot's series when a theme's
own tones are too few to tell apart."""


def link_colour(palette: Palette, ground: str | None = None) -> str | None:
    """What a link is painted in where the accent cannot tell it from the words -- a
    theme of greys (print, swiss, bauhaus) -- Okabe and Ito's blue, as links are blue,
    made to read on ``ground`` (what the words are set on); ``None`` where a link is the
    accent, as in every other theme."""

    from flexo.colour import chroma, contrast, is_dark, with_contrast

    if chroma(palette.get("tone-1-stroke")) >= 0.03:
        return None
    if ground is None:
        ink, page = palette.get("ink"), palette.get("canvas")
        # The page, unless the words are set over something else (a photograph).
        ground = page if contrast(ink, page) >= 3.0 else ("#ffffff" if is_dark(ink) else "#000000")
    return with_contrast(OKABE_ITO[4], ground, 4.5)


def data_colours(palette: Palette, dark: bool) -> list[str]:
    """Six colours for a plot's series, set to one lightness so they read as a set: the
    theme's tones, each kept only if it can be told from those before it, then Okabe and
    Ito's hues. A theme of greys (swiss, print) leads with its ink."""

    from flexo.colour import chroma, hue_distance, with_lightness

    lightness = 0.74 if dark else 0.58
    tones = [palette.get(f"tone-{index}-stroke") for index in range(1, 7)]
    first = tones[0]
    colours = [palette.get("ink") if chroma(first) < 0.03 else with_lightness(first, lightness, 0.16)]
    for candidate in [*tones[1:], *OKABE_ITO]:
        if len(colours) == 6:
            break
        if chroma(candidate) < 0.03:
            continue
        shown = with_lightness(candidate, lightness, 0.16)
        if all(hue_distance(shown, other) > 0.05 for other in colours):
            colours.append(shown)
    for candidate in OKABE_ITO:  # six, however near the theme's own hues they come
        shown = with_lightness(candidate, lightness, 0.16)
        if len(colours) < 6 and shown not in colours:
            colours.append(shown)
    return colours


MOST_LEVELS = 100
"""More levels than a list on any slide nests."""

_STYLE_NUMBERS: dict[str, tuple[float, float]] = {
    # PowerPoint's slides are 1 to 56 inches each way.
    "width": (72.0, 4032.0), "height": (72.0, 4032.0), "margin": (0.0, 2016.0),
    **{name: (1.0, 400.0) for name in ("title_size", "subtitle_size", "body_size", "small_size", "figure_size")},
    "line_height": (0.5, 5.0), "paragraph_gap": (0.0, 20.0),
    **{name: (0.0, 2016.0) for name in ("indent", "column_gap", "block_gap", "title_gap")},
}
"""DeckStyle's numbers, and the range each may take (points, or a share of a size)."""

_STYLE_CHOICES: dict[str, tuple[str, ...]] = {
    "header": ("rule", "band", "line", "none"),
    "opening": ("centred", "left", "band"),
    "sections": ("rule", "fill", "number"),
    "align": ("auto", "top", "middle"),
    "title_align": ("start", "middle"),
}


def _said(value: float) -> str:
    return f"{value:g}"


# -- settings, checked as they are given (from Python, documents and the studio alike) --


def _number(value: object, what: str, low: float, high: float, example: str) -> float:
    import math

    if isinstance(value, bool) or not isinstance(value, int | float) or not math.isfinite(value):
        raise SettingError(what, f"{what} must be a number, such as {example}, not {value!r}.")
    if not low <= value <= high:
        raise SettingError(what, f"{what} must be between {_said(low)} and {_said(high)}, not {_said(value)}.")
    return float(value)


def _width(value: object) -> float | None:
    """A width in points, or None for the width the place sets."""

    return None if value is None else _number(value, "width", 1.0, 4032.0, "300 (points)")


def _size(value: object, what: str = "size") -> float | None:
    """A size in points, or None for the size the place sets."""

    return None if value is None else _number(value, what, 4.0, 400.0, "20 (points)")


def _flag(value: object, what: str) -> bool:
    if not isinstance(value, bool):
        raise SettingError(what, f"{what} must be true or false, not {value!r}.")
    return value


def _choice(value: object, what: str, allowed: tuple[str, ...]) -> str:
    # "centre" is what a British hand writes for "middle".
    value = {"centre": "middle", "center": "middle"}.get(value, value) if isinstance(value, str) else value
    if value not in allowed:
        raise SettingError(what, f"{what} must be one of {', '.join(allowed)}, not {value!r}.")
    return value


def _words(value: object, what: str) -> str:
    """Words: a string, or a number written as one; never a list, mapping or nothing."""

    if isinstance(value, bool) or not isinstance(value, str | int | float):
        raise SettingError(what, f"{what} must be text, not {value!r}.")
    return str(value)


def _caption(value: object) -> str:
    """A caption's words, on one line of markup ("" for none)."""

    return "" if value is None else " ".join(_words(value, "caption").split())


def _colour(value: object, what: str = "colour") -> str | None:
    """A colour: a palette role (accent, muted, ink...) or #rgb / #rrggbb."""

    if value is None:
        return None
    if not isinstance(value, str) or not value.strip():
        raise SettingError(what, f"{what} must be a palette role (accent, muted) or a #rrggbb colour, not {value!r}.")
    if value.startswith("#") and not re.fullmatch(r"#(?:[0-9a-fA-F]{3}|[0-9a-fA-F]{6}|[0-9a-fA-F]{8})", value):
        raise SettingError(what, f"{what} must be a colour written as #rgb or #rrggbb in hex digits, not {value!r}.")
    if not value.startswith("#") and paint_role(value) not in _roles():
        # A role no palette has would be painted black, whatever the theme.
        raise SettingError(
            what, f"{what} must be accent (accent2, \u2026), muted, ink or a #rrggbb colour, not {value!r}."
        )
    return value


def paint_role(colour: str) -> str:
    """The palette role a block's colour names: ``accent`` (``accent2``...) is a tone's
    stroke, ``muted`` the muted ink, and a role is itself."""

    if colour.startswith("accent"):
        return f"tone-{colour[6:] or 1}-stroke"
    return {"muted": "muted-ink"}.get(colour, colour)


def named_colour(value: object) -> bool:
    """Whether a slide's background names one of its theme's colours (``accent``,
    ``accent2``..., ``ink``, ``muted``) -- painted as the theme paints it, so a change of
    theme repaints the slide -- rather than a ``#rrggbb`` colour or a picture file."""

    return isinstance(value, str) and bool(value) and not value.startswith("#") and paint_role(value) in _roles()


def theme_colour(deck: Deck, name: str) -> str:
    """A colour of a deck's theme by name, as it fills a slide: ``accent`` (``accent2``...)
    the theme's own colour that tone takes -- not its stroke, which is that colour set to the
    theme's outline lightness for lines and words on the page -- and ``ink`` or ``muted``
    as the palette paints them."""

    from flexo.themes import palette_order

    if name.startswith("accent"):
        order = palette_order(deck.theme, deck.palette_name)
        if order:
            return order[(int(name[6:] or 1) - 1) % len(order)]
    return deck.palette.get(paint_role(name))


_ROLES: set[str] = set()


def _roles() -> set[str]:
    """The roles a palette paints: every theme's and palette's are the same."""

    if not _ROLES:
        palette = with_tone_roles(resolve_palette("paper", "default"))
        _ROLES.update(palette.paints, (alias for alias, _ in palette.aliases))
    return _ROLES


LOOKS: dict[str, dict[str, object]] = {
    "classic": {},
    "band": {"header": "band", "opening": "band", "sections": "fill"},
    "editorial": {"header": "line", "opening": "left", "sections": "number", "title_size": 32},
    "keynote": {
        "header": "none", "title_align": "middle", "sections": "fill", "title_size": 34, "body_size": 22,
        "align": "middle",
    },
    "margin": {"edge": True, "opening": "left", "sections": "number", "title_role": "tone-1-stroke"},
}
"""Named looks: the same theme and words, a different page. ``classic`` is a short
rule under each title; ``band`` sets titles on a band of the accent colour and fills
section slides with it; ``editorial`` rules a hairline under each title and numbers
sections large; ``keynote`` centres titles and content, without rules; ``margin``
runs an accent bar down each slide's edge and paints titles in the accent."""


@dataclass(slots=True)
class _Bullets:
    items: list[tuple[int, tuple[TextRun, ...]]]
    size: float | None = None
    numbered: bool = False
    reveal: bool = False
    colour: str | None = None
    """The words' paint, as a text's ``colour``; the bullets and numbers keep the theme's."""
    plain: bool = False
    """Whether its items have no bullets or numbers, their levels kept (Keynote's None)."""


@dataclass(slots=True)
class _Words:
    runs: tuple[TextRun, ...]
    size: float | None = None
    align: Literal["start", "middle", "end"] = "start"
    muted: bool = False
    colour: str | None = None


@dataclass(slots=True)
class _Figure:
    figure: flexo.Figure | FigureSpec
    turn: bool | None = None
    """Whether flexo may lay the figure out turned when that fits its place better: ``None``
    lets it unless its parts were arranged by hand (one put under another beside others),
    ``True`` lets it even so, ``False`` keeps it as written."""
    width: float | None = None
    """The width it is drawn at (points), as its place allows; ``None`` sizes it to its place."""
    said: tuple[str, ...] = ()
    """What is wrong with it that it is drawn despite: said when the slide is drawn."""
    description: str = ""
    """What it shows, for whoever cannot see it; else it is said from its shapes' words."""
    caption: tuple[TextRun, ...] = ()
    """Words set under it, centred, a size smaller: its caption, part of it (Keynote's)."""
    caption_held: bool = False
    """Its caption put there empty (``caption: ""``), to be written: its placeholder drawn
    while editing."""


@dataclass(slots=True)
class _Image:
    source: str
    width: float | None = None
    description: str = ""
    """What the picture shows, in words, for whoever cannot see it: its alt text."""
    caption: tuple[TextRun, ...] = ()
    """Words set under it, centred, a size smaller: its caption, part of it."""
    caption_held: bool = False
    """Its caption put there empty, to be written: its placeholder drawn while editing."""


@dataclass(slots=True)
class _Plot:
    figure: object
    """A matplotlib ``Figure``."""
    aspect: float | None = None
    """Width over height; ``None`` fills the height the place has."""
    drawn: str = ""
    """The SVG it was last drawn as, at the size of its place (what ``convert`` saves)."""


@dataclass(slots=True)
class _Table:
    rows: list[list[tuple[TextRun, ...]]]
    header: bool = True
    align: tuple[str, ...] = ()
    size: float | None = None
    ragged: bool = False
    """Whether its rows were written with different numbers of cells (the short filled)."""
    caption: tuple[TextRun, ...] = ()
    """Words set under it, centred, a size smaller: its caption, part of it."""
    caption_held: bool = False
    """Its caption put there empty, to be written: its placeholder drawn while editing."""


@dataclass(slots=True)
class _Gallery:
    items: list[tuple[str, tuple[TextRun, ...]]]
    """``(picture file, caption runs)`` for each cell."""
    columns: int | None = None
    height: float | None = None
    crop: str | None = None
    size: float | None = None
    align: str | None = None
    """``start`` or ``middle``; ``None`` sets one column flush with the words, a grid centred."""


@dataclass(slots=True)
class _Code:
    lines: list[str]
    size: float | None = None


@dataclass(slots=True)
class _Quote:
    runs: tuple[TextRun, ...]
    by: tuple[TextRun, ...] = ()
    size: float | None = None
    held: bool = False
    """Who said it put there empty (``by: ""``), to be written: its placeholder drawn while
    editing, in its place."""


@dataclass(slots=True)
class _Stats:
    items: list[tuple[tuple[TextRun, ...], tuple[TextRun, ...]]]
    """``(value, label)`` runs for each figure."""
    colour: str | None = None
    size: float | None = None


@dataclass(slots=True)
class _Callout:
    runs: tuple[TextRun, ...]
    title: tuple[TextRun, ...] = ()
    colour: str = "accent"
    size: float | None = None
    held: bool = False
    """Its heading put there empty (``title: ""``), to be written: its placeholder drawn while
    editing."""


@dataclass(slots=True)
class _Missing:
    """What stands for a picture or figure whose file is not there, as the slide is
    edited: a box saying so, where it would be."""

    what: str
    """``picture``, ``figure`` or ``plot``."""
    name: str
    """The file, as the document names it."""
    said: str | None = None
    """What is wrong, when it is not a missing file (a figure that cannot be drawn)."""


@dataclass(slots=True)
class _Math:
    source: str
    """LaTeX maths, without its ``$$``."""
    size: float | None = None
    align: Literal["start", "middle", "end"] = "middle"
    colour: str | None = None


class Reference:
    """A figure or plot named by where it is made (``plots.py:loss``), made only when drawn."""

    def __init__(self, target: str, make) -> None:
        self.target = target
        self._make = make
        self._made: list[object] = []

    def resolve(self) -> object:
        if not self._made:
            self._made.append(self._make())
        return self._made[0]

    def __repr__(self) -> str:
        return f"Reference({self.target!r})"


def _check_theme(theme: object) -> None:
    """A theme is a name flexo knows, or a theme file: said in words, before anything is drawn."""

    from flexo.themes import theme_names

    if isinstance(theme, Path) or (isinstance(theme, str) and theme.lower().endswith((".yaml", ".yml", ".json"))):
        if not Path(theme).is_file():
            raise SettingError("theme", f"Cannot find the theme file \u201c{theme}\u201d.")
        return
    if not isinstance(theme, str):
        raise SettingError("theme", f"theme must name a theme ({', '.join(theme_names())}) or a theme file, "
                                    f"not {theme!r}.")
    if theme not in theme_names():
        raise SettingError("theme", f"Unknown theme \u201c{theme}\u201d. Use one of {', '.join(theme_names())}, "
                                    "or a theme file.")


def _check_settings(settings: dict[str, object]) -> None:
    """A deck's other settings, each said in words under its own name before anything is
    drawn: a wrong one would otherwise fail every slide, or be drawn as Python writes it."""

    from flexo.conventions import parse_conventions
    from flexo.sketch import Sketch, parse_sketch

    def wrong(key: str, said: str) -> SettingError:
        return SettingError(key, f"{key} must be {said}, not {settings[key]!r}.")

    for key in ("font", "title_font", "figure_font"):
        if settings[key] is not None and not isinstance(settings[key], str):
            raise wrong(key, "a font family name, such as IBM Plex Sans")
    palette = settings["palette"]
    if not isinstance(palette, str | Path) and not (
        isinstance(palette, list | tuple) and palette and all(isinstance(colour, str) for colour in palette)
    ):
        raise wrong("palette", "a palette name or a list of #rrggbb colours")
    look = settings["look"]
    if look is not None and not isinstance(look, str):
        raise wrong("look", f"one of {', '.join(LOOKS)}")
    if look is not None and look not in LOOKS:
        raise SettingError("look", f"Unknown look \u201c{look}\u201d. Available looks: {', '.join(LOOKS)}.")
    background = settings["background"]
    if not isinstance(background, bool | str | Path):
        raise wrong("background", "true (the theme's page colour), false, a #rrggbb colour or a picture file")
    if isinstance(background, str) and background.startswith("#"):
        _colour(background, "background")
    for key in ("id", "footer"):
        if settings[key] is not None:
            _words(settings[key], key)
    conventions, sketch = settings["conventions"], settings["sketch"]
    if conventions is not None and not isinstance(conventions, dict):
        raise wrong("conventions", "a mapping of flexo conventions, such as {lines: straight}")
    if sketch is not None and not isinstance(sketch, bool | dict | Sketch):
        raise wrong("sketch", "true (for a hand-drawn look) or a mapping of roughness, passes, fill, paper and seed")
    for key, parse in (("conventions", parse_conventions), ("sketch", parse_sketch)):
        try:
            parse(settings[key])  # type: ignore[operator]
        except (TypeError, ValueError) as error:
            raise SettingError(key, str(error)) from None


def _flexo_said(error: Exception) -> str:
    """A flexo error's words, with its hint, on one line."""

    return " ".join(
        " ".join(filter(None, (item.message, item.hint))) for item in getattr(error, "diagnostics", ())
    ) or str(error)


def made(value: object) -> object:
    """A block's figure or plot, made now if a deck document named it by reference."""

    return value.resolve() if isinstance(value, Reference) else value


type _Block = (
    _Bullets | _Words | _Figure | _Image | _Plot | _Table | _Code | _Gallery | _Quote | _Stats | _Callout
    | _Math | _Missing
)


def accent_field(palette: Palette) -> str:
    """The accent as a field to set words on: itself, or deepened when it is light
    (a dark theme's accent), so light words read on it either way."""

    from flexo.colour import is_dark, with_lightness

    accent = palette.get("tone-1-stroke")
    return accent if is_dark(accent) else with_lightness(accent, 0.45)


_WORDS_IN = r"(?:[^\[\]\n]|\[[^\[\]\n]+\](?:\([^)\s]+\)|\{[^}\s]+\})|\[(?![^\[\]\n]+\](?:\([^)\s]+\)|\{[^}\s]+\})))+"
"""A link's or a colour's words: no bracket in them but those of another link or colour
(a link's words coloured, a colour's words linked), or one on its own that starts
none."""

_INLINE = rf"(\[{_WORDS_IN}\]\([^)\s]+\)|\[{_WORDS_IN}\]\{{[^}}\s]+\}}|`[^`]*`|\*\*|\*)"
_LINK = re.compile(rf"\[({_WORDS_IN})\]\(([^)\s]+)\)")
_COLOURED = re.compile(rf"\[({_WORDS_IN})\]\{{([^}}\s]+)\}}")
_KEPT = re.compile(r"(\\`|`[^`]*`)|\\\\(?=[(\[])")
"""Where a typed \\( or \\[ is written \\\\( or \\\\[ (outside code): a backslash
before a bracket, which is no maths."""
_MATHS = re.compile("\ue010(\\d+)\ue011")


_DISPLAYED = re.compile(r"\s*(?:\$\$(?P<dollars>.+?)\$\$|\\\[(?P<brackets>.+?)\\\])\s*", re.DOTALL)


def display_source(source: str) -> str:
    """An equation's LaTeX without the ``$$`` or ``\\[ \\]`` it may be written in."""

    whole = _DISPLAYED.fullmatch(source)
    if whole:
        return (whole.group("dollars") or whole.group("brackets") or "").strip()
    return source.strip()


def displayed(words: str) -> bool:
    """Whether ``words`` are one equation and nothing else: ``$$...$$`` or ``\\[...\\]``."""

    return bool(_DISPLAYED.fullmatch(words))


def inline(words: str) -> tuple[TextRun, ...]:
    """Slide text as runs: ``*emphasis*`` is italic, ``**strong**`` bold, ``$...$``
    math, ``code`` between backticks is set in the monospace family,
    ``[words](url)`` links, and ``[words]{accent}`` (or ``{accent2}``, ``{muted}``,
    ``{#c0392b}``) colours.

    Emphasis is slide markup only -- a figure's labels keep their asterisks.
    """

    runs: list[TextRun] = []
    # Split on links, colours, code, ** and *, maths (read as flexo reads it) standing
    # aside meanwhile as a letter that is no mark, so maths in a link's or a colour's
    # words stays in them; each piece takes the styles open around it. \* is an asterisk,
    # \` a backtick, \] a bracket (as typed: "[1](2)") and \\( or \\[ a backslash and a
    # bracket (as typed: "\(x\)"), kept out of the split.
    masked = _KEPT.sub(lambda found: found.group(1) or "\ue003\ue003", words)
    maths: list[str] = []
    text = ""
    at = 0
    for start, end in math_spans(masked):
        text += f"{masked[at:start]}\ue010{len(maths)}\ue011"
        maths.append(words[start:end])
        at = end
    text += masked[at:]

    def back(part: str) -> str:
        return _MATHS.sub(lambda found: maths[int(found.group(1))], part)

    tokens: list[str] = []
    for token in re.split(_INLINE, _held(text.replace("\ue003\ue003", "\ue003"))):
        if _LINK.fullmatch(token) or _COLOURED.fullmatch(token):
            tokens.append(back(token))
        else:
            tokens += [back(part) for part in re.split("(\ue010\\d+\ue011)", token)]
    tokens = [token for token in tokens if token]
    paired = _emphasis(tokens)
    bold = italic = False
    for index, token in enumerate(tokens):
        if token == "**" and index in paired:
            bold = not bold
            continue
        if token == "*" and index in paired:
            italic = not italic
            continue
        link = _LINK.fullmatch(token)
        coloured = None if link else _COLOURED.fullmatch(token)
        # A link's or a colour's words may carry emphasis of their own.
        if link:
            pieces = tuple(replace(run, link=link.group(2)) for run in inline(link.group(1)))
        elif coloured:
            pieces = tuple(replace(run, color=coloured.group(2)) for run in inline(coloured.group(1)))
        else:
            pieces = parse_label(token)
        for run in pieces:
            runs.append(
                replace(
                    run,
                    text=_freed(run.text),
                    # Strong words' maths stays regular, as LaTeX's \textbf leaves it.
                    weight=700 if bold and not run.maths else run.weight,
                    italic=run.italic or italic,
                )
            )
    return _displayed_apart(runs)


def _displayed_apart(runs: list[TextRun]) -> tuple[TextRun, ...]:
    """``runs`` with each formula displayed among words (``$$...$$``) on a line of its own,
    as a figure's label sets one (``flexo.markup``): there it is centred, as LaTeX sets it."""

    laid: list[TextRun] = []
    for at, run in enumerate(runs):
        if run.math.startswith("\\displaystyle"):
            # Broken before and after, unless the words are broken there already (a new
            # line typed before or after it): never a line left empty.
            if laid and not laid[-1].text.rstrip(" ").endswith("\n"):
                laid.append(TextRun("\n"))
            laid.append(run)
            after = runs[at + 1].text.lstrip(" ") if at + 1 < len(runs) else ""
            if not after.startswith("\n") and any(later.text.strip() or later.math for later in runs[at + 1 :]):
                laid.append(TextRun("\n"))
            continue
        if at and runs[at - 1].math.startswith("\\displaystyle"):
            run = replace(run, text=run.text.lstrip(" "))
        laid.append(run)
    return tuple(laid)


_ASTERISK = "\ue000"
"""Where an escaped asterisk (\\*) waits while emphasis is read."""

_HELD = {"\\*": _ASTERISK, "\\`": "\ue001", "\\]": "\ue002"}
"""Escaped marks, and where each waits while the markup is read."""


def _held(words: str) -> str:
    for mark, held in _HELD.items():
        words = words.replace(mark, held)
    return words


def _freed(text: str) -> str:
    for mark, held in _HELD.items():
        text = text.replace(held, mark[1])
    return text.replace("\ue003", "\\")


def _emphasis(tokens: list[str]) -> set[int]:
    """The indices of the ``*`` and ``**`` that open or close emphasis, as Markdown pairs
    them: an opener touches the word after it, a closer the word before, and one with
    no partner (2 * 3 * 4, a footnote's lone *) is an asterisk."""

    paired: set[int] = set()
    open_at: list[int] = []
    for index, token in enumerate(tokens):
        if token not in ("*", "**"):
            continue
        before = tokens[index - 1][-1:] if index > 0 else ""
        after = tokens[index + 1][:1] if index + 1 < len(tokens) else ""
        can_close = bool(before) and not before.isspace()
        can_open = bool(after) and not after.isspace()
        same = [at for at in open_at if tokens[at] == token]
        if can_close and same:
            # The nearest one open of its kind: ***both*** is bold and italic both.
            open_at.remove(same[-1])
            paired |= {same[-1], index}
        elif can_open:
            open_at.append(index)
    return paired


class Region:
    """A place on a slide that holds blocks, one under the other."""

    def __init__(self, slide: Slide, name: str) -> None:
        self._slide = slide
        self.name = name
        self.blocks: list[_Block] = []
        self.sources: list[dict[str, object]] = []
        """Each block as a deck document writes it (see ``flexo_talk.document``)."""
        self.placeholders: set[int] = set()
        self.builds: set[int] = set()
        """The blocks (by index) that build in: each appears on a click of its own, in the
        order they are on the slide (see ``build_in``)."""
        """The blocks (by index) that are placeholders: put there to be made one's own (the
        studio's sample table, figure or equation), drawn faintly while editing and never
        presented or exported until changed."""

    def _record(self, kind: str, value: object, **options: object) -> None:
        self.sources.append({kind: value, **{key: item for key, item in options.items() if item is not None}})

    def bullets(
        self,
        *items: str | Sequence[str],
        size: float | None = None,
        numbered: bool = False,
        reveal: bool = False,
        colour: str | None = None,
        plain: bool = False,
    ) -> Region:
        """A bulleted list. A nested list of strings is the level below the item before it.
        ``numbered=True`` numbers every level, each in its tier (1., a., i.), as Keynote does.
        ``reveal=True`` shows the outer items one at a time: a click each in the
        PowerPoint, a page each in the PDF (the SVG and PNG show them all). ``colour``
        paints its words, as a text's does. ``plain=True`` draws no bullets or numbers,
        each item at its level's indent (Keynote's None)."""

        size, numbered, reveal = _size(size), _flag(numbered, "numbered"), _flag(reveal, "reveal")
        plain = _flag(plain, "plain")
        numbered = numbered and not plain
        colour = _colour(colour)
        flattened: list[tuple[int, tuple[TextRun, ...]]] = []

        def add(entries: Iterable[str | Sequence[str]], level: int) -> None:
            for entry in entries:
                if isinstance(entry, list | tuple):
                    if level + 1 >= MOST_LEVELS:
                        # A slide shows a few levels; this many would outrun Python's own.
                        raise ValueError(f"A list is nested more than {MOST_LEVELS} levels deep.")
                    add(entry, level + 1)
                elif str(_words(entry, "A bullet")).strip():
                    # A number is an item too (a year); anything else is not words. An
                    # empty item is left out, rather than drawn as a bare bullet.
                    flattened.append((level, inline(_words(entry, "A bullet"))))

        add(items, 0)
        self.blocks.append(_Bullets(flattened, size, numbered, reveal, colour, plain))
        self._record(
            "bullets", _plain(items), size=size, numbered=numbered or None, reveal=reveal or None, colour=colour,
            plain=plain or None,
        )
        return self

    def text(
        self,
        words: str,
        *,
        size: float | None = None,
        align: Literal["start", "middle", "end"] = "start",
        muted: bool = False,
        colour: str | None = None,
    ) -> Region:
        """A paragraph, wrapped to the region; ``$...$`` is math, as in flexo labels.
        ``colour`` paints it: ``accent`` (``accent2``...), ``muted``, a palette role,
        or ``#rrggbb``; ``[words]{colour}`` paints only some words."""

        words, size = _words(words, "text"), _size(size)
        align = _choice(align, "align", ("start", "middle", "end"))
        muted, colour = _flag(muted, "muted"), _colour(colour)
        if displayed(words):
            # A paragraph that is one equation ($$...$$) is displayed, as LaTeX displays
            # it: centred unless placed, as a document's is.
            return self.math(
                words, size=size, align="middle" if align == "start" else align,
                colour=colour or ("muted" if muted else None),
            )
        runs = inline(words)
        worded = [run for run in runs if run.text.strip() or run.math]
        if len(worded) == 1 and worded[0].math and not worded[0].math.startswith("\\displaystyle"):
            # A paragraph that is one formula ($\frac{a}{b}$) and nothing else is set as a
            # formula on a line of its own is: in display style, not shrunk to sit among words.
            runs = tuple(
                replace(run, math=f"\\displaystyle {run.math}") if run is worded[0] else run for run in runs
            )
        self.blocks.append(_Words(runs, size, align, muted, colour))
        self._record(
            "text", words, size=size, align=None if align == "start" else align, muted=muted or None, colour=colour
        )
        return self

    def math(
        self,
        source: str,
        *,
        size: float | None = None,
        align: Literal["start", "middle", "end"] = "middle",
        colour: str | None = None,
    ) -> Region:
        """An equation on a line of its own, as LaTeX displays one: ``\\frac``, ``\\sum``
        with its limits, matrices, ``cases``, and lines aligned at ``&`` and broken at
        ``\\\\``. Centred (``align`` to set it at the start or end), at the words' size
        (``size``) or smaller if that is wider than its place."""

        source = display_source(_words(source, "math"))
        size, colour = _size(size), _colour(colour)
        align = _choice(align, "align", ("start", "middle", "end"))
        self.blocks.append(_Math(source, size, align, colour))
        self._record("math", source, size=size, align=None if align == "middle" else align, colour=colour)
        return self

    def mechanism(
        self,
        steps: str | Sequence[str | dict[str, object]],
        *,
        lone_pairs: Literal["used", "all", "none"] = "used",
        charges: Literal["circled", "plain"] = "circled",
        per_row: int | None = None,
        arrow_colour: str | None = None,
    ) -> Region:
        """A reaction mechanism, drawn as chemists draw it (see ``flexo.mechanism``):
        each step a structure in SMILES and its curly arrows, a reaction arrow (reagents
        over it, conditions under it) to the next. ``steps`` is a SMILES or a list of
        steps, each a SMILES or ``{"smiles": ..., "arrows": ["5 -> 2", "2=3 -> 3"],
        "label": ..., "reagents": ..., "conditions": ..., "arrow": "equilibrium"}``.

        Atoms are named by their atom maps (``[O-:5]``). An arrow from a lone pair is
        ``"5 -> 2"``, from a bond ``"2=3 -> 3"``, a bond moved ``"1=2 -> 2-6"``, a
        fishhook ``"~>"``. A step with no SMILES is drawn from the arrows before it;
        one written out is checked against them. A step that cannot be (carbon with ten
        electrons) is drawn as far as it goes, its arrows on it, and what is wrong said
        when the slide is drawn -- as it is between one arrow and the next while a step
        is written. A step's ``place`` moves its molecules from where they are laid out
        (``{5: {"move": [-1, 0.5], "turn": 30, "flip": True}}``: the molecule with atom 5).
        The curly arrows are magenta, or ``arrow_colour``: a palette role (accent, ink,
        muted) or #rrggbb."""

        lone_pairs = _choice(lone_pairs, "lone_pairs", ("used", "all", "none"))
        arrow_colour = _colour(arrow_colour, "arrow_colour")
        if arrow_colour is not None and not re.fullmatch(r"#.*|ink|muted|accent\d*", arrow_colour):
            raise SettingError("arrow_colour", "arrow_colour must be accent (accent2, \u2026), ink, muted or a "
                               f"#rrggbb colour, not {arrow_colour!r}.")
        charges = _choice(charges, "charges", ("circled", "plain"))
        if per_row is not None:
            per_row = int(_number(per_row, "per_row", 1, 20, "3"))
        written = [steps] if isinstance(steps, str) else list(steps)
        if not written:
            raise ValueError("A mechanism needs at least one step.")
        for number, step in enumerate(written, start=1):
            if not isinstance(step, str | dict):
                raise ValueError(f"Step {number} of the mechanism must be a SMILES string or a mapping with smiles "
                                 "and arrows.")
        deck = self._slide.deck
        identifier = f"{self._slide.id}-{self.name}-{len(self.blocks)}"
        figure = flexo.Figure(identifier, **deck.figure_options())
        node = figure.root.mechanism(
            "mechanism", written, lone_pairs=lone_pairs, charges=charges, per_row=per_row,
            arrow_colour=arrow_colour, partial=True,
        )
        from flexo.diagnostics import FlexoError
        from flexo.mechanism import mechanism_states

        try:
            _, problem = mechanism_states(next(item for item in figure.spec.nodes if item.id == node.id))
        except FlexoError as error:
            # Nothing to draw: the first structure itself, or the steps, are not written right.
            said = error.diagnostics[0]
            raise ValueError(f"{said.message}{' ' + said.hint if said.hint else ''}") from None
        wrong = () if problem is None else (f"{problem.message}{' ' + problem.hint if problem.hint else ''}",)
        self.blocks.append(_Figure(figure, False, said=wrong))
        self._record(
            "mechanism", steps if isinstance(steps, str) else [dict(step) if isinstance(step, dict) else step
                                                               for step in written],
            lone_pairs=None if lone_pairs == "used" else lone_pairs,
            charges=None if charges == "circled" else charges, per_row=per_row, arrow_colour=arrow_colour,
        )
        return self

    def gallery(
        self,
        items: Sequence[str | Path | tuple[str | Path, str]],
        *,
        columns: int | None = None,
        height: float | None = None,
        crop: Literal["circle", "square"] | None = None,
        size: float | None = None,
        align: Literal["start", "middle"] | None = None,
    ) -> Region:
        """Pictures in a grid -- logos, or people with their names -- each with an
        optional caption under it (``(file, "**Name**\\nInstitute")``).

        ``columns`` defaults to all in one row up to five; ``height`` is each
        picture's height (the cell's width at most); ``crop="circle"`` cuts
        photographs to circles (and ``"square"`` to squares), which needs Pillow.
        ``align`` sets a single column flush with the words (``start``, its default)
        or centred; a grid of several columns is centred.
        """

        if isinstance(items, str | Path) or not items:
            raise ValueError("A gallery needs at least one picture (a file, or a file and its caption).")
        if columns is not None and (
            isinstance(columns, bool) or not isinstance(columns, int) or not 1 <= columns <= 12
        ):
            raise ValueError(f"columns must be a whole number from 1 to 12, not {columns!r}.")
        height = None if height is None else _number(height, "height", 8.0, 4032.0, "120 (points)")
        crop = None if crop is None else _choice(crop, "crop", ("circle", "square"))
        size = _size(size)
        align = None if align is None else _choice(align, "align", ("start", "middle"))
        cells = []
        for item in items:
            if isinstance(item, str | Path):
                source, caption = item, ""
            elif isinstance(item, list | tuple) and len(item) == 2:
                source, caption = item
            else:
                raise ValueError(f"A gallery picture must be a file, or a file and its caption, not {item!r}.")
            cells.append((str(source), inline(_words(caption, "A caption")) if caption else ()))
        self.blocks.append(_Gallery(cells, columns, height, crop, size, align))
        pictures = [str(item) if isinstance(item, str | Path) else {"picture": str(item[0]), "caption": item[1]}
                    for item in items]
        self._record("gallery", pictures, columns=columns, height=height, crop=crop, size=size, align=align)
        return self

    def quote(self, words: str, *, by: str | None = None, size: float | None = None) -> Region:
        """A quotation set large in the title face, an accent quotation mark hung in
        the margin beside it, and who said it (``by``) under it, muted (an empty one, ``""``,
        holds its place while the deck is edited, as a placeholder)."""

        held = by == ""
        words, by, size = _words(words, "quote"), _words(by or "", "by"), _size(size)
        self.blocks.append(_Quote(inline(words), inline(f"\u2014 {by}") if by else (), size, held))
        self._record("quote", words, by=by or None, size=size)
        return self

    def stats(
        self,
        *items: tuple[object, str],
        colour: str | None = None,
        size: float | None = None,
    ) -> Region:
        """Numbers to remember, side by side: ``stats(("93%", "top-1 accuracy"), ("4x", "faster"))``.
        Each value is set very large in the accent colour (``colour`` to choose
        another: ``accent2``, ``#hex``) with its label under it, muted; ``size``
        is the values' size."""

        if not items:
            raise ValueError("Stats need at least one (value, label) pair.")
        for item in items:
            if isinstance(item, str) or not isinstance(item, list | tuple) or len(item) != 2:
                raise ValueError(f'Each stat must be a (value, label) pair, such as ("93%", "accuracy"), not {item!r}.')
        items = tuple((_words(value, "A stat's value"), _words(label, "A stat's label")) for value, label in items)
        colour, size = _colour(colour), _size(size)
        self.blocks.append(
            _Stats([(inline(str(value)), inline(label)) for value, label in items], colour, size)
        )
        self._record(
            "stats", [{"value": value, "label": label} for value, label in items], colour=colour, size=size
        )
        return self

    def callout(
        self, words: str, *, title: str | None = None, colour: str = "accent", size: float | None = None
    ) -> Region:
        """A key point on a panel tinted in a tone, a bar of the tone along its edge:
        ``colour`` is ``accent`` (``accent2``, ...); ``title`` is set bold above the words (an
        empty one, ``""``, holds its place while the deck is edited, as a placeholder)."""

        held = title == ""
        words, title, size = _words(words, "callout"), _words(title or "", "title"), _size(size)
        if not (isinstance(colour, str) and colour.startswith("accent") and paint_role(colour) in _roles()):
            raise ValueError(f"A callout's colour must be an accent (accent, accent2, \u2026), not {colour!r}.")
        self.blocks.append(_Callout(inline(words), inline(f"**{title}**") if title else (), colour, size, held))
        self._record(
            "callout", words, title=title or None, colour=None if colour == "accent" else colour, size=size
        )
        return self

    def figure(
        self, id: str | None = None, *, turn: bool | None = None, width: float | None = None,
        **options: object,
    ) -> flexo.Figure:
        """A flexo figure in the deck's theme, laid out for this place: use it as a
        ``with`` block. ``turn=False`` keeps it from turning, and ``width`` draws it that
        wide (see ``add``)."""

        deck = self._slide.deck
        turn = None if turn is None else _flag(turn, "turn")
        width = _width(width)
        options = {**deck.figure_options(), **options}
        figure = flexo.Figure(id or f"{self._slide.id}-{self.name}-{len(self.blocks)}", **options)
        self.blocks.append(_Figure(figure, turn, width))
        self._record("figure", None, turn=turn, width=width)
        return figure

    def add(
        self, figure: flexo.Figure | FigureSpec, *, turn: bool | None = None, width: float | None = None,
        description: str | None = None, caption: str | None = None,
    ) -> Region:
        """An existing flexo figure, laid out again in the deck's theme for this place.

        Flexo lays it out for the place's width *and* height: as written, or turned
        (a tall stack read left to right) or spaced closer when that lets its words
        be larger -- ``turn=False`` keeps it from turning (folded onto two lines it may
        still be: that is no turn), and a figure whose parts were arranged by hand (a part
        under another beside others) is kept as written unless ``turn=True``.
        It is drawn as large as its place lets its words be the size of the words round
        it; ``width`` (points) draws it that wide instead, smaller or larger, as far as
        its place allows.
        ``description`` says what it shows, as a picture's does; ``caption`` is set under it.
        """

        width = _width(width)
        description = " ".join(str(description).split()) if description is not None else ""
        turn = None if turn is None else _flag(turn, "turn")
        held, caption = caption == "", _caption(caption)
        self.blocks.append(
            _Figure(figure, turn, width, description=description, caption=inline(caption), caption_held=held)
        )
        self._record("figure", None, turn=turn, width=width, description=description or None, caption=caption or None)
        return self

    def image(
        self, source: str | Path, *, width: float | None = None, description: str | None = None,
        caption: str | None = None,
    ) -> Region:
        """A picture file, scaled to fit: an SVG (a saved plot, a drawing) is drawn
        as vectors -- native shapes and text in the PowerPoint -- and a PNG as a picture.
        ``description`` says what it shows, for whoever cannot see it (a screen reader,
        PowerPoint's alt text); ``caption`` is set under it, centred, a size smaller."""

        width = _width(width)
        description = " ".join(str(description).split()) if description is not None else ""
        held, caption = caption == "", _caption(caption)
        self.blocks.append(_Image(str(source), width, description, inline(caption), held))
        self._record("image", str(source), width=width, description=description or None, caption=caption or None)
        return self

    def build_in(self) -> Region:
        """The block added last appears on a click when presenting, after what is on the
        slide before it (Keynote's Build In, Appear): a click in the PowerPoint, a page in
        the PDF. A list's items revealed one at a time (``reveal``) appear by themselves."""

        if not self.blocks:
            raise ValueError("Add a block before building it in.")
        self.builds.add(len(self.blocks) - 1)
        if self.sources[-1]:  # a stand-in for what is missing is written as nothing
            self.sources[-1]["build"] = True
        return self

    def stand_in(self, what: str, name: str, *, said: str | None = None) -> Region:
        """A box where the ``what`` (picture, figure, plot) in the file ``name`` would be,
        saying it is missing -- or what else is wrong (``said``): the rest of the slide is
        drawn meanwhile."""

        self.blocks.append(_Missing(what, name, said))
        self.sources.append({})
        return self

    def table(
        self,
        rows: Sequence[Sequence[object]],
        *,
        header: bool = True,
        align: str | Sequence[str] = "",
        size: float | None = None,
        caption: str | None = None,
    ) -> Region:
        """A table, ruled as in a paper: a rule above, one under the header, one below.

        ``rows`` are lists of cells (words, with ``$...$`` maths, or numbers);
        the first row is the header unless ``header=False``. ``align`` gives each
        column ``start``, ``middle``, or ``end`` (``"lrr"`` also works); by
        default a column of numbers is set flush right and any other flush left.
        ``caption`` is set under it, centred, a size smaller.
        """

        if isinstance(rows, str) or not all(isinstance(row, list | tuple) for row in rows):
            raise ValueError("A table must be a list of rows, each a list of cells.")
        header, size = _flag(header, "header"), _size(size)
        cells = [[inline("" if cell is None else _words(cell, "A table cell")) for cell in row] for row in rows]
        columns = max((len(row) for row in cells), default=0)
        ragged = len({len(row) for row in cells}) > 1
        cells = [row + [()] * (columns - len(row)) for row in cells]
        names = {"l": "start", "c": "middle", "r": "end"}
        if isinstance(align, str) and align and all(ch in names for ch in align):
            aligned = tuple(names[ch] for ch in align)
        elif align == "":
            aligned = ()
        elif isinstance(align, str):
            raise SettingError("align", "align must be a letter for each column (l, c or r) or a list of start, "
                                        f"middle and end, not {align!r}.")
        else:
            aligned = tuple(_choice(item, "A column's alignment", ("start", "middle", "end")) for item in align)
        if len(aligned) != columns:
            body = [list(row) for row in rows[1 if header else 0 :]]
            aligned = tuple(
                "end"
                if any(_numeric(row[index]) for row in body if index < len(row))
                and all(_numeric(row[index]) or _blank(row[index]) for row in body if index < len(row))
                else "start"
                for index in range(columns)
            )
        held, caption = caption == "", _caption(caption)
        self.blocks.append(_Table(cells, header, aligned, size, ragged, inline(caption), held))
        given = align if isinstance(align, str) else list(align)
        self._record(
            "table", _plain(rows), header=None if header else False, align=given or None, size=size,
            caption=caption or None,
        )
        return self

    def code(self, source: str, *, size: float | None = None) -> Region:
        """A code listing in the monospace family, on a tinted panel; lines are kept as
        written (tabs become four spaces) and whole-line comments are set muted."""

        import textwrap

        source, size = _words(source, "code"), _size(size)
        text = textwrap.dedent(source.expandtabs(4)).strip("\n")
        self.blocks.append(_Code(text.splitlines() or [""], size))
        self._record("code", text, size=size)
        return self

    def plot(self, figure: object, *, aspect: float | None = None) -> Region:
        """A matplotlib figure, drawn at the size of this place in the deck's type.

        The figure is laid out again at the place's size (matplotlib's
        constrained layout), so its words are the deck's figure size rather than
        scaled; its text is set in the deck's font and stays text. Make it inside
        ``with deck.plotting():`` for the deck's colours as well.
        """

        aspect = None if aspect is None else _number(aspect, "aspect", 0.1, 10.0, "1.6 (width over height)")
        self.blocks.append(_Plot(figure, aspect))
        self._record("plot", None, aspect=aspect)
        return self


def _plain(items: object) -> object:
    """Nested tuples and lists as lists, for a document."""

    if isinstance(items, list | tuple):
        return [_plain(item) for item in items]
    return items


def _blank(cell: object) -> bool:
    """A cell that stands for no value: empty, a dash, or n/a. A column of numbers
    with gaps in it is still a column of numbers."""

    return str(cell).strip().lower() in {"", "-", "--", "\u2013", "\u2014", "n/a", "na"}


def _numeric(cell: object) -> bool:
    """A number, with what may go with one: a sign, ± a spread, a %, a multiple (k, M, x,
    before it or after it: x7, 7x, as with the multiplication sign) or a unit (38 ms,
    1.2 GB, 400 req/s)."""

    if isinstance(cell, int | float):
        return True
    text = str(cell).strip().replace("$", "").replace("*", "").replace(",", "")
    text = text.replace("\\pm", "±").rstrip("%").strip()
    return bool(re.fullmatch(_NUMBER, text))


_NUMBER = (
    r"[-+\u2212]?([x\u00d7]\s?)?\d+(\.\d+)?(\s*±\s*\d+(\.\d+)?)?"
    r"\s*([kKMGTBx\u00d7]|[A-Za-z\u00b5\u03bc\u00b0\u03a9]{1,4}(/[A-Za-z\u00b5\u03bc]{1,3})?)?"
)
"""A number as a table's cell gives one (see ``_numeric``)."""


class Slide:
    """One slide: a title, regions by layout, and speaker notes."""

    def __init__(
        self,
        deck: Deck,
        index: int,
        title: str,
        layout: Layout,
        subtitle: str,
        split: float = 0.5,
        columns: int = 3,
        widths: Sequence[float] | None = None,
        background: str | Path | None = None,
        shade: float = 0.0,
        dark: bool | None = None,
        align: str | None = None,
    ) -> None:
        if layout not in LAYOUTS:
            raise ValueError(f"Unknown layout \u201c{layout}\u201d. Available layouts: {', '.join(LAYOUTS)}.")
        title, subtitle = _words(title or "", "title"), _words(subtitle or "", "subtitle")
        split = _number(split, "split", 0.15, 0.85, "0.5 (the left column's share of the width)")
        shade = _number(shade, "shade", 0.0, 1.0, "0.4 (how much a picture is darkened)")
        if dark is not None:
            dark = _flag(dark, "dark")
        if widths is not None:
            widths = [_number(share, "A column width", 0.01, 100.0, "1 (shares of the width)") for share in widths]
        if background is not None and not isinstance(background, str | Path):
            raise SettingError(
                "background", f"background must be a #rrggbb colour or a picture file, not {background!r}."
            )
        if isinstance(background, str) and background.startswith("#"):
            _colour(background, "background")
        self.deck = deck
        self.index = index
        self.id = f"slide{index}"
        self.title_runs = inline(title) if title.strip() else ()
        self.subtitle_runs = inline(subtitle) if subtitle.strip() else ()
        self.layout = layout
        self.split = split
        """The share of the width the left column takes, on a two-column slide."""
        self.notes_text = ""
        self.footnotes: list[tuple[TextRun, ...]] = []
        self.footnote_sources: list[str] = []
        self.source: dict[str, object] = {}
        """The slide's settings as a deck document writes them (see ``flexo_talk.document``)."""
        self.background = str(background) if background is not None else None
        """This slide's own background: a colour of its theme's (``accent``), any colour
        (``#1b2a41``) or a picture file."""
        self.shade = shade
        """How much a background picture is darkened (0 to 1), for words over it."""
        self.dark = dark
        """Whether the slide's words are light; decided from the background when unset."""
        if align not in {None, "auto", "top", "middle"}:
            raise SettingError("align", f"align must be auto, top or middle, not {align!r}.")
        self.align = align
        """Where the content sits in the body; the deck style's ``align`` when unset."""
        self.byline_runs: tuple[TextRun, ...] = ()
        """Who and when, on a title slide."""
        self.placeholders: frozenset[str] = frozenset()
        """The fields written but left empty (title, subtitle, words): each holds its place."""
        if layout == "columns":
            count = len(widths) if widths else columns
            if count < 1:
                raise ValueError("A columns slide needs at least one column.")
            names = tuple(f"column{index + 1}" for index in range(count))
            total = sum(widths) if widths else float(count)
            self.shares = [share / total for share in widths] if widths else [1.0 / count] * count
        else:
            names = {"two-columns": ("left", "right")}.get(layout, ("body",))
            self.shares = [split, 1.0 - split] if layout == "two-columns" else [1.0]
        """Each column's share of the width, left to right."""
        self.regions = {name: Region(self, name) for name in names}

    @property
    def backdrop(self) -> str | None:
        """What the slide is drawn on when not the deck's page: its own background,
        or the accent colour that fills a section slide in a look that fills them."""

        if named_colour(self.background):
            return theme_colour(self.deck, self.background)
        if self.background:
            return self.background
        if self.layout == "section" and self.deck.style.sections == "fill":
            return accent_field(self.deck.palette)
        return None

    @property
    def columns(self) -> list[Region]:
        """The regions left to right: ``slide.columns[0]`` is the first column."""

        return list(self.regions.values())

    def __enter__(self) -> Slide:
        return self

    def __exit__(self, *exc: object) -> None:
        return None

    @property
    def body(self) -> Region:
        return self._region("body")

    @property
    def left(self) -> Region:
        return self._region("left")

    @property
    def right(self) -> Region:
        return self._region("right")

    def _region(self, name: str) -> Region:
        if name not in self.regions:
            raise AttributeError(
                f"A \u201c{self.layout}\u201d slide has no region \u201c{name}\u201d. Its regions are "
                f"{', '.join(self.regions)}."
            )
        return self.regions[name]

    # The first region stands for the slide, so a one-region slide reads simply.
    def bullets(
        self,
        *items: str | Sequence[str],
        size: float | None = None,
        numbered: bool = False,
        reveal: bool = False,
        colour: str | None = None,
        plain: bool = False,
    ) -> Slide:
        next(iter(self.regions.values())).bullets(
            *items, size=size, numbered=numbered, reveal=reveal, colour=colour, plain=plain
        )
        return self

    def text(self, words: str, **options: object) -> Slide:
        next(iter(self.regions.values())).text(words, **options)  # type: ignore[arg-type]
        return self

    def figure(
        self, id: str | None = None, *, turn: bool | None = None, width: float | None = None,
        **options: object,
    ) -> flexo.Figure:
        return next(iter(self.regions.values())).figure(id, turn=turn, width=width, **options)

    def add(
        self, figure: flexo.Figure | FigureSpec, *, turn: bool | None = None, width: float | None = None,
        description: str | None = None, caption: str | None = None,
    ) -> Slide:
        next(iter(self.regions.values())).add(figure, turn=turn, width=width, description=description, caption=caption)
        return self

    def image(
        self, source: str | Path, *, width: float | None = None, description: str | None = None,
        caption: str | None = None,
    ) -> Slide:
        next(iter(self.regions.values())).image(source, width=width, description=description, caption=caption)
        return self

    def build_in(self) -> Slide:
        """The block added last appears on a click (see ``Region.build_in``)."""

        next(iter(self.regions.values())).build_in()
        return self

    def gallery(self, items, **options: object) -> Slide:
        next(iter(self.regions.values())).gallery(items, **options)  # type: ignore[arg-type]
        return self

    def code(self, source: str, *, size: float | None = None) -> Slide:
        next(iter(self.regions.values())).code(source, size=size)
        return self

    def table(self, rows: Sequence[Sequence[object]], **options: object) -> Slide:
        next(iter(self.regions.values())).table(rows, **options)  # type: ignore[arg-type]
        return self

    def plot(self, figure: object, *, aspect: float | None = None) -> Slide:
        next(iter(self.regions.values())).plot(figure, aspect=aspect)
        return self

    def quote(self, words: str, **options: object) -> Slide:
        next(iter(self.regions.values())).quote(words, **options)  # type: ignore[arg-type]
        return self

    def stats(self, *items: tuple[object, str], **options: object) -> Slide:
        next(iter(self.regions.values())).stats(*items, **options)  # type: ignore[arg-type]
        return self

    def callout(self, words: str, **options: object) -> Slide:
        next(iter(self.regions.values())).callout(words, **options)  # type: ignore[arg-type]
        return self

    def math(self, source: str, **options: object) -> Slide:
        next(iter(self.regions.values())).math(source, **options)  # type: ignore[arg-type]
        return self

    def mechanism(self, steps, **options: object) -> Slide:
        next(iter(self.regions.values())).mechanism(steps, **options)  # type: ignore[arg-type]
        return self

    def notes(self, text: str) -> Slide:
        """What to say: kept as the slide's speaker notes."""

        self.notes_text = text
        return self

    def footnote(self, text: str) -> Slide:
        """A reference or aside, set small and muted at the foot of the slide
        (above the footer); several stack in the order given."""

        self.footnotes.append(inline(text))
        self.footnote_sources.append(text)
        return self


THEME_SLIDE_KEYS = ("look", "style", "background", "font", "title_font", "figure_font")
_THEME_SLIDES: dict[str, tuple[int, dict[str, object]]] = {}


def theme_slides(theme: object) -> dict[str, object]:
    """What a theme file says about the slides set in it, beside its figures' look.

    A theme file may carry ``slides:`` next to ``theme:``: the deck's ``look``,
    ``style`` (``DeckStyle`` fields), ``background`` (a colour, or a picture such
    as a paper texture, found beside the theme file), and its families by role
    (``font``, ``title_font``, ``figure_font``). A deck set in the theme takes
    each of these unless it says otherwise. A theme named rather than filed has
    none: ``{}``.
    """

    import yaml

    if not isinstance(theme, str) or not theme.lower().endswith((".yaml", ".yml", ".json")):
        return {}
    path = Path(theme).expanduser().resolve()
    if not path.is_file():
        return {}
    stamp = path.stat().st_mtime_ns
    known = _THEME_SLIDES.get(str(path))
    if known and known[0] == stamp:
        return dict(known[1])
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    slides = (data.get("slides") or {}) if isinstance(data, dict) else {}
    if not isinstance(slides, dict):
        raise ValueError(f"{path.name}: slides must be a mapping ({', '.join(THEME_SLIDE_KEYS)}).")
    unknown = sorted(set(slides) - set(THEME_SLIDE_KEYS))
    if unknown:
        raise ValueError(
            f"{path.name}: Unknown {'key' if len(unknown) == 1 else 'keys'} in slides: {', '.join(unknown)}. "
            f"Valid keys: {', '.join(THEME_SLIDE_KEYS)}."
        )
    style = slides.get("style") or {}
    names = {item.name for item in fields(DeckStyle)}
    if not isinstance(style, dict):
        raise ValueError(f"{path.name}: slides.style must be a mapping of DeckStyle fields.")
    if set(style) - names:
        wrong = sorted(set(style) - names)
        raise ValueError(f"{path.name}: Unknown {'field' if len(wrong) == 1 else 'fields'} in slides.style: "
                         f"{', '.join(wrong)}.")
    look = slides.get("look")
    if look is not None and look not in LOOKS:
        raise ValueError(f"{path.name}: Unknown look \u201c{look}\u201d. Available looks: {', '.join(LOOKS)}.")
    background = slides.get("background")
    if isinstance(background, str) and not background.startswith("#"):
        picture = (path.parent / background).resolve()
        if not picture.is_file():
            raise ValueError(f"{path.name}: Cannot find the picture {background} named in slides.background.")
        slides = {**slides, "background": str(picture)}
    _THEME_SLIDES[str(path)] = (stamp, slides)
    return dict(slides)


class Deck:
    """A slide deck in one flexo theme; see the module docs."""

    def __init__(
        self,
        id: str = "talk",
        *,
        theme: str = "paper",
        palette: str | Sequence[str] = "default",
        font: str | None = None,
        title_font: str | None = None,
        figure_font: str | None = None,
        conventions: dict[str, object] | None = None,
        sketch: object = None,
        background: bool | str = True,
        footer: str = "",
        style: DeckStyle | None = None,
        look: str | None = None,
    ) -> None:
        self.source: dict[str, object] = {
            "theme": theme, "palette": _plain(palette), "font": font, "title_font": title_font,
            "figure_font": figure_font, "conventions": conventions, "sketch": sketch, "background": background,
            "footer": footer, "look": look,
        }
        """What the deck was made with, as a deck document writes it (see ``flexo_talk.document``)."""
        # A theme file is read now, by the Figure machinery that knows how, and
        # what it says about slides fills in what the deck leaves unsaid.
        _check_theme(theme)
        _check_settings({
            "id": id, "palette": palette, "font": font, "title_font": title_font, "figure_font": figure_font,
            "look": look, "background": background, "footer": footer, "conventions": conventions, "sketch": sketch,
        })
        try:
            probe = flexo.Figure("probe", theme=theme, palette=palette)
        except (TypeError, ValueError) as error:
            raise SettingError("palette", str(error)) from None
        slides = theme_slides(theme)
        own_look = look
        look = look if look is not None else slides.get("look")  # type: ignore[assignment]
        font = font or slides.get("font")  # type: ignore[assignment]
        title_font = title_font or slides.get("title_font")  # type: ignore[assignment]
        figure_font = figure_font or slides.get("figure_font")  # type: ignore[assignment]
        if background is True and slides.get("background") is not None:
            background = slides["background"]  # type: ignore[assignment]
        self.id = id
        self.theme = probe.style
        self.palette_name = probe.palette
        from flexo.diagnostics import FlexoError

        try:
            # A palette named but not known is said now, not on every slide.
            resolve_palette(self.theme, self.palette_name)
        except FlexoError as error:
            raise SettingError("palette", _flexo_said(error)) from None
        self.font = font
        """The family of the slides' words and figures; the theme's when unset."""
        self.title_font = title_font
        """The family of slide titles and section headings; ``font`` when unset."""
        self.figure_font = figure_font
        """The family of the figures' words; ``font`` when unset."""
        from flexo.fonts import require_family

        for key, family in (("font", font), ("title_font", title_font), ("figure_font", figure_font)):
            if family:
                try:
                    require_family(family)
                except FlexoError as error:
                    raise SettingError(key, _flexo_said(error)) from None
        self.conventions = conventions
        self.sketch = sketch
        self.background = background
        """The page every slide is drawn on: the theme's page colour (``True``), a colour,
        a picture that fills each slide (a paper texture), or nothing (``False``)."""
        self.footer = "" if footer is None else str(footer)
        if look is not None and look not in LOOKS:
            raise SettingError("look", f"Unknown look \u201c{look}\u201d. Available looks: {', '.join(LOOKS)}.")
        # The theme's proportions, and the look: the deck's own look over the
        # theme's style, the theme's style over a look the theme chose.
        theme_style = slides.get("style") or {}
        baseline = DeckStyle()
        if own_look is not None:
            baseline = replace(replace(baseline, **theme_style), **LOOKS[own_look])  # type: ignore[arg-type]
        elif look is not None:
            baseline = replace(DeckStyle.look(look), **theme_style)  # type: ignore[arg-type]
        else:
            baseline = replace(baseline, **theme_style)  # type: ignore[arg-type]
        self.baseline = baseline
        """The style before the deck's own changes: the look and the theme's proportions."""
        if style is not None and own_look is not None:
            # A look sets the page; a style given beside it keeps its own sizes.
            style = replace(style, **LOOKS[own_look])  # type: ignore[arg-type]
        self.style = style or baseline
        self.look = look
        """The named look the style started from, if any (the deck's, or its theme's)."""
        self.slides: list[Slide] = []

    def __enter__(self) -> Deck:
        return self

    def __exit__(self, *exc: object) -> None:
        return None

    # -- authoring --

    def slide(
        self,
        title: str = "",
        *,
        layout: Layout = "content",
        subtitle: str = "",
        split: float = 0.5,
        columns: int = 3,
        widths: Sequence[float] | None = None,
        background: str | Path | None = None,
        shade: float = 0.0,
        dark: bool | None = None,
        align: Literal["auto", "top", "middle"] | None = None,
    ) -> Slide:
        """A slide: ``content`` (a title over one body), ``two-columns`` (``split`` is
        the left column's share of the width), ``columns`` (``columns`` of them, or
        as many as ``widths``, relative: ``(2, 1, 1)``; ``slide.columns[i]``),
        ``figure`` (a title over a figure as large as the slide allows), or ``blank``.

        ``background`` gives this slide its own background: a colour, or a picture
        that fills the slide (cropped, never stretched), darkened by ``shade``; on a
        dark background the slide's words are set light (``dark`` overrides).
        ``align`` places the content in the body (see ``DeckStyle.align``)."""

        split = _number(split, "split", 0.15, 0.85, "0.5 (the left column's share of the width)")
        if isinstance(columns, bool) or not isinstance(columns, int) or not 1 <= columns <= 12:
            raise SettingError("columns", f"columns must be a whole number from 1 to 12, not {columns!r}.")
        made = Slide(
            self, len(self.slides) + 1, title, layout, subtitle, split, columns, widths,
            background, shade, dark, align,
        )
        made.source = {
            "layout": layout, "title": title, "subtitle": subtitle, "split": split,
            "widths": list(widths) if widths else None, "columns": columns,
            "background": str(background) if background is not None else None, "shade": shade, "dark": dark,
            "align": align,
        }
        self.slides.append(made)
        return made

    def title(
        self,
        title: str,
        *,
        subtitle: str = "",
        author: str = "",
        date: str = "",
        background: str | Path | None = None,
        shade: float = 0.0,
    ) -> Slide:
        """The opening slide: the talk's title, a subtitle, who and when (and, if
        given, a background colour or picture: see ``slide``). A ``date`` object is
        written as a document writes one: 2026-10-01."""

        import datetime

        if isinstance(date, datetime.date):
            date = date.isoformat()
        author, date = _words(author, "author"), _words(date, "date")
        made = self.slide(title, layout="title", subtitle=subtitle, background=background, shade=shade)
        made.source.update(author=author, date=date)
        parts = [part for part in (author, date) if part]
        # In a right-to-left byline a middle dot reads as the Persian and Arabic zero
        # (15 and a dot read as 150): a dash keeps author and date apart.
        from flexo.bidi import has_rtl

        byline = (" \u2013 " if any(has_rtl(part) for part in parts) else " · ").join(parts)
        made.byline_runs = inline(byline) if byline else ()
        return made

    def section(
        self, title: str, *, subtitle: str = "", background: str | Path | None = None, shade: float = 0.0
    ) -> Slide:
        """A divider between parts of the talk."""

        return self.slide(title, layout="section", subtitle=subtitle, background=background, shade=shade)

    def statement(
        self, words: str, *, by: str = "", background: str | Path | None = None, shade: float = 0.0
    ) -> Slide:
        """A slide that says one thing, large, in the middle: a claim, a question, a
        quotation (``by`` says whose). ``[words]{accent}`` paints the words that matter."""

        by = _words(by, "by")
        made = self.slide(words, layout="statement", background=background, shade=shade)
        made.source.update(by=by)
        made.byline_runs = inline(f"\u2014 {by}") if by else ()
        return made

    def agenda(self, title: str = "Outline") -> Slide:
        """A slide listing the talk's sections, numbered -- the ``section`` slides
        anywhere in the deck, so it can come before them."""

        return self.slide(title, layout="agenda")

    def figure_options(self) -> dict[str, object]:
        options: dict[str, object] = {"theme": self.theme, "palette": self.palette_name}
        if self.figure_font or self.font:
            options["font"] = self.figure_font or self.font
        if self.conventions:
            options["conventions"] = self.conventions
        if self.sketch is not None:
            options["sketch"] = self.sketch
        return options

    # -- the look --

    @property
    def layout_style(self) -> LayoutStyle:
        return resolve_style(self.theme, self.font, None, flexo.sketch.parse_sketch(self.sketch))

    @property
    def palette(self) -> Palette:
        # Asked for scores of times a slide: derived once for the theme and palette as they
        # are (a theme file read again is a theme of its own).
        from flexo.themes import theme as named_theme

        named = self.palette_name
        key = (self.theme, named if isinstance(named, str | None) else tuple(named), id(named_theme(self.theme)))
        painted = getattr(self, "_painted", None)
        if painted is None or painted[0] != key:
            painted = self._painted = (key, with_tone_roles(resolve_palette(self.theme, self.palette_name)))
        return painted[1]

    def plot_style(self) -> dict[str, object]:
        """matplotlib settings for plots in the deck's look: its font and figure
        size, its inks, and the palette's tones as the colour cycle."""

        from cycler import cycler
        from flexo.colour import is_dark

        palette = self.palette
        dark = is_dark(palette.get("canvas"))
        colours = data_colours(palette, dark)
        ink, muted = palette.get("ink"), palette.get("muted-ink")
        family = self.layout_style.typography.family
        # Plot words sit a little above figure labels: tick labels are read from afar.
        size = self.style.figure_size * 1.15
        return {
            "font.family": [family],
            "font.size": size,
            "axes.titlesize": size * 1.1,
            "axes.labelsize": size,
            "xtick.labelsize": size * 0.9,
            "ytick.labelsize": size * 0.9,
            "legend.fontsize": size * 0.9,
            "text.color": ink,
            "axes.labelcolor": ink,
            "axes.titlecolor": ink,
            "axes.edgecolor": muted,
            "xtick.color": muted,
            "ytick.color": muted,
            "xtick.labelcolor": ink,
            "ytick.labelcolor": ink,
            "grid.color": muted,
            "grid.alpha": 0.25,
            "axes.prop_cycle": cycler(color=colours),
            "axes.spines.top": False,
            "axes.spines.right": False,
            "axes.facecolor": "none",
            "figure.facecolor": "none",
            "legend.frameon": False,
            "lines.linewidth": 2.0,
            "patch.edgecolor": "none",
            "mathtext.fontset": "custom",
            "mathtext.rm": family,
            "mathtext.it": f"{family}:italic",
            "mathtext.bf": f"{family}:bold",
            # Symbols the deck's face lacks come from Unicode fonts, so they stay
            # the right characters when set as text (TeX fonts would not).
            "mathtext.fallback": "stix",
            "svg.fonttype": "none",
            "figure.constrained_layout.use": True,
        }

    def plotting(self):
        """``with deck.plotting():`` -- matplotlib figures made inside take the deck's look."""

        import matplotlib

        from flexo_talk.compose import register_fonts_with_matplotlib

        register_fonts_with_matplotlib()
        return matplotlib.rc_context(self.plot_style())

    def typography(self, size: float, *, title: bool = False) -> TypographyStyle:
        """The type at ``size``: in the title font for a heading, else the words' font."""

        typography = self.layout_style.typography
        if title and self.title_font:
            typography = typography.with_family(self.title_font)
        return replace(typography, size=pt(size), minimum_size=pt(min(size, 6.0)))

    @property
    def title_weight(self) -> int:
        return self.style.title_weight or self.layout_style.typography.title_weight

    # -- output --

    def render(self) -> list[RenderedSlide]:
        """Every slide laid out and drawn as SVG."""

        from flexo_talk.compose import render_slide

        return [render_slide(self, slide) for slide in self.slides]

    def build(
        self,
        directory: str | Path = "build",
        *,
        formats: Sequence[str] = ("pptx", "pdf", "svg", "png"),
        handout: bool = False,
        editable_maths: bool = True,
    ) -> DeckBuild:
        """Write the deck: ``pptx`` and ``pdf`` (one file each), ``svg`` and ``png`` per slide.

        ``editable_maths`` writes the PowerPoint's maths as its own equations, editable
        there (set in PowerPoint's maths font), with flexo's drawing for other programs;
        ``False`` keeps only the drawing, set in the deck's fonts everywhere."""

        from flexo_talk.export import build_deck

        return build_deck(self, Path(directory), tuple(formats), handout=handout, editable_maths=editable_maths)


@dataclass(slots=True)
class ListLayout:
    """Where a bulleted list was set, for writers that set lists natively."""

    x: float
    y: float
    width: float
    size: float
    line_height: float
    gap: float
    indent: float
    items: list[tuple[int, tuple[TextRun, ...], float]] = field(default_factory=list)
    """``(level, runs, baseline of its first line)`` for each item."""
    id: str = ""
    numbered: bool = False
    reveal: bool = False
    """Whether the outer items appear one click (one PDF page) at a time."""
    stepped: list[int] = field(default_factory=list)
    """The step each outer item appears at, when revealed: the slide's builds' order."""
    plain: bool = False
    """Whether the items have no bullets or numbers: each starts at its level's indent."""
    number_room: float = 0.0
    sub_room: float = 0.0
    """In a numbered list, the room an item's number takes below the top level ("a.", "iv.")."""
    """How far an outer item's words start from its number's left edge, when numbered."""
    palette: Palette | None = None
    """The slide's paints (light words on a dark slide); the deck's when unset."""
    ink: str | None = None
    """The words' colour, when the list has one of its own; else the palette's ink."""
    steps: list[float] = field(default_factory=list)
    """Each item's line height: a formula taller than the words opens its item's lines."""
    opened: list[tuple[float, float, int]] = field(default_factory=list)
    """Each item's room for a formula above and below its words, and its line count."""

    def step(self, index: int) -> float:
        """The line height of item ``index``."""

        return self.steps[index] if 0 <= index < len(self.steps) else self.line_height

    def offset(self, level: int) -> float:
        """Where an item's words start, from the list's left edge."""

        if self.numbered:
            return self.number_room if level == 0 else self.mark_at(level) + self.sub_room
        if self.plain:
            return self.indent * level
        return self.indent * level + self.size * 0.95

    def mark_at(self, level: int) -> float:
        """Where an item's bullet or number starts, from the list's left edge."""

        if self.numbered:
            # Each level's number where the level above's words start, as Keynote's tiers are.
            return 0.0 if level == 0 else self.number_room + self.indent * (level - 1)
        if self.plain:
            return self.indent * level
        return self.indent * level + self.size * 0.12


def list_number(count: int, level: int) -> str:
    """An item's number at its level in a numbered list, as Keynote and PowerPoint tier
    them: 1. at the top, a. under it, i. under that, and round again."""

    if level % 3 == 1:
        letters = ""
        while count:
            count, rest = divmod(count - 1, 26)
            letters = chr(ord("a") + rest) + letters
        return f"{letters}."
    if level % 3 == 2:
        numerals = [(10, "x"), (9, "ix"), (5, "v"), (4, "iv"), (1, "i")]
        roman = ""
        for value, numeral in [(1000, "m"), (900, "cm"), (500, "d"), (400, "cd"), (100, "c"), (90, "xc"),
                               (50, "l"), (40, "xl"), *numerals]:
            while count >= value:
                roman += numeral
                count -= value
        return f"{roman}."
    return f"{count}."


def list_numbers(levels: Sequence[int]) -> list[str]:
    """The numbers of a numbered list's items, by their levels: each level counts on until
    an item above it, then starts again."""

    counts: list[int] = []
    numbers = []
    for level in levels:
        counts = (counts + [0] * (level + 1))[: level + 1]
        counts[level] += 1
        numbers.append(list_number(counts[level], level))
    return numbers


@dataclass(slots=True)
class TableLayout:
    """Where a table was set, for writers that set tables natively."""

    x: float
    y: float
    widths: list[float]
    heights: list[float]
    cells: list[list[tuple[TextRun, ...]]]
    align: tuple[str, ...]
    size: float
    line_height: float
    baseline: float
    """Where each row's first baseline sits below the row's top."""
    pad: float
    header: bool
    rules: tuple[float, float, float]
    """The widths of the top rule, the rule under the header, and the bottom rule."""
    id: str = ""
    rtl: bool = False
    """Whether the table reads from the right (its header is in a right-to-left script)."""
    palette: Palette | None = None
    """The slide's paints (light words on a dark slide); the deck's when unset."""
    room: tuple[float, float] | None = None
    """The left edge and the width of the place the table was set in: how wide it may grow."""
    measured: list | None = None
    """Each cell's words as they were set to size the table, for the drawing to set them so
    (its rows as tall as their lines); let go once it is drawn."""


@dataclass(slots=True)
class WordsLayout:
    """Words with maths in them, as they were set -- a paragraph, a title, a caption --
    for writers that set them natively (PowerPoint, its equations its own)."""

    id: str
    x: float
    """Where the lines are aligned: their left edge, middle, or right edge (``align``)."""
    baseline: float
    """The first line's baseline."""
    width: float
    line_height: float
    lines: list[tuple[TextRun, ...]]
    size: float
    align: str = "start"
    family: str = ""
    weight: int | None = None
    fill: str = "#000000"
    downs: list[float] | None = None
    """Each line's baseline below the first's, where the lines are not evenly spaced (a tall
    formula opens only its own line); ``heights`` is then each line's own height."""
    heights: list[float] | None = None


@dataclass(slots=True)
class RenderedSlide:
    slide: Slide
    svg: str
    lists: list[ListLayout]
    diagnostics: list[str] = field(default_factory=list)
    tables: list[TableLayout] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)
    steps: int = 1
    """How many states the slide shows in turn (revealed lists); 1 for most."""
    held: list[str] = field(default_factory=list)
    """Python the slide names that was not run (its folder not yet trusted): a quiet line
    stands in its place."""
    worded: list[WordsLayout] = field(default_factory=list)
    """Words with maths in them, where they were set (see ``WordsLayout``)."""
    settled: bool = True
    """False when a figure on it kept the layout it had while it was being edited, rather
    than the best one being found (``compose.EDITING``): drawn again once edits stop."""
    builds: list[tuple[int, str]] = field(default_factory=list)
    """``(step, id)`` of each block that builds in: the step it appears at."""

    def at_step(self, step: int) -> str:
        """The slide's SVG as it stands at ``step`` (1-based): later items hidden."""

        if self.steps <= 1:
            return self.svg
        import xml.etree.ElementTree as ET

        root = ET.fromstring(self.svg)
        for parent in root.iter():
            for child in list(parent):
                if int(child.get("data-flexo-step", "0")) > step:
                    parent.remove(child)
        return '<?xml version="1.0" encoding="UTF-8"?>\n' + ET.tostring(root, encoding="unicode")


@dataclass(frozen=True, slots=True)
class DeckBuild:
    pptx: Path | None
    pdf: Path | None
    svgs: tuple[Path, ...]
    pngs: tuple[Path, ...]
    diagnostics: tuple[str, ...]
    notes: tuple[str, ...] = ()
    """What the build chose that is worth knowing: a figure laid out turned to fit."""

    def summary(self) -> str:
        written = [str(path) for path in (self.pptx, self.pdf, *self.svgs, *self.pngs) if path]
        head = "ok" if not self.diagnostics else "warnings:\n  " + "\n  ".join(self.diagnostics)
        notes = ["notes:", *(f"  {note}" for note in self.notes)] if self.notes else []
        return "\n".join([head, *notes, *written])
