"""The "Jev Decision Monitor" window: Task Manager-style group boxes with XP progress bars,
one per option, plus totals, the reason for the pick, and a list of recent decisions.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import pygame

from hearts.cards import Card
from jev_agent.jev import JevDecision

from . import card_art, theme, xp

SOURCE_TEXT = {
    "jev": ("Answered by Jev", "info"),
    "heuristic": ("Answered by the local heuristic", "info"),
    "random": ("Picked at random", "info"),
    "forced": ("Only one legal card: no call needed", "info"),
    "fallback": ("Jev failed: the heuristic played instead", "error"),
}


@dataclass
class PanelState:
    jev_name: str
    model: str | None = None
    current: JevDecision | None = None
    thinking_since: float | None = None  # perf_counter when the request went out
    thinking_title: str = ""
    thinking_options: list[Card] = field(default_factory=list)
    history: list[tuple[str, JevDecision]] = field(default_factory=list)  # (tag, decision)
    avg_latency_ms: float | None = None
    requests: int = 0


def status_panels(st: PanelState) -> list[tuple[str, int | None]]:
    avg = f"{st.avg_latency_ms:.0f} ms" if st.avg_latency_ms is not None else "–"
    return [
        (f"Decisions: {len(st.history)}", 110),
        (f"API calls: {st.requests}", 100),
        (f"Avg latency: {avg}", 130),
        (f"Model: {st.model or st.jev_name}", None),
    ]


def draw(surface: pygame.Surface, c: pygame.Rect, st: PanelState, now: float) -> None:
    x, w = c.x + 8, c.w - 16
    y = c.y + 6
    d = st.current
    thinking = st.thinking_since is not None

    # ---- Question
    q_rect = pygame.Rect(x, y, w, 96)
    inner = xp.group_box(surface, q_rect, "Current question")
    if d is None and not thinking:
        theme.text(surface, "Waiting for South's first decision…", theme.font(12), theme.TEXT_DIM, inner.topleft)
    else:
        title = st.thinking_title if thinking else d.title
        theme.text(surface, title, theme.font(15, bold=True), theme.TEXT, (inner.x, inner.y))
        sy = inner.y + 22
        if thinking:
            ms = (now - st.thinking_since) * 1000
            xp.icon(surface, "wait", (inner.x, sy + 1))
            theme.text(surface, f"Waiting for Jev… {ms:4.0f} ms", theme.font(12), theme.TEXT, (inner.x + 22, sy + 2))
        else:
            label, ic = SOURCE_TEXT.get(d.source, (d.source, "info"))
            xp.icon(surface, ic, (inner.x, sy + 1))
            theme.text(surface, label, theme.font(12), theme.TEXT, (inner.x + 22, sy + 2))
            sy += 22
            f = theme.font(11)
            for line in theme.wrap(d.situation, f, inner.w)[:2]:
                theme.text(surface, line, f, theme.TEXT_DIM, (inner.x, sy))
                sy += 15
    y = q_rect.bottom + 6

    # ---- Probabilities
    if thinking:
        rows = [(card, None) for card in st.thinking_options]
    elif d is not None:
        rows = sorted(((card, d.probabilities.get(card.id, 0.0)) for card in d.options), key=lambda r: -r[1])
    else:
        rows = []
    fixed_below = 136 + 6 + 150  # decision box + history minimum
    avail = c.bottom - y - fixed_below
    row_h = max(19, min(26, (avail - 40) // max(1, len(rows))))
    p_rect = pygame.Rect(x, y, w, max(60, len(rows) * row_h + 44))
    inner = xp.group_box(surface, p_rect, "Probability by option")
    lv = pygame.Rect(inner.x, inner.y + 2, inner.w, len(rows) * row_h + 6)
    xp.sunken(surface, lv)
    ry = lv.y + 3
    for card, p in rows:
        chosen = not thinking and d is not None and card == d.choice
        if chosen:
            pygame.draw.rect(surface, theme.SELECT, (lv.x + 1, ry, lv.w - 2, row_h))
        card_art.chip(surface, card, (lv.x + 6, ry + (row_h - 18) // 2), h=18)
        bar = pygame.Rect(lv.x + 58, ry + 3, lv.w - 58 - 64, row_h - 6)
        xp.progress(surface, bar, p, now + ry * 0.003, theme.PROGRESS_SELECTED if chosen else theme.PROGRESS)
        if p is not None:
            theme.text(surface, f"{p * 100:.1f}%", theme.font(12, bold=chosen), theme.WHITE if chosen else theme.TEXT,
                       (lv.right - 8, ry + row_h // 2), "midright")
        ry += row_h
    y = p_rect.bottom + 6

    # ---- Decision: the numbers, then what Jev was told about its pick
    t_rect = pygame.Rect(x, y, w, 136)
    inner = xp.group_box(surface, t_rect, "Decision")
    show = d if not thinking else None
    fields = [
        ("P(choice)", f"{show.chosen_p * 100:.0f}%" if show and show.chosen_p is not None else "–"),
        ("Confidence", f"{show.confidence:.2f}" if show and show.confidence is not None else "–"),
        ("Latency", f"{show.latency_ms:.0f} ms" if show and show.latency_ms is not None else "–"),
        ("Avg latency", f"{st.avg_latency_ms:.0f} ms" if st.avg_latency_ms is not None else "–"),
    ]
    fw = inner.w // 4
    f = theme.font(11)
    for i, (label, value) in enumerate(fields):
        fx = inner.x + i * fw
        theme.text(surface, label, f, theme.TEXT, (fx, inner.y + 1))
        box = pygame.Rect(fx, inner.y + 16, fw - 10, 20)
        xp.sunken(surface, box)
        theme.text(surface, value, theme.font(12, bold=True), theme.TEXT, (box.right - 5, box.centery), "midright")
    ty = inner.y + 46
    if show is not None:
        if show.error:
            xp.icon(surface, "error", (inner.x, ty + 1))
            body = f"{show.error}. The heuristic played {show.choice.label}."
        else:
            xp.icon(surface, "info", (inner.x, ty + 1))
            body = show.criteria.get(show.choice.id, "")
        for line in theme.wrap(body, theme.font(12), inner.w - 24)[:4]:
            theme.text(surface, line, theme.font(12), theme.TEXT, (inner.x + 24, ty))
            ty += 16
    y = t_rect.bottom + 6

    # ---- Recent decisions (list view)
    lv = pygame.Rect(x, y, w, c.bottom - y - 6)
    xp.sunken(surface, lv)
    cols = [("Move", 90), ("Card", 60), ("P(choice)", lv.w - 90 - 60 - 110), ("Source", 110)]
    xp.list_header(surface, pygame.Rect(lv.x + 1, lv.y + 1, lv.w - 2, 20), cols)
    ry = lv.y + 23
    rh = 20
    fit = max(0, (lv.bottom - ry - 2) // rh)
    f = theme.font(11)
    for i, (tag, h) in enumerate(list(reversed(st.history))[:fit]):
        selected = i == 0 and not thinking
        if selected:
            pygame.draw.rect(surface, theme.SELECT, (lv.x + 1, ry, lv.w - 2, rh))
        fg = theme.WHITE if selected else theme.TEXT
        theme.text(surface, tag, f, fg, (lv.x + 6, ry + rh // 2), "midleft")
        card_art.chip(surface, h.choice, (lv.x + 96, ry + 2), h=rh - 4)
        p = h.chosen_p
        bar = pygame.Rect(lv.x + 156, ry + 4, cols[2][1] - 60, rh - 8)
        xp.progress(surface, bar, p or 0.0)
        if p is not None:
            theme.text(surface, f"{p * 100:.0f}%", f, fg, (bar.right + 8, ry + rh // 2), "midleft")
        label = {"jev": "Jev", "forced": "only move", "fallback": "fallback"}.get(h.source, h.source)
        theme.text(surface, label, f, theme.WHITE if selected else (theme.ERROR_RED if h.source == "fallback" else theme.TEXT),
                   (lv.right - 110 + 6, ry + rh // 2), "midleft")
        ry += rh
