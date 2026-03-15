#!/usr/bin/env python3
"""
Kie.ai Image Generation Studio
Interactive terminal agent for generating images via Kie.ai API.
Supports 5 models: Nano Banana 2, NB Pro, Seedream 4.0, Seedream 4.5, Flux 2 Pro.
"""

import os
import re
import sys
import json
import time
import subprocess
from datetime import datetime
from pathlib import Path

import requests

from image_cache import get_cached_url, store_cache_entry, get_cache_stats, clear_cache
from projects import (
    list_projects, create_project, load_project, save_project,
    get_project_paths, get_project_eval_log, increment_project_stats,
    get_project_display_name, slugify,
)
from description_enhancer import enhance_description
from prompt_history import scan_prompts, filter_by_tags, get_all_tags, format_entry_label, entry_to_settings
from prompt_fitter import fit_prompt
from feedback_learner import (
    compute_preferences, load_preferences,
    get_model_recommendation, get_enhance_recommendation,
    get_negative_warnings, get_not_ready_message,
)

try:
    import questionary
    from questionary import Style as QStyle
    HAS_QUESTIONARY = True
except ImportError:
    HAS_QUESTIONARY = False

try:
    from rich.console import Console
    from rich.panel import Panel
    from rich.text import Text
    from rich.table import Table
    from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn, TimeElapsedColumn
    from rich.syntax import Syntax
    from rich.rule import Rule
    from rich.columns import Columns
    from rich import box
    HAS_RICH = True
except ImportError:
    HAS_RICH = False
    print("Install rich for better UI: pip install rich questionary")

# ── Constants ────────────────────────────────────────────────────────────────

PROJECT_ROOT = Path(__file__).parent
IMAGES_DIR = PROJECT_ROOT / "images"
PROMPTS_DIR = PROJECT_ROOT / "prompts"
ENV_PATH = PROJECT_ROOT / ".env"
LAST_USED_PATH = PROJECT_ROOT / "last_used.json"
API_URL = "https://api.kie.ai/api/v1/jobs/createTask"
POLL_URL = "https://api.kie.ai/api/v1/jobs/recordInfo"
PROMPT_CHAR_LIMIT = 20000  # NB2/Pro/Edit support up to 20K chars
UPLOAD_URL = "https://kieai.redpandaai.co/api/file-stream-upload"
EVALUATIONS_DIR = PROJECT_ROOT / "evaluations"
EVALUATION_LOG = EVALUATIONS_DIR / "evaluation_log.json"

RATING_CHOICES = [
    "5 — Perfect",
    "4 — Good",
    "3 — Okay",
    "2 — Poor",
    "1 — Terrible",
    "Skip evaluation",
]

CATEGORY_DESCRIPTIONS = {
    "portrait": "People, faces, headshots, character studies",
    "product": "Product photography, e-commerce, mockups",
    "landscape": "Nature, scenery, wide environmental shots",
    "architecture-exterior": "Building facades, site context, urban photography",
    "architecture-interior": "Room volumes, material showcase, interior design",
    "architecture-detail": "Materials, joints, textures, construction details",
    "scene": "Environmental storytelling, cinematic setups",
    "miscellaneous": "Everything else — infographics, abstract, mixed",
}

TOP_LEVEL_ACTIONS = [
    "Generate an image",
    "Select / Create project",
    "Browse prompt history",
    "View evaluation history",
    "Manage image cache",
    "Help / How to use",
    "Quit",
]

MODELS = {
    "Nano Banana 2  — Realism, fast, 14 refs ($0.04/1K)":          "nano-banana-2",
    "Nano Banana Pro — Max quality, typography ($0.09/1K)":         "nano-banana-pro",
    "Seedream 4.0   — Budget quality, 10 refs ($0.025)":           "bytedance/seedream-v4-text-to-image",
    "Seedream 4.5   — Best value, 2K/3K, spatial ($0.032)":        "seedream/4.5-text-to-image",
    "Flux 2 Pro     — Detail, consistency, max 2K ($0.025/1K)":    "flux-2/pro-text-to-image",
}

MODEL_DETAILS = {
    "nano-banana-2": {
        "name": "Nano Banana 2",
        "engine": "Gemini 3.1 Flash",
        "speed": "Fast (15-30s)",
        "price": {"1K": 0.025, "2K": 0.04, "4K": 0.06},
        "best_for": "General realism, portraits, landscapes, multi-reference compositions",
        "tip": "Best all-rounder. Handles 5+ simultaneous constraints well. Use for most tasks.",
    },
    "nano-banana-pro": {
        "name": "Nano Banana Pro",
        "engine": "Gemini 3.0 Pro",
        "speed": "Slow (60-120s)",
        "price": {"1K": 0.04},
        "best_for": "Precise typography, logos, complex multi-constraint scenes, maximum fidelity",
        "tip": "Use when you need exact text rendering or maximum fidelity. 1K only.",
    },
    "bytedance/seedream-v4-text-to-image": {
        "name": "Seedream 4.0",
        "engine": "ByteDance",
        "speed": "Medium (20-40s)",
        "price": {"1K": 0.025, "2K": 0.025, "4K": 0.025},
        "best_for": "Budget-friendly quality, high-volume generation, strong color accuracy",
        "tip": "Cheapest option with solid quality. Good for high-volume work.",
    },
    "seedream/4.5-text-to-image": {
        "name": "Seedream 4.5",
        "engine": "ByteDance",
        "speed": "Medium (20-40s)",
        "price": {"2K": 0.032, "3K": 0.032},
        "best_for": "Best value, 2K/3K output, spatial understanding, text rendering",
        "tip": "Max 3K (quality='high'). 3K prompt limit. Better spatial layouts than 4.0.",
    },
    "flux-2/pro-text-to-image": {
        "name": "Flux 2 Pro",
        "engine": "Black Forest Labs",
        "speed": "Medium (20-40s)",
        "price": {"1K": 0.025, "2K": 0.025},
        "best_for": "Fine detail, character consistency, stylized outputs, artistic work",
        "tip": "Max 2K resolution. Strong at maintaining character identity.",
    },
}

def estimate_cost(model, resolution):
    """Return estimated cost in USD or None if unavailable."""
    detail = MODEL_DETAILS.get(model)
    if not detail:
        return None
    return detail["price"].get(resolution)


def load_last_used() -> dict:
    """Load last-used settings per category. Returns {category: {settings}}."""
    if not LAST_USED_PATH.exists():
        return {}
    try:
        with open(LAST_USED_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, IOError):
        return {}


