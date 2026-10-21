"""Slides copied in one deck and pasted in a deck of another folder bring the files they name
(``flexo_talk.pasting``): each where it was when that is free, once however many slides name it,
numbered beside another file of its name, a figure file with its own files in a folder of their
own when they clash -- and the paste, through the studio, only from a folder a studio has open,
its copies the studio's to take away if nothing uses them."""

from __future__ import annotations

import json
import threading
import urllib.error
import urllib.request
from collections.abc import Iterator
from pathlib import Path

import pytest

from flexo_talk.pasting import brought

FIGURE = """\
figure: {id: model}
nodes:
- {id: a, label: Alpha}
- {id: logo, kind: image, properties: {source: ../pictures/logo.png}}
"""


def _write(path: Path, content: str | bytes) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    if isinstance(content, bytes):
        path.write_bytes(content)
    else:
        path.write_text(content, encoding="utf-8")
    return path


@pytest.fixture
def decks(tmp_path: Path) -> tuple[Path, Path]:
    """Deck A's folder, its pictures, a figure file and a plot; deck B's, empty but for a
    picture of the same name as one of A's, and other bytes."""

    a, b = tmp_path / "a", tmp_path / "b"
    _write(a / "assets/red.png", b"red")
    _write(a / "assets/shared.png", b"A's")
    _write(a / "pictures/logo.png", b"logo")
    _write(a / "figures/model.yaml", FIGURE)
    _write(a / "plots.py", "def loss():\n    return None\n")
    _write(a / "art.pdf", b"%PDF-1.4")
    _write(b / "assets/shared.png", b"B's")
    return a, b


def test_each_file_comes_where_it_was_once_however_many_slides_name_it(decks) -> None:
    a, b = decks
    slides = [
        {"title": "Two", "body": [{"image": "assets/red.png"}]},
        {"title": "Three", "body": [{"image": "assets/red.png"}, {"gallery": ["assets/red.png"]}],
         "people": ["assets/red.png"]},
    ]
    made = brought(slides, a, b)
    assert made["slides"] == slides
    assert made["files"] == [(b / "assets/red.png").resolve()]
    assert (b / "assets/red.png").read_bytes() == b"red"
    # Pasted again, they are there already: nothing written, nothing renamed.
    again = brought(slides, a, b)
    assert again["slides"] == slides and again["files"] == []


def test_a_file_whose_name_is_another_s_here_is_numbered_beside_it(decks) -> None:
    a, b = decks
    slides = [
        {"title": "One", "body": [{"image": "assets/shared.png"}]},
        {"title": "Two", "body": [{"text": "assets/shared.png"}], "background": "assets/shared.png",
         "shapes": [{"kind": "picture", "source": "assets/shared.png", "at": [0, 0]}]},
    ]
    made = brought(slides, a, b)
    assert (b / "assets/shared.png").read_bytes() == b"B's"  # theirs, untouched
    assert (b / "assets/shared-2.png").read_bytes() == b"A's"
    assert made["slides"][0]["body"][0]["image"] == "assets/shared-2.png"
    assert made["slides"][1]["background"] == "assets/shared-2.png"
    assert made["slides"][1]["shapes"][0]["source"] == "assets/shared-2.png"
    # Words that read as a file's name are words.
    assert made["slides"][1]["body"][0]["text"] == "assets/shared.png"
    # A third deck's file of that name too: -3; A's again: -2, written once.
    _write(b / "assets/shared-2.png", b"C's")
    assert brought(slides, a, b)["slides"][0]["body"][0]["image"] == "assets/shared-3.png"
    assert brought(slides, a, b)["files"] == []


def test_a_figure_file_comes_with_the_files_it_names(decks) -> None:
    a, b = decks
    slides = [{"title": "Model", "body": [{"figure": "figures/model.yaml"}, {"plot": "plots.py:loss"}]}]
    made = brought(slides, a, b)
    assert made["slides"] == slides
    assert (b / "figures/model.yaml").read_text() == FIGURE
    assert (b / "pictures/logo.png").read_bytes() == b"logo"
    assert (b / "plots.py").exists()
    # Here another figure file of its name, and a plot's: they come in a folder of their own,
    # laid out as they were, so the names in the figure still find its picture.
    other = b.parent / "c"
    _write(other / "figures/model.yaml", "figure: {id: other}\nnodes: []\n")
    _write(other / "plots.py", "def loss():\n    return 1\n")
    made = brought(slides, a, other)
    block, plot = made["slides"][0]["body"]
    assert block["figure"] == "assets/a/figures/model.yaml"
    assert plot["plot"] == "assets/a/plots.py:loss"
    assert (other / "assets/a/figures/model.yaml").read_text() == FIGURE
    assert (other / "assets/a/pictures/logo.png").read_bytes() == b"logo"
    assert (other / "figures/model.yaml").read_text().startswith("figure: {id: other}")


