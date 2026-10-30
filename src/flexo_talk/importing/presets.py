# Adapted from DeckWerk's importers/pptx/import_pptx.py (preset and custom geometry), by
# Vincent Sitzmann, under the MIT License: Copyright (c) 2026 Vincent Sitzmann. Permission is
# hereby granted, free of charge, to any person obtaining a copy of that software, to deal in
# it without restriction, provided this notice is kept; it is provided "as is", without
# warranty of any kind. Flexo's changes are under the Apache License 2.0, as the rest of it.
"""A PowerPoint shape's geometry as Flexo draws it: one of Flexo's own kinds where it has the
same one (a rectangle, a rounded one, an ellipse, a block arrow, a speech bubble...), with its
settings from the preset's adjustments; else its outline as SVG path data in its box."""

from __future__ import annotations

import math
import re
from collections.abc import Iterable

from lxml import etree

A = "http://schemas.openxmlformats.org/drawingml/2006/main"

Point = tuple[float, float]

RECTANGLES = {"rect", "flowChartProcess", "flowChartPredefinedProcess", "flowChartInternalStorage",
              "actionButtonBlank", "flowChartPunchedCard"}
ROUNDED = {"roundRect", "flowChartAlternateProcess"}
ELLIPSES = {"ellipse", "flowChartConnector"}
LINES = {"line", "straightConnector1", "lineInv"}
OPEN = {"arc", "bentConnector2", "bentConnector3", "bentConnector4", "bentConnector5", "curvedConnector2",
        "curvedConnector3", "curvedConnector4", "curvedConnector5", "leftBracket", "rightBracket", "bracketPair",
        "leftBrace", "rightBrace", "bracePair"}
"""Presets that are lines, not areas: never filled."""


def adjustments(geometry: etree._Element | None) -> dict[str, float]:
    """A preset's adjustments (``a:avLst``), by name, in DrawingML's units."""

    out: dict[str, float] = {}
    if geometry is None:
        return out
    for guide in geometry.iterfind(f"{{{A}}}avLst/{{{A}}}gd"):
        found = re.match(r"val\s+(-?\d+)", guide.get("fmla") or "")
        if found and guide.get("name"):
            out[guide.get("name") or ""] = float(found.group(1))
    return out


def flexo_kind(preset: str, adjust: dict[str, float], w: float, h: float) -> tuple[str, dict[str, object]] | None:
    """Flexo's kind for a preset, and its settings, where Flexo has the same shape."""

    ss = max(min(w, h), 1e-6)

    def value(name: str, default: float) -> float:
        return adjust.get(name, default)

    if preset in RECTANGLES:
        return "rectangle", {}
    if preset in ROUNDED:
        return "rounded-rectangle", {"corner": max(value("adj", 16667), 0.0) / 100000 * ss}
    if preset in ELLIPSES:
        return "ellipse", {}
    if preset in ("triangle", "flowChartExtract", "flowChartMerge") and preset != "flowChartMerge":
        return "triangle", {"apex": min(max(value("adj", 50000) / 100000, 0.0), 1.0)}
    if preset == "rtTriangle":
        return "right-triangle", {}
    if preset in ("diamond", "flowChartDecision"):
        return "diamond", {}
    if preset == "parallelogram":
        return "parallelogram", {"slant": min(max(value("adj", 25000) / 100000, 0.0), 2.0)}
    if preset == "trapezoid":
        return "trapezoid", {"inset": min(max(value("adj", 25000) / 100000, 0.0), 1.0)}
    if preset == "pentagon":
        return "polygon", {"sides": 5}
    arrows = {"rightArrow": "arrow-right", "leftArrow": "arrow-left", "upArrow": "arrow-up", "downArrow": "arrow-down",
              "leftRightArrow": "arrow-left-right"}
    if preset in arrows:
        return arrows[preset], {"shaft": min(max(value("adj1", 50000) / 100000, 0.0), 1.0),
                                "head": min(max(value("adj2", 50000) / 100000, 0.0), 2.0)}
    if preset == "chevron":
        return "chevron", {"point": min(max(value("adj", 50000) / 100000, 0.0), 2.0)}
    if preset == "plus":
        return "plus", {"arm": min(max(value("adj", 25000) / 100000, 0.0), 0.5)}
    if preset in ("star4", "star5", "star6", "star7", "star8", "star10", "star12", "star16", "star24", "star32"):
        defaults = {"star4": 12500, "star5": 19098, "star6": 28868, "star7": 34601, "star8": 37500, "star10": 42533,
                    "star12": 37500, "star16": 37500, "star24": 37500, "star32": 37500}
        ratio = min(max(value("adj", defaults[preset]) / 50000, 0.05), 0.95)
        return "star", {"tips": int(preset[4:]), "ratio": round(ratio, 3)}
    if preset == "cloud":
        return "cloud", {}
    callouts = {"wedgeRectCallout": "rectangle", "wedgeRoundRectCallout": "rounded", "wedgeEllipseCallout": "oval"}
    if preset in callouts:
        x = value("adj1", -20833) / 100000 * w + w / 2
        y = value("adj2", 62500) / 100000 * h + h / 2
        settings: dict[str, object] = {"body": callouts[preset], "tail": (x, y)}
        if preset == "wedgeRoundRectCallout":
            settings["corner"] = value("adj3", 16667) / 100000 * ss
        return "bubble", settings
    return None


