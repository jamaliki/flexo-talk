---
name: flexo-talk
description: Make slide decks in one consistent theme with flexo-talk -- titles, bullets, and real flexo figures -- exported to editable PowerPoint (PPTX) and to SVG/PNG per slide. Use when asked for a talk, presentation, or slides that should match a paper's figures or a lab's style.
---

# Making slide decks with flexo-talk

flexo-talk writes a deck the way [flexo](https://github.com/jamaliki/flexo)
writes a figure: a `with` block in one theme, no coordinates. Every figure on a
slide is a real flexo figure, compiled in the deck's theme and scaled to its
place. The PowerPoint it writes is native shapes and text, editable everywhere.

## The loop

1. Write the deck (below): a title slide, then one slide per idea.
2. `result = deck.build("build")` writes `build/<id>.pptx` and an SVG and PNG
   per slide; `print(result.summary())` lists any figure's lint diagnostics.
3. Look at the PNGs; fix wording, split crowded slides, simplify figures.

## Writing a deck

```python
from flexo_talk import Deck

with Deck("results", theme="paper", footer="Group meeting") as deck:
    deck.title("A clear title", subtitle="What the talk shows", author="Name", date="2026")
    with deck.slide("One idea per slide") as slide:
        slide.bullets("A short claim", "Another", ["a detail, one level in"])
        slide.notes("What to say here.")
    with deck.slide("Words and a figure", layout="two-columns") as slide:
        slide.left.bullets("What the model *is*", "Why it works")
        with slide.right.figure() as figure:              # a flexo Figure
            x = figure.root.text("x", "Input $x$")
            figure.root.block("enc", label="Encoder", input=x, tone="encoder")
    deck.section("Part two")
    with deck.slide("A figure alone", layout="figure") as slide:
        slide.add(existing_flexo_figure)                    # redrawn in the deck's look
deck.build("build")
```

- `Deck(id, theme=, palette=, font=, conventions=, sketch=, background=True, footer=, style=DeckStyle(...))`.
- Slides: `deck.title(...)`, `deck.section(title, subtitle=)`,
  `deck.slide(title, layout=...)` with layouts `content` (one `slide.body`),
  `two-columns` (`slide.left`, `slide.right`), `figure` (one large figure), `blank`.
- A region stacks blocks top to bottom: `bullets(*items)` (nested list = next
  level), `text(words, size=, align="start"|"middle"|"end", muted=)`,
  `figure(**flexo_figure_options)` (use as `with`), `add(figure)`, `image(path)`.
  Calling these on the slide uses its first region.
- Slide text: `$...$` math (as in flexo), `*emphasis*`, `**strong**`.
- `slide.notes(text)` becomes the PowerPoint speaker notes.

## Beautiful by default: habits that pay

- **One theme for the talk and the paper.** Use the paper's flexo theme or theme
  file (`theme="lab.yaml"`) so figures, colours, and type match everywhere.
- **Figures from the paper, unchanged.** `slide.add(figure)` recompiles them at
  the slide's size; a `figure` layout makes one as large as the slide allows.
- **Few words.** Three to five bullets, one line each; put detail in the notes.
- **Tones carry meaning across slides:** keep the same `tone=` names in every
  figure so "encoder" is one colour throughout; `badge="frozen"|"trained"|"tuned"`
  marks what trains.
- Proportions live in `DeckStyle` (title, body, figure text sizes; margins;
  indents; title rule; slide numbers) -- change them once for the whole deck.

## PowerPoint notes

- Every rectangle, ellipse, line (exact arrowheads), and word is a native,
  editable shape; flexo components are named groups; lists are real bulleted
  lists; the background and notes are set natively.
- Text is drawn by the program opening the file with its installed fonts:
  install the theme's fonts there (flexo bundles them), or use a theme font that
  is installed everywhere.

## Reference

`README.md` (the API), `examples/demo.py` (a complete deck),
flexo's `SKILL.md` and `docs/tutorial.md` (everything about the figures).
