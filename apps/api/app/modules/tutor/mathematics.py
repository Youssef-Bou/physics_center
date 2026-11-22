"""Bounded symbolic checks, without evaluating Python supplied by users or models.

Only a tiny AST language is translated to explicit SymPy constructors. SymPy is an
optional dependency and is imported exclusively in a disposable spawned process.
A symbolic result is never a check of units, modelling assumptions, or physics.
"""

from __future__ import annotations

import ast
import importlib.util
import math
import multiprocessing
import re
from decimal import Decimal
from time import monotonic
from typing import Literal, Protocol

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

Operation = Literal["simplify", "differentiate", "integrate", "check_identity", "limit"]
MathStatus = Literal[
    "tool_computed", "verified", "failed", "inconclusive", "unavailable", "not_checked"
]
Assumption = Literal["real", "positive", "nonnegative", "nonzero"]
_FUNCTIONS = frozenset({"sin", "cos", "exp", "log", "sqrt"})
_CONSTANTS = frozenset({"pi", "E"})
_NAME = re.compile(r"[A-Za-z][A-Za-z0-9]{0,15}\Z")
_WORKER_PROTOCOL = "physics-sympy-worker.v1"


def _worker_message(request: MathCheckRequest | MathCheckResult, event: str, result=None) -> dict:
    message = {
        "protocol": _WORKER_PROTOCOL,
        "request_id": request.id,
        "operation": request.operation,
        "event": event,
    }
    if result is not None:
        message["result"] = result
    return message


def _valid_worker_message(message, request: MathCheckRequest, event: str) -> bool:
    keys = {"protocol", "request_id", "operation", "event"}
    if event in {"result", "startup_result"}:
        keys.add("result")
    return (
        isinstance(message, dict)
        and set(message) == keys
        and message.get("protocol") == _WORKER_PROTOCOL
        and message.get("request_id") == request.id
        and message.get("operation") == request.operation
        and message.get("event") == event
    )


def _integer_literal(node: ast.AST) -> int | None:
    if isinstance(node, ast.Constant) and type(node.value) is int:
        return node.value
    if isinstance(node, ast.UnaryOp) and isinstance(node.op, (ast.UAdd, ast.USub)):
        if isinstance(node.operand, ast.Constant) and type(node.operand.value) is int:
            return node.operand.value if isinstance(node.op, ast.UAdd) else -node.operand.value
    return None


def _syntax(expression: str, variables: list[str]) -> ast.Expression:
    try:
        tree = ast.parse(expression, mode="eval")
    except (SyntaxError, RecursionError, ValueError) as exc:
        raise ValueError("The mathematical expression has invalid syntax.") from exc
    if len(list(ast.walk(tree))) > 64:
        raise ValueError("The mathematical expression exceeds the 64-node limit.")

    def visit(node: ast.AST, depth: int = 0) -> None:
        if depth > 12:
            raise ValueError("The mathematical expression exceeds the depth limit.")
        if isinstance(node, ast.Expression):
            visit(node.body, depth + 1)
        elif isinstance(node, ast.Constant):
            if type(node.value) not in {int, float} or abs(node.value) > 1_000_000:
                raise ValueError("Only bounded finite numeric literals are allowed.")
            if not math.isfinite(node.value):
                raise ValueError("Non-finite numeric literals are not allowed.")
            if type(node.value) is float:
                literal_text = ast.get_source_segment(expression, node).replace("_", "")
                literal = Decimal(literal_text)
                if abs(literal) > Decimal("1000000"):
                    raise ValueError("Numeric literals must have magnitude at most one million.")
                if literal and abs(literal) < Decimal("1e-12"):
                    raise ValueError("Nonzero decimal literals must have magnitude at least 1e-12.")
                node.decimal_literal = literal_text
        elif isinstance(node, ast.Name):
            if node.id not in variables and node.id not in _CONSTANTS:
                raise ValueError("The expression contains an undeclared variable.")
        elif isinstance(node, ast.UnaryOp) and isinstance(node.op, (ast.UAdd, ast.USub)):
            visit(node.operand, depth + 1)
        elif isinstance(node, ast.BinOp) and isinstance(
            node.op, (ast.Add, ast.Sub, ast.Mult, ast.Div, ast.Pow)
        ):
            if isinstance(node.op, ast.Pow):
                power = _integer_literal(node.right)
                if power is None or abs(power) > 10:
                    raise ValueError(
                        "Powers require a literal integer exponent between -10 and 10."
                    )
                if any(isinstance(child, ast.Pow) for child in ast.walk(node.left)):
                    raise ValueError("Nested powers are not supported.")
            visit(node.left, depth + 1)
            visit(node.right, depth + 1)
        elif isinstance(node, ast.Call):
            if (
                not isinstance(node.func, ast.Name)
                or node.func.id not in _FUNCTIONS
                or len(node.args) != 1
                or node.keywords
            ):
                raise ValueError("Only one-argument sin/cos/exp/log/sqrt calls are allowed.")
            visit(node.args[0], depth + 1)
        else:
            raise ValueError("The expression contains an unsupported construct.")

    visit(tree)
    return tree


class MathCheckRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str = Field(min_length=1, max_length=64)
    operation: Operation
    expression: str = Field(min_length=1, max_length=256)
    variables: list[str] = Field(default_factory=lambda: ["x"], min_length=1, max_length=5)
    variable: str | None = Field(default=None, max_length=16)
    expected: str | None = Field(default=None, min_length=1, max_length=256)
    assumptions: dict[str, Assumption] = Field(default_factory=dict, max_length=5)
    point: str | None = Field(default=None, min_length=1, max_length=32)
    direction: Literal["+", "-", "both"] = "both"

    @field_validator("id")
    @classmethod
    def valid_identifier(cls, value: str) -> str:
        if not value.strip() or any(ord(char) < 32 for char in value):
            raise ValueError("A nonempty printable check ID is required.")
        return value

    @field_validator("variables")
    @classmethod
    def valid_variables(cls, values: list[str]) -> list[str]:
        if len(set(values)) != len(values):
            raise ValueError("Variables must be unique.")
        if any(
            not _NAME.fullmatch(value) or value in _FUNCTIONS | _CONSTANTS | {"oo"}
            for value in values
        ):
            raise ValueError(
                "Variable names must be short ASCII identifiers without reserved names."
            )
        return values

    @model_validator(mode="after")
    def valid_request(self):
        if self.variable is not None and self.variable not in self.variables:
            raise ValueError("The calculation variable must be declared.")
        if any(name not in self.variables for name in self.assumptions):
            raise ValueError("Assumptions must address declared variables.")
        if self.operation == "check_identity" and self.expected is None:
            raise ValueError("Identity checks require an expected expression.")
        expression_tree = _syntax(self.expression, self.variables)
        if self.expected is not None:
            if self.operation == "limit":
                if self.expected not in {"oo", "-oo"}:
                    _syntax(self.expected, [])
            else:
                _syntax(self.expected, self.variables)
        if self.operation == "limit":
            if self.point is None:
                raise ValueError("Limit checks require an approach point.")
            if self.point not in {"oo", "-oo"}:
                _syntax(self.point, [])
            variable = self.variable or self.variables[0]
            names = {node.id for node in ast.walk(expression_tree) if isinstance(node, ast.Name)}
            if (names & set(self.variables)) - {variable}:
                raise ValueError("Only single-variable limits are supported.")
        elif self.point is not None or self.direction != "both":
            raise ValueError("Approach point and direction are supported only for limit checks.")
        return self


class MathCheckResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    operation: Operation
    status: MathStatus
    result: str | None = None
    details: str
    method: str
    conditions: list[str] = Field(default_factory=list)
    physics_proof: Literal[False] = False


class MathTool(Protocol):
    def check(self, request: MathCheckRequest) -> MathCheckResult: ...


