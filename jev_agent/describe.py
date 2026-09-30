"""Turn an `Observation` into what Jev reads: plain-language state plus per-option criteria.

The Flappy experiments showed that Jev judges well from sentences and badly from raw
numbers, so everything here is pre-digested: who is winning the trick, which high cards
are still out, who is known to be void, and what each card would do if played.
"""

from __future__ import annotations

from hearts.cards import QUEEN_SPADES, Card, Suit, ranks_text
from hearts import moon
from hearts.simulate import Estimate
from hearts.game import Observation
from hearts.rules import PASS_OFFSET, SEATS, pass_target, trick_points, winning_index

# Kept deliberately plain. Jev is a fast pattern-matcher: repeating "Q♠" in the goal and the
# instructions pulled it *towards* options that mention the queen (A/B tested: P(leading your
# own Q♠) fell from 0.39 to 0.13 with a plain goal, plain instructions and numbered option keys).
GOAL = (
    "Take as few points as possible. Each heart is 1 point; the queen of spades is 13 points, as much as "
    "all the hearts together. You take the points in every trick you win. Shooting the moon: whoever takes "
    "all 26 points in a round scores 0 and every opponent scores 26 instead."
)
SUITS_BY_NAME = (Suit.SPADES, Suit.HEARTS, Suit.DIAMONDS, Suit.CLUBS)


def _plural(n: int, word: str) -> str:
    return f"{n} {word}{'' if n == 1 else 's'}"


def _unseen_by_suit(obs: Observation) -> dict[Suit, list[Card]]:
    out: dict[Suit, list[Card]] = {s: [] for s in Suit}
    for c in obs.unseen():
        out[c.suit].append(c)
    return out


def _queen_status(obs: Observation) -> str:
    for t in obs.tricks:
        for seat, c in t.plays:
            if c == QUEEN_SPADES:
                return f"The Q♠ has been played; {SEATS[t.winner]} took it."
    for seat, c in obs.trick:
        if c == QUEEN_SPADES:
            return f"{SEATS[seat]} has just played the Q♠ into this trick."
    if QUEEN_SPADES in obs.hand:
        return "You hold the Q♠."
    if QUEEN_SPADES in obs.passed:
        return f"You passed the Q♠ to {SEATS[pass_target(obs.seat, obs.direction)]}; it has not been played yet."
    return "The Q♠ has not been played yet; an opponent holds it."


def _trick_leader_text(obs: Observation) -> tuple[Card, int] | None:
    if not obs.trick:
        return None
    cards = [c for _, c in obs.trick]
    i = winning_index(cards)
    return cards[i], obs.trick[i][0]


def situation(obs: Observation) -> str:
    s: list[str] = []
    if obs.phase == "pass":
        to = SEATS[pass_target(obs.seat, obs.direction)]
        s.append(f"Round {obs.hand_no + 1}. You are passing 3 cards {obs.direction} to {to} before play starts.")
        if obs.pass_picked:
            s.append(f"Already chosen to pass: {' '.join(c.label for c in obs.pass_picked)}.")
        return " ".join(s)
    s.append(f"Round {obs.hand_no + 1}, trick {obs.trick_no} of 13.")
    lead = _trick_leader_text(obs)
    if lead is None:
        s.append("You are leading this trick.")
    else:
        led = obs.trick[0][1].suit
        card, seat = lead
        pts = trick_points(c for _, c in obs.trick)
        s.append(f"{SEATS[obs.trick[0][0]]} led {led.plural}; {SEATS[seat]} is winning with the {card.label}.")
        s.append(f"The trick holds {_plural(pts, 'point')} so far.")
        after = 3 - len(obs.trick)
        s.append("You play last." if after == 0 else f"{_plural(after, 'player')} still to play after you.")
    s.append("Hearts are broken." if obs.hearts_broken else "Hearts are not broken yet.")
    s.append(_queen_status(obs))
    mine = obs.points_hand[obs.seat]
    s.append(f"You have taken {_plural(mine, 'point')} this round.")
    s.append(moon.status(obs, SEATS))
    return " ".join(s)


def _who(obs: Observation, seat: int) -> str:
    return "you" if seat == obs.seat else SEATS[seat]


