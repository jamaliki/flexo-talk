"""Overlaying slides (``studio/static/overlaying.js``): which slides are drawn over the one shown
-- those chosen in the list, else the presented ones either side -- where Page Up and Page Down
go among them, the tint each ghost is drawn in, and the setting kept for the person, carried
over from Show Neighbouring Slides -- run in Node, with this browser's storage stood in for."""

from __future__ import annotations

import itertools
import json
import shutil
import subprocess
from pathlib import Path

import pytest

OVERLAYING = Path(__file__).parents[1] / "src/flexo_talk/studio/static/overlaying.js"


def _node(code: str, kept: dict[str, str] | None = None) -> object:
    node = shutil.which("node")
    if node is None:
        pytest.skip("Node is not installed")
    script = (
        f"const kept = new Map(Object.entries({json.dumps(kept or {})}));\n"
        "const storage = { getItem: (key) => (kept.has(key) ? kept.get(key) : null),\n"
        "  setItem: (key, value) => { kept.set(key, String(value)); },\n"
        "  removeItem: (key) => { kept.delete(key); } };\n"
        f"const O = await import({json.dumps(OVERLAYING.as_uri())});\n"
        f"{code}"
    )
    done = subprocess.run([node, "--input-type=module", "-e", script], capture_output=True, text=True, check=True)
    return json.loads(done.stdout)


def test_the_slides_overlaid_are_those_chosen_else_the_presented_ones_either_side() -> None:
    made = _node("""
      const deck = [{}, {}, { skip: true }, {}, {}, { skip: true }];
      console.log(JSON.stringify({
        // One chosen: the presented slides either side, a skipped one passed over.
        middle: O.overlaidOf(deck, 3),
        first: O.overlaidOf(deck, 0),
        last: O.overlaidOf(deck, 5),
        // Shown, a skipped slide is overlaid with those either side all the same.
        skipped: O.overlaidOf(deck, 2),
        // Chosen: those, in order, once each -- the slide shown among them.
        chosen: O.overlaidOf(deck, 3, [4, 1, 3, 4]),
        // Gone to a slide out of them: none (the overlay stops).
        left: O.overlaidOf(deck, 0, [1, 3, 4]),
        // A set with fewer than two slides left on the deck is no set.
        shrunk: O.overlaidOf(deck, 1, [1, 9]),
        set: [O.setOf([5, 2, 2], 6), O.setOf([2], 6), O.setOf([], 6), O.setOf(null, 6)],
      }));
    """)
    assert made == {
        "middle": [1, 3, 4],
        "first": [0, 1],
        "last": [4, 5],
        "skipped": [1, 2, 3],
        "chosen": [1, 3, 4],
        "left": None,
        "shrunk": None,
        "set": [[2, 5], None, None, None],
    }


def test_page_up_and_page_down_go_among_the_slides_overlaid() -> None:
    made = _node("""
      const set = [27, 28, 29, 30];
      console.log(JSON.stringify({
        down: O.stepAmong(set, 29, 1), up: O.stepAmong(set, 29, -1),
        // At either end, nowhere: the slide shown stays.
        end: O.stepAmong(set, 30, 1), start: O.stepAmong(set, 27, -1),
        // Far apart in the deck, the next of them all the same.
        apart: O.stepAmong([3, 11, 20], 3, 1),
      }));
    """)
    assert made == {"down": 30, "up": 28, "end": None, "start": None, "apart": 11}


def test_four_ghosts_or_fewer_are_blue_before_and_red_after_fainter_further_away() -> None:
    made = _node("""
      const tints = O.tintsOf([27, 28, 29, 30], 29);
      const one = (index) => tints.get(index);
      console.log(JSON.stringify({
        shown: tints.has(29), count: tints.size,
        sides: [27, 28, 30].map((index) => [one(index).side, one(index).away, one(index).colour]),
        fading: one(28).opacity > one(27).opacity, near: one(28).opacity === one(30).opacity,
        // Each its lighter tint, for a dark slide.
        light: one(30).light,
        // Four on one side: each fainter than the one nearer.
        far: [5, 6, 7, 8].map((index) => O.tintsOf([4, 5, 6, 7, 8], 4).get(index).opacity),
        before: O.BEFORE, after: O.AFTER,
      }));
    """)
    assert made["shown"] is False and made["count"] == 3
    assert made["sides"] == [
        ["before", 2, "#2f63d6"],
        ["before", 1, "#2f63d6"],
        ["after", 1, "#d8452b"],
    ]
    assert made["fading"] and made["near"]
    assert made["light"] == made["after"][1]
    far = made["far"]
    assert all(a > b for a, b in itertools.pairwise(far)) and far[0] <= 0.6
    assert far[-1] >= 0.1


def test_more_than_four_ghosts_have_a_hue_each_kept_as_the_slides_are_gone_through() -> None:
    made = _node("""
      const set = [10, 11, 12, 13, 14, 15];
      const at = (here) => Object.fromEntries([...O.tintsOf(set, here)].map(([index, tint]) => [index, tint.colour]));
      const tints = O.tintsOf(set, 12);
      console.log(JSON.stringify({ at12: at(12), at13: at(13),
        opacity: [...new Set([...tints.values()].map((tint) => tint.opacity))],
        sides: [...tints].map(([index, tint]) => [index, tint.side]) }));
    """)
    hues = list(made["at12"].values())
    assert len(set(hues)) == 5
    # The slides keep their hues as another of them is shown.
    assert all(made["at13"][index] == hue for index, hue in made["at12"].items() if index != "13")
    assert len(made["opacity"]) == 1 and made["opacity"][0] < 0.5
    assert made["sides"][:2] == [[10, "before"], [11, "before"]]


def test_a_dark_slide_is_told_by_its_colour() -> None:
    made = _node("""
      console.log(JSON.stringify(["#101418", "#ffffff", "rgb(20, 24, 40)", "rgb(250, 250, 250)", ""]
        .map((colour) => O.isDark(colour))));
    """)
    assert made == [True, False, True, False, False]


def test_the_setting_is_kept_and_carried_over_from_show_neighbouring_slides() -> None:
    made = _node(
        """
      const was = O.keptOverlay(storage);
      const moved = [kept.get("flexo-studio-overlay"), kept.has("flexo-studio-neighbours")];
      O.keepOverlay("off", storage);
      console.log(JSON.stringify({ was, moved, now: O.keptOverlay(storage) }));
    """,
        {"flexo-studio-neighbours": "both"},
    )
    assert made == {"was": "on", "moved": ["on", False], "now": "off"}
    # Only the slide before shown: on too; hidden, or never set: off.
    for old, want in (("before", "on"), ("off", "off")):
        assert (
            _node(
                "console.log(JSON.stringify(O.keptOverlay(storage)));",
                {"flexo-studio-neighbours": old},
            )
            == want
        )
    assert _node("console.log(JSON.stringify(O.keptOverlay(storage)));") == "off"
    # Storage that can't be read: off.
    assert _node("console.log(JSON.stringify(O.keptOverlay({ getItem() { throw 1; } })));") == "off"
