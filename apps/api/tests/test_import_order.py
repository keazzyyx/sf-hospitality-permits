"""Guard: `neatlogs.init()` runs in app/main.py before anything imports `anthropic`."""

from __future__ import annotations

import ast
import subprocess
import sys
from pathlib import Path

MAIN = Path(__file__).resolve().parents[1] / "app" / "main.py"
ANTHROPIC_IMPORTERS = ("anthropic", "app.agents", "app.tools", "app.routes", "app.deps", "app.services")


def _imports_of(node: ast.stmt) -> list[str]:
    if isinstance(node, ast.Import):
        return [a.name for a in node.names]
    if isinstance(node, ast.ImportFrom):
        return [node.module or ""]
    return []


def test_static_order_in_main() -> None:
    tree = ast.parse(MAIN.read_text())
    init_index = None
    for i, node in enumerate(tree.body):
        if isinstance(node, ast.Expr) and isinstance(node.value, ast.Call):
            fn = node.value.func
            if (
                isinstance(fn, ast.Attribute)
                and fn.attr == "init"
                and isinstance(fn.value, ast.Name)
                and fn.value.id == "neatlogs"
            ):
                init_index = i
                break
    assert init_index is not None, "app/main.py must call neatlogs.init(...) at module level"
    before = [m for node in tree.body[:init_index] for m in _imports_of(node)]
    assert before, "neatlogs must be imported before init"
    for m in before:
        assert not m.startswith(ANTHROPIC_IMPORTERS), f"{m} is imported before neatlogs.init()"
    assert all(m in {"neatlogs", "app.core.config", "app.core.observability"} for m in before), before
    # required init arguments
    call = tree.body[init_index].value  # type: ignore[attr-defined]
    kw = {k.arg for k in call.keywords}
    assert {"api_key", "workflow_name", "instrumentations", "tags", "mask"} <= kw
    instr = next(k.value for k in call.keywords if k.arg == "instrumentations")
    assert ast.literal_eval(instr) == ["anthropic"]


def test_runtime_order_anthropic_not_loaded_before_init() -> None:
    code = r"""
import sys, neatlogs
seen = {}
orig = neatlogs.init
def spy(*a, **k):
    seen["anthropic_loaded"] = "anthropic" in sys.modules
    seen["instrumentations"] = k.get("instrumentations")
    return orig(*a, **k)
neatlogs.init = spy
import app.main  # noqa
print("ANTHROPIC_LOADED=%s" % seen.get("anthropic_loaded"))
print("INSTR=%s" % seen.get("instrumentations"))
print("ANTHROPIC_AFTER=%s" % ("anthropic" in sys.modules))
"""
    proc = subprocess.run(
        [sys.executable, "-c", code],
        capture_output=True,
        text=True,
        cwd=MAIN.parents[1],
        check=False,
        env={
            "PATH": "/usr/bin:/bin",
            "ENV": "test",
            "WEB_VERIFY_ENABLED": "false",
            "PYTHONPATH": str(MAIN.parents[1]),
        },
    )
    assert proc.returncode == 0, proc.stderr[-2000:]
    assert "ANTHROPIC_LOADED=False" in proc.stdout, proc.stdout
    assert "INSTR=['anthropic']" in proc.stdout
    assert "ANTHROPIC_AFTER=True" in proc.stdout


def test_config_modules_do_not_import_anthropic() -> None:
    for rel in ("app/core/config.py", "app/core/observability.py"):
        src = (MAIN.parent.parent / rel).read_text()
        assert "import anthropic" not in src and "from anthropic" not in src