def known_voids(obs: Observation) -> list[str]:
    """Every suit a player has shown they're out of, with the evidence."""
    out: list[str] = []
    seen: set[tuple[int, Suit]] = set()
    tricks = [(i + 1, t.plays) for i, t in enumerate(obs.tricks)]
    if obs.trick:
        tricks.append((obs.trick_no, obs.trick))
    for n, plays in tricks:
        led_seat, led = plays[0][0], plays[0][1].suit
        for seat, c in plays[1:]:
            if c.suit is not led and seat != obs.seat and (seat, led) not in seen:
                seen.add((seat, led))
                out.append(f"{SEATS[seat]} has no {led.plural} (played the {c.label} when "
                           f"{_who(obs, led_seat)} led {led.plural} in trick {n}).")
    mine = [s.plural for s in SUITS_BY_NAME if not any(c.suit is s for c in obs.hand)]
    if mine and obs.phase == "play":
        out.append(f"You have no {' or '.join(mine)}.")
    return out


def trick_history(obs: Observation) -> list[str]:
    """One sentence per finished trick this round, in order."""
    lines = []
    for i, t in enumerate(obs.tricks, 1):
        (lead_seat, lead), *rest = t.plays
        follows = ", ".join(
            f"{_who(obs, seat)} {c.label}" + (" (discard)" if c.suit is not lead.suit else "") for seat, c in rest
        )
        took = f" and took {_plural(t.points, 'point')}" if t.points else ", no points"
        winner = _who(obs, t.winner)
        lines.append(f"Trick {i}: {_who(obs, lead_seat)} led {lead.label}; {follows}. "
                     f"{winner[0].upper() + winner[1:]} won{took}.")
    return lines


def hand_text(cards) -> dict[str, str]:
    return {s.plural: ranks_text([c for c in cards if c.suit is s]) for s in SUITS_BY_NAME}


def build_state(obs: Observation) -> dict:
    unseen = _unseen_by_suit(obs)
    state: dict = {
        "game": "Hearts",
        "goal": GOAL,
        "you_are": SEATS[obs.seat],
        "situation": situation(obs),
        "your_hand": hand_text(obs.hand),
    }
    if obs.phase == "play":
        state["tricks_this_round"] = trick_history(obs) or "none yet - this is the first trick"
        state["current_trick"] = [f"{SEATS[seat]} played {c.label}" for seat, c in obs.trick] or "empty - you lead"
        state["known_voids"] = known_voids(obs) or "nobody has shown a void yet"
        boss = moon.boss_cards(obs)
        state["your_sure_winners"] = (
            " ".join(c.label for c in boss) + " - no unplayed card of the same suit can beat these"
            if boss else "none - every card in your hand can still be beaten"
        )
        if obs.passed:
            to = SEATS[pass_target(obs.seat, obs.direction)]
            frm = SEATS[(obs.seat - PASS_OFFSET[obs.direction]) % 4]
            state["passing"] = (
                f"You passed {' '.join(c.label for c in obs.passed)} to {to}. "
                f"You received {' '.join(c.label for c in obs.received)} from {frm}."
            )
        else:
            state["passing"] = "No passing this round."
        state["still_out"] = {
            s.plural: f"{ranks_text(unseen[s])} ({_plural(len(unseen[s]), 'card')} held by opponents)"
            for s in SUITS_BY_NAME
        }
        state["opponents"] = {
            SEATS[p]: _opponent_text(obs, p) for p in range(4) if p != obs.seat
        }
    state["scores"] = {
        SEATS[p]: f"{obs.points_hand[p]} this round, {obs.scores[p]} in the game (game ends at {obs.target})"
        for p in range(4)
    }
    return state


def _opponent_text(obs: Observation, p: int) -> str:
    parts = [f"{_plural(obs.points_hand[p], 'point')} this round"]
    if obs.voids[p]:
        parts.append("known to be out of " + " and ".join(s.plural for s in Suit if s in obs.voids[p]))
    return ", ".join(parts)


# ---- per-option criteria ----------------------------------------------------------------


def play_criterion(obs: Observation, card: Card) -> str:
    """'Result: ...' headline (comparable across options) followed by the detail."""
    return f"Result: {_outcome(obs, card)}. {_play_detail(obs, card)}"


