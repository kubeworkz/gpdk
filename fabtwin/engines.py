"""Engine registry; adding a domain adapter does not change the runner."""

from __future__ import annotations

from .adapters.factory import FactoryAtpEngine
from .adapters.factory_replay import FactoryMesReplayEngine
from .adapters.gpdk import GpdkEngine
from .adapters.mcm_yield import McmYieldEngine
from .adapters.pta import PtaEngine
from .adapters.pta_photonic import PtaPhotonicEngine
from .adapters.yield_engine import (
    YieldEngine,
    YieldSensitivityEngine,
    YieldVariationEngine,
    YieldWaferMapEngine,
)
from .model import Engine

ENGINE_CLASSES = {
    FactoryAtpEngine.name: FactoryAtpEngine,
    FactoryMesReplayEngine.name: FactoryMesReplayEngine,
    GpdkEngine.name: GpdkEngine,
    McmYieldEngine.name: McmYieldEngine,
    PtaEngine.name: PtaEngine,
    PtaPhotonicEngine.name: PtaPhotonicEngine,
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
