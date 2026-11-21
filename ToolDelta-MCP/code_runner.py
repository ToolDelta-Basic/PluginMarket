"""Run a bounded subset of Python against the bridge's authorized game tools."""

import ast
import math
from time import monotonic


TOOL_NAMES = frozenset(
    {
        "game_command", "bot_chat", "players_list", "status", "logs_read", "events_read",
        "events_wait", "docs_search", "docs_get", "console_list",
    }
)
BUILTINS = frozenset({"print", "len", "range", "str", "int", "bool"})
MAX_SOURCE = 12_000
MAX_STEPS = 4_000
MAX_LOOPS = 512
MAX_CALLS = 12
MAX_ITEMS = 512
MAX_STRING = 16_384
MAX_OUTPUT = 16_384
MAX_VALUE_SIZE = 65_536
MAX_SECONDS = 45

ALLOWED_NODES = (
    ast.Module, ast.Expr, ast.Assign, ast.AugAssign, ast.If, ast.For, ast.Pass,
    ast.Name, ast.Load, ast.Store, ast.Constant, ast.List, ast.Dict, ast.Subscript,
    ast.BinOp, ast.Add, ast.Sub, ast.Mult, ast.Div, ast.FloorDiv, ast.Mod,
    ast.UnaryOp, ast.UAdd, ast.USub, ast.Not, ast.BoolOp, ast.And, ast.Or,
    ast.Compare, ast.Eq, ast.NotEq, ast.Lt, ast.LtE, ast.Gt, ast.GtE,
    ast.In, ast.NotIn, ast.Call, ast.keyword, ast.IfExp,
)


def _check_value(value):
    """Check size, depth and exact JSON types before computing with a value."""
    remaining = MAX_VALUE_SIZE
    nodes = 0

    def visit(item, depth):
        nonlocal remaining, nodes
        nodes += 1
        if depth > 24 or nodes > 4096:
            raise ValueError("value exceeds the nesting or element limit")
        kind = type(item)
        remaining -= 1
        if kind is str:
            if len(item) > MAX_STRING:
                raise ValueError("string exceeds the length limit")
            remaining -= len(item.encode("utf-8"))
        elif kind is int:
            if item.bit_length() > 128:
                raise ValueError("integer exceeds 128 bits")
            remaining -= 40
        elif kind is float:
            if not math.isfinite(item):
                raise ValueError("non-finite number")
            remaining -= 24
        elif kind in (list, dict):
            if len(item) > MAX_ITEMS:
                raise ValueError("collection exceeds the item limit")
            if kind is list:
                for child in item:
                    visit(child, depth + 1)
            else:
                for key, child in item.items():
                    if type(key) is not str:
                        raise ValueError("dictionary keys must be strings")
                    visit(key, depth + 1)
                    visit(child, depth + 1)
        elif item is not None and kind is not bool:
            raise ValueError("only JSON values are supported")
        if remaining < 0:
            raise ValueError("value exceeds the size limit")

    visit(value, 0)
    return value


def _validate(tree, runner):
    allowed_calls = TOOL_NAMES.intersection(runner.api) | BUILTINS
    for count, node in enumerate(ast.walk(tree), 1):
        runner.line = getattr(node, "lineno", runner.line)
        if count > 1200:
            raise ValueError("code exceeds the syntax node limit")
        if not isinstance(node, ALLOWED_NODES):
            raise ValueError(f"unsupported syntax: {type(node).__name__}")
        if isinstance(node, ast.Constant):
            _check_value(node.value)
        if isinstance(node, ast.Name):
            if node.id.startswith("_") or len(node.id) > 80:
                raise ValueError("private or oversized variable name")
            if isinstance(node.ctx, ast.Store) and node.id in TOOL_NAMES | BUILTINS:
                raise ValueError(f"reserved name: {node.id}")
        if isinstance(node, ast.Call):
            if not isinstance(node.func, ast.Name) or node.func.id not in allowed_calls:
                raise ValueError("only available tools and builtins can be called")
            if any(k.arg is None for k in node.keywords):
                raise ValueError("expanded keyword arguments are unsupported")
            keys = [k.arg for k in node.keywords]
            if len(set(keys)) != len(keys):
                raise ValueError("duplicate keyword argument")
        if isinstance(node, ast.Dict) and None in node.keys:
            raise ValueError("expanded dictionaries are unsupported")
        if isinstance(node, ast.Assign):
            if len(node.targets) != 1 or not isinstance(node.targets[0], ast.Name):
                raise ValueError("assign to one variable at a time")
        if isinstance(node, (ast.AugAssign, ast.For)):
            if not isinstance(node.target, ast.Name):
                raise ValueError("target must be a variable")
        if isinstance(node, ast.For) and node.orelse:
            raise ValueError("for/else is unsupported")


