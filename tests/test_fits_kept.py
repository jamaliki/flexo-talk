"""Figures laid out for a slide are kept by what they are laid out from, each file saying which
version of the code laid it out: another version's is not read back, and laid out again it is
replaced in its file; only the most recently used are kept."""

from __future__ import annotations

import os
import time
from pathlib import Path

from flexo import kept_versions

import flexo_talk.compose as compose


def test_a_layout_kept_by_another_version_is_laid_out_again_in_its_place(monkeypatch) -> None:
    monkeypatch.setattr(kept_versions, "_CODE", ["0ld0ld0ld0ld0ld0"])
    compose._FITS.clear()
    key = ("a figure", 1.0)
    compose._store_fit(key, {"svg": "<svg>old</svg>"})
    path = compose._cache_path(key)
    assert path.read_bytes().startswith(b"flexo-kept 0ld0ld0ld0ld0ld0\n")
    compose._FITS.clear()  # (the app started again, updated)
    monkeypatch.setattr(kept_versions, "_CODE", ["11e911e911e911e9"])
    assert compose._cached_fit(key) is None
    compose._store_fit(key, {"svg": "<svg>new</svg>"})
    compose._FITS.clear()
    assert compose._cached_fit(key) == {"svg": "<svg>new</svg>"}
    assert list(path.parent.glob("*.json")) == [path]


def test_laid_out_figures_kept_are_the_most_recently_used(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(compose, "FITS_KEPT", 3)
    folder = tmp_path / "fits"
    folder.mkdir()
    now = time.time()
    for number in range(6):
        made = folder / f"{number}.json"
        made.write_text("{}")
        os.utime(made, (now - 100 + number, now - 100 + number))
    (folder / "half.json.1.2.saving").write_text("{")
    compose._prune_fits(folder)
    assert sorted(item.name for item in folder.iterdir()) == ["3.json", "4.json", "5.json", "half.json.1.2.saving"]