def test_a_page_of_a_pdf_and_files_outside_or_missing(decks) -> None:
    a, b = decks
    _write(b / "art.pdf", b"other")
    _write(a.parent / "elsewhere.png", b"out")
    slides = [{"title": "T", "body": [{"image": "art.pdf#2"}, {"image": "../elsewhere.png"},
                                     {"image": "gone.png"}, {"image": str(a / "assets/red.png")}]}]
    made = brought(slides, a, b)
    body = made["slides"][0]["body"]
    assert body[0]["image"] == "art-2.pdf#2" and (b / "art-2.pdf").read_bytes() == b"%PDF-1.4"
    # Outside its folder: by its whole path, which finds it from here too.
    assert body[1]["image"] == str(a.parent / "elsewhere.png")
    # Not there, or named by its whole path already: left as named.
    assert body[2]["image"] == "gone.png" and made["missing"] == ["gone.png"]
    assert body[3]["image"] == str(a / "assets/red.png")


def test_slides_pasted_in_their_own_folder_are_as_they_were(decks) -> None:
    a, _ = decks
    slides = [{"title": "Two", "body": [{"image": "assets/shared.png"}]}]
    assert brought(slides, a, a) == {"slides": slides, "files": [], "missing": []}


# -- through the studio --


def _call(url: str, token: str, body: object) -> tuple[int, dict]:
    request = urllib.request.Request(
        url, data=json.dumps(body).encode(), headers={"Content-Type": "application/json", "X-Studio-Token": token}
    )
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    try:
        with opener.open(request) as response:
            return response.status, json.loads(response.read())
    except urllib.error.HTTPError as error:
        return error.code, json.loads(error.read())


@pytest.fixture
def studios(decks, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[list]:
    from flexo.studio.server import start

    monkeypatch.setenv("XDG_RUNTIME_DIR", str(tmp_path / "run"))
    a, b = decks
    for folder in (a, b):
        _write(folder / "talk.yaml", "deck: {}\nslides:\n- title: One\n")
    running = []
    for folder in (a, b):
        server, workspace = start(folder / "talk.yaml", browser=False)
        threading.Thread(target=server.serve_forever, daemon=True).start()
        running.append((server, workspace))
    try:
        yield running
    finally:
        for server, workspace in running:
            workspace.close()
            server.shutdown()
            server.server_close()


def test_the_studio_brings_slides_files_from_an_open_deck_only(studios, decks, tmp_path: Path) -> None:
    (_, _), (server, workspace) = studios
    a, b = decks
    url = f"http://127.0.0.1:{server.server_address[1]}/api/act"
    slides = [{"title": "Two", "body": [{"image": "assets/shared.png"}, {"image": "assets/red.png"}]}]
    asked = {"do": "bring-slides", "from": str(a), "slides": slides}
    status, answer = _call(url, workspace.token, {"file": "talk.yaml", "action": asked})
    assert status == 200, answer
    assert [block["image"] for block in answer["slides"][0]["body"]] == ["assets/shared-2.png", "assets/red.png"]
    assert "uploaded" not in answer
    # The studio's copies: taken away if nothing comes to use them.
    assert {(b / "assets/shared-2.png").resolve(), (b / "assets/red.png").resolve()} <= workspace.uploads
    # A folder no studio has open is not read.
    stranger = tmp_path / "stranger"
    _write(stranger / "assets/secret.png", b"no")
    secret = [{"title": "S", "body": [{"image": "assets/secret.png"}]}]
    asked = {"do": "bring-slides", "from": str(stranger), "slides": secret}
    status, answer = _call(url, workspace.token, {"file": "talk.yaml", "action": asked})
    assert status == 400 and "no longer open" in json.dumps(answer)
    assert not (b / "assets/secret.png").exists()
