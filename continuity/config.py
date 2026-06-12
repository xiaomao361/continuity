"""Configuration and path resolution."""

import os


def get_continuity_root() -> str:
    """Resolve CONTINUITY_ROOT from env or default."""
    return os.environ.get("CONTINUITY_ROOT", os.path.expanduser("~/.claracore/continuity"))


def get_default_agent_id() -> str:
    """Resolve current agent namespace from env or default."""
    return os.environ.get("CONTINUITY_AGENT_ID", "default")


def get_db_path() -> str:
    """Return path to SQLite database."""
    return os.path.join(get_continuity_root(), "continuity.db")


def ensure_directories() -> None:
    """Create continuity root directory if absent."""
    os.makedirs(get_continuity_root(), exist_ok=True)
