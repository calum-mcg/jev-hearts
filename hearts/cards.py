"""Cards and suits. A card's `id` (e.g. "QS", "10H") is what Jev sees as an option key."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class Suit(Enum):
    CLUBS = "C"
    DIAMONDS = "D"
    SPADES = "S"
    HEARTS = "H"

    @property
    def symbol(self) -> str:
        return {"C": "♣", "D": "♦", "S": "♠", "H": "♥"}[self.value]

    @property
    def plural(self) -> str:
        return self.name.lower()

    @property
    def red(self) -> bool:
        return self in (Suit.DIAMONDS, Suit.HEARTS)

    @property
    def order(self) -> int:
        """Display order in a hand: clubs, diamonds, spades, hearts."""
        return list(Suit).index(self)


RANK_NAMES = {11: "J", 12: "Q", 13: "K", 14: "A"}
RANK_WORDS = {11: "jack", 12: "queen", 13: "king", 14: "ace"}


@dataclass(frozen=True)
class Card:
    rank: int  # 2..14 (ace high)
    suit: Suit

    @property
    def rank_str(self) -> str:
        return RANK_NAMES.get(self.rank, str(self.rank))

    @property
    def id(self) -> str:
        return f"{self.rank_str}{self.suit.value}"

    @property
    def label(self) -> str:
        return f"{self.rank_str}{self.suit.symbol}"

    @property
    def points(self) -> int:
        if self.suit is Suit.HEARTS:
            return 1
        return 13 if self == QUEEN_SPADES else 0

    @property
    def sort_key(self) -> tuple[int, int]:
        return self.suit.order, self.rank

    @classmethod
    def parse(cls, text: str) -> Card:
        """Inverse of `id` (case-insensitive; also accepts "T" for ten)."""
        t = text.strip().upper()
        suit, rank = Suit(t[-1]), t[:-1]
        inverse = {v: k for k, v in RANK_NAMES.items()} | {"T": 10}
        return cls(inverse[rank] if rank in inverse else int(rank), suit)

    def __str__(self) -> str:
        return self.label


QUEEN_SPADES = Card(12, Suit.SPADES)
TWO_CLUBS = Card(2, Suit.CLUBS)


def full_deck() -> list[Card]:
    return [Card(r, s) for s in Suit for r in range(2, 15)]


def sort_hand(cards) -> list[Card]:
    return sorted(cards, key=lambda c: c.sort_key)


def ranks_text(cards) -> str:
    """"A K 7 3" - ranks high to low."""
    return " ".join(c.rank_str for c in sorted(cards, key=lambda c: -c.rank)) or "none"