def _moon_outcome(obs: Observation, card: Card) -> str:
    """Result line while shooting the moon: winning point tricks is now the goal."""
    unseen = obs.unseen()
    higher = [c for c in unseen if c.suit is card.suit and c.rank > card.rank]
    if not obs.trick:
        return ("you win the trick - keeps your moon going" if not higher
                else "risky for the moon - an opponent could win this trick and take points")
    cards = [c for _, c in obs.trick]
    win_seat = obs.trick[winning_index(cards)][0]
    pts = trick_points(cards) + card.points
    if _cannot_win(obs, card):
        if pts:
            return f"ends your moon - {SEATS[win_seat]} takes points"
        if len(obs.trick) == 3:
            return "safe for the moon - no points go to anyone else"
        return "safe for now - but a player after you could throw points on this trick"
    if len(obs.trick) == 3 or not higher:
        return "you win the trick - keeps your moon going"
    return "you take the lead - keeps the moon going unless someone plays higher"


def _block_outcome(obs: Observation, card: Card, shooter: int) -> str | None:
    """Result line while an opponent may be shooting the moon (which would cost you 26)."""
    name = SEATS[shooter]
    unseen = obs.unseen()
    higher = [c for c in unseen if c.suit is card.suit and c.rank > card.rank]
    if not obs.trick:
        if card.suit is Suit.HEARTS:
            if not higher:
                return f"stops {name}'s moon for certain - you win this heart trick and take its points"
            return f"a heart trick that {name} may win, keeping their moon going"
        if not higher:
            return f"you win the trick - if anyone throws a point on it, {name}'s moon is stopped"
        return None
    cards = [c for _, c in obs.trick]
    win_seat = obs.trick[winning_index(cards)][0]
    pts = trick_points(cards) + card.points
    if not _cannot_win(obs, card):
        if win_seat != shooter:
            return None
        if pts:
            return f"stops {name}'s moon - you take {_plural(pts, 'point')} instead of risking 26"
        return f"you take the trick from {name} - any point that lands here stops their moon"
    if win_seat == shooter:
        if card.points:
            return f"feeds {name}'s moon - you hand them {_plural(card.points, 'more point')}"
        # Only the good option echoes the goal ("stop the moon"): Jev is drawn to matching words.
        if card.rank >= 11 or not higher:
            return "throws away one of your high cards"
        return f"keeps your high cards, so you can still win a later trick and stop {name}'s moon"
    if card.points:
        return f"gives points to {SEATS[win_seat]} - that stops {name}'s moon"
    return None


def _outcome(obs: Observation, card: Card) -> str:
    """The likely points outcome for you of playing `card`, in a few words."""
    if moon.should_shoot(obs):
        return _moon_outcome(obs, card)
    shooter = moon.threat(obs)
    if shooter is not None and (blocked := _block_outcome(obs, card, shooter)):
        return blocked
    unseen = obs.unseen()
    queen_out = QUEEN_SPADES in unseen and not moon.should_shoot(obs)
    higher = [c for c in unseen if c.suit is card.suit and c.rank > card.rank]
    if not obs.trick:
        if card == QUEEN_SPADES:
            return "you take 13 points for certain" if not higher else "high risk you take the Q♠'s 13 points"
        if card.suit is Suit.SPADES and card.rank > 12 and queen_out:
            return "high risk you take 13 points (the Q♠ can be dropped under it)"
        risk = " - risk of 13 more if the Q♠ is thrown on it" if queen_out else ""
        if not higher:
            hearts = " plus the hearts in it" if card.suit is Suit.HEARTS else ""
            return f"you win the trick{hearts}{risk}"
        return "probably 0 points - a higher card is likely to win" if len(higher) >= 2 else \
            f"you may win the trick - only one higher card is out{risk}"
    cards = [c for _, c in obs.trick]
    if _cannot_win(obs, card):
        why = _danger(obs, card)
        if why:
            return "0 points, guaranteed - and it gets rid of a dangerous card"
        best = _best_duck(obs)
        if card.suit is cards[0].suit and best is not None:
            if card == best:
                return "0 points, guaranteed - the best duck: your highest card that still loses"
            return "0 points, but it wastes a low card"
        return "0 points, guaranteed"
    total = trick_points(cards) + card.points
    if len(obs.trick) == 3:
        return f"you win the trick and take {_plural(total, 'point')} for certain"
    base = (f"you win the trick and take at least {_plural(total, 'point')}" if not higher
            else f"you take the lead for now ({_plural(total, 'point')} in the trick)")
    return base + (" - risk of 13 more if the Q♠ is thrown on it" if queen_out else "")


