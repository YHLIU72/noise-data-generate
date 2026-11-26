"""Low-order fan/system operating-point calculation."""

from __future__ import annotations

import math

from .models import AirState, Geometry, OperatingPoint, OperatingPointResult


def air_state(operating_point: OperatingPoint, gamma: float, gas_constant: float) -> AirState:
    operating_point.validate()
    temperature_k = operating_point.temperature_c + 273.15
    density = operating_point.ambient_pressure_pa / (gas_constant * temperature_k)
    sound_speed = math.sqrt(gamma * gas_constant * temperature_k)
    return AirState(
        temperature_k=temperature_k,
        density_kg_m3=density,
        sound_speed_m_s=sound_speed,
    )


def fan_characteristic(
    flow_m3_s: float,
    geometry: Geometry,
    operating_point: OperatingPoint,
    air: AirState,
) -> tuple[float, float, float]:
    """Return fan pressure, shut pressure, and free-flow capacity.

    This is a compact affinity-law fan curve, not a CFD solution.  The
    coefficients are exposed through the equations and are intended to be
    calibrated against a fan-map reference before quantitative claims.
    """

    tip_speed = math.pi * geometry.impeller_outer_diameter_m * operating_point.rpm / 60.0
    gap_factor = max(0.55, 1.0 - 0.9 * geometry.tongue_gap_ratio)
    inlet_ratio = geometry.impeller_inlet_diameter_m / geometry.impeller_outer_diameter_m
    blockage_factor = max(0.55, 1.0 - 0.18 * (1.0 - inlet_ratio))
    shut_pressure = 0.55 * air.density_kg_m3 * tip_speed**2 * gap_factor * blockage_factor

    free_flow = (
        0.36
        * geometry.impeller_flow_area_m2
        * tip_speed
        * math.sqrt(max(0.25, geometry.scroll_expansion_ratio / 1.4))
        * (1.0 - 0.15 * geometry.tongue_gap_ratio)
    )
    if free_flow <= 0.0:
        return 0.0, shut_pressure, 0.0
    normalized_flow = max(0.0, min(flow_m3_s / free_flow, 1.0))
    pressure = shut_pressure * max(0.0, 1.0 - normalized_flow**2)
    return pressure, shut_pressure, free_flow


def system_pressure(
    flow_m3_s: float,
    geometry: Geometry,
    operating_point: OperatingPoint,
    air: AirState,
) -> float:
    """Return the lumped system pressure drop at the requested flow."""

    if flow_m3_s <= 0.0:
        return 0.0
    hydraulic_area = min(
        geometry.duct_area_m2,
        geometry.outlet_area_m2,
        geometry.core_area_m2 * geometry.door_opening_fraction,
    )
    hydraulic_diameter = math.sqrt(4.0 * hydraulic_area / math.pi)
    velocity = flow_m3_s / hydraulic_area

    core_loss = 2.0 + 0.7 * geometry.core_thickness_m / 0.038 + 0.8 * (1.0 - geometry.core_porosity)
    duct_loss = 0.7 + 0.12 * geometry.duct_length_m / max(hydraulic_diameter, 1e-9)
    door_loss = 0.35 / geometry.door_opening_fraction**2
    expansion_loss = 0.25 * (geometry.scroll_expansion_ratio - 1.0) ** 2
    loss_coefficient = (core_loss + duct_loss + door_loss + expansion_loss) * operating_point.system_resistance_multiplier
    return 0.5 * air.density_kg_m3 * loss_coefficient * velocity**2


def solve_operating_point(
    geometry: Geometry,
    operating_point: OperatingPoint,
    air: AirState,
    max_iterations: int = 80,
) -> OperatingPointResult:
    """Solve ``fan_pressure(Q) = system_pressure(Q)`` by bisection."""

    geometry.validate()
    operating_point.validate()
    tip_speed = math.pi * geometry.impeller_outer_diameter_m * operating_point.rpm / 60.0
    _, shut_pressure, free_flow = fan_characteristic(0.0, geometry, operating_point, air)
    if free_flow <= 0.0:
        raise ValueError("fan free-flow capacity is not positive")

    def residual(flow: float) -> float:
        fan_p, _, _ = fan_characteristic(flow, geometry, operating_point, air)
        return fan_p - system_pressure(flow, geometry, operating_point, air)

    low = 0.0
    high = free_flow
    low_residual = residual(low)
    high_residual = residual(high)
    if low_residual < 0.0 or high_residual > 0.0:
        raise RuntimeError(
            f"operating-point bracket failed: residuals=({low_residual:.6g}, {high_residual:.6g})"
        )

    midpoint = 0.5 * (low + high)
    for iteration in range(1, max_iterations + 1):
        midpoint = 0.5 * (low + high)
        mid_residual = residual(midpoint)
        if abs(mid_residual) < 1e-8 * max(shut_pressure, 1.0):
            break
        if mid_residual > 0.0:
            low = midpoint
        else:
            high = midpoint

    fan_pressure, _, _ = fan_characteristic(midpoint, geometry, operating_point, air)
    system_p = system_pressure(midpoint, geometry, operating_point, air)
    velocity = midpoint / geometry.duct_area_m2
    return OperatingPointResult(
        flow_m3_s=midpoint,
        fan_pressure_pa=fan_pressure,
        system_pressure_pa=system_p,
        pressure_residual_pa=fan_pressure - system_p,
        tip_speed_m_s=tip_speed,
        duct_mean_velocity_m_s=velocity,
        fan_shut_pressure_pa=shut_pressure,
        fan_free_flow_m3_s=free_flow,
        converged=abs(fan_pressure - system_p) < 1e-5 * max(shut_pressure, 1.0),
        iterations=iteration,
    )
