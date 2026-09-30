"""Render the whole window headless through a full hand: no crashes in any phase."""

import os

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")

import pygame  # noqa: E402
import pytest  # noqa: E402

from jev_agent.jev import HeuristicJev  # noqa: E402
from ui.app import WINDOW, Driver, render  # noqa: E402
from ui.console_panel import ConsoleLog  # noqa: E402


@pytest.fixture(scope="module")
def screen():
    pygame.init()
    yield pygame.display.set_mode(WINDOW)
    pygame.quit()


def test_renders_every_phase(screen):
    d = Driver(HeuristicJev(), seed=2, target=100, delay_ms=0, log=ConsoleLog())
    phases = set()
    t = 0.0
    for _ in range(400):
        t += 0.01
        d.update(t)
        render(screen, d, t)
        phases.add(d.game.phase)
        if d.game.hand_no == 1:
            break
    assert {"pass", "play", "hand_over"} <= phases
    assert d.panel.history and d.log.lines


def test_small_window_layout(screen):
    small = pygame.Surface((1100, 700))
    d = Driver(HeuristicJev(), seed=2, target=100, delay_ms=0, log=ConsoleLog())
    d.update(0.0)
    render(small, d, 0.0)
