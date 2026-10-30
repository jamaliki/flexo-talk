"""A deck taught to an agent a little at a time (``flexo.studio.agent_guides``): the brief it is
given first, the topics the deck's guide (``DeckKind.guide``) is cut into, and an example or
two of each, which a test puts together into one deck and draws (``tests/test_agent_guides.py``):
an example that no longer draws fails the tests, not an agent."""

from __future__ import annotations

import textwrap

from flexo.studio.agent_guides import Snippet, Topic, topic_list, topics_from, written

BRIEF = """\
A flexo-talk deck: one YAML document -- the deck's settings, then its slides, each a layout and
the objects (blocks) in its places. Flexo lays every slide out: write what a slide says, never
where things go. PowerPoint, PDF and pictures are all drawn from the same slides.

schema_version: 1
deck: {id: talk, theme: paper, look: classic, footer: Group meeting}
slides:
- layout: title
  title: Figures that draw themselves
  author: Ada Lovelace
- title: Hand-drawn figures cost a day each       # a claim; layout content when left out
  body:
  - bullets: [Boxes drift out of line, [and arrows with them], Each edit means redrawing]
  - text: Measured over **12** papers
  notes: What to say while it shows.
- title: The model
  layout: two-columns
  left:
  - text: Write what the model *is*
  right:
  - figure:                                       # a figure is written in its slide
      figure: {id: model}
      nodes: [{id: encoder, label: Encoder}, {id: decoder, label: Decoder}]
      edges: [{from: encoder, to: decoder}]

Layouts: {layouts}.
Objects: {blocks}.
Words are markup: **strong**, *emphasis*, $maths$, `code`, [link](url), [words]{accent}.

How to work
1. {tool:outline} first: each slide's number, title, layout, objects, build steps, TODOs and
   warnings, and what the user has selected, as a path (slides[2].body[0]) -- "this".
2. {tool:read_document} with {arg:read_document.slides}: [n, ...] reads just the slides you
   need, exactly as the whole text has them.
3. {tool:edit_document} a few lines at a time, `old` copied exactly from what you read. Its reply
   says what changed, warns of anything deleted, and says what to look at next.
4. {tool:look} at the slides you changed, once ({arg:look.pages}: [n]). {arg:look.sheet}: true tiles many slides
   small, to match a talk's style; {arg:look.annotate}: true labels each object, shape and figure
   part with its path; {arg:look.step}: n shows a slide at a build step.
5. Stop when that look shows no warnings and the slide reads as you mean; tell the user.

Habits
- A slide says one thing: a title that is a claim, few words, six bullets at most, a figure
  where a picture helps. Several ideas are several slides.
- Never compute positions or sizes: choose a layout, its places and the order of objects. Use
  `at` and shapes' points only to mark something up, or where the user asks for a place.
- If valid YAML is laid out badly -- objects overlapping, words cut off or too small, a figure
  squeezed -- tell the user it looks like a Flexo bug, naming the slide and the YAML. Don't
  nudge places or sizes to hide it.
- When the deck sets no style yet and the user gave none, ask one question about the look
  before making many slides; otherwise match the slides around yours (look at a sheet).
- When an edit is refused (`old` does not occur), read those slides again before retrying: the
  user may have changed them. Prefer {tool:edit_document} to {tool:write_document}, and never write the
  whole deck from an old copy.
- Delete a slide or an object only when asked. Every reply names what it deleted: check it.
- Mark up a slide -- an arrow at a figure's part, a ring, a brace, a label -- with shapes over
  it, not by changing the figure or picture under them (guide shapes).
- A figure for a deck is written in its slide's object (guide figures), not as a file.
- Say what you are doing, in a few words, with {tool:status}.

Topics ({tool:guide} with topic: one of these and kind: deck; reference is the whole guide):
{topics}
"""

ABOUT = {
    "basics": "A deck's slides, places and objects; plots and figures named from files",
    "layouts": "Each layout and its keys, columns and rows",
    "blocks": "Each kind of object and its options",
    "words": "Markup in slide words",
    "figures": "Figures written in a slide, shared by several, or drawn as one across slides",
    "pictures": "Pictures: cropping, masks, GIFs, an SVG's words and colours, galleries",
    "shapes": "Shapes over a slide: arrows, rings, braces, boxes of words, glued ends",
    "insets": "Part of a picture, figure or plot shown magnified",
    "placing": "An object placed anywhere on its slide, out of the flow",
    "showing": "Objects and parts hidden, dimmed or highlighted, and built in on clicks",
    "maths": "Equations and reaction mechanisms",
    "people": "Portraits beside a slide's title",
    "themes": "The deck's settings: theme, look, palette, fonts, proportions, logos",
}

