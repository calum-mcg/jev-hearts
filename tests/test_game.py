"""Full games between bots: the state machine stays consistent."""

from collections import Counter

import pytest

from hearts.bots import HeuristicBot, RandomBot
from hearts.cards import full_deck
from hearts.game import HeartsGame


def play_game(seed: int) -> HeartsGame:
    game = HeartsGame(seed=seed)
    bots = [RandomBot(seed), HeuristicBot(), HeuristicBot(), RandomBot(seed + 1)]
    while game.phase != "game_over":
        d = game.pending()
        if d is None:
            game.next_hand()
            continue
        obs = game.observation(d.seat)
        assert set(obs.options) == set(d.options) and obs.hand == tuple(game.hands[d.seat])
        before = len(game.tricks)
        game.apply(bots[d.seat].choose(obs))
        if len(game.tricks) == 13 and before == 12:
            played = Counter(c for t in game.tricks for _, c in t.plays)
            assert played == Counter(full_deck())  # every card exactly once
            assert sum(t.points for t in game.tricks) == 26
    return game


@pytest.mark.parametrize("seed", [1, 2, 3])
def test_seeded_game_finishes_with_consistent_scores(seed):
    game = play_game(seed)
    assert max(game.scores) >= 100
    for added in game.history:
        assert sum(added) in (26, 78)  # 78 = someone shot the moon
    assert game.scores == [sum(h[s] for h in game.history) for s in range(4)]


def test_same_seed_same_game():
    assert play_game(7).history == play_game(7).history


def test_passing_exchanges_three_cards():
    game = HeartsGame(seed=4)  # hand 1 passes left
    bot = HeuristicBot()
    while game.phase == "pass":
        d = game.pending()
        game.apply(bot.choose(game.observation(d.seat)))
    obs = game.observation(0)
    assert len(obs.passed) == 3 and len(obs.received) == 3
    assert not set(obs.passed) & set(obs.hand)
    assert set(obs.received) <= set(obs.hand)
    assert set(game.observation(1).received) == set(obs.passed)  # South passed to West


def test_illegal_card_is_rejected():
    game = HeartsGame(seed=4)
    d = game.pending()
    not_mine = next(c for c in full_deck() if c not in game.hands[d.seat])
    with pytest.raises(ValueError):
        game.apply(not_mine)
