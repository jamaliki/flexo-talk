"""What a click shows anew (``flexo_talk.onclick``), in a PowerPoint: each step a click of the
slide's animations, with its builds.

PowerPoint animates a shape on the slide, or a paragraph of one: what a click shows anew inside
an object (a figure's part, a line of code, a picture of a gallery) is lifted out of it into a
group of its own beside it, where it was drawn (``lifted``), as a figure's parts that appear on a
click are (``export.clicks_lifted``). Everything shown anew is drawn plainly, and each step is:

- hidden: its Disappear on the click it goes, its Appear on the click it comes back (a shape
  whose first is an Appear is not there before it, as PowerPoint has it);
- dimmed: its Transparency, to the strength flexo draws what is faint at (``flexo.showing.DIM``)
  -- the faint colour itself, on the page -- held until a later Transparency sets it back to
  whole;
- shown again: the Appear or the Transparency that undoes the one before.

How it is shown before the first click is set as the slide begins (with its animations' first,
not waiting for a click). A table is animated as one: a row or a cell of one shown anew is
covered, where it is, by a veil of the page's colour -- see-through enough to leave its words
as faint as flexo draws them, or not at all to hide them -- that comes and goes on its clicks
(``veils``). (PowerPoint's own view of the slide, being edited, shows every shape, veils too.)
"""

from __future__ import annotations

import re
import xml.etree.ElementTree as ET
from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field

from lxml import etree

from flexo_talk.onclick import SHOWN, SHOWS, all_plainly

_A = "http://schemas.openxmlformats.org/drawingml/2006/main"
_P = "http://schemas.openxmlformats.org/presentationml/2006/main"
_NS = f'xmlns:a="{_A}" xmlns:p="{_P}"'
EMU_PER_POINT = 12700


@dataclass(frozen=True, slots=True)
class Target:
    """What one of a slide's animations acts on: a shape (``spid``), or a run of its paragraphs
    (``paragraphs``: the first and the last, from 0)."""

    spid: int
    paragraphs: tuple[int, int] | None = None


@dataclass(slots=True)
class Effect:
    """One animation: ``kind`` -- ``appear``, ``disappear``, or ``fade`` (Transparency, to
    ``opacity``) -- of ``target``."""

    kind: str
    target: Target
    opacity: float = 1.0


@dataclass(slots=True)
class Timeline:
    """A slide's animations: those as it begins, and each click's."""

    start: list[Effect] = field(default_factory=list)
    clicks: list[list[Effect]] = field(default_factory=list)

    def at(self, click: int) -> list[Effect]:
        while len(self.clicks) < click:
            self.clicks.append([])
        return self.clicks[click - 1]


# -- lifted out of what they are drawn in ---------------------------------------------------


