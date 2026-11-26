"""Core data models for the parameterized HVAC aeroacoustic ROM.

The package deliberately keeps the model inputs and outputs explicit.  Values
produced by this project are parameterized numerical simulations; they are not
experimental measurements.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Mapping, Sequence
import math


def _require_positive(name: str, value: float) -> None:
    if not math.isfinite(value) or value <= 0.0:
        raise ValueError(f"{name} must be finite and > 0, got {value!r}")


@dataclass(frozen=True)
class Geometry:
    """Reduced-order geometry and lumped acoustic-path parameters.

    The geometry is intentionally not a CAD representation.  It supplies the
    dimensions needed by the low-order fan, source, and plane-wave path
    models.
    """

    impeller_outer_diameter_m: float = 0.150
    impeller_inlet_diameter_m: float = 0.115
    impeller_height_m: float = 0.074
    blade_count: int = 39
    blade_thickness_m: float = 0.0012
    tongue_gap_ratio: float = 0.080
    blade_spacing_modulation: float = 0.0
    blade_spacing_order: int = 1
    duct_length_m: float = 0.80
    duct_area_m2: float = 0.0120
    outlet_area_m2: float = 0.0100
    core_area_m2: float = 0.0120
    core_thickness_m: float = 0.038
    core_porosity: float = 0.78
    door_opening_fraction: float = 0.75
    scroll_expansion_ratio: float = 1.40

    def validate(self) -> None:
        for name in (
            "impeller_outer_diameter_m",
            "impeller_inlet_diameter_m",
            "impeller_height_m",
            "blade_thickness_m",
            "duct_length_m",
            "duct_area_m2",
            "outlet_area_m2",
            "core_area_m2",
            "core_thickness_m",
        ):
            _require_positive(name, float(getattr(self, name)))
        if self.impeller_inlet_diameter_m >= self.impeller_outer_diameter_m:
            raise ValueError("impeller_inlet_diameter_m must be smaller than outer diameter")
        if self.blade_count < 3:
            raise ValueError("blade_count must be >= 3")
        if self.blade_spacing_order < 1:
            raise ValueError("blade_spacing_order must be >= 1")
        if not 0.0 <= self.tongue_gap_ratio <= 0.5:
            raise ValueError("tongue_gap_ratio must be in [0, 0.5]")
        if not 0.0 <= self.blade_spacing_modulation <= 2.0:
            raise ValueError("blade_spacing_modulation must be in [0, 2]")
        if not 0.05 <= self.core_porosity <= 0.99:
            raise ValueError("core_porosity must be in [0.05, 0.99]")
        if not 0.05 <= self.door_opening_fraction <= 1.0:
            raise ValueError("door_opening_fraction must be in [0.05, 1]")
        if self.scroll_expansion_ratio < 1.0:
            raise ValueError("scroll_expansion_ratio must be >= 1")

    @property
    def impeller_flow_area_m2(self) -> float:
        return math.pi * self.impeller_outer_diameter_m * self.impeller_height_m

    @property
    def equivalent_duct_diameter_m(self) -> float:
        return math.sqrt(4.0 * self.duct_area_m2 / math.pi)


@dataclass(frozen=True)
class OperatingPoint:
    """Operating inputs used by the coupled fan/system operating-point solver."""

    rpm: float = 2500.0
    temperature_c: float = 20.0
    ambient_pressure_pa: float = 101325.0
    system_resistance_multiplier: float = 1.0
    mode: str = "open"

    def validate(self) -> None:
        _require_positive("rpm", self.rpm)
        _require_positive("ambient_pressure_pa", self.ambient_pressure_pa)
        if not -40.0 <= self.temperature_c <= 80.0:
            raise ValueError("temperature_c must be in [-40, 80]")
        if self.system_resistance_multiplier <= 0.0:
            raise ValueError("system_resistance_multiplier must be > 0")
        if not self.mode:
            raise ValueError("mode must not be empty")


@dataclass(frozen=True)
class ModelConfig:
    """Numerical and calibration settings for the reduced-order model.

    Calibration coefficients are explicit because absolute levels cannot be
    inferred from geometry alone.  They must be fitted against an identified
    reference dataset before engineering claims are made.
    """

    frequency_min_hz: float = 20.0
    frequency_max_hz: float = 1000.0
    frequency_step_hz: float = 2.0
    plane_wave_margin: float = 0.70
    allow_out_of_validity: bool = False
    reference_distance_m: float = 1.0
    microphone_distance_m: float = 1.0
    pressure_reference_pa: float = 20e-6
    thermoviscous_loss_db_per_m_at_1khz: float = 0.04
    core_attenuation_db_max: float = 9.0
    core_cutoff_hz: float = 800.0
    tonal_pressure_coefficient: float = 0.0015
    broadband_pressure_coefficient: float = 0.020
    turbulence_intensity: float = 0.08
    gamma_air: float = 1.4
    gas_constant_air_j_per_kgk: float = 287.05
    reference_temperature_c: float = 20.0
    seed: int = 20261126

    def validate(self) -> None:
        _require_positive("frequency_min_hz", self.frequency_min_hz)
        _require_positive("frequency_max_hz", self.frequency_max_hz)
        _require_positive("frequency_step_hz", self.frequency_step_hz)
        _require_positive("reference_distance_m", self.reference_distance_m)
        _require_positive("microphone_distance_m", self.microphone_distance_m)
        _require_positive("pressure_reference_pa", self.pressure_reference_pa)
        _require_positive("core_cutoff_hz", self.core_cutoff_hz)
        if self.frequency_max_hz <= self.frequency_min_hz:
            raise ValueError("frequency_max_hz must be > frequency_min_hz")
        if not 0.0 < self.plane_wave_margin <= 1.0:
            raise ValueError("plane_wave_margin must be in (0, 1]")
        if self.thermoviscous_loss_db_per_m_at_1khz < 0.0:
            raise ValueError("thermoviscous_loss_db_per_m_at_1khz must be >= 0")
        if self.core_attenuation_db_max < 0.0:
            raise ValueError("core_attenuation_db_max must be >= 0")
        if self.tonal_pressure_coefficient < 0.0 or self.broadband_pressure_coefficient < 0.0:
            raise ValueError("source pressure coefficients must be >= 0")
        if not 0.0 < self.turbulence_intensity < 1.0:
            raise ValueError("turbulence_intensity must be in (0, 1)")
        if self.gamma_air <= 1.0 or self.gas_constant_air_j_per_kgk <= 0.0:
            raise ValueError("invalid air constants")

    def frequency_axis(self) -> List[float]:
        self.validate()
        count = int(round((self.frequency_max_hz - self.frequency_min_hz) / self.frequency_step_hz)) + 1
        return [self.frequency_min_hz + i * self.frequency_step_hz for i in range(count)]


@dataclass(frozen=True)
class AirState:
    temperature_k: float
    density_kg_m3: float
    sound_speed_m_s: float


@dataclass(frozen=True)
class OperatingPointResult:
    flow_m3_s: float
    fan_pressure_pa: float
    system_pressure_pa: float
    pressure_residual_pa: float
    tip_speed_m_s: float
    duct_mean_velocity_m_s: float
    fan_shut_pressure_pa: float
    fan_free_flow_m3_s: float
    converged: bool
    iterations: int

    def as_dict(self) -> Dict[str, Any]:
        return {
            "flow_m3_s": self.flow_m3_s,
            "fan_pressure_pa": self.fan_pressure_pa,
            "system_pressure_pa": self.system_pressure_pa,
            "pressure_residual_pa": self.pressure_residual_pa,
            "tip_speed_m_s": self.tip_speed_m_s,
            "duct_mean_velocity_m_s": self.duct_mean_velocity_m_s,
            "fan_shut_pressure_pa": self.fan_shut_pressure_pa,
            "fan_free_flow_m3_s": self.fan_free_flow_m3_s,
            "converged": self.converged,
            "iterations": self.iterations,
        }


@dataclass(frozen=True)
class PropagationValidity:
    equivalent_duct_diameter_m: float
    first_mode_cutoff_hz: float
    valid_max_frequency_hz: float
    requested_max_frequency_hz: float
    within_limit: bool
    note: str

    def as_dict(self) -> Dict[str, Any]:
        return {
            "equivalent_duct_diameter_m": self.equivalent_duct_diameter_m,
            "first_mode_cutoff_hz": self.first_mode_cutoff_hz,
            "valid_max_frequency_hz": self.valid_max_frequency_hz,
            "requested_max_frequency_hz": self.requested_max_frequency_hz,
            "within_limit": self.within_limit,
            "note": self.note,
        }


@dataclass
class ValidationReport:
    passed: bool
    errors: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    metrics: Dict[str, float] = field(default_factory=dict)


@dataclass
class SimulationResult:
    case_id: str
    geometry: Geometry
    operating_point: OperatingPoint
    config: ModelConfig
    air: AirState
    operating: OperatingPointResult
    validity: PropagationValidity
    frequency_hz: List[float]
    psd_pa2_per_hz: List[float]
    narrowband_spl_db: List[float]
    a_weighted_narrowband_spl_db: List[float]
    octave_bands: List[Dict[str, float]]
    oaspl_db: float
    a_weighted_oaspl_db: float
    tonal_components: List[Dict[str, float]]
    source_summary: Dict[str, float]
    warnings: List[str]
    provenance: Dict[str, Any]

    def summary_record(self) -> Dict[str, Any]:
        bpf_hz = self.operating_point.rpm / 60.0 * self.geometry.blade_count
        return {
            "case_id": self.case_id,
            "rpm": self.operating_point.rpm,
            "temperature_c": self.operating_point.temperature_c,
            "mode": self.operating_point.mode,
            "blade_count": self.geometry.blade_count,
            "impeller_outer_diameter_m": self.geometry.impeller_outer_diameter_m,
            "impeller_height_m": self.geometry.impeller_height_m,
            "tongue_gap_ratio": self.geometry.tongue_gap_ratio,
            "blade_spacing_modulation": self.geometry.blade_spacing_modulation,
            "flow_m3_s": self.operating.flow_m3_s,
            "pressure_rise_pa": self.operating.system_pressure_pa,
            "bpf_hz": bpf_hz,
            "oaspl_db": self.oaspl_db,
            "a_weighted_oaspl_db": self.a_weighted_oaspl_db,
            "validity_within_limit": self.validity.within_limit,
            "warning_count": len(self.warnings),
            "data_kind": self.provenance.get("data_kind", ""),
        }

    def input_record(self) -> Dict[str, Any]:
        record = self.summary_record()
        record.update(
            {
                "ambient_pressure_pa": self.operating_point.ambient_pressure_pa,
                "system_resistance_multiplier": self.operating_point.system_resistance_multiplier,
                "duct_area_m2": self.geometry.duct_area_m2,
                "outlet_area_m2": self.geometry.outlet_area_m2,
                "core_area_m2": self.geometry.core_area_m2,
                "core_thickness_m": self.geometry.core_thickness_m,
                "core_porosity": self.geometry.core_porosity,
                "door_opening_fraction": self.geometry.door_opening_fraction,
                "valid_max_frequency_hz": self.validity.valid_max_frequency_hz,
                "requested_max_frequency_hz": self.validity.requested_max_frequency_hz,
                "warnings": " | ".join(self.warnings),
            }
        )
        return record


def dataclass_to_dict(value: Any) -> Any:
    """Convert the small model dataclasses into JSON-safe values."""

    if hasattr(value, "__dataclass_fields__"):
        return {name: dataclass_to_dict(getattr(value, name)) for name in value.__dataclass_fields__}
    if isinstance(value, Mapping):
        return {str(k): dataclass_to_dict(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [dataclass_to_dict(v) for v in value]
    return value
