"""Small data contracts shared by the orchestrator and engine adapters."""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Any, Mapping, Protocol

if TYPE_CHECKING:
    from .scenario import Scenario


EVIDENCE_CLASSES = frozenset(
    {"measured", "vendor", "literature", "proxy", "assumed"}
)


@dataclass(frozen=True)
class Observation:
    """One metric for one entity in one run.

    Values are stored in base SI units.  The report layer may convert them to
    practical display units, but the evidence store never carries a bare float.
    """

    entity_type: str
    entity_id: str
    metric: str
    value: float
    unit: str
    uncertainty: float | None
    evidence_class: str
    source_artifact: str
    model_version: str

    def __post_init__(self) -> None:
        if not self.entity_type:
            raise ValueError("observation entity_type must not be empty")
        if not self.entity_id:
            raise ValueError("observation entity_id must not be empty")
        if not self.metric:
            raise ValueError("observation metric must not be empty")
        if not self.unit:
            raise ValueError("observation unit must not be empty")
        if not math.isfinite(float(self.value)):
            raise ValueError(f"{self.metric}: value must be finite")
        if self.uncertainty is not None:
            if not math.isfinite(float(self.uncertainty)):
                raise ValueError(f"{self.metric}: uncertainty must be finite")
            if float(self.uncertainty) < 0.0:
                raise ValueError(f"{self.metric}: uncertainty must be >= 0")
        if self.evidence_class not in EVIDENCE_CLASSES:
            raise ValueError(
                f"{self.metric}: unknown evidence class {self.evidence_class!r}"
            )
        if not self.source_artifact:
            raise ValueError("observation source_artifact must not be empty")
        if not self.model_version:
            raise ValueError("observation model_version must not be empty")


@dataclass(frozen=True)
class InputFile:
    """An input file the engine actually consumed."""

    path: Path
    role: str

    def __post_init__(self) -> None:
        if not self.role:
            raise ValueError("input role must not be empty")


@dataclass(frozen=True)
class EngineResult:
    """What an engine returns; it never writes a report or a database."""

    engine: str
    engine_version: str
    fidelity: str
    model_version: str
    observations: tuple[Observation, ...]
    inputs: tuple[InputFile, ...]
    metadata: Mapping[str, Any] = field(default_factory=dict)
    warnings: tuple[str, ...] = ()


class Engine(Protocol):
    """The stable adapter interface every domain engine implements."""

    name: str
    version: str
    fidelity: str

    def validate(self, scenario: "Scenario") -> list[str]:
        """Return scenario-specific errors without running the engine."""

    def run(self, scenario: "Scenario") -> EngineResult:
        """Execute one deterministic or seeded experiment."""