class SympyMathTool:
    """Bound cold startup separately; computation still has a maximum of two seconds."""

    def __init__(self, *, timeout_seconds: float = 2.0, startup_timeout_seconds: float = 5.0):
        if not math.isfinite(timeout_seconds) or not 0 < timeout_seconds <= 2:
            raise ValueError("The calculation timeout must be positive and at most two seconds.")
        if not math.isfinite(startup_timeout_seconds) or not 0 < startup_timeout_seconds <= 5:
            raise ValueError(
                "The worker startup timeout must be positive and at most five seconds."
            )
        self.timeout_seconds = timeout_seconds
        self.startup_timeout_seconds = startup_timeout_seconds

    @staticmethod
    def _inconclusive(request, details):
        return MathCheckResult(
            id=request.id,
            operation=request.operation,
            status="inconclusive",
            details=details,
            method="sympy_isolated",
        )

    @staticmethod
    def _result(message, request, event):
        if not _valid_worker_message(message, request, event):
            return None
        try:
            result = MathCheckResult.model_validate(message["result"])
        except (ValueError, TypeError):
            return None
        if result.id != request.id or result.operation != request.operation:
            return None
        if event == "startup_result" and result.status not in {"failed", "unavailable"}:
            return None
        return result

    def check(self, request: MathCheckRequest) -> MathCheckResult:
        # Validate again if an internal adapter used model_construct/model_copy.
        request = MathCheckRequest.model_validate(request.model_dump())
        if importlib.util.find_spec("sympy") is None:
            return MathCheckResult(
                id=request.id,
                operation=request.operation,
                status="unavailable",
                details="Optional SymPy support is not installed; no mathematical check was run.",
                method="sympy_unavailable",
            )
        context = multiprocessing.get_context("spawn")
        parent, child = context.Pipe(duplex=True)
        # The CPU backstop covers both bounded phases; the compute wall deadline
        # remains independent of how much startup/import CPU was consumed.
        cpu_seconds = math.ceil(self.startup_timeout_seconds + self.timeout_seconds) + 1
        process = context.Process(
            target=_worker,
            args=(request.model_dump(), child, cpu_seconds),
            daemon=True,
        )
        phase = "startup"
        try:
            startup_deadline = monotonic() + self.startup_timeout_seconds
            process.start()
            child.close()
            remaining = startup_deadline - monotonic()
            if remaining <= 0 or not parent.poll(remaining) or monotonic() > startup_deadline:
                return self._inconclusive(
                    request, "The isolated worker did not become ready within its startup budget."
                )
            message = parent.recv()
            if _valid_worker_message(message, request, "startup_result"):
                result = self._result(message, request, "startup_result")
                if result is not None:
                    return result
            if not _valid_worker_message(message, request, "ready"):
                return self._inconclusive(
                    request, "The isolated worker startup protocol was invalid."
                )
            # A loaded worker cannot calculate before this acknowledgement. Cold
            # Python/SymPy import time therefore never consumes the compute budget.
            phase = "compute"
            compute_deadline = monotonic() + self.timeout_seconds
            parent.send(_worker_message(request, "compute"))
            remaining = compute_deadline - monotonic()
            if remaining <= 0 or not parent.poll(remaining) or monotonic() > compute_deadline:
                return self._inconclusive(
                    request, "The isolated calculation did not complete within its compute budget."
                )
            result = self._result(parent.recv(), request, "result")
            return result or self._inconclusive(
                request, "The isolated calculation returned an invalid result protocol."
            )
        except (EOFError, OSError):
            return self._inconclusive(
                request, f"The isolated worker exited during its bounded {phase} protocol."
            )
        finally:
            parent.close()
            child.close()
            if process.pid is not None:
                if process.is_alive():
                    process.terminate()
                process.join(timeout=0.5)
                if process.is_alive():
                    process.kill()
                    process.join(timeout=0.5)
                if not process.is_alive():
                    process.close()


def _worker(payload: dict, connection, cpu_seconds: int) -> None:
    """No dynamic Python evaluation; only this fixed interpreter runs in the child."""
    try:
        import resource

        resource.setrlimit(resource.RLIMIT_CPU, (cpu_seconds, cpu_seconds))
        resource.setrlimit(resource.RLIMIT_AS, (384 * 1024 * 1024, 384 * 1024 * 1024))
    except (ImportError, ValueError, OSError):
        pass  # The parent wall-clock deadline remains active on other platforms.
    event = "startup_result"
    try:
        request = MathCheckRequest.model_validate(payload)
        try:
            import sympy as sp
        except ImportError:
            response = MathCheckResult(
                id=request.id,
                operation=request.operation,
                status="unavailable",
                details="Optional SymPy support is not available in the worker.",
                method="sympy_unavailable",
            )
        else:
            connection.send(_worker_message(request, "ready"))
            # The parent tears this child down if it cannot acknowledge readiness;
            # no calculation runs until the complete compute command is checked.
            command = connection.recv()
            if not _valid_worker_message(command, request, "compute"):
                connection.close()
                return
            event = "result"
            response = _compute(request, sp)
    except Exception:
        # Never send internal tracebacks, arbitrary exception text, or source code.
        response = MathCheckResult(
            id=payload["id"],
            operation=payload["operation"],
            status="failed",
            details="The expression could not be checked within the supported symbolic domain.",
            method="sympy_isolated",
        )
    try:
        connection.send(_worker_message(response, event, response.model_dump()))
    except (EOFError, OSError):
        pass  # Parent deadlines can close the pipe while the child is exiting.
    finally:
        connection.close()