def save_last_used(category, settings):
    """Save settings for a category to last_used.json."""
    data = load_last_used()
    data[category] = settings
    try:
        with open(LAST_USED_PATH, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
    except IOError:
        pass


# Max reference images per model
MODEL_MAX_REFS = {
    "nano-banana-2": 14,
    "nano-banana-pro": 8,
    "bytedance/seedream-v4-text-to-image": 10,
    "seedream/4.5-text-to-image": 10,
    "flux-2/pro-text-to-image": 8,
}

# For edit/img2img modes, some models have separate edit variants
# Edit variants: models that need a DIFFERENT model ID for edit/remix mode.
# NB2 is NOT listed here — it handles edits natively via image_input param,
# preserving resolution, negative_prompt, and output_format support.
MODEL_EDIT_VARIANTS = {
    "bytedance/seedream-v4-text-to-image": "bytedance/seedream-v4-edit",
    "seedream/4.5-text-to-image": "seedream/4.5-edit",
    "flux-2/pro-text-to-image": "flux-2/pro-image-to-image",
}

# Per-model prompt character limits (verified from kie.ai playground maxLength values)
# NB family: 20,000 | Seedream 4.0: 5,000 | Seedream 4.5: 3,000 | Flux 2 Pro: 5,000
MODEL_PROMPT_LIMITS = {
    "nano-banana-2": 20000,
    "nano-banana-pro": 20000,
    "google/nano-banana-edit": 20000,
    "bytedance/seedream-v4-text-to-image": 5000,
    "bytedance/seedream-v4-edit": 5000,
    "seedream/4.5-text-to-image": 3000,
    "seedream/4.5-edit": 3000,
    "flux-2/pro-text-to-image": 5000,
    "flux-2/pro-image-to-image": 5000,
}

# Seedream 4.0 uses image_size instead of aspect_ratio
SEEDREAM_V4_SIZE_MAP = {
    "1:1": "square_hd",
    "16:9": "landscape_16_9",
    "9:16": "portrait_16_9",
    "4:3": "landscape_4_3",
    "3:4": "portrait_4_3",
    "3:2": "landscape_4_3",
    "2:3": "portrait_4_3",
    "4:5": "portrait_4_3",
    "21:9": "landscape_16_9",
}

RESOLUTIONS = ["1K", "2K", "4K"]

ASPECT_RATIOS = [
    "1:1  — Square",
    "16:9 — Landscape (YouTube, wallpaper)",
    "9:16 — Portrait (Reels, Stories)",
    "4:5  — Instagram Portrait",
    "3:4  — Portrait",
    "3:2  — Standard Landscape",
    "2:3  — Standard Portrait",
    "4:3  — Classic Widescreen",
    "21:9 — Cinematic Ultrawide",
    "auto — Let the model decide",
]

CATEGORIES = [
    "portrait",
    "product",
    "landscape",
    "architecture-exterior",
    "architecture-interior",
    "architecture-detail",
    "scene",
    "miscellaneous",
]

# Map sub-categories to save directories (each gets its own folder)
CATEGORY_SAVE_DIR = {
    # Architecture sub-categories save to their own directories
    # e.g. /images/architecture-exterior/, /prompts/architecture-exterior/
}

STYLE_PRESETS = [
    "photorealistic",
    "artistic",
    "documentary",
    "editorial",
    "product mockup",
    "custom",
]

# ── Image Modes ──────────────────────────────────────────────────────────────

IMAGE_MODES = [
    "Generate         — Create from scratch",
    "Edit             — Modify an existing image",
    "Style Transfer   — Apply reference style to new scene",
    "Remix            — Create variation of existing image",
    "Consistency      — Same subject, new scene",
]

IMAGE_MODE_KEYS = {
    "Generate         — Create from scratch": "generate",
    "Edit             — Modify an existing image": "edit",
    "Style Transfer   — Apply reference style to new scene": "style_transfer",
    "Remix            — Create variation of existing image": "remix",
    "Consistency      — Same subject, new scene": "consistency",
}

EDIT_OPERATIONS = [
    "Convert 3D render to photorealistic",
    "Adjust mood / atmosphere",
    "Add or remove elements",
    "Change colors / grading",
    "Change background",
    "Modify subject details",
    "Transform artistic style",
    "Custom edit instructions",
]

EDIT_OPERATION_KEYS = {
    "Convert 3D render to photorealistic": "render_to_photo",
    "Adjust mood / atmosphere": "mood",
    "Add or remove elements": "elements",
    "Change colors / grading": "colors",
    "Change background": "background",
    "Modify subject details": "subject",
    "Transform artistic style": "style",
    "Custom edit instructions": "custom",
}

ARCH_SUB_TYPES = [
    "architecture-exterior",
    "architecture-interior",
    "architecture-detail",
]

# ── Enhancement Levels ───────────────────────────────────────────────────────

ENHANCE_LEVELS = [
    "Director's Cut — Full cinematic enhancement",
    "Standard       — Solid professional output",
    "Minimal        — Your prompt + essentials only",
]

ENHANCE_LEVEL_KEYS = {
    "Director's Cut — Full cinematic enhancement": "directors_cut",
    "Standard       — Solid professional output": "standard",
    "Minimal        — Your prompt + essentials only": "minimal",
}

QUESTIONARY_STYLE = QStyle([
    ("qmark", "fg:#F5A623 bold"),
    ("question", "bold"),
    ("answer", "fg:#F5A623 bold"),
    ("pointer", "fg:#F5A623 bold"),
    ("highlighted", "fg:#F5A623 bold"),
    ("selected", "fg:#F5A623"),
    ("separator", "fg:#6C6C6C"),
    ("instruction", "fg:#6C6C6C"),
]) if HAS_QUESTIONARY else None

# ── Console ───────────────────────────────────────────────────────────────────

console = Console() if HAS_RICH else None

BANNER_ART = r"""
[bold yellow]    ██╗  ██╗██╗███████╗   [bold cyan]  █████╗ ██╗[/bold cyan]
[bold yellow]    ██║ ██╔╝██║██╔════╝   [bold cyan] ██╔══██╗██║[/bold cyan]
[bold yellow]    █████╔╝ ██║█████╗     [bold cyan] ███████║██║[/bold cyan]
[bold yellow]    ██╔═██╗ ██║██╔══╝     [bold cyan] ██╔══██║██║[/bold cyan]
[bold yellow]    ██║  ██╗██║███████╗   [bold cyan] ██║  ██║██║[/bold cyan]
[bold yellow]    ╚═╝  ╚═╝╚═╝╚══════╝   [bold cyan] ╚═╝  ╚═╝╚═╝[/bold cyan]
[dim]─────────────────────────────────────────[/dim]
[bold white]       I M A G E   S T U D I O[/bold white]

[dim]  5 models  ·  5 modes  ·  12-layer prompts[/dim]
[dim]  NB2 · NB Pro · Seedream · Flux · more[/dim]"""

def print_header():
    if HAS_RICH:
        console.print(Panel(
            BANNER_ART,
            border_style="yellow",
            padding=(1, 4),
            subtitle="[dim]v3.0  ·  powered by kie.ai[/dim]",
            subtitle_align="right",
        ))
        console.print()
    else:
        print("\n=== KIE.AI IMAGE STUDIO v3.0 ===\n")

def cprint(msg, style=""):
    if HAS_RICH:
        console.print(msg, style=style)
    else:
        print(msg)

def rule(title=""):
    if HAS_RICH:
        console.print(Rule(title, style="yellow"))
    else:
        print(f"\n── {title} ──" if title else "\n────────────────")

# ── Help ──────────────────────────────────────────────────────────────────────

def show_help():
    """Display comprehensive help guide for the Kie.ai Image Studio agent."""
    if HAS_RICH:
        console.print()
        # ── Overview ──
        console.print(Panel(
            "[bold]Interactive terminal agent for generating professional images "
            "via Kie.ai API.[/bold]\n\n"
            "Supports [cyan]5 generation modes[/cyan], [cyan]5 models[/cyan], "
            "[cyan]8 categories[/cyan], and a [cyan]12-layer prompt enhancement engine[/cyan] "
            "that transforms simple descriptions into professional-grade cinematic narratives.\n\n"
            "Your input prompt is always enhanced — the engine adds composition, atmosphere, "
            "depth, lighting, camera math, micro-details, quality directives, and negative "
            "prompt stacks automatically.",
            title="[bold yellow]KIE.AI IMAGE STUDIO v3.0[/bold yellow]",
            border_style="yellow",
        ))

        # ── Image Modes ──
        modes_table = Table(title="Image Modes", box=box.ROUNDED, border_style="cyan")
        modes_table.add_column("Mode", style="bold cyan", width=16)
        modes_table.add_column("Description", width=50)
        modes_table.add_column("Images", style="dim", width=12)
        modes_table.add_row("Generate", "Create an image from scratch using text description", "Optional")
        modes_table.add_row("Edit", "Modify mood, elements, colors, background, subject, or style", "Required 1+")
        modes_table.add_row("Style Transfer", "Apply a reference image's style to a new scene", "Required 1+")
        modes_table.add_row("Remix", "Create a variation of an existing image", "Required 1+")
        modes_table.add_row("Consistency", "Same subject in a new scene (3-5 refs recommended)", "Required 1+")
        console.print(modes_table)

        # ── Enhancement Levels ──
        enhance_table = Table(title="Enhancement Levels", box=box.ROUNDED, border_style="magenta")
        enhance_table.add_column("Level", style="bold magenta", width=16)
        enhance_table.add_column("Layers Applied", width=40)
        enhance_table.add_column("Best For", width=30)
        enhance_table.add_row("Director's Cut", "All 12 layers (composition, atmosphere,\ndepth, lighting, camera, micro-details,\nquality, inline negatives)", "Maximum quality output")
        enhance_table.add_row("Standard", "Shot type, description, lighting,\ncamera, quality, negatives", "Solid professional results")
        enhance_table.add_row("Minimal", "Shot type, description, camera,\nnegatives only", "Fast iteration, custom prompts")
        console.print(enhance_table)

        # ── Model Comparison ──
        model_table = Table(title="Model Comparison", box=box.ROUNDED, border_style="green")
        model_table.add_column("Model", style="bold green", width=18)
        model_table.add_column("Speed", width=14)
        model_table.add_column("Refs", width=5, justify="center")
        model_table.add_column("Price", width=16)
        model_table.add_column("Best For", width=40)
        for model_id, detail in MODEL_DETAILS.items():
            prices = detail["price"]
            price_str = " / ".join(f"${v:.3f}/{k}" for k, v in prices.items())
            model_table.add_row(
                detail["name"], detail["speed"],
                str(MODEL_MAX_REFS.get(model_id, "?")),
                price_str, detail["best_for"],
            )
        console.print(model_table)

        # ── Categories ──
        cat_table = Table(title="Image Categories", box=box.ROUNDED, border_style="blue")
        cat_table.add_column("Category", style="bold blue", width=22)
        cat_table.add_column("Description", width=50)
        for cat, desc in CATEGORY_DESCRIPTIONS.items():
            cat_table.add_row(cat, desc)
        console.print(cat_table)

        # ── Best Practices ──
        tips = (
            "[bold]Prompting Tips (from research):[/bold]\n\n"
            "  [yellow]1.[/yellow] Write [bold]narrative paragraphs[/bold], not keyword lists — "
            "increases quality 3.2x\n"
            "  [yellow]2.[/yellow] Include [bold]camera math[/bold] in your description "
            "(e.g., '85mm, f/1.8, ISO 200') — the engine adds this automatically,\n"
            "       but you can override with your own specs\n"
            "  [yellow]3.[/yellow] [bold]The Noise Trap:[/bold] Keep ISO under 800 for realism — "
            "high ISO in complex scenes triggers the model's\n"
            "       illustration biases. Rely on subject imperfections (pores, asymmetry) "
            "not camera noise\n"
            "  [yellow]4.[/yellow] [bold]Inline negative commands[/bold] in your description "
            "('Do not smooth skin') work better than separate negatives\n"
            "  [yellow]5.[/yellow] For [bold]consistency mode:[/bold] provide 3-5 reference angles. "
            "State 'maintain exact facial structure' in description\n"
            "  [yellow]6.[/yellow] For [bold]style transfer:[/bold] 1-2 style reference images work best — "
            "the model copies style/lighting, not content\n"
            "  [yellow]7.[/yellow] Use [bold]Nano Banana Pro[/bold] for precise typography, logos, "
            "and complex text rendering\n"
            "  [yellow]8.[/yellow] For [bold]architecture:[/bold] the engine automatically adds "
            "tilt-shift lens correction, anti-CGI negatives, and\n"
            "       construction-grade material descriptions\n"
            "  [yellow]9.[/yellow] [bold]Describe imperfections explicitly[/bold] — 'visible pores, "
            "mild redness, subtle freckles' beats 'realistic'\n"
            "  [yellow]10.[/yellow] [bold]Rate your results[/bold] — the evaluation system helps track "
            "what works and what doesn't"
        )
        console.print(Panel(tips, border_style="yellow", title="[yellow]Best Practices[/yellow]"))

        # ── Navigation ──
        nav = (
            "[bold]Menu Flow:[/bold]\n"
            "  Main Menu -> Image Mode -> Settings (model, resolution, aspect, format)\n"
            "  -> Enhancement Level -> Category & Style -> Description -> Images\n"
            "  -> Prompt Preview -> Cost Estimate -> Generate -> Evaluate Result\n\n"
            "[bold]Controls:[/bold]\n"
            "  [dim]Ctrl+C[/dim]  Exit at any time\n"
            "  [dim]Arrow keys[/dim]  Navigate menus\n"
            "  [dim]Enter[/dim]  Confirm selection"
        )
        console.print(Panel(nav, border_style="dim", title="[dim]Navigation[/dim]"))
        console.print()
    else:
        # Plain text fallback
        print("\n=== KIE.AI IMAGE STUDIO v3.0 — HELP ===\n")
        print("Interactive terminal agent for generating professional images via Kie.ai API.")
        print("Supports 5 modes, 5 models, 8 categories, 12-layer prompt enhancement.\n")
        print("IMAGE MODES:")
        print("  Generate        — Create from scratch (images optional)")
        print("  Edit            — Modify existing image (requires 1+ images)")
        print("  Style Transfer  — Apply reference style to new scene (requires 1+ images)")
        print("  Remix           — Create variation of existing image (requires 1+ images)")
        print("  Consistency     — Same subject, new scene (requires 1+ images, 3-5 recommended)\n")
        print("ENHANCEMENT LEVELS:")
        print("  Director's Cut  — All 12 layers, maximum quality")
        print("  Standard        — 6 layers, solid professional results")
        print("  Minimal         — 4 layers, fast iteration\n")
        print("MODELS:")
        for model_id, detail in MODEL_DETAILS.items():
            print(f"  {detail['name']:20s} {detail['speed']:16s} {detail['best_for']}")
        print("\nCATEGORIES:")
        for cat, desc in CATEGORY_DESCRIPTIONS.items():
            print(f"  {cat:24s} {desc}")
        print("\nTIPS:")
        print("  - Write narrative paragraphs, not keyword lists")
        print("  - Keep ISO under 800 for realism (The Noise Trap)")
        print("  - Use inline negative commands ('Do not smooth skin')")
        print("  - For consistency: provide 3-5 reference angles")
        print("  - For typography: use Nano Banana Pro model")
        print("  - Rate your results to track what works\n")
        print("CONTROLS: Ctrl+C to exit, Arrow keys to navigate, Enter to confirm\n")


# ── API ───────────────────────────────────────────────────────────────────────

def _read_env_key() -> str | None:
    """Read KIE_API_KEY from environment variable or .env file. Returns None if not found."""
    # Environment variable takes priority (supports containers / CI)
    key = os.environ.get("KIE_API_KEY")
    if key:
        return key.strip()
    # Fall back to .env file
    if not ENV_PATH.exists():
        return None
    with open(ENV_PATH) as f:
        for line in f:
            if line.startswith("KIE_API_KEY="):
                return line.strip().split("=", 1)[1].strip("\"'")
    return None


def _run_setup_wizard() -> str:
    """Interactive first-run wizard that guides the user through API key setup."""
    console.print() if HAS_RICH else print()

    # ── Welcome ──
    if HAS_RICH:
        console.print(Panel(
            "[bold]Welcome to Kie.ai Image Studio![/bold]\n\n"
            "Generate professional AI images with 5 models, a 12-layer prompt\n"
            "enhancement engine, customer projects, and more.\n\n"
            "To get started you need a [cyan]Kie.ai API key[/cyan] (free to create).",
            border_style="yellow",
            title="[bold yellow]First-Time Setup[/bold yellow]",
        ))
    else:
        print("=" * 50)
        print("  Welcome to Kie.ai Image Studio!")
        print("  First-Time Setup")
        print("=" * 50)
        print("\nTo get started you need a Kie.ai API key (free to create).\n")

    # ── Instructions ──
    if HAS_RICH:
        console.print(Panel(
            "[bold]How to get your API key:[/bold]\n\n"
            "  [yellow]1.[/yellow] Go to [cyan underline]https://kie.ai[/cyan underline] "
            "and create an account (or sign in)\n"
            "  [yellow]2.[/yellow] Navigate to [cyan underline]https://kie.ai/api-key[/cyan underline] "
            "(API Keys page)\n"
            "  [yellow]3.[/yellow] Click [bold]\"Create API Key\"[/bold] and give it a name\n"
            "  [yellow]4.[/yellow] Copy the generated key\n\n"
            "[dim]Docs: https://docs.kie.ai[/dim]",
            border_style="cyan",
        ))
    else:
        print("How to get your API key:")
        print("  1. Go to https://kie.ai and create an account (or sign in)")
        print("  2. Navigate to https://kie.ai/api-key (API Keys page)")
        print("  3. Click 'Create API Key' and give it a name")
        print("  4. Copy the generated key")
        print("\nDocs: https://docs.kie.ai\n")

    # ── Key input loop ──
    while True:
        key = ask_text("Paste your Kie.ai API key").strip()
        if not key:
            cprint("[yellow]No key entered.[/yellow]")
            if not ask_confirm("Try again?", default=True):
                cprint("[dim]You can run the app again when you have your key.[/dim]")
                sys.exit(0)
            continue

        # Validate format — warn but don't reject
        if not re.fullmatch(r"[a-f0-9]{32}", key):
            cprint("[yellow]Note:[/yellow] This doesn't look like a standard Kie.ai key "
                   "(expected 32 hex characters).")
            if not ask_confirm("Use this key anyway?", default=True):
                continue

        # ── Write .env ──
        with open(ENV_PATH, "w") as f:
            f.write(f"KIE_API_KEY={key}\n")

        cprint("[green]API key saved![/green] Stored in [bold].env[/bold] (git-ignored).")
        console.print() if HAS_RICH else print()
        return key


def ensure_api_key(force_setup: bool = False) -> str:
    """Load API key from env/file, or run the setup wizard if not found."""
    if not force_setup:
        key = _read_env_key()
        if key:
            return key
    return _run_setup_wizard()

def upload_local_file(api_key, file_path):
    """Upload a local file to Kie.ai's temporary hosting. Returns public URL."""
    p = Path(file_path).expanduser().resolve()
    if not p.exists():
        cprint(f"[red]ERROR:[/red] File not found: {p}")
        return None
    if not p.suffix.lower() in (".png", ".jpg", ".jpeg", ".webp"):
        cprint(f"[red]ERROR:[/red] Unsupported file type: {p.suffix}. Use PNG, JPG, or WEBP.")
        return None
    # Check image cache first
    cached_url, time_ago = get_cached_url(PROJECT_ROOT, str(p))
    if cached_url:
        cprint(f"[green]Using cached URL[/green] [dim](uploaded {time_ago})[/dim]")
        cprint(f"[dim]{cached_url}[/dim]")
        return cached_url
    cprint(f"[dim]Uploading {p.name} to Kie.ai...[/dim]")
    with open(p, "rb") as f:
        resp = requests.post(
            UPLOAD_URL,
            headers={"Authorization": f"Bearer {api_key}"},
            files={"file": (p.name, f)},
            data={"uploadPath": "images"},
            timeout=60,
        )
    resp.raise_for_status()
    data = resp.json()
    url = (data.get("data") or {}).get("downloadUrl")
    if not url:
        cprint(f"[red]Upload failed:[/red] {json.dumps(data, indent=2)[:300]}")
        return None
    cprint(f"[green]Uploaded:[/green] [dim]{url}[/dim]")
    # Store in cache for reuse (URLs expire in 3 days)
    store_cache_entry(PROJECT_ROOT, str(p), url)
    return url


def resolve_image_input(api_key, raw_input):
    """Resolve user input to a public URL. Uploads local files automatically."""
    raw = raw_input.strip().strip("'\"")
    if raw.startswith(("http://", "https://")):
        return raw
    # Unescape backslash-escaped spaces (from terminal drag-and-drop)
    raw = raw.replace("\\ ", " ")
    # Treat as local file path
    return upload_local_file(api_key, raw)


def create_task(api_key, model, prompt, negative_prompt, aspect_ratio, resolution, output_format, image_urls=None):
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {api_key}",
    }

    # Safety fallback: hard truncate if prompt fitting didn't handle it
    max_len = MODEL_PROMPT_LIMITS.get(model, 3000)  # conservative fallback
    if len(prompt) > max_len:
        prompt = prompt[:max_len]
        cprint(f"[yellow]Warning: Prompt hard-truncated to {max_len} chars "
               f"(fitting should have handled this)[/yellow]")

    inp = {"prompt": prompt}

    if model == "google/nano-banana-edit":
        # NB Edit — uses image_urls, image_size, output_format
        # NB Edit accepts "png" or "jpg" (not "jpeg")
        inp["output_format"] = output_format
        inp["image_size"] = aspect_ratio  # NB Edit accepts aspect ratio string directly
        if image_urls:
            inp["image_urls"] = image_urls
    elif model.startswith("nano-banana"):
        # NB2 / NB Pro — text-to-image with optional reference images
        inp["negative_prompt"] = negative_prompt
        inp["aspect_ratio"] = aspect_ratio
        inp["resolution"] = resolution
        inp["output_format"] = output_format
        inp["google_search"] = False
        if image_urls:
            inp["image_input"] = image_urls
    elif model.startswith("bytedance/seedream-v4"):
        # Seedream 4.0 (t2i + edit)
        inp["image_size"] = SEEDREAM_V4_SIZE_MAP.get(aspect_ratio, "square_hd")
        inp["image_resolution"] = resolution or "1K"
        inp["max_images"] = 1
        if image_urls:
            inp["image_urls"] = image_urls
    elif model.startswith("seedream/4.5"):
        # Seedream 4.5 / V5 Lite (t2i + edit)
        # quality: "basic" = 2K, "high" = 3K (max resolution, no 4K)
        inp["aspect_ratio"] = aspect_ratio
        inp["quality"] = "high" if resolution == "4K" else "basic"
        if image_urls:
            inp["image_urls"] = image_urls
    elif model.startswith("flux-2/"):
        # Flux 2 Pro (t2i + i2i)
        inp["aspect_ratio"] = aspect_ratio
        inp["resolution"] = resolution or "1K"
        if image_urls:
            inp["input_urls"] = image_urls
    else:
        # Fallback — NB2-style
        inp["negative_prompt"] = negative_prompt
        inp["aspect_ratio"] = aspect_ratio
        inp["resolution"] = resolution
        inp["output_format"] = output_format
        if image_urls:
            inp["image_input"] = image_urls

    payload = {"model": model, "input": inp}

    # Debug: show model + prompt length
    cprint(f"[dim]API model: {model} | Prompt: {len(prompt)} chars[/dim]")

    resp = requests.post(API_URL, headers=headers, json=payload, timeout=30)
    resp.raise_for_status()
    data = resp.json()
    task_id = (data.get("data") or {}).get("taskId")
    if not task_id:
        cprint(f"[red]ERROR:[/red] No taskId returned. API response:")
        cprint(f"[dim]{json.dumps(data, indent=2)[:500]}[/dim]")
        sys.exit(1)
    return task_id

def poll_task(api_key, task_id):
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {api_key}",
    }
    consecutive_errors = 0
    max_consecutive_errors = 5
    for attempt in range(90):
        time.sleep(4)
        try:
            resp = requests.get(POLL_URL, headers=headers, params={"taskId": task_id}, timeout=15)
            resp.raise_for_status()
            body = resp.json()
        except Exception as e:
            consecutive_errors += 1
            if consecutive_errors >= max_consecutive_errors:
                cprint(f"[red]ERROR:[/red] {max_consecutive_errors} consecutive network errors. Last: {e}")
                sys.exit(1)
            continue

        consecutive_errors = 0  # reset on successful request

        # Check API-level error code (e.g. 422 "recordInfo is null" = task not found)
        api_code = body.get("code")
        if api_code and api_code != 200:
            api_msg = body.get("msg", "unknown error")
            cprint(f"[red]ERROR:[/red] API error {api_code}: {api_msg}")
            cprint(f"[dim]Task ID: {task_id}[/dim]")
            sys.exit(1)

        data = body.get("data") or {}
        state = data.get("state", "")
        if state in ("success", "completed"):
            result_json = json.loads(data.get("resultJson", "{}"))
            urls = result_json.get("resultUrls", [])
            if urls:
                return urls[0]
            cprint("[red]ERROR:[/red] No result URL in response")
            sys.exit(1)
        elif state in ("failed", "error"):
            cprint(f"[red]ERROR:[/red] Task failed: {json.dumps(data, indent=2)}")
            sys.exit(1)
    cprint("[red]ERROR:[/red] Timed out waiting for generation")
    sys.exit(1)

