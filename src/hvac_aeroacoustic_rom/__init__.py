"""Pure-Python parameterized HVAC aeroacoustic reduced-order model."""

from .engine import ENGINE_VERSION, case_from_parameters, generate_batch, simulate_case
from .models import Geometry, ModelConfig, OperatingPoint, SimulationResult
from .sampling import ParameterSpec, default_parameter_specs, latin_hypercube
from .validation import validate_result

__all__ = [
    "ENGINE_VERSION",
    "Geometry",
    "ModelConfig",
    "OperatingPoint",
    "SimulationResult",
    "ParameterSpec",
    "default_parameter_specs",
    "latin_hypercube",
    "case_from_parameters",
    "simulate_case",
    "generate_batch",
    "validate_result",
]
