"""``flexo-talk import``: a PowerPoint or Keynote deck made a new bundle, named as it is, here --
or where ``-o`` says, or a folder with ``--folder`` -- never over what is there unless asked,
never over its source, and what could not be brought across said after."""

from __future__ import annotations

import zipfile
from pathlib import Path

import pytest
from presentations import keynote, powerpoint

from flexo_talk.cli import main


def test_a_deck_is_made_a_bundle_named_as_it_is_here(tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
                                                       capsys: pytest.CaptureFixture) -> None:
    source = powerpoint(tmp_path / "Lab meeting.pptx")
    monkeypatch.chdir(tmp_path)
    assert main(["import", str(source), "--quiet"]) == 0
    made = tmp_path / "Lab meeting.flexo"
    with zipfile.ZipFile(made) as bundle:
        assert "Lab meeting.yaml" in bundle.namelist()
    said = capsys.readouterr().out
    assert "12 slides imported from Lab meeting.pptx." in said
    assert "2 objects became placeholders:" in said
    # Not again over what it made, unless asked.
    assert main(["import", str(source), "--quiet"]) == 1
    assert "is there already" in capsys.readouterr().err
    assert main(["import", str(source), "--quiet", "--force"]) == 0


def test_a_keynote_deck_is_made_a_folder_where_asked(tmp_path: Path) -> None:
    source = keynote(tmp_path / "talk.key")
    # A folder named: made, the deck in it named as it is.
    assert main(["import", str(source), "--folder", "-o", str(tmp_path / "Old talk"), "--quiet"]) == 0
    assert (tmp_path / "Old talk" / "Old talk.yaml").is_file()
    # A folder that is there: the deck's folder made in it.
    (tmp_path / "decks").mkdir()
    assert main(["import", str(source), "--folder", "-o", str(tmp_path / "decks"), "--quiet"]) == 0
    assert (tmp_path / "decks" / "talk" / "talk.yaml").is_file()


def test_what_is_no_deck_is_said_so(tmp_path: Path, capsys: pytest.CaptureFixture) -> None:
    junk = tmp_path / "junk.key"
    junk.write_bytes(b"nothing")
    assert main(["import", str(junk), "-o", str(tmp_path / "out.flexo"), "--quiet"]) == 1
    assert "is not a PowerPoint (.pptx) or Keynote (.key) deck" in capsys.readouterr().err