def _play_detail(obs: Observation, card: Card) -> str:
    unseen = _unseen_by_suit(obs)
    higher = [c for c in unseen[card.suit] if c.rank > card.rank]
    lower = [c for c in unseen[card.suit] if c.rank < card.rank]
    left_after = 3 - len(obs.trick)
    danger = " (the queen of spades, 13 points)" if card == QUEEN_SPADES else ""
    if not obs.trick:
        void_opps = [SEATS[p] for p in range(4) if p != obs.seat and card.suit in obs.voids[p]]
        text = f"Lead the {card.label}{danger}. "
        if not higher:
            text += f"No higher {card.suit.plural} are out, so you would win this trick"
            text += " and take whatever the others throw on it." if card.suit is not Suit.HEARTS else " and take the hearts in it."
        else:
            text += (f"{_plural(len(higher), 'higher ' + card.suit.plural[:-1])} "
                     f"({ranks_text(higher)}) and {len(lower)} lower are still out; you win only if nobody plays higher.")
        if void_opps:
            text += f" {' and '.join(void_opps)} can't follow {card.suit.plural} and may dump points."
        return text + _queen_risk(obs, card) + _shed_note(obs, card)

    cards = [c for _, c in obs.trick]
    led = cards[0].suit
    win = cards[winning_index(cards)]
    win_seat = obs.trick[winning_index(cards)][0]
    pts = trick_points(cards)
    if card.suit is not led:
        worth = (f" It gives {_plural(card.points, 'point')} to whoever wins the trick (currently {SEATS[win_seat]})."
                 if card.points else "")
        note = _moon_note(obs, card, wins=False, win_seat=win_seat, points=pts + card.points)
        return (f"Discard the {card.label}{danger}: you have no {led.plural}, so it can't win.{worth}"
                f"{_shed_note(obs, card)}{note}{_keep_note(obs, card)}")
    if card.rank < win.rank:
        note = _moon_note(obs, card, wins=False, win_seat=win_seat, points=pts)
        return (f"Play the {card.label}{danger} under the winning {win.label}: it can't win, so you take 0 points and nothing thrown on this trick can hurt you."
                f"{_shed_note(obs, card)}{note}{_keep_note(obs, card)}")
    total = pts + card.points
    note = _moon_note(obs, card, wins=True, win_seat=win_seat, points=total)
    note += _queen_risk(obs, card) + _shed_note(obs, card)
    if left_after == 0:
        return (f"Play the {card.label}{danger}: it beats the {win.label} and you play last, so you win the trick "
                f"and take {_plural(total, 'point')}.{note}")
    if not higher:
        return (f"Play the {card.label}{danger}: nothing higher is out, so you win the trick and take its "
                f"{_plural(total, 'point')} plus anything the {_plural(left_after, 'player')} after you throw.{note}")
    return (f"Play the {card.label}{danger}: it takes the lead from the {win.label} "
            f"({_plural(total, 'point')} in the trick). {_plural(len(higher), 'higher card')} ({ranks_text(higher)}) "
            f"{'is' if len(higher) == 1 else 'are'} still out among the {_plural(left_after, 'player')} after you.{note}")


def _moon_note(obs: Observation, card: Card, wins: bool, win_seat: int, points: int) -> str:
    """How this card affects a moon attempt - yours or an opponent's."""
    me = obs.seat
    others_have_points = any(obs.points_hand[s] for s in range(4) if s != me)
    shooter = moon.threat(obs)
    if shooter is not None:
        name = SEATS[shooter]
        if wins and win_seat == shooter:
            return f" It takes the trick away from {name}, stopping their moon attempt."
        if not wins and win_seat == shooter and card.points:
            return f" It feeds {name}'s possible moon."
        if not wins and win_seat != shooter and card.points:
            return f" Giving points to {SEATS[win_seat]} also stops {name}'s moon."
        return ""
    if obs.points_hand[me] > 0 and not others_have_points:
        if wins and points:
            return " Winning these points keeps your moon chance alive."
        if not wins and points:
            return f" Letting {SEATS[win_seat]} take these points ends your moon chance."
    return ""


