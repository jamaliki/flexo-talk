"""Going from slide to slide draws only what changed, as soon as it can: run in Node with
stand-ins for the page -- the slide list's thumbnail brought into view (railview.js), the panel
drawn a frame after a slide gone to by ↓, ↑ or its thumbnail (panelsoon.js) -- and the editor's
use of them, and its frame's grid never sized to what is in it."""

from __future__ import annotations

import json
import re
import shutil
import subprocess
from pathlib import Path

import pytest

STATIC = Path(__file__).parents[1] / "src" / "flexo_talk" / "studio" / "static"

PAGE = """
let clock = 0, frames = [], timers = [];
globalThis.requestAnimationFrame = (fn) => { frames.push(fn); return frames.length; };
globalThis.cancelAnimationFrame = (id) => { frames[id - 1] = null; };
globalThis.setTimeout = (fn, ms = 0) => { timers.push({ fn, at: clock + ms }); return timers.length; };
globalThis.clearTimeout = (id) => { if (id) timers[id - 1] = null; };
const frame = () => { const now = frames; frames = []; now.forEach((fn) => fn && fn()); };
const pass = (ms) => {
  clock += ms;
  timers.forEach((t, k) => { if (t && t.at <= clock) { timers[k] = null; t.fn(); } });
};
const box = (top, height, left = 0, width = 100) =>
  ({ top, bottom: top + height, height, left, right: left + width, width, x: left, y: top });
"""


def run(module: str, body: str) -> object:
    node = shutil.which("node")
    if node is None:
        pytest.skip("Node is not installed")
    script = (
        PAGE
        + f"const M = await import({json.dumps((STATIC / module).as_uri())});\n"
        + f"console.log(JSON.stringify(await (async () => {{ {body} }})()));\n"
    )
    result = subprocess.run([node, "--input-type=module", "-e", script], capture_output=True, text=True, check=True)
    return json.loads(result.stdout.strip().splitlines()[-1])


def test_a_thumbnail_near_an_edge_of_the_list_is_scrolled_whole_into_view() -> None:
    found = run(
        "railview.js",
        """
      const list = { getBoundingClientRect: () => box(100, 400) };
      const item = (top) => ({ asked: [], getBoundingClientRect: () => box(top, 80),
        scrollIntoView(o) { this.asked.push(o.block); } });
      const below = item(430), above = item(95), inside = item(200), edge = item(415);
      return [below, above, inside, edge].map((each) => [M.intoView(list, each), each.asked]);
    """,
    )
    assert found == [[True, ["end"]], [True, ["start"]], [False, []], [True, ["end"]]]


def test_the_editor_brings_the_thumbnail_into_view_before_the_slide_is_drawn_anew() -> None:
    editor = (STATIC / "editor.js").read_text("utf-8")
    select = editor[editor.index("  function select(index, focus = null") :]
    select = select[: select.index("\n  }\n")]
    # Measured and scrolled before the slide, list and panel are drawn anew; later only for a
    # thumbnail new or made anew.
    assert select.index("if (early) intoView(railList, early);") < select.index("renderRail();")
    assert "if (thumbLater) requestAnimationFrame(thumbInView);" in select
    # The empty date's example made with one formatter, not a new one for each slide gone to.
    assert "toLocaleDateString" not in editor
    assert "dayFormatter ||= new Intl.DateTimeFormat(" in editor


def test_the_panel_is_drawn_once_after_the_frame_and_at_once_when_flushed() -> None:
    found = run(
        "panelsoon.js",
        """
      let drawn = 0;
      const panel = M.afterFrame(() => { drawn += 1; });
      panel.soon(0);
      const before = drawn;
      frame(); pass(0);
      const after = drawn;
      // Held: asked again and again, it waits for the keys to stop, and is drawn once.
      panel.soon(150); frame(); pass(30); panel.soon(150); frame(); pass(30); panel.soon(150); frame(); pass(100);
      const waiting = [drawn, panel.pending()];
      pass(60);
      const held = drawn;
      // Something else pressed meanwhile: drawn at once, and not again.
      panel.soon(0); panel.flush(); frame(); pass(0);
      const flushed = drawn;
      // Drawn by other means meanwhile: not again.
      panel.soon(0); panel.cancel(); frame(); pass(0);
      return { before, after, waiting, held, flushed, cancelled: drawn, idle: panel.pending() };
    """,
    )
    assert found == {
        "before": 0,
        "after": 1,
        "waiting": [1, True],
        "held": 2,
        "flushed": 3,
        "cancelled": 3,
        "idle": False,
    }


def test_a_slide_gone_to_by_an_arrow_key_has_its_panel_drawn_after_it() -> None:
    editor = (STATIC / "editor.js").read_text("utf-8")
    select = editor[editor.index("  function select(index, focus = null") :]
    select = select[: select.index("\n  }\n")]
    # ↓ or ↑: the panel a frame after the slide; held (or pressed again at once), once the keys stop.
    assert 'if (panel === "now") renderInspector();' in select
    assert 'panelAfterSlide.soon(panel === "held" ? 150 : 0);' in select
    assert 'select(index, null, { panel: quick ? "held" : "after" });' in editor
    assert 'select(to, null, held ? { panel: "held" } : {});' in editor
    # A click on a thumbnail (not ⇧ or ⌘ with it): the panel a frame after the slide too.
    assert '} else { select(index, null, { panel: "after" }); return; }' in editor
    # Anything else pressed or clicked finds the panel drawn; drawn by other means, not again.
    assert "panelAfterSlide.flush();" in editor
    render = editor[editor.index("  function renderInspector() {") :]
    assert "    panelAfterSlide.cancel();" in render.split("\n", 3)[2]


def test_the_deck_editor_s_frame_is_never_sized_to_what_is_in_it() -> None:
    css = (STATIC / "editor.css").read_text("utf-8")
    rule = lambda selector: re.search(rf"(?m)^\s*{re.escape(selector)} {{([^}}]*)}}", css).group(1)  # noqa: E731
    deck = rule(".deck")
    assert "grid-template-columns: 184px minmax(0, 1fr) var(--inspector, 340px);" in deck
    assert "grid-template-rows: minmax(0, 1fr);" in deck
    # No 1fr track of the frame left to measure its contents for its least size.
    for selector in (
        ".deck.wide",
        ".deck.no-inspector, .deck.wide.no-inspector",
        ".thumb",
        ".deck-center",
        "body.side-open .deck",
    ):
        assert re.search(r"(?<!\(0, )\b1fr\b", rule(selector)) is None, selector
    # The slide list a block, its thumbnails 10 px apart, not a grid's rows.
    assert "display: block;" in rule(".rail-list") and "gap:" not in rule(".rail-list")
    assert rule(".rail-list > .thumb + .thumb").strip() == "margin-top: 10px;"
    assert rule(".deck-stage:not(.zoomed)").strip() == "grid-template-columns: minmax(0, 1fr);"
