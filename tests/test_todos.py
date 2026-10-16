"""A deck's TODOs (``studio/static/todos.js``, with ``deckwords.js`` and flexo's ``todos.js``): the
word TODO, in capitals, as a word of its own, on every kind of words a slide has -- titles,
subtitles and bylines; texts, lists, quotes and tables; shapes' words; figures' labels, in the
deck or in a figure file; equations -- and in its speaker notes; the slides they are on, said as
the show starts and the deck is exported; read again quickly as a deck of 200 slides is typed in.
Run in Node."""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import pytest
from flexo import freeform

STUDIO = Path(freeform.__file__).parent / "studio" / "static" / "studio"
STATIC = Path(__file__).parents[1] / "src/flexo_talk/studio/static"


def run(body: str) -> object:
    node = shutil.which("node")
    if node is None:
        pytest.skip("Node is not installed")
    script = (
        f"const F = await import({json.dumps((STUDIO / 'finding.js').as_uri())});\n"
        f"const T = await import({json.dumps((STUDIO / 'todos.js').as_uri())});\n"
        f"const D = await import({json.dumps((STATIC / 'deckwords.js').as_uri())});\n"
        f"const C = await import({json.dumps((STATIC / 'todocount.js').as_uri())});\n"
        "const todos = (deck, files = {}) =>\n"
        "  T.todoIndex().find(D.deckFields(deck, { files, figure: F.figureFields })).matches;\n"
        f"console.log(JSON.stringify(await (async () => {{ {body} }})()));\n"
    )
    done = subprocess.run([node, "--input-type=module", "-e", script], capture_output=True, text=True, check=True)
    return json.loads(done.stdout.strip().splitlines()[-1])


DECK = {
    "deck": {"id": "talk", "footer": "Group meeting"},
    "figures": {"shared": {"nodes": [{"id": "s", "label": "Shared TODO"}]}},
    "slides": [
        {"layout": "title", "title": "Enzymes TODO", "subtitle": "TODO: venue", "author": "Ada TODO", "date": "TODO"},
        {"layout": "statement", "words": "One TODO at a time", "by": "TODO who said it"},
        {
            "title": "Methods",
            "body": [
                {"text": "A **TODO** in bold"},
                {"bullets": ["First", ["Nested TODO: cite"], "Third"]},
                {"quote": "An enzyme said TODO", "by": "Someone"},
                {"callout": "TODO callout words", "title": "Note"},
                {"table": [["Tool", "Use"], ["kaveh", "TODO — what it does"]], "caption": "Tools TODO"},
                {"math": "E = k_\\text{TODO}"},
                {"stats": [{"value": "93%", "label": "TODO kept"}]},
            ],
            "notes": "Say why. TODO: the rates",
            "footnotes": ["TODO footnote"],
            "shapes": [
                {"kind": "text", "at": [0, 0], "text": "Shape TODO"},
                {"kind": "group", "shapes": [{"kind": "ellipse", "text": "Grouped TODO"}]},
            ],
        },
        {
            "title": "Figures",
            "layout": "two-columns",
            "left": [
                {"figure": {"figure": {"id": "f"}, "nodes": [{"id": "a", "label": "Inline\\nTODO"}], "edges": []}},
                {"figure": "#shared"},
            ],
            "right": [{"figure": "pipeline.yaml"}],
        },
        {"title": "Lower case: todo, Todo, ToDo, TODOs and XTODO are words", "notes": "todo later"},
    ],
}
FILES = {
    "pipeline.yaml": {
        "nodes": [{"id": "x", "label": [{"text": "Filed "}, {"text": "TODO", "weight": "bold"}]}],
        "edges": [],
    }
}