def download_image(url, dest_path):
    resp = requests.get(url, timeout=60)
    resp.raise_for_status()
    dest_path.parent.mkdir(parents=True, exist_ok=True)
    with open(dest_path, "wb") as f:
        f.write(resp.content)

# ══════════════════════════════════════════════════════════════════════════════
# PROMPT ENHANCEMENT ENGINE
# ══════════════════════════════════════════════════════════════════════════════
#
# Layers (applied in order for "Director's Cut"):
#   1. Mode prefix        — edit/style/remix/consistency framing
#   2. Shot type          — category-specific photographic declaration
#   3. User description   — the raw creative input
#   4. Composition        — professional framing & visual hierarchy
#   5. Atmosphere         — environmental presence & physical air
#   6. Depth layers       — foreground / midground / background separation
#   7. Lighting behavior  — what the light DOES (shadows, specular, temperature)
#   8. Camera math        — optical physics (focal length, aperture, ISO, shutter)
#   9. Micro-details      — forensic-level texture & material specifics
#  10. Quality directives — rendering fidelity & processing rules
#  11. Inline negatives   — imperative "do not" commands inside positive prompt
#  12. Mode negatives     — mode-specific preservation commands
#
# "Standard" applies layers 2,3,7,8,10,11
# "Minimal" applies layers 2,3,8,11

# ── 2. Shot Type Declarations ────────────────────────────────────────────────

CATEGORY_SHOT_TYPES = {
    "portrait":      "Close-up portrait photograph",
    "product":       "Professional product photograph",
    "landscape":     "Wide-angle landscape photograph",
    "scene":         "Cinematic environmental scene photograph",
    "architecture-exterior": "Professional exterior architectural photograph",
    "architecture-interior": "Professional interior architectural photograph",
    "architecture-detail":   "Architectural detail and materiality photograph",
    "miscellaneous": "Photograph",
}

# ── 4. Composition Directives ────────────────────────────────────────────────

COMPOSITION_DIRECTIVES = {
    "portrait": (
        "Subject positioned using the rule of thirds — face at the upper-right "
        "power point, gaze direction creating visual tension toward the opposite "
        "frame edge. Negative space balancing the composition on the gaze side."
    ),
    "product": (
        "Hero product centered with geometric precision, occupying approximately "
        "60% of the frame. Clean negative space surrounding the product on all sides. "
        "Camera angle slightly elevated at 30-45 degrees to reveal dimension and form."
    ),
    "landscape": (
        "Strong foreground anchor element in the lower third — textured rock, "
        "vegetation, or leading line. Horizon placed at the upper or lower third, "
        "never bisecting the frame. Leading lines drawing the viewer's eye from "
        "the immediate foreground through the midground into the vanishing distance."
    ),
    "scene": (
        "Environmental storytelling composition — primary subject placed at one-third "
        "intersection, the surrounding environment filling the remaining frame with "
        "narrative context. Depth created through overlapping planes of foreground "
        "props, midground action, and background atmosphere."
    ),
    "architecture-exterior": (
        "Two-point perspective with corrected verticals — no keystoning or "
        "converging vertical lines. Building facade occupying the primary frame "
        "with deliberate negative space for sky composition. Foreground landscaping "
        "or hardscape providing visual entry into the composition. Two to four "
        "human figures near entrances or pathways for architectural scale reference, "
        "slightly out of focus, contemporary clothing, mid-stride."
    ),
    "architecture-interior": (
        "One-point or two-point perspective from standing eye-height at 1.5 meters, "
        "centered on the primary spatial axis. Vertical lines perfectly corrected. "
        "The composition reveals the full spatial volume — floor to ceiling visible, "
        "walls establishing room geometry. Foreground furniture or material detail "
        "anchoring the immediate plane. View through doorways or windows establishing "
        "spatial continuity beyond the primary room."
    ),
    "architecture-detail": (
        "Tight framing on the material junction, connection, or texture element, "
        "filling 70-80% of the frame. The surrounding architectural context visible "
        "but subordinate — establishing the detail within its spatial relationship "
        "to the whole building. Diagonal composition preferred for material joints "
        "and connection details."
    ),
    "miscellaneous": (
        "Intentional composition with clear visual hierarchy — primary subject "
        "anchored at a focal intersection point, supporting elements arranged "
        "to guide the viewer's eye through the frame."
    ),
}

# ── 5. Atmosphere Amplifiers ─────────────────────────────────────────────────

ATMOSPHERE_AMPLIFIERS = {
    ("portrait", "photorealistic"): (
        "The air between lens and subject carries physical presence — "
        "the faintest atmospheric haze, dust motes suspended in the light path, "
        "a sense of temperature and humidity in the ambient space."
    ),
    ("portrait", "documentary"): (
        "The unfiltered atmosphere of a real moment — environmental context "
        "pressing in from the edges, ambient tension visible in the frame."
    ),
    ("portrait", "editorial"): (
        "Controlled atmospheric clarity — the space between lens and subject "
        "is optically precise, every tonal gradation intentional."
    ),
    ("portrait", "artistic"): (
        "The atmosphere saturated with mood — visible light quality, "
        "tonal drama hanging in the air between subject and lens."
    ),
    ("landscape", "photorealistic"): (
        "Atmospheric perspective deepening the scene — near elements sharp and "
        "color-saturated, middle distance softened by aerial moisture, "
        "far horizon veiled in atmospheric haze with blue-shifted temperature."
    ),
    ("landscape", "documentary"): (
        "True atmospheric conditions — the sky and air as they actually appear, "
        "no enhancement, weather visible in the quality of ambient light."
    ),
    ("landscape", "artistic"): (
        "The atmosphere alive with dramatic energy — clouds in deliberate motion, "
        "light shafts breaking through with theatrical intent, "
        "the landscape breathing with tonal drama."
    ),
    ("scene", "photorealistic"): (
        "The lived-in atmosphere of a real space — ambient warmth, "
        "the imperceptible haze of activity, surfaces carrying the patina "
        "of regular use, the air thick with environmental character."
    ),
    ("scene", "documentary"): (
        "Raw atmospheric truth — competing light temperatures, "
        "the uncontrolled quality of real ambient air, environmental "
        "sounds almost palpable in the visual texture."
    ),
    ("product", "photorealistic"): (
        "Clinical atmospheric clarity — zero haze, zero dust, "
        "the air between lens and product optically invisible, "
        "every surface detail rendered without atmospheric interference."
    ),
    ("product", "product mockup"): (
        "Studio-perfect atmospheric control — hermetically still, "
        "every photon directed with purpose, the product existing "
        "in a vacuum of precise illumination."
    ),
    ("*", "photorealistic"): (
        "Physical atmospheric presence — the scene carries the weight "
        "of real air, real light, real temperature."
    ),
    ("*", "documentary"): (
        "Raw unfiltered atmosphere — the scene feels captured, not created."
    ),
    ("*", "editorial"): (
        "Controlled atmosphere with intentional mood — every element "
        "contributing to a deliberate tonal narrative."
    ),
    ("*", "artistic"): (
        "Expressive atmospheric energy — the scene breathing with "
        "deliberate artistic tension and tonal drama."
    ),
    ("architecture-exterior", "photorealistic"): (
        "The building sits within its atmospheric context — aerial perspective "
        "softening distant urban or landscape elements, the sky carrying real "
        "weather with volumetric cumulus clouds. Atmospheric haze near the "
        "horizon line. Trees and vegetation responding to ambient breeze — "
        "leaves catching light at different angles. Micro-particles of dust "
        "and pollen visible where direct sunlight rakes through the scene."
    ),
    ("architecture-exterior", "editorial"): (
        "Blue hour atmospheric perfection — crystalline air clarity, sky "
        "graduated from deep cobalt zenith to pale lavender at the horizon, "
        "the building's warm interior glow spilling through every window "
        "against the cool twilight exterior."
    ),
    ("architecture-exterior", "documentary"): (
        "Real-site atmosphere — construction dust, surrounding urban context "
        "pressing in, the building existing in its actual environment rather "
        "than an idealized setting. Sky as it actually appears."
    ),
    ("architecture-exterior", "artistic"): (
        "Dramatic atmospheric tension — storm clouds building behind the "
        "structure, a single shaft of golden light breaking through to "
        "illuminate the primary facade, theatrical atmospheric energy."
    ),
    ("architecture-interior", "photorealistic"): (
        "The interior atmosphere alive with inhabitation — dust motes floating "
        "in shafts of window light, the faintest haze where warm light meets "
        "cool shadow, a sense of air temperature conveyed through visual warmth. "
        "Daylight quality visible through windows establishing the time of day "
        "and exterior-interior relationship. The space smells of materials — "
        "fresh timber, polished concrete, leather."
    ),
    ("architecture-interior", "editorial"): (
        "Atmosphere of curated perfection — every surface pristine, air "
        "crystalline and still, the space existing in its most photogenic "
        "possible moment. Styled with a few considered objects adding life."
    ),
    ("architecture-interior", "documentary"): (
        "Raw interior atmosphere — the space before styling, pure architectural "
        "volume and material presence. Unmanipulated light conditions."
    ),
    ("architecture-detail", "photorealistic"): (
        "Micro-atmospheric presence at the material surface — the patina of "
        "time and weather on every joint and edge, moisture patterns where "
        "water has traced paths, dust settling in recessed joints."
    ),
    ("*", "product mockup"): "Hermetically controlled studio atmosphere.",
    ("*", "custom"): "",
}

# ── 6. Depth Layers ──────────────────────────────────────────────────────────

DEPTH_LAYERS = {
    "portrait": (
        "A soft foreground element at the bottom edge of frame — a shoulder, "
        "a hand, a surface — slightly out of focus, establishing the shallow "
        "focal plane. The subject occupies the tack-sharp mid-ground. Behind, "
        "the environment dissolves through progressive bokeh circles into "
        "an abstract backdrop of color and diffused shape."
    ),
    "product": (
        "The product exists on a single precise focal plane — front-to-back "
        "sharpness across the entire object. Background drops cleanly to "
        "pure neutral tone with no distracting elements."
    ),
    "landscape": (
        "Hyper-sharp foreground textures in the immediate plane — individual "
        "material details visible at forensic level. Middle distance with "
        "clearly defined features softened by natural atmospheric perspective. "
        "Far background receding into aerial haze, color temperature cooling "
        "with distance."
    ),
    "scene": (
        "Layered environmental depth — immediate foreground props and surfaces "
        "in sharp detail, subject in the mid-ground focal plane, background "
        "environment softening progressively to provide context without "
        "visual competition."
    ),
    "architecture-exterior": (
        "Sharp foreground landscaping or hardscape in the immediate plane — "
        "individual paving joints, planted vegetation, grass blade texture in "
        "crisp detail. The building facade in the tack-sharp middle ground, "
        "every window mullion, cladding joint, and surface texture fully resolved. "
        "Background context — neighboring structures, distant trees, sky — "
        "softening through natural atmospheric perspective with blue-shifted "
        "color temperature."
    ),
    "architecture-interior": (
        "Foreground material detail — furniture surface grain, flooring texture, "
        "a tactile object — sharp and inviting at the immediate plane. Mid-ground "
        "spatial volume revealing the room's full architecture — walls, openings, "
        "ceiling detail in complete focus. Background depth through doorways, "
        "corridors, and windows establishing spatial continuity and the natural "
        "light source beyond."
    ),
    "architecture-detail": (
        "The detail element in crystalline focus across its entire surface plane, "
        "focus-stacked for front-to-back sharpness. Immediately adjacent "
        "architectural context softening gently to a secondary read. Background "
        "building mass dissolving into abstract form and color."
    ),
    "miscellaneous": (
        "Clear focal plane separation — primary subject sharp, "
        "surrounding context softening naturally with distance."
    ),
}

# ── 8. Camera Mathematics ────────────────────────────────────────────────────

CAMERA_MATH = {
    ("portrait", "photorealistic"): (
        "Shot on a Sony A7 IV, 85mm f/1.8 lens, ISO 200, 1/250s shutter. "
        "Shallow depth of field, natural background bokeh."
    ),
    ("portrait", "documentary"): (
        "Shot on a Canon 5D Mark IV, 35mm f/2.8 lens, ISO 800, 1/60s. "
        "Available light, slight motion in environment, handheld feel."
    ),
    ("portrait", "editorial"): (
        "Shot on a Hasselblad X2D, 80mm f/2.8 lens, ISO 100, 1/200s. "
        "Clean background separation, precisely metered."
    ),
    ("portrait", "artistic"): (
        "Shot with vintage Helios 44-2 58mm f/2 lens on Sony A7III, ISO 400, 1/125s. "
        "Signature swirly bokeh, dreamy optical character, slight vignetting."
    ),
    ("landscape", "photorealistic"): (
        "Shot on a Sony A7R V, 24mm f/8 lens, ISO 100, 1/125s. "
        "Deep focus — infinite depth of field, front to back sharpness."
    ),
    ("landscape", "documentary"): (
        "Shot on a Canon 5D Mark IV, 24mm f/5.6 lens, ISO 400, 1/125s. "
        "Deep focus, available light."
    ),
    ("landscape", "artistic"): (
        "Shot on a Sony A7R V, 16mm f/11 lens, ISO 100, 1/60s. "
        "Maximum depth of field. Foreground and horizon both sharp."
    ),
    ("product", "product mockup"): (
        "Studio macro setup, 90mm tilt-shift lens, f/11, ISO 50, 1/125s. "
        "Focus plane precisely aligned with product face."
    ),
    ("product", "photorealistic"): (
        "Studio setup, 50mm f/8 lens, ISO 100, 1/125s. "
        "Even depth of field across the full product."
    ),
    ("product", "editorial"): (
        "50mm f/5.6 lens, ISO 100, 1/200s. Clean, controlled exposure."
    ),
    ("scene", "photorealistic"): (
        "Shot on a Sony A7 IV, 35mm f/2.8 lens, ISO 400, 1/60s. "
        "Environmental depth of field — subject sharp, background soft."
    ),
    ("scene", "documentary"): (
        "Shot on a Canon 5D Mark IV, 35mm f/5.6 lens, ISO 640, 1/60s. "
        "Deep focus, reportage handheld feel."
    ),
    ("scene", "artistic"): (
        "Shot on a Leica M11, 50mm Summilux f/1.4 wide open, ISO 320, 1/125s. "
        "Signature Leica rendering — micro-contrast, 3D pop, smooth focus falloff."
    ),
    ("*", "photorealistic"): (
        "Shot on a Sony A7 IV, 50mm f/2.8 lens, ISO 200, 1/200s shutter."
    ),
    ("*", "documentary"): (
        "Shot on a Canon 5D Mark IV, 35mm f/5.6 lens, ISO 640, 1/60s. "
        "Available light, reportage feel."
    ),
    ("*", "editorial"): (
        "Shot on a Hasselblad X2D, 80mm f/2.8 lens, ISO 100, 1/200s. "
        "Precisely metered exposure."
    ),
    ("*", "artistic"): (
        "Painterly rendering with selective focus. Expressive tonal depth."
    ),
    # ── Architecture ──────────────────────────────────────────────────────────
    ("architecture-exterior", "photorealistic"): (
        "Shot on a Canon EOS R5, Canon TS-E 24mm f/3.5L II tilt-shift lens, "
        "f/8, ISO 100, 1/125s. Shift applied to correct perspective — perfectly "
        "vertical lines, zero keystoning. Tripod-mounted for maximum sharpness. "
        "Deep focus — building and foreground both tack-sharp."
    ),
    ("architecture-exterior", "editorial"): (
        "Shot on a Phase One IQ4 150MP, Rodenstock 32mm HR Digaron, f/11, "
        "ISO 50, 1/60s. Medium format sensor resolving every material texture "
        "and cladding joint. Tilt-shift corrected verticals. Maximum resolving power."
    ),
    ("architecture-exterior", "documentary"): (
        "Shot on a Canon 5D Mark IV, 24mm f/5.6, ISO 400, 1/250s handheld. "
        "Slight natural perspective convergence left uncorrected for documentary "
        "authenticity. Available light, real conditions."
    ),
    ("architecture-exterior", "artistic"): (
        "Shot on a Sony A7R V, Laowa 14mm f/2.8 Zero-D ultra-wide, ISO 200, "
        "1/60s. Dramatic low-angle perspective exaggeration intentional — "
        "the building towering upward with controlled barrel distortion."
    ),
    ("architecture-interior", "photorealistic"): (
        "Shot on a Sony A7R V, Canon TS-E 17mm f/4L tilt-shift lens, f/8, "
        "ISO 200, 1/30s tripod-mounted. Exposure bracketed — interior and "
        "window views both properly exposed through HDR merge. Perfectly "
        "corrected verticals. Deep focus throughout the spatial volume."
    ),
    ("architecture-interior", "editorial"): (
        "Shot on a Phase One IQ4 150MP, 28mm f/8, ISO 100, 1/15s tripod. "
        "Exposure bracketed for window-interior balance. Corrected verticals. "
        "Medium format resolving every material surface and texture."
    ),
    ("architecture-interior", "documentary"): (
        "Shot on a Canon 5D Mark IV, 24mm f/4, ISO 800, 1/30s handheld. "
        "Available light only, natural exposure with real window blowouts "
        "and shadow crush. Authentic interior conditions."
    ),
    ("architecture-interior", "artistic"): (
        "Shot on a Leica Q3, 28mm Summicron f/1.7 wide open, ISO 400, "
        "1/60s handheld. Selective focus isolating one spatial element "
        "against a soft dissolving room. Signature Leica micro-contrast."
    ),
    ("architecture-detail", "photorealistic"): (
        "Shot on a Sony A7R V, Sony 90mm f/2.8 Macro G OSS, f/5.6, ISO 100, "
        "1/125s tripod-mounted. Focus-stacked — 8 frames merged for front-to-back "
        "sharpness across the entire material surface."
    ),
    ("architecture-detail", "editorial"): (
        "Shot on a Hasselblad X2D 100C, XCD 120mm f/3.5 Macro, f/5.6, ISO 64, "
        "1/200s. Medium format rendering of material texture and tonality."
    ),
    ("*", "product mockup"): (
        "Studio macro setup, 90mm tilt-shift lens, f/11, ISO 50, 1/125s."
    ),
    ("*", "custom"): "",
}

