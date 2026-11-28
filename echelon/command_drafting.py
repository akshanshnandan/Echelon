"""Version 4 Command army budgets. Costs match the Expanded draft."""
from random import Random

from .drafting import RULES, resources

SIZES = {
    "skirmish": (4, 13_000, 50, 1200, 800),
    "field": (8, 26_000, 100, 1400, 900),
    "grand": (15, 50_000, 180, 1600, 1000),
}
PRESETS = {
    "skirmish": ("infantry", "infantry", "cavalry", "artillery"),
    "field": ("infantry",) * 4 + ("cavalry",) * 2 + ("artillery",) * 2,
    "grand": ("infantry",) * 6 + ("cavalry",) * 5 + ("artillery",) * 4,
}
AI_PRESETS = {
    "balanced": PRESETS,
    "aggressive": {
        "skirmish": ("infantry", "cavalry", "cavalry", "artillery"),
        "field": ("infantry",) * 2 + ("cavalry",) * 4 + ("artillery",) * 2,
        "grand": ("infantry",) * 4 + ("cavalry",) * 8 + ("artillery",) * 3,
    },
    "defensive": {
        "skirmish": PRESETS["skirmish"],
        "field": PRESETS["field"],
        "grand": ("infantry",) * 7 + ("cavalry",) * 4 + ("artillery",) * 4,
    },
}


def limits(size, budget=None, manpower=None):
    if size not in SIZES:
        raise ValueError("Unknown Command battle size")
    cap, default_gold, default_people, width, height = SIZES[size]
    gold = default_gold if budget is None else budget
    people = default_people if manpower is None else manpower
    if not isinstance(gold, int) or not 4_000 <= gold <= default_gold * 2:
        raise ValueError("Command budget outside allowed range")
    if not isinstance(people, int) or not 15 <= people <= default_people * 2:
        raise ValueError("Command manpower outside allowed range")
    return cap, gold, people, width, height


def validate(roster, size, budget=None, manpower=None):
    cap, gold, people, _, _ = limits(size, budget, manpower)
    if not 2 <= len(roster) <= cap or any(kind not in RULES.costs for kind in roster):
        raise ValueError("Illegal Command formation roster")
    spent, used = resources(roster)
    if spent > gold or used > people:
        raise ValueError("Command roster exceeds budget or manpower")
    return tuple(roster)


def ai_draft(size, preference, seed, budget=None, manpower=None):
    """Deterministic independent draft with all arms available to each personality."""
    if preference not in ("balanced", "aggressive", "defensive"):
        raise ValueError("Unknown tactical preference")
    cap, gold, people, _, _ = limits(size, budget, manpower)
    weights = {"balanced": (5, 3, 2), "aggressive": (3, 5, 2), "defensive": (6, 2, 2)}[preference]
    rng = Random(f"{seed}:{size}:{preference}:draft")
    preferred = AI_PRESETS[preference][size]
    if resources(preferred)[0] <= gold and resources(preferred)[1] <= people:
        roster = list(preferred)
        rng.shuffle(roster)
        return validate(roster, size, budget, manpower)
    kinds = ("infantry", "cavalry", "artillery")
    roster = list(kinds)
    while len(roster) < cap:
        choices = [kind for kind in kinds if resources((*roster, kind))[0] <= gold and resources((*roster, kind))[1] <= people]
        if not choices:
            break
        roster.append(rng.choices(choices, weights=[weights[kinds.index(k)] for k in choices])[0])
    rng.shuffle(roster)
    return validate(roster, size, budget, manpower)
