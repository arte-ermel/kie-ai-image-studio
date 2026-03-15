"""
Prompt history browser for Kie.ai Image Studio.

Scans saved prompt JSON files and presents them for browsing,
filtering, and re-use. Supports project-scoped browsing and tag filtering.
"""

import json
from datetime import datetime
from pathlib import Path


def scan_prompts(prompts_dir: Path) -> list[dict]:
    """Scan a prompts directory for JSON files and return parsed entries.

    Returns list of dicts, each with full prompt data plus 'file_path' added.
    Sorted by generated_at descending (newest first).
    """
    if not prompts_dir.exists():
        return []
    entries = []
    for json_file in prompts_dir.rglob("*.json"):
        try:
            with open(json_file, "r", encoding="utf-8") as f:
                data = json.load(f)
            data["file_path"] = str(json_file)
            entries.append(data)
        except (json.JSONDecodeError, IOError):
            continue
    # Sort newest first
    entries.sort(key=lambda e: e.get("generated_at", ""), reverse=True)
    return entries


def filter_by_tags(entries: list[dict], tags: list[str]) -> list[dict]:
    """Filter prompt entries to those containing ANY of the given tags."""
    if not tags:
        return entries
    tag_set = {t.lower() for t in tags}
    return [
        e for e in entries
        if tag_set.intersection(t.lower() for t in e.get("tags", []))
    ]


def filter_by_category(entries: list[dict], category: str) -> list[dict]:
    """Filter prompt entries by category."""
    return [e for e in entries if e.get("category") == category]


def filter_by_model(entries: list[dict], model: str) -> list[dict]:
    """Filter prompt entries by model ID."""
    return [e for e in entries if e.get("model") == model]


def format_entry_label(entry: dict, max_len: int = 70) -> str:
    """Format a prompt entry for display in a selection menu."""
    ts = entry.get("generated_at", "")[:16].replace("T", " ")
    model = entry.get("model", "?")
    category = entry.get("category", "?")
    mode = entry.get("image_mode", "generate")

    # Try to get a meaningful description snippet
    desc = entry.get("original_description", "")
    if not desc:
        # Fall back to extracting from the full prompt (first ~50 chars)
        desc = entry.get("prompt", "")[:50]
    desc = desc[:40].replace("\n", " ")

    # Rating indicator
    eval_data = entry.get("evaluation", {})
    rating = eval_data.get("rating", 0) if eval_data else 0
    stars = f" {'★' * rating}" if rating else ""

    # Tags
    tags = entry.get("tags", [])
    tag_str = f" [{', '.join(tags)}]" if tags else ""

    label = f"{ts} | {model[:15]:15s} | {category[:12]:12s} | {desc}{stars}{tag_str}"
    return label[:max_len]


def get_all_tags(entries: list[dict]) -> list[str]:
    """Extract all unique tags from a list of prompt entries."""
    tags = set()
    for e in entries:
        for t in e.get("tags", []):
            tags.add(t.lower())
    return sorted(tags)


def entry_to_settings(entry: dict) -> dict:
    """Extract re-usable generation settings from a prompt entry."""
    api_params = entry.get("api_parameters", {})
    return {
        "model": entry.get("model", "nano-banana-2"),
        "category": entry.get("category", "miscellaneous"),
        "style": entry.get("style", "photorealistic"),
        "image_mode": entry.get("image_mode", "generate"),
        "enhance_level": entry.get("enhance_level", "directors_cut"),
        "aspect_ratio": api_params.get("aspect_ratio", "1:1"),
        "resolution": api_params.get("resolution", "1K"),
        "output_format": api_params.get("output_format", "jpg"),
        "edit_operation": entry.get("edit_operation"),
        "description": entry.get("original_description", entry.get("prompt", "")),
        "tags": entry.get("tags", []),
    }
