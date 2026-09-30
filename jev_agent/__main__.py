"""Jev plays Hearts as South against three heuristic bots, in one window.

Run: `uv run jev` (or `python -m jev_agent`).
"""

from __future__ import annotations

import argparse
import json
import os
import sys

from . import config


def _first_decision(seed: int | None, kind: str):
    """Advance a game with bots until South faces a real `kind` decision; return its observation."""
    from hearts.bots import HeuristicBot
    from hearts.game import HeartsGame

    game = HeartsGame(seed=seed)
    bot = HeuristicBot()
    for _ in range(2000):
        d = game.pending()
        if d is None:
            game.next_hand()
            continue
        obs = game.observation(d.seat)
        if d.seat == 0 and d.kind == kind and len(d.options) > 1 and (kind == "pass" or game.tricks):
            return obs
        game.apply(bot.choose(obs))
    raise RuntimeError("no suitable decision found")


def main(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--jev", choices=["heuristic", "remote", "random"], default="heuristic",
                    help="who decides for South (heuristic needs no API key)")
    ap.add_argument("--seed", type=int, default=None, help="reproducible deals")
    ap.add_argument("--delay-ms", type=float, default=700, help="pause between moves (adjust live with +/-)")
    ap.add_argument("--target", type=int, default=100, help="the game ends when someone reaches this score")
    ap.add_argument("--model", default=None, help="remote: model id (overrides JEV_MODEL)")
    ap.add_argument("--print-request", choices=["play", "pass"], nargs="?", const="play", default=None,
                    help="print one real Jev request body (JSON) and exit")
    ap.add_argument("--echo", action="store_true", help="also print console lines to stdout")
    ap.add_argument("--seconds", type=float, default=None, help="quit after this many seconds")
    ap.add_argument("--screenshot", default=None, help="with --seconds: save the last frame to this PNG")
    args = ap.parse_args(argv)
    config.load_env()
    if args.model:
        os.environ["JEV_MODEL"] = args.model

    from .jev import build_request, make_jev

    if args.print_request:
        sys.stdout.reconfigure(encoding="utf-8")
        from hearts.simulate import estimates

        obs = _first_decision(args.seed, args.print_request)
        print(json.dumps(build_request(obs, config.model(), estimates(obs)), indent=2, ensure_ascii=False))
        return

    from ui.app import run

    jev = make_jev(args.jev, seed=args.seed)
    run(jev, seed=args.seed, target=args.target, delay_ms=args.delay_ms,
        model=config.model() if args.jev == "remote" else None,
        seconds=args.seconds, screenshot=args.screenshot, echo=args.echo)


if __name__ == "__main__":
    main()