def _danger(obs: Observation, card: Card) -> str | None:
    """Why holding `card` is risky later in the round, or None if it's a safe card to keep."""
    queen_live = QUEEN_SPADES not in obs.played
    if card == QUEEN_SPADES:
        return "the Q♠ (13 points for whoever wins the trick it lands in)"
    if card.suit is Suit.SPADES and card.rank > 12 and queen_live and QUEEN_SPADES not in obs.hand:
        return f"the {card.label}, which can be forced to win the trick the Q♠ is thrown on"
    if card.suit is Suit.HEARTS and card.rank >= 10:
        return f"the {card.label}, a high heart likely to win a heart trick later"
    if card.rank >= 12:
        return f"the {card.label}, a high card likely to win a trick later, perhaps one full of points"
    return None


def _queen_live_elsewhere(obs: Observation) -> bool:
    """The Q♠ is still in an opponent's hand."""
    return QUEEN_SPADES in obs.unseen()


def _queen_risk(obs: Observation, card: Card) -> str:
    """Could playing `card` end with the Q♠ (13 points) landing on your trick?"""
    if moon.should_shoot(obs):
        return ""
    unseen = obs.unseen()
    if card == QUEEN_SPADES and not obs.trick:
        above = [c for c in unseen if c.suit is Suit.SPADES and c.rank > 12]
        if not above:
            return " Leading your own Q♠ now is certain to win the trick: you take its 13 points yourself."
        return (f" Very risky: leading your own Q♠ means you take its 13 points unless an opponent plays the "
                f"{' or '.join(c.label for c in above)}. Keep it and throw it away on a trick you can't win instead.")
    if QUEEN_SPADES not in unseen:
        return ""  # you hold it, or it has been played
    after = [(obs.seat + i) % 4 for i in range(1, 4 - len(obs.trick))]  # seats still to play after you
    suit = card.suit if not obs.trick else obs.trick[0][1].suit
    left_in_suit = sum(1 for c in unseen if c.suit is suit)
    voids = [SEATS[p] for p in after if suit in obs.voids[p]]
    if not obs.trick:  # leading
        if card.suit is Suit.SPADES and card.rank > 12:
            return (f" Danger: the Q♠ is still out. Leading the {card.label} invites whoever holds it to drop it "
                    "under your card - 13 points to you.")
        if card.suit is Suit.SPADES:
            return " A low spade lead is a safe way to flush out the Q♠: someone above you will have to win it."
        sure = not any(c.suit is suit and c.rank > card.rank for c in unseen)
        if voids:
            return (f" Risk: {' and '.join(voids)} can't follow {suit.plural} and could throw the Q♠ on your "
                    "trick if you win it (13 points).")
        if sure and left_in_suit <= 4:
            return (f" Risk: you will win this trick and only {left_in_suit} {suit.plural} are left among three "
                    "opponents, so someone may be out and throw the Q♠ on it (13 points).")
        if sure:
            return f" You will win this trick, so anyone out of {suit.plural} can throw the Q♠ on it (13 points)."
        return ""
    if not after:
        return ""  # playing last: nothing can be added to the trick
    if suit is Suit.SPADES and card.suit is Suit.SPADES and card.rank > 12:
        return (f" Danger: the Q♠ is still out and a player after you can drop it under your {card.label} - "
                "that is 13 points to you, far worse than any hearts.")
    if voids:
        return (f" Risk: {' and '.join(voids)} can't follow {suit.plural} and could throw the Q♠ on this trick "
                "(13 points to you).")
    return (f" If you end up winning, a player after you who is out of {suit.plural} could throw the Q♠ on "
            "this trick (13 points to you).")


def _best_duck(obs: Observation) -> Card | None:
    """The highest card of the led suit that still loses to the card winning the trick."""
    if not obs.trick:
        return None
    cards = [c for _, c in obs.trick]
    win = cards[winning_index(cards)]
    ducks = [c for c in obs.options if c.suit is cards[0].suit and c.rank < win.rank]
    return max(ducks, key=lambda c: c.rank) if ducks else None


