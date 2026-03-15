"""
Project management for Kie.ai Image Studio.

Provides customer/client project folders with:
- Project-specific instructions injected into prompts
- Default settings per project (model, resolution, category, etc.)
- Isolated images/prompts/evaluations directories
- Cost tracking and generation counts
"""

import json
import re
import unicodedata
from datetime import datetime
from pathlib import Path


def _projects_dir(project_root: Path) -> Path:
    return project_root / "projects"


def slugify(name: str) -> str:
    """Convert project name to filesystem-safe directory name.

    'Client X Office Building' -> 'client-x-office-building'
    """
    # Normalize unicode
    name = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode("ascii")
    name = name.lower().strip()
    # Replace spaces and underscores with hyphens
    name = re.sub(r"[\s_]+", "-", name)
    # Remove non-alphanumeric chars (keep hyphens)
    name = re.sub(r"[^a-z0-9-]", "", name)
    # Collapse multiple hyphens
    name = re.sub(r"-{2,}", "-", name).strip("-")
    return name[:60] or "unnamed-project"


def list_projects(project_root: Path) -> list[dict]:
    """Scan projects directory for valid project.json files.

    Returns list of project configs, each with an added 'slug' field.
    """
    pdir = _projects_dir(project_root)
    if not pdir.exists():
        return []
    projects = []
    for d in sorted(pdir.iterdir()):
        if not d.is_dir():
            continue
        config_path = d / "project.json"
        if config_path.exists():
            try:
                with open(config_path, "r", encoding="utf-8") as f:
                    config = json.load(f)
                config["slug"] = d.name
                projects.append(config)
            except (json.JSONDecodeError, IOError):
                continue
    return projects


def create_project(project_root: Path, name: str, description: str = "",
                   defaults: dict = None, instructions: str = "") -> dict:
    """Create a new project directory with project.json.

    Returns the project config dict (with 'slug' field).
    Raises ValueError if slug already exists.
    """
    slug = slugify(name)
    pdir = _projects_dir(project_root) / slug
    if pdir.exists():
        raise ValueError(f"Project directory already exists: {slug}")

    config = {
        "name": name,
        "description": description,
        "created_at": datetime.now().isoformat(),
        "defaults": defaults or {},
        "instructions": instructions,
        "total_cost": 0.0,
        "generation_count": 0,
    }

    # Create directory structure
    pdir.mkdir(parents=True, exist_ok=True)
    (pdir / "images").mkdir(exist_ok=True)
    (pdir / "prompts").mkdir(exist_ok=True)
    (pdir / "evaluations").mkdir(exist_ok=True)

    # Write project.json
    with open(pdir / "project.json", "w", encoding="utf-8") as f:
        json.dump(config, f, indent=2, ensure_ascii=False)

    config["slug"] = slug
    return config


def load_project(project_root: Path, slug: str) -> dict | None:
    """Load project.json for a given project slug. Returns None if not found."""
    config_path = _projects_dir(project_root) / slug / "project.json"
    if not config_path.exists():
        return None
    try:
        with open(config_path, "r", encoding="utf-8") as f:
            config = json.load(f)
        config["slug"] = slug
        return config
    except (json.JSONDecodeError, IOError):
        return None


def save_project(project_root: Path, slug: str, config: dict) -> None:
    """Write updated project.json."""
    config_path = _projects_dir(project_root) / slug / "project.json"
    # Remove transient 'slug' field before saving
    save_data = {k: v for k, v in config.items() if k != "slug"}
    with open(config_path, "w", encoding="utf-8") as f:
        json.dump(save_data, f, indent=2, ensure_ascii=False)


def get_project_paths(project_root: Path, slug: str) -> tuple[Path, Path, Path]:
    """Return (images_dir, prompts_dir, evaluations_dir) for a project."""
    pdir = _projects_dir(project_root) / slug
    return pdir / "images", pdir / "prompts", pdir / "evaluations"


def get_project_eval_log(project_root: Path, slug: str) -> Path:
    """Return path to project-specific evaluation log."""
    return _projects_dir(project_root) / slug / "evaluations" / "evaluation_log.json"


def increment_project_stats(project_root: Path, slug: str, cost: float) -> None:
    """Increment generation count and add cost to project total."""
    config = load_project(project_root, slug)
    if not config:
        return
    config["total_cost"] = config.get("total_cost", 0.0) + cost
    config["generation_count"] = config.get("generation_count", 0) + 1
    save_project(project_root, slug, config)


def get_project_display_name(config: dict) -> str:
    """Format project name for display in menus."""
    name = config.get("name", config.get("slug", "Unknown"))
    count = config.get("generation_count", 0)
    cost = config.get("total_cost", 0.0)
    return f"{name} ({count} images, ${cost:.2f})"