# -- outlines -----------------------------------------------------------------------------------


def _fmt(points: Iterable[Point], close: bool = True) -> str:
    coords = list(points)
    if not coords:
        return ""
    out = [f"M {coords[0][0]:.2f} {coords[0][1]:.2f}"]
    out.extend(f"L {x:.2f} {y:.2f}" for x, y in coords[1:])
    if close:
        out.append("Z")
    return " ".join(out)


def arc_path(cx: float, cy: float, rx: float, ry: float, start: float, sweep: float, move: bool = True) -> str:
    """An elliptical arc (angles in degrees, clockwise on the page) as cubic curves."""

    segments = max(1, math.ceil(abs(sweep) / 90.0))
    step = math.radians(sweep / segments)
    theta = math.radians(start)
    k = 4 / 3 * math.tan(step / 4)
    parts: list[str] = []
    if move:
        parts.append(f"M {cx + rx * math.cos(theta):.2f} {cy + ry * math.sin(theta):.2f}")
    for _ in range(segments):
        cos1, sin1 = math.cos(theta), math.sin(theta)
        theta2 = theta + step
        cos2, sin2 = math.cos(theta2), math.sin(theta2)
        c1 = (cx + rx * (cos1 - k * sin1), cy + ry * (sin1 + k * cos1))
        c2 = (cx + rx * (cos2 + k * sin2), cy + ry * (sin2 - k * cos2))
        end = (cx + rx * cos2, cy + ry * sin2)
        parts.append(f"C {c1[0]:.2f} {c1[1]:.2f} {c2[0]:.2f} {c2[1]:.2f} {end[0]:.2f} {end[1]:.2f}")
        theta = theta2
    return " ".join(parts)