def _binary(op, left, right):
    kind = type(left)
    if isinstance(op, ast.Add) and kind in (str, list) and kind is type(right):
        limit = MAX_STRING if kind is str else MAX_ITEMS
        if len(left) + len(right) > limit:
            raise ValueError("concatenation exceeds the size limit")
        return left + right
    if isinstance(op, ast.Mult):
        if kind is int and type(right) in (str, list):
            left, right = right, left
        if type(left) in (str, list) and type(right) is int:
            if not left or right <= 0:
                return left[:0]
            limit = MAX_STRING if type(left) is str else MAX_ITEMS
            if len(left) * right > limit:
                raise ValueError("repetition exceeds the size limit")
            return left * right
    if type(left) not in (int, float) or type(right) not in (int, float):
        raise ValueError("this operator requires numbers")
    if isinstance(op, ast.Add):
        return left + right
    if isinstance(op, ast.Sub):
        return left - right
    if isinstance(op, ast.Mult):
        return left * right
    if isinstance(op, ast.Div):
        return left / right
    if isinstance(op, ast.FloorDiv):
        return left // right
    if isinstance(op, ast.Mod):
        return left % right
    raise ValueError("unsupported arithmetic operator")


def _compare(op, left, right):
    if isinstance(op, ast.Eq):
        return left == right
    if isinstance(op, ast.NotEq):
        return left != right
    if isinstance(op, ast.Lt):
        return left < right
    if isinstance(op, ast.LtE):
        return left <= right
    if isinstance(op, ast.Gt):
        return left > right
    if isinstance(op, ast.GtE):
        return left >= right
    if isinstance(op, ast.In):
        return left in right
    return left not in right


