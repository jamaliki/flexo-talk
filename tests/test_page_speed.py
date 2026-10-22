"""What keeps the deck editor's page quick on a long deck, run in Node with a few stand-ins for
the page: the slide list's thumbnails drawn as they come into sight (thumbs.js), and the closed
hand shown on what the pointer is over while something is dragged (grabbing.js) -- and the
editor's use of both, and of its thumbnails kept while a slide is edited."""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import pytest

STATIC = Path(__file__).parents[1] / "src" / "flexo_talk" / "studio" / "static"

# A page as far as the two modules see it: elements with classes and children, an observer of
# what is in sight that the test says is in sight, and one of an element's class.
PAGE = """
class Element {
  constructor(name) {
    this.name = name; this.children = []; this.parentNode = null; this.isConnected = true; this.classes = new Set();
  }
  get className() { return [...this.classes].join(" "); }
  set className(value) { this.classes = new Set(String(value).split(" ").filter(Boolean)); }
  get classList() {
    const el = this;
    return { add: (c) => el.classes.add(c), remove: (c) => el.classes.delete(c), contains: (c) => el.classes.has(c) };
  }
  replaceChildren(...nodes) {
    for (const n of this.children) n.parentNode = null;
    const from = (n) => n.parentNode && n.parentNode !== this ? n.parentNode : null;
    for (const n of nodes) if (from(n)) from(n).children = from(n).children.filter((m) => m !== n);
    this.children = nodes;
    for (const n of nodes) n.parentNode = this;
  }
}
const observers = [];
globalThis.IntersectionObserver = class {
  constructor(callback, options) {
    this.callback = callback; this.options = options; this.seen = new Set(); observers.push(this);
  }
  observe(node) { this.seen.add(node); }
  unobserve(node) { this.seen.delete(node); }
  tell(node, near) { this.callback([{ target: node, isIntersecting: near }]); }
};
const listeners = {};
let mutated = null;
globalThis.MutationObserver = class { constructor(callback) { mutated = callback; } observe() {} };
globalThis.document = { createElement: (name) => new Element(name), body: new Element("body"),
  addEventListener: (type, fn) => { (listeners[type] ||= []).push(fn); } };
const fire = (type, target) => (listeners[type] || []).forEach((fn) => fn({ type, target }));
"""


def run(body: str) -> object:
    node = shutil.which("node")
    if node is None:
        pytest.skip("Node is not installed")
    script = (
        PAGE
        + f"const T = await import({json.dumps((STATIC / 'thumbs.js').as_uri())});\n"
        + f"const G = await import({json.dumps((STATIC / 'grabbing.js').as_uri())});\n"
        + f"console.log(JSON.stringify(await (async () => {{ {body} }})()));\n"
    )
    result = subprocess.run([node, "--input-type=module", "-e", script], capture_output=True, text=True, check=True)
    return json.loads(result.stdout.strip().splitlines()[-1])


def test_a_thumbnail_is_drawn_only_while_near_enough_to_be_seen() -> None:
    found = run("""
      const made = [];
      const picture = (svg, hash) => { made.push(hash); return new Element("picture"); };
      const slot = T.lazyPictures(new Element("list"), picture);
      const thumb = new Element("thumb");
      const one = slot("<svg/>", "h1", 0);
      one.watch(thumb);
      const before = [one.children.length, made.length];
      observers[0].tell(thumb, true);
      const near = [one.children.length, made.length, one.whole()];
      observers[0].tell(thumb, false);
      const far = [one.children.length, made.length];
      return { before, near, far, margin: observers[0].options.rootMargin, watched: observers[0].seen.has(thumb) };
    """)
    assert found["before"] == [0, 0]
    assert found["near"] == [1, 1, True]
    assert found["far"] == [0, 1]
    assert found["margin"] == "600px 0px" and found["watched"] is True


def test_a_thumbnail_made_again_where_one_was_seen_is_drawn_at_once() -> None:
    found = run("""
      const slot = T.lazyPictures(new Element("list"), () => new Element("picture"));
      const first = slot("<svg/>", "a", 3), thumb = new Element("thumb");
      first.watch(thumb);
      observers[0].tell(thumb, true);
      first.drop();
      const again = slot("<svg/>", "b", 3), elsewhere = slot("<svg/>", "c", 9);
      return [again.children.length, elsewhere.children.length, observers[0].seen.has(thumb)];
    """)
    assert found == [1, 0, False]


def test_a_picture_taken_for_another_drawing_leaves_its_thumbnail_not_whole() -> None:
    assert (
        run("""
      const slot = T.lazyPictures(new Element("list"), () => new Element("picture"));
      const one = slot("<svg/>", "a", 0), thumb = new Element("thumb");
      one.watch(thumb);
      observers[0].tell(thumb, true);
      const ghost = new Element("ghost");
      ghost.replaceChildren(one.children[0]);
      return one.whole();
    """)
        is False
    )


def test_the_closed_hand_is_on_what_the_pointer_is_over_only_while_dragging() -> None:
    found = run("""
      G.grabbingHand();
      const a = new Element("path"), b = new Element("div");
      fire("pointermove", a);
      const before = a.classList.contains("grab-here");
      document.body.classList.add("block-grabbing"); mutated();
      const started = a.classList.contains("grab-here");
      fire("pointermove", b);
      const moved = [a.classList.contains("grab-here"), b.classList.contains("grab-here")];
      document.body.classList.remove("block-grabbing"); mutated();
      const ended = b.classList.contains("grab-here");
      G.grabbingHand();
      return { before, started, moved, ended, once: (listeners.pointermove || []).length };
    """)
    assert found == {"before": False, "started": True, "moved": [False, True], "ended": False, "once": 1}


def test_the_editor_draws_thumbnails_lazily_marks_the_chosen_one_and_holds_the_edited_one() -> None:
    editor = (STATIC / "editor.js").read_text("utf-8")
    css = (STATIC / "editor.css").read_text("utf-8")
    assert "lazyPictures(railList, (svg, hash) => picture(svg, hash))" in editor
    assert 'old[index].classList.toggle("on"' in editor
    assert "holdThumb(state.slide, was)" in editor and "letThumbGo();" in editor
    assert "grabbingHand();" in editor
    # Never a rule over every element as a drag starts: WebKit styles the whole window again.
    assert "body.block-grabbing *" not in css
    assert "body.block-grabbing .grab-here" in css
