"""Typing over a slide's wrapped line follows its drawn lines in the Mac app: run in Node with
stand-ins for the page -- a drawn line's box where WebKit gives every line the whole text's
(drawnlines.js) -- and the editor's use of it."""

from __future__ import annotations

import json
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


def test_a_drawn_line_is_its_first_letter_s_cell_where_webkit_gives_it_the_whole_text_s_box() -> None:
    found = run(
        "drawnlines.js",
        """
      // Lines 36 units apart at 0.75 a unit: WebKit as the Mac app has it gives both lines the
      // text's whole box, 54 px tall; its letters' cells say where each line is.
      const ctm = { a: 0.75, b: 0, c: 0, d: 0.75, e: 200, f: 100 };
      const span = (cellTop, own) => ({ getBoundingClientRect: () => own, getNumberOfChars: () => 10,
        getExtentOfChar: () => ({ x: 48, y: cellTop, width: 20, height: 36 }), getScreenCTM: () => ctm });
      const whole = box(136, 54, 236, 400);
      const mac = [span(48, whole), span(84, whole)].map(M.lineBox);
      // Elsewhere each line's own box, taken as it is.
      const own = [span(48, box(136, 27, 236, 400)), span(84, box(163, 27, 236, 300))].map(M.lineBox);
      const empty = M.lineBox({ getBoundingClientRect: () => box(0, 0), getNumberOfChars: () => 0 });
      return { mac: mac.map((b) => [b.top, b.height, b.left, b.width]), own: own.map((b) => [b.top, b.height, b.width]),
               empty: empty.height };
    """,
    )
    assert found == {
        "mac": [[136, 27, 236, 400], [163, 27, 236, 400]],
        "own": [[136, 27, 400], [163, 27, 300]],
        "empty": 0,
    }


def test_the_editor_reads_a_slide_s_drawn_lines_as_drawnlines_js_has_them() -> None:
    editor = (STATIC / "editor.js").read_text("utf-8")
    # Typing over a slide's lines: where each line is, and the first line's height.
    assert ".map(lineBox).filter((box) => box.width)" in editor
    assert "const first = firstSpan ? lineBox(firstSpan) : texts[0].getBoundingClientRect();" in editor
    # A line typed under another keeps clear of the letters over it, read the same way.
    assert "const box = line === text ? line.getBoundingClientRect() : lineBox(line)" in editor
