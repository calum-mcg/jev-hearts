"""Windows XP (Luna) widgets drawn with pygame: windows, status bars, group boxes, progress
bars, list views, buttons, tooltips, icons, a toolbar and the desktop wallpaper.
"""

from __future__ import annotations

import math
import random
from functools import lru_cache

import pygame

from . import theme

Stops = tuple[tuple[float, tuple[int, int, int]], ...]

TITLE_H = 28
STATUS_H = 22
BORDER = 4


# ---- gradients --------------------------------------------------------------------------


def _lerp(a, b, t):
    return tuple(int(x + (y - x) * t) for x, y in zip(a, b))


def _at(stops: Stops, t: float):
    for (t0, c0), (t1, c1) in zip(stops, stops[1:]):
        if t <= t1:
            return _lerp(c0, c1, 0 if t1 == t0 else (t - t0) / (t1 - t0))
    return stops[-1][1]


@lru_cache(maxsize=256)
def vgradient(w: int, h: int, stops: Stops) -> pygame.Surface:
    col = pygame.Surface((1, max(1, h)))
    for y in range(h):
        col.set_at((0, y), _at(stops, y / max(1, h - 1)))
    return pygame.transform.scale(col, (max(1, w), max(1, h)))


@lru_cache(maxsize=64)
def hgradient(w: int, h: int, stops: Stops) -> pygame.Surface:
    row = pygame.Surface((max(1, w), 1))
    for x in range(w):
        row.set_at((x, 0), _at(stops, x / max(1, w - 1)))
    return pygame.transform.scale(row, (max(1, w), max(1, h)))


def rounded(surf: pygame.Surface, tl=0, tr=0, bl=0, br=0) -> pygame.Surface:
    """Copy of `surf` with rounded (transparent) corners."""
    out = pygame.Surface(surf.get_size(), pygame.SRCALPHA)
    out.blit(surf, (0, 0))
    mask = pygame.Surface(surf.get_size(), pygame.SRCALPHA)
    pygame.draw.rect(mask, (255, 255, 255, 255), mask.get_rect(), border_top_left_radius=tl,
                     border_top_right_radius=tr, border_bottom_left_radius=bl, border_bottom_right_radius=br)
    out.blit(mask, (0, 0), special_flags=pygame.BLEND_RGBA_MIN)
    return out


@lru_cache(maxsize=256)
def rgrad(w: int, h: int, stops: Stops, tl=0, tr=0, bl=0, br=0, horizontal: bool = False) -> pygame.Surface:
    """Cached rounded gradient."""
    return rounded((hgradient if horizontal else vgradient)(w, h, stops), tl, tr, bl, br)


# ---- desktop ------------------------------------------------------------------------------


@lru_cache(maxsize=4)
def desktop(w: int, h: int) -> pygame.Surface:
    """A 'Bliss'-like wallpaper: blue sky, soft clouds, a rolling green hill."""
    surf = vgradient(w, h, theme.SKY).copy()
    rng = random.Random(2001)
    clouds = pygame.Surface((w, h), pygame.SRCALPHA)
    for _ in range(14):
        cx, cy = rng.uniform(0, w), rng.uniform(h * 0.05, h * 0.45)
        for _ in range(7):
            rw, rh = rng.uniform(80, 220), rng.uniform(22, 50)
            r = pygame.Rect(0, 0, rw, rh)
            r.center = (cx + rng.uniform(-110, 110), cy + rng.uniform(-14, 14))
            pygame.draw.ellipse(clouds, (255, 255, 255, 34), r)
    surf.blit(clouds, (0, 0))
    hill = vgradient(w, int(h * 0.55), theme.HILL)
    mask = pygame.Surface((w, int(h * 0.55)), pygame.SRCALPHA)
    pts = [(0, mask.get_height())]
    for x in range(0, w + 20, 20):
        y = mask.get_height() * (0.35 - 0.28 * math.sin(math.pi * x / w * 0.9 + 0.35))
        pts.append((x, y))
    pts.append((w, mask.get_height()))
    pygame.draw.polygon(mask, (255, 255, 255, 255), pts)
    hill_img = pygame.Surface(mask.get_size(), pygame.SRCALPHA)
    hill_img.blit(hill, (0, 0))
    hill_img.blit(mask, (0, 0), special_flags=pygame.BLEND_RGBA_MIN)
    surf.blit(hill_img, (0, h - mask.get_height()))
    return surf


# ---- icons (16x16) -----------------------------------------------------------------------


