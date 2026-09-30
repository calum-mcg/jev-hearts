"""Jev: the fast "system-1" decision maker. Observation in, a card (with probabilities) out.

Every Jev returns a `Future[JevDecision]` so the UI never blocks on the API. A
decision carries the probability of every option, which the panel draws as bars.
"""

from __future__ import annotations

import math
import threading
import time
from concurrent.futures import Future, ThreadPoolExecutor
from dataclasses import dataclass, field
from typing import Protocol

from hearts.bots import HeuristicBot, scores
from hearts.cards import Card
from hearts.game import Observation
from hearts.simulate import Estimate, estimates

from . import describe


@dataclass
class JevDecision:
    kind: str  # "pass" | "play"
    title: str
    options: list[Card]
    choice: Card
    probabilities: dict[str, float] = field(default_factory=dict)  # card id -> P
    criteria: dict[str, str] = field(default_factory=dict)  # card id -> what Jev was told
    situation: str = ""
    confidence: float | None = None
    latency_ms: float | None = None
    source: str = "jev"  # jev | heuristic | random | forced | fallback
    error: str | None = None

    @property
    def chosen_p(self) -> float | None:
        return self.probabilities.get(self.choice.id)


class Jev(Protocol):
    name: str

    def decide(self, obs: Observation) -> Future[JevDecision]: ...


def _done(decision: JevDecision) -> Future[JevDecision]:
    f: Future[JevDecision] = Future()
    f.set_result(decision)
    return f


def _base(obs: Observation, choice: Card, source: str, est: dict[Card, Estimate] | None = None) -> JevDecision:
    _, q = describe.question(obs, est)
    return JevDecision(
        kind=obs.phase, title=describe.title(obs), options=list(obs.options), choice=choice,
        criteria=q["criteria"], situation=describe.situation(obs), source=source,
    )


def forced(obs: Observation) -> JevDecision:
    """Only one legal card: no need to ask."""
    d = _base(obs, obs.options[0], "forced")
    d.probabilities = {obs.options[0].id: 1.0}
    return d


def softmax(values: dict[str, float], temperature: float) -> dict[str, float]:
    top = max(values.values())
    ex = {k: math.exp((v - top) / temperature) for k, v in values.items()}
    total = sum(ex.values())
    return {k: v / total for k, v in ex.items()}


class HeuristicJev:
    """Stands in for Jev without an API key: the bot's scores, softmaxed into probabilities."""

    name = "heuristic"

    def __init__(self, temperature: float = 8.0) -> None:
        self.temperature = temperature

    def decide(self, obs: Observation) -> Future[JevDecision]:
        if len(obs.options) == 1:
            return _done(forced(obs))
        s = scores(obs)
        d = _base(obs, max(obs.options, key=lambda c: s[c]), "heuristic")
        d.probabilities = softmax({c.id: v for c, v in s.items()}, self.temperature)
        return _done(d)


class RandomJev:
    name = "random"

    def __init__(self, seed: int | None = None) -> None:
        import random

        self.rng = random.Random(seed)

    def decide(self, obs: Observation) -> Future[JevDecision]:
        d = _base(obs, self.rng.choice(list(obs.options)), "random")
        d.probabilities = {c.id: 1 / len(obs.options) for c in obs.options}
        return _done(d)


def option_keys(obs: Observation) -> dict[str, Card]:
    """Neutral keys sent to Jev ("option1", ...) -> card. Card ids like "QS" as keys made Jev
    favour whichever option the prompt talked about most, so the card is named only in the text."""
    return {f"option{i}": c for i, c in enumerate(obs.options, 1)}


def build_request(obs: Observation, model: str | None = None, est: dict | None = None) -> dict:
    """Full POST body for the System One API. `est`: simulated results per option (see `describe.question`)."""
    qid, q = describe.question(obs, est)
    keys = {c.id: k for k, c in option_keys(obs).items()}
    q = dict(q, criteria={keys[cid]: text for cid, text in q["criteria"].items()})
    body: dict = {"state": describe.build_state(obs), "questions": {qid: q}}
    if model:
        body["model"] = model
    return body


def parse_answer(data: dict, question_id: str) -> dict:
    """Find our question's answer ({"choice", "probabilities", "confidence"}) in the response.

    Tolerates the answer being at the top level or nested (e.g. under "answers"/"results").
    """
    def search(node, depth=0):
        if depth > 4 or not isinstance(node, dict):
            return None
        hit = node.get(question_id)
        if isinstance(hit, dict) and "choice" in hit:
            return hit
        for v in node.values():
            found = search(v, depth + 1)
            if found:
                return found
        return None

    answer = search(data)
    if answer is None:
        raise ValueError(f"no '{question_id}' answer in response: {str(data)[:300]}")
    return answer


