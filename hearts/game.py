"""The Hearts state machine: deal -> pass -> 13 tricks -> score, until someone reaches the target.

The game never decides anything itself. `pending()` says whose decision is next (pick a
card to pass, or play a card), and `apply(card)` takes it. Every change is recorded
as an `Event`, which the UI drains for its console. `observation(seat)` is what a player
is allowed to know: its own hand plus everything public.
"""

from __future__ import annotations

import random
from dataclasses import dataclass, field

from .cards import QUEEN_SPADES, TWO_CLUBS, Card, Suit, full_deck, sort_hand
from .rules import (
    N_SEATS,
    PASS_COUNT,
    SEATS,
    hand_scores,
    legal_plays,
    pass_direction,
    pass_target,
    trick_points,
    winning_index,
)


@dataclass(frozen=True)
class Decision:
    seat: int
    kind: str  # "pass" | "play"
    options: tuple[Card, ...]
    pass_round: int = 0  # for "pass": how many cards this seat has already picked


@dataclass(frozen=True)
class Event:
    kind: str  # deal | pass | exchange | play | trick | hand | game | info
    text: str
    seat: int | None = None


@dataclass(frozen=True)
class Trick:
    leader: int
    plays: tuple[tuple[int, Card], ...]  # (seat, card) in play order
    winner: int
    points: int


@dataclass(frozen=True)
class Observation:
    """Everything `seat` may know right now."""

    seat: int
    phase: str
    hand_no: int
    direction: str
    hand: tuple[Card, ...]
    options: tuple[Card, ...]  # legal choices if it's this seat's decision, else ()
    pass_round: int
    pass_picked: tuple[Card, ...]  # cards this seat has picked to pass so far
    passed: tuple[Card, ...]  # after the exchange: what this seat gave away
    received: tuple[Card, ...]  # after the exchange: what it got
    trick: tuple[tuple[int, Card], ...]
    leader: int
    tricks: tuple[Trick, ...]  # completed tricks this hand
    hearts_broken: bool
    points_hand: tuple[int, ...]
    scores: tuple[int, ...]
    voids: tuple[frozenset[Suit], ...]  # suits each seat has shown it's out of
    target: int

    @property
    def trick_no(self) -> int:
        return len(self.tricks) + 1

    @property
    def played(self) -> list[Card]:
        return [c for t in self.tricks for _, c in t.plays] + [c for _, c in self.trick]

    def unseen(self) -> list[Card]:
        """Cards not in this hand and not yet played (held by opponents)."""
        gone = set(self.played) | set(self.hand)
        return [c for c in full_deck() if c not in gone]


