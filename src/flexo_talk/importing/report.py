"""What an import brought across, and what it could not: said to the person after it."""

from __future__ import annotations

from collections import Counter
from collections.abc import Callable
from dataclasses import dataclass, field

Progress = Callable[[float, str], None]
"""Told how far an import has gone (0 to 1) and what it is doing, as it goes."""


def quiet(fraction: float, message: str) -> None:
    """A progress that says nothing."""


@dataclass
class Placeholder:
    """Something kept only as its place (or a picture of itself): its slide, what it is, why."""

    slide: int
    kind: str
    why: str = ""
    picture: bool = False
    """Whether a picture of it stands where it was (else an empty box, marked TODO)."""


@dataclass
class Report:
    """What an import made: its slides, what it brought across by kind, what became a
    placeholder, which faces it set in others, and anything else worth saying."""

    source: str = ""
    slides: int = 0
    made: Counter = field(default_factory=Counter)
    placeholders: list[Placeholder] = field(default_factory=list)
    fonts: dict[str, str] = field(default_factory=dict)
    """The source's families not on this Mac, and those set in their place."""
    notes: list[str] = field(default_factory=list)
    _said: set[str] = field(default_factory=set)

    def note(self, words: str) -> None:
        """Something worth saying, said once however often it happens."""

        if words not in self._said:
            self._said.add(words)
            self.notes.append(words)

    def placeholder(self, slide: int, kind: str, why: str = "", *, picture: bool = False) -> None:
        self.placeholders.append(Placeholder(slide, kind, why, picture))

    def summary(self) -> str:
        """The report in a few lines of words."""

        lines = [f"{self.slides} slide{'s' if self.slides != 1 else ''} imported from {self.source}."]
        if self.made:
            kinds = ", ".join(f"{count} {kind}" for kind, count in sorted(self.made.items(), key=lambda item: -item[1]))
            lines.append(f"Brought across: {kinds}.")
        lines.extend(self.placeholder_lines())
        for missing, used in self.fonts.items():
            lines.append(f"{missing} is not on this Mac: set in {used}.")
        lines.extend(self.notes)
        return "\n".join(lines)

    def placeholder_lines(self) -> list[str]:
        """Each kind of placeholder, how many and on which slides."""

        if not self.placeholders:
            return []
        lines = []
        kinds: dict[str, list[Placeholder]] = {}
        for place in self.placeholders:
            kinds.setdefault(place.kind, []).append(place)
        total = len(self.placeholders)
        lines.append(f"{total} objects became placeholders:" if total != 1 else "1 object became a placeholder:")
        for kind, places in kinds.items():
            slides = sorted({place.slide for place in places})
            shown = ", ".join(str(number) for number in slides[:12]) + (", …" if len(slides) > 12 else "")
            pictured = all(place.picture for place in places)
            how = " (a picture of it kept)" if pictured else ""
            lines.append(f"  {len(places)} {kind}{how}: slide{'s' if len(slides) != 1 else ''} {shown}")
        return lines

    def as_dict(self) -> dict[str, object]:
        return {
            "source": self.source,
            "slides": self.slides,
            "made": dict(self.made),
            "placeholders": [place.__dict__ for place in self.placeholders],
            "fonts": dict(self.fonts),
            "notes": list(self.notes),
        }