def lifted(
    svg: str, slide_id: str, native: Iterable[str]
) -> tuple[str, dict[str, tuple[str, ...]], dict[str, str]]:
    """The slide (its drawing: ``svg``) with all it shows anew drawn plainly, and what of it is
    inside an object lifted out of it: for each object, what is shown alike at every step
    gathered into a group of its own beside it (``<object>.shows.<n>``) -- each part keeping its
    place, and every group it was in round it again -- drawn over the rest of it. ``native``:
    the lists and tables a PowerPoint sets itself, whose parts are animated there. How each
    thing animated (by its name) is shown at each step, and what each group lifted out of
    something is lifted out of (by their names: it builds in with it)."""

    root = ET.fromstring(svg)
    shows = all_plainly(root)
    if not shows:
        return svg, {}, {}
    for item in root.iter():
        item.attrib.pop(SHOWS, None)
    natives = tuple(native)
    parents = {child: parent for parent in root.iter() for child in parent}
    holders = {"region", "placed"}
    elements = {item.get("id"): item for item in root.iter() if item.get("id") in shows}
    found: dict[str, tuple[str, ...]] = {}
    gathered: dict[tuple[ET.Element, tuple[str, ...]], list[ET.Element]] = {}
    for ident, seq in shows.items():
        item = elements.get(ident)
        if item is None or item not in parents:
            continue
        native = any(ident == name or ident.startswith(f"{name}.") for name in natives)
        if native or ident.startswith(f"{slide_id}.shapes."):
            found[ident] = seq
            continue
        # The object it is drawn in: what stands on the slide itself (in its layer, a region, or
        # with the objects placed where they say).
        holder = item
        while holder in parents and not _standing(parents[holder], slide_id, holders):
            holder = parents[holder]
        if holder is item or holder not in parents:
            found[ident] = seq
            continue
        # Lifted out of what it is in, it is shown as that is as well: hidden with it, faint with it.
        at = parents.get(item)
        while at is not None and at is not root:
            if at.get("id") in shows:
                seq = tuple(_together(own, outer) for own, outer in zip(seq, shows[at.get("id")], strict=True))
            at = parents.get(at)
        gathered.setdefault((holder, seq), []).append(item)
    after: dict[ET.Element, int] = {}
    out_of: dict[str, str] = {}
    for (holder, seq), items in gathered.items():
        after[holder] = after.get(holder, 0) + 1
        name = f"{holder.get('id') or slide_id}.shows.{after[holder]}"
        kept = {key: value for key, value in holder.attrib.items() if not key.startswith("data-")}
        group = ET.Element(holder.tag, {**kept, "id": name})
        twins = {holder: group}

        def twin(item: ET.Element, twins: dict = twins) -> ET.Element:
            if item not in twins:
                shell = {key: value for key, value in item.attrib.items() if key != "id"}
                twins[item] = ET.SubElement(twin(parents[item]), item.tag, shell)
            return twins[item]

        for item in items:
            # (One within another lifted with it goes with it.)
            if any(other is not item and _within(item, other, parents) for other in items):
                continue
            parents[item].remove(item)
            twin(parents[item]).append(item)
        place = parents[holder]
        place.insert(list(place).index(holder) + after[holder], group)
        found[name] = seq
        out_of[name] = holder.get("id") or ""
    return '<?xml version="1.0" encoding="UTF-8"?>\n' + ET.tostring(root, encoding="unicode"), found, out_of


def _together(own: str, outer: str) -> str:
    """How something shown ``own`` in what is shown ``outer`` is shown: the more apart of the two."""

    from flexo_talk.showing import stronger

    return stronger(None if own == SHOWN else own, None if outer == SHOWN else outer) or SHOWN


def _standing(parent: ET.Element, slide_id: str, holders: set[str]) -> bool:
    return (parent.get("data-flexo-talk") in holders or parent.get("id") == f"{slide_id}.content"
            or parent.tag.rsplit("}", 1)[-1] == "svg")


def _within(item: ET.Element, other: ET.Element, parents: dict) -> bool:
    at = parents.get(item)
    while at is not None:
        if at is other:
            return True
        at = parents.get(at)
    return False


# -- the animations ------------------------------------------------------------------------


def look(how: str) -> tuple[bool, float]:
    """How a shape that is shown ``how`` looks: whether it is there, and how much of it shows."""

    from flexo.showing import DIM

    return (how != "hidden", DIM if how == "dimmed" else 1.0)


def animate(timeline: Timeline, target: Target, looks: Sequence[tuple[bool, float]]) -> None:
    """``target``'s animations, it looking as ``looks`` says at each step (``look``): set as the
    slide begins, then on each click that changes it."""

    there, opacity = looks[0]
    if there and opacity != 1.0:
        timeline.start.append(Effect("fade", target, opacity))
    elif not there:
        opacity = 1.0
    for click, (now, wanted) in enumerate(looks[1:], 1):
        effects = timeline.at(click)
        if now and not there:
            # (Appearing first: a shape whose first animation is its Appear is not there before.)
            effects.append(Effect("appear", target))
        if now and wanted != opacity:
            effects.append(Effect("fade", target, wanted))
            opacity = wanted
        if there and not now:
            effects.append(Effect("disappear", target))
        there = now


