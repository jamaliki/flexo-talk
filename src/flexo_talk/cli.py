"""``flexo-talk build deck.py`` -- build the deck a Python file makes.

The file names its deck as a function that returns one (``deck.py:talk``, or a
function called ``talk`` by default) or as a module-level ``deck``.
"""

from __future__ import annotations

import argparse
import importlib.util
import sys
from pathlib import Path

from flexo_talk.deck import Deck
from flexo_talk.export import FORMATS


def load_deck(target: str, theme: str | None = None) -> Deck:
    path, _, name = target.partition(":")
    source = Path(path).resolve()
    spec = importlib.util.spec_from_file_location(source.stem, source)
    if spec is None or spec.loader is None:
        raise SystemExit(f"cannot read {path}")
    module = importlib.util.module_from_spec(spec)
    sys.path.insert(0, str(source.parent))
    spec.loader.exec_module(module)
    found = getattr(module, name or "talk", None) or getattr(module, "deck", None)
    if isinstance(found, Deck):
        return found
    if callable(found):
        return found(theme) if theme else found()
    raise SystemExit(f"{path} has no function {name or 'talk'!r} and no deck")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="flexo-talk", description="Build slide decks written with flexo-talk.")
    commands = parser.add_subparsers(dest="command", required=True)
    build = commands.add_parser("build", help="build a deck: PPTX, PDF, and an SVG and PNG per slide")
    build.add_argument("deck", help="deck.py, or deck.py:function")
    build.add_argument("-o", "--output", default="build", help="directory to write into (default: build)")
    build.add_argument("--theme", help="pass a theme name to the deck function")
    build.add_argument("--formats", default=",".join(FORMATS), help=f"comma-separated: {', '.join(FORMATS)}")
    arguments = parser.parse_args(argv)
    deck = load_deck(arguments.deck, arguments.theme)
    result = deck.build(arguments.output, formats=tuple(arguments.formats.split(",")))
    print(result.summary())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
