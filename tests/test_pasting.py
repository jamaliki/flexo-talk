"""Slides copied in one deck and pasted in a deck of another folder bring the files they name
(``flexo_talk.pasting``): each where it was when that is free, once however many slides name it,
numbered beside another file of its name, a figure file with its own files in a folder of their
own when they clash -- and the paste, through the studio, only from a folder a studio has open,
its copies the studio's to take away if nothing uses them."""

from __future__ import annotations

import json
import threading
import urllib.error
import urllib.parse
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
    assert brought(slides, a, a) == {"slides": slides, "figures": {}, "files": [], "missing": []}


def test_the_deck_s_own_figures_a_slide_shows_come_with_their_files(decks) -> None:
    """A slide showing a figure the deck keeps once ('#pipeline') carries it: its parts' files
    come too, renamed beside another file of their name, and the figure names them so."""

    a, b = decks
    _write(b / "pictures/logo.png", b"B's logo")
    figures = {"pipeline": {"figure": {"id": "pipeline"}, "nodes": [
        {"id": "logo", "kind": "image", "properties": {"source": "pictures/logo.png"}}]}}
    slides = [{"title": "Pipeline", "body": [{"figure": "#pipeline"}]}]
    made = brought(slides, a, b, figures)
    assert made["slides"] == slides
    assert made["figures"]["pipeline"]["nodes"][0]["properties"]["source"] == "pictures/logo-2.png"
    assert (b / "pictures/logo-2.png").read_bytes() == b"logo"
    assert figures["pipeline"]["nodes"][0]["properties"]["source"] == "pictures/logo.png"  # as given


PASTED = Path(__file__).parents[1] / "src/flexo_talk/studio/static/pastedslides.js"


def _node(code: str) -> object:
    """``code`` run in Node with pastedslides.js as ``P`` (the studio's modules it imports read
    from flexo, its notes kept in ``notes``)."""

    import shutil
    import subprocess

    import flexo

    if shutil.which("node") is None:
        pytest.skip("Node is not installed")
    static = Path(flexo.__file__).parent / "studio/static/studio"
    stub = (
        f"export {{ same }} from {json.dumps((static / 'merge.js').as_uri())};"
        "export const toast = (words) => { globalThis.notes.push(String(words)); };"
    )
    source = PASTED.read_text(encoding="utf-8")
    inline = "data:text/javascript," + urllib.parse.quote(stub)
    source = source.replace('"/static/studio/studio.js"', json.dumps(inline))
    source = source.replace('"/static/studio/mixing.js"', json.dumps((static / "mixing.js").as_uri()))
    script = (
        "globalThis.notes = [];\n"
        f"const P = await import({json.dumps('data:text/javascript,' + urllib.parse.quote(source))});\n{code}"
    )
    done = subprocess.run(["node", "--input-type=module", "-e", script], capture_output=True, text=True, check=True)
    return json.loads(done.stdout)


def test_a_copy_carries_the_deck_s_own_figures_it_shows_and_they_are_named_apart_here() -> None:
    made = _node("""
      const pipeline = { figure: { id: "pipeline" }, nodes: [{ id: "a" }] };
      const other = { figure: { id: "pipeline" }, nodes: [{ id: "b" }] };
      const deck = { pipeline, unused: other };
      const block = { what: "block", block: { figure: "#pipeline" } };
      const slides = { what: "slides", slides: [{ body: [{ figure: "#pipeline" }] },
        { left: [{ figure: "#pipeline" }], right: [{ image: "a.png" }] }] };
      const mixed = { what: "mixed", clips: [
        { what: "blocks", blocks: [{ figure: "#pipeline" }, { text: "#pipeline" }] }, { what: "shapes", shapes: [] }] };
      const out = {
        named: [P.figuresNamed(block, deck), P.figuresNamed(slides, deck), P.figuresNamed(mixed, deck),
                P.figuresNamed({ what: "block", block: { figure: "#gone" } }, deck)],
      };
      const carried = { ...slides, figures: { pipeline } };
      // This deck has none of that name: it is added; the very same one: used as it is.
      out.none = P.placedFigures(carried, {});
      out.same = P.placedFigures(carried, { pipeline: structuredClone(pipeline) });
      // Another of its name, and another of the name after: numbered past both, renamed where named.
      out.clash = P.placedFigures(carried, { pipeline: other, "pipeline-2": other });
      out.blocks = P.placedFigures({ ...mixed, figures: { pipeline } }, { pipeline: other });
      console.log(JSON.stringify(out));
    """)
    one = {"pipeline": {"figure": {"id": "pipeline"}, "nodes": [{"id": "a"}]}}
    assert made["named"] == [one, one, one, {}]
    assert made["none"]["add"] == one and made["none"]["clip"]["slides"][0]["body"][0]["figure"] == "#pipeline"
    assert made["same"]["add"] == {} and made["same"]["clip"]["slides"][1]["left"][0]["figure"] == "#pipeline"
    clash = made["clash"]
    assert clash["add"] == {"pipeline-3": one["pipeline"]}
    pasted = clash["clip"]["slides"]
    assert [pasted[0]["body"][0]["figure"], pasted[1]["left"][0]["figure"]] == ["#pipeline-3"] * 2
    assert clash["clip"]["slides"][1]["right"] == [{"image": "a.png"}]
    blocks = made["blocks"]["clip"]["clips"][0]["blocks"]
    assert blocks == [{"figure": "#pipeline-2"}, {"text": "#pipeline"}]  # words are words


