"""Controlled symbolic examples and hostile-input checks; no provider calls."""

import importlib.util
from types import SimpleNamespace

import pytest
from pydantic import ValidationError

from app.modules.tutor import mathematics
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


def worker_frame(event, result=None):
    """Independent protocol fixture; successful outcomes still need request binding."""
    frame = {
        "protocol": "physics-sympy-worker.v1",
        "request_id": "protocol-fixture",
        "operation": "simplify",
        "event": event,
    }
    if result is not None:
        frame["result"] = result
    return frame


def successful_worker_result(**changes):
    result = {
        "id": "protocol-fixture",
        "operation": "simplify",
        "status": "tool_computed",
        "result": "2*x",
        "details": "A controlled worker-protocol fixture.",
        "method": "sympy-fixture-isolated",
        "physics_proof": False,
    }
    result.update(changes)
    return result


def fake_worker(monkeypatch, frames, *, launch_delay=0.0, stubborn=False, ignore_kill=False):
    """No sleeps/processes: advance a virtual monotonic clock only by requested waits."""
    state = SimpleNamespace(now=0.0)

    class Endpoint:
        closed = False

        def close(self):
            self.closed = True

    class Pipe(Endpoint):
        def __init__(self):
            self.frames = list(frames)
            self.poll_timeouts = []
            self.sent = []
            self.pending = None

        def poll(self, timeout):
            assert timeout >= 0
            self.poll_timeouts.append(timeout)
            if not self.frames or self.frames[0][0] > timeout:
                state.now += timeout
                return False
            delay, self.pending = self.frames.pop(0)
            state.now += delay
            return True

        def recv(self):
            if isinstance(self.pending, BaseException):
                raise self.pending
            return self.pending

        def send(self, value):
            self.sent.append(value)

    class Process:
        pid = None
        alive = False
        closed = False
        terminated = False
        killed = False

        def __init__(self):
            self.join_timeouts = []

        def start(self):
            self.pid = 123
            self.alive = True
            state.now += launch_delay

        def is_alive(self):
            return self.alive

        def terminate(self):
            self.terminated = True
            if not stubborn:
                self.alive = False

        def join(self, timeout):
            self.join_timeouts.append(timeout)
            if self.alive:
                state.now += timeout

        def kill(self):
            self.killed = True
            if not ignore_kill:
                self.alive = False

        def close(self):
            assert not self.alive
            self.closed = True

    parent, child, process = Pipe(), Endpoint(), Process()

    class Context:
        def Pipe(self, duplex):
            assert duplex is True
            return parent, child

        def Process(self, *, target, args, daemon):
            assert target is mathematics._worker and daemon is True
            assert 1 <= args[2] <= 8
            return process

    monkeypatch.setattr(mathematics.importlib.util, "find_spec", lambda name: object())
    monkeypatch.setattr(mathematics.multiprocessing, "get_context", lambda name: Context())
    monkeypatch.setattr(mathematics, "monotonic", lambda: state.now)
    state.parent, state.child, state.process = parent, child, process
    return state


def protocol_check(tool=None):
    return (tool or SympyMathTool()).check(
        MathCheckRequest(id="protocol-fixture", operation="simplify", expression="x+x")
    )


def test_cold_start_has_a_separate_budget_before_the_compute_command(monkeypatch):
    state = fake_worker(
        monkeypatch,
        [(4.8, worker_frame("ready")), (1.9, worker_frame("result", successful_worker_result()))],
    )
    result = protocol_check()
    assert result.status == "tool_computed"
    assert result.result == "2*x"
    assert state.now == pytest.approx(6.7)
    assert state.parent.poll_timeouts == pytest.approx([5.0, 2.0])
    assert state.parent.sent == [worker_frame("compute")]
    assert state.parent.closed and state.child.closed and state.process.closed


def test_worker_launch_time_is_part_of_the_startup_deadline(monkeypatch):
    state = fake_worker(monkeypatch, [(0.1, worker_frame("ready"))], launch_delay=5.1)
    result = protocol_check()
    assert result.status == "inconclusive"
    assert "startup budget" in result.details
    assert state.parent.poll_timeouts == []
    assert state.parent.sent == []


