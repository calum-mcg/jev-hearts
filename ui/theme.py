"""Windows XP (Luna) colour tokens, fonts and small text helpers."""

from __future__ import annotations

from functools import lru_cache

import pygame

# ---- Luna chrome
FACE = (236, 233, 216)  # window body / 3D face
FACE_SHADOW = (172, 168, 153)
FACE_DARK = (113, 111, 100)
WHITE = (255, 255, 255)
BLACK = (0, 0, 0)
TEXT = (0, 0, 0)
TEXT_DIM = (98, 98, 92)
TEXT_GREY = (161, 161, 146)  # disabled text
SELECT = (49, 106, 197)  # list selection
FIELD_BORDER = (127, 157, 185)  # text box / list view border
GROUP_BORDER = (208, 208, 191)
GROUP_TEXT = (0, 70, 213)
LINK = (0, 102, 204)
FRAME = (0, 84, 227)
FRAME_OUTER = (0, 19, 140)
FRAME_INACTIVE = (122, 150, 223)
TITLE_ACTIVE = ((0.0, (9, 97, 255)), (0.07, (58, 147, 255)), (0.16, (0, 98, 247)),
                (0.5, (0, 84, 227)), (0.86, (0, 76, 218)), (1.0, (0, 61, 190)))
TITLE_INACTIVE = ((0.0, (154, 180, 238)), (0.1, (180, 202, 247)), (0.2, (148, 175, 236)),
                  (1.0, (125, 152, 224)))
TOOLTIP = (255, 255, 225)
ERROR_RED = (215, 45, 30)
WARN_YELLOW = (250, 200, 30)

# ---- progress bar chunks (XP green)
PROGRESS = ((0.0, (175, 238, 175)), (0.35, (47, 207, 47)), (0.65, (38, 190, 38)), (1.0, (140, 228, 140)))
PROGRESS_SELECTED = ((0.0, (255, 236, 170)), (0.4, (250, 196, 40)), (1.0, (255, 226, 130)))

# ---- desktop
SKY = ((0.0, (40, 96, 200)), (0.55, (110, 165, 235)), (1.0, (185, 220, 250)))
HILL = ((0.0, (110, 185, 60)), (0.4, (70, 150, 35)), (1.0, (30, 95, 20)))

# ---- game
FELT = (0, 128, 0)
FELT_LINE = (0, 108, 0)
CARD_FACE = (255, 255, 255)
CARD_EDGE = (0, 0, 0)
CARD_RED = (220, 0, 0)
CARD_BLACK = (0, 0, 0)
CARD_BACK = (16, 40, 160)
CARD_BACK_2 = (90, 140, 230)
SEAT_COLOURS = ((250, 200, 30), (80, 150, 255), (230, 60, 50), (60, 190, 70))  # South, West, North, East

# ---- cmd.exe
CMD_BG = (0, 0, 0)
CMD_TEXT = (192, 192, 192)
CMD_BRIGHT = (255, 255, 255)
CMD_GREEN = (0, 255, 0)
CMD_YELLOW = (255, 255, 0)
CMD_RED = (255, 80, 80)
CMD_CYAN = (0, 255, 255)
CMD_MAGENTA = (255, 110, 255)
CMD_GREY = (128, 128, 128)

_SANS = "tahoma,verdana,arial"
_TITLE = "trebuchetms,tahoma,arial"
_MONO = "lucidaconsole,consolas,couriernew"


@lru_cache(maxsize=None)
def font(size: int, bold: bool = False, mono: bool = False, title: bool = False) -> pygame.font.Font:
    return pygame.font.SysFont(_MONO if mono else _TITLE if title else _SANS, size, bold=bold)


def text(surface: pygame.Surface, s: str, f: pygame.font.Font, colour, pos, anchor: str = "topleft") -> pygame.Rect:
    img = f.render(s, True, colour)
    r = img.get_rect(**{anchor: pos})
    surface.blit(img, r)
    return r


def wrap(s: str, f: pygame.font.Font, width: int) -> list[str]:
    lines: list[str] = []
    for para in s.split("\n"):
        line = ""
        for word in para.split(" "):
            trial = f"{line} {word}".strip()
            if f.size(trial)[0] <= width or not line:
                line = trial
            else:
                lines.append(line)
                line = word
        lines.append(line)
    return lines


def ellipsize(s: str, f: pygame.font.Font, width: int) -> str:
    if f.size(s)[0] <= width:
        return s
    while s and f.size(s + "…")[0] > width:
        s = s[:-1]
    return s + "…"