def test_a_todo_is_found_in_every_kind_of_words_a_slide_has_and_its_notes() -> None:
    found = run(f"""
      return todos({json.dumps(DECK)}, {json.dumps(FILES)}).map((match) =>
        [match.field.slide, match.field.name, match.field.notes ? "notes" : match.field.element ?? match.field.file]);
    """)
    assert found == [
        [0, "Title", "slide1.title"],
        [0, "Subtitle", "slide1.subtitle"],
        [0, "Author", "slide1.byline"],
        [0, "Date", "slide1.byline"],
        [1, "Statement", "slide2.title"],
        [1, "Attribution", "slide2.byline"],
        [2, "Text", "slide3.body.0"],
        [2, "List", "slide3.body.1.1"],
        [2, "Quote", "slide3.body.2.words"],
        [2, "Callout", "slide3.body.3.words"],
        [2, "Table", "slide3.body.4.1.1"],
        [2, "Caption", "slide3.body.4.caption"],
        [2, "Equation", "slide3.body.5"],
        [2, "Numbers", "slide3.body.6.0.label"],
        [2, "Footnote", "slide3.footnote0"],
        [2, "Shape", "slide3.shapes.0.text"],
        [2, "Shape", "slide3.shapes.1.0.text"],
        [2, "Notes", "notes"],
        [3, "Figure", "slide4.left.0.a.label"],
        [3, "Figure", "slide4.left.1.s.label"],
        # A figure file's label, written as runs: its words read as one.
        [3, "Figure", "slide4.right.0.x.label"],
    ]


def test_lower_case_and_longer_words_are_not_work_left() -> None:
    found = run(f"""
      const deck = {json.dumps(DECK)};
      return {{ last: todos(deck).filter((match) => match.field.slide === 4).length,
        // (A figure file not read yet has no words: its TODO is found once it is.)
        unread: todos(deck).filter((match) => match.field.file).length }};
    """)
    assert found == {"last": 0, "unread": 0}


def test_the_slides_with_todos_are_said_those_skipped_aside() -> None:
    found = run(f"""
      const deck = {json.dumps(DECK)};
      deck.slides[1].skip = true;
      const matches = todos(deck, {json.dumps(FILES)});
      const slides = C.slidesWithTodos(deck, matches);
      return {{ slides, said: C.slidesSaid(slides.length), one: C.slidesSaid(1), none: C.slidesSaid(0) }};
    """)
    assert found == {"slides": [0, 2, 3], "said": "3 slides have TODOs", "one": "1 slide has TODOs", "none": ""}


def test_a_todo_typed_and_fixed_is_found_and_gone_and_a_deck_of_200_slides_is_read_quickly() -> None:
    found = run("""
      const slides = Array.from({ length: 200 }, (_, n) => ({ title: `Slide ${n} on enzymes`,
        body: [{ bullets: ["One point", "Another point, longer, with **bold** and $x^2$ in it", ["A nested one"]] },
          { table: [["a", "b"], ["c", "d"]] }],
        notes: `Notes for slide ${n}, said slowly.`, shapes: [{ kind: "text", text: "A label" }] }));
      const deck = { slides };
      const index = T.todoIndex();
      const read = () => index.find(D.deckFields(deck, { figure: F.figureFields })).matches;
      const t0 = performance.now();
      read();
      const cold = performance.now() - t0;
      // Typed, a key at a time, in slide 120's notes: read again after each.
      const keys = " TODO: the rates";
      const t1 = performance.now();
      const counts = [];
      for (const key of keys) { slides[120].notes += key; counts.push(read().length); }
      const typed = (performance.now() - t1) / keys.length;
      // Fixed: the word taken out.
      slides[120].notes = slides[120].notes.replace("TODO: ", "");
      return { cold: cold < 400, typed: typed < 15, perKey: typed,
        counts: [counts[3], counts[4], counts[5], counts.at(-1)], fixed: read().length };
    """)
    assert found["cold"], found
    assert found["typed"], found
    # "TOD" is no TODO; "TODO" is, and stays one as ": the rates" follows it.
    assert found["counts"] == [0, 1, 1, 1]
    assert found["fixed"] == 0
