"""Anything on a slide shown anew on a click: a figure, a mechanism or a list walked through
part by part, on one slide.

How an object, a part of one or a shape is shown -- shown, highlighted, dimmed or hidden
(``flexo_talk.showing``) -- may change on a click, and holds until a later click of its own
changes it again. Beside its ``hide``, ``dim`` and ``highlight``, an object or a shape says how
it is shown from a click on with ``click N``: a mapping of those same keys, all of how it is
shown from that click on (what it said before, its own keys too, no longer)::

  - figure: '#sn2'
    click 1: {highlight: [nucleophile, attack]}   # the rest of the figure faint
    click 2: {highlight: [leaving, departure]}
    click 3: {}                                   # all of it, plainly, again
  - bullets: [Attack, Departure, Inversion]
    click 1: {highlight: [1]}
    click 2: {highlight: [2]}
  shapes:
  - {kind: ring, at: [300, 220], size: [120, 80], hide: true, click 2: {}}   # appears on click 2

The clicks are the slide's, counted from 1 as its builds are: an object that builds in takes
the click after those before it, and ``click 2`` comes with the second. The slide has as many
clicks as its builds take or its last ``click`` names, whichever is more. A figure's parts are
named as its own ``hide`` names them; what a click does not say of a figure's parts is as its
figure says it.

Drawn, the slide is as it is before its first click; what a click changes is marked with how it
is shown at each step (``SHOWS``), and what is faint at the first step but not at another keeps
its paints as they are plainly (``WAS``): a show (present.js, stepping.js) shows each step by
changing those alone, and a PDF draws a page of each (``at_step``) as the slide would be drawn
were each step its own.
"""

from __future__ import annotations

import re
import xml.etree.ElementTree as ET
from collections.abc import Mapping, Sequence
from dataclasses import replace
from typing import Any

from flexo_talk.showing import DIMMED, HIDDEN, _key

SHOWN = "shown"
"""How what is shown plainly at a step is said (``SHOWS``)."""
SHOWS = "data-flexo-shows"
"""On what a click shows anew: how it is shown at each of the slide's steps, in turn, a word
each -- ``shown``, ``dimmed`` or ``hidden`` (its last word holds for any step after)."""
WAS = "data-flexo-was-"
"""On each part of what is faint at the slide's first step but plain at another: each paint
of its as it is plainly, by name (``data-flexo-was-fill``; "" where it has none)."""
PAGE = "data-flexo-page"
"""On a slide's drawing with steps that show anything anew: the page's colour, which what is
faint is drawn nearer to."""

CLICK = re.compile(r"click ([1-9][0-9]*)")
"""The key saying how an object or a shape is shown from a click on: ``click 2``."""
_NEARLY = re.compile(r"\s*(?:on\s*)?clicks?[\s_-]*[+-]?\d*\s*", re.IGNORECASE)


def click_of(key: object) -> int | None:
    """The click a key names (``click 2``: 2), or None for any other."""

    found = CLICK.fullmatch(key) if isinstance(key, str) else None
    return int(found.group(1)) if found else None


def key_of(click: int) -> str:
    """The key that says how something is shown from ``click`` on."""

    return f"click {click}"


def nearly_click(key: object) -> bool:
    """Whether a key looks meant to name a click and does not (``click2``, ``click 0``)."""

    return isinstance(key, str) and click_of(key) is None and bool(_NEARLY.fullmatch(key))


def clicks_said(said: Mapping[str, Any]) -> dict[int, Any]:
    """What a block or a shape says of each click (``click 2: {...}``), by its number, in order."""

    return dict(sorted((number, value) for key, value in said.items() if (number := click_of(key)) is not None))


def entry_problem(value: object, *, shape: bool = False) -> str | None:
    """What is wrong with what a ``click`` says, if anything: it is a mapping of ``hide``, ``dim``
    and ``highlight`` (a shape's each true or false)."""

    example = "{dim: true}" if shape else "{highlight: [2]}"
    if value is None:
        return None
    if not isinstance(value, dict):
        return (f"says how it is shown from that click on: a mapping of hide, dim and highlight, as its own "
                f"({example}; {{}} for plainly), not {value!r}.")
    unknown = [str(key) for key in value if key not in ("hide", "dim", "highlight")]
    if unknown:
        return (f"says how it is shown from that click on, with hide, dim and highlight alone, not "
                f"{', '.join(unknown)}.")
    if shape:
        wrong = [key for key, said in value.items() if not isinstance(said, bool)]
        if wrong:
            return f"is a shape\u2019s: {wrong[0]} is true or false."
    return None


