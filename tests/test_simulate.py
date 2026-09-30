"""Monte Carlo lookahead: sampled deals agree with what South knows; estimates cover every option."""

import random

from hearts.bots import HeuristicBot
from hearts.cards import Card, full_deck
from hearts.game import HeartsGame
from hearts.simulate import estimates, sample_hands
from jev_agent import describe


def south_decision(kind: str, seed: int, min_trick: int = 1):
    game = HeartsGame(seed=seed)
    bot = HeuristicBot()
    while True:
        d = game.pending()
        obs = game.observation(d.seat)
        if d.seat == 0 and d.kind == kind and len(d.options) > 1 and obs.trick_no >= min_trick:
            return game, obs
        game.apply(bot.choose(obs))


def test_sampled_hands_are_consistent():
    for seed in range(8):
        game, obs = south_decision("play", seed, min_trick=6)
        rng = random.Random(seed)
        for _ in range(10):
            hands = sample_hands(obs, rng)
            assert hands is not None
            assert hands[0] == list(obs.hand)
            assert [len(h) for h in hands] == [len(h) for h in game.hands]
            dealt = [c for h in hands for c in h]
            assert sorted(dealt, key=Card.sort_key.fget) == sorted(
                [c for c in full_deck() if c not in obs.played], key=Card.sort_key.fget)
            for seat in range(1, 4):
                assert not any(c.suit in obs.voids[seat] for c in hands[seat])
            to = 1 if obs.direction == "left" else 3 if obs.direction == "right" else 2
            if obs.passed:
                assert all(c in hands[to] for c in obs.passed if c not in obs.played)


def test_estimates_cover_options_and_feed_the_question():
    _, obs = south_decision("play", 3)
    est = estimates(obs, samples=6)
    assert set(est) == set(obs.options)
    crit = describe.question(obs, est)[1]["criteria"]
    assert all(t.startswith("Result: you take ") for t in crit.values())
    assert sum("the fewest of all options" in t for t in crit.values()) >= 1


def test_pass_estimates():
    _, obs = south_decision("pass", 3)
    est = estimates(obs, samples=3)
    assert set(est) == set(obs.options)
    assert all(0 <= e.points <= 26 for e in est.values())
