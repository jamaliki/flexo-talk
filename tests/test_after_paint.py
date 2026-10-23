"""What a click chooses on a slide is painted chosen before the inspector's panel for it is drawn
(afterpaint.js, run in Node with frames and timers the test runs by hand), and the deck editor
leaves the panel, and a figure's part's +, to it as a click, an undo or a redo chooses."""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import pytest

STATIC = Path(__file__).parents[1] / "src" / "flexo_talk" / "studio" / "static"

# Frames and timers that run when the test says: `frame()` runs the frame callbacks asked for
# so far, `tick(ms)` the timers due by then.
CLOCK = """
let now = 0, frames = [], timers = [], nextId = 1;
globalThis.requestAnimationFrame = (fn) => { frames.push(fn); return frames.length; };
globalThis.setTimeout = (fn, ms = 0) => { const id = nextId++; timers.push({ id, fn, at: now + ms }); return id; };
globalThis.clearTimeout = (id) => { timers = timers.filter((timer) => timer.id !== id); };
const frame = () => { const due = frames; frames = []; due.forEach((fn) => fn()); };
const tick = (ms = 0) => {
  now += ms;
  for (;;) {
    const due = timers.filter((timer) => timer.at <= now).sort((a, b) => a.at - b.at || a.id - b.id)[0];
    if (!due) break;
    timers = timers.filter((timer) => timer !== due);
    due.fn();
  }
};
"""


def run(body: str) -> object:
    node = shutil.which("node")
    if node is None:
        pytest.skip("Node is not installed")
    script = (
        CLOCK
        + f"const A = await import({json.dumps((STATIC / 'afterpaint.js').as_uri())});\n"
        + f"console.log(JSON.stringify(await (async () => {{ {body} }})()));\n"
    )
    result = subprocess.run([node, "--input-type=module", "-e", script], capture_output=True, text=True, check=True)
    return json.loads(result.stdout.strip().splitlines()[-1])


def test_what_is_owed_is_done_once_after_the_frame_that_shows_the_choice() -> None:
    found = run("""
      let runs = 0;
      const panel = A.owing(() => { runs += 1; });
      panel.soon(); panel.soon();
      const asked = [runs, panel.owed];
      tick(); frame();
      const firstFrame = runs;
      frame(); tick();
      const after = [runs, panel.owed];
      tick(500); frame(); frame(); tick();
      return { asked, firstFrame, after, never: runs };
    """)
    # Asked twice, done once: not in the frame that shows the choice, but once it is painted.
    assert found == {"asked": [0, True], "firstFrame": 0, "after": [1, False], "never": 1}


def test_what_is_owed_is_done_at_once_when_wanted_dropped_when_done_and_done_without_frames() -> None:
    found = run("""
      let runs = 0;
      const panel = A.owing(() => { runs += 1; });
      // A key pressed before it is done: done then, and not again.
      panel.soon(); panel.now();
      const wanted = runs;
      frame(); frame(); tick(500);
      const once = runs;
      // Done meanwhile by other means: not done again.
      panel.soon(); panel.drop();
      frame(); frame(); tick(500);
      const dropped = runs;
      // A window that draws no frames: done all the same, a little later.
      panel.soon(); tick(100);
      const early = runs;
      tick(100);
      return { wanted, once, dropped, early, late: runs };
    """)
    assert found == {"wanted": 1, "once": 1, "dropped": 1, "early": 1, "late": 2}


EDITOR = (STATIC / "editor.js").read_text(encoding="utf-8")


def body_of(name: str) -> str:
    start = EDITOR.index(f"  function {name}(")
    end = EDITOR.index("\n  }\n", start)
    return EDITOR[start:end]


def test_a_click_on_the_slide_paints_its_choice_before_the_panel_is_drawn() -> None:
    # The slide's click listener says a click is choosing while it runs.
    listener = 'pageNode.addEventListener("click", (event) => { choosing = true; try { onPick(event); }'
    assert listener + " finally { choosing = false; } });" in EDITOR
    # An object chosen by it: its frame placed now, its panel owed.
    focus = body_of("focusBlock")
    assert "if (choosing) panelSoon.soon();" in focus
    assert focus.index("panelSoon.soon()") < focus.index("placeChosen();")
    # A figure's part chosen by it: marked at once (its + owed should it take a while), the panel owed.
    assert "placeFigure({ quick: choosing }); if (choosing) panelSoon.soon(); else renderInspector();" in EDITOR
    place = body_of("placeFigure")
    assert "figure.parts.markViews({ quick })" in place and "if (views.later) plusSoon.soon();" in place
    # Drawn meanwhile, the panel is not drawn again; a key reaches both drawn.
    assert body_of("renderInspector").splitlines()[1].strip() == "panelSoon.drop();"
    assert place.splitlines()[1].strip() == "plusSoon.drop();"
    assert 'document.addEventListener("keydown", () => { plusSoon.now(); panelSoon.now(); }, true);' in EDITOR


def test_an_undo_or_a_redo_paints_what_it_brings_back_before_the_panel_is_drawn() -> None:
    assert 'choosing = source === "history";' in EDITOR
    drawn = "if (!quiet) { renderRail(); if (choosing) panelSoon.soon(); else renderInspector(); renderStage();"
    assert drawn + " renderBar(); }" in EDITOR
