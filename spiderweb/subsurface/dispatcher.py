"""Deterministic dispatch from AOI analysis requests to Spiderweb capability families."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Iterable

from .aoi import FrozenAOI


LAYER_FAMILIES: tuple[str, ...] = (
    "GEOLOGY_KARST_CAVES",
    "AQUIFERS_WELLS_SPRINGS",
    "FAULTS_STRUCTURES",
    "MINES_QUARRIES_SHAFTS",
    "MILITARY_HARDENED_SUBSURFACE",
    "INDUSTRIAL_REMEDIATION",
    "UTILITIES_UNDERGROUND",
    "HISTORICAL_CORROBORATION",
)


@dataclass(frozen=True)
class DispatchTask:
    family: str
    handler_name: str | None
    state: str
    reason: str


Handler = Callable[[FrozenAOI], Iterable[object]]


class SubsurfaceDispatcher:
    """Registry-backed dispatcher with explicit OPEN state for missing adapters.

    The dispatcher never equates absence of a registered handler with absence of
    subsurface evidence. Missing capability is an analysis gap, not a negative finding.
    """

    def __init__(self) -> None:
        self._handlers: dict[str, tuple[str, Handler]] = {}

    def register(self, family: str, handler: Handler, *, name: str | None = None) -> None:
        if family not in LAYER_FAMILIES:
            raise ValueError(f"unknown layer family: {family}")
        if family in self._handlers:
            raise ValueError(f"duplicate handler for layer family: {family}")
        self._handlers[family] = (name or getattr(handler, "__name__", "handler"), handler)

    def plan(self, families: Iterable[str] | None = None) -> list[DispatchTask]:
        requested = list(families or LAYER_FAMILIES)
        if len(requested) != len(set(requested)):
            raise ValueError("duplicate layer family in dispatch request")
        tasks = []
        for family in requested:
            if family not in LAYER_FAMILIES:
                raise ValueError(f"unknown layer family: {family}")
            if family in self._handlers:
                handler_name, _ = self._handlers[family]
                tasks.append(DispatchTask(family, handler_name, "READY", "handler registered"))
            else:
                tasks.append(
                    DispatchTask(
                        family,
                        None,
                        "OPEN",
                        "no registered adapter; do not interpret as negative evidence",
                    )
                )
        return tasks

    def run(self, aoi: FrozenAOI, families: Iterable[str] | None = None) -> dict[str, list[object]]:
        outputs: dict[str, list[object]] = {}
        for task in self.plan(families):
            if task.state != "READY":
                continue
            _, handler = self._handlers[task.family]
            outputs[task.family] = list(handler(aoi))
        return outputs