# ── 7. Lighting Behavior ─────────────────────────────────────────────────────

LIGHTING_BEHAVIOR = {
    ("portrait", "photorealistic"): (
        "Warm late-afternoon window light from camera-left, "
        "casting a soft graduated shadow on the right cheek and neck, "
        "creating natural skin-tone warmth on the lit side. "
        "No fill reflector — gentle shadow falloff on the away side. "
        "A single catchlight in each eye reflecting the light source shape."
    ),
    ("portrait", "documentary"): (
        "Harsh overhead fluorescent or single practical light source, "
        "creating strong specular highlights on the forehead and nose bridge, "
        "deep shadows under the eyes and jawline. Uncontrolled, unmodified."
    ),
    ("portrait", "editorial"): (
        "Butterfly lighting from a 60x90cm softbox directly above camera axis, "
        "producing a crisp catchlight in both eyes, minimal shadow under the nose, "
        "and clean even skin illumination."
    ),
    ("portrait", "artistic"): (
        "Dramatic single-source sidelight in the Rembrandt tradition — "
        "a triangular highlight on the shadowed cheek, deep shadows elsewhere, "
        "rich chiaroscuro contrast. The light sculpts the face into three dimensions."
    ),
    ("product", "photorealistic"): (
        "Soft diffused natural light from upper-left at 45 degrees, "
        "controlled specular highlights along material edges, "
        "subtle surface reflections revealing texture and material quality."
    ),
    ("product", "product mockup"): (
        "Three-point studio setup: large octabox key light overhead-left, "
        "white reflector fill from below-right, thin hairlight rim from behind. "
        "Zero harsh shadows, even illumination across all material surfaces."
    ),
    ("product", "editorial"): (
        "High-key studio lighting with a single large diffused overhead source, "
        "clean white background with no shadow spill, "
        "sharp edge definition on all product contours."
    ),
    ("landscape", "photorealistic"): (
        "Golden hour directional sunlight at 15 degrees above the horizon from the right, "
        "long warm shadows stretching diagonally across the foreground, "
        "atmospheric haze softening distant elements, "
        "warm-to-cool color gradient from horizon to zenith."
    ),
    ("landscape", "documentary"): (
        "Flat overcast light with even diffuse illumination, "
        "no harsh shadows, muted naturalistic tones, "
        "true-to-life color temperature."
    ),
    ("landscape", "artistic"): (
        "Dramatic storm light — one shaft of golden sunlight breaking through "
        "heavy clouds, illuminating a single foreground element "
        "while the rest remains in cool shadow."
    ),
    ("scene", "photorealistic"): (
        "Mixed ambient and practical lighting — overhead room light "
        "supplemented by a warm practical source within the frame, "
        "creating realistic dual-tone illumination with natural shadow scatter "
        "and slight color temperature contrast between sources."
    ),
    ("scene", "documentary"): (
        "Available light only, fully uncontrolled. "
        "Multiple competing color temperatures — warm tungsten from lamps, "
        "cool daylight from windows. Realistic interior exposure trade-offs: "
        "near-blown highlights near windows, shadow crush in corners."
    ),
    ("scene", "editorial"): (
        "Clean controlled lighting with intentional atmosphere — "
        "a key source establishing mood, fill keeping shadow detail, "
        "deliberate color palette throughout."
    ),
    ("scene", "artistic"): (
        "Dramatically sculpted environmental light — a single dominant source "
        "carving the space into zones of illumination and shadow, "
        "the subject emerging from darkness into a pool of intentional light."
    ),
    ("*", "photorealistic"): (
        "Natural available light falling physically on the scene, "
        "consistent shadows and highlights. Realistic exposure — "
        "no crushed blacks or blown whites."
    ),
    ("*", "documentary"): (
        "Available light only, fully uncontrolled. "
        "Realistic competing color temperatures, unmodified exposure."
    ),
    ("*", "editorial"): (
        "Controlled intentional lighting — key source establishing mood, "
        "fill preserving shadow detail, deliberate color palette."
    ),
    ("*", "artistic"): (
        "Dramatic expressive lighting with intentional contrast. "
        "Selective emphasis guiding the viewer's eye."
    ),
    # ── Architecture ──────────────────────────────────────────────────────────
    ("architecture-exterior", "photorealistic"): (
        "Golden hour sunlight from camera-left at 15-20 degrees elevation, "
        "raking across the facade to reveal surface texture and depth in every "
        "reveal, recess, and cladding joint. Long warm shadows cast by overhangs, "
        "mullions, and projecting elements creating a three-dimensional reading "
        "of the facade. Sky gradient from warm horizon to cool zenith providing "
        "natural fill on the shadow side of the building. Ground-plane shadows "
        "anchoring the building to its site."
    ),
    ("architecture-exterior", "editorial"): (
        "Blue hour twilight — deep cobalt sky with the building's interior "
        "lighting glowing warm at 2700K through every window, creating the "
        "iconic architectural photography moment where warm interior meets "
        "cool exterior. Building facade illuminated by ambient sky light — "
        "soft, even, shadowless. Exterior landscape fixtures providing accent "
        "pools of warm light at the ground plane."
    ),
    ("architecture-exterior", "documentary"): (
        "Midday overcast light — flat, even illumination revealing the "
        "building's true form without dramatic shadow. Construction-site "
        "conditions, uncontrolled natural light."
    ),
    ("architecture-exterior", "artistic"): (
        "Dramatic storm light — a single shaft of golden sunlight breaking "
        "through heavy dark cloud cover, striking the building's primary "
        "facade while surrounding context remains in moody blue-grey shadow. "
        "Extreme contrast emphasizing the architecture as protagonist."
    ),
    ("architecture-interior", "photorealistic"): (
        "Mixed natural and artificial illumination — cool 5500K daylight "
        "streaming through windows at a raking angle, creating light pools "
        "on floor surfaces and warm wall washes. Interior artificial sources "
        "at 2700-3000K providing warm fill — pendant fixtures, recessed "
        "downlights, indirect cove lighting washing the ceiling. The color "
        "temperature contrast between natural and artificial sources creating "
        "depth and spatial atmosphere. Light falloff from windows establishing "
        "a luminance gradient across the room."
    ),
    ("architecture-interior", "editorial"): (
        "Balanced exposure throughout — supplemental interior lighting bringing "
        "shadow areas within 2 stops of highlights. Window views properly "
        "exposed through HDR blending — exterior landscape visible, not blown "
        "out. Every surface evenly illuminated to showcase materials and "
        "spatial quality. Color temperature precisely controlled at 4000K."
    ),
    ("architecture-interior", "documentary"): (
        "Available light only — uncontrolled real interior conditions. "
        "Multiple competing color temperatures from different sources. "
        "Near-blown window highlights, shadow crush in corners. Real."
    ),
    ("architecture-interior", "artistic"): (
        "Single dramatic light source — a large window or skylight creating "
        "a powerful shaft of light cutting through the space, the rest of "
        "the interior falling into rich shadow. Chiaroscuro volumetric "
        "quality revealing the architecture through light and darkness."
    ),
    ("architecture-detail", "photorealistic"): (
        "Directional side-light raking across the material surface at 30-45 "
        "degrees elevation, revealing every texture, joint line, and surface "
        "imperfection through micro-shadow. The light casting tiny shadows "
        "in surface relief to emphasize tactile material quality."
    ),
    ("architecture-detail", "editorial"): (
        "Even diffused light from a large north-facing window, revealing "
        "true material color and texture without dramatic shadow. "
        "Color-accurate illumination for material specification."
    ),
    ("*", "product mockup"): (
        "Three-point studio setup: octabox key light overhead-left, "
        "white reflector fill from below-right, thin rim light from behind. "
        "Zero harsh shadows, even illumination across all surfaces."
    ),
    ("*", "custom"): "",
}

# ── 9. Micro-Detail Injection ────────────────────────────────────────────────

MICRO_DETAILS = {
    "portrait": (
        "Individual eyelashes distinguishable at their roots, subtle asymmetry "
        "in facial features matching real human variance, natural lip texture "
        "with fine vertical lines and slight moisture sheen on the lower lip, "
        "visible vellus hair catching sidelight along the jawline, iris showing "
        "radial fibers, crypts, and collarette ring, pore texture varying across "
        "facial zones — finer on forehead, more open on nose and cheeks."
    ),
    "product": (
        "Surface micro-texture rendered at forensic detail — thread count visible "
        "in fabrics, wood grain following natural growth rings, microscopic surface "
        "imperfections and tooling marks in metal, natural material color variation "
        "and mottling, light interaction at the micro level — specular micro-highlights, "
        "subsurface scattering in translucent materials, fingerprint oils on glossy surfaces."
    ),
    "landscape": (
        "Individual leaf detail in the near canopy, bark texture showing lichen "
        "colonies and weathering patterns, water surface simultaneously showing "
        "reflection and subsurface transparency, rock faces with geological "
        "stratification and mineral crystal structures visible where fractured, "
        "soil showing organic matter and moisture variation."
    ),
    "scene": (
        "Environmental surface textures at observational detail — wall surfaces "
        "showing paint texture and aging, furniture showing wear patterns where "
        "hands naturally rest, floor surfaces with accumulated character, objects "
        "carrying the evidence of daily use — scuffs, patina, fingerprints, "
        "dust settling in crevices and corners."
    ),
    "architecture-exterior": (
        "Building material surfaces rendered at forensic construction detail — "
        "concrete showing formwork imprints, aggregate exposure, and hairline "
        "cracking with water staining at drip edges. Brick showing mortar joint "
        "variation, color mottling between individual units, and efflorescence. "
        "Curtain wall glass reflecting sky and surroundings with accurate Fresnel "
        "distortion varying by viewing angle. Metal cladding showing fastener "
        "heads, panel joints, and anodized finish variation. Window frames with "
        "gasket details and sealant lines. Vegetation: individual leaf shapes "
        "identifiable by species — Betula, Quercus, Acer — bark texture on "
        "trunks, grass blade variation, planted beds showing soil and mulch. "
        "Hardscape: paving joints, expansion gaps, tactile warning strips."
    ),
    "architecture-interior": (
        "Material surfaces at intimate viewing distance — wood grain following "
        "natural growth rings with visible ray fleck in quarter-sawn surfaces, "
        "end-grain pattern visible at cut edges. Natural stone showing mineral "
        "veining, fossil inclusions, and crystalline structure catching light. "
        "Fabric upholstery showing weave pattern and pile direction. Metal "
        "hardware showing machined precision, brushed or satin finish direction. "
        "Grout lines in tilework with natural thickness variation. Floor surfaces "
        "showing reflection gradient, micro-texture, and wear patterns where "
        "foot traffic concentrates. Ceiling: recessed fixture trims, sprinkler "
        "heads, HVAC diffuser grilles — the infrastructure of real buildings."
    ),
    "architecture-detail": (
        "Material surface at near-macro resolution — individual aggregate "
        "particles visible in exposed concrete, wood grain fibers at their "
        "cellular level, crystalline mineral structure in natural stone slabs, "
        "weld bead profiles in steel connections, surface coating thickness "
        "variation and orange-peel texture, patina development patterns on "
        "copper and bronze, weathering erosion at exposed edges and drip lines, "
        "sealant joints showing proper tooling profiles, bolt head torque "
        "marks on structural connections."
    ),
    "miscellaneous": (
        "Primary surfaces rendered with physically accurate micro-texture — "
        "material grain, surface imperfections, natural variation in color and finish."
    ),
}

# ── 9b. Architectural Precision Preservation ─────────────────────────────────
# Injected for ALL architecture categories to enforce measurement-level fidelity.

