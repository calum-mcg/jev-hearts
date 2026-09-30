"""The console, drawn as a cmd.exe window: black, Lucida Console, XP scrollbar."""

from __future__ import annotations

import time
from collections import deque
from dataclasses import dataclass

import pygame

from . import theme, xp

KIND_COLOURS = {
    "deal": theme.CMD_BRIGHT,
    "pass": theme.CMD_TEXT,
    "exchange": theme.CMD_CYAN,
    "play": theme.CMD_TEXT,
    "trick": theme.CMD_BRIGHT,
    "hand": theme.CMD_YELLOW,
    "game": theme.CMD_YELLOW,
    "info": theme.CMD_MAGENTA,
    "jev": theme.CMD_GREEN,
    "error": theme.CMD_RED,
    "sys": theme.CMD_GREY,
}
SCROLL_W = 17


@dataclass
class Line:
    t: float
    kind: str
    text: str
    colour: tuple | None = None
    clock: str = ""


class ConsoleLog:
    def __init__(self, maxlen: int = 400, echo: bool = False) -> None:
        self.lines: deque[Line] = deque(maxlen=maxlen)
        self.start = time.perf_counter()
        self.scroll = 0  # lines scrolled up from the bottom
        self.echo = echo

    def add(self, kind: str, text: str, colour=None) -> None:
        self.lines.append(Line(time.perf_counter() - self.start, kind, text, colour, time.strftime("%H:%M:%S")))
        if self.scroll:
            self.scroll += 1  # keep the view still while scrolled back
        if self.echo:
            print(f"{self.lines[-1].t:8.2f}s  [{kind}] {text}", flush=True)

    def on_wheel(self, dy: int) -> None:
        self.scroll = max(0, min(len(self.lines) - 1, self.scroll + dy * 3))


def draw(surface: pygame.Surface, c: pygame.Rect, log: ConsoleLog, now: float) -> None:
    pygame.draw.rect(surface, theme.CMD_BG, c)
    text_rect = pygame.Rect(c.x + 4, c.y + 2, c.w - SCROLL_W - 8, c.h - 4)
    f = theme.font(13, mono=True)
    lh = f.get_linesize() + 1
    rows = max(1, text_rect.h // lh)
    header = ["Microsoft Windows XP [Version 5.1.2600]", "(C) Copyright 1985-2001 Microsoft Corp.", "",
              r"C:\Documents and Settings\Jev> uv run jev"]
    lines = [(None, h) for h in header] + [(ln, None) for ln in log.lines]
    end = len(lines) - log.scroll
    start = max(0, end - rows)
    visible = lines[start:end]
    clip = surface.get_clip()
    surface.set_clip(text_rect)
    y = text_rect.y
    cw = f.size("0")[0]
    for ln, raw in visible:
        if ln is None:
            theme.text(surface, raw, f, theme.CMD_TEXT, (text_rect.x, y))
        else:
            colour = ln.colour or KIND_COLOURS.get(ln.kind, theme.CMD_TEXT)
            theme.text(surface, ln.clock, f, theme.CMD_GREY, (text_rect.x, y))
            theme.text(surface, f"{ln.kind.upper():<8}", f, colour, (text_rect.x + cw * 10, y))
            body = ln.colour or (theme.CMD_TEXT if ln.kind in ("play", "pass", "sys") else colour)
            theme.text(surface, ln.text, f, body, (text_rect.x + cw * 19, y))
        y += lh
    if log.scroll == 0 and int(now * 2) % 2 == 0 and y + lh <= text_rect.bottom + lh:  # blinking cursor
        pygame.draw.rect(surface, theme.CMD_TEXT, (text_rect.x, y + lh - 4, cw, 3))
    surface.set_clip(clip)
    total = max(1, len(lines))
    xp.scrollbar(surface, pygame.Rect(c.right - SCROLL_W, c.y, SCROLL_W, c.h), start / max(1, total - rows),
                 rows / total)
