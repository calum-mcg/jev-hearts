"""One window: the table (top-left), Jev's decisions (right), the console (bottom).

`Driver` runs the game at a watchable pace. Bots act after a delay. For South it asks
Jev, shows the probabilities as soon as the answer lands, then plays the card one delay
later, so you can read the bars before the card moves.
"""

from __future__ import annotations

import time
from concurrent.futures import Future

import pygame

from hearts.bots import HeuristicBot
from hearts.game import HeartsGame, Trick
from jev_agent import describe
from jev_agent.jev import Jev, JevDecision

from . import console_panel, jev_panel, table, theme, xp
from .console_panel import ConsoleLog

WINDOW = (1600, 900)
MIN_DELAY_MS, MAX_DELAY_MS = 60, 5000
JEV_SEAT = 0


class Driver:
    def __init__(self, jev: Jev, seed: int | None, target: int, delay_ms: float, log: ConsoleLog,
                 model: str | None = None) -> None:
        self.jev, self.seed, self.target, self.log = jev, seed, target, log
        self.delay_ms = delay_ms
        self.paused = False
        self.step = False
        self.games = 0
        self.panel = jev_panel.PanelState(jev.name, model)
        self.new_game()

    @property
    def delay(self) -> float:
        return self.delay_ms / 1000

    def new_game(self) -> None:
        seed = None if self.seed is None else self.seed + self.games
        self.games += 1
        self.game = HeartsGame(seed=seed, target=self.target)
        self.bots = {s: HeuristicBot() for s in range(4) if s != JEV_SEAT}
        self.future: Future[JevDecision] | None = None
        self.ready: JevDecision | None = None  # answered, waiting to be played
        self.shown_trick: Trick | None = None
        self.next_at = 0.0
        self.log.add("sys", f"New game {self.games}" + (f" (seed {seed})" if seed is not None else "")
                     + f" · Jev = {self.jev.name} · first to {self.target} loses")
        self._drain()

    def _drain(self) -> None:
        for e in self.game.drain_events():
            self.log.add(e.kind, e.text)

    def view(self) -> table.TableView:
        return table.TableView(
            highlight=self.ready.choice if self.ready else None,
            thinking=self.future is not None,
            shown_trick=self.shown_trick,
            paused=self.paused,
        )

    def update(self, now: float) -> None:
        self._poll(now)
        if self.paused and not self.step:
            return
        if now < self.next_at and not self.step:
            return
        g = self.game
        if g.phase == "hand_over":
            self.shown_trick = None
            g.next_hand()
            self._drain()
            self.next_at = now + self.delay
            self.step = False
            return
        d = g.pending()
        if d is None:
            return
        if d.seat == JEV_SEAT:
            if self.ready is not None:
                card, self.ready = self.ready.choice, None
                self._apply(card, now)
            elif self.future is None:
                obs = g.observation(JEV_SEAT)
                self.future = self.jev.decide(obs)
                self.panel.thinking_since = now
                self.panel.thinking_title = describe.title(obs)
                self.panel.thinking_options = list(obs.options)
                self._poll(now)
        else:
            self._apply(self.bots[d.seat].choose(g.observation(d.seat)), now)

    def _poll(self, now: float) -> None:
        if self.future is None or not self.future.done():
            return
        d = self.future.result()
        self.future = None
        self.ready = d
        self.panel.thinking_since = None
        self.panel.current = d
        g = self.game
        tag = f"R{g.hand_no + 1} " + (f"pass{len(g.pass_picks[JEV_SEAT]) + 1}" if d.kind == "pass"
                                       else f"T{len(g.tricks) + 1:<2}")
        self.panel.history.append((tag, d))
        if d.source in ("jev", "fallback"):
            self.panel.requests += 1
        del self.panel.history[:-40]
        lat = [h.latency_ms for _, h in self.panel.history if h.latency_ms is not None]
        if lat:
            self.panel.avg_latency_ms = sum(lat[-20:]) / len(lat[-20:])
        p = f"{d.chosen_p * 100:.0f}%" if d.chosen_p is not None else "–"
        extra = f" · {d.latency_ms:.0f} ms" if d.latency_ms is not None else ""
        if d.confidence is not None:
            extra += f" · conf {d.confidence:.2f}"
        self.log.add("jev", f"{d.title}: {d.choice.label} (p {p}, {len(d.options)} option{'s' if len(d.options) != 1 else ''}, {d.source}){extra}")
        if d.error:
            self.log.add("error", f"Jev error: {d.error} → heuristic played {d.choice.label}")
        # Let the bars be read before the card moves.
        self.next_at = max(self.next_at, now + (0 if d.source == "forced" else self.delay))

    def _apply(self, card, now: float) -> None:
        g = self.game
        was_pass = g.phase == "pass"
        tricks_before = len(g.tricks)
        seat = g.pending().seat
        if g.trick:
            self.shown_trick = None
        g.apply(card)
        self._drain()
        self.step = False
        if len(g.tricks) > tricks_before:
            self.shown_trick = g.tricks[-1]
            self.next_at = now + self.delay * (4 if g.phase in ("hand_over", "game_over") else 2)
        elif was_pass and seat != JEV_SEAT:
            self.next_at = now + self.delay * 0.15
        else:
            self.next_at = now + self.delay

    def faster(self) -> None:
        self.delay_ms = max(MIN_DELAY_MS, self.delay_ms / 1.4)

    def set_speed(self, name: str) -> None:
        self.delay_ms = SPEEDS[name]
        self.log.add("sys", f"Speed: {name} ({self.delay_ms} ms per move).")

    def toggle_pause(self) -> None:
        self.paused = not self.paused
        self.log.add("sys", "Paused." if self.paused else "Resumed.")

    def action(self, name: str) -> None:
        """A toolbar button or shortcut."""
        if name == "pause":
            self.toggle_pause()
        elif name == "step":
            self.step = True
        elif name == "new":
            self.new_game()
        elif name in SPEEDS:
            self.set_speed(name)

    def slower(self) -> None:
        self.delay_ms = min(MAX_DELAY_MS, self.delay_ms * 1.4)


