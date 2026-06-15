"""Model adjustments — per-model negative constraints (forbidden phrases, patterns, inject prompt).

Stored as a standalone JSON file so it migrates cleanly to Afterglow or any other
runtime without touching the SQLite schema.
"""

import json
import os
from copy import deepcopy
from dataclasses import dataclass, field
from typing import Optional

from .config import get_continuity_root, ensure_directories
from .models import now_iso

FILE_VERSION = 1


def _file_path() -> str:
    ensure_directories()
    return os.path.join(get_continuity_root(), "model_adjustments.json")


def _load() -> dict:
    """Read the full adjustments store from disk, or return an empty scaffold."""
    path = _file_path()
    if not os.path.exists(path):
        return {"version": FILE_VERSION, "updated_at": "", "models": {}}
    with open(path, "r", encoding="utf-8") as fh:
        return json.load(fh)


def _save(data: dict) -> None:
    data["updated_at"] = now_iso()
    with open(_file_path(), "w", encoding="utf-8") as fh:
        json.dump(data, fh, ensure_ascii=False, indent=2)


# ── Public API ──────────────────────────────────────────────────

def list_models() -> list:
    """Return list of model names that have adjustments configured."""
    store = _load()
    return sorted(store.get("models", {}).keys())


def get_model(model: str) -> Optional[dict]:
    """Get adjustments for a single model. Returns None if not configured."""
    store = _load()
    return store.get("models", {}).get(model)


def set_model(model: str,
              forbidden_phrases: Optional[list] = None,
              forbidden_patterns: Optional[list] = None,
              inject_prompt: Optional[str] = None,
              updated_by: str = "user") -> dict:
    """Create or update adjustments for *model*. Only provided fields are changed."""
    store = _load()
    if "models" not in store:
        store["models"] = {}

    existing = store["models"].get(model, {})
    entry = deepcopy(existing)
    entry["model"] = model

    if forbidden_phrases is not None:
        entry["forbidden_phrases"] = forbidden_phrases
    if forbidden_patterns is not None:
        entry["forbidden_patterns"] = forbidden_patterns
    if inject_prompt is not None:
        entry["inject_prompt"] = inject_prompt

    entry.setdefault("forbidden_phrases", [])
    entry.setdefault("forbidden_patterns", [])
    entry.setdefault("inject_prompt", "")

    entry["updated_by"] = updated_by
    entry["updated_at"] = now_iso()

    store["models"][model] = entry
    _save(store)
    return entry


def delete_model(model: str, actor: str = "user") -> bool:
    """Remove adjustments for *model*. Returns False if it didn't exist."""
    store = _load()
    if model not in store.get("models", {}):
        return False
    del store["models"][model]
    _save(store)
    return True


def get_inject_prompt(model: str) -> Optional[str]:
    """Convenience: return the inject_prompt for *model*, or None."""
    entry = get_model(model)
    if not entry:
        return None
    return entry.get("inject_prompt") or None


def get_all_inject_prompts() -> dict:
    """Return {model_name: inject_prompt} for all configured models."""
    store = _load()
    return {
        m: cfg.get("inject_prompt", "")
        for m, cfg in store.get("models", {}).items()
        if cfg.get("inject_prompt")
    }