def icon(surface: pygame.Surface, kind: str, pos: tuple[int, int], size: int = 16) -> None:
    x, y = pos
    s = size
    if kind == "hearts":
        r = pygame.Rect(x + 2, y, s - 4, s)
        pygame.draw.rect(surface, theme.WHITE, r, border_radius=2)
        pygame.draw.rect(surface, theme.BLACK, r, 1, border_radius=2)
        from .card_art import pip
        from hearts.cards import Suit

        p = pip(Suit.HEARTS, s - 8)
        surface.blit(p, (x + 4, y + 4))
    elif kind == "jev":  # a little Task Manager graph
        r = pygame.Rect(x, y + 1, s, s - 2)
        pygame.draw.rect(surface, theme.BLACK, r)
        pygame.draw.rect(surface, (160, 160, 160), r, 1)
        pts = [(x + 2, y + s - 4), (x + 5, y + 8), (x + 8, y + 10), (x + 11, y + 4), (x + s - 2, y + 6)]
        pygame.draw.lines(surface, theme.CMD_GREEN, False, pts, 2)
    elif kind == "cmd":
        r = pygame.Rect(x, y + 1, s, s - 2)
        pygame.draw.rect(surface, theme.BLACK, r)
        pygame.draw.rect(surface, (200, 200, 200), r, 1)
        pygame.draw.rect(surface, (40, 80, 200), pygame.Rect(x, y + 1, s, 3))
        theme.text(surface, "C:\\", theme.font(8, mono=True), theme.CMD_TEXT, (x + 2, y + 6))
    elif kind in ("error", "warning", "info", "wait"):
        _message_icon(surface, kind, pygame.Rect(x, y, s, s))


def _message_icon(surface: pygame.Surface, kind: str, r: pygame.Rect) -> None:
    c = r.center
    rad = r.w // 2
    if kind == "error":
        pygame.draw.circle(surface, (160, 20, 10), c, rad)
        pygame.draw.circle(surface, theme.ERROR_RED, c, rad - 1)
        d = rad // 2
        pygame.draw.line(surface, theme.WHITE, (c[0] - d, c[1] - d), (c[0] + d, c[1] + d), 2)
        pygame.draw.line(surface, theme.WHITE, (c[0] + d, c[1] - d), (c[0] - d, c[1] + d), 2)
    elif kind == "warning":
        pts = [(r.centerx, r.y), (r.right, r.bottom - 1), (r.x, r.bottom - 1)]
        pygame.draw.polygon(surface, theme.WARN_YELLOW, pts)
        pygame.draw.polygon(surface, (120, 90, 0), pts, 1)
        theme.text(surface, "!", theme.font(max(9, r.h - 5), bold=True), theme.BLACK, (r.centerx, r.bottom), "midbottom")
    elif kind == "info":
        pygame.draw.circle(surface, (20, 60, 170), c, rad)
        pygame.draw.circle(surface, (40, 110, 230), c, rad - 1)
        theme.text(surface, "i", theme.font(max(9, r.h - 4), bold=True), theme.WHITE, c, "center")
    else:  # wait: hourglass
        top = [(r.x + 3, r.y + 1), (r.right - 3, r.y + 1), (r.centerx, r.centery)]
        bot = [(r.centerx, r.centery), (r.right - 3, r.bottom - 1), (r.x + 3, r.bottom - 1)]
        pygame.draw.polygon(surface, (250, 230, 150), top)
        pygame.draw.polygon(surface, (230, 180, 60), bot)
        pygame.draw.polygon(surface, (80, 60, 20), top, 1)
        pygame.draw.polygon(surface, (80, 60, 20), bot, 1)
        pygame.draw.line(surface, (80, 60, 20), (r.x + 1, r.y), (r.right - 2, r.y), 2)
        pygame.draw.line(surface, (80, 60, 20), (r.x + 1, r.bottom - 1), (r.right - 2, r.bottom - 1), 2)


# ---- windows ------------------------------------------------------------------------------


