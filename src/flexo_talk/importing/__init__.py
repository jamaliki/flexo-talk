"""PowerPoint and Keynote decks brought into Flexo: each a new deck of its own.

``import_presentation(source, target)`` reads a ``.pptx`` (``powerpoint``) or a ``.key``
(``keynote``) and writes a new Flexo deck at ``target`` -- a bundle (``.flexo``), or a folder
-- its slides looking as they did: words, lists, pictures, tables and equations placed where
they stood, shapes and connectors as Flexo's own (``writing``). The source is only read.
Nothing makes an import fail but a file that is no deck at all: what cannot be brought across
is kept as its place and said in the ``Report`` it answers.

    flexo-talk import talk.pptx -o talk.flexo
"""

from __future__ import annotations

import re
import shutil
import tempfile
import zipfile
from pathlib import Path

from flexo_talk.importing.report import Placeholder, Progress, Report, quiet

__all__ = ["ENDINGS", "ImportFailed", "Placeholder", "Report", "import_presentation", "kind_of", "read"]

ENDINGS = (".pptx", ".key")
"""The files a deck is imported from."""

class ImportFailed(ValueError):
    """A file that is no PowerPoint or Keynote deck (or cannot be read as one), said in words."""


def kind_of(source: Path) -> str | None:
    """``powerpoint`` or ``keynote`` for a file that is one (by its contents, then its name)."""

    source = Path(source)
    if source.is_dir():
        return "keynote" if (source / "Index.zip").exists() or (source / "Index").is_dir() else None
    try:
        with zipfile.ZipFile(source) as archive:
            names = archive.namelist()
    except (OSError, zipfile.BadZipFile):
        return None
    if any(name == "ppt/presentation.xml" or name.endswith("/presentation.xml") for name in names):
        return "powerpoint"
    if any(name.startswith(("Index/", "Index.zip")) or "/Index/" in name or name.endswith("/Index.zip")
           for name in names):
        return "keynote"
    return None


def read(source: Path, report: Report, progress: Progress = quiet):
    """The deck at ``source`` as a ``Presentation``, whichever program made it."""

    kind = kind_of(source)
    if kind == "powerpoint":
        from flexo_talk.importing import powerpoint

        return powerpoint.read(source, report, progress)
    if kind == "keynote":
        from flexo_talk.importing import keynote

        return keynote.read(source, report, progress)
    ending = source.suffix.lower()
    if ending == ".ppt":
        raise ImportFailed(f"{source.name} is an old PowerPoint file (.ppt): save it as .pptx in PowerPoint first.")
    raise ImportFailed(f"{source.name} is not a PowerPoint (.pptx) or Keynote (.key) deck.")


def import_presentation(
    source: str | Path,
    target: str | Path,
    *,
    progress: Progress = quiet,
    folder: bool | None = None,
) -> Report:
    """``source`` (a ``.pptx`` or ``.key``) as a new Flexo deck at ``target``: a bundle
    (``.flexo``; one named otherwise is given the ending), or -- ``folder``, or a ``target``
    that is a folder already -- a folder holding the deck and its pictures. The source is never
    changed. What it made, and what it could not bring across, is in the report answered."""

    from flexo_talk.document import save_document
    from flexo_talk.importing.writing import write

    source, target = Path(source).expanduser(), Path(target).expanduser()
    if not source.exists():
        raise ImportFailed(f"{source.name} isn\u2019t there.")
    report = Report(source=source.name)
    progress(0.0, f"Opening {source.name}")
    try:
        presentation = read(source, report, progress)
    except ImportFailed:
        raise
    except (OSError, ValueError, KeyError, zipfile.BadZipFile) as error:
        raise ImportFailed(f"{source.name} could not be read: {error}") from error
    as_folder = folder if folder is not None else target.is_dir()
    stem = _stem(target if not as_folder or not target.is_dir() else target / source.stem)
    with tempfile.TemporaryDirectory(prefix="flexo-import-") as aside:
        made = Path(aside) / stem
        made.mkdir()
        document = write(presentation, made, stem, report, progress)
        deck = made / f"{stem}.yaml"
        progress(0.96, "Saving the deck")
        save_document(document, deck)
        if as_folder:
            destination = target / stem if target.is_dir() else target
            if destination.exists():
                raise ImportFailed(f"{destination.name} is there already.")
            shutil.copytree(made, destination)
        else:
            from flexo import bundle
            from flexo.bundle import pack

            if target.suffix.lower() != bundle.SUFFIX:
                target = target.with_name(target.name + bundle.SUFFIX)
            pack(deck, target)
    progress(1.0, "Imported")
    return report


def _stem(target: Path) -> str:
    name = target.name
    for ending in (".flexo", ".yaml", ".yml"):
        if name.lower().endswith(ending):
            name = name[: -len(ending)]
    name = re.sub(r"[/\\:]", "-", name).strip() or "Imported"
    return name