def _compute(request: MathCheckRequest, sp) -> MathCheckResult:
    symbols = {}
    conditions = []
    domain_requirements = []
    for name in request.variables:
        assumption = request.assumptions.get(name, "real")
        symbols[name] = sp.Symbol(
            name, real=True, **({assumption: True} if assumption != "real" else {})
        )
        conditions.append(
            f"{name} is real" + (f" and {assumption}" if assumption != "real" else "")
        )
        if assumption != "real":
            domain_requirements.append(
                (
                    symbols[name],
                    {"positive": "> 0", "nonnegative": ">= 0", "nonzero": "!= 0"}[assumption],
                )
            )
    variable = symbols[request.variable or request.variables[0]]

    def require(expr, relation: str) -> None:
        nonzero = None if expr.is_zero is None else not expr.is_zero
        predicate = {"!= 0": nonzero, "> 0": expr.is_positive, ">= 0": expr.is_nonnegative}[
            relation
        ]
        if predicate is False:
            raise ValueError("Expression is outside the supported real domain.")
        if predicate is not True:
            conditions.append(f"{sp.sstr(expr)} {relation}")
            domain_requirements.append((expr, relation))

    def translate(node):
        if isinstance(node, ast.Expression):
            return translate(node.body)
        if isinstance(node, ast.Constant):
            return (
                sp.Integer(node.value)
                if type(node.value) is int
                else sp.Rational(node.decimal_literal)
            )
        if isinstance(node, ast.Name):
            return symbols[node.id] if node.id in symbols else {"pi": sp.pi, "E": sp.E}[node.id]
        if isinstance(node, ast.UnaryOp):
            return translate(node.operand) * (-1 if isinstance(node.op, ast.USub) else 1)
        if isinstance(node, ast.BinOp):
            left, right = translate(node.left), translate(node.right)
            if isinstance(node.op, ast.Add):
                return sp.Add(left, right, evaluate=False)
            if isinstance(node.op, ast.Sub):
                return sp.Add(left, -right, evaluate=False)
            if isinstance(node.op, ast.Mult):
                return sp.Mul(left, right, evaluate=False)
            if isinstance(node.op, ast.Div):
                require(right, "!= 0")
                return sp.Mul(left, sp.Pow(right, -1, evaluate=False), evaluate=False)
            if isinstance(node.op, ast.Pow):
                if _integer_literal(node.right) <= 0:
                    require(left, "!= 0")
                return sp.Pow(left, right, evaluate=False)
        if isinstance(node, ast.Call):
            argument = translate(node.args[0])
            name = node.func.id
            if name == "log":
                require(argument, "> 0")
            elif name == "sqrt":
                # Boundary differentiability is not implied by the real sqrt
                # domain. A conservative open-domain restriction avoids claiming
                # a finite derivative at a zero of a variable radicand.
                require(
                    argument,
                    "> 0"
                    if request.operation == "differentiate" and argument.has(variable)
                    else ">= 0",
                )
            return {"sin": sp.sin, "cos": sp.cos, "exp": sp.exp, "log": sp.log, "sqrt": sp.sqrt}[
                name
            ](argument)
        raise ValueError("Unsupported mathematical AST node.")

    expression = translate(_syntax(request.expression, request.variables))
    if request.operation == "limit" and request.expected in {"oo", "-oo"}:
        expected = sp.oo if request.expected == "oo" else -sp.oo
    else:
        expected = (
            translate(_syntax(request.expected, request.variables)) if request.expected else None
        )
    limit_issue = None
    limit_description = None
    if request.operation == "differentiate":
        computed = sp.diff(expression, variable)
    elif request.operation == "integrate":
        computed = sp.integrate(expression, variable)
    elif request.operation == "check_identity":
        computed = expression
    elif request.operation == "limit":
        point = (
            {"oo": sp.oo, "-oo": -sp.oo}[request.point]
            if request.point in {"oo", "-oo"}
            else translate(_syntax(request.point, []))
        )
        if point not in {sp.oo, -sp.oo} and (
            point.is_real is not True or point.is_finite is not True
        ):
            raise ValueError(
                "The approach point must be a finite real constant or an explicit infinity."
            )
        if point in {sp.oo, -sp.oo}:
            limit_description = (
                f"Limit as {variable} approaches {sp.sstr(point)} along the real axis."
            )
        else:
            side = {"+": "from above", "-": "from below", "both": "from both sides"}[
                request.direction
            ]
            limit_description = f"Limit as {variable} approaches {sp.sstr(point)} {side}."
        conditions.append(limit_description)
        computed, limit_issue = _limit(
            expression, variable, point, request.direction, domain_requirements, sp
        )
    else:
        computed = sp.simplify(expression)
    # Computation can introduce restrictions absent from the input, e.g. the
    # antiderivative log(x) or the derivative 1/(2*sqrt(x)). Record them before
    # asserting equality rather than silently extending the real domain.
    for node in sp.preorder_traversal(computed) if computed is not None else ():
        if node.func == sp.log:
            require(node.args[0], "> 0")
        elif isinstance(node, sp.Pow):
            if node.exp.is_negative:
                require(node.base, "!= 0")
            if node.exp.is_Rational and node.exp.q % 2 == 0:
                require(node.base, ">= 0")
    if limit_issue is not None:
        status = "inconclusive"
        details = limit_issue
    elif computed.has(sp.Integral, sp.Limit):
        status = "inconclusive"
        details = "The calculation remains unevaluated; no symbolic verification is claimed."
    elif computed.has(sp.zoo, sp.nan) or (
        request.operation != "limit" and computed.has(sp.oo, -sp.oo)
    ):
        status = "failed"
        details = "The expression is undefined or non-finite in the supported domain."
    elif expected is not None:
        difference = sp.S.Zero if computed == expected else sp.simplify(computed - expected)
        if difference == 0:
            status = "verified"
            details = (
                "Symbolic equality under the stated conditions; no physical claim is verified."
            )
        elif difference.is_zero is False:
            status = "failed"
            details = (
                "The computed expression is not symbolically equal to the expected expression."
            )
        else:
            status = "inconclusive"
            details = "The symbolic tool could not establish equality or inequality."
    else:
        status = "tool_computed"
        details = "Symbolic tool result under stated conditions; no expected result was verified."
    if request.operation == "integrate":
        conditions.append("Indefinite integral: an arbitrary constant must be added.")
    if request.operation == "differentiate":
        conditions.append("Derivative is local to open domains where the input is differentiable.")
    if request.operation == "limit":
        details = f"{limit_description} {details} A limit does not assert that the function is defined at the target or prove a physical model."
        conditions.append(
            "The function need not be defined at the approach point; its punctured real domain is used."
        )
    result = sp.sstr(computed) if computed is not None else None
    if result is not None and len(result) > 4096:
        result = None
        status = "inconclusive"
        details = "The result exceeds the bounded output size; no verification is claimed."
    return MathCheckResult(
        id=request.id,
        operation=request.operation,
        status=status,
        result=result,
        details=details,
        method=f"sympy-{sp.__version__}-isolated",
        conditions=list(dict.fromkeys(conditions)),
        physics_proof=False,
    )


