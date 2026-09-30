"""The language state and per-card criteria Jev reads."""

import json

from hearts.cards import Card
from hearts.game import Observation, Trick
from jev_agent import describe

C = Card.parse


def make_obs(**over) -> Observation:
    base = dict(
        seat=0, phase="play", hand_no=0, direction="left",
        hand=tuple(map(C, ["4S", "QS", "KS", "3H", "10H", "7D"])),
        options=tuple(map(C, ["4S", "QS", "KS"])),
        pass_round=3, pass_picked=(), passed=tuple(map(C, ["AS", "AH", "KH"])),
        received=tuple(map(C, ["2D", "3D", "4D"])),
        trick=((1, C("9S")), (2, C("JS"))), leader=1,
        tricks=(Trick(0, ((0, C("2C")), (1, C("AC")), (2, C("3C")), (3, C("5D"))), 1, 0),),
        hearts_broken=False, points_hand=(0, 0, 0, 0), scores=(10, 20, 30, 40),
        voids=(frozenset(), frozenset(), frozenset(), frozenset({C("2C").suit})), target=100,
    )
    base.update(over)
    return Observation(**base)


def test_state_is_plain_language_and_json():
    obs = make_obs()
    s = describe.build_state(obs)
    json.dumps(s)
    assert s["situation"].startswith("Round 1, trick 2 of 13. West led spades; North is winning with the J♠.")
    assert "1 player still to play after you" in s["situation"]
    assert "You hold the Q♠." in s["situation"]
    assert s["your_hand"]["spades"] == "K Q 4"
    assert s["passing"] == "You passed A♠ A♥ K♥ to West. You received 2♦ 3♦ 4♦ from East."
    assert "known to be out of clubs" in s["opponents"]["East"]
    assert s["current_trick"] == ["West played 9♠", "North played J♠"]


def test_play_criteria_describe_consequences():
    qid, q = describe.question(make_obs())
    assert qid == "card"
    crit = q["criteria"]
    assert set(crit) == {"4S", "QS", "KS"}
    assert "can't win, so you take 0 points" in crit["4S"]
    assert "queen of spades" in crit["QS"] and "takes the lead from the J♠" in crit["QS"]
    assert "A" in crit["KS"]  # the ace is still out


def test_discard_criterion_names_current_winner():
    obs = make_obs(trick=((1, C("9C")), (2, C("JC"))), options=tuple(map(C, ["QS", "3H", "7D"])))
    crit = describe.question(obs)[1]["criteria"]
    assert "you have no clubs, so it can't win" in crit["3H"]
    assert "(currently North)" in crit["3H"]
    assert "empties your diamonds" in crit["7D"]


def test_pass_question():
    obs = make_obs(phase="pass", pass_round=1, pass_picked=(C("10H"),), passed=(), received=(), trick=(),
                   tricks=(), options=tuple(map(C, ["4S", "QS", "KS", "3H", "7D"])))
    qid, q = describe.question(obs)
    assert qid == "pass"
    assert "card 2 of 3" in q["instructions"]
    assert "13 points" in q["criteria"]["QS"]
    assert "Already chosen to pass: 10♥." in describe.situation(obs)
    assert "still_out" not in describe.build_state(obs)


def test_trick_history_and_void_evidence():
    obs = make_obs()
    assert describe.trick_history(obs) == ["Trick 1: you led 2♣; West A♣, North 3♣, East 5♦ (discard). West won, no points."]
    voids = describe.known_voids(obs)
    assert "East has no clubs (played the 5♦ when you led clubs in trick 1)." in voids
    assert "You have no clubs." in voids
    s = describe.build_state(obs)
    assert s["tricks_this_round"] == describe.trick_history(obs)
    assert "Q♠" not in s["your_sure_winners"]  # the ace and king of spades are still out


def _spade_obs(hand, options, trick, leader):
    return make_obs(hand=tuple(map(C, hand)), options=tuple(map(C, options)), trick=trick, leader=leader,
                    passed=(), received=(), direction="hold")


def test_safe_queen_dump_is_flagged_and_other_options_warned():
    # North led 3♠, East played K♠; South can drop the Q♠ underneath.
    obs = _spade_obs(["5S", "9S", "QS", "7D"], ["5S", "9S", "QS"], ((2, C("3S")), (3, C("KS"))), leader=2)
    crit = describe.question(obs)[1]["criteria"]
    assert "safely gets rid of the Q♠" in crit["QS"]
    assert "keeps the Q♠" in crit["5S"] and "keeps the Q♠" in crit["9S"]


def test_high_spade_warns_about_the_queen():
    # East led 7♠, the Q♠ is unseen, and two players follow South.
    obs = _spade_obs(["3S", "KS", "7D"], ["3S", "KS"], ((3, C("7S")),), leader=3)
    crit = describe.question(obs)[1]["criteria"]
    assert "Danger: the Q♠ is still out" in crit["KS"]
    assert "Danger" not in crit["3S"]


def test_goal_weighs_the_queen_against_hearts():
    assert "as much as all the hearts together" in describe.GOAL


def test_leading_own_queen_is_flagged_very_risky():
    obs = _spade_obs(["QS", "3S", "7D"], ["QS", "3S", "7D"], (), leader=0)
    crit = describe.question(obs)[1]["criteria"]
    assert "Very risky: leading your own Q♠" in crit["QS"]
    assert "Very risky" not in crit["7D"]


def test_duck_with_the_highest_card_that_still_loses():
    # West led the 5♣, North played the 10♣; South holds 3♣ 7♣ 9♣ K♣.
    obs = _spade_obs(["3C", "7C", "9C", "KC", "4D"], ["3C", "7C", "9C", "KC"], ((1, C("5C")), (2, C("10C"))), leader=1)
    crit = describe.question(obs)[1]["criteria"]
    assert "the best duck" in crit["9C"]
    assert "wastes a low card" in crit["3C"] and "wastes a low card" in crit["7C"]
    assert "9♣" not in crit["3C"]  # never name the better card inside a worse option
    assert "take the lead" in crit["KC"] or "win the trick" in crit["KC"]
    from jev_agent.jev import HeuristicJev
    assert HeuristicJev().decide(obs).result().choice == C("9C")
