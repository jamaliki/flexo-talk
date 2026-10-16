"""Frames: a visualisation that changes a little from slide to slide, drawn as one figure.

A talk often shows one picture slide after slide, a little changed on each: a part added, a
label changed, a step lit. Each slide's figure, laid out alone for its place, comes out its own
size -- one with a part more is drawn smaller to fit, its parts shifted along -- so the figure
jumps from one slide to the next, the parts that stayed the same with it. Figure blocks that
name the same frame are drawn as one::

  slides:
  - title: Sample the prior
    right:
    - {figure: figures/smc-1.yaml, frame: smc}
  - title: Weight the samples
    right:
    - {figure: figures/smc-2.yaml, frame: smc}

- **The same parts.** Each version is laid out with every part the frame's others have
  (``completed``): what it lacks is put where its others have it -- in the same group, beside
  the same neighbours -- and hidden (``flexo.showing``), so the layout keeps its room. The
  layout sees the same figure in each, and puts the parts they share in the same places.
- **The same way.** Each is laid out as the frame's first is -- turned to fit or not, spaced
  closer or not, folded or not (flexo's ``fit_in_box(keep=...)``) -- the way that suits the
  first with all of it shown, as the frame draws all of its versions' parts' room.
- **The same places.** Each is moved so that its parts are where the first's of the same name
  are (``offset``): by the move that brings the most of them exactly there.
- **One size.** They are drawn as one figure as large as all of them together (``extent``):
  each version at the scale that fits that whole -- the largest version's, so none is made
  smaller to fit what it holds -- from its top left, wherever the slide sets it.

So parts with the same id that the layout puts in the same place within their own figure end
up in exactly the same place on every slide. A frame's figures line up where their slides set
them in the same place: the same place of the same layout, or placed with the same ``at`` and
``width`` (the studio's Match on Other Slides sets both). A version's own ``hide``, ``dim``,
``highlight`` and ``stages`` are its own as ever; a frame of one figure shown with different
parts hidden (``'#pipeline'`` with ``hide:`` on each slide) is that figure's room kept whole on
every slide, its hidden parts' too.

The layout itself is not seeded or pinned from the first version: flexo's layout is a box
layout -- rows, columns, grids, each part's place following from the sizes of what is beside it
-- not a search that could start from positions, and a part pinned where the first version had
it would leave its group a size its neighbours were not laid out for. Laying each out with the
same parts does what pinning would, where it can: the same parts, of the same sizes, in the same
groups, are placed the same way.
"""

from __future__ import annotations

import xml.etree.ElementTree as ET
from collections import Counter
from collections.abc import Iterable, Sequence
from dataclasses import replace
from typing import Any

SVG_NS = "http://www.w3.org/2000/svg"
ET.register_namespace("", SVG_NS)
ET.register_namespace("inkscape", "http://www.inkscape.org/namespaces/inkscape")
ET.register_namespace("xlink", "http://www.w3.org/1999/xlink")

ALIKE = 0.05
"""How near two moves are (points) to be the same move, as parts are lined up."""


def members(deck: Any, name: str) -> list[Any]:
    """The figure blocks of ``deck`` in the frame ``name``, in the order its slides show them."""

    from flexo_talk.deck import _Figure

    return [
        block
        for slide in deck.slides
        for region in slide.regions.values()
        for block in region.blocks
        if isinstance(block, _Figure) and block.frame == name
    ]


def frames_of(document: Any) -> dict[str, list[dict[str, Any]]]:
    """The frames of a deck document: each name, with the figure blocks naming it, in order."""

    from flexo_talk.embedding import places

    found: dict[str, list[dict[str, Any]]] = {}
    for _, block in places(document):
        name = block.get("frame")
        if isinstance(name, str) and name.strip():
            found.setdefault(name.strip(), []).append(block)
    return found


# -- the same parts --


def _ends(edge: Any) -> tuple[str, str]:
    return edge.source.node_id, edge.target.node_id


def completed(spec: Any, others: Iterable[Any]) -> tuple[Any, tuple[str, ...]]:
    """``spec`` with every part of ``others`` that it lacks, hidden: shapes, groups, lines and
    branching lines, each put where its own figure has it -- in the same group (one it lacks
    made too), after the part before it there -- unless that would take one of ``spec``'s own
    from where it is. A line is one it has already if it joins the same ends. What was added,
    by id, for it to be left out of the drawing."""

    added: list[str] = []
    for other in others:
        spec, more = _merged(spec, other)
        added += more
    if added:
        spec = replace(spec, hidden=(*spec.hidden, *dict.fromkeys(added)))
    return spec, tuple(dict.fromkeys(added))


