"""Tests for the source-only route authorization regression guard."""

from __future__ import annotations

import importlib.util
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "verify_route_auth_dependencies",
    ROOT / "scripts" / "verify_route_auth_dependencies.py",
)
assert SPEC and SPEC.loader
guard = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(guard)


def write_routes(tmp_path: Path, content: str) -> Path:
    routes = tmp_path / "memanto" / "app" / "routes"
    routes.mkdir(parents=True)
    (routes / "example.py").write_text(content, encoding="utf-8")
    return routes


def test_allows_handler_and_decorator_dependencies(tmp_path: Path) -> None:
    routes = write_routes(
        tmp_path,
        """\
from fastapi import APIRouter, Depends
router = APIRouter()
def get_current_session(): pass
@router.get('/parameter')
async def parameter_route(session=Depends(get_current_session)): pass
@router.post('/decorator', dependencies=[Depends(get_current_session)])
async def decorator_route(): pass
router_level = APIRouter(dependencies=[Depends(get_current_session)])
@router_level.patch('/router-level')
async def router_level_route(): pass
""",
    )
    assert guard.audit(routes) == []


def test_rejects_unprotected_non_health_route(tmp_path: Path) -> None:
    routes = write_routes(
        tmp_path,
        """\
from fastapi import APIRouter
router = APIRouter()
@router.get('/missing-auth')
async def missing_auth(): pass
""",
    )
    failures = guard.audit(routes)
    assert len(failures) == 1
    assert "missing_auth" in failures[0]


def test_current_route_tree_declares_authorization_dependencies() -> None:
    routes = ROOT / "memanto" / "app" / "routes"
    assert guard.audit(routes) == []
