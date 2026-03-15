"""
Feedback learning module for Image Studio.

Analyzes evaluation history to extract patterns and provide data-driven
recommendations for model selection, enhancement levels, and quality
improvement. All recommendations are rule-based (no LLM calls).
"""

import json
from collections import defaultdict
from pathlib import Path

from prompt_history import scan_prompts


# ── Thresholds ────────────────────────────────────────────────────────────────

MIN_TOTAL = 10           # Don't recommend until this many rated images exist
MIN_PER_COMBO = 3        # Need 3+ ratings for a model×category combo
MIN_RATING_DIFF = 0.5    # Only recommend if difference is meaningful

# Keywords that signal quality issues when found in low-rated notes
NEGATIVE_KEYWORDS = [
    "ai", "cgi", "render", "fake", "plastic", "wrong", "distort",
    "blurry", "missing", "floating", "duplicate", "extra",
    "smooth", "unrealistic", "cartoon", "generated",
]

PREFERENCES_FILENAME = "learned_preferences.json"


# ── Core Analysis ─────────────────────────────────────────────────────────────

def _collect_evaluated_entries(prompts_dir, project_prompts_dir=None):
    """Scan prompt JSONs and return only those with evaluations."""
    dirs = [prompts_dir]
    if project_prompts_dir and project_prompts_dir != prompts_dir:
        dirs.append(project_prompts_dir)

    evaluated = []
    for d in dirs:
        for entry in scan_prompts(d):
            eval_data = entry.get("evaluation")
            if eval_data and "rating" in eval_data:
                evaluated.append(entry)
    return evaluated


def _compute_combo_stats(entries, key_fn):
    """Compute average rating per group defined by key_fn.

    Args:
        entries: list of prompt JSON dicts with evaluation data
        key_fn: callable that takes an entry and returns a grouping key (str)

    Returns:
        dict mapping group key -> {"avg": float, "count": int, "total": int}
    """
    groups = defaultdict(lambda: {"total": 0, "count": 0})
    for entry in entries:
        key = key_fn(entry)
        if not key:
            continue
        rating = entry["evaluation"]["rating"]
        groups[key]["total"] += rating
        groups[key]["count"] += 1

    stats = {}
    for key, data in groups.items():
        if data["count"] >= MIN_PER_COMBO:
            stats[key] = {
                "avg": round(data["total"] / data["count"], 2),
                "count": data["count"],
            }
    return stats


def _analyze_notes(entries):
    """Extract keyword frequency from low-rated evaluation notes.

    Returns dict mapping keyword -> {"count": int, "avg_rating": float}
    """
    keyword_data = defaultdict(lambda: {"count": 0, "rating_sum": 0})

    for entry in entries:
        eval_data = entry.get("evaluation", {})
        rating = eval_data.get("rating", 0)
        notes = eval_data.get("notes", "").lower()
        if not notes or rating > 3:
            continue  # Only analyze notes from low/medium-rated images

        for keyword in NEGATIVE_KEYWORDS:
            if keyword in notes:
                keyword_data[keyword]["count"] += 1
                keyword_data[keyword]["rating_sum"] += rating

    result = {}
    for keyword, data in keyword_data.items():
        if data["count"] >= 2:  # Need at least 2 mentions
            result[keyword] = {
                "count": data["count"],
                "avg_rating": round(data["rating_sum"] / data["count"], 2),
            }
    return result


def compute_preferences(project_root, project_slug=None):
    """Analyze all evaluated prompts and compute learned preferences.

    Args:
        project_root: Path to the project root directory
        project_slug: Optional project slug for project-scoped analysis

    Returns:
        dict with computed preferences, or None if not enough data
    """
    prompts_dir = project_root / "prompts"
    project_prompts_dir = None
    if project_slug:
        project_prompts_dir = project_root / "projects" / project_slug / "prompts"

    entries = _collect_evaluated_entries(prompts_dir, project_prompts_dir)

    if len(entries) < MIN_TOTAL:
        return {
            "total_evaluations": len(entries),
            "ready": False,
            "needed": MIN_TOTAL - len(entries),
        }

    # Model × Category stats
    model_by_category = {}
    cat_groups = defaultdict(list)
    for entry in entries:
        cat = entry.get("category", "")
        if cat:
            cat_groups[cat].append(entry)

    for cat, cat_entries in cat_groups.items():
        model_stats = _compute_combo_stats(
            cat_entries, lambda e: e.get("model", "")
        )
        if model_stats:
            best_model = max(model_stats, key=lambda k: model_stats[k]["avg"])
            model_by_category[cat] = {
                "recommended": best_model,
                "avg_rating": model_stats[best_model]["avg"],
                "sample_size": model_stats[best_model]["count"],
                "alternatives": {
                    k: v for k, v in model_stats.items() if k != best_model
                },
            }

    # Model × Enhancement Level stats
    enhance_by_model = {}
    model_groups = defaultdict(list)
    for entry in entries:
        model = entry.get("model", "")
        if model:
            model_groups[model].append(entry)

    for model, model_entries in model_groups.items():
        enhance_stats = _compute_combo_stats(
            model_entries, lambda e: e.get("enhance_level", "")
        )
        if enhance_stats:
            best_enhance = max(enhance_stats, key=lambda k: enhance_stats[k]["avg"])
            enhance_by_model[model] = {
                "recommended": best_enhance,
                "avg_rating": enhance_stats[best_enhance]["avg"],
                "sample_size": enhance_stats[best_enhance]["count"],
            }

    # Negative note patterns
    negative_patterns = _analyze_notes(entries)

    preferences = {
        "total_evaluations": len(entries),
        "ready": True,
        "model_by_category": model_by_category,
        "enhance_by_model": enhance_by_model,
        "negative_patterns": negative_patterns,
    }

    # Save to file
    _save_preferences(project_root, project_slug, preferences)

    return preferences


