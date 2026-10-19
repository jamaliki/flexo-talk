"""A deck kept as one bundle in Google Drive, open on two computers at once
(``flexo.studio.cloud_bundles``): both save within moments, the service keeps one saving as
the bundle and the other as ``talk (1).flexo`` beside it -- and the studio merges them, slide
by slide, from the version both had, so the folder holds one deck with both computers' edits."""

from __future__ import annotations

import os
import shutil
import zipfile
from pathlib import Path

import pytest
import yaml
from flexo import bundle as B
from flexo.studio import bundles as studio_bundles

from flexo_talk.document import save_document


@pytest.fixture(autouse=True)
def _apart(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("FLEXO_BUNDLES", str(tmp_path / "support" / "bundles"))
    monkeypatch.setenv("XDG_RUNTIME_DIR", str(tmp_path / "run"))


def _deck() -> dict:
    slides = [{"layout": "title", "title": "GBI symposium 2026", "subtitle": "Kiarash Jamali"}]
    for number in range(2, 61):
        slides.append({"title": f"Slide {number}", "body": [{"bullets": [f"Point {number}.{n}" for n in (1, 2, 3)]}]})
    return {"schema_version": 1, "deck": {"id": "talk", "theme": "paper"}, "slides": slides}


def _carried(source: Path, target: Path) -> None:
    partial = target.with_name(f".{target.name}.carrying")
    shutil.copy2(source, partial)
    os.replace(partial, target)


def _drive(computer: str) -> Path:
    drive = Path.home() / "Library" / "CloudStorage" / f"GoogleDrive-{computer}@lab.org"
    folder = drive / "My Drive" / "GBI symposium 2026"
    folder.mkdir(parents=True)
    return folder / "talk.flexo"


def _edited(keeper: studio_bundles.Keeper, change) -> None:
    """The deck as the studio writes it, after ``change``."""

    document = keeper.root / "talk.yaml"
    deck = yaml.safe_load(document.read_text(encoding="utf-8"))
    change(deck)
    save_document(deck, document, previous=document.read_text(encoding="utf-8"))


def _slides(source: Path | studio_bundles.Keeper) -> list[dict]:
    if isinstance(source, studio_bundles.Keeper):
        return yaml.safe_load((source.root / "talk.yaml").read_text(encoding="utf-8"))["slides"]
    with zipfile.ZipFile(source) as archive:
        return yaml.safe_load(archive.read("talk.yaml"))["slides"]


def _added_a_slide_and_sharpened_slide_44(deck: dict) -> None:
    deck["slides"].insert(20, {"title": "New results", "body": [{"bullets": ["Fresh point"]}]})
    bullets = deck["slides"][44]["body"][0]["bullets"]  # (slide 44 of the deck both had)
    bullets[1] = "Point 44.2, sharpened"
    bullets.append("Point 44.4, added")


def _laid_slide_51_out_in_two_columns(deck: dict) -> None:
    slide = deck["slides"][50]
    slide["layout"] = "two-columns"
    slide["left"] = slide.pop("body")
    slide["right"] = [{"text": "What it means"}]


def _merged(slides: list[dict]) -> bool:
    """Whether a deck has both computers' edits, and every other slide as it was."""

    titles = [slide.get("title") for slide in slides]
    slide_44, slide_51 = slides[44], slides[51]
    return (
        len(slides) == 61
        and titles[20] == "New results"
        and titles[44] == "Slide 44"
        and slide_44["body"][0]["bullets"] == ["Point 44.1", "Point 44.2, sharpened", "Point 44.3", "Point 44.4, added"]
        and titles[51] == "Slide 51"
        and slide_51.get("layout") == "two-columns"
        and slide_51["left"] == [{"bullets": ["Point 51.1", "Point 51.2", "Point 51.3"]}]
        and slide_51["right"] == [{"text": "What it means"}]
        and "body" not in slide_51
        and all(slide.get("title") == f"Slide {n}" for slide, n in zip(slides[21:], range(21, 61), strict=True))
    )


def test_a_deck_saved_on_two_computers_at_once_in_google_drive_comes_back_as_one(tmp_path: Path) -> None:
    made = tmp_path / "made" / "talk.yaml"
    made.parent.mkdir()
    save_document(_deck(), made)
    laptop, desktop = _drive("laptop"), _drive("desktop")
    B.pack(made, laptop)
    _carried(laptop, desktop)
    here, there = studio_bundles.opened(laptop), studio_bundles.opened(desktop)

    # On the laptop, a slide added and slide 44's bullets edited; on the desktop, slide 51 laid
    # out in two columns -- both saved within moments of each other.
    _edited(here, _added_a_slide_and_sharpened_slide_44)
    _edited(there, _laid_slide_51_out_in_two_columns)
    assert here.save() and there.save()
    # Google Drive keeps the laptop's as talk.flexo, the desktop's as talk (1).flexo, on both.
    _carried(desktop, laptop.with_name("talk (1).flexo"))
    os.rename(desktop, desktop.with_name("talk (1).flexo"))
    _carried(laptop, desktop)

    there.step(now=100.0)  # the desktop takes the laptop's in: its own edit kept
    assert _merged(_slides(there))
    here.step(now=100.0)  # the laptop merges the copy, saves, and puts the copy away
    assert _merged(_slides(here)) and _merged(_slides(laptop))
    assert not laptop.with_name("talk (1).flexo").exists()
    assert here.notices and here.notices[0].startswith("Merged edits from another computer (talk (1).flexo")

    # Carried back to the desktop: one bundle again, the same deck on both computers.
    _carried(laptop, desktop)
    desktop.with_name("talk (1).flexo").unlink()
    there.step(now=120.0)
    assert _merged(_slides(there)) and not there.save()
    assert _slides(here) == _slides(there) == _slides(desktop)
    assert sorted(path.name for path in laptop.parent.iterdir()) == ["talk.flexo"]


def test_two_merges_of_one_deck_saved_at_once_never_double_a_slide(tmp_path: Path) -> None:
    # Both computers merge the same two savings and save before either sees the other's merge
    # (the other computer gone quiet): Google Drive keeps one merge as the bundle, the other as
    # a copy -- merged from the merge each made, so the slides each added stay one each.
    made = tmp_path / "made" / "talk.yaml"
    made.parent.mkdir()
    save_document(_deck(), made)
    laptop, desktop = _drive("laptop"), _drive("desktop")
    B.pack(made, laptop)
    _carried(laptop, desktop)
    here, there = studio_bundles.opened(laptop), studio_bundles.opened(desktop)
    _edited(here, lambda deck: deck["slides"].insert(10, {"title": "From the laptop"}))
    _edited(there, lambda deck: deck["slides"].insert(40, {"title": "From the desktop"}))
    assert here.save() and there.save()
    _carried(desktop, laptop.with_name("talk (1).flexo"))
    os.rename(desktop, desktop.with_name("talk (1).flexo"))
    _carried(laptop, desktop)
    there.step(now=100.0)
    here.step(now=100.0)
    there.step(now=100.0 + studio_bundles.HOLD + 1)  # (the laptop's merge never came: saved)
    desktop.with_name("talk (1).flexo").unlink()
    # Each goes on editing its merge.
    _edited(here, lambda deck: deck["slides"][1].update(title="Slide 2, retitled on the laptop"))
    _edited(there, lambda deck: deck["slides"][3].update(title="Slide 4, retitled on the desktop"))
    assert here.save() and there.save()
    # Saved at once again: the desktop's merge is the bundle, the laptop's the copy.
    _carried(laptop, desktop.with_name("talk (1).flexo"))
    os.rename(laptop, laptop.with_name("talk (1).flexo"))
    _carried(desktop, laptop)
    here.step(now=200.0)  # (the desktop's merge taken in, the laptop waiting for its own)
    there.step(now=200.0)  # (the laptop's copy merged, saved, put away)
    assert not desktop.with_name("talk (1).flexo").exists()
    _carried(desktop, laptop)
    laptop.with_name("talk (1).flexo").unlink()
    here.step(now=210.0)
    assert not here.save()
    for slides in (_slides(here), _slides(there), _slides(laptop), _slides(desktop)):
        titles = [slide.get("title") for slide in slides]
        assert len(titles) == 62 and titles.count("From the laptop") == 1 and titles.count("From the desktop") == 1
        assert titles[1:4] == ["Slide 2, retitled on the laptop", "Slide 3", "Slide 4, retitled on the desktop"]