def _merged(spec: Any, other: Any) -> tuple[Any, list[str]]:
    nodes = {node.id: node for node in spec.nodes}
    groups = {group.id: group for group in spec.groups}
    children = {group.id: list(group.children) for group in spec.groups}
    placed = {child for group in spec.groups for child in group.children}
    theirs = {group.id: group for group in other.groups}
    their_nodes = {node.id: node for node in other.nodes}
    added: list[str] = []
    new_nodes: list[Any] = []
    new_groups: list[Any] = []

    def held(ident: str) -> bool:
        return ident in nodes or ident in groups

    def put(parent: str, ident: str, order: Sequence[str]) -> None:
        # After the last of those before it in its own group that this figure has there.
        kids = children[parent]
        before = list(order[: list(order).index(ident)])
        at = 0
        for one in reversed(before):
            if one in kids:
                at = kids.index(one) + 1
                break
        kids.insert(at, ident)
        placed.add(ident)

    def take(ident: str, parent: str, order: Sequence[str]) -> None:
        """One of ``other``'s parts (and, a group, all it holds that this figure lacks)."""

        if held(ident) or ident in placed:
            return
        if ident in their_nodes:
            node = their_nodes[ident]
            if node.align_with and node.align_with not in nodes and node.align_with not in their_nodes:
                node = replace(node, align_with=None)
            nodes[ident] = node
            new_nodes.append(node)
        elif ident in theirs:
            group = theirs[ident]
            groups[ident] = group
            children[ident] = []
            for child in group.children:
                take(child, ident, group.children)
            if not children[ident]:
                del groups[ident], children[ident]
                return
            new_groups.append(ident)
        else:
            return
        added.append(ident)
        put(parent, ident, order)

    # Group by group, as the other figure holds them, from its root down.
    for group in other.groups:
        if group.id not in groups:
            continue
        for child in group.children:
            if child in theirs and child in groups:
                continue
            take(child, group.id, group.children)
    # (A shape it holds in no group: the other's root holds it.)
    if spec.root in groups:
        for node in other.nodes:
            if not held(node.id) and node.id not in placed and not any(node.id in g.children for g in other.groups):
                take(node.id, spec.root, [node.id])

    edges = list(spec.edges)
    ids = {edge.id for edge in edges}
    joined = {_ends(edge) for edge in edges}
    for edge in other.edges:
        if edge.id in ids and _ends(edge) in joined:
            continue
        if _ends(edge) in joined or not (held(edge.source.node_id) and held(edge.target.node_id)):
            continue
        ident = edge.id if edge.id not in ids else f"{edge.id}.frame"
        edges.append(replace(edge, id=ident))
        ids.add(ident)
        joined.add(_ends(edge))
        added.append(ident)
    nets = list(spec.nets)
    known = {net.id for net in nets}
    for net in other.nets:
        ends = [port.node_id for port in (*net.sources, *net.targets)]
        if net.id in known or not all(held(end) for end in ends):
            continue
        nets.append(net)
        known.add(net.id)
        added.append(net.id)
    if not added:
        return spec, []
    groups_now = [replace(group, children=tuple(children[group.id])) for group in spec.groups]
    groups_now += [replace(groups[ident], children=tuple(children[ident])) for ident in new_groups]
    return replace(
        spec, nodes=(*spec.nodes, *new_nodes), groups=tuple(groups_now), edges=tuple(edges), nets=tuple(nets),
    ), added


EVENED = frozenset({"block", "text", "terminal", "database", "server", "queue", "document", "io"})
"""Shapes that are a box round their words: given the largest size they have in any version of
a frame, a shape whose words change keeps its size, and what is beside it its place."""

ROOM = 0.5
"""How much wider (points) than its widest words a shape is given, for them never to wrap."""

_EVENED: dict[tuple, list[Any]] = {}


