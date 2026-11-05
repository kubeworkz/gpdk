"""Exceptions used by the foundry-twin runner."""

from __future__ import annotations

from collections.abc import Sequence


class FabTwinError(Exception):
    """Base class for expected fabtwin failures."""


class ScenarioError(FabTwinError):
    """A scenario could not be read or loaded."""


class ScenarioValidationError(ScenarioError):
    """One or more scenario fields failed validation."""

    def __init__(self, errors: Sequence[str]) -> None:
        self.errors = tuple(str(error) for error in errors)
        super().__init__("\n".join(self.errors))


class EngineError(FabTwinError):
    """An engine rejected a scenario or could not produce a result."""


class StoreError(FabTwinError):
    """The SQLite observation index could not be read or written."""