def last_click(slide: Any) -> int:
    """The last click anything on ``slide`` names to be shown anew on (0 for none)."""

    found = 0
    for region in slide.regions.values():
        for later in region.later.values():
            found = max(found, *later)
    for shape in slide.shapes:
        if isinstance(shape, dict):
            found = max(found, *clicks_said(shape), 0)
    return found


def shape_said(shape: Mapping[str, Any], click: int) -> Mapping[str, Any]:
    """What says how a shape is shown at ``click``: its last ``click`` up to it, else itself."""

    named = [number for number in clicks_said(shape) if number <= click]
    if not named:
        return shape
    said = shape[key_of(max(named))]
    return said if isinstance(said, dict) else {}


# -- a figure's parts --------------------------------------------------------------------


def figure_parts(
    spec: Any, identifier: str, lists: tuple[Sequence[str], Sequence[str], Sequence[str]]
) -> dict[str, str]:
    """How each part of a figure drawn as ``identifier`` is drawn where not plainly, by the id it
    is drawn with on the slide, with ``lists`` -- its parts hidden, dimmed and highlighted -- as
    the figure would draw them itself (``flexo.showing``): a line as its ends, a group's box and
    title as what it holds, a branch of a line as the shape it goes to, a shape drawn over the
    figure as what it is on."""

    from flexo.showing import states

    hidden, dimmed, lit = (tuple(str(name) for name in names) for names in lists)
    if not (hidden or dimmed or lit):
        return {}
    figure = replace(spec, hidden=hidden, dimmed=dimmed, highlighted=lit)
    shown = states(figure)
    shown = _branches(shown, figure)
    shown |= _over(shown, figure)
    groups = {group.id for group in figure.groups}
    found: dict[str, str] = {}
    for entity, how in shown.items():
        if entity in groups:
            # (A group is its box and its title: what it holds is shown as each says.)
            for piece in ("container", "label", "shadow"):
                found[f"{identifier}.{entity}.{piece}"] = how
        else:
            found[f"{identifier}.{entity}"] = how
    return found


def _branches(shown: dict[str, str], figure: Any) -> dict[str, str]:
    """``shown`` with each branch of a line that branches shown as the shape it goes to or comes
    from is, where the line as a whole is not (``flexo.showing.branches``): its branches drawn in
    the order of its ends."""

    found = dict(shown)
    for net in figure.nets:
        whole = shown.get(net.id)
        if whole == HIDDEN:
            continue
        for side, ports in (("source", net.sources), ("target", net.targets)):
            for index, port in enumerate(ports, 1):
                how = shown.get(port.node_id)
                if how == HIDDEN or (how == DIMMED and whole is None):
                    found[f"{net.id}.{side}.{index}"] = how
    return found


def _over(shown: Mapping[str, str], figure: Any) -> dict[str, str]:
    """How each shape drawn over a figure is shown (``flexo.figure_shapes``): as the figure's
    lists name it, else as the parts it is on are."""

    from flexo.figure_shapes import attached, name_of

    hidden, dimmed, lit = set(figure.hidden), set(figure.dimmed), set(figure.highlighted)
    found: dict[str, str] = {}
    for index, shape in enumerate(getattr(figure, "shapes", ()) or ()):
        written = getattr(shape, "spec", None)
        if not written:
            continue
        name = name_of(written, index)
        if name in hidden:
            found[name] = HIDDEN
            continue
        if name in lit:
            continue
        if name in dimmed:
            found[name] = DIMMED
            continue
        round_ = [str(part) for part in written.get("around") or []]
        ends = [part for part in attached(written) if part not in round_]
        how = [shown.get(part) for part in ends]
        boxed = [shown.get(part) for part in round_]
        if HIDDEN in how or (boxed and all(item == HIDDEN for item in boxed)):
            found[name] = HIDDEN
        elif any(item is not None for item in (*how, *boxed)) or (
            lit and not any(part in lit for part in (*ends, *round_))
        ):
            found[name] = DIMMED
    return found


# -- drawn -------------------------------------------------------------------------------


def chosen_at(root: ET.Element, states: Sequence[Mapping[str, str]]) -> list[dict[str, str]]:
    """For each of ``states`` (how what is on a slide is shown at a step, by the id it is drawn
    with: ``flexo_talk.showing.slide_states``), what of ``root`` is marked so: each once, at the
    outermost of what is drawn of it -- in something faint, only what is hidden marked again
    (as ``flexo_talk.showing.mark_slide`` marks one). Gone through once for them all."""

    count = len(states)
    found: list[dict[str, str]] = [{} for _ in states]
    if not any(states):
        return found
    empty: frozenset[str] = frozenset()
    stack: list[tuple[ET.Element, tuple[frozenset[str], ...], tuple[str | None, ...]]] = [
        (root, (empty,) * count, (None,) * count)
    ]
    while stack:
        element, covered, within = stack.pop()
        identifier = element.get("id")
        if identifier:
            now_covered, now_within = list(covered), list(within)
            for step, states_here in enumerate(states):
                if not states_here or within[step] == HIDDEN:
                    continue
                key = _key(states_here, identifier)  # type: ignore[arg-type]
                if key is None or key in covered[step]:
                    continue
                how = states_here[key]
                if within[step] is None or how == HIDDEN:
                    found[step][identifier] = how
                    now_within[step] = how if within[step] is None or how == HIDDEN else within[step]
                now_covered[step] = covered[step] | {key}
            covered, within = tuple(now_covered), tuple(now_within)
        stack.extend((child, covered, within) for child in reversed(list(element)))
    return found


