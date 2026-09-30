"""Monte Carlo lookahead: what does each option cost, averaged over plausible deals?

For every legal card we sample hands for the three opponents that agree with everything
the deciding seat knows (hand sizes, shown voids, the cards it passed), play the card,
and let heuristic bots finish the round. The average result is what Jev is told.

Sampling uses one fixed set of deals for every option, so differences between options
come from the card, not from luck of the draw.
"""

from __future__ import annotations

import random
from dataclasses import dataclass

from .bots import HeuristicBot
from .cards import Card, Suit, full_deck, sort_hand
from .game import HeartsGame, Observation
from .rules import N_SEATS, PASS_COUNT, hand_scores, pass_target

MOON = 26


@dataclass(frozen=True)
class Estimate:
    """Average outcome of one option over the sampled deals, for the deciding seat."""

    points: float  # points you add to your score this round (moon included)
    others: float  # average points each opponent adds
    moon_against: float  # share of deals where an opponent shot the moon
    moon_for: float  # share of deals where you shot it
    queen: float  # share of deals where you took the Q♠
    n: int

    @property
    def margin(self) -> float:
        """Your points minus the opponents' average: what decides the game."""
        return self.points - self.others


def _hand_sizes(obs: Observation) -> list[int]:
    sizes = []
    in_trick = {s for s, _ in obs.trick}
    for s in range(N_SEATS):
        sizes.append(13 - len(obs.tricks) - (1 if s in in_trick else 0))
    return sizes


def sample_hands(obs: Observation, rng: random.Random) -> list[list[Card]] | None:
    """Opponent hands consistent with what `obs.seat` knows, or None if sampling failed."""
    me = obs.seat
    sizes = _hand_sizes(obs)
    played = set(obs.played)
    hands: list[list[Card]] = [[] for _ in range(N_SEATS)]
    hands[me] = list(obs.hand)
    pool = [c for c in obs.unseen()]
    # Cards we passed are in the receiver's hand until they're played.
    if obs.passed:
        to = pass_target(me, obs.direction)
        for c in obs.passed:
            if c not in played:
                hands[to].append(c)
                pool.remove(c)
    for _ in range(50):
        rng.shuffle(pool)
        # Most constrained seats first: those void in the most suits.
        seats = sorted((s for s in range(N_SEATS) if s != me), key=lambda s: -len(obs.voids[s]))
        trial = [list(h) for h in hands]
        rest = list(pool)
        ok = True
        for s in seats:
            need = sizes[s] - len(trial[s])
            fits = [c for c in rest if c.suit not in obs.voids[s]]
            if len(fits) < need:
                ok = False
                break
            # Leave cards the remaining seats can hold when possible.
            others = [o for o in seats if o != s and len(trial[o]) < sizes[o]]
            fits.sort(key=lambda c: sum(c.suit not in obs.voids[o] for o in others) - rng.random() * 0.5)
            take = fits[:need]
            trial[s].extend(take)
            for c in take:
                rest.remove(c)
        if ok and not rest:
            return [sort_hand(h) for h in trial]
    return None


def _game_from(obs: Observation, hands: list[list[Card]]) -> HeartsGame:
    """A HeartsGame positioned at `obs`, with the given hidden hands, that plays out one round."""
    g = HeartsGame.__new__(HeartsGame)
    g.seed = None
    g.target = 10**9
    g.rng = random.Random(0)
    g.scores = list(obs.scores)
    g.hand_no = obs.hand_no
    g.events = []
    g.history = []
    g.hands = [list(h) for h in hands]
    g.direction = obs.direction
    g.pass_picks = [[] for _ in range(N_SEATS)]
    g.passed = [[] for _ in range(N_SEATS)]
    g.received = [[] for _ in range(N_SEATS)]
    g.passed[obs.seat] = list(obs.passed)
    g.received[obs.seat] = list(obs.received)
    g.trick = list(obs.trick)
    g.leader = obs.leader
    g.tricks = list(obs.tricks)
    g.hearts_broken = obs.hearts_broken
    g.points_hand = list(obs.points_hand)
    g.voids = [set(v) for v in obs.voids]
    g.last_scores = None
    g.moon = None
    g.phase = "play"
    return g


def _finish(g: HeartsGame, bot: HeuristicBot) -> None:
    while g.phase in ("pass", "play"):
        d = g.pending()
        g.apply(bot.choose(g.observation(d.seat)))