def window(surface: pygame.Surface, rect: pygame.Rect, title: str, icon_kind: str | None = None,
           active: bool = True) -> pygame.Rect:
    """Draw an XP window frame (title bar only); returns the client rect."""
    shadow = pygame.Surface((rect.w + 8, rect.h + 8), pygame.SRCALPHA)
    for i, a in enumerate((20, 28, 36)):
        pygame.draw.rect(shadow, (0, 0, 0, a), pygame.Rect(i + 2, i + 3, rect.w + 2 - 2 * i, rect.h + 2 - 2 * i),
                         border_radius=8)
    surface.blit(shadow, (rect.x - 2, rect.y - 1))
    frame_colour = theme.FRAME if active else theme.FRAME_INACTIVE
    pygame.draw.rect(surface, frame_colour, rect, border_top_left_radius=8, border_top_right_radius=8)
    bar = rgrad(rect.w, TITLE_H, theme.TITLE_ACTIVE if active else theme.TITLE_INACTIVE, 8, 8)
    surface.blit(bar, rect.topleft)
    pygame.draw.rect(surface, theme.FRAME_OUTER if active else (90, 110, 190), rect, 1,
                     border_top_left_radius=8, border_top_right_radius=8)
    x = rect.x + 8
    if icon_kind:
        icon(surface, icon_kind, (x, rect.y + 6))
        x += 22
    tf = theme.font(14, bold=True, title=True)
    shown = theme.ellipsize(title, tf, rect.w - (x - rect.x) - 12)
    if active:
        theme.text(surface, shown, tf, (10, 24, 131), (x + 1, rect.y + 6))
    theme.text(surface, shown, tf, theme.WHITE if active else (216, 228, 248), (x, rect.y + 5))
    client = pygame.Rect(rect.x + BORDER, rect.y + TITLE_H, rect.w - 2 * BORDER, rect.h - TITLE_H - BORDER)
    pygame.draw.rect(surface, theme.FACE, client)
    return client


def status_bar(surface: pygame.Surface, client: pygame.Rect, panels: list[tuple[str, int | None]],
               icons: dict[int, str] | None = None) -> pygame.Rect:
    """Status bar along the bottom of `client`; panels are (text, width or None = fill). Returns the area above."""
    bar = pygame.Rect(client.x, client.bottom - STATUS_H, client.w, STATUS_H)
    pygame.draw.rect(surface, theme.FACE, bar)
    pygame.draw.line(surface, theme.FACE_SHADOW, bar.topleft, bar.topright)
    pygame.draw.line(surface, theme.WHITE, (bar.x, bar.y + 1), (bar.right, bar.y + 1))
    fixed = sum(w for _, w in panels if w)
    flex = max(40, bar.w - fixed - 20 - 4 * len(panels))
    x = bar.x + 2
    f = theme.font(11)
    for i, (label, w) in enumerate(panels):
        pw = w or flex
        r = pygame.Rect(x, bar.y + 3, pw, bar.h - 5)
        pygame.draw.line(surface, theme.FACE_SHADOW, r.topleft, r.topright)
        pygame.draw.line(surface, theme.FACE_SHADOW, r.topleft, r.bottomleft)
        pygame.draw.line(surface, theme.WHITE, r.bottomleft, r.bottomright)
        pygame.draw.line(surface, theme.WHITE, r.topright, r.bottomright)
        tx = r.x + 4
        if icons and i in icons:
            icon(surface, icons[i], (tx, r.y + 1), 13)
            tx += 17
        theme.text(surface, theme.ellipsize(label, f, r.right - tx - 4), f, theme.TEXT, (tx, r.centery), "midleft")
        x = r.right + 3
    for i in range(3):  # size grip: a triangle of dots in the corner
        for j in range(3 - i):
            gx, gy = bar.right - 5 - j * 4, bar.bottom - 5 - i * 4
            pygame.draw.rect(surface, theme.WHITE, (gx + 1, gy + 1, 2, 2))
            pygame.draw.rect(surface, theme.FACE_SHADOW, (gx, gy, 2, 2))
    return pygame.Rect(client.x, client.y, client.w, client.h - STATUS_H)


def group_box(surface: pygame.Surface, rect: pygame.Rect, label: str) -> pygame.Rect:
    """XP group box; returns the inner content rect."""
    f = theme.font(12)
    top = rect.y + f.get_height() // 2
    frame = pygame.Rect(rect.x, top, rect.w, rect.bottom - top)
    pygame.draw.rect(surface, theme.GROUP_BORDER, frame, 1, border_radius=3)
    lw = f.size(label)[0]
    pygame.draw.rect(surface, theme.FACE, (rect.x + 7, rect.y, lw + 6, f.get_height()))
    theme.text(surface, label, f, theme.GROUP_TEXT, (rect.x + 10, rect.y))
    return pygame.Rect(rect.x + 9, rect.y + f.get_height() + 4, rect.w - 18, rect.h - f.get_height() - 12)


def sunken(surface: pygame.Surface, rect: pygame.Rect, fill=theme.WHITE) -> None:
    pygame.draw.rect(surface, fill, rect)
    pygame.draw.rect(surface, theme.FIELD_BORDER, rect, 1)


