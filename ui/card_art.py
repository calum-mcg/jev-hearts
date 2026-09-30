"""Cards drawn in code: faces, backs and suit pips (vector shapes, no font glyphs needed).

Everything is drawn at 4x and smooth-scaled down for anti-aliasing, then cached.
"""

from __future__ import annotations

from functools import lru_cache

import pygame

from hearts.cards import Card, Suit

from . import theme

SS = 4  # supersampling factor


def _suit_shape(surf: pygame.Surface, suit: Suit, s: int, colour) -> None:
    """Fill a suit pip into an s x s surface."""
    def P(x, y):
        return (x * s, y * s)

    def circle(x, y, r):
        pygame.draw.circle(surf, colour, P(x, y), r * s)

    if suit is Suit.HEARTS:
        circle(0.29, 0.34, 0.25)
        circle(0.71, 0.34, 0.25)
        pygame.draw.polygon(surf, colour, [P(0.055, 0.42), P(0.945, 0.42), P(0.5, 0.95)])
    elif suit is Suit.DIAMONDS:
        pygame.draw.polygon(surf, colour, [P(0.5, 0.02), P(0.88, 0.5), P(0.5, 0.98), P(0.12, 0.5)])
    elif suit is Suit.SPADES:
        circle(0.29, 0.58, 0.23)
        circle(0.71, 0.58, 0.23)
        pygame.draw.polygon(surf, colour, [P(0.07, 0.52), P(0.93, 0.52), P(0.5, 0.03)])
        pygame.draw.polygon(surf, colour, [P(0.5, 0.6), P(0.33, 0.97), P(0.67, 0.97)])
    else:  # clubs
        circle(0.5, 0.28, 0.21)
        circle(0.27, 0.6, 0.21)
        circle(0.73, 0.6, 0.21)
        circle(0.5, 0.55, 0.12)
        pygame.draw.polygon(surf, colour, [P(0.5, 0.5), P(0.33, 0.97), P(0.67, 0.97)])


def suit_colour(suit: Suit):
    return theme.CARD_RED if suit.red else theme.CARD_BLACK


@lru_cache(maxsize=None)
def pip(suit: Suit, size: int, colour: tuple | None = None) -> pygame.Surface:
    big = pygame.Surface((size * SS, size * SS), pygame.SRCALPHA)
    _suit_shape(big, suit, size * SS, colour or suit_colour(suit))
    return pygame.transform.smoothscale(big, (size, size))


def _rounded(size: tuple[int, int], fill, edge, radius: int) -> pygame.Surface:
    w, h = size
    big = pygame.Surface((w * SS, h * SS), pygame.SRCALPHA)
    r = pygame.Rect(0, 0, w * SS, h * SS)
    pygame.draw.rect(big, edge, r, border_radius=radius * SS)
    pygame.draw.rect(big, fill, r.inflate(-2 * SS, -2 * SS), border_radius=(radius - 1) * SS)
    return pygame.transform.smoothscale(big, size)


@lru_cache(maxsize=None)
def face(card: Card, w: int, h: int) -> pygame.Surface:
    surf = _rounded((w, h), theme.CARD_FACE, theme.CARD_EDGE, max(3, w // 14))
    colour = suit_colour(card.suit)
    rank_font = theme.font(max(12, int(h * 0.2)), bold=True)
    corner = pygame.Surface((w, h), pygame.SRCALPHA)
    x0, y0 = int(w * 0.09), int(h * 0.04)
    r = theme.text(corner, card.rank_str, rank_font, colour, (x0 + int(w * 0.1), y0), "midtop")
    small = max(8, int(w * 0.2))
    corner.blit(pip(card.suit, small), (r.centerx - small // 2, r.bottom))
    surf.blit(corner, (0, 0))
    surf.blit(pygame.transform.rotate(corner, 180), (0, 0))
    big = int(w * 0.5)
    surf.blit(pip(card.suit, big), (w // 2 - big // 2, h // 2 - big // 2))
    return surf


@lru_cache(maxsize=None)
def back(w: int, h: int) -> pygame.Surface:
    """Classic lattice card back: white border, blue weave."""
    surf = _rounded((w, h), theme.WHITE, theme.CARD_EDGE, max(3, w // 14))
    inner = pygame.Rect(0, 0, w, h).inflate(-max(6, w // 8), -max(6, w // 8))
    pygame.draw.rect(surf, theme.CARD_BACK, inner)
    step = max(4, w // 9)
    clip = surf.get_clip()
    surf.set_clip(inner)
    for i in range(-h, w + h, step):
        pygame.draw.line(surf, theme.CARD_BACK_2, (inner.x + i, inner.y), (inner.x + i + h, inner.y + h), 1)
        pygame.draw.line(surf, theme.CARD_BACK_2, (inner.x + i + h, inner.y), (inner.x + i, inner.y + h), 1)
    surf.set_clip(clip)
    pygame.draw.rect(surf, (10, 25, 110), inner, 1)
    return surf


def draw(surface: pygame.Surface, card: Card | None, rect: pygame.Rect, glow=None, dim: bool = False) -> None:
    """Draw a face (or back when card is None) at rect, with an optional outline colour."""
    img = back(rect.w, rect.h) if card is None else face(card, rect.w, rect.h)
    surface.blit(img, rect)
    if dim:
        veil = pygame.Surface(rect.size, pygame.SRCALPHA)
        pygame.draw.rect(veil, (0, 40, 0, 95), veil.get_rect(), border_radius=max(3, rect.w // 14))
        surface.blit(veil, rect)
    if glow:
        pygame.draw.rect(surface, glow, rect.inflate(4, 4), 3, border_radius=max(4, rect.w // 12))


def chip(surface: pygame.Surface, card: Card, pos: tuple[int, int], h: int = 24) -> pygame.Rect:
    """A compact inline card label (rank + pip) on a small white tile."""
    f = theme.font(int(h * 0.62), bold=True)
    tw = f.size(card.rank_str)[0]
    p = int(h * 0.55)
    r = pygame.Rect(pos, (tw + p + 14, h))
    pygame.draw.rect(surface, theme.CARD_FACE, r, border_radius=3)
    pygame.draw.rect(surface, (120, 120, 120), r, 1, border_radius=3)
    colour = suit_colour(card.suit)
    theme.text(surface, card.rank_str, f, colour, (r.x + 5, r.centery), "midleft")
    surface.blit(pip(card.suit, p), (r.x + 7 + tw, r.centery - p // 2))
    return r
