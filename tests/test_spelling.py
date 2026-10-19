"""A deck's words for Check Spelling… (``studio/static/spellwords.js``, with deckwords.js and
flexo's finding.js): every field of prose, with what no dictionary knows blanked in place --
code and equations, words between backticks or dollars, links, words with digits -- and the
misspelt words the Mac's dictionary finds, less those the deck knows or were passed over. Run
in Node. And the deck's own words, kept in it (``deck.spelling``)."""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import pytest
from flexo import freeform

from flexo_talk.document import DeckDocumentError, deck_from_document, dump_document, load_document

FINDING = Path(freeform.__file__).parent / "studio" / "static" / "studio" / "finding.js"
STATIC = Path(__file__).parents[1] / "src/flexo_talk/studio/static"


def run(body: str) -> object:
    node = shutil.which("node")
    if node is None:
        pytest.skip("Node is not installed")
    script = (
        f"const F = await import({json.dumps(FINDING.as_uri())});\n"
        f"const D = await import({json.dumps((STATIC / 'deckwords.js').as_uri())});\n"
        f"const S = await import({json.dumps((STATIC / 'spellwords.js').as_uri())});\n"
        f"console.log(JSON.stringify(await (async () => {{ {body} }})()));\n"
    )
    done = subprocess.run([node, "--input-type=module", "-e", script], capture_output=True, text=True, check=True)
    return json.loads(done.stdout.strip().splitlines()[-1])


DECK = {
    "deck": {"id": "talk", "spelling": ["Mechazyme"]},
    "slides": [
        {
            "title": "We work on [enzime design]{accent1}",
            "body": [
                {"bullets": ["Run `mechazyme --fast` on 5KKA", "See https://example.org/enzimes and $k_{cat}$"]},
                {"code": "enzime = fold()"},
                {"math": "E = k_{enzime}"},
                {"mechanism": [{"smiles": "[OH-:1].[CH3:2]Cl", "arrows": ["1 -> 2"], "reagents": "NaOH",
                                "label": "tetrahedrl intermediate"}]},
            ],
            "notes": "Say what Mechazyme does.",
        },
    ],
}


def test_what_is_not_prose_is_blanked_where_it_is() -> None:
    texts = run(f"""
        const fields = D.deckFields({json.dumps(DECK)}, {{ figure: F.figureFields }});
        return S.spellingTexts(fields, F.wordsOf).map((one) => [one.field.name, one.text]);
    """)
    assert texts == [
        ["Title", "We work on enzime design"],
        # (Each blank as long as what it blanks: a word found is where it is in the field.)
        ["List", "Run " + " " * len("mechazyme --fast") + " on " + " " * len("5KKA")],
        ["List", "See " + " " * len("https://example.org/enzimes") + " and " + " " * len("k_{cat}")],
        ["Mechanism", "tetrahedrl intermediate"],
        ["Notes", "Say what Mechazyme does."],
    ]


def test_the_misspelt_words_are_those_the_deck_does_not_know() -> None:
    found = run(f"""
        const fields = D.deckFields({json.dumps(DECK)}, {{ figure: F.figureFields }});
        const texts = S.spellingTexts(fields, F.wordsOf);
        // What the Mac's dictionary would say of each.
        const answers = texts.map((one) => [...one.text.matchAll(/enzime|tetrahedrl|Mechazyme/g)]
          .map((m) => ({{ start: m.index, end: m.index + m[0].length,
                          guesses: m[0] === "enzime" ? ["enzyme"] : [] }})));
        return S.misspellings(texts, answers, {{ known: ["mechazyme"], ignored: ["Tetrahedrl"] }})
          .map((one) => [one.word, one.field.name, one.start, one.end, one.guesses, one.index]);
    """)
    # (Mechazyme the deck knows, whatever its case; tetrahedrl was passed over.)
    assert found == [["enzime", "Title", 11, 17, ["enzyme"], 0]]


def test_a_deck_keeps_its_own_words(tmp_path: Path) -> None:
    path = tmp_path / "talk.yaml"
    path.write_text(dump_document(DECK))
    document = load_document(path)
    assert document["deck"]["spelling"] == ["Mechazyme"]
    deck_from_document(document, tmp_path)
    bad = {**DECK, "deck": {"id": "talk", "spelling": "Mechazyme"}}
    with pytest.raises(DeckDocumentError, match="spelling must be a list of words"):
        deck_from_document(bad, tmp_path)
