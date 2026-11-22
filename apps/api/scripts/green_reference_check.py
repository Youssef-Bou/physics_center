"""Offline checks of developer-encoded Green reference equations, never model code.

Requires the optional math extra. These identities do not validate all reference
prose, physical assumptions, source authority, or any model answer.
"""

import argparse
import hashlib
import json
from pathlib import Path

import sympy as sp

from app.modules.evaluation.dataset import dataset_fingerprint, load_dataset
from app.modules.evaluation.reporting import export_report

DATASET = (
    Path(__file__).resolve().parents[1] / "app/modules/evaluation/data/physics_adaptive_v1.json"
)
CASE_ID = "ELECTROSTATIC_GREEN_DIRICHLET"


def check_reference():
    dataset = load_dataset(DATASET)
    case = next(case for case in dataset.cases if case.id == CASE_ID)
    x, xi, length, epsilon = sp.symbols("x xi L epsilon", positive=True)
    va, vb, rho0 = sp.symbols("Va Vb rho0", real=True)
    rho = sp.Function("rho")
    left = x * (length - xi) / length  # 0 < x < xi < L
    right = xi * (length - x) / length  # 0 < xi < x < L
    lift = va * (1 - x / length) + vb * x / length
    integral = (
        (length - x) * sp.Integral(xi * rho(xi), (xi, 0, x))
        + x * sp.Integral((length - xi) * rho(xi), (xi, x, length))
    ) / length
    potential = lift + integral / epsilon
    constant_integral = sp.integrate(right, (xi, 0, x)) + sp.integrate(left, (xi, x, length))
    constant_potential = lift + rho0 * constant_integral / epsilon
    field = -sp.diff(constant_potential, x)
    jump = sp.diff(right, x) - sp.diff(left, x)
    residuals = {
        "left_homogeneous_equation": sp.diff(left, x, 2),
        "right_homogeneous_equation": sp.diff(right, x, 2),
        "left_boundary": left.subs(x, 0),
        "right_boundary": right.subs(x, length),
        "continuity": (right - left).subs(x, xi),
        "derivative_jump_minus_one": jump + 1,
        "kernel_symmetry": left - right.xreplace({x: xi, xi: x}),
        "general_poisson_equation": -sp.diff(potential, x, 2) - rho(x) / epsilon,
        "general_left_boundary": potential.subs(x, 0) - va,
        "general_right_boundary": potential.subs(x, length) - vb,
        "constant_charge_integral": constant_integral - x * (length - x) / 2,
        "constant_charge_poisson": -sp.diff(constant_potential, x, 2) - rho0 / epsilon,
        "constant_charge_field": field
        - ((va - vb) / length - rho0 * (length - 2 * x) / (2 * epsilon)),
        "gauss_equation": sp.diff(field, x) - rho0 / epsilon,
        "field_voltage_integral": sp.integrate(field, (x, 0, length)) - (va - vb),
        "zero_charge_limit": constant_potential.subs(rho0, 0) - lift,
    }
    checks = []
    for name, residual in residuals.items():
        simplified = sp.simplify(residual)
        checks.append({"id": name, "passed": simplified == 0, "residual": str(simplified)})

    # SI exponent vectors (kg, m, s, A); this verifies declared units only.
    voltage = sp.Matrix([1, 2, -3, -1])
    metre = sp.Matrix([0, 1, 0, 0])
    charge_density = sp.Matrix([0, -3, 1, 1])
    permittivity = sp.Matrix([-1, -3, 4, 2])
    checks.extend(
        [
            {
                "id": "poisson_si_units",
                "passed": charge_density - permittivity == voltage - 2 * metre,
            },
            {
                "id": "potential_integral_si_units",
                "passed": metre + charge_density - permittivity + metre == voltage,
            },
            {"id": "wrong_jump_sign_detected", "passed": sp.simplify(-jump + 1) != 0},
            {
                "id": "omitted_boundary_lift_detected",
                "passed": sp.simplify((integral / epsilon).subs(x, 0) - va) != 0,
            },
        ]
    )
    sources = {source.id: source for source in dataset.sources}
    return {
        "schema_version": "physics-green-reference-check.v1",
        "method": "symbolic",
        "sympy_version": sp.__version__,
        "script_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        "dataset": {
            "id": dataset.id,
            "version": dataset.version,
            "sha256": dataset_fingerprint(dataset),
        },
        "case_id": case.id,
        "reference_status": case.validation.status,
        "reference_sha256": hashlib.sha256(case.reference_solution.encode()).hexdigest(),
        "expected_source_pages": [
            {
                "source_id": expected.source_id,
                "page_number": expected.page_number,
                "page_sha256": hashlib.sha256(
                    sources[expected.source_id].pages[expected.page_number - 1].encode()
                ).hexdigest(),
            }
            for expected in case.expected_sources
        ],
        "assumptions": [
            "L>0, epsilon>0 constant, 0<x<L, 0<xi<L",
            "rho in C([0,L]); classical potential in C²([0,L])",
            "planar translational symmetry; rho is a volume charge density",
        ],
        "checks": checks,
        "all_checks_passed": all(check["passed"] for check in checks),
        "physics_proof": False,
        "scientific_quality_established": False,
        "limitations": [
            "Checks trusted developer-encoded equations, not arbitrary reference prose.",
            "Continuity and jump imply the delta identity under distribution theory; not checked here.",
            "Existence, uniqueness, geometry and source authority need separate review.",
            "No model call, model answer rating or human validation was performed.",
        ],
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    report = check_reference()
    if args.output:
        export_report(report, args.output)
    print(json.dumps(report, ensure_ascii=False, indent=2, allow_nan=False))
    return 0 if report["all_checks_passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