ARCH_PRECISION_DIRECTIVES = {
    "architecture-exterior": (
        "NANO-PRECISION MANDATE: Preserve every architectural element from the "
        "source at measurement-grade fidelity with zero tolerance for deviation. "
        "Every window count, floor count, facade proportion, setback, overhang "
        "depth, mullion spacing, and structural rhythm must match the original "
        "exactly — do not add, remove, merge, reposition, or alter the scale of "
        "any building element. Maintain exact height proportions between floors, "
        "parapets, sills, lintels, and roof features — if a floor is 3.2m "
        "floor-to-floor, that ratio must hold against all adjacent floors. If "
        "specific dimensions are stated (e.g. chimney height 23m, building width "
        "15m), those proportions must be metrically accurate relative to human "
        "scale (1.75m average height). Window-to-wall ratios must be preserved "
        "per facade — count every opening, maintain exact spacing intervals. "
        "Roof pitch angles, eave overhangs, parapet heights, and cornice "
        "projections must maintain their exact angular and dimensional "
        "relationships. Placed elements (vehicles, signage, street furniture, "
        "infrastructure) must sit precisely on their correct surfaces — wheels "
        "on road, rails embedded in tracks, signs on poles, benches on paving. "
        "No floating objects, no misaligned placements, no elements hovering "
        "above or sinking below their contact surfaces. Respect the existing "
        "spatial geometry with surveyor-grade accuracy: if a tramway runs "
        "left-to-right, the tram rides centered on the tramway, not beside it. "
        "If a sidewalk is 2m wide, pedestrians fit within it. Shadow directions "
        "must be geometrically consistent with the stated sun position — every "
        "shadow angle must agree across the entire scene."
    ),
    "architecture-interior": (
        "NANO-PRECISION MANDATE: Preserve every interior element at measurement-grade "
        "fidelity with zero tolerance for deviation. Ceiling heights, door "
        "proportions (standard 2.1m), window placement, column spacing, beam "
        "depths, and room geometry must match the source exactly — if a room is "
        "4.5m x 6m, that proportion holds. Do not alter wall positions, opening "
        "sizes, structural elements, or ceiling plane heights. Furniture "
        "placement must respect floor plan logic and ergonomic clearances — "
        "items sit flat on floors with visible contact shadows, hang from "
        "walls at correct mounting heights (e.g. art at 1.5m center, switches "
        "at 1.2m), and maintain realistic scale relative to room dimensions. "
        "Light fixtures remain at their exact mounting points — pendants at "
        "stated drop lengths, recessed lights at exact ceiling grid positions. "
        "Material transitions (floor-to-wall, wall-to-ceiling, material-to-material) "
        "preserve exact joint lines, reveal widths, trim profiles, and shadow "
        "gaps from the original. Skirting board heights, architrave widths, and "
        "window sill depths must maintain their millimeter-level proportions. "
        "Reflected ceiling plans must match — every beam line, soffit edge, and "
        "ceiling height change at exact positions."
    ),
    "architecture-detail": (
        "NANO-PRECISION MANDATE: Preserve every construction detail at sub-millimeter "
        "visual fidelity with zero tolerance for simplification. Joint widths "
        "(mortar joints 10mm, expansion joints 20mm), fastener spacing (bolt "
        "patterns, screw intervals), material layer thicknesses, and connection "
        "geometry must match the source exactly. Do not simplify complex "
        "assemblies — every bolt head, weld bead, gasket compression, sealant "
        "line, and washer must be individually resolved at their correct "
        "dimensions. Maintain exact material boundaries where different materials "
        "meet — the shadow gap between cladding panels, the sealant bead at "
        "glass-to-frame junctions, the drip edge profile at flashings. If "
        "specific measurements are referenced, the proportional relationships "
        "must be metrically correct — a 6mm joint must visibly differ from a "
        "10mm joint. Surface textures must be forensically accurate: formwork "
        "board widths in concrete, brick coursing patterns (stretcher, header, "
        "Flemish), stone bedding plane orientation, timber grain direction "
        "following structural span. Fixings must match their specified type — "
        "countersunk vs pan-head, hex vs Torx, exposed vs concealed."
    ),
}

# ── 10. Quality Directives ───────────────────────────────────────────────────

QUALITY_DIRECTIVES = {
    ("portrait", "photorealistic"): (
        "Hyper-realistic, zero post-processing. "
        "Natural micro-textures: visible pores, peach fuzz on the skin surface, "
        "asymmetrical features, slight redness around the nose and cheeks, "
        "natural lip texture with fine lines, unguided hair. "
        "Dynamic range limited — realistic shadow crush and highlight rolloff. "
        "White balance slightly warm. No retouching whatsoever."
    ),
    ("portrait", "documentary"): (
        "Raw, unprocessed skin. Visible sensor grain. "
        "Unmanipulated natural features — blemishes, uneven skin tone, "
        "natural under-eye circles. True-to-life color. No gloss."
    ),
    ("portrait", "editorial"): (
        "Tack sharp skin detail with precise micro-contrast. "
        "Clean but not retouched — pores visible, natural texture preserved. "
        "Magazine-quality composition. Color-graded, naturalistic."
    ),
    ("portrait", "artistic"): (
        "Rich tonal rendering with deliberate contrast. Skin rendered with "
        "painterly quality while maintaining photographic texture. "
        "Color palette driven by artistic intent rather than accuracy."
    ),
    ("product", "photorealistic"): (
        "Crystal-sharp material detail. Physically accurate surface rendering: "
        "visible material grain, natural specular highlights, "
        "realistic depth of material layers. No CGI sheen."
    ),
    ("product", "product mockup"): (
        "Crystal-sharp material detail. Surface texture physically accurate: "
        "subsurface scattering through translucent materials, "
        "specular microglints on hard surfaces, fabric micro-weave visible. "
        "No lens distortion. Shadows only where physically intended."
    ),
    ("product", "editorial"): (
        "Tack sharp, perfectly composed product. "
        "High micro-contrast on material edges. "
        "Clean, intentional negative space."
    ),
    ("landscape", "photorealistic"): (
        "Hyper-realistic natural textures: individual rock surface grain, "
        "foliage micro-detail, water surface caustics and ripple texture, "
        "soil and organic material physically accurate. "
        "Atmospheric haze with true depth. No HDR tone-mapping. "
        "Dynamic range natural — no crushed shadows or blown highlights."
    ),
    ("landscape", "documentary"): (
        "Unmanipulated natural scene. True-to-life colors, "
        "no artificial saturation boost. Candid unposed composition."
    ),
    ("landscape", "artistic"): (
        "Rich tonal palette, expressive composition. "
        "Painterly atmospheric depth. Saturated but not garish."
    ),
    ("scene", "photorealistic"): (
        "Hyper-realistic environmental textures: surface materials, "
        "dust, wear-and-tear on objects, natural depth-of-field falloff. "
        "Dynamic range natural. No post-processing sheen."
    ),
    ("scene", "documentary"): (
        "Raw unprocessed look. Visible grain. True-to-life colors. "
        "Unposed, candid scene energy. No digital processing gloss."
    ),
    ("scene", "editorial"): (
        "Controlled clarity with intentional styling. "
        "High-contrast rendering, precise color grading, editorial polish."
    ),
    ("scene", "artistic"): (
        "Expressive rendering with dramatic tonal range. "
        "Deliberate stylistic choices in color and contrast."
    ),
    ("*", "photorealistic"): (
        "Hyper-realistic, zero post-processing. "
        "Physically accurate textures and materials. "
        "Natural dynamic range. No retouching."
    ),
    ("*", "documentary"): (
        "Raw, unprocessed look. Visible grain. "
        "True-to-life color. Candid energy. No gloss."
    ),
    ("*", "editorial"): (
        "Tack sharp. High micro-contrast. "
        "Color-graded but naturalistic. Magazine-quality output."
    ),
    ("*", "artistic"): (
        "Rich tonal contrast, deliberate stylistic palette. "
        "Expressive composition. Painterly texture in rendering."
    ),
    # ── Architecture ──────────────────────────────────────────────────────────
    ("architecture-exterior", "photorealistic"): (
        "Photorealistic architectural photograph indistinguishable from work "
        "published in ArchDaily, Dezeen, or Architectural Record. Corrected "
        "verticals — zero keystoning. Natural material aging and weathering "
        "visible on all exposed surfaces. Realistic vegetation — multiple "
        "species at varied growth stages, natural growth patterns, seasonal "
        "accuracy. Sky with real cloud formations and atmospheric depth. "
        "Ground plane showing proper shadow contact anchoring the building. "
        "Not a 3D render — a photograph of a real built structure."
    ),
    ("architecture-exterior", "editorial"): (
        "Magazine-cover architectural photography. Perfectly corrected verticals. "
        "Precise exposure and intentional color grading — warm materials "
        "photographed in warm light, cool in cool. Publishable quality in "
        "any international architecture publication. Razor sharp."
    ),
    ("architecture-exterior", "documentary"): (
        "Construction-site documentation quality. Real conditions, no staging. "
        "The building in its actual context. True-to-life exposure."
    ),
    ("architecture-exterior", "artistic"): (
        "Dramatic architectural photography with strong artistic intent. "
        "Bold contrast, expressive composition, the building as sculptural "
        "object in theatrical light. Inspired by Helene Binet."
    ),
    ("architecture-interior", "photorealistic"): (
        "Photorealistic interior photograph as published in Architectural Digest "
        "or Dwell. Balanced exposure — interior spaces and window views both "
        "properly visible. Natural material warmth and texture. Subtly lived-in "
        "with a few considered personal objects adding authenticity — a book, "
        "a coffee cup, draped textile. Corrected verticals. Not a CGI render — "
        "a photograph of a real inhabited space."
    ),
    ("architecture-interior", "editorial"): (
        "Magazine-quality interior photography. Perfectly balanced HDR exposure. "
        "Styled but not over-produced — curated minimalism. Materials "
        "photographed to showcase their character. Precise color accuracy."
    ),
    ("architecture-interior", "documentary"): (
        "Raw interior documentation. Unmanipulated light conditions, "
        "real window exposure trade-offs. The space as-built."
    ),
    ("architecture-interior", "artistic"): (
        "Dramatic interior photography — chiaroscuro light revealing "
        "architectural volume. Moody, atmospheric, the space as experience."
    ),
    ("architecture-detail", "photorealistic"): (
        "Forensic material photography — every surface texture, joint line, "
        "and construction imperfection resolved at near-macro detail. "
        "Focus-stacked for complete front-to-back sharpness. Color accuracy "
        "suitable for material specification and documentation."
    ),
    ("architecture-detail", "editorial"): (
        "Material beauty shot — the texture and tactility of the material "
        "as the subject. Clean, precise, celebrating craft and materiality."
    ),
    ("*", "product mockup"): (
        "Crystal-sharp material detail. Physically accurate surface texture. "
        "No lens distortion. Shadows only where physically intended."
    ),
    ("*", "custom"): "",
}

# ── 11. Inline Negative Commands ─────────────────────────────────────────────

INLINE_NEGATIVES = {
    ("portrait", "photorealistic"): (
        "Do not alter facial proportions or anatomy. "
        "Do not apply beauty filters, skin smoothing, or airbrushing. "
        "Do not idealize or normalize any physical feature. "
        "No makeup styling. No CGI sheen."
    ),
    ("portrait", "documentary"): (
        "No retouching. No beauty filters. No posed arrangement."
    ),
    ("portrait", "editorial"): (
        "No oversaturation. No lens distortion. No digital artifacts."
    ),
    ("portrait", "artistic"): (
        "Do not default to photorealistic rendering. Maintain artistic intent. "
        "No generic AI art style."
    ),
    ("product", "photorealistic"): (
        "No CGI sheen. No fake material rendering. No background clutter."
    ),
    ("product", "product mockup"): (
        "No lens distortion. No color cast. No background clutter. "
        "No shadows outside physical intent."
    ),
    ("landscape", "photorealistic"): (
        "No HDR tone-mapping. No artificial saturation. "
        "No painted or illustrated look. No composite artifacts."
    ),
    ("landscape", "artistic"): (
        "Do not flatten into generic digital painting. Maintain photographic foundation."
    ),
    ("scene", "photorealistic"): (
        "No digital processing sheen. No posed arrangement. "
        "No oversaturated tones."
    ),
    ("scene", "documentary"): (
        "No studio setup. No posed arrangement. No clean digital look. "
        "No artificial color correction."
    ),
    ("*", "documentary"): (
        "No studio setup. No posed arrangement. No clean digital look."
    ),
    ("*", "editorial"): (
        "No oversaturated tones. No lens distortion. No digital compression artifacts."
    ),
    ("architecture-exterior", "photorealistic"): (
        "Do not render as a 3D visualization, CGI, or architectural rendering. "
        "Do not apply uniform or plastic material textures. Do not use perfectly "
        "clean surfaces — include natural weathering, water staining, and aging. "
        "Do not distort perspective or converge vertical lines. Do not use "
        "generic copy-paste vegetation — each tree and plant must be unique. "
        "Do not float the building — it must have ground-contact shadows."
    ),
    ("architecture-exterior", "editorial"): (
        "Do not converge verticals. Do not blow out sky or windows. "
        "No 3D render quality. No generic vegetation."
    ),
    ("architecture-interior", "photorealistic"): (
        "Do not render as a 3D visualization, CGI, or interior rendering. "
        "Do not use uniform lighting — include natural light variation and "
        "shadow gradients. Do not apply plastic or synthetic material textures. "
        "Do not blow out window views — maintain exterior visibility through "
        "HDR-balanced exposure. Do not distort verticals."
    ),
    ("architecture-interior", "editorial"): (
        "Do not blow out windows. Do not converge verticals. "
        "No 3D render quality. No synthetic material textures."
    ),
    ("architecture-detail", "photorealistic"): (
        "Do not smooth or simplify material texture. Do not apply uniform "
        "color to natural materials — include natural variation and mottling. "
        "Do not render as CGI. Preserve all construction imperfections."
    ),
    ("*", "artistic"): "",
    ("*", "custom"): "",
    ("*", "photorealistic"): (
        "No CGI sheen. No artificial processing. No airbrushing."
    ),
}

# ── 12. Mode-Specific Inline Negatives ───────────────────────────────────────

MODE_INLINE_NEGATIVES = {
    "generate": "",
    "edit": (
        "Do not alter any aspect of the image not explicitly mentioned in the "
        "edit instructions. Preserve the original resolution and image quality. "
        "Maintain all unmentioned subjects, objects, and background elements exactly."
    ),
    "style_transfer": (
        "Do not copy the content or subject matter of the reference image — "
        "only replicate its visual style, color palette, and lighting treatment. "
        "The scene content must match the text description, not the reference."
    ),
    "remix": (
        "Maintain the core identity of the subject from the original. "
        "Do not alter fundamental proportions or identity. "
        "Apply modifications naturally, not as obvious overlays."
    ),
    "consistency": (
        "Do not alter the subject's physical features from the reference in any way. "
        "No age regression, no symmetry correction, no feature idealization, "
        "no skin tone shift. The reference images are absolute ground truth."
    ),
}

# ── Mode Prompt Templates ────────────────────────────────────────────────────

MODE_PROMPT_TEMPLATES = {
    "edit": (
        "Using the provided input image as the base, apply the following "
        "modifications while preserving all unmentioned elements exactly "
        "as they appear in the original. "
    ),
    "style_transfer": (
        "Generate a new image matching the scene described below, precisely "
        "replicating the visual style, color palette, lighting mood, contrast "
        "curve, grain structure, and artistic treatment from the provided "
        "reference image. "
    ),
    "remix": (
        "Create a distinct variation of the provided input image. Maintain "
        "the core subject and overall composition while applying the following "
        "modifications. "
    ),
    "consistency": (
        "Generate the scene described below while maintaining exact facial "
        "structure, body proportions, skin tone, hair texture, and all "
        "identifying physical features from the provided reference images. "
        "The reference images are absolute ground truth for the subject's "
        "appearance. "
    ),
}

# ── Edit Operation Prompt Prefixes ───────────────────────────────────────────

EDIT_OPERATION_PROMPTS = {
    "render_to_photo": (
        "Transform this 3D architectural render into a photorealistic photograph. "
        "Replace all CGI artifacts with natural material textures, realistic lighting, "
        "and physical imperfections. Apply natural weathering, aging, and material "
        "variation to all surfaces. "
    ),
    "mood": "Shift the emotional atmosphere and mood of the image — ",
    "elements": "Add or remove the following elements in the scene — ",
    "colors": "Adjust the color grading and palette — ",
    "background": "Replace or modify the background while keeping the subject intact — ",
    "subject": "Modify the following aspects of the subject — ",
    "style": "Transform the artistic style of the image — ",
    "custom": "",
}

RENDER_TO_PHOTO_NEGATIVES = (
    "Do not preserve any CGI rendering artifacts, uniform lighting, or perfect geometry. "
    "Remove all V-Ray, Lumion, SketchUp, Enscape, or Corona rendering signatures. "
    "Replace uniform material textures with natural variation, weathering, and aging. "
    "Do not keep perfectly clean surfaces — add construction imperfections, water staining, "
    "and natural material patina."
)

# ── Negative Prompt Stacks ───────────────────────────────────────────────────

