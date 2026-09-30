"""Shooting-the-moon analysis shared by the bots and by Jev's descriptions.

Taking all 26 points in a hand scores 0 for you and 26 for everyone else. It is only
possible while one player has taken every point so far.
"""

from __future__ import annotations

from .cards import QUEEN_SPADES, Card, Suit
from .game import Observation

MIN_HONOURS = 6  # A/K/Q count in a fresh hand to start a moon attempt
BLOCK_POINTS = 8  # an opponent with this many (and all) points is a real moon threat: block it
MOON_POINTS_IN = 8  # holding all points and at least this many, push for the moon if the cards allow
MAX_LOSERS = 2  # ...and at most this many cards could lose a trick (none of them hearts)


def boss_cards(obs: Observation) -> list[Card]:
    """Cards in hand that no unseen card can beat (sure winners if their suit is led)."""
    unseen = obs.unseen()
    return [c for c in obs.hand if not any(u.suit is c.suit and u.rank > c.rank for u in unseen)]


def winners_and_losers(obs: Observation) -> tuple[list[Card], list[Card]]:
    """Split the hand into cards expected to win a trick and cards that could lose one.

    A card wins if nothing unseen in its suit beats it (a boss), or if it is a length
    winner: once your bosses in that suit have been played the opponents will have run
    out, estimated as unseen cards in the suit <= 3 x your bosses there.
    """
    unseen = obs.unseen()
    hand = [c for c in obs.hand if c not in obs.pass_picked]
    winners: list[Card] = []
    losers: list[Card] = []
    for suit in Suit:
        mine = [c for c in hand if c.suit is suit]
        out = [u for u in unseen if u.suit is suit]
        bosses = [c for c in mine if not any(u.rank > c.rank for u in out)]
        runs_out = len(out) <= 3 * len(bosses)
        for c in mine:
            (winners if c in bosses or runs_out else losers).append(c)
    return winners, losers


def sole_taker(obs: Observation) -> int | None:
    """The only seat to have taken points this hand, or None (no points yet, or split)."""
    takers = [s for s in range(4) if obs.points_hand[s] > 0]
    return takers[0] if len(takers) == 1 else None


def points_left(obs: Observation) -> int:
    """Points not yet taken in a finished trick."""
    return 26 - sum(obs.points_hand)


def should_shoot(obs: Observation) -> bool:
    """Should `obs.seat` try to take every point this hand?"""
    me = obs.seat
    if any(obs.points_hand[s] for s in range(4) if s != me):
        return False  # someone else has points: the moon is gone
    hand = [c for c in obs.hand if c not in obs.pass_picked]
    if not hand:
        return False
    honours = sum(1 for c in hand if c.rank >= 12)
    high_hearts = sum(1 for c in hand if c.suit is Suit.HEARTS and c.rank >= 12)
    hearts = sum(1 for c in hand if c.suit is Suit.HEARTS)
    _, losers = winners_and_losers(obs)
    heart_losers = any(c.suit is Suit.HEARTS for c in losers)
    if obs.points_hand[me] >= MOON_POINTS_IN and obs.phase == "play":
        # Committed: every point so far is yours. Keep going while the cards can win the rest.
        return len(losers) <= MAX_LOSERS and not heart_losers
    fresh = honours >= MIN_HONOURS * len(hand) / 13 and high_hearts >= 1 and hearts >= 3
    return fresh or (len(losers) <= 1 and not heart_losers)


def threat(obs: Observation) -> int | None:
    """An opponent who has taken every point so far and enough of them to be a real moon threat."""
    s = sole_taker(obs)
    if s is None or s == obs.seat:
        return None
    return s if obs.points_hand[s] >= BLOCK_POINTS else None


def status(obs: Observation, seat_names) -> str:
    """One sentence on the state of the moon for the describing seat."""
    me = obs.seat
    if sum(obs.points_hand) == 0:
        return "No points have been taken yet, so anyone could still shoot the moon."
    s = sole_taker(obs)
    if s is None:
        takers = " and ".join(seat_names[p] if p != me else "you" for p in range(4) if obs.points_hand[p])
        return f"Nobody can shoot the moon: points are split between {takers}."
    left = points_left(obs)
    if s == me:
        winners, losers = winners_and_losers(obs)
        sure = " ".join(c.label for c in winners) or "none"
        if should_shoot(obs):
            return (f"Moon is on: you have all {obs.points_hand[me]} points so far and only "
                    f"{len(losers)} card{'s' if len(losers) != 1 else ''} that could lose a trick "
                    f"(sure winners: {sure}). Try to win every one of the {left} remaining points.")
        return (f"You have taken all {obs.points_hand[me]} points so far, but {len(losers)} of your cards could "
                f"lose a trick (sure winners: {sure}), so shooting the moon looks unlikely.")
    return (f"{seat_names[s]} has taken all {obs.points_hand[s]} points so far and could be shooting the moon. "
            f"Taking even one point yourself stops it.")