def veils(
    tree: etree._Element, tables: Iterable[str], shows: dict[str, tuple[str, ...]], page: str,
    calls: dict[int, str],
) -> dict[int, tuple]:
    """Over each native table's rows and cells that a click shows anew, veils of the page's
    colour, put in the slide's ``tree`` over the table -- a row's whole where all its cells are
    shown alike, else a cell's: one see-through enough to leave its words as faint as flexo draws
    them, there at the steps it is faint, and one not see-through at all, there at the steps it
    is hidden. How each veil (by its shape's id) looks at each step (``look``); ``calls`` is told
    what each is called."""

    from flexo.showing import DIM

    found: dict[int, tuple] = {}
    ids = max((int(item) for item in tree.xpath(".//@id") if str(item).isdigit()), default=1)
    colour = page.lstrip("#").upper() if re.fullmatch(r"#[0-9A-Fa-f]{6}", page or "") else "FFFFFF"
    for name in tables:
        frame = next((item for item in tree.iter(f"{{{_P}}}graphicFrame")
                      if (named := next(item.iter(f"{{{_P}}}cNvPr"), None)) is not None and named.get("name") == name),
                     None)
        if frame is None:
            continue
        cells = {key: seq for key, seq in shows.items() if key.startswith(f"{name}.")}
        if not cells:
            continue
        off = frame.find(f"{{{_P}}}xfrm/{{{_A}}}off")
        left, top = int(off.get("x", "0")), int(off.get("y", "0"))
        columns = [int(column.get("w", "0")) for column in frame.iter(f"{{{_A}}}gridCol")]
        rows = [int(row.get("h", "0")) for row in frame.iter(f"{{{_A}}}tr")]
        place = frame.getparent()
        at = list(place).index(frame)
        for row, height in enumerate(rows):
            each = [cells.get(f"{name}.{row}.{column}") for column in range(len(columns))]
            if not any(each):
                continue
            y = top + sum(rows[:row])
            if all(seq == each[0] for seq in each):
                spans = [(0, len(columns), each[0])]
            else:
                spans = [(column, column + 1, seq) for column, seq in enumerate(each) if seq]
            for first, end, seq in spans:
                x = left + sum(columns[:first])
                for how, alpha in (("dimmed", 1.0 - DIM), ("hidden", 1.0)):
                    if how not in seq:
                        continue
                    ids += 1
                    # (Named as its table is, to be read with it -- export._read_in_order -- then as a
                    # person would name it: ``name_added``.)
                    called = f"{'Faint ' if how == 'dimmed' else ''}Veil over Row {row + 1}" + (
                        f", Cell {first + 1}" if end - first == 1 and len(columns) > 1 else "")
                    calls[ids] = called
                    veil = etree.fromstring(
                        f'<p:sp {_NS}><p:nvSpPr><p:cNvPr id="{ids}" name="{name}.veil.{ids}"/>'
                        f'<p:cNvSpPr/><p:nvPr/></p:nvSpPr><p:spPr><a:xfrm><a:off x="{x}" y="{y}"/>'
                        f'<a:ext cx="{sum(columns[first:end])}" cy="{height}"/></a:xfrm><a:prstGeom prst="rect">'
                        f'<a:avLst/></a:prstGeom><a:solidFill><a:srgbClr val="{colour}"><a:alpha '
                        f'val="{round(alpha * 100000)}"/></a:srgbClr></a:solidFill><a:ln><a:noFill/></a:ln></p:spPr>'
                        f"</p:sp>"
                    )
                    at += 1
                    place.insert(at, veil)
                    found[ids] = tuple((state == how, 1.0) for state in seq)
    return found