def evened(specs: Sequence[Any], own: Sequence[Iterable[str]]) -> list[Any]:
    """``specs`` (a frame's versions, ``completed``) with each shape whose words differ from one
    to another (``EVENED``'s kinds) given, in all of them, the largest size it has in any: its
    words centred in it, whatever they are, and nothing beside it moved along by them. ``own``:
    the shapes each version has of its own (not added from the others), whose sizes count."""

    from flexo.layout.measure import measure_figure
    from flexo.themes import figure_style
    from flexo.units import Length

    key = tuple(specs)
    if key in _EVENED:
        return _EVENED[key]
    sizes: dict[str, list[tuple[float, float]]] = {}
    for spec, mine in zip(specs, own, strict=True):
        mine = set(mine)
        try:
            measured = measure_figure(spec, style=figure_style(spec))
        except Exception:
            return list(specs)
        for node in measured.nodes:
            free = node.spec.width is None and node.spec.height is None
            if node.spec.id in mine and node.spec.kind in EVENED and free:
                sizes.setdefault(node.spec.id, []).append((node.intrinsic_size.width, node.intrinsic_size.height))
    widest = {
        name: (max(width for width, _ in found) + ROOM, max(height for _, height in found))
        for name, found in sizes.items()
        if len(found) > 1 and len({(round(width, 2), round(height, 2)) for width, height in found}) > 1
    }
    made = list(specs)
    if widest:
        made = [
            replace(spec, nodes=tuple(
                replace(node, width=Length(widest[node.id][0]), height=Length(widest[node.id][1]))
                if node.id in widest and node.kind in EVENED else node
                for node in spec.nodes
            ))
            for spec in specs
        ]
    _EVENED[key] = made
    while len(_EVENED) > 32:
        _EVENED.pop(next(iter(_EVENED)))
    return made


def stripped(svg: str, added: Iterable[str]) -> str:
    """A figure's drawing without the parts ``added`` to it (``completed``): laid out, and
    hidden, they are nowhere in what it draws -- nor chosen, nor shown faintly by an editor."""

    gone = set(added)
    if not gone:
        return svg
    root = ET.fromstring(svg)
    for parent in list(root.iter()):
        for child in list(parent):
            name = child.get("id") or ""
            if name in gone or (child.get("data-hit-for") or "") in gone:
                parent.remove(child)
    return ET.tostring(root, encoding="unicode")


# -- the same places, one size --


def part_boxes(compilation: Any) -> dict[str, list[float]]:
    """Where a compiled figure's shapes are, by id: ``[x, y, width, height]`` in its points."""

    found: dict[str, list[float]] = {}
    for node in compilation.routed.fitted.nodes:
        bounds = node.bounds
        found[node.measured.spec.id] = [bounds.x, bounds.y, bounds.width, bounds.height]
    return found


def offset(first: dict[str, Sequence[float]], parts: dict[str, Sequence[float]]) -> tuple[float, float]:
    """How far a version is moved for its parts to be where the frame's first has those of the
    same name: the move the most of them agree on (to within ``ALIKE``), the least of those
    should several agree as often. None shared: none."""

    moves: dict[tuple[int, int], list[tuple[float, float]]] = {}
    for name, box in parts.items():
        theirs = first.get(name)
        if theirs is None:
            continue
        here = (box[0] + box[2] / 2, box[1] + box[3] / 2)
        there = (theirs[0] + theirs[2] / 2, theirs[1] + theirs[3] / 2)
        move = (there[0] - here[0], there[1] - here[1])
        moves.setdefault((round(move[0] / ALIKE), round(move[1] / ALIKE)), []).append(move)
    if not moves:
        return 0.0, 0.0
    counted = Counter({key: len(found) for key, found in moves.items()})
    best = max(counted.values())
    agreed = [key for key, count in counted.items() if count == best]
    key = min(agreed, key=lambda key: (abs(key[0]) + abs(key[1]), key))
    # (Those that agree, as they are: the move most of them make exactly.)
    exact = Counter(moves[key]).most_common(1)[0][0]
    return exact


def extent(inks: Iterable[Sequence[float]], moves: Iterable[Sequence[float]]) -> tuple[float, float, float, float]:
    """What all of a frame's versions draw together, each moved as ``offset`` says: ``left,
    top, width, height`` in its first's points."""

    lefts, tops, rights, bottoms = [], [], [], []
    for (left, top, width, height), (dx, dy) in zip(inks, moves, strict=True):
        lefts.append(left + dx)
        tops.append(top + dy)
        rights.append(left + width + dx)
        bottoms.append(top + height + dy)
    left, top = min(lefts), min(tops)
    return left, top, max(rights) - left, max(bottoms) - top