def preset_path(preset: str, w: float, h: float, adjust: dict[str, float]) -> str | None:
    """A preset's outline in a ``w`` by ``h`` box, for those Flexo has no kind of; ``None`` for
    one not known here (drawn as its box)."""

    ss = max(min(w, h), 1e-6)

    def value(name: str, default: float) -> float:
        return adjust.get(name, default)

    if preset == "flowChartMerge":
        return _fmt([(0, 0), (w, 0), (w / 2, h)])
    if preset == "hexagon":
        d = value("adj", 25000) / 100000 * ss
        return _fmt([(d, 0), (w - d, 0), (w, h / 2), (w - d, h), (d, h), (0, h / 2)])
    if preset == "octagon":
        d = value("adj", 29289) / 100000 * ss
        return _fmt([(d, 0), (w - d, 0), (w, d), (w, h - d), (w - d, h), (d, h), (0, h - d), (0, d)])
    if preset in ("heptagon", "decagon", "dodecagon"):
        n = {"heptagon": 7, "decagon": 10, "dodecagon": 12}[preset]
        return _fmt([(w / 2 + w / 2 * math.cos(-math.pi / 2 + 2 * math.pi * k / n),
                      h / 2 + h / 2 * math.sin(-math.pi / 2 + 2 * math.pi * k / n)) for k in range(n)])
    if preset in ("homePlate", "flowChartOffpageConnector"):
        d = value("adj", 50000) / 100000 * ss
        return _fmt([(0, 0), (w - d, 0), (w, h / 2), (w - d, h), (0, h)])
    if preset == "upDownArrow":
        shaft = value("adj1", 50000) / 100000
        head = min(value("adj2", 50000) / 100000 * ss, h / 2)
        half = w * shaft / 2
        return _fmt([(w / 2, 0), (w, head), (w / 2 + half, head), (w / 2 + half, h - head), (w, h - head),
                     (w / 2, h), (0, h - head), (w / 2 - half, h - head), (w / 2 - half, head), (0, head)])
    if preset == "bentArrow":
        a2 = min(max(value("adj2", 25000), 0), 50000)
        a1 = min(max(value("adj1", 25000), 0), 2 * a2)
        a3 = min(max(value("adj3", 25000), 0), 50000)
        th = a1 / 100000 * ss
        aw2 = a2 / 100000 * ss
        dh2 = aw2 - th / 2
        ah = a3 / 100000 * ss
        a4 = min(max(value("adj4", 43750), 0), 100000 * min(w - ah, h - dh2) / ss)
        bd = a4 / 100000 * ss
        bd2 = max(bd - th, 0)
        x3, x4, y3 = th + bd2, w - ah, dh2 + th
        return (f"M 0 {h:.2f} L 0 {dh2 + bd:.2f} " + arc_path(bd, dh2 + bd, bd, bd, 180, 90, move=False)
                + f" L {x4:.2f} {dh2:.2f} L {x4:.2f} 0 L {w:.2f} {aw2:.2f} L {x4:.2f} {y3 + dh2:.2f}"
                + f" L {x4:.2f} {y3:.2f} L {x3:.2f} {y3:.2f} " + arc_path(x3, y3 + bd2, bd2, bd2, 270, -90, move=False)
                + f" L {th:.2f} {h:.2f} Z")
    if preset == "mathPlus":
        arm = value("adj", 23520) / 100000 * ss
        return _fmt([((w - arm) / 2, 0), ((w + arm) / 2, 0), ((w + arm) / 2, (h - arm) / 2), (w, (h - arm) / 2),
                     (w, (h + arm) / 2), ((w + arm) / 2, (h + arm) / 2), ((w + arm) / 2, h), ((w - arm) / 2, h),
                     ((w - arm) / 2, (h + arm) / 2), (0, (h + arm) / 2), (0, (h - arm) / 2),
                     ((w - arm) / 2, (h - arm) / 2)])
    if preset == "mathMinus":
        arm = value("adj", 23520) / 100000 * h
        return _fmt([(0, (h - arm) / 2), (w, (h - arm) / 2), (w, (h + arm) / 2), (0, (h + arm) / 2)])
    if preset == "mathEqual":
        arm = value("adj1", 23520) / 100000 * h
        gap = value("adj2", 11760) / 100000 * h
        top = (h - gap) / 2 - arm
        return (_fmt([(0, top), (w, top), (w, top + arm), (0, top + arm)]) + " "
                + _fmt([(0, h - top - arm), (w, h - top - arm), (w, h - top), (0, h - top)]))
    if preset == "mathMultiply":
        t = value("adj", 23520) / 100000 * ss / math.sqrt(2)
        return (_fmt([(0, t), (t, 0), (w, h - t), (w - t, h)]) + " " + _fmt([(w - t, 0), (w, t), (t, h), (0, h - t)]))
    if preset == "arc":
        start = value("adj1", 16200000) / 60000
        end = value("adj2", 0) / 60000
        return arc_path(w / 2, h / 2, w / 2, h / 2, start, (end - start) % 360)
    if preset == "blockArc":
        start = value("adj1", 10800000) / 60000
        end = value("adj2", 0) / 60000
        thickness = value("adj3", 25000) / 100000 * ss
        sweep = (end - start) % 360
        outer = arc_path(w / 2, h / 2, w / 2, h / 2, start, sweep)
        inner = arc_path(w / 2, h / 2, w / 2 - thickness, h / 2 - thickness, start + sweep, -sweep, move=False)
        angle = math.radians(start + sweep)
        x0 = w / 2 + (w / 2 - thickness) * math.cos(angle)
        y0 = h / 2 + (h / 2 - thickness) * math.sin(angle)
        return f"{outer} L {x0:.2f} {y0:.2f} {inner} Z"
    if preset == "donut":
        thickness = value("adj", 25000) / 100000 * ss
        outer = arc_path(w / 2, h / 2, w / 2, h / 2, 0, 359.99) + " Z"
        inner = arc_path(w / 2, h / 2, w / 2 - thickness, h / 2 - thickness, 0, -359.99) + " Z"
        return f"{outer} {inner}"
    if preset == "pie":
        start = value("adj1", 0) / 60000
        end = value("adj2", 16200000) / 60000
        arc = arc_path(w / 2, h / 2, w / 2, h / 2, start, (end - start) % 360)
        return f"M {w / 2:.2f} {h / 2:.2f} L " + arc[2:] + " Z"
    if preset == "heart":
        return (f"M {w / 2:.2f} {h:.2f} C {-0.1 * w:.2f} {0.55 * h:.2f} {0.05 * w:.2f} {-0.15 * h:.2f} "
                f"{w / 2:.2f} {0.25 * h:.2f} C {0.95 * w:.2f} {-0.15 * h:.2f} {1.1 * w:.2f} {0.55 * h:.2f} "
                f"{w / 2:.2f} {h:.2f} Z")
    if preset in ("leftBracket", "rightBracket", "bracketPair"):
        r = min(value("adj", 8333) / 100000 * ss, w / 2, h / 2)
        left = (f"M {w:.2f} 0 L {r:.2f} 0 " + arc_path(r, r, r, r, 270, -90, move=False)
                + f" L 0 {h - r:.2f} " + arc_path(r, h - r, r, r, 180, -90, move=False) + f" L {w:.2f} {h:.2f}")
        right = (f"M 0 0 L {w - r:.2f} 0 " + arc_path(w - r, r, r, r, 270, 90, move=False)
                 + f" L {w:.2f} {h - r:.2f} " + arc_path(w - r, h - r, r, r, 0, 90, move=False) + f" L 0 {h:.2f}")
        if preset == "leftBracket":
            return left
        if preset == "rightBracket":
            return right
        return (f"M {r:.2f} 0 " + arc_path(r, r, r, r, 270, -90, move=False) + f" L 0 {h - r:.2f} "
                + arc_path(r, h - r, r, r, 180, -90, move=False) + f" M {w - r:.2f} 0 "
                + arc_path(w - r, r, r, r, 270, 90, move=False) + f" L {w:.2f} {h - r:.2f} "
                + arc_path(w - r, h - r, r, r, 0, 90, move=False))
    if preset in ("leftBrace", "rightBrace"):
        r = min(value("adj1", 8333) / 100000 * ss, h / 4)
        if preset == "leftBrace":
            return (f"M {w:.2f} 0 " + arc_path(w, r, w / 2, r, 270, -90, move=False)
                    + f" L {w / 2:.2f} {h / 2 - r:.2f} " + arc_path(0, h / 2 - r, w / 2, r, 0, 90, move=False)
                    + " " + arc_path(0, h / 2 + r, w / 2, r, 270, 90, move=False)
                    + f" L {w / 2:.2f} {h - r:.2f} " + arc_path(w, h - r, w / 2, r, 180, -90, move=False))
        return ("M 0 0 " + arc_path(0, r, w / 2, r, 270, 90, move=False)
                + f" L {w / 2:.2f} {h / 2 - r:.2f} " + arc_path(w, h / 2 - r, w / 2, r, 180, -90, move=False)
                + " " + arc_path(w, h / 2 + r, w / 2, r, 270, -90, move=False)
                + f" L {w / 2:.2f} {h - r:.2f} " + arc_path(0, h - r, w / 2, r, 0, 90, move=False))
    if preset in ("borderCallout1", "borderCallout2", "accentCallout1", "callout1", "callout2", "cloudCallout"):
        if preset == "cloudCallout":
            return arc_path(w / 2, h / 2, w / 2, h / 2, 0, 359.99) + " Z"
        return _fmt([(0, 0), (w, 0), (w, h), (0, h)])
    if preset == "flowChartTerminator":
        r = h / 2
        return (f"M {r:.2f} 0 L {w - r:.2f} 0 " + arc_path(w - r, r, r, r, 270, 180, move=False)
                + f" L {r:.2f} {h:.2f} " + arc_path(r, r, r, r, 90, 180, move=False) + " Z")
    if preset == "flowChartDocument":
        return (f"M 0 0 L {w:.2f} 0 L {w:.2f} {0.8 * h:.2f} C {0.75 * w:.2f} {0.65 * h:.2f} "
                f"{0.25 * w:.2f} {1.1 * h:.2f} 0 {0.85 * h:.2f} Z")
    if preset == "cube":
        d = value("adj", 25000) / 100000 * ss
        return (_fmt([(0, d), (w - d, d), (w - d, h), (0, h)]) + " " + _fmt([(0, d), (d, 0), (w, 0), (w - d, d)])
                + " " + _fmt([(w - d, d), (w, 0), (w, h - d), (w - d, h)]))
    if preset == "can":
        d = value("adj", 25000) / 100000 * ss / 2
        body = (f"M 0 {d:.2f} L 0 {h - d:.2f} " + arc_path(w / 2, h - d, w / 2, d, 180, -180, move=False)
                + f" L {w:.2f} {d:.2f} " + arc_path(w / 2, d, w / 2, d, 0, -180, move=False) + " Z")
        return f"{body} {arc_path(w / 2, d, w / 2, d, 0, 359.99)} Z"
    if preset in ("snip1Rect", "snip2SameRect", "snip2DiagRect", "snipRoundRect"):
        d = value("adj1" if preset != "snip1Rect" else "adj", 16667) / 100000 * ss
        if preset == "snip1Rect":
            return _fmt([(0, 0), (w - d, 0), (w, d), (w, h), (0, h)])
        if preset == "snip2SameRect":
            return _fmt([(d, 0), (w - d, 0), (w, d), (w, h), (0, h), (0, d)])
        if preset == "snip2DiagRect":
            return _fmt([(d, 0), (w, 0), (w, h - d), (w - d, h), (0, h), (0, d)])
        return _fmt([(d, 0), (w - d, 0), (w, d), (w, h), (0, h), (0, d)])
    if preset in ("round1Rect", "round2SameRect", "round2DiagRect"):
        r = min(value("adj1" if preset != "round1Rect" else "adj", 16667) / 100000 * ss, w / 2, h / 2)
        corners = {"round1Rect": (False, True, False, False), "round2SameRect": (True, True, False, False),
                   "round2DiagRect": (True, False, True, False)}[preset]
        return _rounded(w, h, r, corners)
    if preset == "frame":
        d = value("adj1", 12500) / 100000 * ss
        return f"{_fmt([(0, 0), (w, 0), (w, h), (0, h)])} {_fmt([(d, d), (d, h - d), (w - d, h - d), (w - d, d)])}"
    if preset == "corner":
        d = value("adj1", 50000) / 100000 * ss
        return _fmt([(0, 0), (d, 0), (d, h - d), (w, h - d), (w, h), (0, h)])
    if preset == "lightningBolt":
        return _fmt([(0.4 * w, 0), (0.7 * w, 0.35 * h), (0.55 * w, 0.4 * h), (w, h), (0.35 * w, 0.55 * h),
                     (0.5 * w, 0.5 * h), (0, 0.2 * h)])
    if preset == "flowChartPreparation":
        d = 0.2 * w
        return _fmt([(d, 0), (w - d, 0), (w, h / 2), (w - d, h), (d, h), (0, h / 2)])
    if preset in ("flowChartInputOutput", "flowChartData"):
        d = 0.2 * w
        return _fmt([(d, 0), (w, 0), (w - d, h), (0, h)])
    if preset == "flowChartManualInput":
        return _fmt([(0, 0.2 * h), (w, 0), (w, h), (0, h)])
    if preset == "flowChartDelay":
        arc = arc_path(w / 2, h / 2, w / 2, h / 2, 270, 180, move=False)
        return f"M 0 0 L {w / 2:.2f} 0 " + arc + f" L 0 {h:.2f} Z"
    if preset in ("flowChartSummingJunction", "flowChartOr", "noSmoking", "ellipseRibbon"):
        return arc_path(w / 2, h / 2, w / 2, h / 2, 0, 359.99) + " Z"
    return None


