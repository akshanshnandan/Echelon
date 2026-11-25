"""Balanced side/turn assignments and disjoint training/evaluation seeds."""
import hashlib


SIDE_FIRST = (("Blue", "Blue"), ("Red", "Red"),
              ("Blue", "Red"), ("Red", "Blue"))

DEV_BASE_SEED = 2027
FINAL_TEST_BASE_SEED = 3037  # Reserved; do not evaluate during development.


def scenario_seed(split: str, base_seed: int, index: int) -> int:
    """Stable, disjoint train, legacy eval, development, and final pools."""
    if split not in ("train", "eval", "dev", "final") or index < 0:
        raise ValueError("Unknown split or negative index")
    digest = hashlib.blake2b(f"{base_seed}:{index}".encode(), digest_size=8).digest()
    value = int.from_bytes(digest, "big") & ((1 << 63) - 1)
    if split in ("train", "eval"):
        return 2 * value + (split == "eval")  # Preserve Phase 5 seeds exactly.
    return (1 << 64 if split == "dev" else 1 << 65) + value
