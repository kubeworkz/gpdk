"""Event-derived factory replay adapter.

This engine does not simulate the line. It replays a verified MES extract and
reports cycle time, queue time, WIP, throughput and tool usage computed from
the event timestamps. The extract manifest supplies the evidence class, so a
synthetic fixture stays `assumed` all the way into the observation store.
"""

from __future__ import annotations

from typing import Callable

from ..errors import EngineError, MesReplayError
from ..mes_replay import MesReplayResult, load_replay
from ..model import EngineResult, InputFile, Observation
from ..provenance import display_path
from ..scenario import Scenario

HOURS_PER_WEEK = 168.0
SECONDS_PER_HOUR = 3600.0
_MODEL_VERSION_PREFIX = "mes-replay"

_SCALAR_METRICS: dict[
    str, tuple[str, Callable[[MesReplayResult], float]]
] = {
    "cycle_time_s": (
        "s",
        lambda result: result.cycle_time_hours * SECONDS_PER_HOUR,
    ),
    "queue_time_s": (
        "s",
        lambda result: result.queue_time_hours * SECONDS_PER_HOUR,
    ),
    "wip_lots": ("lot", lambda result: result.wip_lots),
    "peak_wip_lots": (
        "lot",
        lambda result: float(result.peak_wip_lots),
    ),
    "throughput_wafers_per_s": (
        "1/s",
        lambda result: result.throughput_wafers_per_week
        / (HOURS_PER_WEEK * SECONDS_PER_HOUR),
    ),
    "completed_lots": (
        "lot",
        lambda result: float(result.completed_lots),
    ),
    "completed_wafers": (
        "wafer",
        lambda result: float(result.completed_wafers),
    ),
    "open_lots": ("lot", lambda result: float(result.open_lots)),
    "observation_window_s": (
        "s",
        lambda result: result.window_hours * SECONDS_PER_HOUR,
    ),
}
_EXTRA_METRICS = frozenset(
    {
        "step_queue_time_s",
        "tool_utilization",
        "tool_group_utilization",
    }
)
SUPPORTED_METRICS = frozenset({*_SCALAR_METRICS, *_EXTRA_METRICS})


