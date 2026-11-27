"""Public simulation and batch-generation API."""

from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence, Tuple

from .models import Geometry, ModelConfig, OperatingPoint, SimulationResult, dataclass_to_dict
from .operating_point import air_state, solve_operating_point
from .propagation import propagation_validity, transfer_power
from .sources import broadband_source_psd, tonal_source_psd
from .spectrum import analyze_psd, a_weighting_db
from .validation import validate_result


ENGINE_VERSION = "0.1.0"


def simulate_case(
    case_id: str = "case-0001",
    geometry: Optional[Geometry] = None,
    operating_point: Optional[OperatingPoint] = None,
    config: Optional[ModelConfig] = None,
) -> SimulationResult:
    """Run one deterministic reduced-order aeroacoustic simulation."""

    geometry = geometry or Geometry()
    operating_point = operating_point or OperatingPoint()
    config = config or ModelConfig()
    geometry.validate()
    operating_point.validate()
    config.validate()

    frequencies = config.frequency_axis()
    air = air_state(operating_point, config.gamma_air, config.gas_constant_air_j_per_kgk)
    operating = solve_operating_point(geometry, operating_point, air)
    validity = propagation_validity(frequencies, geometry, air, config)
    if not validity.within_limit and not config.allow_out_of_validity:
        raise ValueError(
            f"requested frequency maximum {validity.requested_max_frequency_hz:.3f} Hz exceeds "
            f"the conservative plane-wave limit {validity.valid_max_frequency_hz:.3f} Hz; "
            "set allow_out_of_validity=True only for exploratory output"
        )

    tonal_psd, tonal_components, tonal_summary = tonal_source_psd(
        frequencies, geometry, operating_point, operating, air, config
    )
    broadband_psd, broadband_summary = broadband_source_psd(
        frequencies, geometry, operating, air, config
    )
    propagation_power = transfer_power(frequencies, geometry, config, air)
    total_psd = [
        max(0.0, (tonal + broadband) * path_gain)
        for tonal, broadband, path_gain in zip(tonal_psd, broadband_psd, propagation_power)
    ]
    spectral = analyze_psd(frequencies, total_psd, config.pressure_reference_pa)
    warnings = []
    if not validity.within_limit:
        warnings.append(validity.note)
    warnings.append("Absolute source levels use explicit uncalibrated reduced-order coefficients.")

    provenance = {
        "engine": "hvac_aeroacoustic_rom",
        "engine_version": ENGINE_VERSION,
        "data_kind": "parameterized_numerical_simulation",
        "experimental_data": False,
        "cfd_or_caa_solver": False,
        "calibrated_against_experiment": False,
        "model_scope": "fan/system operating point + tonal/broadband sources + lumped plane-wave path",
        "validity": validity.as_dict(),
        "calibration_note": (
            "Tonal and broadband pressure coefficients are modeling defaults. "
            "Fit them against identified reference measurements before reporting absolute accuracy."
        ),
    }

    result = SimulationResult(
        case_id=case_id,
        geometry=geometry,
        operating_point=operating_point,
        config=config,
        air=air,
        operating=operating,
        validity=validity,
        frequency_hz=list(frequencies),
        psd_pa2_per_hz=total_psd,
        narrowband_spl_db=list(spectral["narrowband_spl_db"]),
        a_weighted_narrowband_spl_db=list(spectral["a_weighted_narrowband_spl_db"]),
        octave_bands=list(spectral["octave_bands"]),
        oaspl_db=float(spectral["oaspl_db"]),
        a_weighted_oaspl_db=float(spectral["a_weighted_oaspl_db"]),
        tonal_components=tonal_components,
        source_summary={**tonal_summary, **broadband_summary},
        warnings=warnings,
        provenance=provenance,
    )
    report = validate_result(result)
    if not report.passed:
        raise RuntimeError("internal simulation validation failed: " + "; ".join(report.errors))
    return result