def layout(size: tuple[int, int]) -> tuple[pygame.Rect, pygame.Rect, pygame.Rect]:
    """Window rects (Hearts, Jev monitor, cmd) on the desktop."""
    w, h = size
    m = 10
    desk_h = h
    panel_w = max(460, int(w * 0.33))
    left_w = w - panel_w - 3 * m
    table_h = int((desk_h - 3 * m) * 0.67)
    tbl = pygame.Rect(m, m, left_w, table_h)
    con = pygame.Rect(m, tbl.bottom + m, left_w, desk_h - tbl.bottom - 2 * m)
    pnl = pygame.Rect(tbl.right + m, m, panel_w, desk_h - 2 * m)
    return tbl, pnl, con


KEYS_HINT = "Space pause · N step · 1-4 speed · R new game"
SPEEDS = {"Slow": 1500, "Normal": 700, "Fast": 250, "Turbo": 60}


def _toolbar(screen: pygame.Surface, client: pygame.Rect, driver: Driver) -> tuple[pygame.Rect, list]:
    """Pause / Step | Speed: Slow Normal Fast Turbo | New game. Returns (area below, hotspots)."""
    bar = xp.toolbar(screen, client)
    mouse = pygame.mouse.get_pos()
    hotspots: list[tuple[pygame.Rect, str]] = []
    x = bar.x + 12

    def btn(label: str, action: str, glyph: str | None = None, checked: bool = False) -> None:
        nonlocal x
        r = pygame.Rect(x, bar.y + 3, xp.toolbar_width(label, glyph), bar.h - 6)
        xp.toolbar_button(screen, r, label, checked, r.collidepoint(mouse), glyph)
        hotspots.append((r, action))
        x = r.right + 2

    btn("Resume" if driver.paused else "Pause", "pause", "play" if driver.paused else "pause", driver.paused)
    btn("Step", "step", "step")
    xp.toolbar_separator(screen, x + 4, bar)
    x += 12
    xp.glyph(screen, "speed", pygame.Rect(x, bar.centery - 5, 12, 12))
    x = theme.text(screen, "Speed:", theme.font(11), theme.TEXT, (x + 17, bar.centery), "midleft").right + 6
    for name, ms in SPEEDS.items():
        btn(name, name, checked=abs(driver.delay_ms - ms) < 1)
    custom = not any(abs(driver.delay_ms - ms) < 1 for ms in SPEEDS.values())
    x = theme.text(screen, f"{driver.delay_ms:.0f} ms/move" + (" (custom)" if custom else ""), theme.font(11),
                   theme.TEXT_DIM, (x + 8, bar.centery), "midleft").right
    xp.toolbar_separator(screen, x + 10, bar)
    x += 18
    btn("New game", "new", "new")
    hint_f = theme.font(11)
    if bar.right - 10 - hint_f.size(KEYS_HINT)[0] > x + 10:
        theme.text(screen, KEYS_HINT, hint_f, theme.TEXT_DIM, (bar.right - 10, bar.centery), "midright")
    area = pygame.Rect(client.x, bar.bottom + 1, client.w, client.bottom - bar.bottom - 1)
    return area, hotspots


