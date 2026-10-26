"""Guard: every background task of the provider has an owner that unload cancels."""

from __future__ import annotations

import ast
from pathlib import Path

_PROVIDER = Path(__file__).resolve().parents[2] / "provider" / "provider.py"


def _create_task_callers(source: str) -> list[tuple[str, int]]:
    """Return (enclosing function, line) of every ``*.create_task(...)`` call."""
    calls: list[tuple[str, int]] = []

    class Visitor(ast.NodeVisitor):
        def __init__(self) -> None:
            self.stack: list[str] = []

        def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
            self.stack.append(node.name)
            self.generic_visit(node)
            self.stack.pop()

        def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:
            self.stack.append(node.name)
            self.generic_visit(node)
            self.stack.pop()

        def visit_Call(self, node: ast.Call) -> None:
            if isinstance(node.func, ast.Attribute) and node.func.attr == "create_task":
                calls.append((self.stack[-1] if self.stack else "<module>", node.lineno))
            self.generic_visit(node)

    Visitor().visit(ast.parse(source))
    return calls


def test_provider_creates_tasks_only_through_spawn() -> None:
    """Tasks started anywhere else would outlive unload."""
    stray = [
        (func, line)
        for func, line in _create_task_callers(_PROVIDER.read_text(encoding="utf-8"))
        if func != "_spawn"
    ]

    assert stray == [], f"create_task outside _spawn in provider/provider.py: {stray}"


def test_guard_detects_a_stray_task() -> None:
    """The guard is live: a create_task outside _spawn is reported."""
    source = "class P:\n    def _spawn(self, c):\n        return self.mass.create_task(c)\n    def f(self):\n        self.mass.create_task(x)\n"

    assert _create_task_callers(source) == [("_spawn", 3), ("f", 5)]