def _rounded(w: float, h: float, r: float, corners: tuple[bool, bool, bool, bool]) -> str:
    """A box with some of its corners rounded: top left, top right, bottom right, bottom left."""

    tl, tr, br, bl = (r if on else 0.0 for on in corners)
    parts = [f"M {tl:.2f} 0", f"L {w - tr:.2f} 0"]
    if tr:
        parts.append(arc_path(w - tr, tr, tr, tr, 270, 90, move=False))
    parts.append(f"L {w:.2f} {h - br:.2f}")
    if br:
        parts.append(arc_path(w - br, h - br, br, br, 0, 90, move=False))
    parts.append(f"L {bl:.2f} {h:.2f}")
    if bl:
        parts.append(arc_path(bl, h - bl, bl, bl, 90, 90, move=False))
    parts.append(f"L 0 {tl:.2f}")
    if tl:
        parts.append(arc_path(tl, tl, tl, tl, 180, 90, move=False))
    parts.append("Z")
    return " ".join(parts)


def custom_path(custom: etree._Element, w: float, h: float) -> tuple[str, bool] | None:
    """A drawn outline (``a:custGeom``) in a ``w`` by ``h`` box, and whether any of its
    pieces is filled; arcs made cubic curves."""

    paths = list(custom.iterfind(f"{{{A}}}pathLst/{{{A}}}path"))
    if not paths:
        return None
    out: list[str] = []
    filled = False
    for path in paths:
        pw = float(path.get("w") or 0)
        ph = float(path.get("h") or 0)
        sx = w / pw if pw else 1.0
        sy = h / ph if ph else 1.0
        if path.get("fill") != "none":
            filled = True
        current: Point = (0.0, 0.0)
        start: Point = (0.0, 0.0)

        def point(element: etree._Element, sx: float = sx, sy: float = sy) -> Point:
            try:
                return float(element.get("x") or 0) * sx, float(element.get("y") or 0) * sy
            except ValueError:
                return 0.0, 0.0

        for command in path:
            if not isinstance(command.tag, str):
                continue
            name = etree.QName(command).localname
            points = [point(p) for p in command.iterfind(f"{{{A}}}pt")]
            if name == "moveTo" and points:
                current = start = points[0]
                out.append(f"M {current[0]:.2f} {current[1]:.2f}")
            elif name == "lnTo" and points:
                current = points[0]
                out.append(f"L {current[0]:.2f} {current[1]:.2f}")
            elif name == "cubicBezTo" and len(points) >= 3:
                out.append(" ".join(["C", *(f"{x:.2f} {y:.2f}" for x, y in points[:3])]))
                current = points[2]
            elif name == "quadBezTo" and len(points) >= 2:
                out.append(" ".join(["Q", *(f"{x:.2f} {y:.2f}" for x, y in points[:2])]))
                current = points[1]
            elif name == "arcTo":
                try:
                    rx = float(command.get("wR") or 0) * sx
                    ry = float(command.get("hR") or 0) * sy
                    begin = float(command.get("stAng") or 0) / 60000
                    sweep = float(command.get("swAng") or 0) / 60000
                except ValueError:
                    continue
                if rx <= 0 or ry <= 0 or sweep == 0:
                    continue
                theta = math.radians(begin)
                cx, cy = current[0] - rx * math.cos(theta), current[1] - ry * math.sin(theta)
                out.append(arc_path(cx, cy, rx, ry, begin, sweep, move=False))
                end = math.radians(begin + sweep)
                current = (cx + rx * math.cos(end), cy + ry * math.sin(end))
            elif name == "close":
                out.append("Z")
                current = start
    data = " ".join(out)
    return (data, filled) if data else None
