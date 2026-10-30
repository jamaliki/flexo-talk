"""What both readers do once a deck is read: find the faces its words are set in, and how it
sets its titles, from its slides themselves (a template's theme may name neither)."""

from __future__ import annotations

from collections import Counter

from flexo_talk.importing.model import Box, Element, Group, Presentation, TextBox


def faces(out: Presentation) -> None:
    """The deck's faces as its words are set: the one most of its titles are set in, and the
    one most of its other words are."""

    titles: Counter = Counter()
    words: Counter = Counter()

    def count(elements: list[Element]) -> None:
        for element in elements:
            if isinstance(element, Group):
                count(element.children)
                continue
            frame = getattr(element, "frame", None)
            if frame is None:
                continue
            counter = titles if getattr(element, "role", None) == "title" else words
            for paragraph in frame.paragraphs:
                for run in paragraph.runs:
                    if run.font and run.text.strip() and run.tex is None:
                        counter[run.font] += len(run.text)

    for slide in out.slides:
        count(slide.elements)
    if words:
        out.theme.minor = words.most_common(1)[0][0]
    if titles:
        out.theme.major = titles.most_common(1)[0][0]
    elif words:
        out.theme.major = out.theme.minor


def title_look(out: Presentation) -> dict[str, object]:
    """How most of the deck's titles are set: their size, whether bold, their side, and how far
    in from the slide's left they start."""

    sizes, bold, align, lefts = [], [], [], []
    for slide in out.slides:
        if slide.layout == "title":
            continue
        for element in slide.elements:
            if isinstance(element, TextBox) and element.role == "title" and not element.frame.empty:
                runs = [run for paragraph in element.frame.paragraphs for run in paragraph.runs if run.text.strip()]
                if runs and runs[0].size:
                    sizes.append(runs[0].size * element.frame.scale)
                if runs:
                    bold.append(all(run.bold for run in runs))
                first = next((paragraph for paragraph in element.frame.paragraphs if paragraph.words.strip()), None)
                if first is not None:
                    align.append(first.align or "start")
                lefts.append(element.box.x + element.frame.insets[0])
                break
    look: dict[str, object] = {}
    if sizes:
        look["size"] = sorted(sizes)[len(sizes) // 2]
        look["bold"] = sum(bold) * 2 > len(bold)
        look["align"] = max(set(align), key=align.count)
        look["box"] = Box(sorted(lefts)[len(lefts) // 2], 0.0, 0.0, 0.0)
    return look