def progress(surface: pygame.Surface, rect: pygame.Rect, frac: float | None, now: float = 0.0,
             stops: Stops = theme.PROGRESS) -> None:
    """XP progress bar with green chunks. frac=None draws the marquee animation."""
    pygame.draw.rect(surface, theme.WHITE, rect, border_radius=3)
    pygame.draw.rect(surface, (104, 104, 104), rect, 1, border_radius=3)
    inner = rect.inflate(-4, -4)
    chunk_w, gap = 8, 2
    chunk = vgradient(chunk_w, inner.h, stops)
    if frac is None:
        span = 4 * (chunk_w + gap)
        start = int((now * 140) % (inner.w + span)) - span
        xs = [inner.x + start + i * (chunk_w + gap) for i in range(4)]
    else:
        n = int(round(inner.w * max(0.0, min(1.0, frac)) / (chunk_w + gap)))
        if frac > 0 and n == 0:
            n = 1
        xs = [inner.x + i * (chunk_w + gap) for i in range(n)]
    clip = surface.get_clip()
    surface.set_clip(inner.clip(clip) if clip else inner)
    for x in xs:
        surface.blit(chunk, (x, inner.y))
    surface.set_clip(clip)


def button(surface: pygame.Surface, rect: pygame.Rect, label: str, default: bool = False, disabled: bool = False) -> None:
    stops = ((0.0, (255, 255, 255)), (0.85, (240, 240, 234)), (1.0, (214, 208, 197)))
    surface.blit(rgrad(rect.w, rect.h, stops, 3, 3, 3, 3), rect)
    pygame.draw.rect(surface, (0, 60, 116) if not disabled else (201, 199, 186), rect, 1, border_radius=3)
    if default and not disabled:
        pygame.draw.rect(surface, (152, 180, 232), rect.inflate(-4, -4), 1, border_radius=2)
    theme.text(surface, label, theme.font(12), theme.TEXT_GREY if disabled else theme.TEXT, rect.center, "center")


def tooltip(surface: pygame.Surface, lines: list[tuple[str, bool]], pos, anchor: str = "topleft",
            fill=theme.TOOLTIP, fg=theme.TEXT, border=theme.BLACK) -> pygame.Rect:
    """Yellow XP tooltip; lines are (text, bold)."""
    fonts = [theme.font(12, bold=b) for _, b in lines]
    w = max(f.size(s)[0] for (s, _), f in zip(lines, fonts)) + 12
    h = sum(f.get_height() for f in fonts) + 6
    r = pygame.Rect(0, 0, w, h)
    setattr(r, anchor, pos)
    pygame.draw.rect(surface, fill, r)
    pygame.draw.rect(surface, border, r, 1)
    y = r.y + 3
    for (s, _), f in zip(lines, fonts):
        theme.text(surface, s, f, fg, (r.x + 6, y))
        y += f.get_height()
    return r


def list_header(surface: pygame.Surface, rect: pygame.Rect, columns: list[tuple[str, int]]) -> None:
    stops = ((0.0, (255, 255, 255)), (0.8, (247, 246, 240)), (1.0, (226, 222, 205)))
    surface.blit(vgradient(rect.w, rect.h, stops), rect)
    pygame.draw.line(surface, (214, 210, 194), rect.bottomleft, rect.bottomright)
    x = rect.x
    f = theme.font(11)
    for label, w in columns:
        theme.text(surface, label, f, theme.TEXT, (x + 6, rect.centery), "midleft")
        x += w
        pygame.draw.line(surface, (199, 197, 178), (x - 1, rect.y + 4), (x - 1, rect.bottom - 4))


