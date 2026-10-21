"""Static dependency/config boundaries that must survive implementation changes."""

import ast
from pathlib import Path

from app.config import Settings

ROOT = Path(__file__).resolve().parents[2]


def test_runner_has_no_concrete_fake_dependencies() -> None:
    tree = ast.parse((ROOT / "backend/app/agent/runner.py").read_text())
    imports = []
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            imports.append(node.module or "")
        elif isinstance(node, ast.Import):
            imports.extend(alias.name for alias in node.names)
    assert not any("fakes" in name.split(".") for name in imports)


def test_env_example_exactly_matches_settings() -> None:
    names = [
        line.split("=", 1)[0].strip()
        for line in (ROOT / "backend/.env.example").read_text().splitlines()
        if "=" in line and not line.lstrip().startswith("#")
    ]
    assert len(names) == len(set(names)), "Duplicate environment settings"
    assert set(names) == {name.upper() for name in Settings.model_fields}
