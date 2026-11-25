"""Programmed roster preferences, not trained neural-network policies."""
import random

from .drafting import RULES, legal_compositions, resources


WEIGHTS = {
    "balanced": {"infantry": 3.0, "cavalry": 3.0, "artillery": 3.0},
    "cavalry": {"infantry": 1.0, "cavalry": 5.0, "artillery": 0.5},
    "artillery": {"infantry": 2.0, "cavalry": 0.5, "artillery": 5.0},
    "infantry": {"infantry": 5.0, "cavalry": 2.2, "artillery": 1.5},
}


def draft(doctrine, seed, rules=RULES):
    if doctrine not in WEIGHTS:
        raise ValueError(f"Unknown doctrine: {doctrine}")
    rng = random.Random(seed)
    weights = WEIGHTS[doctrine]
    choices = legal_compositions(rules)
    if doctrine == "infantry":
        choices = [roster for roster in choices
                   if roster.count("infantry") >= max(roster.count("cavalry"),
                                                       roster.count("artillery"))]

    def value(roster):
        gold, _ = resources(roster, rules)
        mix = 3 if doctrine == "balanced" and len(set(roster)) == 3 else 0
        # Modest seed variation cannot turn a doctrine into its opposite.
        return (sum(weights[kind] for kind in roster) + mix
                + gold / rules.gold * 2 + rng.uniform(-1.2, 1.2))

    return max(choices, key=value)