CATEGORY_NEGATIVES = {
    "portrait": (
        "anatomy normalization, body proportion averaging, dataset-average anatomy, "
        "skin smoothing, plastic skin, airbrushed texture, beautification filters, "
        "stylized realism, editorial fashion proportions, depth flattening, "
        "mirror selfies, reflections, more realistic reinterpretation, "
        "extra fingers, extra limbs, distorted face, heavy makeup, unrealistic skin, "
        "lens compression not in reference, wide-angle distortion not in reference, "
        "cropping that removes volume"
    ),
    "product": (
        "lens distortion, color cast, oversaturation, background clutter, "
        "motion blur, CGI render look, plastic texture, fake lighting, "
        "depth of field artifacts, overexposed highlights, underexposed shadows"
    ),
    "landscape": (
        "oversaturated, HDR tone-mapped, painted look, artificial color grading, "
        "lens distortion, excessive vignetting, blown sky highlights, "
        "composite artifacts, watermark"
    ),
    "scene": (
        "anatomy normalization, plastic skin, airbrushed texture, "
        "cartoon, CGI, oversaturated colors, depth flattening, "
        "mirror artifacts, more realistic reinterpretation"
    ),
    "architecture-exterior": (
        "3D render, CGI, visualization, V-Ray, Lumion, SketchUp, Enscape, "
        "converging verticals, keystoning, perspective distortion, "
        "plastic materials, uniform textures, copy-paste vegetation, "
        "generic trees, floating building, missing ground shadows, "
        "oversaturated sky, unrealistic clouds, fish-eye distortion, "
        "barrel distortion, empty site, no people, dead landscape, "
        "altered building proportions, merged windows, missing floors, "
        "repositioned structural elements, floating vehicles, "
        "objects not on their correct surface"
    ),
    "architecture-interior": (
        "3D render, CGI, visualization, V-Ray, Lumion, SketchUp, Enscape, "
        "converging verticals, blown-out windows, white-out windows, "
        "uniform lighting, plastic materials, synthetic textures, "
        "empty lifeless space, oversaturated colors, fish-eye distortion, "
        "barrel distortion, dead flat lighting, no depth, "
        "altered room proportions, moved walls, resized openings, "
        "floating furniture, objects clipping through surfaces"
    ),
    "architecture-detail": (
        "3D render, CGI, smooth surfaces, plastic texture, uniform color, "
        "oversimplified geometry, missing construction joints, "
        "perfect unblemished surface, no material variation, "
        "simplified assemblies, merged fasteners, lost joint lines"
    ),
    "miscellaneous": "",
}

BASE_NEGATIVE_STACK = (
    "blurry, low resolution, distorted, "
    "cartoon, CGI, watermark, text overlay, signature, "
    "overexposed, underexposed"
)

# When user wants text in the image, these terms are stripped from negatives
TEXT_NEGATIVE_CONFLICTS = {"text overlay", "watermark", "signature"}


# ── Prompt Builder ────────────────────────────────────────────────────────────

def _lookup(table, category, style):
    """Look up (category, style) in a dict, falling back to ('*', style) then ''."""
    return table.get((category, style)) or table.get(("*", style)) or ""


def _detect_embedded_text(description):
    """
    Detect if the user's description contains embedded text/captions to render.
    Returns list of quoted strings found, or empty list.
    """
    # Match text in double quotes, single quotes, or after keywords like
    # "caption says", "text reads", "sign says", "title:", "label:"
    quoted = re.findall(r'"([^"]+)"', description)
    quoted += re.findall(r"'([^']{3,})'", description)  # skip short contractions
    return quoted


def _build_text_placement_instructions(description, quoted_texts):
    """
    When embedded text is detected, add explicit rendering constraints
    to prevent duplication and ensure proper placement.
    """
    if not quoted_texts:
        return ""

    # Determine placement from context clues in description
    desc_lower = description.lower()
    if any(kw in desc_lower for kw in ("caption", "meme", "subtitle", "bottom text")):
        placement = "at the bottom of the image"
    elif any(kw in desc_lower for kw in ("title", "heading", "top text", "header")):
        placement = "at the top of the image"
    elif any(kw in desc_lower for kw in ("sign", "neon", "banner", "label", "logo")):
        placement = "on the sign/surface described"
    else:
        placement = "in a single clearly defined location"

    parts = [
        f"Render all text exactly once, {placement}.",
        "Do not duplicate, mirror, or repeat the text anywhere else in the image.",
        "The text must appear in only one location — never render the same text "
        "in multiple positions.",
    ]

    # If text is long, add legibility instruction
    for t in quoted_texts:
        if len(t) > 30:
            parts.append(
                "Use a font size that keeps the full text legible within "
                "the available space. Prefer line breaks over shrinking."
            )
            break

    return " ".join(parts)


def _strip_text_conflicts(negative_stack):
    """Remove negative terms that conflict with intentional text rendering."""
    terms = [t.strip() for t in negative_stack.split(",")]
    filtered = [t for t in terms if t.lower() not in TEXT_NEGATIVE_CONFLICTS]
    return ", ".join(filtered)


def build_prompt(description, category, style, extra_negative="",
                 image_mode="generate", edit_operation=None,
                 enhance_level="directors_cut", project_instructions=""):
    """
    Multi-layer prompt builder.

    Director's Cut: all 12 layers — composition, atmosphere, depth, micro-details
    Standard:       layers 2,3,7,8,10,11 — lighting, camera, quality
    Minimal:        layers 2,3,8,11 — shot type + description + camera + negatives

    Returns:
        (full_prompt, negative_prompt, layer_parts) where layer_parts is a dict
        mapping layer names to their text content for intelligent prompt fitting.
    """
    parts = []
    layer_parts = {}  # Captures each layer's text for prompt fitting

    # ── Detect embedded text in description ──────────────────────────────────
    quoted_texts = _detect_embedded_text(description)
    has_text = bool(quoted_texts)

    # ── Layer 1: Mode prefix (for non-generate modes) ────────────────────────
    if image_mode == "edit":
        op_prompt = EDIT_OPERATION_PROMPTS.get(edit_operation, "")
        layer_parts["mode_prefix"] = MODE_PROMPT_TEMPLATES["edit"] + op_prompt
    elif image_mode in MODE_PROMPT_TEMPLATES:
        layer_parts["mode_prefix"] = MODE_PROMPT_TEMPLATES[image_mode]
    if layer_parts.get("mode_prefix"):
        parts.append(layer_parts["mode_prefix"])

    # Helper: should full enhancement layers apply?
    is_render_convert = (edit_operation == "render_to_photo")
    apply_full_layers = image_mode in ("generate", "consistency") or is_render_convert

    # ── Layer 2: Shot type declaration ───────────────────────────────────────
    if apply_full_layers:
        shot_type = CATEGORY_SHOT_TYPES.get(category, "Photograph")
        layer_parts["shot_type"] = f"{shot_type}."
        parts.append(layer_parts["shot_type"])

    # ── Layer 3: User description ────────────────────────────────────────────
    layer_parts["description"] = description.strip()
    parts.append(layer_parts["description"])

    # ── Layer 3b: Text placement constraints (if text detected) ──────────────
    if has_text:
        text_instructions = _build_text_placement_instructions(description, quoted_texts)
        if text_instructions:
            layer_parts["text_placement"] = text_instructions
            parts.append(text_instructions)

    # ── Layer 3c: Project instructions (if active project) ─────────────────
    if project_instructions:
        layer_parts["project_instructions"] = f"Project context: {project_instructions}"
        parts.append(layer_parts["project_instructions"])

    # ── Layer 4: Composition (Director's Cut only) ───────────────────────────
    if enhance_level == "directors_cut" and apply_full_layers:
        comp = COMPOSITION_DIRECTIVES.get(category, COMPOSITION_DIRECTIVES.get("miscellaneous", ""))
        if comp:
            layer_parts["composition"] = comp
            parts.append(comp)

    # ── Layer 5: Atmosphere (Director's Cut only) ────────────────────────────
    if enhance_level == "directors_cut" and apply_full_layers:
        atmo = _lookup(ATMOSPHERE_AMPLIFIERS, category, style)
        if atmo:
            layer_parts["atmosphere"] = atmo
            parts.append(atmo)

    # ── Layer 6: Depth layers (Director's Cut only) ──────────────────────────
    if enhance_level == "directors_cut" and apply_full_layers:
        depth = DEPTH_LAYERS.get(category, DEPTH_LAYERS.get("miscellaneous", ""))
        if depth:
            layer_parts["depth"] = depth
            parts.append(depth)

    # ── Layer 7: Lighting behavior (Standard+) ───────────────────────────────
    if enhance_level in ("directors_cut", "standard") and apply_full_layers:
        lighting = _lookup(LIGHTING_BEHAVIOR, category, style)
        if lighting:
            layer_parts["lighting"] = lighting
            parts.append(lighting)

    # ── Layer 8: Camera math (all levels, generate/consistency/style_transfer/render) ─
    if image_mode in ("generate", "consistency", "style_transfer") or is_render_convert:
        camera = _lookup(CAMERA_MATH, category, style)
        if camera:
            layer_parts["camera"] = camera
            parts.append(camera)

    # ── Layer 9: Micro-details (Director's Cut only) ─────────────────────────
    if enhance_level == "directors_cut" and apply_full_layers:
        micro = MICRO_DETAILS.get(category, MICRO_DETAILS.get("miscellaneous", ""))
        if micro:
            layer_parts["micro_details"] = micro
            parts.append(micro)

    # ── Layer 9b: Architectural precision (all levels, architecture only) ────
    arch_precision = ARCH_PRECISION_DIRECTIVES.get(category)
    if arch_precision:
        layer_parts["arch_precision"] = arch_precision
        parts.append(arch_precision)

    # ── Layer 10: Quality directives (Standard+) ─────────────────────────────
    if enhance_level in ("directors_cut", "standard"):
        quality = _lookup(QUALITY_DIRECTIVES, category, style)
        if quality:
            layer_parts["quality"] = quality
            parts.append(quality)

    # ── Layer 11: Inline negatives ───────────────────────────────────────────
    inline_neg = _lookup(INLINE_NEGATIVES, category, style)
    if inline_neg:
        layer_parts["inline_negatives"] = inline_neg
        parts.append(inline_neg)

    # ── Layer 11b: Render-to-photo specific negatives ─────────────────────────
    if is_render_convert:
        layer_parts["render_negatives"] = RENDER_TO_PHOTO_NEGATIVES
        parts.append(RENDER_TO_PHOTO_NEGATIVES)

    # ── Layer 12: Mode-specific inline negatives ─────────────────────────────
    mode_neg = MODE_INLINE_NEGATIVES.get(image_mode, "")
    if mode_neg:
        layer_parts["mode_negatives"] = mode_neg
        parts.append(mode_neg)

    full_prompt = " ".join(p for p in parts if p)

    # ── Negative prompt stack ────────────────────────────────────────────────
    neg_parts = [p for p in [
        BASE_NEGATIVE_STACK,
        CATEGORY_NEGATIVES.get(category, ""),
        extra_negative.strip(),
    ] if p]
    negative = ", ".join(neg_parts)

    # Strip conflicting negatives when user wants text in the image
    if has_text:
        negative = _strip_text_conflicts(negative)

    return full_prompt, negative, layer_parts


# ── File I/O ──────────────────────────────────────────────────────────────────

# Stop words and technical terms to strip from filenames
_FILENAME_STOP_WORDS = {
    "a", "an", "the", "in", "on", "at", "with", "of", "for", "is", "are",
    "and", "or", "to", "from", "by", "that", "this", "it", "its", "my",
    "your", "their", "our", "has", "have", "had", "be", "been", "being",
    "was", "were", "will", "would", "could", "should", "may", "might",
    "into", "onto", "about", "through", "during", "before", "after",
    "above", "below", "between", "under", "over", "very", "really",
    "just", "also", "so", "but", "not", "no", "some", "any", "all",
}
_FILENAME_TECH_TERMS = {
    "iso", "lens", "aperture", "shutter", "photograph", "photography",
    "photo", "image", "picture", "shot", "camera", "focal", "bokeh",
    "exposure", "resolution", "megapixel", "tripod", "handheld",
    "professional", "cinematic", "hyper", "ultra", "super", "hd",
    "realistic", "photorealistic", "macro", "tilt", "shift",
}


def generate_filename(description: str, max_words: int = 5) -> str:
    """Extract a short descriptive slug from user's description for file naming.

    'A woman in a red dress on a beach at sunset' -> 'woman-red-dress-beach-sunset'
    """
    if not description:
        return ""
    text = description.lower()
    # Remove punctuation except hyphens
    text = re.sub(r"[^\w\s-]", " ", text)
    words = text.split()
    # Filter stop words and technical terms
    meaningful = [
        w for w in words
        if w not in _FILENAME_STOP_WORDS
        and w not in _FILENAME_TECH_TERMS
        and len(w) > 1
        and not re.match(r"^\d+$", w)  # skip bare numbers
        and not re.match(r"^f\d", w)   # skip f-stops like f1.8
    ]
    # Take first N meaningful words
    slug_words = meaningful[:max_words]
    if not slug_words:
        return ""
    slug = "-".join(slug_words)
    # Clean up: only alphanumeric and hyphens, collapse multiple hyphens
    slug = re.sub(r"[^a-z0-9-]", "", slug)
    slug = re.sub(r"-{2,}", "-", slug).strip("-")
    # Truncate to max 50 chars
    return slug[:50]


def get_output_paths(category, output_format, description="", project_dirs=None):
    """Generate timestamped output paths for image and prompt files.

    Args:
        category: Image category (e.g. 'portrait', 'architecture-exterior')
        output_format: File extension ('jpg' or 'png')
        description: User's raw description for smart filename generation
        project_dirs: Optional (images_dir, prompts_dir) tuple for project-scoped output
    """
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    ext = output_format.lower()
    cat_dir = CATEGORY_SAVE_DIR.get(category, category) if category else "miscellaneous"

    # Generate descriptive slug from description, fallback to category name
    slug = generate_filename(description) if description else ""
    base_name = f"{slug}_{ts}" if slug else f"{cat_dir}_{ts}"

    images_dir = project_dirs[0] if project_dirs else IMAGES_DIR
    prompts_dir = project_dirs[1] if project_dirs else PROMPTS_DIR

    img_path = images_dir / cat_dir / f"{base_name}.{ext}"
    prompt_path = prompts_dir / cat_dir / f"{base_name}.json"
    return img_path, prompt_path

def save_prompt_json(path, model, prompt, negative_prompt, aspect_ratio, resolution,
                     output_format, image_urls, category, style,
                     image_mode="generate", enhance_level="directors_cut",
                     edit_operation=None, tags=None, project=None,
                     original_description="", layers_dropped=None):
    data = {
        "model": model,
        "category": category,
        "style": style,
        "image_mode": image_mode,
        "enhance_level": enhance_level,
        "prompt": prompt,
        "negative_prompt": negative_prompt,
        "api_parameters": {
            "aspect_ratio": aspect_ratio,
            "resolution": resolution,
            "output_format": output_format,
        },
        "image_input": image_urls or [],
        "generated_at": datetime.now().isoformat(),
    }
    if edit_operation:
        data["edit_operation"] = edit_operation
    if tags:
        data["tags"] = tags
    if project:
        data["project"] = project
    if original_description and original_description != prompt:
        data["original_description"] = original_description
    if layers_dropped:
        data["layers_dropped"] = layers_dropped
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)

def open_image(path):
    try:
        if sys.platform == "darwin":
            subprocess.Popen(["open", str(path)])
        elif sys.platform.startswith("linux"):
            subprocess.Popen(["xdg-open", str(path)])
        elif sys.platform == "win32":
            os.startfile(str(path))
    except Exception:
        pass


# ── Evaluation System ────────────────────────────────────────────────────────

def _load_evaluation_log(eval_log_path=None):
    """Load evaluation log, return list of entries."""
    log_path = eval_log_path or EVALUATION_LOG
    if not log_path.exists():
        return []
    try:
        with open(log_path, "r", encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, IOError):
        return []


def _save_evaluation_log(entries, eval_log_path=None):
    """Write full evaluation log array."""
    log_path = eval_log_path or EVALUATION_LOG
    log_path.parent.mkdir(parents=True, exist_ok=True)
    with open(log_path, "w", encoding="utf-8") as f:
        json.dump(entries, f, indent=2, ensure_ascii=False)


