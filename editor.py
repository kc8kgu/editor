#!/usr/bin/env python3
"""Editor - a nano / pico-style terminal text editor."""

import curses
import curses.ascii
import os
import sys


class Editor:
    def __init__(self, stdscr, filename):
        self.stdscr = stdscr
        self.filename = filename
        self.lines = [""]
        self.cy = 0          # cursor row in buffer
        self.cx = 0          # cursor col in buffer
        self.top = 0         # first visible buffer row
        self.dirty = False
        self.message = ""
        self.quit_pending = False
        self.clipboard = None
        self.clipboard_is_line = False  # True if clipboard holds a whole cut/copied line
        self.sel_anchor = None  # (y, x) selection anchor, or None if no selection

        if filename and os.path.exists(filename):
            with open(filename, "rb") as f:
                raw = f.read()
            try:
                text = raw.decode("utf-8")
            except UnicodeDecodeError:
                text = raw.decode("utf-8", errors="replace")
                self.message = f"Warning: {filename} is not valid UTF-8; invalid bytes were replaced"
            self.lines = text.split("\n") if text else [""]

        curses.curs_set(1)
        curses.raw()
        stdscr.keypad(True)
        curses.mousemask(curses.ALL_MOUSE_EVENTS)

        self.title_attr = curses.A_REVERSE
        self.status_attr = curses.A_REVERSE
        self.sel_attr = curses.A_REVERSE
        if curses.has_colors():
            curses.start_color()
            curses.init_pair(1, curses.COLOR_WHITE, curses.COLOR_BLUE)
            curses.init_pair(2, curses.COLOR_BLACK, curses.COLOR_YELLOW)
            self.title_attr = curses.color_pair(1)
            self.status_attr = curses.color_pair(1)
            self.sel_attr = curses.color_pair(2)

    @property
    def rows(self):
        return self.stdscr.getmaxyx()[0] - 2  # leave room for title + status

    @property
    def cols(self):
        return self.stdscr.getmaxyx()[1]

    def run(self):
        while True:
            self.draw()
            try:
                ch = self.stdscr.get_wch()
            except curses.error:
                continue
            self.handle_key(ch)
            if self.quit_pending:
                return

    def draw(self):
        self.stdscr.erase()
        maxy, maxx = self.stdscr.getmaxyx()

        path = os.path.abspath(self.filename) if self.filename else "[No Name]"
        title = f" editor  -  {path}{' *' if self.dirty else ''} "
        self.stdscr.addnstr(0, 0, title.center(maxx), maxx - 1, self.title_attr)

        self.scroll()
        sel = self.selection_range()
        for i in range(self.rows):
            lineno = self.top + i
            if lineno < len(self.lines):
                self.draw_line(i + 1, lineno, self.lines[lineno], sel, maxx)

        status = self.message or "^Q Quit  ^S Save  ^F Search  ^X Cut  ^C Copy  ^V Paste"
        view_end = min(self.top + self.rows, len(self.lines))
        position = f"Ln {self.cy + 1}/{len(self.lines)}, Col {self.cx + 1}  [{self.top + 1}-{view_end}]"
        width = maxx - 1
        status = status[:width]
        pad = width - len(status) - len(position)
        if pad >= 1:
            status = status + " " * pad + position
        else:
            status = status.ljust(width)
        self.stdscr.addnstr(maxy - 1, 0, status, width, self.status_attr)

        screen_y = self.cy - self.top + 1
        screen_x = min(self.cx, maxx - 1)
        self.stdscr.move(max(0, min(screen_y, maxy - 1)), max(0, screen_x))
        self.stdscr.refresh()

    def draw_line(self, screen_row, lineno, text, sel, maxx):
        width = maxx - 1
        if sel is None:
            self.stdscr.addnstr(screen_row, 0, text, width)
            return
        (sy, sx), (ey, ex) = sel
        if lineno < sy or lineno > ey:
            self.stdscr.addnstr(screen_row, 0, text, width)
            return
        start = sx if lineno == sy else 0
        end = ex if lineno == ey else len(text)
        before, middle, after = text[:start], text[start:end], text[end:]
        x = 0
        if before:
            self.stdscr.addnstr(screen_row, x, before, width)
            x += len(before)
        if middle and x < width:
            self.stdscr.addnstr(screen_row, x, middle, width - x, self.sel_attr)
            x += len(middle)
        elif not middle and lineno != ey and x < width:
            # selection spans the line break; show a highlighted blank cell
            self.stdscr.addnstr(screen_row, x, " ", width - x, self.sel_attr)
            x += 1
        if after and x < width:
            self.stdscr.addnstr(screen_row, x, after, width - x)

    def selection_range(self):
        if self.sel_anchor is None:
            return None
        a = self.sel_anchor
        b = (self.cy, self.cx)
        return (a, b) if a <= b else (b, a)

    def selected_text(self):
        sel = self.selection_range()
        if sel is None:
            return ""
        (sy, sx), (ey, ex) = sel
        if sy == ey:
            return self.lines[sy][sx:ex]
        parts = [self.lines[sy][sx:]]
        parts.extend(self.lines[sy + 1 : ey])
        parts.append(self.lines[ey][:ex])
        return "\n".join(parts)

    def delete_selection(self):
        sel = self.selection_range()
        if sel is None:
            return False
        (sy, sx), (ey, ex) = sel
        self.lines[sy] = self.lines[sy][:sx] + self.lines[ey][ex:]
        if ey > sy:
            del self.lines[sy + 1 : ey + 1]
        self.cy, self.cx = sy, sx
        self.sel_anchor = None
        self.dirty = True
        return True

    def scroll(self):
        if self.cy < self.top:
            self.top = self.cy
        elif self.cy >= self.top + self.rows:
            self.top = self.cy - self.rows + 1

    def handle_key(self, ch):
        self.message = ""
        code = ord(ch) if isinstance(ch, str) else ch

        if code == curses.KEY_RESIZE:
            return
        elif code == curses.KEY_MOUSE:
            self.handle_mouse()
        elif code in (curses.KEY_UP,):
            self.sel_anchor = None
            self.move_cursor(-1, 0)
        elif code in (curses.KEY_DOWN,):
            self.sel_anchor = None
            self.move_cursor(1, 0)
        elif code in (curses.KEY_LEFT,):
            self.sel_anchor = None
            self.move_cursor(0, -1)
        elif code in (curses.KEY_RIGHT,):
            self.sel_anchor = None
            self.move_cursor(0, 1)
        elif code in (getattr(curses, "KEY_SR", None), getattr(curses, "KEY_SUP", None), 547):  # shift+up
            self.sel_anchor = self.sel_anchor or (self.cy, self.cx)
            self.move_cursor(-1, 0)
        elif code in (getattr(curses, "KEY_SF", None), getattr(curses, "KEY_SDOWN", None), 548):  # shift+down
            self.sel_anchor = self.sel_anchor or (self.cy, self.cx)
            self.move_cursor(1, 0)
        elif code == curses.KEY_SLEFT:  # shift+left
            self.sel_anchor = self.sel_anchor or (self.cy, self.cx)
            self.move_cursor(0, -1)
        elif code == curses.KEY_SRIGHT:  # shift+right
            self.sel_anchor = self.sel_anchor or (self.cy, self.cx)
            self.move_cursor(0, 1)
        elif code == curses.KEY_HOME:
            self.sel_anchor = None
            self.cx = 0
        elif code == curses.KEY_END:
            self.sel_anchor = None
            self.cx = len(self.lines[self.cy])
        elif code == curses.KEY_PPAGE:
            self.sel_anchor = None
            self.move_cursor(-self.rows, 0)
        elif code == curses.KEY_NPAGE:
            self.sel_anchor = None
            self.move_cursor(self.rows, 0)
        elif code == curses.KEY_SHOME:  # shift+home
            self.sel_anchor = self.sel_anchor or (self.cy, self.cx)
            self.cx = 0
        elif code == curses.KEY_SEND:  # shift+end
            self.sel_anchor = self.sel_anchor or (self.cy, self.cx)
            self.cx = len(self.lines[self.cy])
        elif code == curses.KEY_SPREVIOUS:  # shift+page up
            self.sel_anchor = self.sel_anchor or (self.cy, self.cx)
            self.move_cursor(-self.rows, 0)
        elif code == curses.KEY_SNEXT:  # shift+page down
            self.sel_anchor = self.sel_anchor or (self.cy, self.cx)
            self.move_cursor(self.rows, 0)
        elif code in (curses.KEY_BACKSPACE, curses.ascii.BS, curses.ascii.DEL, 127):
            self.backspace()
        elif code == curses.KEY_DC:
            self.delete_forward()
        elif code in (curses.ascii.CR, curses.ascii.NL, 10, 13):
            self.newline()
        elif code == curses.ascii.ctrl(ord("q")):  # ^Q exit
            self.exit()
        elif code == curses.ascii.ctrl(ord("d")):  # ^D exit
            self.exit()
        elif code == curses.ascii.ctrl(ord("s")):  # ^S save
            self.save()
        elif code == curses.ascii.ctrl(ord("g")):  # ^G help
            self.message = "^Q Quit ^S Save  ^F Search  ^X Cut  ^C Copy  ^V Paste  Shift+Arrows Select"
        elif code == curses.ascii.ctrl(ord("f")):  # ^F search
            self.search()
        elif code == curses.ascii.ctrl(ord("x")):  # ^X cut line
            self.cut_line()
        elif code == curses.ascii.ctrl(ord("c")):  # ^C copy line
            self.copy_line()
        elif code == curses.ascii.ctrl(ord("v")):  # ^V paste
            self.paste()
        elif code == curses.ascii.ESC:  # cancel selection
            self.sel_anchor = None
        elif isinstance(ch, str) and code >= 32:
            self.insert(ch)

    def move_cursor(self, dy, dx):
        if dy:
            self.cy = max(0, min(len(self.lines) - 1, self.cy + dy))
            self.cx = min(self.cx, len(self.lines[self.cy]))
        if dx:
            self.cx += dx
            if self.cx < 0:
                if self.cy > 0:
                    self.cy -= 1
                    self.cx = len(self.lines[self.cy])
                else:
                    self.cx = 0
            elif self.cx > len(self.lines[self.cy]):
                if self.cy < len(self.lines) - 1:
                    self.cy += 1
                    self.cx = 0
                else:
                    self.cx = len(self.lines[self.cy])

    def handle_mouse(self):
        try:
            _, mx, my, _, bstate = curses.getmouse()
        except curses.error:
            return

        button4_pressed = getattr(curses, "BUTTON4_PRESSED", 0x00080000)
        button5_pressed = getattr(curses, "BUTTON5_PRESSED", 0x02000000)

        if bstate & (curses.BUTTON1_PRESSED | curses.BUTTON1_CLICKED):
            self.click_to_position(my, mx)
        elif bstate & button4_pressed:
            self.move_cursor(-3, 0)
        elif bstate & button5_pressed:
            self.move_cursor(3, 0)

    def click_to_position(self, my, mx):
        if my < 1 or my > self.rows:
            return
        self.sel_anchor = None
        row = self.top + my - 1
        row = max(0, min(len(self.lines) - 1, row))
        self.cy = row
        self.cx = max(0, min(mx, len(self.lines[row])))

    def insert(self, ch):
        self.delete_selection()
        line = self.lines[self.cy]
        self.lines[self.cy] = line[: self.cx] + ch + line[self.cx :]
        self.cx += 1
        self.dirty = True

    def newline(self):
        self.delete_selection()
        line = self.lines[self.cy]
        rest = line[self.cx :]
        self.lines[self.cy] = line[: self.cx]
        self.lines.insert(self.cy + 1, rest)
        self.cy += 1
        self.cx = 0
        self.dirty = True

    def backspace(self):
        if self.delete_selection():
            return
        if self.cx > 0:
            line = self.lines[self.cy]
            self.lines[self.cy] = line[: self.cx - 1] + line[self.cx :]
            self.cx -= 1
            self.dirty = True
        elif self.cy > 0:
            prev_len = len(self.lines[self.cy - 1])
            self.lines[self.cy - 1] += self.lines[self.cy]
            del self.lines[self.cy]
            self.cy -= 1
            self.cx = prev_len
            self.dirty = True

    def delete_forward(self):
        if self.delete_selection():
            return
        line = self.lines[self.cy]
        if self.cx < len(line):
            self.lines[self.cy] = line[: self.cx] + line[self.cx + 1 :]
            self.dirty = True
        elif self.cy < len(self.lines) - 1:
            self.lines[self.cy] += self.lines[self.cy + 1]
            del self.lines[self.cy + 1]
            self.dirty = True

    def cut_line(self):
        if self.sel_anchor is not None:
            self.clipboard = self.selected_text()
            self.clipboard_is_line = False
            self.delete_selection()
            self.message = "Cut selection"
            return
        self.clipboard = self.lines[self.cy]
        self.clipboard_is_line = True
        if len(self.lines) > 1:
            del self.lines[self.cy]
            self.cy = min(self.cy, len(self.lines) - 1)
        else:
            self.lines[self.cy] = ""
        self.cx = 0
        self.dirty = True
        self.message = "Cut line"

    def copy_line(self):
        if self.sel_anchor is not None:
            self.clipboard = self.selected_text()
            self.clipboard_is_line = False
            self.sel_anchor = None
            self.message = "Copied selection"
            return
        self.clipboard = self.lines[self.cy]
        self.clipboard_is_line = True
        self.message = "Copied line"

    def paste(self):
        if self.clipboard is None:
            self.message = "Clipboard empty"
            return
        self.delete_selection()
        if self.clipboard_is_line:
            self.lines.insert(self.cy, self.clipboard)
            self.cy += 1
            self.cx = 0
        else:
            parts = self.clipboard.split("\n")
            line = self.lines[self.cy]
            tail = line[self.cx :]
            self.lines[self.cy] = line[: self.cx] + parts[0]
            self.lines[self.cy + 1 : self.cy + 1] = parts[1:]
            self.cy += len(parts) - 1
            self.cx = len(parts[-1])
            self.lines[self.cy] += tail
        self.dirty = True
        self.message = "Pasted"

    def prompt(self, label):
        maxy, maxx = self.stdscr.getmaxyx()
        curses.curs_set(1)
        buf = ""
        while True:
            self.stdscr.addnstr(maxy - 1, 0, (label + buf).ljust(maxx), maxx - 1, curses.A_REVERSE)
            self.stdscr.move(maxy - 1, min(len(label) + len(buf), maxx - 1))
            self.stdscr.refresh()
            try:
                ch = self.stdscr.get_wch()
            except curses.error:
                continue
            code = ord(ch) if isinstance(ch, str) else ch
            if code in (curses.ascii.CR, curses.ascii.NL, 10, 13):
                return buf
            elif code == curses.ascii.ESC:
                return None
            elif code in (curses.KEY_BACKSPACE, curses.ascii.BS, 127):
                buf = buf[:-1]
            elif isinstance(ch, str) and code >= 32:
                buf += ch

    def save(self):
        name = self.filename
        if not name:
            name = self.prompt("File Name to Write: ")
            if not name:
                self.message = "Save cancelled"
                return
            self.filename = name
        with open(name, "w", encoding="utf-8") as f:
            f.write("\n".join(self.lines))
        self.dirty = False
        self.message = f"Wrote {len(self.lines)} lines to {name}"

    def search(self):
        term = self.prompt("Search: ")
        if not term:
            return
        n = len(self.lines)
        idx = self.lines[self.cy].find(term, self.cx)
        if idx != -1:
            self.sel_anchor = (self.cy, idx)
            self.cx = idx + len(term)
            self.message = f"Found at line {self.cy + 1}"
            return
        for offset in range(1, n + 1):
            row = (self.cy + offset) % n
            idx = self.lines[row].find(term)
            if idx != -1:
                self.sel_anchor = (row, idx)
                self.cy, self.cx = row, idx + len(term)
                self.message = f"Found at line {row + 1}"
                return
        self.sel_anchor = None
        self.message = f"\"{term}\" not found"

    def exit(self):
        if self.dirty:
            ans = self.prompt("Save modified buffer? (y/N): ")
            if ans and ans.lower().startswith("y"):
                self.save()
        self.quit_pending = True


def main(stdscr, filename):
    editor = Editor(stdscr, filename)
    editor.run()


if __name__ == "__main__":
    target = sys.argv[1] if len(sys.argv) > 1 else None
    curses.wrapper(main, target)
