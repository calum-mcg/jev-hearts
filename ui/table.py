"""The Hearts table: classic green felt, four hands, name labels right next to each hand,
the current trick in the middle, and an XP "Score Sheet" dialog between hands.
"""

from __future__ import annotations

from dataclasses import dataclass

import pygame

from hearts.cards import QUEEN_SPADES, Card
from hearts.game import HeartsGame, Trick
from hearts.rules import PASS_OFFSET, SEATS

from . import card_art, theme, xp

WIN_OUTLINE = (255, 230, 0)
LABEL_FILL, LABEL_BORDER = (0, 92, 0), (0, 60, 0)


@dataclass
class TableView:
    highlight: Card | None = None  # Jev's pick, raised and outlined
    thinking: bool = False
    shown_trick: Trick | None = None  # a finished trick still on display
    paused: bool = False


def status_panels(game: HeartsGame) -> list[tuple[str, int | None]]:
    """Text for the Hearts window's status bar."""
    trick_no = min(len(game.tricks) + (1 if game.phase == "play" else 0), 13)
    q = game.queen_taker()
    queen_in_trick = any(c == QUEEN_SPADES for _, c in game.trick)
    last = game.last_trick
    if game.phase == "pass":
        msg = f"Passing {game.direction}: each player picks three cards."
    elif last is not None and not game.trick:
        pts = f" and {last.points} point{'s' if last.points != 1 else ''}" if last.points else ""
        msg = f"{SEATS[last.winner]} took the trick{pts}."
    else:
        d = game.pending()
        msg = f"{SEATS[d.seat]} to play." if d else ""
    return [
        (msg, None),
        (f"Trick {trick_no} of 13" if game.phase != "pass" else "Passing", 90),
        ("Hearts broken" if game.hearts_broken else "Hearts not broken", 120),
        (f"Q♠ taken by {SEATS[q]}" if q is not None else "Q♠ in this trick" if queen_in_trick else "Q♠ not played", 130),
    ]


def _label(surface, game: HeartsGame, seat: int, pos, anchor: str, state: str, bounds: pygame.Rect,
           extra: str | None = None) -> None:
    """Name label right next to a hand. state: normal | active | winner."""
    who = "Jev" if seat == 0 else "computer"
    lines = [(f"{SEATS[seat]} ({who})", True),
             (f"{game.points_hand[seat]} this round · {game.scores[seat]} total", False)]
    if extra:
        lines.append((extra, True))
    style = {"fill": LABEL_FILL, "fg": theme.WHITE, "border": LABEL_BORDER} if state == "normal" else {}
    # measure off-screen first so the label can be clamped onto the felt
    probe = pygame.Surface((1, 1))
    r = xp.tooltip(probe, lines, pos, anchor, **style)
    xp.tooltip(surface, lines, r.clamp(bounds.inflate(-8, -8)).topleft, **style)


