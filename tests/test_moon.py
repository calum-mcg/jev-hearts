"""Shooting the moon: detection, bot attempts, bot blocking, and what Jev is told."""

from hearts import moon
from hearts.bots import HeuristicBot, play_scores
from hearts.cards import Card
from hearts.game import HeartsGame, Observation, Trick
from jev_agent import describe

C = Card.parse
NO_VOIDS = (frozenset(),) * 4


def obs_with(points, hand, options, trick=(), tricks=(), seat=0, phase="play"):
    return Observation(
        seat=seat, phase=phase, hand_no=0, direction="hold", hand=tuple(map(C, hand)), options=tuple(map(C, options)),
        pass_round=3, pass_picked=(), passed=(), received=(), trick=trick, leader=trick[0][0] if trick else seat,
        tricks=tricks, hearts_broken=True, points_hand=points, scores=(0, 0, 0, 0), voids=NO_VOIDS, target=100,
    )


def test_status_sentences():
    assert "No points have been taken yet" in moon.status(obs_with((0, 0, 0, 0), ["2C"], ["2C"]), describe.SEATS)
    split = moon.status(obs_with((3, 13, 0, 0), ["2C"], ["2C"]), describe.SEATS)
    assert "Nobody can shoot the moon" in split
    theirs = moon.status(obs_with((0, 16, 0, 0), ["2C"], ["2C"]), describe.SEATS)
    assert theirs.startswith("West has taken all 16 points") and "stops it" in theirs


def test_strong_hand_goes_for_the_moon():
    strong = ["AS", "KS", "QS", "AH", "KH", "QH", "JH", "AD", "KD", "AC", "KC", "2C", "3D"]
    assert moon.should_shoot(obs_with((0, 0, 0, 0), strong, strong))
    weak = ["2S", "3S", "4S", "5H", "6H", "7H", "8H", "2D", "3D", "4C", "5C", "6C", "7D"]
    assert not moon.should_shoot(obs_with((0, 0, 0, 0), weak, weak))
    assert not moon.should_shoot(obs_with((0, 1, 0, 0), strong, strong))  # someone else has a point


def test_bot_blocks_a_moon_shooter():
    # West has taken all 16 points and leads the 9♥. North can win it with the 10♥ (taking a point) or duck.
    trick = ((1, C("9H")),)
    obs = obs_with((0, 16, 0, 0), ["2H", "10H", "3C"], ["2H", "10H"], trick=trick, seat=2)
    assert HeuristicBot().choose(obs) == C("10H")
    # Without the threat the bot ducks.
    calm = obs_with((0, 3, 0, 0), ["2H", "10H", "3C"], ["2H", "10H"], trick=trick, seat=2)
    assert HeuristicBot().choose(calm) == C("2H")


def test_jev_criteria_mention_the_moon():
    trick = ((1, C("9H")),)
    obs = obs_with((0, 16, 0, 0), ["2H", "10H", "3C"], ["2H", "10H"], trick=trick)
    crit = describe.question(obs)[1]["criteria"]
    assert "stopping their moon attempt" in crit["10H"]
    mine = obs_with((5, 0, 0, 0), ["AH", "2C"], ["AH"], trick=((1, C("9H")), (2, C("3H")), (3, C("4H"))))
    assert "keeps your moon chance alive" in describe.play_criterion(mine, C("AH"))


def test_moons_happen_in_bot_games():
    moons = 0
    for seed in range(60):
        g = HeartsGame(seed=seed, target=10**6)
        bot = HeuristicBot()
        while g.phase in ("pass", "play"):
            d = g.pending()
            g.apply(bot.choose(g.observation(d.seat)))
        moons += g.moon is not None
    assert moons >= 1


def test_moon_mode_never_discards_points():
    # South is shooting (all 14 points, strong hand) and void in clubs: it must not throw hearts away.
    obs = obs_with((14, 0, 0, 0), ["AH", "KH", "AD", "2D"], ["AH", "KH", "AD", "2D"], trick=((1, C("5C")),),
                   tricks=(Trick(0, ((0, C("QS")),), 0, 13),))
    s = play_scores(obs)
    assert max(s, key=s.get) in (C("2D"), C("AD"))


def test_committed_moon_after_taking_the_queen():
    # South took the Q♠ (13 points, the only points so far) and holds A♣ K♣ Q♣ plus top hearts.
    queen = Trick(1, ((1, C("3S")), (2, C("QS")), (3, C("5S")), (0, C("AS"))), 0, 13)
    hand = ["AC", "KC", "QC", "AH", "KH", "QH", "JH", "10H", "AD", "2D"]
    obs = obs_with((13, 0, 0, 0), hand, hand, tricks=(queen,))
    assert moon.should_shoot(obs)
    assert moon.status(obs, describe.SEATS).startswith("Moon is on")
    q = describe.question(obs)[1]
    assert "shoot the moon" in q["instructions"]
    assert "keeps your moon going" in describe.play_criterion(obs, C("AC"))


def test_no_moon_with_too_many_losers():
    queen = Trick(1, ((1, C("3S")), (2, C("QS")), (3, C("5S")), (0, C("AS"))), 0, 13)
    hand = ["AC", "KC", "QC", "2H", "4H", "6H", "3D", "5D", "7D", "9D"]
    obs = obs_with((13, 0, 0, 0), hand, hand, tricks=(queen,))
    assert not moon.should_shoot(obs)
    assert "looks unlikely" in moon.status(obs, describe.SEATS)
    assert "shoot the moon" not in describe.question(obs)[1]["instructions"]


def test_block_mode_frames_stopping_the_moon():
    # West has all 16 points and leads the 9♥: taking it with the 10♥ stops the moon.
    obs = obs_with((0, 16, 0, 0), ["2H", "10H", "3C"], ["2H", "10H"], trick=((1, C("9H")),))
    q = describe.question(obs)[1]
    assert "may be shooting the moon" in q["instructions"]
    assert describe.play_criterion(obs, C("10H")).startswith("Result: stops West's moon")
    assert "feeds West's moon" in describe.play_criterion(obs, C("2H"))


def test_pass_options_rank_the_risk_of_keeping():
    hand = ["QS", "3S", "AH", "2H", "4C", "9D", "8D", "7D", "6D", "5D", "KC", "2C", "3C"]
    obs = obs_with((0, 0, 0, 0), hand, hand, phase="pass")
    assert describe.pass_criterion(obs, C("QS")).startswith("Result: high risk to keep")
    assert describe.pass_criterion(obs, C("2H")).startswith("Result: safe to keep")