def _result(g: HeartsGame, me: int) -> tuple[int, float, bool, bool, bool]:
    added, moon = hand_scores(g.points_hand)
    others = sum(added[s] for s in range(N_SEATS) if s != me) / 3
    took_queen = any(c.rank == 12 and c.suit is Suit.SPADES for t in g.tricks if t.winner == me for _, c in t.plays)
    return added[me], others, moon is not None and moon != me, moon == me, took_queen


def _estimate(results) -> Estimate:
    n = len(results)
    return Estimate(
        points=sum(r[0] for r in results) / n,
        others=sum(r[1] for r in results) / n,
        moon_against=sum(r[2] for r in results) / n,
        moon_for=sum(r[3] for r in results) / n,
        queen=sum(r[4] for r in results) / n,
        n=n,
    )


def play_estimates(obs: Observation, samples: int = 40, seed: int = 0) -> dict[Card, Estimate]:
    """Average outcome of playing each legal card, then heuristic play to the end of the round."""
    rng = random.Random(seed)
    bot = HeuristicBot()
    deals = [h for h in (sample_hands(obs, rng) for _ in range(samples)) if h is not None]
    out: dict[Card, Estimate] = {}
    for card in obs.options:
        results = []
        for hands in deals:
            g = _game_from(obs, hands)
            g.apply(card)
            _finish(g, bot)
            results.append(_result(g, obs.seat))
        out[card] = _estimate(results)
    return out


def pass_estimates(obs: Observation, samples: int = 24, seed: int = 0) -> dict[Card, Estimate]:
    """Average outcome of passing each card (with the cards already picked), then heuristic play.

    The other hands are unknown before the pass, so each sample deals the 39 unseen cards at
    random; every seat then passes and plays as the heuristic would.
    """
    rng = random.Random(seed)
    bot = HeuristicBot()
    me = obs.seat
    unseen = [c for c in full_deck() if c not in obs.hand]
    deals = []
    for _ in range(samples):
        rng.shuffle(unseen)
        others = [s for s in range(N_SEATS) if s != me]
        hands: list[list[Card]] = [[] for _ in range(N_SEATS)]
        hands[me] = list(obs.hand)
        for i, s in enumerate(others):
            hands[s] = sort_hand(unseen[i * 13:(i + 1) * 13])
        deals.append(hands)
    out: dict[Card, Estimate] = {}
    for card in obs.options:
        results = []
        for hands in deals:
            g = HeartsGame.__new__(HeartsGame)
            g.seed, g.target, g.rng = None, 10**9, random.Random(0)
            g.scores, g.hand_no, g.events, g.history = list(obs.scores), obs.hand_no, [], []
            g.hands = [list(h) for h in hands]
            g.direction = obs.direction
            g.pass_picks = [[] for _ in range(N_SEATS)]
            g.pass_picks[me] = list(obs.pass_picked) + [card]
            g.passed = [[] for _ in range(N_SEATS)]
            g.received = [[] for _ in range(N_SEATS)]
            g.trick, g.leader, g.tricks = [], 0, []
            g.hearts_broken, g.points_hand = False, [0] * N_SEATS
            g.voids = [set() for _ in range(N_SEATS)]
            g.last_scores, g.moon, g.phase = None, None, "pass"
            # Our own remaining picks follow the heuristic too.
            while g.phase == "pass":
                d = g.pending()
                g.apply(bot.choose(g.observation(d.seat)))
            _finish(g, bot)
            results.append(_result(g, me))
        out[card] = _estimate(results)
    return out


def estimates(obs: Observation, **kw) -> dict[Card, Estimate]:
    return pass_estimates(obs, **kw) if obs.phase == "pass" else play_estimates(obs, **kw)


class LookaheadBot:
    """Plays the option with the best simulated result. A yardstick for what the estimates are worth."""

    name = "lookahead"

    def __init__(self, samples: int = 40, relative: bool = False, pass_samples: int = 0) -> None:
        self.samples, self.relative, self.pass_samples = samples, relative, pass_samples
        self._fallback = HeuristicBot()
        self._n = 0

    def choose(self, obs: Observation) -> Card:
        if len(obs.options) == 1:
            return obs.options[0]
        if obs.phase == "pass":
            if not self.pass_samples:
                return self._fallback.choose(obs)
            est = pass_estimates(obs, samples=self.pass_samples, seed=self._n)
        else:
            est = play_estimates(obs, samples=self.samples, seed=self._n)
        self._n += 1
        key = (lambda c: est[c].margin) if self.relative else (lambda c: est[c].points)
        return min(obs.options, key=key)
