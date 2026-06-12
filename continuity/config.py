"""Configuration and path resolution."""

import os


def get_continuity_root() -> str:
    """Resolve CONTINUITY_ROOT from env or default."""
    return os.environ.get("CONTINUITY_ROOT", os.path.expanduser("~/.claracore/continuity"))


def get_default_agent_id() -> str | None:
    """Resolve current agent namespace from env. Returns None if not set."""
    return os.environ.get("CONTINUITY_AGENT_ID")


def require_agent_id(explicit: str | None = None) -> str:
    """Resolve agent ID with explicit override. Raises if neither set."""
    agent_id = explicit or get_default_agent_id()
    if not agent_id:
        raise SystemExit(
            "Agent ID required. Set CONTINUITY_AGENT_ID env var or pass --agent-id.\n"
            "Example:  CONTINUITY_AGENT_ID=clara  or  --agent-id clara"
        )
    return agent_id


def get_db_path() -> str:
    """Return path to SQLite database."""
    return os.path.join(get_continuity_root(), "continuity.db")


def ensure_directories() -> None:
    """Create continuity root directory if absent."""
    os.makedirs(get_continuity_root(), exist_ok=True)