def add_timing(slide_element: etree._Element, timeline: Timeline, kinds: dict[int, str]) -> None:
    """The slide's animations (``timeline``) as its timing: what it begins with started as it
    begins, then a click for each of its clicks, those it shows together together. ``kinds``:
    each shape's kind (``sp``, ``pic``, ``grpSp``, ``graphicFrame``), by its id, for how
    PowerPoint lists its builds."""

    clicks = list(timeline.clicks)
    while clicks and not clicks[-1]:
        clicks.pop()
    if not timeline.start and not any(clicks):
        return
    ids = iter(range(3, 1_000_000))
    built: dict[int, int] = {}
    groups: list[tuple[int, int, bool]] = []  # (shape, its build, by paragraph)

    def effect_xml(effect: Effect, node: str) -> str:
        spid = effect.target.spid
        group = built.get(spid, 0)
        built[spid] = group + 1
        groups.append((spid, group, effect.target.paragraphs is not None))
        within = (f'<p:txEl><p:pRg st="{effect.target.paragraphs[0]}" end="{effect.target.paragraphs[1]}"/></p:txEl>'
                  if effect.target.paragraphs else "")
        target = f'<p:tgtEl><p:spTgt spid="{spid}">{within}</p:spTgt></p:tgtEl>'
        outer, inner = next(ids), next(ids)
        if effect.kind == "fade":
            last = next(ids)
            amount = f"{effect.opacity:.4g}"
            return (
                f'<p:par><p:cTn id="{outer}" presetID="9" presetClass="emph" presetSubtype="0" fill="hold" '
                f'grpId="{group}" nodeType="{node}"><p:stCondLst><p:cond delay="0"/></p:stCondLst><p:childTnLst>'
                f'<p:set><p:cBhvr><p:cTn id="{inner}" dur="indefinite"/>{target}<p:attrNameLst>'
                f"<p:attrName>style.opacity</p:attrName></p:attrNameLst></p:cBhvr>"
                f'<p:to><p:strVal val="{amount}"/></p:to></p:set>'
                f'<p:animEffect filter="image" prLst="opacity: {amount} "><p:cBhvr rctx="IE">'
                f'<p:cTn id="{last}" dur="indefinite"/>{target}</p:cBhvr></p:animEffect>'
                f"</p:childTnLst></p:cTn></p:par>"
            )
        kind, shown = ("entr", "visible") if effect.kind == "appear" else ("exit", "hidden")
        return (
            f'<p:par><p:cTn id="{outer}" presetID="1" presetClass="{kind}" presetSubtype="0" fill="hold" '
            f'grpId="{group}" nodeType="{node}"><p:stCondLst><p:cond delay="0"/></p:stCondLst><p:childTnLst><p:set>'
            f'<p:cBhvr><p:cTn id="{inner}" dur="1" fill="hold"><p:stCondLst><p:cond delay="0"/></p:stCondLst>'
            f"</p:cTn>{target}<p:attrNameLst><p:attrName>style.visibility</p:attrName></p:attrNameLst></p:cBhvr>"
            f'<p:to><p:strVal val="{shown}"/></p:to></p:set></p:childTnLst></p:cTn></p:par>'
        )

    def click_xml(effects: list[Effect], begins: bool) -> str:
        outer, inner = next(ids), next(ids)
        start = ('<p:cond delay="indefinite"/><p:cond evt="onBegin" delay="0"><p:tn val="2"/></p:cond>' if begins
                 else '<p:cond delay="indefinite"/>')
        shown = "".join(effect_xml(effect, "withEffect" if begins or order else "clickEffect")
                        for order, effect in enumerate(effects))
        return (
            f'<p:par><p:cTn id="{outer}" fill="hold"><p:stCondLst>{start}</p:stCondLst><p:childTnLst><p:par>'
            f'<p:cTn id="{inner}" fill="hold"><p:stCondLst><p:cond delay="0"/></p:stCondLst>'
            f"<p:childTnLst>{shown}</p:childTnLst></p:cTn></p:par></p:childTnLst></p:cTn></p:par>"
        )

    # (A click that changes nothing PowerPoint draws is none there, as a build of nothing is.)
    steps = ([click_xml(timeline.start, True)] if timeline.start else []) + [
        click_xml(effects, False) for effects in clicks if effects
    ]
    builds = []
    for spid, group, paragraphs in groups:
        kind = kinds.get(spid)
        if paragraphs:
            builds.append(f'<p:bldP spid="{spid}" grpId="{group}" build="p"/>')
        elif kind == "sp":
            builds.append(f'<p:bldP spid="{spid}" grpId="{group}" animBg="1"/>')
        elif kind == "graphicFrame":
            builds.append(f'<p:bldGraphic spid="{spid}" grpId="{group}"><p:bldAsOne/></p:bldGraphic>')
    listed = f"<p:bldLst>{''.join(builds)}</p:bldLst>" if builds else ""
    timing = etree.fromstring(
        f'<p:timing {_NS}><p:tnLst><p:par><p:cTn id="1" dur="indefinite" restart="never" nodeType="tmRoot">'
        f'<p:childTnLst><p:seq concurrent="1" nextAc="seek"><p:cTn id="2" dur="indefinite" nodeType="mainSeq">'
        f"<p:childTnLst>{''.join(steps)}</p:childTnLst></p:cTn>"
        f'<p:prevCondLst><p:cond evt="onPrev" delay="0"><p:tgtEl><p:sldTgt/></p:tgtEl></p:cond></p:prevCondLst>'
        f'<p:nextCondLst><p:cond evt="onNext" delay="0"><p:tgtEl><p:sldTgt/></p:tgtEl></p:cond></p:nextCondLst>'
        f"</p:seq></p:childTnLst></p:cTn></p:par></p:tnLst>{listed}</p:timing>"
    )
    slide_element.append(timing)


