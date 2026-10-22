"""A figure edited on a slide in the studio: one request, sent as the edit and the version the
page has, kept and drawn as it is made, answered with what changed and the slide drawn -- at
its best at once where the layout it has is its best, and what would make it larger left to
be weighed once it is shown."""

from __future__ import annotations

import itertools
import json
import threading
import urllib.request
from collections.abc import Iterator
from pathlib import Path

import pytest
import yaml
from flexo.studio.server import start

OPENER = urllib.request.build_opener(urllib.request.ProxyHandler({}))
AT = {"slide": 0, "region": "body", "index": 0}
HINTS = {"focus": 0, "client": "page-1"}


def _call(url: str, token: str, body: object = None) -> dict:
    data = None if body is None else json.dumps(body).encode()
    headers = {"Content-Type": "application/json", "X-Studio-Token": token}
    with OPENER.open(urllib.request.Request(url, data=data, headers=headers)) as response:
        return json.loads(response.read())


@pytest.fixture
def studio(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator:
    monkeypatch.setenv("FLEXO_TALK_CACHE", "0")
    monkeypatch.setenv("XDG_RUNTIME_DIR", str(tmp_path / "run"))
    servers = []

    def served(figure: dict):
        folder = tmp_path / f"talk{len(servers)}"
        folder.mkdir()
        deck = {"deck": {"id": "edits"}, "slides": [{"title": "Figure", "body": [{"figure": figure}]}]}
        (folder / "talk.yaml").write_text(yaml.safe_dump(deck))
        server, workspace = start(folder / "talk.yaml", browser=False)
        threading.Thread(target=server.serve_forever, daemon=True).start()
        servers.append((server, workspace))
        return f"http://127.0.0.1:{server.server_address[1]}", workspace

    yield served
    for server, workspace in servers:
        workspace.close()
        server.shutdown()
        server.server_close()


def _edit(url: str, token: str, opened: dict, page: dict, edit: dict) -> dict:
    body = {
        "file": "talk.yaml",
        "kind": "deck",
        "base": opened["version"],
        "instance": opened["instance"],
        "client": "page-1",
        "who": {"id": "ada", "name": "Ada"},
        "commit": True,
        "action": {"do": "figure", "at": AT, "edit": edit},
        "draw": {"version": 2, "known": {page["id"]: page["hash"]}, "hints": HINTS},
    }
    return _call(f"{url}/api/act", token, body)


def _opened(url: str, token: str) -> tuple[dict, dict]:
    opened = _call(f"{url}/api/open?file=talk.yaml", token)
    body = {"file": "talk.yaml", "document": opened["document"], "version": 1, "known": {}, "hints": HINTS}
    (page,) = _call(f"{url}/api/draw", token, body)["pages"]
    return opened, page


def test_a_figure_edited_on_a_slide_is_kept_and_drawn_at_its_best_in_one_request(studio) -> None:
    # (Two steps, as large as words on the slide may be: no other way of laying them out could
    # set them larger.)
    figure = {"figure": {"id": "steps"}, "nodes": [{"id": "read", "label": "Read"}, {"id": "align", "label": "Align"}]}
    url, workspace = studio(figure)
    opened, page = _opened(url, workspace.token)
    edit = {"do": "update", "target": {"type": "node", "id": "align"}, "values": {"label": "Align reads"}}
    answer = _edit(url, workspace.token, opened, page, edit)
    doc = workspace.open("talk.yaml")
    # Kept at once, and answered with what changed alone, not the deck.
    assert "document" not in answer and answer["version"] == doc.version == opened["version"] + 1
    assert [path for path, *_ in answer["delta"]] == [["slides", 0, "body", 0, "figure", "nodes", 1, "label"]]
    assert doc.document["slides"][0]["body"][0]["figure"]["nodes"][1]["label"] == "Align reads"
    # Drawn with it, in full and at its best: nothing to settle, nothing more to ask for.
    (shown,) = answer["drawing"]["pages"]
    assert "Align reads" in shown["svg"]
    assert answer["drawing"]["info"]["unsettled"] is False and answer["drawing"]["info"]["weighing"] is False
    settled = _call(
        f"{url}/api/draw",
        workspace.token,
        {
            "file": "talk.yaml",
            "base": doc.version,
            "instance": opened["instance"],
            "version": 3,
            "known": {page["id"]: shown["hash"]},
            "hints": {**HINTS, "settle": True},
        },
    )
    assert "svg" not in settled["pages"][0]


def test_what_would_make_a_figure_edited_larger_is_weighed_once_it_is_shown(studio, monkeypatch) -> None:
    import flexo

    # A long row arranged by hand (its last step under the one before), drawn small: turning it
    # would set its words larger.
    steps = [f"n{index}" for index in range(9)]
    figure = {
        "figure": {"id": "row"},
        "nodes": [{"id": step, "label": f"Step number {index}"} for index, step in enumerate(steps)],
        "edges": [{"from": a, "to": b} for a, b in itertools.pairwise(steps)],
        "groups": [
            {"id": "root", "layout": {"kind": "column"}, "role": "canvas", "children": ["line", "n8"]},
            {"id": "line", "layout": {"kind": "row"}, "role": "layout", "children": steps[:8]},
        ],
    }
    url, workspace = studio(figure)
    token = workspace.token
    opened, page = _opened(url, token)
    tried = []
    real = flexo.fit_in_box
    monkeypatch.setattr(flexo, "fit_in_box", lambda *a, **k: tried.append(k.get("turn")) or real(*a, **k))
    edit = {"do": "update", "target": {"type": "node", "id": "n3"}, "values": {"label": "Step four"}}
    answer = _edit(url, token, opened, page, edit)
    (shown,) = answer["drawing"]["pages"]
    assert "Step four" in shown["svg"] and answer["drawing"]["info"]["unsettled"] is True
    # Settled, it is laid out every way it may be -- not turned, to say whether turning would
    # set it larger: that is weighed once the slide is shown.
    version = workspace.open("talk.yaml").version
    asked = {"file": "talk.yaml", "base": version, "instance": opened["instance"], "known": {page["id"]: shown["hash"]}}
    settled = _call(f"{url}/api/draw", token, {**asked, "version": 3, "hints": {**HINTS, "settle": True}})
    assert True not in tried and settled["info"]["unsettled"] is False and settled["info"]["weighing"] is True
    hashed = settled["pages"][0]["hash"]
    weighed = _call(
        f"{url}/api/draw",
        token,
        {**asked, "version": 4, "known": {page["id"]: hashed}, "hints": {**HINTS, "settle": True, "weigh": True}},
    )
    # The slide as it was; what is said of it, new.
    assert True in tried and "svg" not in weighed["pages"][0] and weighed["info"]["weighing"] is False
    assert any(message["code"] == "figure.small.turn" for message in weighed["messages"])