def scrollbar(surface: pygame.Surface, rect: pygame.Rect, top: float, size: float) -> None:
    """Vertical XP scrollbar; top/size are fractions of the content."""
    pygame.draw.rect(surface, (243, 241, 236), rect)
    btn_stops = ((0.0, (230, 238, 252)), (1.0, (187, 206, 244)))
    for r, up in ((pygame.Rect(rect.x, rect.y, rect.w, rect.w), True),
                  (pygame.Rect(rect.x, rect.bottom - rect.w, rect.w, rect.w), False)):
        surface.blit(rgrad(r.w, r.h, btn_stops, 3, 3, 3, 3, True), r)
        pygame.draw.rect(surface, theme.WHITE, r, 1, border_radius=3)
        cx, cy = r.center
        d = 3 if up else -3
        pygame.draw.polygon(surface, (77, 97, 133), [(cx - 4, cy + d // 2 + 1), (cx + 4, cy + d // 2 + 1), (cx, cy - d)])
    track = pygame.Rect(rect.x, rect.y + rect.w, rect.w, rect.h - 2 * rect.w)
    th = max(18, int(track.h * min(1.0, size)))
    ty = track.y + int((track.h - th) * max(0.0, min(1.0, top)))
    thumb = pygame.Rect(rect.x + 1, ty, rect.w - 2, th)
    surface.blit(rgrad(thumb.w, thumb.h, ((0.0, (201, 216, 252)), (1.0, (170, 194, 245))), 3, 3, 3, 3, True), thumb)
    pygame.draw.rect(surface, theme.WHITE, thumb, 1, border_radius=3)
    for i in (-3, 0, 3):
        pygame.draw.line(surface, (140, 164, 216), (thumb.centerx - 3, thumb.centery + i), (thumb.centerx + 3, thumb.centery + i))


# ---- toolbar ------------------------------------------------------------------------------

TOOLBAR_H = 30


def toolbar(surface: pygame.Surface, client: pygame.Rect) -> pygame.Rect:
    """Toolbar strip at the top of `client`; returns its rect."""
    bar = pygame.Rect(client.x, client.y, client.w, TOOLBAR_H)
    surface.blit(vgradient(bar.w, bar.h, ((0.0, (250, 249, 244)), (1.0, (228, 225, 208)))), bar)
    pygame.draw.line(surface, theme.FACE_SHADOW, bar.bottomleft, (bar.right, bar.bottom))
    for i in range(0, bar.h - 10, 4):  # gripper
        pygame.draw.rect(surface, theme.FACE_SHADOW, (bar.x + 4, bar.y + 5 + i, 2, 2))
    return bar


def toolbar_button(surface: pygame.Surface, rect: pygame.Rect, label: str, checked: bool = False,
                   hover: bool = False, symbol: str | None = None) -> None:
    if checked:
        pygame.draw.rect(surface, (225, 230, 245), rect, border_radius=3)
        pygame.draw.rect(surface, theme.SELECT, rect, 1, border_radius=3)
    elif hover:
        pygame.draw.rect(surface, (193, 210, 238), rect, border_radius=3)
        pygame.draw.rect(surface, (49, 106, 197), rect, 1, border_radius=3)
    x = rect.x + 7
    if symbol:
        glyph(surface, symbol, pygame.Rect(x, rect.centery - 6, 12, 12))
        x += 17
    theme.text(surface, label, theme.font(11, bold=checked), theme.TEXT, (x, rect.centery), "midleft")


def toolbar_width(label: str, symbol: str | None = None) -> int:
    return theme.font(11, bold=True).size(label)[0] + 14 + (17 if symbol else 0)


def toolbar_separator(surface: pygame.Surface, x: int, bar: pygame.Rect) -> None:
    pygame.draw.line(surface, theme.FACE_SHADOW, (x, bar.y + 5), (x, bar.bottom - 5))
    pygame.draw.line(surface, theme.WHITE, (x + 1, bar.y + 5), (x + 1, bar.bottom - 5))


def glyph(surface: pygame.Surface, kind: str, r: pygame.Rect) -> None:
    green, blue = (40, 150, 40), (40, 90, 200)
    if kind == "pause":
        pygame.draw.rect(surface, blue, (r.x + 2, r.y + 1, 3, r.h - 2))
        pygame.draw.rect(surface, blue, (r.right - 5, r.y + 1, 3, r.h - 2))
    elif kind == "play":
        pygame.draw.polygon(surface, green, [(r.x + 2, r.y), (r.right, r.centery), (r.x + 2, r.bottom)])
    elif kind == "step":
        pygame.draw.polygon(surface, green, [(r.x, r.y + 1), (r.right - 4, r.centery), (r.x, r.bottom - 1)])
        pygame.draw.rect(surface, green, (r.right - 3, r.y + 1, 3, r.h - 2))
    elif kind == "new":
        pygame.draw.rect(surface, theme.WHITE, (r.x + 1, r.y, r.w - 3, r.h))
        pygame.draw.rect(surface, (90, 90, 90), (r.x + 1, r.y, r.w - 3, r.h), 1)
        pygame.draw.circle(surface, theme.CARD_RED, (r.centerx - 1, r.centery), 3)
    elif kind == "speed":  # a little gauge
        pygame.draw.arc(surface, (90, 90, 90), r.inflate(2, 2), 0, 3.1416, 2)
        pygame.draw.line(surface, theme.ERROR_RED, (r.centerx, r.centery + 2), (r.right - 2, r.y + 2), 2)