def test_startup_timeout_does_not_issue_a_compute_command(monkeypatch):
    state = fake_worker(monkeypatch, [])
    result = protocol_check()
    assert result.status == "inconclusive"
    assert result.result is None
    assert "startup budget" in result.details
    assert state.now == pytest.approx(5.0)
    assert state.parent.sent == []
    assert state.process.terminated and state.process.closed


def test_compute_timeout_keeps_its_two_second_limit_after_a_slow_start(monkeypatch):
    state = fake_worker(monkeypatch, [(4.9, worker_frame("ready"))])
    result = protocol_check()
    assert result.status == "inconclusive"
    assert "compute budget" in result.details
    assert state.parent.poll_timeouts == pytest.approx([5.0, 2.0])
    assert state.parent.sent == [worker_frame("compute")]
    assert state.now == pytest.approx(6.9)


@pytest.mark.parametrize("phase", ["startup", "compute"])
def test_worker_eof_is_inconclusive_and_never_a_scientific_result(monkeypatch, phase):
    frames = [(0.1, EOFError())]
    if phase == "compute":
        frames.insert(0, (0.1, worker_frame("ready")))
    state = fake_worker(monkeypatch, frames)
    result = protocol_check()
    assert result.status == "inconclusive"
    assert result.result is None
    assert result.physics_proof is False
    assert phase in result.details
    assert state.parent.closed and state.child.closed and state.process.closed


@pytest.mark.parametrize(
    "change",
    [
        {"protocol": "unknown-worker.v0"},
        {"request_id": "another-request"},
        {"operation": "integrate"},
        {"event": "compute"},
        {"unexpected": "field"},
    ],
)
def test_startup_requires_an_exact_versioned_ready_message(monkeypatch, change):
    state = fake_worker(monkeypatch, [(0.1, {**worker_frame("ready"), **change})])
    result = protocol_check()
    assert result.status == "inconclusive"
    assert "protocol" in result.details
    assert state.parent.sent == []


@pytest.mark.parametrize(
    "change",
    [
        {"id": "another-request"},
        {"operation": "integrate"},
        {"status": "looks_correct"},
        {"physics_proof": True},
    ],
)
def test_result_requires_matching_request_and_validated_result_contract(monkeypatch, change):
    fake_worker(
        monkeypatch,
        [
            (0.1, worker_frame("ready")),
            (0.1, worker_frame("result", successful_worker_result(**change))),
        ],
    )
    result = protocol_check()
    assert result.status == "inconclusive"
    assert result.result is None
    assert "invalid result protocol" in result.details


@pytest.mark.parametrize("status", ["failed", "unavailable"])
def test_startup_can_report_only_explicit_non_success_results(monkeypatch, status):
    state = fake_worker(
        monkeypatch,
        [
            (
                0.1,
                worker_frame(
                    "startup_result", successful_worker_result(status=status, result=None)
                ),
            )
        ],
    )
    result = protocol_check()
    assert result.status == status
    assert state.parent.sent == []


def test_a_result_cannot_claim_success_before_readiness(monkeypatch):
    state = fake_worker(
        monkeypatch, [(0.1, worker_frame("startup_result", successful_worker_result()))]
    )
    assert protocol_check().status == "inconclusive"
    assert state.parent.sent == []


def test_teardown_has_no_unbounded_join_even_when_termination_is_unresponsive(monkeypatch):
    state = fake_worker(monkeypatch, [], stubborn=True, ignore_kill=True)
    result = protocol_check()
    assert result.status == "inconclusive"
    assert state.process.terminated and state.process.killed
    assert state.process.join_timeouts == [0.5, 0.5]
    assert state.now == pytest.approx(6.0)
    assert state.process.closed is False
    assert state.parent.closed and state.child.closed


@pytest.mark.parametrize(
    "setting,value",
    [
        ("startup_timeout_seconds", 0),
        ("startup_timeout_seconds", 5.1),
        ("startup_timeout_seconds", float("inf")),
        ("timeout_seconds", 0),
        ("timeout_seconds", 2.1),
        ("timeout_seconds", float("nan")),
    ],
)
def test_startup_and_compute_budgets_remain_finite_and_bounded(setting, value):
    with pytest.raises(ValueError):
        SympyMathTool(**{setting: value})
