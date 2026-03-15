"""
Reference image URL cache for Kie.ai Image Studio.

Caches uploaded image URLs (which expire after 3 days on Kie.ai's servers)
to avoid redundant re-uploads of the same local file.

Key: absolute file path
Validation: file mtime + file size must match (detects local file changes)
TTL: 3 days (259200 seconds)
"""

import json
import os
import tempfile
from datetime import datetime, timedelta
from pathlib import Path

CACHE_TTL_SECONDS = 3 * 24 * 3600  # 3 days


def _cache_path(project_root: Path) -> Path:
    return project_root / "image_cache.json"


def load_cache(project_root: Path) -> dict:
    """Load cache from disk, cleaning expired entries."""
    path = _cache_path(project_root)
    if not path.exists():
        return {"version": 1, "entries": {}}
    try:
        with open(path, "r", encoding="utf-8") as f:
            cache = json.load(f)
    except (json.JSONDecodeError, IOError):
        return {"version": 1, "entries": {}}
    cache = clean_expired(cache)
    return cache


def save_cache(project_root: Path, cache: dict) -> None:
    """Write cache to disk atomically (temp file + rename)."""
    path = _cache_path(project_root)
    try:
        fd, tmp = tempfile.mkstemp(dir=project_root, suffix=".tmp")
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(cache, f, indent=2, ensure_ascii=False)
        os.replace(tmp, path)
    except Exception:
        # Non-critical — cache miss is fine, don't crash the agent
        try:
            os.unlink(tmp)
        except Exception:
            pass


def _file_key(file_path: str) -> str:
    """Resolve file path to absolute canonical form."""
    return str(Path(file_path).expanduser().resolve())


def _file_stats(file_path: str) -> tuple[float, int]:
    """Return (mtime, size) for a file."""
    st = os.stat(file_path)
    return st.st_mtime, st.st_size


def _is_valid(entry: dict) -> bool:
    """Check if a cache entry is still within TTL."""
    try:
        uploaded = datetime.fromisoformat(entry["uploaded_at"])
        return datetime.now() - uploaded < timedelta(seconds=CACHE_TTL_SECONDS)
    except (KeyError, ValueError):
        return False


def _hours_ago(entry: dict) -> str:
    """Human-readable time since upload."""
    try:
        uploaded = datetime.fromisoformat(entry["uploaded_at"])
        delta = datetime.now() - uploaded
        hours = delta.total_seconds() / 3600
        if hours < 1:
            return f"{int(delta.total_seconds() / 60)}m ago"
        if hours < 24:
            return f"{hours:.1f}h ago"
        return f"{delta.days}d {int(hours % 24)}h ago"
    except (KeyError, ValueError):
        return "unknown"


def get_cached_url(project_root: Path, file_path: str) -> tuple[str | None, str]:
    """Check if file has a valid cached URL.

    Returns (url, time_ago_str) if cache hit + valid TTL + file unchanged.
    Returns (None, "") otherwise.
    """
    cache = load_cache(project_root)
    key = _file_key(file_path)
    entry = cache.get("entries", {}).get(key)
    if not entry:
        return None, ""
    if not _is_valid(entry):
        return None, ""
    # Check file hasn't changed
    try:
        mtime, size = _file_stats(file_path)
        if abs(mtime - entry.get("file_mtime", 0)) > 0.01 or size != entry.get("file_size", -1):
            return None, ""
    except OSError:
        return None, ""
    return entry["url"], _hours_ago(entry)


def store_cache_entry(project_root: Path, file_path: str, url: str) -> None:
    """Add or update a cache entry after successful upload."""
    cache = load_cache(project_root)
    key = _file_key(file_path)
    try:
        mtime, size = _file_stats(file_path)
    except OSError:
        return
    cache.setdefault("entries", {})[key] = {
        "url": url,
        "uploaded_at": datetime.now().isoformat(),
        "file_mtime": mtime,
        "file_size": size,
    }
    save_cache(project_root, cache)


def clean_expired(cache: dict) -> dict:
    """Remove entries older than TTL."""
    entries = cache.get("entries", {})
    cleaned = {k: v for k, v in entries.items() if _is_valid(v)}
    cache["entries"] = cleaned
    return cache


def clear_cache(project_root: Path) -> int:
    """Delete all cache entries. Returns number of entries removed."""
    cache = load_cache(project_root)
    count = len(cache.get("entries", {}))
    cache["entries"] = {}
    save_cache(project_root, cache)
    return count


def get_cache_stats(project_root: Path) -> dict:
    """Return cache statistics for display."""
    path = _cache_path(project_root)
    if not path.exists():
        return {"total": 0, "valid": 0, "expired": 0}
    try:
        with open(path, "r", encoding="utf-8") as f:
            cache = json.load(f)
    except (json.JSONDecodeError, IOError):
        return {"total": 0, "valid": 0, "expired": 0}
    entries = cache.get("entries", {})
    total = len(entries)
    valid = sum(1 for e in entries.values() if _is_valid(e))
    return {"total": total, "valid": valid, "expired": total - valid}