def render(screen: pygame.Surface, driver: Driver, now: float) -> list[tuple[pygame.Rect, str]]:
    """Draw everything; returns clickable (rect, action) hotspots."""
    w, h = screen.get_size()
    screen.blit(xp.desktop(w, h), (0, 0))
    tbl, pnl, con = layout((w, h))

    g = driver.game
    title = f"Hearts - Round {g.hand_no + 1}" + (" (Paused)" if driver.paused else "")
    client = xp.window(screen, tbl, title, "hearts")
    client, hotspots = _toolbar(screen, client, driver)
    felt = xp.status_bar(screen, client, table.status_panels(driver.game))
    table.draw(screen, felt, driver.game, driver.view(), now)

    client = xp.window(screen, pnl, "Jev Decision Monitor", "jev")
    area = xp.status_bar(screen, client, jev_panel.status_panels(driver.panel))
    jev_panel.draw(screen, area, driver.panel, now)

    client = xp.window(screen, con, r"C:\WINDOWS\system32\cmd.exe - uv run jev", "cmd", active=False)
    console_panel.draw(screen, client, driver.log, now)

    return hotspots


def run(jev: Jev, seed: int | None = None, target: int = 100, delay_ms: float = 700, model: str | None = None,
        seconds: float | None = None, screenshot: str | None = None, echo: bool = False) -> None:
    pygame.init()
    pygame.display.set_caption("Jev plays Hearts")
    screen = pygame.display.set_mode(WINDOW, pygame.RESIZABLE)
    clock = pygame.time.Clock()
    log = ConsoleLog(echo=echo)
    driver = Driver(jev, seed, target, delay_ms, log, model)
    t0 = time.perf_counter()
    hotspots: list[tuple[pygame.Rect, str]] = []
    speed_keys = {pygame.K_1: "Slow", pygame.K_2: "Normal", pygame.K_3: "Fast", pygame.K_4: "Turbo"}
    running = True
    while running:
        for ev in pygame.event.get():
            if ev.type == pygame.QUIT:
                running = False
            elif ev.type == pygame.KEYDOWN:
                k = ev.key
                if k == pygame.K_ESCAPE:
                    running = False
                elif k == pygame.K_SPACE:
                    driver.toggle_pause()
                elif k in speed_keys:
                    driver.set_speed(speed_keys[k])
                elif k == pygame.K_n:
                    driver.step = True
                elif k in (pygame.K_PLUS, pygame.K_EQUALS, pygame.K_KP_PLUS):
                    driver.faster()
                elif k in (pygame.K_MINUS, pygame.K_KP_MINUS):
                    driver.slower()
                elif k == pygame.K_r:
                    driver.new_game()
            elif ev.type == pygame.MOUSEBUTTONDOWN and ev.button == 1:
                for rect, name in hotspots:
                    if rect.collidepoint(ev.pos):
                        driver.action(name)
                        break
            elif ev.type == pygame.MOUSEWHEEL:
                _, _, con = layout(screen.get_size())
                if con.collidepoint(pygame.mouse.get_pos()):
                    log.on_wheel(ev.y)
        now = time.perf_counter()
        driver.update(now)
        hotspots = render(screen, driver, now)
        pygame.display.flip()
        clock.tick(60)
        if seconds is not None and now - t0 >= seconds:
            if screenshot:
                pygame.image.save(screen, screenshot)
            running = False
    pygame.quit()

