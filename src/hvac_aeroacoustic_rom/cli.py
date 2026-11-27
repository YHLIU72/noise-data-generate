"""Command-line entry point for reproducible batch generation."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from .engine import generate_batch
from .models import ModelConfig
from .sampling import default_parameter_specs, latin_hypercube, specs_from_mapping


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Generate parameterized HVAC aeroacoustic numerical data")
    parser.add_argument("--output", type=Path, required=True, help="output directory")
    parser.add_argument("--samples", type=int, default=8, help="number of Latin-hypercube cases")
    parser.add_argument("--seed", type=int, default=20261126)
    parser.add_argument("--frequency-min", type=float, default=20.0)
    parser.add_argument("--frequency-max", type=float, default=1000.0)
    parser.add_argument("--frequency-step", type=float, default=2.0)
    parser.add_argument(
        "--allow-out-of-validity",
        action="store_true",
        help="allow exploratory output above the conservative plane-wave limit; provenance will record a warning",
    )
    parser.add_argument(
        "--ranges-json",
        type=Path,
        help="optional JSON object mapping parameter names to {low, high, kind} or {values, kind}",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.ranges_json:
        specs = specs_from_mapping(json.loads(args.ranges_json.read_text(encoding="utf-8")))
    else:
        specs = default_parameter_specs()
    samples = latin_hypercube(specs, args.samples, args.seed)
    config = ModelConfig(
        frequency_min_hz=args.frequency_min,
        frequency_max_hz=args.frequency_max,
        frequency_step_hz=args.frequency_step,
        allow_out_of_validity=args.allow_out_of_validity,
        seed=args.seed,
    )
    results = generate_batch(samples, args.output, config)
    print(
        json.dumps(
            {
                "case_count": len(results),
                "output": str(args.output),
                "data_kind": "parameterized_numerical_simulation",
                "experimental_data": False,
            },
            ensure_ascii=False,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
