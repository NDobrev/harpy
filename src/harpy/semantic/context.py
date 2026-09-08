"""Host-side context budgets and evidence allocation."""

from __future__ import annotations

from math import ceil

DEFAULT_CALL_UNITS = 12_000
DEFAULT_RUN_UNITS = 180_000
DEFAULT_OUTPUT_UNITS = 4_000
RESERVE_FRACTION = 0.2


def estimate_units(text: str) -> int:
    return max(1, ceil(len(text.encode("utf-8")) / 3))


class RunBudget:
    def __init__(
        self,
        *,
        call_units: int = DEFAULT_CALL_UNITS,
        run_units: int = DEFAULT_RUN_UNITS,
        max_calls: int = 16,
    ) -> None:
        self.call_units = call_units
        self.remaining = run_units
        self.max_calls = max_calls
        self.calls = 0
        self.repairs = 0

    def can_schedule(self) -> bool:
        return self.calls < self.max_calls and self.remaining > 0

    def consume(self, units: int, *, repair: bool = False) -> None:
        self.calls += 1
        if repair:
            self.repairs += 1
        self.remaining = max(0, self.remaining - units)

    def exhausted(self) -> bool:
        return not self.can_schedule()
