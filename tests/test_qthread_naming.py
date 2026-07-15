"""Guard test: every QThread subclass must name itself via setObjectName.

An unnamed QThread shows up as '' in Qt teardown warnings
("QThread: Destroyed while thread '' is still running"), which makes crashes
impossible to attribute to a specific worker. This test fails as soon as a new
QThread subclass forgets the `self.setObjectName(...)` call, so the rule is
enforced in CI instead of relying on reviewer memory.

See the engineering rules in CLAUDE.md.
"""

from __future__ import annotations

import ast
from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
_SCANNED_DIRS = ("jukebox", "plugins")


def _is_qthread_base(base: ast.expr) -> bool:
    """Return True if a class base refers to QThread (bare or attribute form)."""
    if isinstance(base, ast.Name):
        return base.id == "QThread"
    if isinstance(base, ast.Attribute):
        return base.attr == "QThread"
    return False


def _calls_set_object_name(class_node: ast.ClassDef) -> bool:
    """Return True if the class body contains a `self.setObjectName(...)` call."""
    for node in ast.walk(class_node):
        if (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr == "setObjectName"
        ):
            return True
    return False


def _find_qthread_subclasses() -> list[tuple[Path, ast.ClassDef]]:
    """Collect every QThread subclass declared under the scanned directories."""
    found: list[tuple[Path, ast.ClassDef]] = []
    for directory in _SCANNED_DIRS:
        for path in (_PROJECT_ROOT / directory).rglob("*.py"):
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
            for node in ast.walk(tree):
                if isinstance(node, ast.ClassDef) and any(
                    _is_qthread_base(base) for base in node.bases
                ):
                    found.append((path, node))
    return found


def test_every_qthread_subclass_sets_object_name() -> None:
    """Fail listing any QThread subclass that never calls setObjectName."""
    subclasses = _find_qthread_subclasses()
    # Sanity check: if this ever drops to zero the discovery logic is broken.
    assert subclasses, "no QThread subclass found — discovery logic is broken"

    offenders = [
        f"{path.relative_to(_PROJECT_ROOT)}::{node.name}"
        for path, node in subclasses
        if not _calls_set_object_name(node)
    ]

    assert not offenders, (
        "QThread subclasses missing a self.setObjectName(...) call "
        f"(unnamed threads appear as '' in Qt warnings): {offenders}"
    )
