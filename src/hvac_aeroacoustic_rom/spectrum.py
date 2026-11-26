"""PSD, narrowband, A-weighted, and one-third-octave calculations."""

from __future__ import annotations

import math
from typing import Dict, List, Sequence


def _db10(value: float, reference: float = 1.0) -> float:
    return 10.0 * math.log10(max(value, 1e-300) / reference)


def one_third_octave_centers(frequency_min_hz: float, frequency_max_hz: float) -> List[float]:
    centers: List[float] = []
    k = math.floor(3.0 * math.log2(frequency_min_hz / 1000.0)) - 2
    while True:
        center = 1000.0 * 2.0 ** (k / 3.0)
        lower = center * 2.0 ** (-1.0 / 6.0)
        if lower > frequency_max_hz:
            break
        if center * 2.0 ** (1.0 / 6.0) >= frequency_min_hz:
            centers.append(center)
        k += 1
        if k > 100:
            raise RuntimeError("octave-band generation did not terminate")
    return centers


def a_weighting_db(frequency_hz: float) -> float:
    if frequency_hz <= 0.0:
        return -200.0
    f2 = frequency_hz**2
    ra = (
        (12194.0**2 * frequency_hz**4)
        / ((f2 + 20.6**2) * math.sqrt((f2 + 107.7**2) * (f2 + 737.9**2)) * (f2 + 12194.0**2))
    )
    return 20.0 * math.log10(max(ra, 1e-300)) + 2.0


def integrate_psd(psd_pa2_per_hz: Sequence[float], frequency_step_hz: float) -> float:
    if frequency_step_hz <= 0.0:
        raise ValueError("frequency_step_hz must be > 0")
    return sum(max(0.0, value) for value in psd_pa2_per_hz) * frequency_step_hz


def psd_to_spl_db(
    psd_pa2_per_hz: Sequence[float], frequency_step_hz: float, pressure_reference_pa: float
) -> List[float]:
    return [
        _db10(max(value, 0.0) * frequency_step_hz, pressure_reference_pa**2)
        for value in psd_pa2_per_hz
    ]


def oaspl_db(psd_pa2_per_hz: Sequence[float], frequency_step_hz: float, pressure_reference_pa: float) -> float:
    return _db10(integrate_psd(psd_pa2_per_hz, frequency_step_hz), pressure_reference_pa**2)


def weighted_oaspl_db(
    frequencies: Sequence[float],
    psd_pa2_per_hz: Sequence[float],
    frequency_step_hz: float,
    pressure_reference_pa: float,
) -> float:
    weighted_psd = [value * 10.0 ** (a_weighting_db(f) / 10.0) for f, value in zip(frequencies, psd_pa2_per_hz)]
    return oaspl_db(weighted_psd, frequency_step_hz, pressure_reference_pa)


def octave_band_levels(
    frequencies: Sequence[float],
    psd_pa2_per_hz: Sequence[float],
    frequency_step_hz: float,
    pressure_reference_pa: float,
) -> List[Dict[str, float]]:
    if len(frequencies) != len(psd_pa2_per_hz) or not frequencies:
        raise ValueError("frequency and PSD arrays must be non-empty and equal length")
    bands: List[Dict[str, float]] = []
    for center in one_third_octave_centers(frequencies[0], frequencies[-1]):
        lower = center * 2.0 ** (-1.0 / 6.0)
        upper = center * 2.0 ** (1.0 / 6.0)
        energy = sum(
            max(0.0, psd) * frequency_step_hz
            for frequency, psd in zip(frequencies, psd_pa2_per_hz)
            if lower <= frequency < upper
        )
        bands.append(
            {
                "center_frequency_hz": center,
                "lower_frequency_hz": lower,
                "upper_frequency_hz": upper,
                "band_energy_pa2": energy,
                "level_db": _db10(energy, pressure_reference_pa**2),
            }
        )
    return bands


def analyze_psd(
    frequencies: Sequence[float], psd_pa2_per_hz: Sequence[float], pressure_reference_pa: float
) -> Dict[str, object]:
    if len(frequencies) < 2 or len(frequencies) != len(psd_pa2_per_hz):
        raise ValueError("frequency and PSD arrays must contain at least two matching points")
    step = frequencies[1] - frequencies[0]
    if step <= 0.0 or any(abs((frequencies[i + 1] - frequencies[i]) - step) > 1e-9 for i in range(len(frequencies) - 1)):
        raise ValueError("frequency axis must be uniformly spaced and increasing")
    spl = psd_to_spl_db(psd_pa2_per_hz, step, pressure_reference_pa)
    weighted_spl = [level + a_weighting_db(f) for f, level in zip(frequencies, spl)]
    return {
        "frequency_step_hz": step,
        "narrowband_spl_db": spl,
        "a_weighted_narrowband_spl_db": weighted_spl,
        "octave_bands": octave_band_levels(frequencies, psd_pa2_per_hz, step, pressure_reference_pa),
        "oaspl_db": oaspl_db(psd_pa2_per_hz, step, pressure_reference_pa),
        "a_weighted_oaspl_db": weighted_oaspl_db(
            frequencies, psd_pa2_per_hz, step, pressure_reference_pa
        ),
    }
