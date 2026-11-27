"""Plane-wave acoustic propagation with explicit validity reporting."""

from __future__ import annotations

import math
from typing import List, Sequence

from .models import AirState, Geometry, ModelConfig, PropagationValidity


def propagation_validity(
    frequencies: Sequence[float], geometry: Geometry, air: AirState, config: ModelConfig
) -> PropagationValidity:
    """Return the conservative plane-wave validity range.

    The first circular-duct mode cutoff is approximated as
    ``1.84*c/(pi*D_eq)``.  The transfer function is only considered valid up
    to ``plane_wave_margin`` times that cutoff.  Above that range the model can
    still be run only when the caller explicitly opts in.
    """

    diameter = geometry.equivalent_duct_diameter_m
    first_mode_cutoff = 1.84 * air.sound_speed_m_s / (math.pi * diameter)
    valid_max = config.plane_wave_margin * first_mode_cutoff
    requested_max = max(frequencies)
    within = requested_max <= valid_max + 1e-12
    note = (
        "Plane-wave transfer model is within its conservative first-mode limit."
        if within
        else "Requested band exceeds the conservative plane-wave limit; modal/reflection effects are not resolved."
    )
    return PropagationValidity(
        equivalent_duct_diameter_m=diameter,
        first_mode_cutoff_hz=first_mode_cutoff,
        valid_max_frequency_hz=valid_max,
        requested_max_frequency_hz=requested_max,
        within_limit=within,
        note=note,
    )


def transfer_power(
    frequencies: Sequence[float], geometry: Geometry, config: ModelConfig, air: AirState
) -> List[float]:
    """Return ``|H(f)|^2`` for a lumped plane-wave path."""

    distance_factor = (config.reference_distance_m / config.microphone_distance_m) ** 2
    diameter_scale = max(geometry.equivalent_duct_diameter_m / 0.10, 1e-6)
    result: List[float] = []
    for frequency in frequencies:
        thermoviscous_db = (
            config.thermoviscous_loss_db_per_m_at_1khz
            * geometry.duct_length_m
            * math.sqrt(max(frequency, 1.0) / 1000.0)
            / math.sqrt(diameter_scale)
        )
        core_fraction = frequency**2 / (frequency**2 + config.core_cutoff_hz**2)
        core_db = config.core_attenuation_db_max * core_fraction * (1.0 - geometry.core_porosity)
        total_loss_db = thermoviscous_db + core_db
        result.append(distance_factor * 10.0 ** (-total_loss_db / 10.0))
    return result