class FactoryMesReplayEngine:
    """Replay a verified MES extract as the factory slice's event view."""

    name = "factory_replay"
    version = "0.1.0"
    fidelity = "F1"

    def validate(self, scenario: Scenario) -> list[str]:
        errors: list[str] = []
        if scenario.samples != 1:
            errors.append("factory_replay is deterministic; samples must be 1")
        unknown = sorted(set(scenario.outputs) - SUPPORTED_METRICS)
        if unknown:
            errors.append(
                "unsupported factory replay metric(s): "
                + ", ".join(unknown)
            )
        if scenario.mes_path is None:
            errors.append("factory_replay requires inputs.mes")
            return errors
        try:
            load_replay(scenario.mes_path)
        except MesReplayError as exc:
            errors.append(f"cannot load MES replay: {exc}")
        return errors

    def run(self, scenario: Scenario) -> EngineResult:
        errors = self.validate(scenario)
        if errors:
            raise EngineError("; ".join(errors))
        assert scenario.mes_path is not None
        result = load_replay(scenario.mes_path)
        source = display_path(result.manifest_path)
        model_version = f"{_MODEL_VERSION_PREFIX}@{self.version}"
        observations: list[Observation] = []
        for metric in scenario.outputs:
            if metric in _SCALAR_METRICS:
                unit, projector = _SCALAR_METRICS[metric]
                observations.append(
                    Observation(
                        entity_type="factory_case",
                        entity_id="mes_replay",
                        metric=metric,
                        value=float(projector(result)),
                        unit=unit,
                        uncertainty=None,
                        evidence_class=result.evidence_class,
                        source_artifact=source,
                        model_version=model_version,
                    )
                )
            elif metric == "step_queue_time_s":
                for operation_id in sorted(result.step_queue_hours):
                    observations.append(
                        Observation(
                            entity_type="route_step",
                            entity_id=f"mes_replay:{operation_id}",
                            metric="step_queue_time_s",
                            value=(
                                result.step_queue_hours[operation_id]
                                * SECONDS_PER_HOUR
                            ),
                            unit="s",
                            uncertainty=None,
                            evidence_class=result.evidence_class,
                            source_artifact=source,
                            model_version=model_version,
                        )
                    )
            elif metric == "tool_utilization":
                for tool_id in sorted(result.tool_utilization):
                    observations.append(
                        Observation(
                            entity_type="tool",
                            entity_id=tool_id,
                            metric="tool_utilization",
                            value=result.tool_utilization[tool_id],
                            unit="1",
                            uncertainty=None,
                            evidence_class=result.evidence_class,
                            source_artifact=source,
                            model_version=model_version,
                        )
                    )
            elif metric == "tool_group_utilization":
                for group_id in sorted(result.tool_group_utilization):
                    observations.append(
                        Observation(
                            entity_type="tool_group",
                            entity_id=group_id,
                            metric="tool_group_utilization",
                            value=result.tool_group_utilization[group_id],
                            unit="1",
                            uncertainty=None,
                            evidence_class=result.evidence_class,
                            source_artifact=source,
                            model_version=model_version,
                        )
                    )
        warnings = [
            "MES replay reads event timestamps; it does not simulate "
            "dispatch, batching, failures or maintenance.",
            "Cycle time, queue time and WIP are descriptive statistics for "
            "the manifest window, not a forecast.",
        ]
        if result.evidence_class == "assumed":
            warnings.append(
                "The event log is synthetic (`assumed`); replay metrics "
                "describe generated events and are not measured line "
                "performance."
            )
        else:
            warnings.append(
                "Replay metrics inherit the manifest evidence class "
                f"`{result.evidence_class}` and describe only the supplied "
                "window."
            )
        return EngineResult(
            engine=self.name,
            engine_version=self.version,
            fidelity=self.fidelity,
            model_version=model_version,
            observations=tuple(observations),
            inputs=(
                InputFile(result.manifest_path, "mes"),
                InputFile(result.route_path, "mes_route"),
                InputFile(result.equipment_path, "mes_equipment"),
            ),
            metadata={
                "mes": {
                    "manifest": source,
                    "manifest_sha256": result.manifest_sha256,
                    "evidence_class": result.evidence_class,
                    "synthetic": result.synthetic,
                    "generator": result.generator,
                    "generator_version": result.generator_version,
                    "window": {
                        "start_utc": result.window_start.isoformat(),
                        "end_utc": result.window_end.isoformat(),
                        "hours": result.window_hours,
                    },
                    "route": {
                        "path": display_path(result.route_path),
                        "sha256": result.route_sha256,
                        "rows": result.route_rows,
                    },
                    "equipment": {
                        "path": display_path(result.equipment_path),
                        "sha256": result.equipment_sha256,
                        "rows": result.equipment_rows,
                    },
                    "lots": result.lot_count,
                    "completed_lots": result.completed_lots,
                    "completed_wafers": result.completed_wafers,
                    "open_lots": result.open_lots,
                    "cycle_time_hours": result.cycle_time_hours,
                    "queue_time_hours": result.queue_time_hours,
                    "wip_lots": result.wip_lots,
                    "peak_wip_lots": result.peak_wip_lots,
                    "throughput_wafers_per_week": (
                        result.throughput_wafers_per_week
                    ),
                    "tool_utilization": dict(result.tool_utilization),
                    "tool_group_utilization": dict(
                        result.tool_group_utilization
                    ),
                    "step_queue_hours": dict(result.step_queue_hours),
                    "basis": (
                        "event timestamps; tool utilization is setup plus "
                        "productive state time divided by the window"
                    ),
                }
            },
            warnings=tuple(warnings),
        )
