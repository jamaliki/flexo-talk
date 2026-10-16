"""A deck's words, for finding them (``studio/static/deckwords.js``, with flexo's
``finding.js``): every line of words on its slides -- titles, lists, tables, quotes, numbers,
captions, footnotes, rows' labels, shapes' words, figures' labels in the deck and in figure
files -- and its speaker notes, each where it is drawn; replaced where it is kept; found fast
in a deck of 200 slides. Run in Node."""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import pytest
from flexo import freeform

FINDING = Path(freeform.__file__).parent / "studio" / "static" / "studio" / "finding.js"
WORDS = Path(__file__).parents[1] / "src/flexo_talk/studio/static/deckwords.js"


def run(body: str) -> object:
    node = shutil.which("node")
    if node is None:
        pytest.skip("Node is not installed")
    script = (
        f"const F = await import({json.dumps(FINDING.as_uri())});\n"
        f"const D = await import({json.dumps(WORDS.as_uri())});\n"
        f"console.log(JSON.stringify(await (async () => {{ {body} }})()));\n"
    )
    done = subprocess.run([node, "--input-type=module", "-e", script], capture_output=True, text=True, check=True)
    return json.loads(done.stdout.strip().splitlines()[-1])


DECK = {
    "deck": {"id": "talk", "footer": "Group meeting on enzymes"},
    "figures": {"shared": {"nodes": [{"id": "s", "label": "Shared enzyme"}]}},
    "slides": [
        {"layout": "title", "title": "Enzyme design", "author": "Ada", "date": "2026, enzymes"},
        {"layout": "statement", "words": "One enzyme at a time", "by": "Ada"},
        {
            "title": "We work on [enzyme design]{accent1}",
            "body": [
                {"table": [["**mechazyme**", "Mechanisms to motifs"], ["kaveh", 3]], "caption": "Tools"},
                {"bullets": ["First enzyme", ["Nested enzyme"], "Third"]},
                {"quote": "An enzyme said", "by": "Someone"},
                {"stats": [{"value": "93%", "label": "enzymes kept"}, ["12", "enzyme folds"]]},
                {"math": "E = k_{enzyme}"},
                {"code": "enzyme = fold()"},
            ],
            "notes": "Say why each enzyme matters.",
            "footnotes": ["An enzyme footnote"],
            "shapes": [
                {"kind": "text", "at": [0, 0], "text": "Enzyme shape"},
                {"kind": "group", "shapes": [{"kind": "ellipse", "text": "Grouped enzyme"}]},
            ],
        },
        {
            "title": "Figures",
            "layout": "two-columns",
            "left": [
                {
                    "figure": {
                        "figure": {"id": "f"},
                        "nodes": [{"id": "a", "label": "Enzyme\\nnode"}, {"id": "b"}],
                        "edges": [{"from": "a", "to": "b", "label": "enzyme edge"}],
                    }
                },
                {"figure": "#shared"},
            ],
            "right": [{"figure": "pipeline.yaml"}, {"figure": "plots.py:figure"}],
        },
        {"title": "Again", "body": [{"figure": "pipeline.yaml"}, {"figure": "#shared"}]},
    ],
}
FILES = {"pipeline.yaml": {"nodes": [{"id": "x", "label": "Filed enzyme"}], "edges": []}}


def test_every_line_of_words_is_a_field_where_it_is_drawn() -> None:
    fields = run(f"""
      const fields = D.deckFields({json.dumps(DECK)}, {{ files: {json.dumps(FILES)}, figure: F.figureFields }});
      return fields.map((f) => [f.slide, f.name, f.element, f.path, f.kind]);
    """)
    seen = {(slide, name, element): (path, kind) for slide, name, element, path, kind in fields}
    assert (0, "Title", "slide1.title") in seen
    # An author and a date are drawn as one line, the byline.
    assert (0, "Author", "slide1.byline") in seen and (0, "Date", "slide1.byline") in seen
    assert seen[(1, "Statement", "slide2.title")] == (["slides", 1, "words"], "markup")
    assert seen[(2, "Table", "slide3.body.0.0.0")] == (["slides", 2, "body", 0, "table", 0, 0], "markup")
    # A number in a cell is its words too.
    assert (2, "Table", "slide3.body.0.1.1") in seen
    assert (2, "Caption", "slide3.body.0.caption") in seen
    # A list's items one line each, depth first, as the slide draws them.
    assert seen[(2, "List", "slide3.body.1.1")] == (["slides", 2, "body", 1, "bullets", 1, 0], "markup")
    assert (2, "Quote", "slide3.body.2.words") in seen and (2, "Quote", "slide3.body.2.by") in seen
    assert seen[(2, "Numbers", "slide3.body.3.1.label")] == (
        ["slides", 2, "body", 3, "stats", 1, 1],
        "markup",
    )
    assert seen[(2, "Equation", "slide3.body.4")][1] == "plain"
    assert seen[(2, "Code", "slide3.body.5")][1] == "plain"
    assert (2, "Footnote", "slide3.footnote0") in seen
    assert seen[(2, "Shape", "slide3.shapes.1.0.text")] == (
        ["slides", 2, "shapes", 1, "shapes", 0, "text"],
        "markup",
    )
    # Speaker notes are words as typed, drawn nowhere on the slide.
    assert seen[(2, "Notes", None)] == (["slides", 2, "notes"], "plain")
    # The footer, the same on every slide, once: on the first slide that shows it.
    assert [f for f in fields if f[1] == "Footer"] == [[2, "Footer", "slide3.footer", ["deck", "footer"], "markup"]]
    # A figure's labels: in the deck, a figure the deck keeps (once), and a figure file (once,
    # changed by an edit of its figure: no path in the deck).
    assert seen[(3, "Figure", "slide4.left.0.a.label")] == (
        ["slides", 3, "left", 0, "figure", "nodes", 0, "label"],
        "label",
    )
    assert (3, "Figure", "slide4.left.0.edge.1.a-to-b.label") in seen
    assert seen[(3, "Figure", "slide4.left.1.s.label")] == (
        ["figures", "shared", "nodes", 0, "label"],
        "label",
    )
    assert seen[(3, "Figure", "slide4.right.0.x.label")] == (None, "label")
    assert not any(slide == 4 and name == "Figure" for slide, name, *_ in fields)
    # Where each is gone to, in the order the slides read.
    assert [slide for slide, *_ in fields] == sorted(slide for slide, *_ in fields)


