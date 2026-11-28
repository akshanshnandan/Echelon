"""Version 4 Command rules and version 3 compatibility."""
import pytest
from concurrent.futures import ThreadPoolExecutor

from echelon.command_drafting import PRESETS, ai_draft, validate
from echelon.command_engine_v4 import CommandBattle
from echelon.command_general_v4 import CommandGeneral
from echelon.command_game import CommandGame
from echelon.command_recording import verify
from fastapi.testclient import TestClient
from echelon.web_api import app


@pytest.mark.parametrize("size,count", [("skirmish", 4), ("field", 8), ("grand", 15)])
def test_deployments_and_limits(size, count):
    a = CommandBattle(19, size=size)
    b = CommandBattle(19, size=size)
    assert a.snapshot() == b.snapshot()
    assert len(a.units) == count * 2
    assert len(a.roster) == count
    assert len(a.enemy_roster) <= count
    assert len(set(a.units)) == count + len(a.enemy_roster)
    assert validate(PRESETS[size], size) == PRESETS[size]
    a.command("Blue", [f"B{i}" for i in range(1, count + 1)], "MOVE", (a.width / 2, a.height / 2))
    assert len({u.destination for u in a.units.values() if u.army == "Blue"}) == count


@pytest.mark.parametrize("size", ["skirmish", "field", "grand"])
def test_full_seeded_battle_terminates_deterministically(size):
    outcomes = []
    for _ in range(2):
        battle = CommandBattle(41, size=size)
        blue, red = CommandGeneral("Blue"), CommandGeneral("Red")
        while not battle.finished:
            blue.decide(battle); red.decide(battle); battle.step()
        assert battle.tick <= 1800
        outcomes.append(battle.snapshot())
    assert outcomes[0] == outcomes[1]


def test_independent_rosters_and_budget():
    a = CommandBattle(2, roster=("infantry", "infantry"), enemy_roster=("cavalry", "artillery"))
    assert [u.kind for u in a.units.values() if u.army == "Red"] == ["cavalry", "artillery"]
    with pytest.raises(ValueError):
        CommandBattle(roster=("artillery",) * 4)
    assert ai_draft("grand", "balanced", 5) == ai_draft("grand", "balanced", 5)


@pytest.mark.parametrize("personality", ["balanced", "aggressive", "defensive"])
def test_large_army_ai_orders_are_bounded(personality):
    battle = CommandBattle(7, size="grand", opponent=personality)
    general = CommandGeneral("Red", personality)
    for _ in range(300):
        general.decide(battle)
        battle.step()
        if battle.finished:
            break
    orders = [e for e in battle.events if e["type"] == "order" and e["unit"].startswith("R")]
    assert orders
    assert len(orders) < 15 * 12


def test_routing_withdrawal_rally_and_shock():
    b = CommandBattle(3)
    broken = b.units["B1"]
    assert broken.snapshot()["morale_state"] == "steady"
    broken.morale = 60
    assert broken.snapshot()["morale_state"] == "shaken"
    broken.morale = 30
    assert broken.snapshot()["morale_state"] == "wavering"
    friend = b.units["B2"]
    friend.x, friend.y = broken.x, broken.y + 50
    broken.morale = 20
    b._route(broken, "casualties")
    assert friend.morale == 92
    x = broken.x
    b.step()
    assert broken.x < x and not broken.effective
    for enemy in (u for u in b.units.values() if u.army == "Red"):
        enemy.x = b.width - 20
    for _ in range(80):
        b.step()
    assert broken.rallies == 1 and broken.effective
    b._route(broken, "casualties")
    for _ in range(90):
        b.step()
    assert broken.rallies == 1 and broken.routing


def test_configurable_morale_effects_are_bounded_and_recorded():
    options = {"casualty": 1.0, "cavalry": 2.0, "break_shock": 12.0}
    battle = CommandBattle(morale_rules=options)
    assert battle.morale_rules == options
    with pytest.raises(ValueError):
        CommandBattle(morale_rules={"break_shock": 100})
    game = CommandGame(ruleset_version=4, morale_rules=options)
    assert game.recording()["morale_rules"] == options


def test_versioned_replays():
    clock = [0.0]
    game = CommandGame(clock=lambda: clock[0], ruleset_version=4, size="skirmish")
    game.control(speed=4)
    for _ in range(240):
        clock[0] += 2
        game.advance()
        if game.battle.finished:
            break
    assert game.battle.finished
    assert verify(game.recording())


def test_public_api_grand_and_independent_rosters():
    client = TestClient(app)
    response = client.post("/api/command", json={"size": "grand", "human_army": "Red", "roster": list(PRESETS["grand"])})
    assert response.status_code == 201
    body = response.json()
    assert body["battle"]["ruleset_version"] == 4
    assert len([u for u in body["battle"]["units"].values() if u["army"] == "Red"]) == 15
    key = body["id"]
    ids = [f"R{i}" for i in range(1, 16)]
    assert client.post(f"/api/command/{key}/orders", json={"ids": ids, "kind": "MOVE", "target": [800, 500]}).status_code == 200
    assert client.post("/api/command", json={"size": "grand", "roster": ["artillery"] * 15}).status_code == 422
    assert client.post("/api/command", json={"morale": {"break_shock": 100}}).status_code == 422


def test_concurrent_grand_sessions():
    client = TestClient(app)
    keys = [client.post("/api/command", json={"size": "grand", "seed": seed}).json()["id"] for seed in range(8)]
    with ThreadPoolExecutor(max_workers=6) as pool:
        statuses = list(pool.map(lambda key: client.get(f"/api/command/{key}").status_code, keys))
    assert statuses == [200] * len(keys)