@dataclass
class HeartsGame:
    seed: int | None = None
    target: int = 100
    rng: random.Random = field(init=False)

    def __post_init__(self) -> None:
        self.rng = random.Random(self.seed)
        self.scores = [0] * N_SEATS
        self.hand_no = -1
        self.events: list[Event] = []
        self.history: list[list[int]] = []  # per-hand added scores
        self.next_hand()

    # ---- flow -------------------------------------------------------------------

    def next_hand(self) -> None:
        self.hand_no += 1
        deck = full_deck()
        self.rng.shuffle(deck)
        self.hands: list[list[Card]] = [sort_hand(deck[i::N_SEATS]) for i in range(N_SEATS)]
        self.direction = pass_direction(self.hand_no)
        self.pass_picks: list[list[Card]] = [[] for _ in range(N_SEATS)]
        self.passed: list[list[Card]] = [[] for _ in range(N_SEATS)]
        self.received: list[list[Card]] = [[] for _ in range(N_SEATS)]
        self.trick: list[tuple[int, Card]] = []
        self.leader = 0
        self.tricks: list[Trick] = []
        self.hearts_broken = False
        self.points_hand = [0] * N_SEATS
        self.voids: list[set[Suit]] = [set() for _ in range(N_SEATS)]
        self.last_scores: list[int] | None = None
        self.moon: int | None = None
        totals = ", ".join(f"{SEATS[s]} {self.scores[s]}" for s in range(N_SEATS))
        self._emit("deal", f"Round {self.hand_no + 1} dealt. Passing {self.direction}. Totals: {totals}.")
        if self.direction == "hold":
            self._start_play()
        else:
            self.phase = "pass"

    def _start_play(self) -> None:
        self.phase = "play"
        self.leader = next(s for s in range(N_SEATS) if TWO_CLUBS in self.hands[s])
        self._emit("info", f"{SEATS[self.leader]} has the 2♣ and leads.", self.leader)

    def pending(self) -> Decision | None:
        """The next decision to make, or None when the hand/game is over."""
        if self.phase == "pass":
            seat = next(s for s in range(N_SEATS) if len(self.pass_picks[s]) < PASS_COUNT)
            options = tuple(c for c in self.hands[seat] if c not in self.pass_picks[seat])
            return Decision(seat, "pass", options, len(self.pass_picks[seat]))
        if self.phase == "play":
            seat = self.to_play
            return Decision(seat, "play", tuple(self.legal(seat)))
        return None

    @property
    def to_play(self) -> int:
        return (self.leader + len(self.trick)) % N_SEATS

    def legal(self, seat: int) -> list[Card]:
        return legal_plays(self.hands[seat], [c for _, c in self.trick], self.hearts_broken, not self.tricks)

    def apply(self, card: Card) -> None:
        d = self.pending()
        if d is None:
            raise RuntimeError(f"no decision pending (phase {self.phase})")
        if card not in d.options:
            raise ValueError(f"{card} is not a legal {d.kind} for {SEATS[d.seat]}")
        if d.kind == "pass":
            self._pick_pass(d.seat, card)
        else:
            self._play(d.seat, card)

    def _pick_pass(self, seat: int, card: Card) -> None:
        self.pass_picks[seat].append(card)
        if len(self.pass_picks[seat]) == PASS_COUNT:
            to = pass_target(seat, self.direction)
            self._emit("pass", f"{SEATS[seat]} passes 3 cards to {SEATS[to]}.", seat)
        if all(len(p) == PASS_COUNT for p in self.pass_picks):
            self._exchange()

    def _exchange(self) -> None:
        for seat in range(N_SEATS):
            to = pass_target(seat, self.direction)
            cards = self.pass_picks[seat]
            self.passed[seat] = list(cards)
            self.received[to] = list(cards)
            for c in cards:
                self.hands[seat].remove(c)
        for seat in range(N_SEATS):
            self.hands[seat] = sort_hand(self.hands[seat] + self.received[seat])
        self._emit("exchange", "Cards exchanged. "
                   f"South gave {_labels(self.passed[0])}, got {_labels(self.received[0])}.")
        self._start_play()

    def _play(self, seat: int, card: Card) -> None:
        self.hands[seat].remove(card)
        if self.trick and card.suit is not self.trick[0][1].suit:
            self.voids[seat].add(self.trick[0][1].suit)
        if card.suit is Suit.HEARTS and not self.hearts_broken:
            self.hearts_broken = True
            self._emit("info", "Hearts are broken.", seat)
        self.trick.append((seat, card))
        self._emit("play", f"{SEATS[seat]:<5} plays {card.label}", seat)
        if len(self.trick) == N_SEATS:
            self._finish_trick()

    def _finish_trick(self) -> None:
        cards = [c for _, c in self.trick]
        winner = self.trick[winning_index(cards)][0]
        pts = trick_points(cards)
        self.tricks.append(Trick(self.leader, tuple(self.trick), winner, pts))
        self.points_hand[winner] += pts
        suffix = f" and takes {pts} point{'s' if pts != 1 else ''}" if pts else ""
        self._emit("trick", f"Trick {len(self.tricks)}: {SEATS[winner]} wins{suffix}.", winner)
        self.trick = []
        self.leader = winner
        if len(self.tricks) == 13:
            self._finish_hand()

    def _finish_hand(self) -> None:
        added, moon = hand_scores(self.points_hand)
        self.moon = moon
        self.last_scores = added
        self.history.append(added)
        self.scores = [s + a for s, a in zip(self.scores, added)]
        if moon is not None:
            self._emit("hand", f"{SEATS[moon]} shot the moon! Everyone else takes 26.", moon)
        summary = ", ".join(f"{SEATS[s]} +{added[s]} ({self.scores[s]})" for s in range(N_SEATS))
        self._emit("hand", f"Round {self.hand_no + 1} over: {summary}")
        if max(self.scores) >= self.target:
            self.phase = "game_over"
            low = min(self.scores)
            winners = [SEATS[s] for s in range(N_SEATS) if self.scores[s] == low]
            self._emit("game", f"Game over. {' and '.join(winners)} win{'s' if len(winners) == 1 else ''} with {low}.")
        else:
            self.phase = "hand_over"

    # ---- views ------------------------------------------------------------------

    @property
    def last_trick(self) -> Trick | None:
        return self.tricks[-1] if self.tricks else None

    def queen_taker(self) -> int | None:
        """Seat that won the trick containing the Q♠ this round, if it has been taken."""
        for t in self.tricks:
            if any(c == QUEEN_SPADES for _, c in t.plays):
                return t.winner
        return None

    def observation(self, seat: int) -> Observation:
        d = self.pending()
        mine = d is not None and d.seat == seat
        return Observation(
            seat=seat,
            phase=self.phase,
            hand_no=self.hand_no,
            direction=self.direction,
            hand=tuple(self.hands[seat]),
            options=d.options if mine else (),
            pass_round=len(self.pass_picks[seat]),
            pass_picked=tuple(self.pass_picks[seat]),
            passed=tuple(self.passed[seat]),
            received=tuple(self.received[seat]),
            trick=tuple(self.trick),
            leader=self.leader if self.phase != "pass" else 0,
            tricks=tuple(self.tricks),
            hearts_broken=self.hearts_broken,
            points_hand=tuple(self.points_hand),
            scores=tuple(self.scores),
            voids=tuple(frozenset(v) for v in self.voids),
            target=self.target,
        )

    def drain_events(self) -> list[Event]:
        out, self.events = self.events, []
        return out

    def _emit(self, kind: str, text: str, seat: int | None = None) -> None:
        self.events.append(Event(kind, text, seat))


def _labels(cards) -> str:
    return " ".join(c.label for c in cards) or "nothing"
