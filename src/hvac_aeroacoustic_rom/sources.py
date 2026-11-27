"""Parameterized tonal and broadband source models."""

from __future__ import annotations

import cmath
import math
from typing import Dict, List, Sequence, Tuple

from .models import AirState, Geometry, ModelConfig, OperatingPoint, OperatingPointResult


def blade_angles(geometry: Geometry) -> List[float]:
    """Return blade angular positions using an explicit spacing perturbation."""

    z = geometry.blade_count
    beta = geometry.blade_spacing_modulation
    mode = geometry.blade_spacing_order
    return [
        2.0 * math.pi * i / z + beta / z * math.sin(2.0 * math.pi * mode * i / z)
        for i in range(z)
    ]


def order_coefficient(angles: Sequence[float], order: int) -> complex:
    """Return the normalized discrete spatial Fourier coefficient for an order."""

    if order < 0:
        raise ValueError("order must be non-negative")
    return sum(cmath.exp(-1j * order * angle) for angle in angles) / len(angles)


def _add_normalized_gaussian(
    spectrum: List[float],
    frequencies: Sequence[float],
    center_hz: float,
    rms_pa: float,
    sigma_hz: float,
) -> None:
    """Add a Gaussian line whose discrete integral equals ``rms_pa**2``."""

    if rms_pa <= 0.0 or center_hz < frequencies[0] - 5.0 * sigma_hz or center_hz > frequencies[-1] + 5.0 * sigma_hz:
        return
    weights = [math.exp(-0.5 * ((f - center_hz) / sigma_hz) ** 2) for f in frequencies]
    df = frequencies[1] - frequencies[0] if len(frequencies) > 1 else 1.0
    normalizer = sum(weights) * df
    if normalizer <= 0.0:
        return
    energy = rms_pa**2
    for i, weight in enumerate(weights):
        spectrum[i] += energy * weight / normalizer


def tonal_source_psd(
    frequencies: Sequence[float],
    geometry: Geometry,
    operating_point: OperatingPoint,
    operating: OperatingPointResult,
    air: AirState,
    config: ModelConfig,
) -> Tuple[List[float], List[Dict[str, float]], Dict[str, float]]:
    """Build a BPF/sideband source PSD from blade spatial coefficients.

    The absolute scale is a tunable pressure coefficient.  The *locations* of
    BPF and sidebands come from shaft speed, blade count, and blade positions;
    the amplitude still requires calibration.
    """

    spectrum = [0.0 for _ in frequencies]
    angles = blade_angles(geometry)
    z = geometry.blade_count
    rotation_hz = operating_point.rpm / 60.0
    bpf_hz = z * rotation_hz
    dynamic_pressure = 0.5 * air.density_kg_m3 * operating.tip_speed_m_s**2
    area_ratio = geometry.impeller_flow_area_m2 / max(geometry.outlet_area_m2, 1e-12)
    gap_factor = max(0.65, (0.08 / max(geometry.tongue_gap_ratio, 1e-6)) ** 0.35)
    flow_factor = math.sqrt(max(operating.flow_m3_s, 1e-9) / 0.10)
    total_tonal_rms = (
        config.tonal_pressure_coefficient
        * dynamic_pressure
        * math.sqrt(max(area_ratio, 0.1))
        * gap_factor
        * flow_factor
    )

    candidates: List[Tuple[int, float, float, complex]] = []
    for harmonic in (1, 2, 3):
        base_order = harmonic * z
        harmonic_weight = harmonic ** (-1.20)
        for sideband_index in range(-2, 3):
            order = base_order + sideband_index * geometry.blade_spacing_order
            if order <= 0:
                continue
            coefficient = order_coefficient(angles, order)
            energy_weight = harmonic_weight * abs(coefficient) ** 2
            if energy_weight > 1e-12:
                candidates.append((order, energy_weight, harmonic_weight, coefficient))

    total_weight = sum(item[1] for item in candidates)
    if total_weight <= 0.0:
        return spectrum, [], {"tonal_rms_pa": 0.0, "bpf_hz": bpf_hz}

    sigma_hz = max(0.75 * (frequencies[1] - frequencies[0]) if len(frequencies) > 1 else 1.0, 0.5)
    components: List[Dict[str, float]] = []
    for order, energy_weight, _, coefficient in candidates:
        energy_fraction = energy_weight / total_weight
        rms = total_tonal_rms * math.sqrt(energy_fraction)
        center_hz = order * rotation_hz
        _add_normalized_gaussian(spectrum, frequencies, center_hz, rms, sigma_hz)
        components.append(
            {
                "order": float(order),
                "frequency_hz": center_hz,
                "rms_pa": rms,
                "spatial_coefficient_abs": abs(coefficient),
                "sideband_offset_orders": float(order - z),
            }
        )

    return spectrum, components, {"tonal_rms_pa": total_tonal_rms, "bpf_hz": bpf_hz}


def _normalize_shape(shape: Sequence[float], frequencies: Sequence[float]) -> List[float]:
    df = frequencies[1] - frequencies[0] if len(frequencies) > 1 else 1.0
    integral = sum(max(0.0, value) for value in shape) * df
    if integral <= 0.0:
        return [0.0 for _ in shape]
    return [max(0.0, value) / integral for value in shape]


def broadband_source_psd(
    frequencies: Sequence[float],
    geometry: Geometry,
    operating: OperatingPointResult,
    air: AirState,
    config: ModelConfig,
) -> Tuple[List[float], Dict[str, float]]:
    """Build a von-Karman-like broadband source PSD.

    The model uses a turbulence intensity and integral length scale to set the
    source variance and turnover frequency.  It is a low-order source model,
    not a direct wall-pressure spectrum from an unsteady CFD solution.
    """

    hydraulic_diameter = geometry.equivalent_duct_diameter_m
    velocity = max(operating.duct_mean_velocity_m_s, 1e-6)
    integral_length = max(0.015, 0.07 * hydraulic_diameter)
    turnover_hz = max(1.0, velocity / (2.0 * math.pi * integral_length))
    pressure_rms = (
        config.broadband_pressure_coefficient
        * air.density_kg_m3
        * velocity**2
        * config.turbulence_intensity
        * math.sqrt(max(0.35, geometry.door_opening_fraction))
    )

    shape = []
    for frequency in frequencies:
        ratio = frequency / turnover_hz
        # Low-frequency roll-up with an approximately -5/3 high-frequency tail.
        shape.append((ratio**2) / (1.0 + ratio**2) ** (17.0 / 6.0))
    normalized_shape = _normalize_shape(shape, frequencies)
    spectrum = [pressure_rms**2 * value for value in normalized_shape]
    return spectrum, {
        "broadband_rms_pa": pressure_rms,
        "turnover_frequency_hz": turnover_hz,
        "integral_length_m": integral_length,
    }
