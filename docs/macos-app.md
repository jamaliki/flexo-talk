# Flexo Studio as a macOS app

A brief for whoever builds it. The goal is one double-clickable app, Flexo Studio, that
edits figures, decks and themes with no terminal and no Python installed. The studio
already does all of this in a browser; the app wraps it.

## Getting the code

Two repositories, side by side (flexo-talk depends on flexo through the uv source
`../flexo`). The newest work is on `claude/flexo-talk-gui-design-4b2djm` in both;
`main` is behind.

```
git clone https://github.com/jamaliki/flexo.git
git clone https://github.com/jamaliki/flexo-talk.git
cd flexo && git checkout claude/flexo-talk-gui-design-4b2djm && uv sync --all-groups --all-extras
cd ../flexo-talk && git checkout claude/flexo-talk-gui-design-4b2djm && uv sync --all-groups
uv run flexo studio examples/            # opens the studio in a browser
uv run pytest                            # in each repository
```

A YAML deck to try: `uv run flexo-talk convert examples/journal_club.py`.

## How the studio works now

- `flexo/src/flexo/studio/server.py`: a standard-library `ThreadingHTTPServer` on
  127.0.0.1. `start(target, port=0, kind=None, browser=True)` returns
  `(server, workspace)` without serving; call `server.serve_forever()` in a thread.
  `serve()` does both and prints the address; `main()` is `flexo studio`. Every API call
  carries a token the page is given when it loads, and the Host header is checked.
- `workspace.py`: the open folder, its documents, undo, and server-sent events to every
  open page. `sessions.py` records running studios under the user cache folder so
  `flexo studio mcp` lets an agent (Claude Code) join one.
- Kinds: figure (`figure_kind.py`, with `figure_edit.py` and `figure_parts.py` for the
  visual editor), theme (`theme_kind.py`), and deck, which flexo-talk adds through the
  `flexo.studio` entry point (`flexo-talk/src/flexo_talk/studio/`). Entry points are read
  from installed package metadata, so a bundler must keep the `.dist-info` folders.
- Pages: `static/studio/` (the shell, `session.js`), `static/figure/`, `static/theme/`,
  and flexo-talk's `studio/static/`. Plain ES modules, no build step.
- Exports are written into the folder beside the document, then offered as a link to
  `/api/raw?...&download=1`. A WKWebView does not download by itself, so the app must
  handle this (see below).
- The assistant (`assistant.py`) calls the Anthropic API with `ANTHROPIC_API_KEY` or
  `ant auth login` credentials; it is optional (`flexo[assistant]`).
- `tests/unit/test_studio.py` starts a server in-process; copy its pattern for app tests.

## What must be bundled

Python 3.12+ and: uharfbuzz, resvg-py, fonttools, jsonschema, pyyaml, ruamel.yaml, lxml,
python-pptx, matplotlib (flexo-talk's plots), anthropic, gemmi (structures), and
molsketch (molecules, which pulls in skia-python, mini-racer and numpy). mini-racer
embeds V8, which needs the JIT entitlement under the hardened runtime. Expect an app
of roughly 300 MB; molecules is the largest part and could become a separate download.

## Recommended architecture

Start with pywebview: a Python process that runs the studio server on a thread and
shows the page in a native WKWebView window, packaged with PyInstaller or Briefcase.
This reuses everything and keeps `flexo studio` working in a browser unchanged. If
pywebview gets in the way (menus, document handling, updates), move to a small Swift
app with a WKWebView that launches a bundled python-build-standalone interpreter
running `python -m flexo.studio.server <folder> --port N --no-browser`. Decide after the
spike, not before.

## Work, in order

1. Spike: an unsigned `.app` that opens a folder, edits a figure and a deck, and exports
   PDF, PPTX and PNG. Check every native wheel loads from inside the bundle.
2. Exports and file pickers through native dialogs: intercept the download link (or add
   a small bridge the page calls when present) and show an NSSavePanel; "Open Folder"
   through NSOpenPanel.
3. A proper Mac app: menu bar with the usual shortcuts wired to the page's commands,
   Open Recent, one window per folder, and quitting stops the server and unregisters
   the session. Kinds are recognised by content, not extension (every kind has a
   `claims` method), so file associations need a choice: claim `.yaml`/`.json` as an
   editor that is not the default, or introduce extensions.
4. The API key in the Keychain, set from a preferences window, passed to the server's
   environment.
5. Signing: codesign every Mach-O inside-out with the hardened runtime and entitlements
   (`com.apple.security.cs.allow-jit` for V8; add others only if a check fails),
   notarize with `notarytool`, staple, ship a DMG.
6. CI: a GitHub Actions macOS workflow that builds, signs and notarizes on tag. Apple
   Silicon first; decide on Intel (universal2 or a second build) later.
7. Updates with Sparkle.

## Conventions

- Tests with pytest; ruff with line length 100 in flexo and 120 in flexo-talk.
- Plain English in identifiers and comments; match the surrounding code.
- The browser studio must keep working; the app is another way to open it.
- App packaging code lives in the `flexo-studio` repository.

## Checking it works

Open the app from Finder on a user account with no Python or Homebrew. Then
`codesign --verify --deep --strict --verbose=2 "Flexo Studio.app"` and
`spctl -a -vv "Flexo Studio.app"` must pass, and a figure, a deck and a theme must each
edit, undo and export.

## Decisions

Answered by the owner on 30 September 2026:

- No Apple Developer ID yet: builds stay ad-hoc signed until there is one.
- The app is Flexo Studio, with a placeholder icon for now.
- It ships as a direct download (DMG), not through the App Store.
- macOS 13 and later, Apple Silicon only.
- The packaging code lives in its own repository, `flexo-studio`, beside these two.

Step 1, the spike, is done: see `flexo-studio/docs/spike.md`. Both PyInstaller and
Briefcase builds open a folder, edit, undo and export a figure, a deck and a theme, with
every native library loading from inside the bundle. The recommendation is to stay with
pywebview in one Python process (not the Swift shell) and package with Briefcase.
