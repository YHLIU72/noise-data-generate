"""Dependency-free Latin-hypercube sampling for batch virtual experiments."""

from __future__ import annotations

from dataclasses import dataclass
import random
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence


@dataclass(frozen=True)
class ParameterSpec:
    name: str
    low: Optional[float] = None
    high: Optional[float] = None
    values: Optional[Sequence[Any]] = None
    kind: str = "float"

    def validate(self) -> None:
        if self.values is not None:
            if not self.values:
                raise ValueError(f"{self.name}: values must not be empty")
            if self.kind not in {"categorical", "int"}:
                raise ValueError(f"{self.name}: values require kind='categorical' or 'int'")
            return
        if self.low is None or self.high is None or self.high < self.low:
            raise ValueError(f"{self.name}: low/high are invalid")
        if self.kind not in {"float", "int"}:
            raise ValueError(f"{self.name}: unsupported kind {self.kind!r}")


def latin_hypercube(
    specs: Sequence[ParameterSpec], n_samples: int, seed: int = 20261126
) -> List[Dict[str, Any]]:
    """Generate deterministic, stratified samples within all parameter bounds."""

    if n_samples < 1:
        raise ValueError("n_samples must be >= 1")
    for spec in specs:
        spec.validate()
    rng = random.Random(seed)
    samples: List[Dict[str, Any]] = [dict() for _ in range(n_samples)]

    for spec in specs:
        if spec.values is not None:
            values = list(spec.values)
            shuffled = [values[i % len(values)] for i in range(n_samples)]
            rng.shuffle(shuffled)
            for i, value in enumerate(shuffled):
                samples[i][spec.name] = value
            continue

        bins = [(i + rng.random()) / n_samples for i in range(n_samples)]
        rng.shuffle(bins)
        assert spec.low is not None and spec.high is not None
        for i, fraction in enumerate(bins):
            value = spec.low + fraction * (spec.high - spec.low)
            if spec.kind == "int":
                value = int(round(value))
                value = max(int(spec.low), min(int(spec.high), value))
            samples[i][spec.name] = value
    return samples


def default_parameter_specs() -> List[ParameterSpec]:
    """Return a conservative automotive-HVAC-style design/operating space.

    These ranges are modeling defaults, not measurements for a named product.
    """

    return [
        ParameterSpec("impeller_outer_diameter_m", 0.135, 0.165),
        ParameterSpec("impeller_height_m", 0.062, 0.085),
        ParameterSpec("blade_count", values=[35, 37, 39, 41, 43, 45], kind="int"),
        ParameterSpec("tongue_gap_ratio", 0.055, 0.115),
        ParameterSpec("blade_spacing_modulation", 0.0, 1.65),
        ParameterSpec("rpm", 1400.0, 4300.0),
        ParameterSpec("temperature_c", 10.0, 35.0),
        ParameterSpec("system_resistance_multiplier", 0.70, 1.40),
        ParameterSpec("door_opening_fraction", 0.35, 0.95),
    ]


def specs_from_mapping(mapping: Mapping[str, Mapping[str, Any]]) -> List[ParameterSpec]:
    specs: List[ParameterSpec] = []
    for name, raw in mapping.items():
        specs.append(
            ParameterSpec(
                name=name,
                low=raw.get("low"),
                high=raw.get("high"),
                values=raw.get("values"),
                kind=raw.get("kind", "float"),
            )
        )
    return specs