def _patch_prompt_json(prompt_path, evaluation):
    """Add evaluation data to an existing prompt JSON file."""
    try:
        with open(prompt_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        data["evaluation"] = evaluation
        with open(prompt_path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
    except Exception:
        pass


def evaluate_image(prompt_path, img_path, model, category, eval_log_path=None):
    """Prompt user to rate a generated image and save the evaluation."""
    rule("EVALUATE")
    rating_label = ask("How did this image turn out?", choices=RATING_CHOICES,
                       default=RATING_CHOICES[0])
    if not rating_label or rating_label == "Skip evaluation":
        cprint("[dim]Evaluation skipped.[/dim]")
        return

    rating = int(rating_label[0])
    notes = ask_text("Any notes? (optional, press Enter to skip)")

    evaluation = {
        "rating": rating,
        "notes": notes or "",
    }

    # Patch prompt JSON with evaluation
    _patch_prompt_json(prompt_path, evaluation)

    # Append to evaluation log (project-scoped if eval_log_path provided)
    entry = {
        "timestamp": datetime.now().isoformat(),
        "rating": rating,
        "notes": notes or "",
        "prompt_file": str(prompt_path.relative_to(PROJECT_ROOT)),
        "image_file": str(img_path.relative_to(PROJECT_ROOT)),
        "model": model,
        "category": category,
    }
    log = _load_evaluation_log(eval_log_path)
    log.append(entry)
    _save_evaluation_log(log, eval_log_path)

    stars = "★" * rating + "☆" * (5 - rating)
    cprint(f"[green]Saved evaluation: {stars}[/green]")


def show_evaluation_stats(eval_log_path=None, title_prefix=""):
    """Display evaluation history and statistics."""
    log = _load_evaluation_log(eval_log_path)

    if not log:
        cprint("[dim]No evaluations yet. Generate some images and rate them![/dim]")
        return

    if HAS_RICH:
        console.print()

        # ── Summary ──
        total = len(log)
        avg = sum(e["rating"] for e in log) / total
        dist = {i: 0 for i in range(1, 6)}
        for e in log:
            dist[e["rating"]] += 1

        summary = Table(title="Evaluation Summary", box=box.ROUNDED, border_style="green")
        summary.add_column("Metric", style="bold")
        summary.add_column("Value", justify="right")
        summary.add_row("Total images rated", str(total))
        summary.add_row("Average rating", f"{avg:.1f} / 5.0")
        for r in range(5, 0, -1):
            bar = "█" * dist[r] + "░" * (max(dist.values()) - dist[r]) if max(dist.values()) > 0 else ""
            summary.add_row(f"{'★' * r}{'☆' * (5-r)}", f"{dist[r]:3d}  {bar}")
        console.print(summary)

        # ── By Model ──
        model_stats = {}
        for e in log:
            m = e.get("model", "unknown")
            model_stats.setdefault(m, []).append(e["rating"])

        mt = Table(title="By Model", box=box.ROUNDED, border_style="cyan")
        mt.add_column("Model", style="bold cyan")
        mt.add_column("Count", justify="right")
        mt.add_column("Avg Rating", justify="right")
        for m, ratings in sorted(model_stats.items()):
            name = MODEL_DETAILS.get(m, {}).get("name", m)
            mt.add_row(name, str(len(ratings)), f"{sum(ratings)/len(ratings):.1f}")
        console.print(mt)

        # ── By Category ──
        cat_stats = {}
        for e in log:
            c = e.get("category", "unknown")
            cat_stats.setdefault(c, []).append(e["rating"])

        ct = Table(title="By Category", box=box.ROUNDED, border_style="blue")
        ct.add_column("Category", style="bold blue")
        ct.add_column("Count", justify="right")
        ct.add_column("Avg Rating", justify="right")
        for c, ratings in sorted(cat_stats.items()):
            ct.add_row(c, str(len(ratings)), f"{sum(ratings)/len(ratings):.1f}")
        console.print(ct)

        # ── Recent ──
        recent = Table(title="Recent Evaluations (last 10)", box=box.ROUNDED, border_style="dim")
        recent.add_column("Date", style="dim", width=12)
        recent.add_column("Rating", width=8)
        recent.add_column("Model", width=18)
        recent.add_column("Category", width=16)
        recent.add_column("Notes", width=30)
        for e in log[-10:]:
            ts = e.get("timestamp", "")[:10]
            stars = "★" * e["rating"] + "☆" * (5 - e["rating"])
            name = MODEL_DETAILS.get(e.get("model", ""), {}).get("name", e.get("model", "?"))
            notes = (e.get("notes", "") or "")[:30]
            recent.add_row(ts, stars, name, e.get("category", "?"), notes)
        console.print(recent)
        console.print()
    else:
        # Plain text fallback
        total = len(log)
        avg = sum(e["rating"] for e in log) / total
        print(f"\n=== EVALUATION STATS ===")
        print(f"Total: {total} | Average: {avg:.1f}/5.0\n")
        print("Recent (last 10):")
        for e in log[-10:]:
            ts = e.get("timestamp", "")[:10]
            print(f"  {ts} | {'★' * e['rating']}{'☆' * (5-e['rating'])} | "
                  f"{e.get('model', '?')} | {e.get('category', '?')} | "
                  f"{(e.get('notes', '') or '')[:40]}")
        print()


# ── Interactive Prompts ───────────────────────────────────────────────────────

def ask(question, choices=None, default=None):
    if HAS_QUESTIONARY and choices:
        return questionary.select(question, choices=choices, style=QUESTIONARY_STYLE, default=default).ask()
    elif HAS_QUESTIONARY:
        return questionary.text(question, style=QUESTIONARY_STYLE, default=default or "").ask()
    else:
        if choices:
            for i, c in enumerate(choices, 1):
                print(f"  {i}. {c}")
            val = input(f"{question} [1-{len(choices)}]: ").strip()
            try:
                return choices[int(val) - 1]
            except Exception:
                return choices[0]
        return input(f"{question}: ").strip()

def ask_confirm(question, default=True):
    if HAS_QUESTIONARY:
        return questionary.confirm(question, default=default, style=QUESTIONARY_STYLE).ask()
    return input(f"{question} [Y/n]: ").strip().lower() not in ("n", "no")

def ask_text(question, default=""):
    if HAS_QUESTIONARY:
        return questionary.text(question, default=default, style=QUESTIONARY_STYLE).ask()
    val = input(f"{question}: ").strip()
    return val or default

# ── Main Agent ────────────────────────────────────────────────────────────────

def _select_project(active_project):
    """Handle project selection / creation flow. Returns (slug, config) or (None, None)."""
    projects = list_projects(PROJECT_ROOT)
    choices = []
    slug_map = {}
    for p in projects:
        label = get_project_display_name(p)
        choices.append(label)
        slug_map[label] = p["slug"]
    choices.append("Create new project")
    choices.append("No project (use main folder)")

    selection = ask("Select project:", choices=choices)

    if not selection or selection == "No project (use main folder)":
        cprint("[dim]Working in main folder (no project).[/dim]")
        return None, None

    if selection == "Create new project":
        name = ask_text("Project name")
        if not name:
            return active_project, load_project(PROJECT_ROOT, active_project) if active_project else (None, None)
        desc = ask_text("Project description (optional)")
        instructions = ask_text("Project instructions (e.g. product dimensions, materials, brand rules)")

        # Collect optional defaults
        cprint("[dim]Set default settings for this project (press Enter to skip each).[/dim]")
        defaults = {}
        def_model = ask("Default model:", choices=["Skip"] + list(MODELS.keys()), default="Skip")
        if def_model and def_model != "Skip":
            defaults["model"] = MODELS[def_model]
        def_cat = ask("Default category:", choices=["Skip"] + CATEGORIES, default="Skip")
        if def_cat and def_cat != "Skip":
            defaults["category"] = def_cat
        def_res = ask("Default resolution:", choices=["Skip"] + RESOLUTIONS, default="Skip")
        if def_res and def_res != "Skip":
            defaults["resolution"] = def_res

        try:
            config = create_project(PROJECT_ROOT, name, desc or "", defaults, instructions or "")
            cprint(f"[green]Created project:[/green] [bold]{name}[/bold] ({config['slug']})")
            return config["slug"], config
        except ValueError as e:
            cprint(f"[red]ERROR:[/red] {e}")
            return active_project, load_project(PROJECT_ROOT, active_project) if active_project else (None, None)

    # Selected an existing project
    slug = slug_map[selection]
    config = load_project(PROJECT_ROOT, slug)
    if config:
        cprint(f"[green]Active project:[/green] [bold]{config['name']}[/bold]")
        if config.get("instructions"):
            cprint(f"[dim]Instructions: {config['instructions'][:100]}{'...' if len(config.get('instructions','')) > 100 else ''}[/dim]")
    return slug, config


def run_agent():
    print_header()

    api_key = ensure_api_key(force_setup="--setup" in sys.argv)

    # ── Project state ──
    active_project = None       # slug string or None
    active_project_config = None  # dict or None

    while True:
        rule("MAIN MENU")

        # Show active project in menu header
        if active_project and active_project_config:
            cprint(f"[bold cyan]Project:[/bold cyan] {active_project_config['name']}")
        else:
            cprint("[dim]Project: None (main folder)[/dim]")

        # ── Top-level action ──
        action = ask("What would you like to do?", choices=TOP_LEVEL_ACTIONS,
                      default=TOP_LEVEL_ACTIONS[0])

        if not action or action == "Quit":
            cprint("\n[yellow]Goodbye![/yellow]\n" if HAS_RICH else "\nGoodbye!\n")
            break

        if action == "Help / How to use":
            show_help()
            continue

        if action == "Select / Create project":
            active_project, active_project_config = _select_project(active_project)
            continue

        if action == "View evaluation history":
            eval_path = None
            if active_project:
                eval_path = get_project_eval_log(PROJECT_ROOT, active_project)
                cprint(f"[dim]Showing evaluations for project: {active_project_config['name']}[/dim]")
            show_evaluation_stats(eval_log_path=eval_path)
            continue

        if action == "Manage image cache":
            stats = get_cache_stats(PROJECT_ROOT)
            rule("IMAGE CACHE")
            cprint(f"  Cached URLs: [bold]{stats['valid']}[/bold] valid, "
                   f"[dim]{stats['expired']} expired[/dim]")
            if stats["valid"] > 0:
                do_clear = ask_confirm("Clear all cached URLs?", default=False)
                if do_clear:
                    removed = clear_cache(PROJECT_ROOT)
                    cprint(f"[yellow]Cleared {removed} cached entries.[/yellow]")
            elif stats["total"] == 0:
                cprint("[dim]No cached images yet. Upload a local file during generation to start caching.[/dim]")
            continue

        if action == "Browse prompt history":
            rule("PROMPT HISTORY")
            # Determine which prompts directory to scan
            if active_project:
                _, p_prompts, _ = get_project_paths(PROJECT_ROOT, active_project)
                cprint(f"[dim]Browsing prompts for project: {active_project_config['name']}[/dim]")
            else:
                p_prompts = PROMPTS_DIR
            entries = scan_prompts(p_prompts)
            if not entries:
                cprint("[dim]No saved prompts found. Generate some images first![/dim]")
                continue

            # Optional tag filter
            all_tags = get_all_tags(entries)
            if all_tags:
                tag_filter = ask("Filter by tag:", choices=["Show all"] + all_tags, default="Show all")
                if tag_filter and tag_filter != "Show all":
                    entries = filter_by_tags(entries, [tag_filter])
                    if not entries:
                        cprint(f"[dim]No prompts found with tag '{tag_filter}'.[/dim]")
                        continue

            # Show entries for selection
            labels = [format_entry_label(e) for e in entries[:30]]
            labels.append("Back to menu")
            selected = ask("Select a prompt:", choices=labels)
            if not selected or selected == "Back to menu":
                continue

            idx = labels.index(selected)
            entry = entries[idx]
            settings = entry_to_settings(entry)

            # Show details
            rule("PROMPT DETAILS")
            cprint(f"[bold]Description:[/bold] {settings['description'][:200]}")
            cprint(f"[dim]Model: {settings['model']} | Category: {settings['category']} | "
                   f"Style: {settings['style']} | Mode: {settings['image_mode']}[/dim]")
            cprint(f"[dim]Resolution: {settings['resolution']} | Aspect: {settings['aspect_ratio']} | "
                   f"Format: {settings['output_format']}[/dim]")
            if settings.get("tags"):
                cprint(f"[dim]Tags: {', '.join(settings['tags'])}[/dim]")
            eval_data = entry.get("evaluation", {})
            if eval_data and eval_data.get("rating"):
                stars = "★" * eval_data["rating"] + "☆" * (5 - eval_data["rating"])
                cprint(f"[dim]Rating: {stars} {eval_data.get('notes', '')}[/dim]")

            reuse = ask_confirm("Re-generate with these settings?", default=False)
            if reuse:
                cprint("[dim]Settings loaded — returning to generation flow.[/dim]")
                # TODO: Pre-fill generation flow with loaded settings
                # For now, show the description so user can copy it
                cprint(f"\n[bold]Copy this description for your next generation:[/bold]")
                cprint(f"{settings['description']}\n")
            continue

        # ── From here: "Generate an image" flow ──
        rule("MODE")

        # ── Image Mode ──
        mode_label = ask("What do you want to do?", choices=IMAGE_MODES,
                         default=IMAGE_MODES[0])
        image_mode = IMAGE_MODE_KEYS[mode_label]

        # ── Edit operation (if edit mode) ──
        edit_operation = None
        arch_render_category = None
        if image_mode == "edit":
            op_label = ask("What kind of edit?", choices=EDIT_OPERATIONS)
            edit_operation = EDIT_OPERATION_KEYS[op_label]

            # For render-to-photo, ask architecture sub-type immediately
            if edit_operation == "render_to_photo":
                arch_render_category = ask("Architecture type:", choices=ARCH_SUB_TYPES,
                                           default=ARCH_SUB_TYPES[0])

        rule("SETTINGS")

        # Smart defaults: project defaults > last_used > hardcoded
        proj_defaults = (active_project_config or {}).get("defaults", {})
        last_used = load_last_used()
        # Use last_used from the most recently used category as session defaults
        lu = {}
        if last_used:
            # Pick the most recent entry (last key in dict)
            last_cat = list(last_used.keys())[-1] if last_used else None
            if last_cat:
                lu = last_used[last_cat]
        # Project defaults take priority over last_used
        smart = {**lu, **proj_defaults}

        # ── Model ──
        model_choices = list(MODELS.keys())
        default_model_label = model_choices[0]
        if smart.get("model"):
            for label, mid in MODELS.items():
                if mid == smart["model"]:
                    default_model_label = label
                    break
        model_label = ask("Select model:", choices=model_choices, default=default_model_label)
        model = MODELS[model_label]
        max_refs = MODEL_MAX_REFS.get(model, 8)

        # Show model tip
        detail = MODEL_DETAILS.get(model)
        if detail:
            cprint(f"[dim]Tip: {detail['tip']}[/dim]")

        # ── Resolution ──
        default_res = smart.get("resolution", "1K")
        resolution = ask("Resolution:", choices=RESOLUTIONS, default=default_res)

        # ── Aspect ratio ──
        default_ratio = "1:1  — Square"
        if smart.get("aspect_ratio"):
            for r in ASPECT_RATIOS:
                if r.startswith(smart["aspect_ratio"]):
                    default_ratio = r
                    break
        ratio_label = ask("Aspect ratio:", choices=ASPECT_RATIOS, default=default_ratio)
        aspect_ratio = ratio_label.split("—")[0].strip().split()[0]

        # ── Output format ──
        default_fmt = smart.get("output_format", "jpg")
        output_format = ask("Output format:", choices=["jpg", "png"], default=default_fmt)

        # ── Enhancement level (for generate/consistency/render_to_photo) ──
        enhance_level = "directors_cut"
        if image_mode in ("generate", "consistency") or edit_operation == "render_to_photo":
            default_enhance = ENHANCE_LEVELS[0]
            if smart.get("enhance_level"):
                for el in ENHANCE_LEVELS:
                    if ENHANCE_LEVEL_KEYS.get(el) == smart["enhance_level"]:
                        default_enhance = el
                        break
            enhance_label = ask("Enhancement level:", choices=ENHANCE_LEVELS,
                                default=default_enhance)
            enhance_level = ENHANCE_LEVEL_KEYS[enhance_label]

        rule("PROMPT BUILDER")

        # ── Category (for generate/consistency modes, or render_to_photo) ──
        category = "miscellaneous"
        style = "photorealistic"
        if arch_render_category:
            # render_to_photo: architecture sub-type already selected
            category = arch_render_category
            style = "photorealistic"
            cprint(f"[dim]Architecture category: {category} | Style: photorealistic[/dim]")
        elif image_mode in ("generate", "consistency"):
            default_cat = smart.get("category", "miscellaneous")
            default_style = smart.get("style", "photorealistic")
            category = ask("Image category:", choices=CATEGORIES, default=default_cat)
            style = ask("Style preset:", choices=STYLE_PRESETS, default=default_style)

        # ── Feedback-based recommendations ──
        preferences = load_preferences(PROJECT_ROOT, active_project)
        if preferences and preferences.get("ready"):
            model_rec = get_model_recommendation(preferences, category)
            if model_rec and model_rec[0] != model:
                cprint(f"[dim]Feedback: {model_rec[1]}[/dim]")
            enhance_rec = get_enhance_recommendation(preferences, model)
            if enhance_rec and enhance_rec[0] != enhance_level:
                cprint(f"[dim]Feedback: {enhance_rec[1]}[/dim]")

        # ── Description / Instructions ──
        if image_mode == "generate":
            description = ask_text("Describe your image")
        elif image_mode == "edit" and edit_operation == "render_to_photo":
            cprint("[dim]Describe the scene, desired changes, camera angle, lighting, or materials. "
                   "The engine will add architecture-specific enhancements automatically.[/dim]")
            description = ask_text("Describe the photorealistic conversion")
        elif image_mode == "edit":
            description = ask_text("Describe the changes you want")
        elif image_mode == "style_transfer":
            description = ask_text("Describe the new scene to render in the reference style")
        elif image_mode == "remix":
            description = ask_text("Describe what to change in the variation")
        elif image_mode == "consistency":
            description = ask_text("Describe the new scene for this subject")
        else:
            description = ask_text("Describe your image")

        if not description:
            cprint("[yellow]No description provided — skipping.[/yellow]")
            continue

        # ── Enhance description ──
        if enhance_level in ("directors_cut", "standard"):
            original_description = description
            description = enhance_description(description, category, style)
            if description != original_description:
                cprint("[dim]Description enhanced with category-specific details and sensory grounding.[/dim]")
        else:
            original_description = description

        # ── Extra negative prompt ──
        add_neg = ask_confirm("Add custom negative prompt terms?", default=False)
        extra_negative = ""
        if add_neg:
            extra_negative = ask_text("Negative terms (comma-separated)")

        # ── Input images ──
        image_urls = []
        requires_images = image_mode in ("edit", "style_transfer", "remix", "consistency")

        if requires_images:
            # Images required for these modes
            if image_mode == "edit":
                img_prompt = "Image URL or local path to edit (required)"
            elif image_mode == "style_transfer":
                img_prompt = "Style reference image URL or path (required)"
                cprint("[dim]Tip: 1-2 style reference images work best. "
                       "The model copies style/lighting/grading, not content.[/dim]")
            elif image_mode == "remix":
                img_prompt = "Image URL or local path to remix (required)"
            elif image_mode == "consistency":
                img_prompt = "Subject reference image URL or path (required)"
                cprint("[dim]Tip: Provide 3-5 reference angles for best consistency. "
                       "State 'maintain exact facial structure' in your description.[/dim]")
            else:
                img_prompt = "Image URL or local path"

            cprint(f"[dim]Enter image URLs or local file paths. "
                   f"Local files are auto-uploaded to Kie.ai (free, expires 3 days).[/dim]")
            cprint(f"[dim]At least 1 required for {image_mode} mode.[/dim]")
            while len(image_urls) < max_refs:
                suffix = " (empty to stop)" if image_urls else ""
                raw = ask_text(f"{img_prompt} [{len(image_urls)+1}/{max_refs}]{suffix}")
                if not raw:
                    if not image_urls:
                        cprint(f"[red]At least 1 image required for {image_mode} mode.[/red]")
                        continue
                    break
                resolved = resolve_image_input(api_key, raw)
                if resolved:
                    image_urls.append(resolved)
                else:
                    cprint("[yellow]Skipped — could not resolve image.[/yellow]")

            # For consistency mode, prompt for additional references
            if image_mode == "consistency" and len(image_urls) < max_refs:
                add_more = ask_confirm("Add more reference angles? (improves consistency)", default=False)
                if add_more:
                    while len(image_urls) < max_refs:
                        raw = ask_text(f"Additional reference [{len(image_urls)+1}/{max_refs}] (empty to stop)")
                        if not raw:
                            break
                        resolved = resolve_image_input(api_key, raw)
                        if resolved:
                            image_urls.append(resolved)
        else:
            add_refs = ask_confirm(f"Add reference images? (max {max_refs})", default=False)
            if add_refs:
                cprint(f"[dim]Enter image URLs or local file paths. Press Enter on empty line when done.[/dim]")
                while len(image_urls) < max_refs:
                    raw = ask_text(f"Image URL or path [{len(image_urls)+1}/{max_refs}] (empty to stop)")
                    if not raw:
                        break
                    resolved = resolve_image_input(api_key, raw)
                    if resolved:
                        image_urls.append(resolved)

        # ── Build prompt ──
        proj_instructions = (active_project_config or {}).get("instructions", "")
        prompt, negative_prompt, layer_parts = build_prompt(
            description, category, style, extra_negative,
            image_mode=image_mode,
            edit_operation=edit_operation,
            enhance_level=enhance_level,
            project_instructions=proj_instructions,
        )

        # ── Fit prompt to model limit (intelligent re-engineering) ──
        layers_dropped = []
        model_limit = MODEL_PROMPT_LIMITS.get(model, 5000)
        if len(prompt) > model_limit:
            prompt, layers_dropped = fit_prompt(layer_parts, model_limit)
            if layers_dropped:
                cprint(f"[yellow]Prompt re-engineered for {model} "
                       f"({len(prompt)}/{model_limit} chars). "
                       f"Dropped: {', '.join(layers_dropped)}[/yellow]")

        # ── Noise Trap warning ──
        iso_match = re.search(r'ISO\s*(\d+)', prompt, re.IGNORECASE)
        if iso_match and int(iso_match.group(1)) >= 800:
            cprint("[yellow]NOISE TRAP:[/yellow] ISO >= 800 detected in prompt. "
                   "High ISO in complex scenes can trigger illustration biases. "
                   "Rely on subject imperfections (pores, asymmetry) over camera noise for realism.")

        # ── Feedback warnings ──
        if preferences and preferences.get("ready"):
            warnings = get_negative_warnings(preferences)
            for w in warnings:
                cprint(f"[dim]Learning: {w}[/dim]")

        rule("PROMPT PREVIEW")
        if HAS_RICH:
            # Show mode badge
            mode_badge = f"[bold cyan]{image_mode.upper()}[/bold cyan]"
            if edit_operation:
                mode_badge += f" [dim]({edit_operation})[/dim]"
            enhance_badge = f"[bold magenta]{enhance_level.upper()}[/bold magenta]"

            preview_parts = [
                f"[dim]Mode:[/dim] {mode_badge}  [dim]Enhancement:[/dim] {enhance_badge}",
                "",
                f"[bold]Prompt[/bold] [dim]({len(prompt)} chars):[/dim]",
                prompt[:1500] + ("..." if len(prompt) > 1500 else ""),
                "",
                f"[bold]Negative[/bold] [dim]({len(negative_prompt)} chars):[/dim]",
                f"[dim]{negative_prompt[:300]}{'...' if len(negative_prompt) > 300 else ''}[/dim]",
            ]
            if image_urls:
                preview_parts.append("")
                preview_parts.append(f"[bold]Input images:[/bold] {len(image_urls)}")
                for i, u in enumerate(image_urls[:3], 1):
                    preview_parts.append(f"  [dim]{i}. {u[:80]}{'...' if len(u) > 80 else ''}[/dim]")
                if len(image_urls) > 3:
                    preview_parts.append(f"  [dim]... and {len(image_urls)-3} more[/dim]")

            console.print(Panel(
                "\n".join(preview_parts),
                border_style="dim",
                title="[dim]Generated Prompt[/dim]",
            ))
        else:
            print(f"\nMode: {image_mode} | Enhancement: {enhance_level}")
            print(f"\nPrompt ({len(prompt)} chars):\n{prompt[:1500]}...")
            print(f"\nNegative ({len(negative_prompt)} chars):\n{negative_prompt[:300]}...")

        # ── Cost estimate ──
        cost = estimate_cost(model, resolution)
        if cost is not None:
            cprint(f"[dim]Estimated cost: [bold]${cost:.3f}[/bold][/dim]")
        else:
            cprint(f"[dim]Cost: pricing unavailable for {resolution} on this model[/dim]")

        proceed = ask_confirm("Generate image?", default=True)
        if not proceed:
            cprint("[yellow]Cancelled.[/yellow]")
        else:
            rule("GENERATING")

            # Auto-switch to edit model variant if available
            api_model = model
            if image_mode in ("edit", "remix") and model in MODEL_EDIT_VARIANTS:
                api_model = MODEL_EDIT_VARIANTS[model]
                cprint(f"[dim]Using edit variant: {api_model}[/dim]")

            task_id = None
            image_url = None

            if HAS_RICH:
                with Progress(
                    SpinnerColumn(spinner_name="dots", style="yellow"),
                    TextColumn("[progress.description]{task.description}"),
                    TimeElapsedColumn(),
                    console=console,
                    transient=False,
                ) as progress:
                    task = progress.add_task("[yellow]Submitting job to Kie.ai...", total=None)
                    try:
                        task_id = create_task(
                            api_key, api_model, prompt, negative_prompt,
                            aspect_ratio, resolution, output_format,
                            image_urls or None
                        )
                        progress.update(task, description=f"[yellow]Polling task {task_id[:8]}... (may take 30-120s)")
                        image_url = poll_task(api_key, task_id)
                        progress.update(task, description="[green]Done!")
                    except SystemExit:
                        raise
            else:
                print("Submitting to Kie.ai...")
                task_id = create_task(
                    api_key, api_model, prompt, negative_prompt,
                    aspect_ratio, resolution, output_format,
                    image_urls or None
                )
                print(f"Task ID: {task_id}. Polling...")
                image_url = poll_task(api_key, task_id)

            # Project-scoped output directories
            proj_dirs = None
            if active_project:
                p_imgs, p_prompts, _ = get_project_paths(PROJECT_ROOT, active_project)
                proj_dirs = (p_imgs, p_prompts)
            img_path, prompt_path = get_output_paths(category, output_format,
                                                      description=description, project_dirs=proj_dirs)

            download_image(image_url, img_path)

            # ── Optional tags ──
            tags = []
            add_tags = ask_confirm("Add tags to this generation?", default=False)
            if add_tags:
                tag_input = ask_text("Tags (comma-separated, e.g. 'hero, v2, client-review')")
                if tag_input:
                    tags = [t.strip().lower() for t in tag_input.split(",") if t.strip()]

            save_prompt_json(
                prompt_path, model, prompt, negative_prompt,
                aspect_ratio, resolution, output_format, image_urls, category, style,
                image_mode=image_mode, enhance_level=enhance_level,
                edit_operation=edit_operation, tags=tags or None,
                project=active_project, original_description=original_description,
                layers_dropped=layers_dropped or None,
            )

            if HAS_RICH:
                result_table = Table(box=box.SIMPLE, show_header=False, padding=(0, 1))
                result_table.add_column(style="dim")
                result_table.add_column(style="bold")
                result_table.add_row("Image", str(img_path.relative_to(PROJECT_ROOT)))
                result_table.add_row("Prompt", str(prompt_path.relative_to(PROJECT_ROOT)))
                result_table.add_row("Model", model)
                result_table.add_row("Mode", image_mode)
                result_table.add_row("Enhancement", enhance_level)
                result_table.add_row("Resolution", resolution)
                result_table.add_row("Aspect", aspect_ratio)
                if image_urls:
                    result_table.add_row("Input images", str(len(image_urls)))
                if tags:
                    result_table.add_row("Tags", ", ".join(tags))
                if active_project and active_project_config:
                    result_table.add_row("Project", active_project_config["name"])
                console.print(Panel(
                    result_table,
                    title="[green bold]Image Generated[/green bold]",
                    border_style="green",
                ))
            else:
                print(f"\nImage saved: {img_path}")
                print(f"Prompt saved: {prompt_path}")
                if tags:
                    print(f"Tags: {', '.join(tags)}")

            open_image(img_path)

            # ── Cost tracking (project) ──
            if active_project:
                gen_cost = estimate_cost(model, resolution) or 0.0
                increment_project_stats(PROJECT_ROOT, active_project, gen_cost)

            # ── Save last-used settings per category ──
            save_last_used(category, {
                "model": model,
                "resolution": resolution,
                "aspect_ratio": aspect_ratio,
                "output_format": output_format,
                "style": style,
                "enhance_level": enhance_level,
            })

            # ── Evaluation ──
            eval_path = get_project_eval_log(PROJECT_ROOT, active_project) if active_project else None
            evaluate_image(prompt_path, img_path, model, category, eval_log_path=eval_path)

            # ── Update learned preferences ──
            compute_preferences(PROJECT_ROOT, active_project)

            # ── A/B Model Comparison ──
            compare = ask_confirm("Compare with another model?", default=False)
            if compare:
                other_models = {k: v for k, v in MODELS.items() if v != model}
                if other_models:
                    other_label = ask("Compare model:", choices=list(other_models.keys()))
                    other_model = other_models[other_label]
                    other_api_model = other_model
                    if image_mode in ("edit", "remix") and other_model in MODEL_EDIT_VARIANTS:
                        other_api_model = MODEL_EDIT_VARIANTS[other_model]

                    # Re-fit prompt for the comparison model's limit
                    compare_prompt = prompt
                    compare_dropped = []
                    other_max = MODEL_PROMPT_LIMITS.get(other_api_model, 5000)
                    if len(prompt) > other_max:
                        compare_prompt, compare_dropped = fit_prompt(layer_parts, other_max)
                        if compare_dropped:
                            cprint(f"[yellow]Prompt adapted for {other_label} "
                                   f"({len(compare_prompt)}/{other_max} chars). "
                                   f"Dropped: {', '.join(compare_dropped)}[/yellow]")

                    rule("COMPARING")
                    cprint(f"[dim]Generating same prompt with {other_label}...[/dim]")
                    try:
                        other_task_id = create_task(
                            api_key, other_api_model, compare_prompt, negative_prompt,
                            aspect_ratio, resolution, output_format,
                            image_urls or None
                        )
                        other_url = poll_task(api_key, other_task_id)
                        other_img_path, other_prompt_path = get_output_paths(
                            category, output_format, description=original_description,
                            project_dirs=proj_dirs)
                        download_image(other_url, other_img_path)
                        save_prompt_json(
                            other_prompt_path, other_model, compare_prompt, negative_prompt,
                            aspect_ratio, resolution, output_format, image_urls, category, style,
                            image_mode=image_mode, enhance_level=enhance_level,
                            edit_operation=edit_operation, tags=tags or None,
                            project=active_project, original_description=original_description,
                            layers_dropped=compare_dropped or None,
                        )
                        cprint(f"[green]Comparison saved:[/green] {other_img_path.relative_to(PROJECT_ROOT)}")
                        open_image(other_img_path)
                    except Exception as e:
                        cprint(f"[red]Comparison failed:[/red] {e}")

        console.print() if HAS_RICH else print()


if __name__ == "__main__":
    run_agent()