def _cannot_win(obs: Observation, card: Card) -> bool:
    if not obs.trick:
        return False
    cards = [c for _, c in obs.trick]
    return card.suit is not cards[0].suit or card.rank < cards[winning_index(cards)].rank


def _safe_sheds(obs: Observation) -> list[Card]:
    """Dangerous cards that can be thrown away right now without winning the trick (worst first)."""
    sheds = [c for c in obs.options if _cannot_win(obs, c) and _danger(obs, c)]
    return sorted(sheds, key=lambda c: (c != QUEEN_SPADES, c.suit is not Suit.SPADES, -c.rank))


def _shed_note(obs: Observation, card: Card) -> str:
    """Getting rid of dangerous cards on tricks you can't win - or missing the chance to."""
    if moon.should_shoot(obs):
        return ""  # going for the moon: you want to keep winners
    if _cannot_win(obs, card) and (why := _danger(obs, card)):
        return f" This safely gets rid of {why}: you take 0 points now and can't be caught with it later."
    sheds = _safe_sheds(obs)
    if sheds and card not in sheds:
        return (f" But it keeps {_danger(obs, sheds[0])} in your hand, when you could throw it away "
                f"safely right now.")
    return ""


def _keep_note(obs: Observation, card: Card) -> str:
    """What playing `card` now does to the rest of your hand."""
    left = sum(1 for c in obs.hand if c.suit is card.suit) - 1
    notes = []
    if left == 0:
        notes.append(f"It empties your {card.suit.plural}, so you can discard whenever {card.suit.plural} are led.")
    return (" " + " ".join(notes)) if notes else ""


def pass_criterion(obs: Observation, card: Card) -> str:
    """'Result: how risky it is to keep this card' headline, then the detail."""
    return f"Result: {_keep_risk(obs, card)}. {_pass_detail(obs, card)}"


def _keep_risk(obs: Observation, card: Card) -> str:
    """How dangerous `card` is to keep, on a scale shared by every pass option."""
    hand = [c for c in obs.hand if c not in obs.pass_picked]
    low_spades = sum(1 for c in hand if c.suit is Suit.SPADES and c.rank < 12)
    same = sum(1 for c in hand if c.suit is card.suit)
    if card == QUEEN_SPADES:
        return ("high risk to keep - with few low spades the Q♠ can be forced out and cost you 13 points"
                if low_spades < 4 else "fairly safe to keep - enough low spades protect it")
    if card.suit is Suit.SPADES and card.rank > 12:
        return ("risky to keep - it can be forced to win the trick the Q♠ (13 points) lands on"
                if low_spades < 4 else "fairly safe to keep - enough low spades protect it")
    if card.suit is Suit.HEARTS:
        high_hearts = [c for c in hand if c.suit is Suit.HEARTS and c.rank >= 12]
        if card.rank >= 12 and len(high_hearts) == 1:
            return ("worth keeping - one high heart is your best defence against someone shooting the moon, "
                    "and passing it helps the player you give it to")
        return ("somewhat risky to keep - it tends to win heart tricks" if card.rank >= 10
                else "safe to keep - it ducks under other hearts")
    if card.suit is Suit.SPADES:
        return "safe to keep - low spades protect you from the Q♠"
    if card.rank >= 11:
        return "somewhat risky to keep - it may win a trick that points get thrown on"
    if same <= 2:
        return f"passing it helps you run out of {card.suit.plural}"
    return "safe to keep - low cards duck easily" if card.rank <= 6 else "fairly safe to keep"