def test_every_enzyme_is_found_and_replaced_where_it_is_kept() -> None:
    made = run(f"""
      const deck = {json.dumps(DECK)};
      const fields = F.wordIndex().build(D.deckFields(deck, {{ files: {json.dumps(FILES)}, figure: F.figureFields }}));
      const found = F.search(fields, "enzyme", {{ wholeWords: true }});
      const copy = structuredClone(deck);
      const byField = new Map();
      for (const m of found) {{
        if (!m.field.path) continue;
        if (!byField.has(m.field)) byField.set(m.field, []);
        byField.get(m.field).push([m.start, m.end]);
      }}
      for (const [field, ranges] of byField) {{
        D.setField(copy, field.path, F.replaced(field.value, field.kind, ranges, "protein"));
      }}
      return {{ count: found.length, files: found.filter((m) => m.field.file).length,
        names: [...new Set(found.map((m) => m.field.name))].sort(),
        title: copy.slides[2].title, cell: copy.slides[2].body[0].table, notes: copy.slides[2].notes,
        node: copy.slides[3].left[0].figure.nodes[0].label, shared: copy.figures.shared.nodes[0].label,
        shape: copy.slides[2].shapes[1].shapes[0].text, kept: D.fieldAt(copy, ["slides", 2, "body", 4, "math"]) }};
    """)
    # Whole words: not "enzymes" (the date's, the footer's, the numbers' label).
    assert made["count"] == 17
    assert made["files"] == 1
    assert made["names"] == [
        "Code",
        "Equation",
        "Figure",
        "Footnote",
        "List",
        "Notes",
        "Numbers",
        "Quote",
        "Shape",
        "Statement",
        "Title",
    ]
    assert made["title"] == "We work on [protein design]{accent1}"
    assert made["cell"] == [["**mechazyme**", "Mechanisms to motifs"], ["kaveh", 3]]
    assert made["notes"] == "Say why each protein matters."
    assert made["node"] == "protein\\nnode"
    assert made["shared"] == "Shared protein"
    assert made["shape"] == "Grouped protein"
    assert made["kept"] == "E = k_{protein}"


def test_two_hundred_slides_are_read_once_and_found_at_each_key() -> None:
    timed = run("""
      const slide = (n) => ({
        title: `Slide ${n}: motif scaffolding with [diffusion]{accent}`,
        body: [
          { bullets: ["We sample **motif** positions", ["through the constraint graph", "step by step"],
            "and prune them"] },
          { table: [["Model", "Motif", "Score"],
            ...Array.from({ length: 5 }, (_, r) => [`m${r}`, `motif ${r}`, String(r)])] },
          { figure: { figure: { id: `f${n}` },
            nodes: Array.from({ length: 12 }, (_, k) => ({ id: `n${k}`, label: `Step ${k}\\\\nmotif` })),
            edges: Array.from({ length: 11 }, (_, k) => ({ from: `n${k}`, to: `n${k + 1}`, label: "then" })) } },
        ],
        shapes: Array.from({ length: 8 },
          (_, k) => ({ kind: "rectangle", at: [k, k], size: [10, 10], text: `Box ${k} motif` })),
        notes: `Say why the motif on slide ${n} matters, and what the enzyme does next.`,
      });
      const deck = { deck: { id: "big" }, slides: Array.from({ length: 200 }, (_, n) => slide(n + 1)) };
      const index = F.wordIndex();
      const ms = (work) => {
        const start = performance.now();
        const out = work();
        return [performance.now() - start, out];
      };
      const [cold, fields] = ms(() => index.build(D.deckFields(deck, { figure: F.figureFields })));
      // A change: one slide's title. The deck is read again, its other words as they were.
      deck.slides[120].title = "A new title";
      const [warm] = ms(() => index.build(D.deckFields(deck, { figure: F.figureFields })));
      const keys = ["m", "mo", "mot", "moti", "motif"].map((typed) => ms(() => F.search(fields, typed)));
      const whole = ms(() => F.search(fields, "Motif", { matchCase: true, wholeWords: true }));
      return { fields: fields.length, cold, warm, keys: keys.map(([t]) => t), found: keys.at(-1)[1].length,
        whole: whole[0], wholeFound: whole[1].length };
    """)
    assert timed["fields"] > 9000
    # Each slide's title, list, table (its heading and five cells), figure, shapes and notes.
    assert timed["found"] == 200 * (1 + 1 + 6 + 12 + 8 + 1)
    assert timed["wholeFound"] == 200
    # Read once as the deck opens, then again as it changes -- never at each key typed -- and
    # each key's search well within a frame.
    assert timed["cold"] < 400, timed
    assert timed["warm"] < 200, timed
    assert max(timed["keys"]) < 40, timed
