"""RemoteJev: request shape, auth header, answer parsing, fallbacks - against a mock HTTP transport."""

import json

import httpx
import pytest

from hearts.bots import HeuristicBot
from hearts.game import HeartsGame
from jev_agent import config
from jev_agent.jev import HeuristicJev, RemoteJev, build_request, option_keys, parse_answer


def south_decision(kind: str, seed: int = 3):
    game = HeartsGame(seed=seed)
    bot = HeuristicBot()
    while True:
        d = game.pending()
        obs = game.observation(d.seat)
        if d.seat == 0 and d.kind == kind and len(d.options) > 1:
            return obs
        game.apply(bot.choose(obs))


@pytest.fixture(autouse=True)
def api_env(monkeypatch):
    monkeypatch.setenv("JEV_API_KEY", "test-key")
    monkeypatch.setenv("JEV_MODEL", "jev-test")
    monkeypatch.delenv("JEV_API_URL", raising=False)


def make_remote(handler) -> tuple[RemoteJev, list[httpx.Request]]:
    seen: list[httpx.Request] = []

    def wrapped(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return handler(request)

    return RemoteJev(transport=httpx.MockTransport(wrapped)), seen


def test_request_options_are_the_legal_cards():
    obs = south_decision("play")
    body = build_request(obs, model="jev-test")
    assert body["model"] == "jev-test"
    (qid, q), = body["questions"].items()
    assert qid == "card" and q["type"] == "choice"
    # neutral keys, one per legal card; each criterion names its card
    keys = option_keys(obs)
    assert set(q["criteria"]) == set(keys) == {f"option{i}" for i in range(1, len(obs.options) + 1)}
    for k, card in keys.items():
        assert card.label in q["criteria"][k]
    json.dumps(body)


def test_remote_decision_uses_answer_and_probabilities():
    obs = south_decision("play")
    pick = obs.options[-1]
    other = obs.options[0]

    keys = {c: k for k, c in option_keys(obs).items()}

    def handler(request):
        body = json.loads(request.content)
        assert set(body["questions"]["card"]["criteria"]) == set(keys.values())
        answer = {"choice": keys[pick], "probabilities": {keys[pick]: 0.8, keys[other]: 0.2}, "confidence": 0.9}
        return httpx.Response(200, json={"answers": {"card": answer}})

    jev, seen = make_remote(handler)
    d = jev.decide(obs).result(timeout=5)
    assert seen[0].headers["authorization"] == "Bearer test-key"
    assert seen[0].url == config.DEFAULT_API_URL
    assert d.source == "jev" and d.choice == pick
    assert d.probabilities == {pick.id: 0.8, other.id: 0.2}
    assert d.chosen_p == 0.8 and d.confidence == 0.9 and d.latency_ms is not None


def test_pass_uses_pass_question():
    obs = south_decision("pass")

    def handler(request):
        body = json.loads(request.content)
        assert list(body["questions"]) == ["pass"]
        return httpx.Response(200, json={"pass": {"choice": obs.options[0].id.lower()}})

    jev, _ = make_remote(handler)
    d = jev.decide(obs).result(timeout=5)
    assert d.kind == "pass" and d.choice == obs.options[0]


def test_illegal_answer_falls_back_to_heuristic():
    obs = south_decision("play")
    illegal = next(c for c in obs.hand if c not in obs.options) if len(obs.hand) > len(obs.options) else None
    choice = illegal.id if illegal else "XX"
    jev, _ = make_remote(lambda r: httpx.Response(200, json={"card": {"choice": choice}}))
    d = jev.decide(obs).result(timeout=5)
    assert d.source == "fallback" and d.choice in obs.options and "not a legal card" in d.error


def test_http_error_falls_back_to_heuristic():
    obs = south_decision("play")
    jev, _ = make_remote(lambda r: httpx.Response(500, text="boom"))
    d = jev.decide(obs).result(timeout=5)
    assert d.source == "fallback" and "HTTP 500" in d.error
    assert d.choice == HeuristicBot().choose(obs)


def test_single_legal_card_makes_no_call():
    game = HeartsGame(seed=3)
    bot = HeuristicBot()
    while True:
        d = game.pending()
        obs = game.observation(d.seat)
        if d.seat == 0 and d.kind == "play" and len(d.options) == 1:
            break
        game.apply(bot.choose(obs))
    jev, seen = make_remote(lambda r: httpx.Response(500))
    dec = jev.decide(obs).result(timeout=5)
    assert dec.source == "forced" and dec.probabilities == {obs.options[0].id: 1.0} and not seen


def test_parse_answer_finds_nested():
    assert parse_answer({"results": {"card": {"choice": "QS"}}}, "card")["choice"] == "QS"
    with pytest.raises(ValueError):
        parse_answer({"nope": 1}, "card")


def test_heuristic_jev_probabilities_sum_to_one():
    obs = south_decision("play")
    d = HeuristicJev().decide(obs).result()
    assert d.source == "heuristic"
    assert sum(d.probabilities.values()) == pytest.approx(1.0)
    assert max(d.probabilities, key=d.probabilities.get) == d.choice.id
