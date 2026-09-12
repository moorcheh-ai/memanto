"""Static regression guard for FastAPI route authentication dependencies.

This source-only check prevents a non-health route from silently omitting both
Memanto authorization dependencies.  It deliberately makes no network calls
and does not require API credentials.
"""

from __future__ import annotations

import argparse
import ast
import json
from pathlib import Path


PUBLIC_ROUTE_FILES = {"health.py"}
AUTH_DEPENDENCIES = {"get_current_session", "verify_moorcheh_api_key"}
HTTP_DECORATORS = {"get", "post", "put", "patch", "delete", "options", "head"}


def call_name(node: ast.AST) -> str | None:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        return node.attr
    return None


def dependency_name(default: ast.expr | None) -> str | None:
    if not isinstance(default, ast.Call) or call_name(default.func) != "Depends":
        return None
    return call_name(default.args[0]) if default.args else None


def handler_dependencies(function: ast.AsyncFunctionDef | ast.FunctionDef) -> set[str]:
    found: set[str] = set()
    for default in [*function.args.defaults, *function.args.kw_defaults]:
        name = dependency_name(default)
        if name:
            found.add(name)
    return found


def decorator_dependencies(decorator: ast.Call) -> set[str]:
    """Find ``dependencies=[Depends(...)]`` declared on a route decorator."""
    found: set[str] = set()
    for keyword in decorator.keywords:
        if keyword.arg != "dependencies" or not isinstance(
            keyword.value, (ast.List, ast.Tuple, ast.Set)
        ):
            continue
        for item in keyword.value.elts:
            name = dependency_name(item)
            if name:
                found.add(name)
    return found


def router_dependency_map(tree: ast.AST) -> dict[str, set[str]]:
    """Map APIRouter variable names to their declared dependencies."""
    routers: dict[str, set[str]] = {}
    for node in ast.walk(tree):
        if not isinstance(node, (ast.Assign, ast.AnnAssign)):
            continue
        value = node.value
        if not isinstance(value, ast.Call) or call_name(value.func) != "APIRouter":
            continue
        targets = node.targets if isinstance(node, ast.Assign) else [node.target]
        names = [target.id for target in targets if isinstance(target, ast.Name)]
        dependencies = decorator_dependencies(value)
        for name in names:
            routers[name] = dependencies
    return routers


def decorator_router_name(decorator: ast.Call) -> str | None:
    receiver = decorator.func.value if isinstance(decorator.func, ast.Attribute) else None
    return receiver.id if isinstance(receiver, ast.Name) else None


def is_http_route(decorator: ast.expr) -> bool:
    return (
        isinstance(decorator, ast.Call)
        and isinstance(decorator.func, ast.Attribute)
        and decorator.func.attr in HTTP_DECORATORS
    )


def route_records(routes_dir: Path) -> list[dict[str, object]]:
    records: list[dict[str, object]] = []
    for source in sorted(routes_dir.glob("*.py")):
        if source.name in PUBLIC_ROUTE_FILES:
            continue
        tree = ast.parse(source.read_text(encoding="utf-8"), filename=str(source))
        router_dependencies = router_dependency_map(tree)
        for node in ast.walk(tree):
            if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            for decorator in (d for d in node.decorator_list if is_http_route(d)):
                assert isinstance(decorator, ast.Call)
                path = (
                    decorator.args[0].value
                    if decorator.args and isinstance(decorator.args[0], ast.Constant)
                    else None
                )
                router_name = decorator_router_name(decorator)
                records.append(
                    {
                        "source": source.name,
                        "line": node.lineno,
                        "function": node.name,
                        "method": decorator.func.attr.upper(),
                        "path": path,
                        "dependencies": sorted(
                            handler_dependencies(node).union(
                                decorator_dependencies(decorator),
                                router_dependencies.get(router_name, set()),
                            )
                        ),
                    }
                )
    return sorted(records, key=lambda item: (str(item["source"]), int(item["line"])))


def audit(routes_dir: Path) -> list[str]:
    failures: list[str] = []
    for record in route_records(routes_dir):
        if not set(record["dependencies"]).intersection(AUTH_DEPENDENCIES):
            failures.append(
                f"{record['source']}:{record['line']} {record['function']} "
                f"-> {record['dependencies']}"
            )
    return failures


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("source_root", nargs="?", type=Path, default=Path("."))
    parser.add_argument("--manifest", type=Path)
    args = parser.parse_args()
    routes_dir = args.source_root / "memanto" / "app" / "routes"
    if not routes_dir.is_dir():
        raise SystemExit(f"routes directory not found: {routes_dir}")
    records = route_records(routes_dir)
    if args.manifest:
        args.manifest.write_text(
            json.dumps({"routes": records}, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
    failures = audit(routes_dir)
    if failures:
        print("AUTH_ROUTE_GUARD=FAIL")
        print("\n".join(failures))
        return 1
    print("AUTH_ROUTE_GUARD=PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