def mark_steps(root: ET.Element, states: Sequence[Mapping[str, str]], page: str) -> dict[str, tuple[str, ...]]:
    """``root`` (a slide's drawing) drawn as the first of ``states`` says -- its steps' each --
    and what is shown otherwise at another step marked with how it is shown at each (``SHOWS``),
    its paints as they are plainly kept where it is faint at the first (``WAS``). What is shown
    alike at every step is drawn so, and marked no more. How each of those is shown at each step,
    by its id."""

    from flexo.showing import mark

    chosen = chosen_at(root, states)
    varying: dict[str, tuple[str, ...]] = {}
    first: dict[str, str] = {}
    for identifier in dict.fromkeys(name for marks in chosen for name in marks):
        seq = tuple(marks.get(identifier) or SHOWN for marks in chosen)
        if all(how == seq[0] for how in seq):
            first[identifier] = seq[0]
        else:
            varying[identifier] = seq
            if seq[0] != SHOWN:
                first[identifier] = seq[0]
    if not varying:
        mark(root, first, canvas=page)
        return varying
    elements = {element.get("id"): element for element in root.iter() if element.get("id") in varying}
    kept = {
        identifier: [(one, dict(one.attrib)) for one in elements[identifier].iter()]
        for identifier, seq in varying.items() if seq[0] == DIMMED and identifier in elements
    }
    mark(root, first, canvas=page)
    for was in kept.values():
        for one, attributes in was:
            for name in dict.fromkeys((*attributes, *one.attrib)):
                if name.startswith("data-flexo") or attributes.get(name) == one.get(name):
                    continue
                one.set(WAS + name, attributes.get(name, ""))
    for identifier, seq in varying.items():
        if identifier in elements:
            elements[identifier].set(SHOWS, " ".join(seq))
    root.set(PAGE, page)
    return varying


def plainly(element: ET.Element) -> None:
    """``element`` -- marked to be shown anew (``SHOWS``) -- drawn plainly: shown again where it
    is hidden, its paints as they are plainly where it is faint."""

    from flexo.showing import MARK

    how = element.attrib.pop(MARK, None)
    if how == HIDDEN:
        element.attrib.pop("visibility", None)
    elif how == DIMMED:
        for one in element.iter():
            for name, value in list(one.attrib.items()):
                if not name.startswith(WAS):
                    continue
                del one.attrib[name]
                if value:
                    one.set(name[len(WAS):], value)
                else:
                    one.attrib.pop(name[len(WAS):], None)


def step_of(seq: str, step: int) -> str:
    """How what is marked ``seq`` (``SHOWS``) is shown at ``step`` (from 1)."""

    words = seq.split()
    return words[max(0, min(step, len(words)) - 1)] if words else SHOWN


def at_step(root: ET.Element, step: int) -> None:
    """``root`` -- a slide's drawing, marked as ``mark_steps`` marks one -- drawn as the slide is
    at ``step`` (from 1): what shows anew drawn as it is shown then, as the slide would be drawn
    were that how it is shown."""

    from flexo.showing import mark

    marked = [element for element in root.iter() if element.get(SHOWS)]
    if not marked:
        return
    shown: dict[str, str] = {}
    for element in marked:
        plainly(element)
        how = step_of(element.get(SHOWS, ""), step)
        if how != SHOWN and element.get("id"):
            shown[element.get("id")] = how  # type: ignore[index]
    mark(root, shown, canvas=root.get(PAGE) or "#ffffff")


def all_plainly(root: ET.Element) -> dict[str, tuple[str, ...]]:
    """``root`` with all it shows anew drawn plainly (each step's way to be shown laid over it
    elsewhere: a PowerPoint's animations): how each is shown at each step, by its id."""

    found: dict[str, tuple[str, ...]] = {}
    for element in root.iter():
        seq = element.get(SHOWS)
        if seq:
            plainly(element)
            if element.get("id"):
                found[element.get("id")] = tuple(seq.split())  # type: ignore[index]
    return found
