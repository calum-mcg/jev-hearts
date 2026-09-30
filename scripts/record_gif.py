"""Record the README demo GIF: run the real app off-screen for one round and save its frames.

Run: `uv run --with pillow python scripts/record_gif.py --eval-seed 1044`
(Pillow is only needed here, so it isn't a project dependency.)
"""

from __future__ import annotations

import argparse
import os
import time

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")

import pygame  # noqa: E402
from PIL import Image  # noqa: E402

from hearts.game import HeartsGame  # noqa: E402
from jev_agent import config  # noqa: E402
from jev_agent.jev import make_jev  # noqa: E402
from ui.app import WINDOW, Driver, render  # noqa: E402
from ui.console_panel import ConsoleLog  # noqa: E402


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--jev", choices=["heuristic", "remote", "random"], default="remote")
    ap.add_argument("--seed", type=int, default=5)
    ap.add_argument("--eval-seed", type=int, default=None,
                    help="replay the round `jev_agent.evaluate` plays for this seed (same deal as the benchmark)")
    ap.add_argument("--delay-ms", type=float, default=300, help="pause between moves")
    ap.add_argument("--seconds", type=float, default=60, help="maximum length of the recording")
    ap.add_argument("--hold", type=float, default=3, help="seconds to keep recording on the Score Sheet")
    ap.add_argument("--skip", type=float, default=0, help="seconds to run before recording starts")
    ap.add_argument("--fps", type=float, default=8)
    ap.add_argument("--width", type=int, default=960, help="GIF width in pixels (height keeps the aspect)")
    ap.add_argument("--out", default="docs/demo.gif")
    args = ap.parse_args()
    config.load_env()

    pygame.init()
    screen = pygame.display.set_mode(WINDOW)
    driver = Driver(make_jev(args.jev, seed=args.seed), args.seed, 100, args.delay_ms, ConsoleLog(),
                    config.model() if args.jev == "remote" else None)
    if args.eval_seed is not None:  # same deal and pass direction as evaluate.play_hand
        game = HeartsGame(seed=args.eval_seed)
        game.hand_no = args.eval_seed % 4 - 1
        game.next_hand()
        game.drain_events()
        driver.game = game
    size = (args.width, round(args.width * WINDOW[1] / WINDOW[0]))
    frames: list[Image.Image] = []
    palette: Image.Image | None = None
    start = time.perf_counter()
    next_frame = start + args.skip
    clock = pygame.time.Clock()
    ended_at: float | None = None  # when the first round finished
    while (now := time.perf_counter()) < start + args.skip + args.seconds:
        if driver.game.phase in ("hand_over", "game_over"):
            ended_at = ended_at or now
            if now - ended_at >= args.hold:
                break  # one full round, ending on the Score Sheet
        pygame.event.pump()
        if ended_at is None:
            driver.update(now)  # freeze on the Score Sheet instead of dealing the next round
        if now >= next_frame:
            render(screen, driver, now)
            img = Image.frombytes("RGB", WINDOW, pygame.image.tobytes(screen, "RGB")).resize(size, Image.LANCZOS)
            if palette is None:  # one shared palette keeps colours steady from frame to frame
                palette = img.quantize(colors=256, method=Image.Quantize.MEDIANCUT)
            frames.append(img.quantize(palette=palette, dither=Image.Dither.NONE))
            next_frame += 1 / args.fps
        clock.tick(60)
    pygame.quit()

    os.makedirs(os.path.dirname(args.out) or ".", exist_ok=True)
    frames[0].save(args.out, save_all=True, append_images=frames[1:], duration=round(1000 / args.fps),
                   loop=0, optimize=True)
    print(f"saved {args.out}: {len(frames)} frames, {size[0]}x{size[1]}, {os.path.getsize(args.out) / 1e6:.1f} MB")
    g = driver.game
    if g.last_scores is not None:
        taker = g.queen_taker()
        print(f"round result: South +{g.last_scores[0]}, all {g.last_scores}, "
              f"Q♠ taken by {['South', 'West', 'North', 'East'][taker] if taker is not None else '-'}")


if __name__ == "__main__":
    main()
