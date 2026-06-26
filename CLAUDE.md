# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

`edit` is a nano/pico-style terminal text editor written in pure Python using `curses`. The entire implementation lives in a single file, [edit.py](edit.py) (one `Editor` class).

## Commands

- Run: `python edit.py [filename]` (no filename opens an empty unnamed buffer)
- Install deps: `pip install -r requirements.txt` (only pulls `windows-curses` on Windows, since `curses` is stdlib on Linux/macOS)
- Build a standalone executable: `pyinstaller edit.spec` (produces `dist/edit`)
- There are no tests, linter, or CI config in this repo.

## Architecture

Everything is one `Editor` class in [edit.py](edit.py) driven by `curses.wrapper(main, filename)`:

- **Buffer model**: `self.lines` is a plain list of strings (no rope/gap buffer). Cursor position is `(self.cy, self.cx)` — row/col into that list. `self.top` is the first visible buffer row, used for scrolling.
- **Main loop** (`run`): draw → blocking `getch()` → `handle_key(ch)` → repeat until `quit_pending`.
- **Input dispatch** (`handle_key`): a single long if/elif chain matching curses key constants and `curses.ascii.ctrl(...)` codes. Add new keybindings here.
- **Selection**: `self.sel_anchor` holds the `(y, x)` anchor when a Shift+Arrow selection is active; `None` means no selection. `selection_range()` normalizes anchor/cursor into ordered `(start, end)`, used by `draw_line` (highlighting), `selected_text`, and `delete_selection`.
- **Clipboard**: `self.clipboard` is an in-process string (not the OS clipboard). Multi-line cut/copy/paste joins/splits on `"\n"`.
- **Rendering** (`draw`): redraws the whole screen each loop iteration — title bar (row 0), buffer rows, status/message bar (last row). No incremental/diff rendering.
- **Mouse**: `handle_mouse` reads `curses.getmouse()` for click-to-position and scroll-wheel (`BUTTON4_PRESSED`/`BUTTON5_PRESSED`) cursor movement.
- **Prompts** (`prompt`): a minimal blocking single-line input reader on the status bar, reused for Save-As filename, search term, and the "save modified buffer?" confirmation.

When extending behavior (new keybinding, new editing command), follow the existing pattern: add a branch in `handle_key`, implement the action as an `Editor` method, and set `self.dirty = True` if it mutates the buffer.