def draw(surface: pygame.Surface, felt: pygame.Rect, game: HeartsGame, view: TableView, now: float) -> None:
    surface.fill(theme.FELT, felt)
    clip = surface.get_clip()
    surface.set_clip(felt)
    pending = game.pending()
    active = pending.seat if pending else None
    over = game.phase in ("hand_over", "game_over")
    cx = felt.centerx

    ch = int(min(112, felt.h * 0.2))
    cw = int(ch * 0.72)
    bh, bw = int(ch * 0.6), int(ch * 0.6 * 0.72)  # opponents' backs (upright size)
    label_h = 40
    cy = felt.y + (felt.h - label_h) // 2

    shown = view.shown_trick if (view.shown_trick is not None and not game.trick and not over) else None
    winner = shown.winner if shown else None

    def state(seat: int) -> str:
        return "winner" if seat == winner else "active" if seat == active and not over else "normal"

    def extra(seat: int) -> str | None:
        if seat != winner:
            return None
        return f"Takes the trick (+{shown.points})" if shown.points else "Takes the trick"

    # ---- South (Jev): face-up hand, label directly underneath
    hand = game.hands[0]
    picked = game.pass_picks[0] if game.phase == "pass" else []
    legal = set(pending.options) if pending and pending.seat == 0 else set()
    received = set(game.received[0]) if game.phase == "play" and not game.tricks else set()
    n = len(hand)
    span = felt.w - 2 * (bh + 110)  # leave room for the West/East labels
    step = min(cw + 6, (span - cw) / max(1, n - 1)) if n > 1 else 0
    x0 = cx - (cw + step * max(0, n - 1)) / 2
    base_y = felt.bottom - ch - label_h - 14
    for i, c in enumerate(hand):
        lift, glow = 0, None
        if c in picked:
            lift, glow = 22, theme.SELECT
        elif c == view.highlight:
            lift, glow = 26, theme.SELECT
        elif c in legal and len(legal) < len(hand):
            lift = 8
        elif c in received:
            glow = theme.TOOLTIP
        r = pygame.Rect(int(x0 + i * step), base_y - lift, cw, ch)
        card_art.draw(surface, c, r, glow=glow, dim=bool(legal) and c not in legal and c not in picked)
    _label(surface, game, 0, (cx, base_y + ch + 6), "midtop", state(0), felt, extra(0))

    # ---- North: backs across the top, label directly underneath
    k = len(game.hands[2])
    step_n = bw * 0.36
    xn = cx - (bw + step_n * max(0, k - 1)) / 2
    top_y = felt.y + 12
    for i in range(k):
        card_art.draw(surface, None, pygame.Rect(int(xn + i * step_n), top_y, bw, bh))
    _label(surface, game, 2, (cx, top_y + (bh if k else 0) + 6), "midtop", state(2), felt, extra(2))

    # ---- Round + running totals, top-left
    board = _scoreboard(surface, felt, game)

    # ---- West / East: sideways stacks (below the scoreboard), label directly underneath each
    for seat, x in ((1, felt.x + 18), (3, felt.right - 18 - bh)):
        k = len(game.hands[seat])
        step_v = bw * 0.22
        stack_h = bw + step_v * max(0, k - 1)
        yv = max(board.bottom + 12, cy - stack_h / 2 - 50)
        for i in range(k):
            card_art.draw(surface, None, pygame.Rect(x, int(yv + i * step_v), bh, bw))
        anchor = "topleft" if seat == 1 else "topright"
        ax = x if seat == 1 else x + bh
        _label(surface, game, seat, (ax, int(yv + (stack_h if k else 0)) + 6), anchor, state(seat), felt, extra(seat))

    # ---- centre: the current trick, or the one just finished
    tw, th = int(cw * 0.95), int(ch * 0.95)
    offsets = {0: (0, th * 0.52), 1: (-tw * 1.1, 0), 2: (0, -th * 0.52), 3: (tw * 1.1, 0)}
    plays = list(game.trick) if game.trick else (list(shown.plays) if shown else [])
    lead_rect = None
    for i, (seat, c) in enumerate(plays):
        ox, oy = offsets[seat]
        r = pygame.Rect(0, 0, tw, th)
        r.center = (int(cx + ox), int(cy + oy))
        card_art.draw(surface, c, r, glow=WIN_OUTLINE if seat == winner else None)
        if i == 0:
            lead_rect = r
    if lead_rect is not None:
        xp.tooltip(surface, [("led", False)], (lead_rect.x + 4, lead_rect.bottom - 4), "bottomleft")

    if game.phase == "pass":
        to = SEATS[PASS_OFFSET[game.direction] % 4]
        f = theme.font(15, bold=True)
        left = 3 - len(picked)
        msg = f"Jev is choosing {left} more card{'s' if left != 1 else ''} to pass to {to}." if left else \
            "Waiting for the other players to pass…"
        theme.text(surface, msg, f, (0, 50, 0), (cx + 1, cy - 29), "center")
        theme.text(surface, msg, f, theme.WHITE, (cx, cy - 30), "center")
        b = pygame.Rect(0, 0, 120, 28)
        b.center = (cx, cy + 6)
        xp.button(surface, b, f"Pass {game.direction.title()}", default=left == 0, disabled=left > 0)

    if view.paused:
        xp.tooltip(surface, [("Paused", True), ("Press SPACE to resume, N to step.", False)],
                   (cx, cy - th - 20), "midbottom")

    surface.set_clip(clip)
    if over:
        _score_sheet(surface, felt, game)


