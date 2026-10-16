"""Match on Other Slides (``studio/static/matching.js``): the same object found on another slide
as a person would find it -- a picture by its file, a figure by its name, file or id, a shape by
its id or its place, else what is in its place -- the run it is in, the slides said, a new frame
named; and an object or a shape put just where the one chosen is -- run in Node."""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import pytest

MATCHING = Path(__file__).parents[1] / "src/flexo_talk/studio/static/matching.js"


def _node(code: str) -> object:
    node = shutil.which("node")
    if node is None:
        pytest.skip("Node is not installed")
    places = MATCHING.with_name("places.js")
    # (matching.js imports places.js beside it, as the page does.)
    script = (
        f"const M = await import({json.dumps(MATCHING.as_uri())});\n"
        f"const P = await import({json.dumps(places.as_uri())});\n"
        "const regions = (slide) => (slide.layout === 'two-columns' ? ['left', 'right'] : ['body']);\n"
        "const blocksAt = (slide, key) => slide[key] || [];\n"
        f"{code}"
    )
    done = subprocess.run(["node", "--input-type=module", "-e", script], capture_output=True, text=True, check=True)
    return json.loads(done.stdout)


def test_the_same_object_is_found_on_another_slide_as_a_person_would_find_it() -> None:
    made = _node("""
      const options = { regions, blocksAt, figures: { smc: { figure: { id: "smc" } } } };
      const here = { region: "right", index: 0 };
      const two = (right, left = [{ text: "Words" }]) => ({ layout: "two-columns", left, right });
      const found = {
        // The same picture, wherever it is on the slide.
        picture: M.matchObject({ image: "a.svg" }, here, two([{ text: "x" }, { image: "a.svg" }]), options),
        // Another picture in its place.
        place: M.matchObject({ image: "a.svg" }, here, two([{ image: "b.svg" }]), options),
        // The same figure: by the deck's name, by file, by id.
        named: M.matchObject({ figure: "#smc" }, here, two([{ image: "x.png" }], [{ figure: "#smc" }]), options),
        file: M.matchObject({ figure: "f/a.yaml" }, here, two([{ text: "x" }, { figure: "f/a.yaml" }]), options),
        id: M.matchObject({ figure: { figure: { id: "smc" } } }, here,
          two([{ text: "x" }], [{ figure: "#smc" }]), options),
        // Words for words in their place; a picture for words, not.
        words: M.matchObject({ text: "A" }, { region: "left", index: 0 }, two([], [{ bullets: ["B"] }]), options),
        none: M.matchObject({ image: "a.svg" }, here, two([{ text: "x" }]), options),
        empty: M.matchObject({ image: "a.svg" }, here, { layout: "content", body: [] }, options),
        // Shapes: by id, else the same kind in the same place.
        shape: M.matchShape({ id: "ring", kind: "ring" }, 0, [{ kind: "line" }, { id: "ring", kind: "ellipse" }]),
        missing: M.matchShape({ id: "ring", kind: "ring" }, 0, [{ kind: "ring" }]),
        placed: M.matchShape({ kind: "arrow" }, 1, [{ kind: "ring" }, { kind: "arrow" }]),
        other: M.matchShape({ kind: "arrow" }, 0, [{ kind: "ring" }]),
      };
      console.log(JSON.stringify(found));
    """)
    assert made["picture"] == {"region": "right", "index": 1}
    assert made["place"] == {"region": "right", "index": 0}
    assert made["named"] == {"region": "left", "index": 0}
    assert made["file"] == {"region": "right", "index": 1}
    assert made["id"] == {"region": "left", "index": 0}
    assert made["words"] == {"region": "left", "index": 0}
    assert "why" in made["none"] and "why" in made["empty"]
    assert made["shape"] == {"index": 1}
    assert made["missing"]["why"] == "no shape “ring”"
    assert made["placed"] == {"index": 1}
    assert "why" in made["other"]


def test_a_run_is_the_slides_either_side_that_each_have_a_match() -> None:
    made = _node("""
      const has = (index) => [false, true, true, true, false, true].at(index);
      console.log(JSON.stringify({ run: M.runOf(6, 2, has), edge: M.runOf(6, 5, has),
        said: [M.slidesSaid([3, 1, 2]), M.slidesSaid([0]), M.slidesSaid([1, 4, 8]), M.slidesSaid([])],
        names: [M.frameName({ figure: "#smc" }, {}, []), M.frameName({ figure: "figures/step-1.yaml" }, {}, ["step-1"]),
                M.frameName({ figure: { figure: { id: "pipeline" } } }, {}, ["pipeline", "pipeline-2"])] }));
    """)
    assert made["run"] == [1, 3]
    assert made["edge"] == [5, 5]
    assert made["said"] == ["Slides 2\u20134", "Slide 1", "Slides 2, 5 and 9", "no slides"]
    assert made["names"] == ["smc", "step-1-2", "pipeline-3"]


def test_an_object_or_a_shape_is_put_where_the_one_chosen_is() -> None:
    made = _node("""
      const family = (kind) => (["line", "arrow"].includes(kind) ? "line" : kind === "polyline" ? "points"
        : kind === "text" ? "text" : "box");
      const bounds = (spec) => {
        const xs = spec.points.map((p) => p[0]), ys = spec.points.map((p) => p[1]);
        return [Math.min(...xs), Math.min(...ys), Math.max(...xs), Math.max(...ys)];
      };
      const mapped = (spec, map) => ({ ...spec, points: spec.points.map(map) });
      const helpers = { bounds, mapped, family };
      const frame = [9, 19, 301, 200];
      console.log(JSON.stringify({
        picture: M.placedAs({ image: "b.svg", width: 120 }, [498, 127.004, 414.0049, 349], "image"),
        figure: M.placedAs({ figure: "#smc" }, [498, 127, 414, 300], "figure", { name: "smc" }),
        standing: [M.standing({ image: "a.svg", at: [10, 20], width: 300 }, frame),
          M.standing({ image: "a.svg" }, frame)],
        box: M.shapeAs({ kind: "ellipse", at: [0, 0], size: [5, 5], fill: "accent" },
          { kind: "rectangle", at: [10, 20], size: [30, 40], rotate: 15 }, helpers),
        line: M.shapeAs({ kind: "arrow", from: [0, 0], to: [1, 1] },
          { kind: "line", from: [5, 6], to: [7, 8] }, helpers),
        points: M.shapeAs({ kind: "polyline", points: [[0, 0], [10, 5], [20, 10]] },
          { kind: "polyline", points: [[100, 100], [140, 120]] }, helpers),
      }));
    """)
    # Just where it stands, as wide, to a ten-thousandth of a point: not a hair apart.
    assert made["picture"] == {"image": "b.svg", "width": 414.0049, "at": [498, 127.004]}
    assert made["figure"] == {"figure": "#smc", "at": [498, 127], "width": 414, "frame": "smc"}
    assert made["standing"] == [[10, 20, 300, 200], [9, 19, 301, 200]]
    # A box: its place, size and turn, its own look kept.
    assert made["box"] == {"kind": "ellipse", "at": [10, 20], "size": [30, 40], "fill": "accent", "rotate": 15}
    assert made["line"] == {"kind": "arrow", "from": [5, 6], "to": [7, 8]}
    assert made["points"]["points"] == [[100, 100], [120, 110], [140, 120]]
