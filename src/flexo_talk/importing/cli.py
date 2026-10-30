"""``flexo-talk import talk.pptx``: a PowerPoint or Keynote deck made a new Flexo deck.

The new deck is a bundle (``talk.flexo``) named as the source is, in the folder the command is
run in, unless ``-o`` names another (or ``--folder``, a folder holding the deck and its
pictures). The source is only read. Its progress goes to the terminal as it goes (a line a
step where the terminal is no terminal), and what could not be brought across is said after.
"""

from __future__ import annotations

import argparse
import os
import shutil
import sys
from pathlib import Path


def run(arguments: argparse.Namespace) -> int:
    from flexo_talk.importing import ImportFailed, import_presentation

    source = Path(arguments.deck).expanduser()
    if arguments.output:
        target = Path(arguments.output).expanduser()
    else:
        target = Path.cwd() / (source.stem if arguments.folder else f"{source.stem}.flexo")
    if not arguments.folder and target.suffix.lower() != ".flexo" and not target.is_dir():
        target = target.with_name(target.name + ".flexo")
    destination = target / source.stem if arguments.folder and target.is_dir() else target
    if destination.resolve() == source.resolve():
        print("flexo-talk: the deck made would be written over its source; name another with -o.", file=sys.stderr)
        return 1
    if destination.exists():
        if not arguments.force:
            print(f"flexo-talk: {destination} is there already (--force replaces it).", file=sys.stderr)
            return 1
        if destination.is_dir():
            shutil.rmtree(destination)
        else:
            destination.unlink()
    tty = sys.stderr.isatty()
    last = [""]

    def progress(fraction: float, message: str) -> None:
        if arguments.quiet:
            return
        line = f"{round(fraction * 100):3d}%  {message}"
        if tty:
            print(f"\r{line[:78]:<78}", end="", file=sys.stderr, flush=True)
        elif message != last[0]:
            print(line, file=sys.stderr)
        last[0] = message

    try:
        report = import_presentation(source, destination if arguments.folder else target, progress=progress,
                                     folder=arguments.folder)
    except ImportFailed as error:
        if tty and not arguments.quiet:
            print(file=sys.stderr)
        print(f"flexo-talk: {error}", file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        return 130
    except Exception as error:
        if os.environ.get("FLEXO_TRACEBACK"):
            raise
        print(f"\nflexo-talk: {source.name} could not be imported: {error}", file=sys.stderr)
        print("(Set FLEXO_TRACEBACK=1 to show the full traceback.)", file=sys.stderr)
        return 1
    if tty and not arguments.quiet:
        print(file=sys.stderr)
    print(f"Made {destination if arguments.folder else target}")
    print(report.summary())
    return 0