def _get_preferences_path(project_root, project_slug=None):
    """Get the path for learned_preferences.json (root or project-scoped)."""
    if project_slug:
        return project_root / "projects" / project_slug / PREFERENCES_FILENAME
    return project_root / PREFERENCES_FILENAME


def _save_preferences(project_root, project_slug, preferences):
    """Write preferences to disk."""
    path = _get_preferences_path(project_root, project_slug)
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(preferences, f, indent=2, ensure_ascii=False)


def load_preferences(project_root, project_slug=None):
    """Load cached preferences from disk.

    Returns the preferences dict, or None if no file exists.
    """
    path = _get_preferences_path(project_root, project_slug)
    if not path.exists():
        return None
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, IOError):
        return None


# ── Recommendation Functions ──────────────────────────────────────────────────

def get_model_recommendation(preferences, category):
    """Get the best-performing model for a category.

    Returns (model_id, reason_string) or None if not enough data.
    """
    if not preferences or not preferences.get("ready"):
        return None

    cat_data = preferences.get("model_by_category", {}).get(category)
    if not cat_data:
        return None

    model = cat_data["recommended"]
    avg = cat_data["avg_rating"]
    n = cat_data["sample_size"]

    # Check if there's a meaningful difference from alternatives
    alts = cat_data.get("alternatives", {})
    if alts:
        best_alt_avg = max(v["avg"] for v in alts.values()) if alts else 0
        if avg - best_alt_avg < MIN_RATING_DIFF:
            return None  # Difference not meaningful

    # Build a display-friendly model name
    model_short = model.split("/")[-1] if "/" in model else model

    return (
        model,
        f"{model_short} averages {avg:.1f}/5 for {category} ({n} ratings)",
    )


def get_enhance_recommendation(preferences, model):
    """Get the best-performing enhancement level for a model.

    Returns (enhance_level, reason_string) or None.
    """
    if not preferences or not preferences.get("ready"):
        return None

    model_data = preferences.get("enhance_by_model", {}).get(model)
    if not model_data:
        return None

    level = model_data["recommended"]
    avg = model_data["avg_rating"]
    n = model_data["sample_size"]

    model_short = model.split("/")[-1] if "/" in model else model
    level_display = level.replace("_", " ").title()

    return (
        level,
        f"{level_display} scores {avg:.1f}/5 on {model_short} ({n} ratings)",
    )


def get_negative_warnings(preferences):
    """Get warning strings about patterns found in negative feedback.

    Returns a list of warning strings, or empty list.
    """
    if not preferences or not preferences.get("ready"):
        return []

    patterns = preferences.get("negative_patterns", {})
    warnings = []

    for keyword, data in sorted(patterns.items(), key=lambda x: -x[1]["count"]):
        count = data["count"]
        avg = data["avg_rating"]
        warnings.append(
            f"{count} low-rated images mention '{keyword}' "
            f"(avg {avg:.1f}/5)"
        )

    return warnings


def get_not_ready_message(preferences):
    """Get a message about how many more ratings are needed.

    Returns a string like "7 more ratings needed" or None if ready.
    """
    if not preferences:
        return f"{MIN_TOTAL} ratings needed before recommendations activate"

    if preferences.get("ready"):
        return None

    needed = preferences.get("needed", MIN_TOTAL)
    total = preferences.get("total_evaluations", 0)
    return f"{needed} more ratings needed ({total}/{MIN_TOTAL} so far)"