def add_steps(
    slide_element: etree._Element, tree: etree._Element, item, clicks: list[tuple[int, int, tuple[int, int] | None]],
    animated: dict[str, tuple[str, ...]], shapes: dict[str, int], page: str, out_of: dict[str, str] | None = None,
) -> dict[int, str]:
    """A slide's builds (``clicks``: ``(step, shape id, paragraphs)``, as ``export.write_pptx``
    gathers them) and what each of its clicks shows anew (``animated``: how each thing is shown
    at each step, by its name -- ``lifted``'s) as its animations: each step a click.
    ``shapes``: the slide's shapes' ids, by name; ``page``: its colour, for veils; ``out_of``:
    what each group lifted out of something was lifted out of, to build in with it. What each
    shape added is to be called, by its id, once the slide's are named (``name_added``)."""

    timeline = Timeline()
    # (What is lifted out of something that builds in builds in with it.)
    lifted_from: dict[int, list[int]] = {}
    for name, holder in (out_of or {}).items():
        if name in shapes and holder in shapes:
            lifted_from.setdefault(shapes[holder], []).append(shapes[name])
    for step, shape_id, paragraphs in clicks:
        timeline.at(step - 1).append(Effect("appear", Target(shape_id, paragraphs)))
        if paragraphs is None:
            timeline.at(step - 1).extend(Effect("appear", Target(one)) for one in lifted_from.get(shape_id, ()))
    lists = {layout.id for layout in item.lists}
    tables = {layout.id for layout in item.tables}
    done: set[Target] = set()
    for name, seq in animated.items():
        target = None
        if name in shapes:
            target = Target(shapes[name])
        else:
            found = re.fullmatch(r"(.+)\.(\d+)(?:\.mark)?", name)
            if found and found.group(1) in lists and found.group(1) in shapes:
                index = int(found.group(2))
                target = Target(shapes[found.group(1)], (index, index))
        if target is None or target in done:
            continue
        done.add(target)
        animate(timeline, target, [look(how) for how in seq])
    covered = [name for name in tables if any(key.startswith(f"{name}.") for key in animated)]
    called: dict[int, str] = {}
    for spid, looks in veils(tree, covered, animated, page, called).items():
        animate(timeline, Target(spid), looks)
    _deferred(timeline)
    kinds = {
        int(properties.get("id")): etree.QName(properties.getparent().getparent()).localname
        for properties in slide_element.iter(f"{{{_P}}}cNvPr") if str(properties.get("id", "")).isdigit()
    }
    add_timing(slide_element, timeline, kinds)
    return called


def _deferred(timeline: Timeline) -> None:
    """What is made faint or whole again before it first appears -- as the slide begins, or on a
    click before its Appear -- made so on that click instead, after it appears, as faint as it
    would have been then: its first animation is its Appear, as PowerPoint has a shape that is
    not there before its first (a paragraph of a list: an Appear of a run of them holding it)."""

    def holds(appearing: Target, target: Target) -> bool:
        if appearing.spid != target.spid:
            return False
        if appearing.paragraphs is None or target.paragraphs is None:
            return appearing.paragraphs is None
        return appearing.paragraphs[0] <= target.paragraphs[0] and target.paragraphs[1] <= appearing.paragraphs[1]

    faded = dict.fromkeys(effect.target for effects in (timeline.start, *timeline.clicks) for effect in effects
                          if effect.kind == "fade")
    for target in faded:
        before: list[tuple[list[Effect], Effect]] = []
        found = None
        for effects in (timeline.start, *timeline.clicks):
            for effect in effects:
                if effect.kind in ("appear", "disappear") and holds(effect.target, target):
                    found = (effects, effect)
                    break
                if effect.kind == "fade" and effect.target == target:
                    before.append((effects, effect))
            if found:
                break
        if found is None or found[1].kind != "appear" or not before:
            continue
        for effects, effect in before:
            effects.remove(effect)
        last = before[-1][1]
        if last.opacity != 1.0:
            effects, appearing = found
            effects.insert(effects.index(appearing) + 1, Effect("fade", target, last.opacity))


def name_added(tree: etree._Element, called: dict[int, str]) -> None:
    """The shapes ``add_steps`` added named as it says (``called``, by their ids)."""

    for properties in tree.iter(f"{{{_P}}}cNvPr"):
        name = called.get(int(properties.get("id", "0")))
        if name:
            properties.set("name", name)