def _limit(expression, variable, point, direction, domain_requirements, sp):
    """Compare admissible one-sided approaches; never invent a two-sided limit."""
    t = sp.Dummy("approach_distance", positive=True)
    directions = ("+", "-") if direction == "both" else (direction,)
    if point in {sp.oo, -sp.oo}:
        # Infinities already determine the real approach direction. SymPy likewise
        # ignores dir there; describe the real-axis approach explicitly to callers.
        directions = ("-" if point == sp.oo else "+",)
    sides = []
    for side in directions:
        approach = (
            (1 / t if point == sp.oo else -1 / t)
            if point in {sp.oo, -sp.oo}
            else point + (t if side == "+" else -t)
        )
        for expr, relation in domain_requirements:
            try:
                leading = sp.simplify(expr.subs(variable, approach)).as_leading_term(t)
                nonzero = None if leading.is_zero is None else not leading.is_zero
                predicate = {
                    "!= 0": nonzero,
                    "> 0": leading.is_positive,
                    ">= 0": leading.is_nonnegative,
                }[relation]
            except (ValueError, NotImplementedError, sp.PoleError):
                predicate = None
            if predicate is not True:
                return (
                    None,
                    "An admissible real approach on every requested side could not be established under the domain conditions.",
                )
        try:
            value = sp.limit(expression, variable, point, dir=side)
        except (ValueError, NotImplementedError):
            return None, "The symbolic tool could not determine the requested one-sided limit."
        if (
            value.has(sp.Limit, sp.zoo, sp.nan)
            or value.free_symbols
            or value.is_extended_real is not True
            or value.is_number is not True
        ):
            return (
                None,
                "The approach has no established single extended-real limit (it may oscillate or remain unevaluated).",
            )
        sides.append(value)
    if len(sides) == 2 and sides[0] != sides[1]:
        difference = sp.simplify(sides[0] - sides[1])
        if difference != 0:
            return (
                None,
                "The one-sided limits differ or their equality is unproved; no two-sided limit is verified.",
            )
    return sides[0], None
