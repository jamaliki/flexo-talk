"""Going from slide to slide stays quick on a large deck: the slides beside the one shown are
read ahead while the window is left alone (stageahead.js), the window is laid out once a slide
is gone to, as its frame is drawn, and the slide list's pictures are layers of their own."""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import pytest

STATIC = Path(__file__).parents[1] / "src" / "flexo_talk" / "studio" / "static"

PAGE = """
const listeners = {};
globalThis.document = { addEventListener: (type, fn) => { (listeners[type] ||= []).push(fn); } };
const fire = (type) => (listeners[type] || []).forEach((fn) => fn({ type }));
const wait = (ms) => new Promise((done) => setTimeout(done, ms));
"""


def run(body: str) -> object:
    node = shutil.which("node")
    if node is None:
        pytest.skip("Node is not installed")
    script = (
        PAGE
        + f"const A = await import({json.dumps((STATIC / 'stageahead.js').as_uri())});\n"
        + f"console.log(JSON.stringify(await (async () => {{ {body} }})()));\n"
    )
    result = subprocess.run([node, "--input-type=module", "-e", script], capture_output=True, text=True, check=True)
    return json.loads(result.stdout.strip().splitlines()[-1])


def test_the_slides_beside_the_one_shown_are_read_once_the_window_is_left_alone() -> None:
    found = run("""
      const read = [];
      const ahead = A.stageAhead((text) => { read.push(text); return { text }; }, { quiet: 40 });
      ahead.want([["4:a", "four"], ["2:b", "two"]]);
      const at_once = read.length;
      await wait(250);
      const left_alone = [...read];
      const taken = [ahead.take("4:a"), ahead.take("4:a")];
      // A key pressed, others beside: nothing read while the keys come, those not beside let go.
      fire("keydown");
      ahead.want([["5:c", "five"], ["3:d", "three"], ["4:e", "four again"]]);
      const gone = ahead.take("2:b");
      await wait(10);
      const while_keyed = read.length;
      await wait(300);
      return { at_once, left_alone, taken, gone, while_keyed, then: read.slice(2), last: ahead.take("4:e") };
    """)
    assert found == {
        "at_once": 0,
        "left_alone": ["four", "two"],
        "taken": [{"text": "four"}, None],
        "gone": None,
        "while_keyed": 2,
        "then": ["five", "three", "four again"],
        "last": {"text": "four again"},
    }


def test_a_slide_gone_to_is_laid_out_once_and_put_in_as_read_ahead() -> None:
    editor = (STATIC / "editor.js").read_text("utf-8")
    css = (STATIC / "editor.css").read_text("utf-8")
    select = editor[editor.index("  function select(index, focus = null) {") :]
    select = select[: select.index("\n  }\n")]
    # Its thumbnail brought into view as the frame is drawn, not measured there and then too.
    assert "requestAnimationFrame(thumbInView);" in select and "inView();" not in select
    # The stage puts in a slide read ahead, and asks for the ones beside it.
    assert "const ready = page?.svg ? ahead.take(shows) : null;" in editor
    assert "ahead.want([state.slide + 1, state.slide - 1]" in editor
    # The notes fitted to their words only when they are other words.
    assert "if (notesArea.value !== notesFitted) {" in editor
    # Typing in an object, or a slide's own lines, copies its slide alone.
    assert '{ quiet: true, within: ["slides", state.slide], ...options }' in editor
    # Each thumbnail's picture a layer: the ring changing round it draws the ring alone.
    assert ".thumb .picture-slot { will-change: transform; }" in css
    # The list's messages and who is on each slide sorted once, not looked for slide by slide.
    rail = editor[editor.index("  function renderRail() {") :]
    rail = rail[: rail.index("\n  }\n")]
    assert "groupedBy(messages" in rail and "messages.filter((m) => m.page ===" not in rail


def test_typing_on_a_slide_reads_its_drawing_s_lines_once_and_finds_the_panel_s_field_once() -> None:
    patch = (STATIC / "slidepatch.js").read_text("utf-8")
    assert 'const before = known.lines || known.text.split("\\n")' in patch
    assert "drawn.set(svg, { text, elements: list, lines: after });" in patch
    editor = (STATIC / "editor.js").read_text("utf-8")
    assert "if (!twin?.isConnected) twin = inspectorBody.querySelector(" in editor
