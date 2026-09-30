"""Score a Jev headless against the heuristic bot on identical deals. Lower points are better.

Two modes:

- `--hands N`: N single rounds. Each is played twice from the same seed, once with the
  chosen Jev as South and once with the heuristic bot as South.
- `--games N`: N full games to 100 points, played the same way. South wins a game by
  finishing with the lowest score (a shared lowest score counts as a tie). The deal
  for every round comes from the game's seed, so both runs see the same cards.

The other three seats are always heuristic bots. The remote Jev makes about 15 API calls
per round; games run in parallel, one process each.

Run: `uv run python -m jev_agent.evaluate --jev remote --games 10`
"""

from __future__ import annotations

import argparse
import statistics
from concurrent.futures import ProcessPoolExecutor
from dataclasses import dataclass

from hearts.bots import HeuristicBot
from hearts.game import HeartsGame

from . import config
from .jev import Jev, make_jev


def play_hand(seed: int, south: Jev | None) -> tuple[int, int]:
    """(South's points, number of fallbacks) for one hand. south=None uses the heuristic."""
    game = HeartsGame(seed=seed, target=10_000)
    game.hand_no = seed % 4 - 1  # vary the pass direction with the seed
    game.next_hand()
    bot = HeuristicBot()
    fallbacks = 0
    while game.phase in ("pass", "play"):
        d = game.pending()
        obs = game.observation(d.seat)
        if d.seat == 0 and south is not None:
            decision = south.decide(obs).result()
            fallbacks += decision.source == "fallback"
            card = decision.choice
        else:
            card = bot.choose(obs)
        game.apply(card)
    return game.last_scores[0], fallbacks


@dataclass
class GameResult:
    seed: int
    scores: list[int]  # final totals, South first
    rounds: list[int]  # South's points in each round
    moons_against: int  # rounds an opponent shot the moon
    fallbacks: int

    @property
    def outcome(self) -> str:
        low = min(self.scores)
        if self.scores[0] > low:
            return "loss"
        return "win" if self.scores.count(low) == 1 else "tie"

    @property
    def per_round(self) -> float:
        return statistics.mean(self.rounds)


def play_game(seed: int, south: Jev | None, target: int = 100) -> GameResult:
    """One full game. south=None: the heuristic bot plays South."""
    game = HeartsGame(seed=seed, target=target)
    bot = HeuristicBot()
    fallbacks = moons = 0
    while True:
        d = game.pending()
        if d is None:
            moons += game.moon not in (None, 0)
            if game.phase == "game_over":
                break
            game.next_hand()
            continue
        obs = game.observation(d.seat)
        if d.seat == 0 and south is not None:
            decision = south.decide(obs).result()
            fallbacks += decision.source == "fallback"
            card = decision.choice
        else:
            card = bot.choose(obs)
        game.apply(card)
    return GameResult(seed, list(game.scores), [h[0] for h in game.history], moons, fallbacks)


def _game_worker(args: tuple[str, int, dict]) -> tuple[GameResult, GameResult]:
    name, seed, options = args
    config.load_env()
    jev = make_jev(name, seed=seed, **options)
    return play_game(seed, jev), play_game(seed, None)


def run_games(name: str, seeds: list[int], workers: int, options: dict) -> None:
    ours, base = [], []
    with ProcessPoolExecutor(workers) as pool:
        for mine, ref in pool.map(_game_worker, [(name, s, options) for s in seeds]):
            ours.append(mine)
            base.append(ref)
            print(f"game seed {mine.seed}: {name} {mine.outcome:<4} {_totals(mine.scores)} | "
                  f"heuristic {ref.outcome:<4} {_totals(ref.scores)}", flush=True)
    print()
    for label, res in ((name, ours), ("heuristic", base)):
        wins = sum(r.outcome == "win" for r in res)
        ties = sum(r.outcome == "tie" for r in res)
        rounds = [p for r in res for p in r.rounds]
        print(f"{label:>10}: {wins} wins, {ties} ties of {len(res)} games; "
              f"{statistics.mean(rounds):.2f} points/round over {len(rounds)} rounds; "
              f"{sum(r.moons_against for r in res)} opponent moons")
    fb = sum(r.fallbacks for r in ours)
    if fb:
        print(f"{fb} decisions fell back to the heuristic (API error or illegal answer)")


def _totals(scores: list[int]) -> str:
    return "S{} W{} N{} E{}".format(*scores)


def main(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--jev", choices=["heuristic", "remote", "random"], default="remote")
    ap.add_argument("--hands", type=int, default=20)
    ap.add_argument("--games", type=int, default=0, help="play full games instead of single rounds")
    ap.add_argument("--seed", type=int, default=1000)
    ap.add_argument("--workers", type=int, default=10, help="--games: games played in parallel")
    ap.add_argument("--no-lookahead", action="store_true", help="remote: don't send simulated results")
    args = ap.parse_args(argv)
    config.load_env()
    options = {"lookahead": False} if args.no_lookahead and args.jev == "remote" else {}

    if args.games:
        run_games(args.jev, [args.seed + i for i in range(args.games)], args.workers, options)
        return

    jev = make_jev(args.jev, seed=args.seed, **options)
    ours, base, fb = [], [], 0
    for i in range(args.hands):
        seed = args.seed + i
        pts, f = play_hand(seed, jev)
        ref, _ = play_hand(seed, None)
        ours.append(pts)
        base.append(ref)
        fb += f
        print(f"hand {i + 1:>3} (seed {seed}): {args.jev} {pts:>2}  heuristic {ref:>2}", flush=True)
    print()
    print(f"{args.jev:>10}: {statistics.mean(ours):5.2f} points/hand")
    print(f"{'heuristic':>10}: {statistics.mean(base):5.2f} points/hand")
    if fb:
        print(f"{fb} decisions fell back to the heuristic (API error or illegal answer)")


if __name__ == "__main__":
    main()
