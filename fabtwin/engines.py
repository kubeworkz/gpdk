"""Engine registry; adding a domain adapter does not change the runner."""

from __future__ import annotations

from .adapters.gpdk import GpdkEngine
from .adapters.pta import PtaEngine
from .adapters.yield_engine import (
    YieldEngine,
    YieldSensitivityEngine,
    YieldVariationEngine,
    YieldWaferMapEngine,
)
from .model import Engine

ENGINE_CLASSES = {
    GpdkEngine.name: GpdkEngine,
    PtaEngine.name: PtaEngine,
    YieldEngine.name: YieldEngine,
    YieldSensitivityEngine.name: YieldSensitivityEngine,
    YieldVariationEngine.name: YieldVariationEngine,
    YieldWaferMapEngine.name: YieldWaferMapEngine,
}


def build_engine(name: str) -> Engine:
    try:
        engine_class = ENGINE_CLASSES[name]
    except KeyError as exc:
        raise KeyError(
            f"unknown engine {name!r}; available: {', '.join(sorted(ENGINE_CLASSES))}"
        ) from exc
    return engine_class()
