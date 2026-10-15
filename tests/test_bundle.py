"""A deck as one file (``flexo.bundle``, with ``flexo_talk.bundling``): every file a deck can
name gathered -- through the figure files and Python it names -- what is not there said, and
the deck built straight from its bundle, its Python run only when trusted."""

from __future__ import annotations

import zipfile
from pathlib import Path

import pytest
from flexo import bundle as B

from flexo_talk.cli import main as talk_main
from flexo_talk.studio import DeckKind

PNG = (
    b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01\x08\x02\x00\x00\x00"
    b"\x90wS\xde\x00\x00\x00\x0cIDATx\x9cc\xf8\xcf\xc0\x00\x00\x03\x01\x01\x00\xc9\xfe\x92\xef"
    b"\x00\x00\x00\x00IEND\xaeB`\x82"
)
SVG = (
    '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 10 10">'
    '<rect width="10" height="10" fill="#c0392b"/></svg>'
)

DECK = """\
schema_version: 1
deck:
  id: talk
  theme: look/lab.theme.yaml
  palette: look/colours.yaml
  background: pictures/paper.png
  logos: [pictures/logo.png, pictures/old-logo.png]
slides:
- layout: title
  title: Everything a deck can name
  background: "#1b2a41"
- title: Pictures
  background: accent
  body:
  - image: pictures/photo.png
  - gallery: [pictures/g1.png, {picture: pictures/g2.png, caption: Two}]
  shapes:
  - {kind: picture, at: [10, 10], size: [40, 40], source: assets/drawing-part-1.svg}
  - kind: group
    shapes:
    - {kind: picture, at: [60, 10], size: [40, 40], source: assets/drawing-part-2.png}
- title: Figures
  layout: two-columns
  background: pictures/slide.png
  left:
  - figure: figures/model.yaml
  right:
  - figure:
      figure: {id: inline}
      nodes:
      - {id: protein, kind: structure, properties: {source: structures/protein.cif}}
      - {id: fetched, kind: structure, properties: {source: 1CRN}}
      - {id: reaction, kind: structure, properties: {source: scenes/reaction.json, density: maps/em.map}}
      - {id: loss, kind: plot, properties: {source: plots.py, function: loss, data: data/loss.csv}}
- title: Plots and code
  columns:
  - - plot: plots.py:accuracy
  - - figure: figures/made.py:figure
  - - image: /Library/Desktop Pictures/Somewhere.heic
    - image: ../elsewhere.png
"""