def test_objects_and_shapes_copied_from_another_deck_bring_their_files_through_the_studio() -> None:
    made = _node("""
      const asked = [];
      const studio = {
        file: "talk.yaml", folder: () => "", workspace: { info: { folder: "/b" } },
        api: async (route, body) => {
          asked.push(body.action);
          const moved = (value) => JSON.parse(JSON.stringify(value).replaceAll('"shared.png"', '"shared-2.png"'));
          const figures = moved(body.action.figures || {});
          return { slides: moved(body.action.slides), figures, missing: ["gone.png"] };
        },
      };
      const out = {};
      const picture = { image: "shared.png" };
      out.block = await P.broughtClip(studio, { what: "block", block: picture, from: "/a", figures: {} });
      out.logo = await P.broughtClip(studio, { what: "block", block: { image: "shared.png" }, logo: 0, from: "/a" });
      const figures = { f: { nodes: [{ properties: { source: "shared.png" } }] } };
      out.mixed = await P.broughtClip(studio, { what: "mixed", from: "/a", figures, clips: [
        { what: "blocks", blocks: [{ gallery: ["shared.png"] }, { text: "x" }] },
        { what: "shapes", shapes: [{ kind: "picture", source: "shared.png" }] },
        { what: "parts", parts: { nodes: [] } }] });
      out.here = await P.broughtClip(studio, { what: "block", block: { image: "shared.png" }, from: "/b" });
      out.asked = asked.length;
      out.slides = asked[2].slides;
      out.notes = globalThis.notes;
      studio.api = async () => { throw new Error("The deck these slides were copied from is no longer open"); };
      out.failed = await P.broughtClip(studio, { what: "block", block: { image: "shared.png" }, from: "/a" });
      out.notes = globalThis.notes;
      console.log(JSON.stringify(out));
    """)
    assert made["block"]["block"] == {"image": "shared-2.png"} and made["block"]["what"] == "block"
    assert made["logo"]["block"] == {"image": "shared-2.png"} and made["logo"]["logo"] == 0
    clips = made["mixed"]["clips"]
    assert clips[0]["blocks"] == [{"gallery": ["shared-2.png"]}, {"text": "x"}]
    assert clips[1]["shapes"] == [{"kind": "picture", "source": "shared-2.png"}]
    assert clips[2] == {"what": "parts", "parts": {"nodes": []}}
    assert made["mixed"]["figures"]["f"]["nodes"][0]["properties"]["source"] == "shared-2.png"
    # Pasted in a deck of the folder it came from: nothing asked, as it is.
    assert made["here"]["block"] == {"image": "shared.png"} and made["asked"] == 3
    assert made["slides"] == [
        {"body": [{"gallery": ["shared.png"]}, {"text": "x"}]},
        {"shapes": [{"kind": "picture", "source": "shared.png"}]},
    ]
    assert made["failed"]["block"] == {"image": "shared.png"}
    assert any("gone.png" in note for note in made["notes"]) and any("no longer open" in note for note in made["notes"])


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
    node = {"id": "n", "kind": "image", "properties": {"source": "assets/shared.png"}}
    figures = {"f": {"figure": {"id": "f"}, "nodes": [node]}}
    asked = {"do": "bring-slides", "from": str(a), "slides": slides, "figures": figures}
    status, answer = _call(url, workspace.token, {"file": "talk.yaml", "action": asked})
    assert status == 200, answer
    assert answer["figures"]["f"]["nodes"][0]["properties"]["source"] == "assets/shared-2.png"
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
