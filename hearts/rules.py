"""Hearts rules: legal plays, trick winner, passing, scoring."""

from __future__ import annotations

from .cards import TWO_CLUBS, Card, Suit, sort_hand

SEATS = ("South", "West", "North", "East")  # play goes clockwise: South -> West -> North -> East
N_SEATS = 4
PASS_DIRECTIONS = ("left", "right", "across", "hold")
PASS_OFFSET = {"left": 1, "across": 2, "right": 3}
PASS_COUNT = 3
MOON_POINTS = 26


def pass_direction(hand_no: int) -> str:
    return PASS_DIRECTIONS[hand_no % 4]


def pass_target(seat: int, direction: str) -> int:
    return (seat + PASS_OFFSET[direction]) % N_SEATS


def legal_plays(hand, trick: list[Card], hearts_broken: bool, first_trick: bool) -> list[Card]:
    """Cards `hand` may play to `trick` (the cards played so far, in order)."""
    hand = sort_hand(hand)
    if not trick:
        if first_trick and TWO_CLUBS in hand:
            return [TWO_CLUBS]
        if not hearts_broken:
            non_hearts = [c for c in hand if c.suit is not Suit.HEARTS]
            if non_hearts:
                return non_hearts
        return hand
    follow = [c for c in hand if c.suit is trick[0].suit]
    if follow:
        return follow
    if first_trick:  # no points on the first trick unless there's no choice
        safe = [c for c in hand if c.points == 0]
        if safe:
            return safe
    return hand


def winning_index(trick: list[Card]) -> int:
    """Index into `trick` of the card currently winning it (highest of the led suit)."""
    led = trick[0].suit
    return max((i for i, c in enumerate(trick) if c.suit is led), key=lambda i: trick[i].rank)


def trick_points(cards) -> int:
    return sum(c.points for c in cards)


def hand_scores(points_taken: list[int]) -> tuple[list[int], int | None]:
    """Scores to add for the hand, and the seat that shot the moon (if any)."""
    for seat, pts in enumerate(points_taken):
        if pts == MOON_POINTS:
            return [0 if s == seat else MOON_POINTS for s in range(N_SEATS)], seat
    return list(points_taken), None
