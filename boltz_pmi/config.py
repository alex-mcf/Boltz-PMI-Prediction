"""Paths configured in environment_variables.sh.

Values are read when a command runs, not at import time, so modules can be
imported (by tests, notebooks, or the app) without the environment loaded.
"""
import os
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent

# Fallbacks used when a variable is unset. Variables without a fallback
# (scratch locations) must come from environment_variables.sh.
_DEFAULTS = {
    "PROJECT_ROOT": PROJECT_ROOT,
    "PROCESSED_DIR": PROJECT_ROOT / "processed_outputs",
    "PLOT_DIR": PROJECT_ROOT / "plots",
    "SOURCE_DIR": PROJECT_ROOT / "inputs" / "proteins",
    "INPUT_DIR": PROJECT_ROOT / "inputs",
}


def path(name: str) -> Path:
    """Return a configured path, exiting with a clear message if it is unset."""
    value = os.environ.get(name)
    if value:
        return Path(value)
    if name in _DEFAULTS:
        return Path(_DEFAULTS[name])
    raise SystemExit(
        f"Environment variable {name} is not set. "
        "Run `source environment_variables.sh` first."
    )


def resolve_input(p: Path | str) -> Path:
    """Resolve a user-supplied input path against the cwd, then the project root."""
    p = Path(p)
    if p.is_absolute() or p.exists():
        return p.resolve()
    return (PROJECT_ROOT / p).resolve()
