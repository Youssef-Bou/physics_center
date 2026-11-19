"""Controlled symbolic examples and hostile-input checks; no provider calls."""

import importlib.util

import pytest
from pydantic import ValidationError

from app.modules.tutor.mathematics import MathCheckRequest, MathCheckResult, SympyMathTool

HAS_SYMPY = importlib.util.find_spec("sympy") is not None
requires_sympy = pytest.mark.skipif(not HAS_SYMPY, reason="Optional SymPy group is not installed")


@pytest.mark.parametrize(
    "expression",
    [
        "__import__('os')",
        "x.__class__",
        "x[0]",
        "lambda: x",
        "[x for x in x]",
        "Symbol('x')",
        "open('file')",
        "eval('1')",
        "sin(x, x)",
        "sin(x=1)",
        "x**x",
        "x**11",
        "x**-11",
        "x**(2**3)",
        "(x**2)**2",
        "1e309",
        "1000001",
        "True",
        "'x'",
        "{x: x}",
        "(x, x)",
        "1e-999",
    ],
)
def test_unsafe_or_unbounded_expression_is_rejected(expression):
    with pytest.raises(ValidationError):
        MathCheckRequest(id="safe", operation="simplify", expression=expression)


@pytest.mark.parametrize(
    "variables",
    [
        ["x);raise"],
        ["__class__"],
        ["x.y"],
        ["sin"],
        ["pi"],
        ["x", "x"],
        ["x", "y", "z", "a", "b", "c"],
        [],
    ],
)
def test_variables_are_explicit_short_identifiers(variables):
    with pytest.raises(ValidationError):
        MathCheckRequest(id="safe", operation="simplify", expression="x", variables=variables)


def test_expression_nodes_depth_and_size_are_bounded():
    for expression in ["+".join(["x"] * 40), "sin(" * 14 + "x" + ")" * 14, "x" * 257]:
        with pytest.raises(ValidationError):
            MathCheckRequest(id="limit", operation="simplify", expression=expression)


def test_identity_needs_expected_and_variable_assumptions_must_be_declared():
    with pytest.raises(ValidationError):
        MathCheckRequest(id="check", operation="check_identity", expression="x")
    with pytest.raises(ValidationError):
        MathCheckRequest(id="check", operation="differentiate", expression="x", variable="y")
    with pytest.raises(ValidationError):
        MathCheckRequest(
            id="check", operation="simplify", expression="x", assumptions={"y": "real"}
        )
    with pytest.raises(ValidationError):
        MathCheckRequest(id="check", operation="dimensional_analysis", expression="x")


def test_no_symbolic_output_can_claim_physics_proof():
    with pytest.raises(ValidationError):
        MathCheckResult(
            id="x",
            operation="simplify",
            status="verified",
            result="1",
            method="fake",
            details="test",
            physics_proof=True,
        )


def test_missing_optional_dependency_returns_explicit_unavailable(monkeypatch):
    monkeypatch.setattr("app.modules.tutor.mathematics.importlib.util.find_spec", lambda name: None)
    result = SympyMathTool().check(
        MathCheckRequest(id="optional", operation="simplify", expression="x")
    )
    assert result.status == "unavailable"
    assert result.result is None
    assert result.physics_proof is False


@requires_sympy
@pytest.mark.parametrize(
    "operation,expression,expected,result",
    [
        ("simplify", "x+x", None, "2*x"),
        ("differentiate", "x**3", "3*x**2", "3*x**2"),
        ("integrate", "2*x", "x**2", "x**2"),
        ("check_identity", "sin(x)**2+cos(x)**2", "1", "sin(x)**2 + cos(x)**2"),
        (
            "simplify",
            "0.1234567890123456789",
            None,
            "1234567890123456789/10000000000000000000",
        ),
    ],
)
def test_known_symbolic_calculations_run_in_isolated_process(
    operation, expression, expected, result
):
    checked = SympyMathTool().check(
        MathCheckRequest(
            id="known",
            operation=operation,
            expression=expression,
            expected=expected,
        )
    )
    assert checked.status == ("verified" if expected else "tool_computed")
    assert checked.result == result
    assert "x is real" in checked.conditions
    assert checked.physics_proof is False
    assert checked.method.startswith("sympy-") and checked.method.endswith("-isolated")
    if operation == "integrate":
        assert any("arbitrary constant" in condition for condition in checked.conditions)


@requires_sympy
def test_incorrect_derivative_is_failed_instead_of_verified():
    result = SympyMathTool().check(
        MathCheckRequest(
            id="negative",
            operation="differentiate",
            expression="x**2",
            expected="3*x",
        )
    )
    assert result.status in {"failed", "inconclusive"}
    assert result.status != "verified"


@requires_sympy
def test_singularities_are_retained_as_explicit_conditions():
    result = SympyMathTool().check(
        MathCheckRequest(
            id="domain",
            operation="check_identity",
            expression="x/x",
            expected="1",
        )
    )
    assert result.status == "verified"
    assert "x != 0" in result.conditions


@requires_sympy
def test_new_domain_restrictions_of_derivative_and_integral_are_disclosed():
    derivative = SympyMathTool().check(
        MathCheckRequest(
            id="sqrt-derivative",
            operation="differentiate",
            expression="sqrt(x)",
        )
    )
    assert derivative.status == "tool_computed"
    assert "x > 0" in derivative.conditions
    integral = SympyMathTool().check(
        MathCheckRequest(
            id="log-integral",
            operation="integrate",
            expression="1/x",
        )
    )
    assert integral.status == "tool_computed"
    assert "x > 0" in integral.conditions


