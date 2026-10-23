"""While the studio draws, a figure's layout is written to its file on a thread of its own: found
meanwhile as it will be there, and there once written."""

from __future__ import annotations

from pathlib import Path

from flexo_talk import compose


def test_a_layout_written_later_is_found_as_it_will_be_written(tmp_path: Path, monkeypatch) -> None:
    from flexo import kept_versions

    monkeypatch.setenv("FLEXO_TALK_CACHE", str(tmp_path))
    monkeypatch.setattr(kept_versions, "_CODE", ["5007e45007e45007"])
    key = ("a figure written later", 1.0)
    laid = {"svg": "<svg>later</svg>", "ink": [0.0, 0.0, 1.0, 1.0]}
    token = compose.WRITTEN_LATER.set(True)
    try:
        compose._store_fit(key, laid)
        compose._store_fit(("the same figure, kept by another key", 1.0), laid)
    finally:
        compose.WRITTEN_LATER.reset(token)
    compose._FITS.clear()
    assert compose._cached_fit(key) == laid
    compose.written()
    path = compose._cache_path(key)
    assert path.read_bytes().startswith(b"flexo-kept 5007e45007e45007\n")
    compose._FITS.clear()
    assert compose._cached_fit(key) == laid
    assert not compose._WRITING
