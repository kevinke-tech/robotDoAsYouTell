"""Static preflight checks for generated skills before promotion."""

from __future__ import annotations

import ast
from pathlib import Path


_VISIBLE_BROWSER_MOD = "webbrowser"
_NETWORK_METHODS = {"get", "post", "put", "delete", "request", "stream"}


def _is_http_literal(node: ast.AST | None) -> bool:
    return isinstance(node, ast.Constant) and isinstance(node.value, str) and node.value.lower().startswith(("http://", "https://"))


def run_skill_preflight(skill_path: Path) -> tuple[bool, list[str], list[str]]:
    errors: list[str] = []
    warnings: list[str] = []

    try:
        src = skill_path.read_text(encoding="utf-8")
        tree = ast.parse(src, filename=str(skill_path))
    except Exception as e:
        return False, [f"preflight parse failed: {type(e).__name__}: {e}"], []

    has_main = False
    run_node: ast.AsyncFunctionDef | None = None

    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name == _VISIBLE_BROWSER_MOD:
                    errors.append("visible browser import is forbidden: webbrowser")
        elif isinstance(node, ast.ImportFrom):
            if node.module == _VISIBLE_BROWSER_MOD:
                errors.append("visible browser import is forbidden: webbrowser")
        elif isinstance(node, ast.AsyncFunctionDef) and node.name == "run":
            run_node = node

    for node in tree.body:
        if isinstance(node, ast.If):
            tst = ast.unparse(node.test) if hasattr(ast, "unparse") else ""
            if "__name__" in tst and "__main__" in tst:
                has_main = True
                for inner in ast.walk(node):
                    if (
                        isinstance(inner, ast.Call)
                        and isinstance(inner.func, ast.Attribute)
                        and isinstance(inner.func.value, ast.Name)
                        and inner.func.value.id == "time"
                        and inner.func.attr == "sleep"
                        and inner.args
                        and isinstance(inner.args[0], ast.Constant)
                        and isinstance(inner.args[0].value, (int, float))
                        and float(inner.args[0].value) > 3.0
                    ):
                        errors.append("smoke __main__ contains time.sleep > 3s")

    if not has_main:
        errors.append('missing `if __name__ == "__main__":` smoke block')

    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        if isinstance(node.func, ast.Attribute):
            base = node.func.value
            attr = node.func.attr
            if isinstance(base, ast.Name) and base.id == "webbrowser" and attr in {"open", "open_new", "open_new_tab"}:
                errors.append("visible browser open call is forbidden")
            if attr in _NETWORK_METHODS and node.args and _is_http_literal(node.args[0]):
                has_timeout = any(kw.arg == "timeout" for kw in (node.keywords or []))
                if not has_timeout:
                    warnings.append("network call detected without explicit timeout")

    if run_node is not None:
        has_try = any(isinstance(n, ast.Try) for n in ast.walk(run_node))
        has_http_literal = any(_is_http_literal(n) for n in ast.walk(run_node))
        if has_http_literal and not has_try:
            warnings.append("run() appears to call external sources without try/except guard")

    return (len(errors) == 0), errors, warnings