class _Runner:
    def __init__(self, api):
        self.api = api
        self.variables = {}
        self.output = ""
        self.steps = 0
        self.loops = 0
        self.calls = 0
        self.line = 1
        self.deadline = monotonic() + MAX_SECONDS

    def step(self, node):
        self.line = node.lineno
        self.steps += 1
        if self.steps > MAX_STEPS or monotonic() > self.deadline:
            raise ValueError("execution budget exhausted")

    def run_block(self, statements):
        for stmt in statements:
            self.step(stmt)
            if isinstance(stmt, ast.Expr):
                self.evaluate(stmt.value)
            elif isinstance(stmt, ast.Assign):
                self.variables[stmt.targets[0].id] = self.evaluate(stmt.value)
            elif isinstance(stmt, ast.AugAssign):
                name = stmt.target.id
                previous = self.variables[name]
                operand = self.evaluate(stmt.value)
                value = _binary(stmt.op, previous, operand)
                self.variables[name] = _check_value(value)
            elif isinstance(stmt, ast.If):
                branch = stmt.body if self.evaluate(stmt.test) else stmt.orelse
                self.run_block(branch)
            elif isinstance(stmt, ast.For):
                sequence = self.evaluate(stmt.iter)
                if type(sequence) not in (list, str, dict):
                    raise ValueError("for requires a list, string or dictionary")
                if self.loops + len(sequence) > MAX_LOOPS:
                    raise ValueError("loop iteration budget exhausted")
                for item in sequence:
                    self.loops += 1
                    if self.loops > MAX_LOOPS:
                        raise ValueError("loop iteration budget exhausted")
                    self.variables[stmt.target.id] = item
                    self.run_block(stmt.body)

    def evaluate(self, node):
        self.step(node)
        if isinstance(node, ast.Constant):
            return node.value
        if isinstance(node, ast.Name):
            return self.variables[node.id]
        if isinstance(node, ast.List):
            return _check_value([self.evaluate(item) for item in node.elts])
        if isinstance(node, ast.Dict):
            values = {}
            for key, child in zip(node.keys, node.values):
                name = self.evaluate(key)
                if type(name) is not str:
                    raise ValueError("dictionary keys must be strings")
                values[name] = self.evaluate(child)
            return _check_value(values)
        if isinstance(node, ast.Subscript):
            data = self.evaluate(node.value)
            return data[self.evaluate(node.slice)]
        if isinstance(node, ast.BinOp):
            left = self.evaluate(node.left)
            right = self.evaluate(node.right)
            return _check_value(_binary(node.op, left, right))
        if isinstance(node, ast.UnaryOp):
            value = self.evaluate(node.operand)
            if isinstance(node.op, ast.Not):
                return not value
            if type(value) not in (int, float):
                raise ValueError("unary arithmetic requires a number")
            return -value if isinstance(node.op, ast.USub) else value
        if isinstance(node, ast.BoolOp):
            for child in node.values:
                value = self.evaluate(child)
                if bool(value) != isinstance(node.op, ast.And):
                    break
            return value
        if isinstance(node, ast.IfExp):
            return self.evaluate(node.body if self.evaluate(node.test) else node.orelse)
        if isinstance(node, ast.Compare):
            left = self.evaluate(node.left)
            for op, child in zip(node.ops, node.comparators):
                right = self.evaluate(child)
                if not _compare(op, left, right):
                    return False
                left = right
            return True
        if isinstance(node, ast.Call):
            args = [self.evaluate(child) for child in node.args]
            kwargs = {kw.arg: self.evaluate(kw.value) for kw in node.keywords}
            self.line = node.lineno
            return self.call(node.func.id, args, kwargs)
        raise ValueError("unsupported expression")

    def call(self, name, args, kwargs):
        if name in TOOL_NAMES:
            if self.calls >= MAX_CALLS:
                raise ValueError("tool call budget exhausted")
            self.calls += 1
            value = self.api[name](*args, **kwargs)
            if monotonic() > self.deadline:
                raise ValueError("execution budget exhausted after the tool call")
            return _check_value(value)
        if kwargs:
            raise ValueError("builtins accept positional arguments only")
        if name == "print":
            parts = []
            size = len(self.output)
            for arg in args:
                part = str(arg)
                size += len(part) + 1
                if size > MAX_OUTPUT:
                    raise ValueError("print output exceeds the size limit")
                parts.append(part)
            if len(self.output) >= MAX_OUTPUT:
                raise ValueError("print output exceeds the size limit")
            self.output += " ".join(parts) + "\n"
            return None
        if name == "range":
            if not 1 <= len(args) <= 3 or any(type(n) is not int for n in args):
                raise ValueError("range needs one to three integers")
            sequence = range(*args)
            if len(sequence) > MAX_ITEMS:
                raise ValueError("range exceeds the item limit")
            return list(sequence)
        if len(args) != 1:
            raise ValueError(f"{name} requires one argument")
        arg = args[0]
        if name == "len":
            return len(arg)
        if name == "bool":
            return bool(arg)
        if name == "str":
            return _check_value(str(arg))
        if type(arg) is str and len(arg) > 80:
            raise ValueError("integer literal is too long")
        return _check_value(int(arg))


def execute_code(code: str, api: dict) -> dict:
    """Return result, stdout, steps and tool_calls. Tools own their I/O timeouts."""
    if not isinstance(code, str) or len(code) > MAX_SOURCE:
        raise ValueError(f"code must be text of at most {MAX_SOURCE} characters")
    runner = _Runner(api)
    try:
        tree = ast.parse(code, mode="exec")
        _validate(tree, runner)
        runner.run_block(tree.body)
    except Exception as exc:
        line = exc.lineno if isinstance(exc, SyntaxError) else runner.line
        raise ValueError(
            f"line {line}, tool calls started: {runner.calls}: {str(exc)[:400]}"
        ) from exc
    return {
        "result": runner.variables.get("result"),
        "stdout": runner.output,
        "steps": runner.steps,
        "tool_calls": runner.calls,
    }
