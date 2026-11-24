"""Independent synthetic days, each with two one-hour slots."""
from dataclasses import dataclass
from random import Random

from .network import Edge, SITES

@dataclass(frozen=True)
class Slot:
    """Available units, requested units and closed edges for one hour."""
    supply: int
    demand: int
    closed: tuple[Edge, ...]

Day = tuple[Slot, Slot]

def generate(count: int, seed: int, closure_probability: float) -> tuple[Day, ...]:
    """Sample independent uniform integer supply 12–20 and demand 13–21."""
    if count < 1 or not 0 <= closure_probability <= 1:
        raise ValueError("Invalid scenario count or closure probability")
    rng = Random(seed)

    def slot() -> Slot:
        """Close each interior edge independently for this hour."""
        return Slot(rng.randint(12, 20), rng.randint(13, 21),
                    tuple(e for e in SITES if rng.random() < closure_probability))

    return tuple((slot(), slot()) for _ in range(count))