def _write(path: Path, data: str | bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if isinstance(data, bytes):
        path.write_bytes(data)
    else:
        path.write_text(data, encoding="utf-8")


@pytest.fixture
def talk(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """A deck naming every kind of file a deck can name, in its folder."""

    cache = tmp_path / "molsketch"
    _write(cache / "1CRN.cif", "data_1CRN\n")
    monkeypatch.setenv("MOLSKETCH_CACHE", str(cache))
    folder = tmp_path / "talk"
    _write(folder / "talk.yaml", DECK)
    _write(folder / "look/lab.theme.yaml", "theme: {name: lab, base: paper}\nfonts: [fonts/Lab.ttf]\n")
    _write(folder / "look/fonts/Lab.ttf", b"font")
    _write(folder / "look/colours.yaml", "palettes: {Lab: ['#123456']}\n")
    for name in ("paper", "logo", "photo", "g1", "g2", "slide"):
        _write(folder / f"pictures/{name}.png", PNG)
    _write(folder / "assets/drawing-part-1.svg", SVG)
    _write(folder / "assets/drawing-part-2.png", PNG)
    _write(
        folder / "figures/model.yaml",
        "figure: {id: model, theme: ../look/lab.theme.yaml}\nnodes:\n"
        "- {id: art, kind: image, properties: {source: art/glyph.svg}}\n"
        "- {id: protein, kind: structure, properties: {source: ../structures/protein.cif}}\n"
        "shapes:\n- {kind: picture, at: [0, 0], size: [5, 5], source: ../assets/figure-part.png}\n",
    )
    _write(folder / "figures/art/glyph.svg", SVG)
    _write(folder / "assets/figure-part.png", PNG)
    _write(folder / "figures/made.py", "import flexo\n\n\ndef figure():\n    return None\n")
    _write(folder / "structures/protein.cif", "data_PROT\n")
    _write(folder / "scenes/reaction.json", '{"keyframes": []}')
    _write(folder / "maps/em.map", b"MAP")
    _write(
        folder / "plots.py",
        "import style\nfrom pathlib import Path\n\nHERE = Path(__file__).parent\n\n\n"
        'def loss():\n    return HERE / "data" / "loss.csv"\n\n\n'
        'def accuracy():\n    return open("data/accuracy.tsv")\n',
    )
    _write(folder / "style.py", "")
    _write(folder / "data/loss.csv", "0,1\n")
    _write(folder / "data/accuracy.tsv", "0\t1\n")
    _write(folder / "unrelated.txt", "not named")
    return folder / "talk.yaml"


def test_a_deck_brings_every_file_it_names_and_those_they_name(talk: Path) -> None:
    gathered = B.gather(talk)
    assert gathered.kind == "deck"
    assert sorted(gathered.files) == [
        ".flexo/pdb/1CRN.cif",
        "assets/drawing-part-1.svg",
        "assets/drawing-part-2.png",
        "assets/figure-part.png",  # a picture among a figure file's shapes
        "data/accuracy.tsv",  # what a plot's function names
        "data/loss.csv",
        "figures/art/glyph.svg",  # a figure file's own pictures, from its folder
        "figures/made.py",
        "figures/model.yaml",
        "look/colours.yaml",
        "look/fonts/Lab.ttf",  # the theme's fonts
        "look/lab.theme.yaml",
        "maps/em.map",
        "pictures/g1.png",
        "pictures/g2.png",
        "pictures/logo.png",
        "pictures/paper.png",
        "pictures/photo.png",
        "pictures/slide.png",
        "plots.py",
        "scenes/reaction.json",
        "structures/protein.cif",
        "style.py",  # imported by the plots
        "talk.yaml",
    ]
    assert [(item.name, item.why, item.where) for item in gathered.left] == [
        ("pictures/old-logo.png", "missing", "deck.logos[1]"),
        ("/Library/Desktop Pictures/Somewhere.heic", "outside", "slides[3].columns[2][0] (image)"),
        ("../elsewhere.png", "outside", "slides[3].columns[2][1] (image)"),
    ]


def test_the_deck_kind_says_what_a_deck_names() -> None:
    names = [ref.name for ref in DeckKind().references({"slides": [{"body": [{"image": "a.png"}]}]}, Path("."))]
    assert names == ["a.png"]


def test_a_deck_unpacks_from_its_bundle_as_it_was(talk: Path, tmp_path: Path) -> None:
    made = B.pack(talk)
    assert made.about["kind"] == "deck" and made.about["missing"][0]["name"] == "pictures/old-logo.png"
    out = tmp_path / "out"
    B.unpack(made.path, out)
    for name, source in made.gathered.files.items():
        assert (out / name).read_bytes() == source.read_bytes(), name


def test_a_deck_builds_straight_from_its_bundle(tmp_path: Path, capsys) -> None:
    folder = tmp_path / "small"
    _write(folder / "pictures/photo.png", PNG)
    _write(folder / "plots.py", "def loss():\n    import matplotlib.pyplot as plt\n\n"
           "    figure, axes = plt.subplots()\n    axes.plot([0, 1], [1, 0])\n    return figure\n")
    _write(folder / "talk.yaml", "deck: {id: small}\nslides:\n- title: A picture\n  body:\n"
           "  - image: pictures/photo.png\n- title: A plot\n  body:\n  - plot: plots.py:loss\n")
    made = B.pack(folder / "talk.yaml", tmp_path / "small.flexo")
    out = tmp_path / "build"
    # Its Python is someone else's until its person says they trust it.
    assert talk_main(["build", str(made.path), "-o", str(out), "--formats", "pdf"]) == 1
    assert "--trust" in capsys.readouterr().err and not out.exists()
    assert talk_main(["build", str(made.path), "-o", str(out), "--formats", "pdf", "--trust"]) == 0
    assert (out / "small.pdf").read_bytes().startswith(b"%PDF")
    # One with no Python builds without being trusted.
    (folder / "talk.yaml").write_text(
        "deck: {id: plain}\nslides:\n- title: A picture\n  body:\n  - image: pictures/photo.png\n", encoding="utf-8"
    )
    made = B.pack(folder / "talk.yaml", tmp_path / "plain.flexo")
    assert talk_main(["build", str(made.path), "-o", str(out), "--formats", "pdf"]) == 0
    with zipfile.ZipFile(made.path) as archive:
        assert "plots.py" not in archive.namelist()