ANCHORS = {
    "pictures": [r"A picture \(``image``\) may be cropped", r"A picture's ``mask`` may be"],
    "figures": [
        r"^A figure lives in the deck",
        r"^A visualisation that changes",
        r"^A figure is drawn in the deck's theme",
        r"^A deck's figures live in the deck",
    ],
    "showing": [r"^A figure block may show its figure", r"^So may any object, and any shape"],
    "maths": [r"^A ``mechanism`` is a reaction"],
    "shapes": [r"^Any slide may have ``shapes``", r"^Shapes \(a slide's shapes"],
    "insets": [r"^A zoom inset is a shape too"],
    "placing": [r"^Any block may be placed anywhere"],
    "layouts": [r"^A slide of columns", r"^Every slide may also take"],
    "python": [r"^``read_deck`` makes"],
    "people": [r"^people: portraits at the title"],
    "blocks": [r"^Blocks:"],
    "themes": [r"^Deck settings:"],
    "words": [r"^Slide words are markup"],
    "basics": [r"^Good slides say one thing"],
}

PNG = b"png"
"""A file an example names, written by the test as a small picture."""

PICTURE = {"pictures/cell.png": PNG}

SNIPPETS: dict[str, list[Snippet]] = {
    "basics": [
        Snippet(
            "a title slide and a slide of content",
            """\
- layout: title
  title: Figures that draw themselves
  subtitle: A group meeting
  author: Ada Lovelace
  date: May 2026
- title: Hand-drawn figures cost a day each
  body:
  - bullets: [Boxes drift out of line, [and arrows with them], Each edit means redrawing]
  - text: Measured over **12** papers
  notes: Everyone here has redrawn a figure at 2 a.m.
""",
        )
    ],
    "layouts": [
        Snippet(
            "a section, a statement, two columns, three columns set in rows",
            """\
- {layout: section, title: Methods}
- {layout: statement, words: Every figure is a program., by: The lab}
- title: Before and after
  layout: two-columns
  split: 0.4
  left: [{text: By hand, size: 24}]
  right: [{bullets: [Laid out, Routed, Themed]}]
- title: Three ways
  layout: columns
  widths: [1, 1, 2]
  rows: ["", Cost]
  columns:
  - [{text: Inkscape}, {text: A day}]
  - [{text: Python}, {text: An hour}]
  - [{text: Flexo}, {text: Minutes}]
""",
        )
    ],
    "blocks": [
        Snippet(
            "a table, code, a quote, numbers and a callout",
            """\
- title: What we measured
  layout: two-columns
  left:
  - table: [[Model, Score], [Ours, "0.91"], [Theirs, "0.85"]]
    header: true
  - code: |
      deck = Deck("talk")
      deck.build()
  right:
  - quote: Figures should draw themselves.
    by: A reviewer
  - stats: [{value: "3x", label: faster}, {value: "0", label: arrows nudged}]
  - callout: Every number here is from the main run.
    title: Note
""",
        )
    ],
    "words": [
        Snippet(
            "markup",
            """\
- title: "Words: **strong**, *emphasis* and [colour]{accent}"
  body:
  - text: "Maths $E = mc^2$, `code`, a [link](https://example.org), and [faint]{dim} words"
""",
        )
    ],
    "figures": [
        Snippet(
            "a figure in a slide, and one shared by two slides",
            """\
slides:
- title: The pipeline
  body:
  - figure:
      figure: {id: pipeline}
      nodes: [{id: data, label: Data}, {id: model, label: Model, properties: {tone: encoder}}]
      edges: [{from: data, to: model}]
- title: Where it fails
  body:
  - figure: '#shared'
- title: Where it works
  body:
  - {figure: '#shared', dim: [loss]}
figures:
  shared:
    figure: {id: shared}
    nodes: [{id: encoder, label: Encoder}, {id: loss, label: Loss}]
    edges: [{from: encoder, to: loss}]
""",
        )
    ],
    "pictures": [
        Snippet(
            "a picture cropped round, and a gallery",
            """\
- title: Cells
  layout: two-columns
  left:
  - {image: pictures/cell.png, crop: [0.1, 0.1, 0.8, 0.8], mask: circle, caption: A cell}
  right:
  - gallery: [pictures/cell.png, pictures/cell.png]
    columns: 2
""",
            files=PICTURE,
        )
    ],
    "shapes": [
        Snippet(
            "an arrow glued to an object, a ring, a brace, a box of words",
            """\
- title: The binding pocket
  body:
  - {image: pictures/cell.png, width: 300}
  shapes:
  - {kind: rounded-rectangle, id: note, at: [620, 140], size: [220, 70], fill: accent2-fill,
     line: accent2, text: "**Binding** pocket"}
  - {kind: arrow, from: {shape: note, side: left}, to: {object: "body[0]", side: right}}
  - {kind: ring, at: [400, 220], size: [120, 80]}
  - {kind: brace, from: [850, 260], to: [850, 420], text: "3 steps"}
  - {kind: text, at: [80, 470], width: 300, text: Measured at 4 K, font_size: 14}
""",
            files=PICTURE,
        )
    ],
    "insets": [
        Snippet(
            "part of a picture, magnified",
            """\
- title: A closer look
  layout: two-columns
  left:
  - image: pictures/cell.png
  shapes:
  - {kind: inset, of: "left[0]", region: [0.55, 0.3, 0.2, 0.15], at: [600, 160], size: [280, 210],
     frame_line: accent2, connector_dash: dashed, text: b}
""",
            files=PICTURE,
        )
    ],
    "placing": [
        Snippet(
            "an object placed out of the flow",
            """\
- title: A note in the corner
  body:
  - bullets: [The list keeps its place, The note sits where it is put]
  - text: Measured at 4 K
    at: [640, 420]
    width: 260
    locked: true
""",
        )
    ],
    "showing": [
        Snippet(
            "a list built item by item, an object dimmed, a figure's parts on clicks",
            """\
- title: One step at a time
  layout: two-columns
  left:
  - bullets: [First, Second, Third]
    reveal: true
  - {text: An aside, dim: true}
  right:
  - figure:
      figure: {id: steps}
      nodes: [{id: a, label: A}, {id: b, label: B}, {id: c, label: C}]
      edges: [{from: a, to: b}, {from: b, to: c}]
    stages: [[a, b], [c]]
  shapes:
  - {kind: text, at: [80, 440], width: 300, text: Then this, build: true}
""",
        )
    ],
    "maths": [
        Snippet(
            "an equation and a mechanism",
            """\
- title: The loss, and the reaction
  layout: two-columns
  left:
  - math: \\mathcal{L} = -\\sum_i y_i \\log p_i
  right:
  - mechanism:
    - {smiles: "[OH-:5].[CH3:1][Cl:4]", arrows: ["5 -> 1", "1-4 -> 4"], label: attack}
""",
        )
    ],
    "people": [
        Snippet(
            "portraits beside the title",
            """\
- title: Who did it
  people: [{image: pictures/cell.png, name: Ada}, {image: pictures/cell.png, name: Alan}]
  body:
  - text: Thanks to both.
""",
            files=PICTURE,
        )
    ],
    "themes": [
        Snippet(
            "a deck's settings (drawn as a deck of its own)",
            """\
schema_version: 1
deck:
  id: styled
  theme: paper
  look: band
  footer: Group meeting
  style: {body_size: 22, title_size: 34}
slides:
- {title: A slide in the band look, body: [{text: Its proportions set in style.}]}
""",
        )
    ],
}


def topics() -> dict[str, Topic]:
    """A deck's topics, cut from its guide."""

    from flexo_talk.studio import DeckKind

    return topics_from(DeckKind().guide(), ABOUT, ANCHORS, SNIPPETS, first="basics")


def brief() -> str:
    """What an agent is told first about a deck."""

    from flexo_talk.document import BLOCKS, SLIDE_KEYS

    def wrapped(text: str) -> str:
        return "\n".join(textwrap.wrap(text, 96, subsequent_indent="  "))

    return (
        written(BRIEF)
        .replace("Layouts: {layouts}.", wrapped(f"Layouts: {', '.join(SLIDE_KEYS)}."))
        .replace("Objects: {blocks}.", wrapped(f"Objects: {', '.join(BLOCKS)}."))
        .replace("{topics}", topic_list(topics()))
    )
