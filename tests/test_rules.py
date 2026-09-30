"""Hearts rules: legal plays, trick winner, passing, scoring."""

import pytest

from hearts.cards import QUEEN_SPADES, TWO_CLUBS, Card, Suit
from hearts.rules import hand_scores, legal_plays, pass_direction, pass_target, winning_index

C = Card.parse


def cards(*ids):
    return [C(i) for i in ids]


def test_card_ids_round_trip():
    for c in cards("2C", "10H", "QS", "AD", "JC"):
        assert Card.parse(c.id) == c
    assert C("TH") == Card(10, Suit.HEARTS)
    assert QUEEN_SPADES.points == 13 and C("AH").points == 1 and C("AS").points == 0


def test_two_of_clubs_leads_first_trick():
    hand = cards("2C", "5C", "AS", "3H")
    assert legal_plays(hand, [], hearts_broken=False, first_trick=True) == [TWO_CLUBS]


def test_must_follow_suit():
    hand = cards("5C", "KC", "AS", "3H")
    assert legal_plays(hand, cards("9C"), False, False) == cards("5C", "KC")


def test_void_can_discard_anything_after_first_trick():
    hand = cards("QS", "3H", "4D")
    assert set(legal_plays(hand, cards("9C"), False, False)) == set(hand)


def test_no_points_on_first_trick_unless_forced():
    hand = cards("QS", "3H", "4D")
    assert legal_plays(hand, cards("2C"), False, True) == cards("4D")
    only_points = cards("QS", "3H")
    assert set(legal_plays(only_points, cards("2C"), False, True)) == set(only_points)


def test_cannot_lead_hearts_until_broken():
    hand = cards("3H", "9H", "4D")
    assert legal_plays(hand, [], hearts_broken=False, first_trick=False) == cards("4D")
    assert set(legal_plays(hand, [], hearts_broken=True, first_trick=False)) == set(hand)
    all_hearts = cards("3H", "9H")
    assert legal_plays(all_hearts, [], False, False) == all_hearts


def test_trick_winner_is_highest_of_led_suit():
    assert winning_index(cards("9C", "AH", "KC", "2C")) == 2
    assert winning_index(cards("3D", "AS", "AH", "AC")) == 0


def test_pass_rotation_and_targets():
    assert [pass_direction(i) for i in range(5)] == ["left", "right", "across", "hold", "left"]
    assert pass_target(0, "left") == 1  # South -> West
    assert pass_target(0, "right") == 3  # South -> East
    assert pass_target(0, "across") == 2


@pytest.mark.parametrize("taken,expected,moon", [
    ([5, 13, 8, 0], [5, 13, 8, 0], None),
    ([0, 26, 0, 0], [26, 0, 26, 26], 1),
])
def test_scoring_and_shooting_the_moon(taken, expected, moon):
    assert hand_scores(taken) == (expected, moon)
