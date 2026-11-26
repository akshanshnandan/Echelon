"""Resource-limited Expanded rosters. A roster is an ordered tuple of unit types."""
from dataclasses import dataclass, field
from itertools import combinations_with_replacement


@dataclass(frozen=True)
class DraftRules:
    gold: int = 13_000
    manpower: int = 50
    maximum: int = 4
    minimum: int = 1
    costs: dict[str, tuple[int, int]] = field(default_factory=lambda: {
        "infantry": (2_000, 15), "cavalry": (3_500, 10),
        "artillery": (4_000, 8)})


RULES = DraftRules()


def resources(roster, rules=RULES):
    return (sum(rules.costs[kind][0] for kind in roster),
            sum(rules.costs[kind][1] for kind in roster))


def validate(roster, rules=RULES, allow_empty=False):
    if any(kind not in rules.costs for kind in roster):
        raise ValueError("Unknown formation type")
    if len(roster) > rules.maximum:
        raise ValueError("Formation cap exceeded")
    if len(roster) < rules.minimum and not (allow_empty and not roster):
        raise ValueError("At least one formation is required")
    gold, manpower = resources(roster, rules)
    if gold > rules.gold:
        raise ValueError("Gold budget exceeded")
    if manpower > rules.manpower:
        raise ValueError("Manpower capacity exceeded")
    return tuple(roster)


def remaining(roster, rules=RULES):
    gold, manpower = resources(roster, rules)
    return rules.gold - gold, rules.manpower - manpower, rules.maximum - len(roster)


def purchase(roster, kind, rules=RULES):
    return validate((*roster, kind), rules)


def remove(roster, index, rules=RULES):
    if not 0 <= index < len(roster):
        raise IndexError("No formation in that slot")
    return validate(roster[:index] + roster[index + 1:], rules, allow_empty=True)


def legal_compositions(rules=RULES):
    kinds = tuple(rules.costs)
    return [composition for count in range(rules.minimum, rules.maximum + 1)
            for composition in combinations_with_replacement(kinds, count)
            if _legal(composition, rules)]


def _legal(roster, rules):
    try:
        validate(roster, rules)
        return True
    except ValueError:
        return False
