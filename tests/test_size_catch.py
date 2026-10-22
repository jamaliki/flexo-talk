"""An object sized in line by the deck editor's own handles -- a picture by a corner, a gallery,
words by a side -- catches where an edge that moves as it grows comes near a guide, as a placed
object's and a shape's do (``studio/static/sizecatch.js``): the size found that puts the edge on
the guide where its place stands it, not the pointer moved -- run in Node."""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import flexo
import pytest

SIZECATCH = Path(__file__).parents[1] / "src/flexo_talk/studio/static/sizecatch.js"
SNAPPING = Path(flexo.__file__).parent / "studio/static/studio/snapping.js"


def _node(code: str) -> object:
    node = shutil.which("node")
    if node is None:
        pytest.skip("Node is not installed")
    # (The guides caught at as the studio catches at them: snapping.js's nearest, 6 within reach.)
    script = (
        f"const {{ sizeCaught }} = await import({json.dumps(SIZECATCH.as_uri())});\n"
        f"const S = await import({json.dumps(SNAPPING.as_uri())});\n"
        "const at = (xs, ys = []) => (axis, values) => S.nearest(values, axis === 'x' ? xs : ys, 6);\n"
        "const round = (hit) => hit && { ...hit, size: Math.round(hit.size * 1e6) / 1e6 };\n"
        f"{code}"
    )
    done = subprocess.run([node, "--input-type=module", "-e", script], capture_output=True, text=True, check=True)
    return json.loads(done.stdout)


def test_the_edge_a_picture_moves_as_it_grows_is_caught_at_a_guide_near_it() -> None:
    made = _node("""
      // A picture standing at the left of its place, 200 by 150, grown from its top left.
      const left = (scale) => ({ left: 48, top: 169, width: 200 * scale, height: 150 * scale });
      // A gallery standing centred: both its edges move.
      const centred = (width) => ({ left: 480 - width / 2, top: 200, width, height: width / 2 });
      console.log(JSON.stringify({
        right: round(sizeCaught(left, 285 / 200, at([330]))),
        down: round(sizeCaught(left, 1.2, at([], [350]))),
        nearer: round(sizeCaught(left, 285 / 200, at([330, 335]))),
        far: sizeCaught(left, 1.2, at([330])),
        still: sizeCaught(left, 1.2, at([48, 50])),
        centred: round(sizeCaught(centred, 446, at([700]))),
        other: round(sizeCaught(centred, 446, at([258]))),
      }));
    """)
    # Its right edge 3 points from the guide: the size that puts it there, the guide said.
    assert made["right"] == {"size": 1.41, "gap": -3, "axis": "x", "at": 330}
    # Its bottom edge, down.
    assert made["down"] == {"size": round(181 / 150, 6), "gap": 1, "axis": "y", "at": 350}
    # The nearer of two guides.
    assert made["nearer"]["at"] == 335
    # None within reach; none caught at the edge that stays where it is, however near a guide.
    assert made["far"] is None
    assert made["still"] is None
    # Standing centred, either edge: the size that puts it there is twice as far from the middle.
    assert made["centred"] == {"size": 440, "gap": -3, "axis": "x", "at": 700}
    assert made["other"] == {"size": 444, "gap": 1, "axis": "x", "at": 258}


def test_an_edge_is_caught_past_where_its_place_stops_it_and_never_past_the_size_it_may_be() -> None:
    made = _node("""
      // Standing at 100, it grows rightwards until it meets its place's right edge (400); then
      // leftwards, against it.
      const against = (width) => ({ left: Math.min(100, 400 - width), top: 0, width, height: 10 });
      console.log(JSON.stringify({
        before: round(sizeCaught(against, 290, at([395]))),
        after: round(sizeCaught(against, 345, at([50]))),
        still: sizeCaught(against, 290, at([102])),
        most: sizeCaught(against, 345, at([50]), { most: 348 }),
        least: sizeCaught(against, 345, at([50]), { least: 0, most: 400 }),
      }));
    """)
    # Its right edge, moving; its left, not -- until it is against the place's edge.
    assert made["before"] == {"size": 295, "gap": 5, "axis": "x", "at": 395}
    assert made["still"] is None
    assert made["after"] == {"size": 350, "gap": -5, "axis": "x", "at": 50}
    # No larger than it may be: a guide only a larger size would reach is not caught at.
    assert made["most"] is None
    assert made["least"]["size"] == 350
