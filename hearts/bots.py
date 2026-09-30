"""Local players. `HeuristicBot` plays solid, standard Hearts; `RandomBot` plays any legal card.

The heuristic goes for the moon with a strong hand (or once it has taken every point
and still holds winners), and blocks an opponent who looks like they're shooting it.

Both work from an `Observation` only. `scores()` rates every option (higher = better),
which also lets the heuristic stand in for Jev with a probability for each option.
"""

from __future__ import annotations

import random

from .cards import QUEEN_SPADES, Card, Suit
from .game import Observation
from .moon import boss_cards, should_shoot, threat
from .rules import winning_index

ACE_SPADES, KING_SPADES = Card(14, Suit.SPADES), Card(13, Suit.SPADES)


def _suit_count(hand, suit: Suit) -> int:
    return sum(1 for c in hand if c.suit is suit)


def pass_scores(obs: Observation) -> dict[Card, float]:
    """How much each card should be passed (danger of keeping it)."""
    hand = [c for c in obs.hand if c not in obs.pass_picked]
    spades = _suit_count(hand, Suit.SPADES)
    low_spades = sum(1 for c in hand if c.suit is Suit.SPADES and c.rank < 12)
    queen_gone = QUEEN_SPADES in obs.pass_picked
    out: dict[Card, float] = {}
    if should_shoot(obs):  # going for the moon: pass away low cards, keep points and winners
        return {c: 15.0 - c.rank - (40 if c.points else 0) for c in obs.options}
    for c in obs.options:
        n = _suit_count(hand, c.suit)
        if c == QUEEN_SPADES:
            s = 60.0 if low_spades < 4 else 8.0  # well protected by low spades: keep it
        elif c in (ACE_SPADES, KING_SPADES):
            s = 50.0 if (QUEEN_SPADES not in hand or queen_gone) and low_spades < 4 else 12.0
        elif c.suit is Suit.HEARTS:
            s = 2.0 * c.rank - 6
        elif c.suit is Suit.SPADES:
            s = c.rank * 0.5 - (6 if spades <= 3 else 0)  # low spades protect against the queen
        else:
            s = c.rank + (12 - 3 * n if n <= 3 else 0)  # short side suits: pass toward a void
        out[c] = s
    return out


def play_scores(obs: Observation) -> dict[Card, float]:
    if should_shoot(obs):
        return _moon_scores(obs)
    out = _normal_scores(obs)
    t = threat(obs)
    if t is not None and obs.trick:
        _block_moon(obs, t, out)
    return out


def _moon_scores(obs: Observation) -> dict[Card, float]:
    """Trying to take every point: win tricks with points, never give points away."""
    trick = [c for _, c in obs.trick]
    boss = set(boss_cards(obs))
    out: dict[Card, float] = {}
    for c in obs.options:
        if not trick:  # lead sure winners first; otherwise the lowest card
            s = 100.0 + c.rank if c in boss else -float(c.rank)
        elif c.suit is trick[0].suit:
            win = trick[winning_index(trick)]
            if c.rank > win.rank:
                sure = c in boss or len(trick) == 3
                s = 200.0 - c.rank if sure else 100.0 + c.rank  # cheapest sure winner, else highest
            else:
                s = -float(c.rank)
        else:  # discarding: never hand points to someone else
            s = -float(c.rank) - (200 if c.points else 0)
        out[c] = s
    return out


def _block_moon(obs: Observation, shooter: int, out: dict[Card, float]) -> None:
    """Adjust scores to stop `shooter` taking every point."""
    trick = [c for _, c in obs.trick]
    winner_seat = obs.trick[winning_index(trick)][0]
    for c in out:
        if c.suit is trick[0].suit:
            if winner_seat == shooter and c.rank > trick[winning_index(trick)].rank and c != QUEEN_SPADES:
                out[c] = 400.0 - c.rank  # take the trick (and its points) away from the shooter
        elif c.points:
            out[c] += -300 if winner_seat == shooter else 50  # don't feed the shooter; do hand points to others


def _normal_scores(obs: Observation) -> dict[Card, float]:
    options = obs.options
    trick = [c for _, c in obs.trick]
    played = set(obs.played)
    queen_out = QUEEN_SPADES not in played
    out: dict[Card, float] = {}

    if not trick:  # leading
        for c in options:
            s = -float(c.rank)
            if c.suit is Suit.HEARTS:
                s -= 6
            if c.suit is Suit.SPADES and queen_out:
                if c.rank < 12 and QUEEN_SPADES not in obs.hand:
                    s += 6  # flush the queen out
                if c.rank >= 12:
                    s -= 40
            # prefer leading a suit that others still follow
            if any(c.suit in obs.voids[s_] for s_ in range(4) if s_ != obs.seat):
                s -= 8
            out[c] = s
        return out

    led = trick[0].suit
    win = trick[winning_index(trick)]
    pts = sum(c.points for c in trick)
    last = len(trick) == 3
    for c in options:
        if c.suit is led:
            if c.rank < win.rank:  # ducks: highest safe card
                s = 100.0 + c.rank
                if c == QUEEN_SPADES:
                    s += 60  # queen goes to whoever played the A/K
            elif last and pts == 0 and c != QUEEN_SPADES:
                s = 80.0 + c.rank  # free trick: win it with the highest card
            else:
                s = -float(c.rank) - 3 * pts - (100 if c == QUEEN_SPADES else 0)
                if led is Suit.SPADES and queen_out and c in (ACE_SPADES, KING_SPADES) and not last:
                    s -= 30
        else:  # discard
            if c == QUEEN_SPADES:
                s = 300.0
            elif c in (ACE_SPADES, KING_SPADES) and queen_out:
                s = 200.0 + c.rank
            elif c.suit is Suit.HEARTS:
                s = 150.0 + c.rank
            else:
                s = 100.0 + c.rank + 3 * max(0, 3 - _suit_count(obs.hand, c.suit))
        out[c] = s
    return out


def scores(obs: Observation) -> dict[Card, float]:
    return pass_scores(obs) if obs.phase == "pass" else play_scores(obs)


class HeuristicBot:
    name = "heuristic"

    def choose(self, obs: Observation) -> Card:
        s = scores(obs)
        return max(obs.options, key=lambda c: s[c])


class RandomBot:
    name = "random"

    def __init__(self, seed: int | None = None) -> None:
        self.rng = random.Random(seed)

    def choose(self, obs: Observation) -> Card:
        return self.rng.choice(list(obs.options))