def case_from_parameters(
    parameters: Mapping[str, Any], config: Optional[ModelConfig] = None
) -> Tuple[Geometry, OperatingPoint]:
    """Map a sampled parameter record to validated model input dataclasses."""

    geometry_fields = {
        "impeller_outer_diameter_m",
        "impeller_inlet_diameter_m",
        "impeller_height_m",
        "blade_count",
        "blade_thickness_m",
        "tongue_gap_ratio",
        "blade_spacing_modulation",
        "blade_spacing_order",
        "duct_length_m",
        "duct_area_m2",
        "outlet_area_m2",
        "core_area_m2",
        "core_thickness_m",
        "core_porosity",
        "door_opening_fraction",
        "scroll_expansion_ratio",
    }
    operating_fields = {
        "rpm",
        "temperature_c",
        "ambient_pressure_pa",
        "system_resistance_multiplier",
        "mode",
    }
    geometry_values = {key: value for key, value in parameters.items() if key in geometry_fields}
    operating_values = {key: value for key, value in parameters.items() if key in operating_fields}
    geometry = Geometry(**geometry_values)
    operating = OperatingPoint(**operating_values)
    geometry.validate()
    operating.validate()
    return geometry, operating


def generate_batch(
    samples: Sequence[Mapping[str, Any]],
    output_dir: Path,
    config: Optional[ModelConfig] = None,
) -> List[SimulationResult]:
    """Generate cases and write CSV/JSON outputs with provenance metadata."""

    config = config or ModelConfig()
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    results: List[SimulationResult] = []
    for index, sample in enumerate(samples, start=1):
        geometry, operating_point = case_from_parameters(sample, config)
        results.append(
            simulate_case(
                case_id=f"case-{index:05d}",
                geometry=geometry,
                operating_point=operating_point,
                config=config,
            )
        )

    metadata_path = output_dir / "metadata.csv"
    with metadata_path.open("w", newline="", encoding="utf-8") as handle:
        records = [result.input_record() for result in results]
        fieldnames = sorted({key for record in records for key in record}) if records else ["case_id"]
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(records)

    spectra_path = output_dir / "spectra.csv"
    with spectra_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=[
                "case_id",
                "frequency_hz",
                "psd_pa2_per_hz",
                "narrowband_spl_db",
                "a_weighted_narrowband_spl_db",
            ],
        )
        writer.writeheader()
        for result in results:
            for frequency, psd, spl, a_spl in zip(
                result.frequency_hz,
                result.psd_pa2_per_hz,
                result.narrowband_spl_db,
                result.a_weighted_narrowband_spl_db,
            ):
                writer.writerow(
                    {
                        "case_id": result.case_id,
                        "frequency_hz": f"{frequency:.9g}",
                        "psd_pa2_per_hz": f"{psd:.12g}",
                        "narrowband_spl_db": f"{spl:.9g}",
                        "a_weighted_narrowband_spl_db": f"{a_spl:.9g}",
                    }
                )

    octave_path = output_dir / "octave_bands.csv"
    with octave_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=[
                "case_id",
                "center_frequency_hz",
                "lower_frequency_hz",
                "upper_frequency_hz",
                "band_energy_pa2",
                "level_db",
            ],
        )
        writer.writeheader()
        for result in results:
            for band in result.octave_bands:
                writer.writerow({"case_id": result.case_id, **band})

    provenance = {
        "schema_version": "0.1",
        "engine_version": ENGINE_VERSION,
        "data_kind": "parameterized_numerical_simulation",
        "experimental_data": False,
        "case_count": len(results),
        "files": {
            "metadata.csv": "one row per simulated case and its operating-point summary",
            "spectra.csv": "one-sided PSD in Pa^2/Hz plus derived narrowband levels",
            "octave_bands.csv": "one-third-octave energies and levels derived from the same PSD",
        },
        "model_config": dataclass_to_dict(config),
        "case_provenance": [result.provenance for result in results],
    }
    (output_dir / "provenance.json").write_text(
        json.dumps(provenance, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return results