def _pass_detail(obs: Observation, card: Card) -> str:
    hand = [c for c in obs.hand if c not in obs.pass_picked]
    same = [c for c in hand if c.suit is card.suit]
    low_spades = [c for c in hand if c.suit is Suit.SPADES and c.rank < 12]
    if card == QUEEN_SPADES:
        return (f"Pass the Q♠ (13 points - as much as all the hearts together). You hold "
                f"{_plural(len(low_spades), 'spade')} below the queen to protect it if you keep it; with fewer "
                "than four, passing it is usually right.")
    if card.suit is Suit.SPADES and card.rank > 12:
        return (f"Pass the {card.label}. High spades can be forced to win the trick the Q♠ (13 points) falls "
                f"on; you hold {_plural(len(low_spades), 'low spade')} to protect it.")
    if card.suit is Suit.HEARTS:
        kind = "a high heart that tends to win heart tricks" if card.rank >= 10 else "a low heart that can duck under others"
        return f"Pass the {card.label}: {kind}."
    if card.suit is Suit.SPADES:
        return f"Pass the {card.label}: a low spade, useful for ducking under the Q♠ if you keep it."
    void = f" Passing it leaves {_plural(len(same) - 1, card.suit.plural[:-1])}, moving you toward a void." if len(same) <= 3 else ""
    height = "a high card that may win tricks" if card.rank >= 11 else "a low card that ducks easily" if card.rank <= 6 else "a middling card"
    return f"Pass the {card.label}: {height} in {card.suit.plural} (you hold {len(same)}).{void}"


SIMULATED = (" Each option's Result comes from playing the rest of this round out many times, with the "
             "unseen cards dealt at random: fewer points is better.")


def simulated(est: dict[Card, Estimate], card: Card) -> str:
    """The option's average simulated result, ranked against the best option."""
    e = est[card]
    gap = e.points - min(x.points for x in est.values())
    rank = "the fewest of all options" if gap < 0.05 else f"{gap:.1f} more than the best option"
    text = f"you take {e.points:.1f} points on average ({rank})"
    extras = []
    if e.moon_for >= 0.1:
        extras.append(f"you shoot the moon {e.moon_for:.0%} of the time")
    if e.moon_against >= 0.1:
        extras.append(f"an opponent shoots the moon {e.moon_against:.0%} of the time")
    if e.queen >= 0.1:
        extras.append(f"you take the Q♠ {e.queen:.0%} of the time")
    return text + (" - " + ", ".join(extras) if extras else "")


def _criterion(obs: Observation, card: Card, est: dict[Card, Estimate] | None) -> str:
    base = pass_criterion(obs, card) if obs.phase == "pass" else play_criterion(obs, card)
    if est is None:
        return base
    return f"Result: {simulated(est, card)}. Also: {base.removeprefix('Result: ')}"


def question(obs: Observation, est: dict[Card, Estimate] | None = None) -> tuple[str, dict]:
    """(question id, Choice question) for the decision `obs` is waiting on.

    With `est` (from `hearts.simulate.estimates`), each option leads with its simulated result.
    """
    sim = SIMULATED if est else ""
    criteria = {c.id: _criterion(obs, c, est) for c in obs.options}
    if obs.phase == "pass":
        to = SEATS[pass_target(obs.seat, obs.direction)]
        instructions = (
            f"Your hand is strong enough to shoot the moon. Pick one card to pass to {to} (card "
            f"{obs.pass_round + 1} of 3): your least useful low card." if moon.should_shoot(obs) and not est else
            f"Pick one card to pass to {to} (card {obs.pass_round + 1} of 3): the card that is most dangerous "
            "for you to keep."
        )
        return "pass", {"type": "choice", "instructions": instructions + sim, "criteria": criteria}
    shooter = moon.threat(obs)
    if moon.should_shoot(obs):
        instructions = ("You have every point so far and a strong hand: which card best helps you win every "
                        "trick that has points (shoot the moon)?")
    elif shooter is not None:
        instructions = (f"{SEATS[shooter]} has taken every point so far and may be shooting the moon, which would "
                        "cost you 26. Which card best stops them while keeping your own points low?")
    else:
        instructions = "Which card should you play so that you take the fewest points, now and later in this round?"
    return "card", {"type": "choice", "instructions": instructions + sim, "criteria": criteria}


def title(obs: Observation) -> str:
    """Short header for the UI."""
    if obs.phase == "pass":
        to = SEATS[pass_target(obs.seat, obs.direction)]
        return f"Pass to {to} · card {obs.pass_round + 1} of 3"
    if not obs.trick:
        return f"Trick {obs.trick_no} · leading"
    return f"Trick {obs.trick_no} · following {obs.trick[0][1].suit.symbol}"