@requires_sympy
def test_real_square_root_is_not_silently_treated_as_positive_variable():
    unknown = SympyMathTool().check(
        MathCheckRequest(
            id="root",
            operation="check_identity",
            expression="sqrt(x**2)",
            expected="x",
        )
    )
    assert unknown.status in {"failed", "inconclusive"}
    positive = SympyMathTool().check(
        MathCheckRequest(
            id="root-positive",
            operation="check_identity",
            expression="sqrt(x**2)",
            expected="x",
            assumptions={"x": "positive"},
        )
    )
    assert positive.status == "verified"
    assert "x is real and positive" in positive.conditions


@requires_sympy
def test_invalid_real_domain_is_sanitized_failed_result():
    result = SympyMathTool().check(
        MathCheckRequest(
            id="real-domain",
            operation="simplify",
            expression="log(-1)",
        )
    )
    assert result.status == "failed"
    assert "Traceback" not in result.details
    assert result.result is None


@requires_sympy
def test_unevaluated_integral_does_not_claim_verified_result():
    result = SympyMathTool().check(
        MathCheckRequest(
            id="unevaluated",
            operation="integrate",
            expression="exp(-x**2)*log(x)",
        )
    )
    assert result.status == "inconclusive"
    assert result.physics_proof is False


@requires_sympy
def test_hard_deadline_terminates_the_worker_without_executing_custom_code():
    result = SympyMathTool(timeout_seconds=0.00001).check(
        MathCheckRequest(
            id="deadline",
            operation="simplify",
            expression="x+x",
        )
    )
    assert result.status == "inconclusive"
    assert result.result is None
    assert "budget" in result.details


@pytest.mark.parametrize(
    "point",
    [
        "__import__('os')",
        "x",
        "y",
        "x.__class__",
        "[0]",
        "(lambda:0)()",
        "Symbol('x')",
        "1e309",
        "oo+1",
        "0" * 33,
    ],
)
def test_limit_point_uses_the_same_bounded_closed_expression_language(point):
    with pytest.raises(ValidationError):
        MathCheckRequest(id="unsafe-point", operation="limit", expression="x", point=point)


def test_limit_requires_point_and_a_single_declared_limit_variable():
    with pytest.raises(ValidationError):
        MathCheckRequest(id="no-point", operation="limit", expression="x")
    with pytest.raises(ValidationError):
        MathCheckRequest(
            id="bad-variable", operation="limit", expression="x", point="0", variable="y"
        )
    with pytest.raises(ValidationError):
        MathCheckRequest(
            id="multi-variable",
            operation="limit",
            expression="x+y",
            point="0",
            variables=["x", "y"],
        )
    with pytest.raises(ValidationError):
        MathCheckRequest(
            id="variable-expected", operation="limit", expression="x", point="0", expected="x"
        )
    with pytest.raises(ValidationError):
        MathCheckRequest(
            id="bad-direction", operation="limit", expression="x", point="0", direction="sideways"
        )
    with pytest.raises(ValidationError):
        MathCheckRequest(id="wrong-operation", operation="simplify", expression="x", point="0")


@requires_sympy
@pytest.mark.parametrize(
    "expression,point,expected,result",
    [
        ("sin(x)/x", "0", "1", "1"),
        ("(1-cos(x))/x**2", "0", "1/2", "1/2"),
        ("x/(x+1)", "oo", "1", "1"),
        ("x/(x+1)", "-oo", "1", "1"),
        ("sin(x)/x", "0", None, "1"),
        ("x", "pi/2", "pi/2", "pi/2"),
    ],
)
def test_known_limits_are_symbolic_and_do_not_claim_target_definiteness(
    expression, point, expected, result
):
    checked = SympyMathTool().check(
        MathCheckRequest(
            id="known-limit",
            operation="limit",
            expression=expression,
            point=point,
            expected=expected,
        )
    )
    assert checked.status == ("verified" if expected is not None else "tool_computed")
    assert checked.result == result
    assert "approaches" in checked.details
    assert "does not assert that the function is defined at the target" in checked.details
    assert checked.physics_proof is False
    assert any("punctured real domain" in condition for condition in checked.conditions)


@requires_sympy
@pytest.mark.parametrize("direction,expected", [("+", "oo"), ("-", "-oo")])
def test_one_sided_infinite_limit_is_distinguished_from_a_finite_value(direction, expected):
    checked = SympyMathTool().check(
        MathCheckRequest(
            id="one-sided",
            operation="limit",
            expression="1/x",
            point="0",
            direction=direction,
            expected=expected,
        )
    )
    assert checked.status == "verified"
    assert checked.result == expected
    assert ("from above" if direction == "+" else "from below") in checked.details
    assert checked.physics_proof is False


@requires_sympy
def test_unequal_one_sided_limits_are_inconclusive_not_an_invented_two_sided_result():
    checked = SympyMathTool().check(
        MathCheckRequest(
            id="two-sided",
            operation="limit",
            expression="1/x",
            point="0",
        )
    )
    assert checked.status == "inconclusive"
    assert checked.result is None
    assert "one-sided limits differ" in checked.details


@requires_sympy
def test_real_limit_does_not_use_an_unavailable_side_of_the_domain():
    checked = SympyMathTool().check(
        MathCheckRequest(
            id="sqrt-domain",
            operation="limit",
            expression="sqrt(x)",
            point="0",
        )
    )
    assert checked.status == "inconclusive"
    assert checked.result is None
    assert "real approach" in checked.details


@requires_sympy
def test_oscillatory_limit_does_not_claim_a_scalar_value():
    checked = SympyMathTool().check(
        MathCheckRequest(
            id="oscillation",
            operation="limit",
            expression="sin(1/x)",
            point="0",
        )
    )
    assert checked.status == "inconclusive"
    assert checked.result is None
