"""Internal consistency checks for generated cases."""

from __future__ import annotations

import math

from .models import SimulationResult, ValidationReport
from .spectrum import integrate_psd


def validate_result(result: SimulationResult) -> ValidationReport:
    errors = []
    warnings = list(result.warnings)
    frequencies = result.frequency_hz
    psd = result.psd_pa2_per_hz

    if len(frequencies) < 2 or len(frequencies) != len(psd):
        errors.append("frequency and PSD arrays must have the same length >= 2")
        return ValidationReport(False, errors, warnings)
    if any(not math.isfinite(value) for value in frequencies + psd):
        errors.append("frequency or PSD contains a non-finite value")
    if any(frequencies[i + 1] <= frequencies[i] for i in range(len(frequencies) - 1)):
        errors.append("frequency axis is not strictly increasing")
    if any(value < -1e-18 for value in psd):
        errors.append("PSD contains a negative value")

    step = frequencies[1] - frequencies[0]
    integrated_energy = integrate_psd(psd, step)
    reconstructed_oaspl = 10.0 * math.log10(max(integrated_energy, 1e-300) / result.config.pressure_reference_pa**2)
    oaspl_error_db = abs(reconstructed_oaspl - result.oaspl_db)
    if oaspl_error_db > 1e-9:
        errors.append(f"OASPL does not match PSD integral ({oaspl_error_db:.3g} dB)")

    octave_energy = sum(max(0.0, band["band_energy_pa2"]) for band in result.octave_bands)
    octave_fraction = octave_energy / integrated_energy if integrated_energy > 0.0 else 0.0
    if abs(octave_fraction - 1.0) > 0.03:
        errors.append(f"one-third-octave energy coverage is {octave_fraction:.5f}, expected ~1")

    if not result.operating.converged:
        errors.append("operating-point solver did not converge")
    if abs(result.operating.pressure_residual_pa) > 1e-5 * max(result.operating.fan_shut_pressure_pa, 1.0):
        errors.append("operating-point pressure residual is too large")
    if result.operating.flow_m3_s <= 0.0 or result.operating.system_pressure_pa < 0.0:
        errors.append("operating-point flow/pressure is nonphysical")

    expected_bpf = result.operating_point.rpm / 60.0 * result.geometry.blade_count
    if not any(abs(item["frequency_hz"] - expected_bpf) <= 1e-9 for item in result.tonal_components):
        warnings.append("BPF component is outside the requested frequency band or was not generated")

    if not result.validity.within_limit:
        warnings.append("requested frequency range exceeds the plane-wave propagation validity limit")
    if result.provenance.get("experimental_data") is not False:
        errors.append("provenance must explicitly state experimental_data=false")
    if result.provenance.get("data_kind") != "parameterized_numerical_simulation":
        errors.append("provenance data_kind is not the expected simulation label")

    metrics = {
        "oaspl_reconstruction_error_db": oaspl_error_db,
        "integrated_energy_pa2": integrated_energy,
        "octave_energy_fraction": octave_fraction,
        "pressure_residual_pa": abs(result.operating.pressure_residual_pa),
    }
    return ValidationReport(not errors, errors, warnings, metrics)
