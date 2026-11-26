from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from hvac_aeroacoustic_rom import (
    Geometry,
    ModelConfig,
    OperatingPoint,
    default_parameter_specs,
    generate_batch,
    latin_hypercube,
    simulate_case,
    validate_result,
)
from hvac_aeroacoustic_rom.sources import blade_angles, order_coefficient


class EngineTests(unittest.TestCase):
    def test_operating_point_converges_and_balances_pressure(self) -> None:
        result = simulate_case(config=ModelConfig(frequency_max_hz=900.0))
        self.assertTrue(result.operating.converged)
        self.assertGreater(result.operating.flow_m3_s, 0.0)
        self.assertAlmostEqual(
            result.operating.fan_pressure_pa,
            result.operating.system_pressure_pa,
            delta=1e-5 * result.operating.fan_shut_pressure_pa,
        )

    def test_psd_octave_and_oaspl_are_consistent(self) -> None:
        result = simulate_case(config=ModelConfig(frequency_max_hz=900.0))
        report = validate_result(result)
        self.assertTrue(report.passed, report.errors)
        self.assertLess(report.metrics["oaspl_reconstruction_error_db"], 1e-9)
        self.assertAlmostEqual(report.metrics["octave_energy_fraction"], 1.0, delta=0.03)
        self.assertGreater(result.oaspl_db, 0.0)
        self.assertGreater(result.a_weighted_oaspl_db, 0.0)

    def test_bpf_moves_with_rpm_and_blade_count(self) -> None:
        result = simulate_case(
            geometry=Geometry(blade_count=41),
            operating_point=OperatingPoint(rpm=3000.0),
            config=ModelConfig(frequency_max_hz=1000.0),
        )
        expected = 41 * 3000.0 / 60.0
        bpf = min(result.tonal_components, key=lambda item: abs(item["frequency_hz"] - expected))
        self.assertAlmostEqual(bpf["frequency_hz"], expected)

    def test_spacing_modulation_creates_sidebands(self) -> None:
        base = Geometry(blade_spacing_modulation=0.0)
        modulated = Geometry(blade_spacing_modulation=1.2)
        base_angles = blade_angles(base)
        mod_angles = blade_angles(modulated)
        base_sideband = abs(order_coefficient(base_angles, base.blade_count + base.blade_spacing_order))
        mod_sideband = abs(order_coefficient(mod_angles, modulated.blade_count + modulated.blade_spacing_order))
        self.assertLess(base_sideband, 1e-10)
        self.assertGreater(mod_sideband, base_sideband + 1e-5)

    def test_validity_limit_is_enforced(self) -> None:
        with self.assertRaises(ValueError):
            simulate_case(config=ModelConfig(frequency_max_hz=5000.0))
        result = simulate_case(
            config=ModelConfig(frequency_max_hz=5000.0, allow_out_of_validity=True)
        )
        self.assertFalse(result.validity.within_limit)
        self.assertTrue(any("validity" in warning.lower() or "plane-wave" in warning.lower() for warning in result.warnings))

    def test_sampling_is_deterministic_and_bounded(self) -> None:
        specs = default_parameter_specs()
        first = latin_hypercube(specs, 11, seed=7)
        second = latin_hypercube(specs, 11, seed=7)
        self.assertEqual(first, second)
        for record in first:
            self.assertGreaterEqual(record["rpm"], 1400.0)
            self.assertLessEqual(record["rpm"], 4300.0)
            self.assertIn(record["blade_count"], [35, 37, 39, 41, 43, 45])

    def test_batch_writes_provenance_and_paired_outputs(self) -> None:
        samples = latin_hypercube(default_parameter_specs(), 3, seed=123)
        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp)
            results = generate_batch(samples, output, ModelConfig(frequency_max_hz=900.0))
            self.assertEqual(len(results), 3)
            for filename in ("metadata.csv", "spectra.csv", "octave_bands.csv", "provenance.json"):
                self.assertTrue((output / filename).exists(), filename)
            provenance = json.loads((output / "provenance.json").read_text(encoding="utf-8"))
            self.assertEqual(provenance["data_kind"], "parameterized_numerical_simulation")
            self.assertFalse(provenance["experimental_data"])


if __name__ == "__main__":
    unittest.main()