def _scoreboard(surface: pygame.Surface, felt: pygame.Rect, game: HeartsGame) -> pygame.Rect:
    """Round number and running totals (this round's points so far, and the game total)."""
    box = pygame.Rect(felt.x + 10, felt.y + 10, 236, 22 + 18 + 4 * 18 + 5)
    title = f"Round {game.hand_no + 1}  ·  pass {game.direction}"
    surface.blit(xp.rgrad(box.w, 22, theme.TITLE_ACTIVE, 5, 5), box.topleft)
    theme.text(surface, title, theme.font(12, bold=True), theme.WHITE, (box.x + 8, box.y + 11), "midleft")
    theme.text(surface, f"to {game.target}", theme.font(11), (200, 220, 255), (box.right - 8, box.y + 11), "midright")
    body = pygame.Rect(box.x, box.y + 22, box.w, box.h - 22)
    xp.sunken(surface, body)
    cols = [("Player", 104), ("This round", 68), ("Total", box.w - 172)]
    xp.list_header(surface, pygame.Rect(body.x + 1, body.y + 1, body.w - 2, 18), cols)
    f, fb = theme.font(11), theme.font(11, bold=True)
    low = min(game.scores)
    y = body.y + 20
    for seat in sorted(range(4), key=lambda s: (game.scores[s], s)):  # leader first
        pygame.draw.circle(surface, theme.SEAT_COLOURS[seat], (body.x + 9, y + 9), 4)
        name = SEATS[seat] + (" (Jev)" if seat == 0 else "")
        theme.text(surface, name, fb if seat == 0 else f, theme.TEXT, (body.x + 18, y + 9), "midleft")
        pts = game.points_hand[seat]
        theme.text(surface, f"+{pts}" if pts else "0", f, theme.CARD_RED if pts else theme.TEXT_DIM,
                   (body.x + 104 + 56, y + 9), "midright")
        total = game.scores[seat]
        theme.text(surface, str(total), fb, theme.GROUP_TEXT if total == low else theme.TEXT,
                   (body.right - 10, y + 9), "midright")
        y += 18
    return box


def _score_sheet(surface: pygame.Surface, felt: pygame.Rect, game: HeartsGame) -> None:
    over = game.phase == "game_over"
    rect = pygame.Rect(0, 0, 400, 262 if game.moon is not None or over else 232)
    rect.center = (felt.centerx, felt.centery - 16)
    client = xp.window(surface, rect, "Game Over" if over else f"Score Sheet - Round {game.hand_no + 1}", "hearts")
    y = client.y + 10
    if over or game.moon is not None:
        low = min(game.scores)
        msg = (f"{' and '.join(SEATS[s] for s in range(4) if game.scores[s] == low)} won with {low} points."
               if over else f"{SEATS[game.moon]} shot the moon!")
        xp.icon(surface, "info", (client.x + 12, y), 20)
        theme.text(surface, msg, theme.font(12, bold=True), theme.TEXT, (client.x + 40, y + 2))
        y += 30
    lv = pygame.Rect(client.x + 12, y, client.w - 24, 30 + 4 * 22)
    xp.sunken(surface, lv)
    cols = [("Player", 170), ("This round", 90), ("Total", lv.w - 260)]
    xp.list_header(surface, pygame.Rect(lv.x + 1, lv.y + 1, lv.w - 2, 22), cols)
    f, fb = theme.font(12), theme.font(12, bold=True)
    ry = lv.y + 26
    added = game.last_scores or [0] * 4
    low = min(game.scores)
    for seat in range(4):
        best = over and game.scores[seat] == low
        if best:
            pygame.draw.rect(surface, theme.SELECT, (lv.x + 1, ry - 1, lv.w - 2, 21))
        fg = theme.WHITE if best else theme.TEXT
        pygame.draw.circle(surface, theme.SEAT_COLOURS[seat], (lv.x + 12, ry + 9), 4)
        theme.text(surface, SEATS[seat] + (" (Jev)" if seat == 0 else ""), fb if seat == 0 else f, fg, (lv.x + 22, ry + 2))
        theme.text(surface, f"+{added[seat]}", f, fg, (lv.x + 170 + 6, ry + 2))
        theme.text(surface, str(game.scores[seat]), fb, fg, (lv.x + 260 + 6, ry + 2))
        ry += 22
    b = pygame.Rect(0, 0, 90, 24)
    b.bottomright = (client.right - 12, client.bottom - 12)
    xp.button(surface, b, "New Game" if over else "OK", default=True)
    hint = "Press R to play again." if over else f"Round {game.hand_no + 2} starts shortly."
    theme.text(surface, hint, theme.font(11), theme.TEXT_DIM, (client.x + 12, b.centery), "midleft")