def _match_option(key: str, options: list[Card], keymap: dict[str, Card] | None = None) -> Card | None:
    if keymap and key.strip().lower() in keymap:
        return keymap[key.strip().lower()]
    try:
        card = Card.parse(key)
    except (ValueError, KeyError, IndexError):
        return None
    return card if card in options else None


class RemoteJev:
    """Calls the Jev System One API on a worker thread, one decision at a time.

    If the call fails or the answer isn't a legal card, the heuristic's card is played
    instead and the decision is marked `fallback` with the error.

    With `lookahead` on, every option is first played out `samples` times (see
    `hearts.simulate`) and Jev reads each option's average result.
    """

    name = "remote"

    def __init__(self, timeout_s: float = 30.0, transport=None, retries: int = 1, lookahead: bool = True,
                 samples: int = 40, pass_samples: int = 24) -> None:
        import httpx  # only needed for the remote Jev

        from . import config

        self.retries = retries  # extra attempts after a 5xx or a network error
        self.lookahead, self.samples, self.pass_samples = lookahead, samples, pass_samples
        self.latency_est_ms: float | None = None  # running average of round trips
        self.last_error: str | None = None
        self.requests = 0
        self._url, self.model, key = config.api_url(), config.model(), config.api_key()
        self._key_error = None if key else "JEV_API_KEY is not set - add it to .env (see .env.example)"
        self._client = httpx.Client(
            transport=transport,  # tests pass an httpx.MockTransport
            timeout=timeout_s,
            headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
        )
        self._pool = ThreadPoolExecutor(1, thread_name_prefix="jev")
        self._lock = threading.Lock()
        self._fallback = HeuristicBot()

    def decide(self, obs: Observation) -> Future[JevDecision]:
        if len(obs.options) == 1:
            return _done(forced(obs))
        return self._pool.submit(self._decide, obs)

    def _decide(self, obs: Observation) -> JevDecision:
        qid, _ = describe.question(obs)
        options = list(obs.options)
        keymap = option_keys(obs)
        t0 = time.perf_counter()
        est = self._estimates(obs)
        try:
            if self._key_error:
                raise RuntimeError(self._key_error)
            resp = self._post(build_request(obs, self.model, est))
            if resp.status_code >= 400:
                raise RuntimeError(f"HTTP {resp.status_code}: {resp.text[:300]}")
            answer = parse_answer(resp.json(), qid)
        except Exception as e:  # keep playing; surface the error in the console
            return self._fail(obs, f"{type(e).__name__}: {e}", t0)
        latency = (time.perf_counter() - t0) * 1000
        with self._lock:
            self.requests += 1
            self.latency_est_ms = latency if self.latency_est_ms is None else 0.8 * self.latency_est_ms + 0.2 * latency
            self.last_error = None

        probs: dict[str, float] = {}
        raw = answer.get("probabilities")
        if isinstance(raw, dict):
            for k, v in raw.items():
                card = _match_option(str(k), options, keymap)
                if card is not None and isinstance(v, (int, float)):
                    probs[card.id] = float(v)
        choice = _match_option(str(answer.get("choice", "")), options, keymap)
        conf = answer.get("confidence")
        if choice is None:
            d = self._fail(obs, f"Jev chose {answer.get('choice')!r}, not a legal card", t0)
            d.probabilities = probs
            return d
        d = _base(obs, choice, "jev", est)
        d.probabilities = probs or {choice.id: 1.0}
        d.confidence = float(conf) if isinstance(conf, (int, float)) else None
        d.latency_ms = latency
        return d

    def _estimates(self, obs: Observation) -> dict[Card, Estimate] | None:
        if not self.lookahead:
            return None
        samples = self.pass_samples if obs.phase == "pass" else self.samples
        # Seeded by position so a replayed game gets the same estimates.
        seed = obs.hand_no * 1000 + obs.trick_no * 10 + len(obs.trick) + obs.pass_round
        return estimates(obs, samples=samples, seed=seed)

    def _post(self, body: dict):
        import httpx

        for attempt in range(self.retries + 1):
            try:
                resp = self._client.post(self._url, json=body)
            except httpx.TransportError:
                if attempt == self.retries:
                    raise
                continue
            if resp.status_code < 500 or attempt == self.retries:
                return resp
        raise AssertionError("unreachable")

    def _fail(self, obs: Observation, error: str, t0: float) -> JevDecision:
        self.last_error = error
        d = _base(obs, self._fallback.choose(obs), "fallback")
        d.error = error
        d.latency_ms = (time.perf_counter() - t0) * 1000
        return d


def make_jev(name: str, seed: int | None = None, **remote_options) -> Jev:
    if name == "remote":
        return RemoteJev(**remote_options)
    if name == "random":
        return RandomJev(seed)
    return HeuristicJev()
