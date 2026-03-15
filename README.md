<p align="center">
  <img src="https://img.shields.io/badge/python-3.10+-3776AB?style=for-the-badge&logo=python&logoColor=white" alt="Python 3.10+">
  <img src="https://img.shields.io/badge/Kie.ai-API-FF6B35?style=for-the-badge" alt="Kie.ai API">
  <img src="https://img.shields.io/badge/terminal-Rich_UI-00D4AA?style=for-the-badge" alt="Rich Terminal UI">
  <img src="https://img.shields.io/badge/license-MIT-green?style=for-the-badge" alt="MIT License">
</p>

<br>

<h1 align="center">
<pre>
██╗  ██╗██╗███████╗     █████╗ ██╗
██║ ██╔╝██║██╔════╝    ██╔══██╗██║
█████╔╝ ██║█████╗      ███████║██║
██╔═██╗ ██║██╔══╝      ██╔══██║██║
██║  ██╗██║███████╗    ██║  ██║██║
╚═╝  ╚═╝╚═╝╚══════╝    ╚═╝  ╚═╝╚═╝
      I M A G E   S T U D I O
</pre>
</h1>

<p align="center">
  <strong>Professional AI image generation from the terminal.</strong><br>
  A 12-layer cinematic prompt engine that transforms simple descriptions into photorealistic output.
</p>

<br>

---

## What It Does

You type a description. The engine wraps it in up to **12 layers** of cinematic directives — composition, atmosphere, depth separation, lighting physics, camera math, forensic-level micro-details, quality gates, and negative stacks — then sends it to one of 5 AI models via the [Kie.ai](https://kie.ai) API.

The result: photorealistic images that look like they were directed, not generated.

---

## Features

```
 MODES               MODELS                 ENGINE
 ─────               ──────                 ──────
 Generate            Nano Banana 2          12-layer prompt enhancement
 Edit                Nano Banana Pro        3 enhancement levels
 Style Transfer      Seedream 4.0           Intelligent prompt fitting
 Remix               Seedream 4.5           Rule-based description enrichment
 Consistency         Flux 2 Pro             A/B model comparison

 WORKFLOW             CATEGORIES             OUTPUT
 ────────             ──────────             ──────
 Customer projects    Portrait               Up to 4K resolution
 Prompt history       Product                10 aspect ratios
 Smart defaults       Landscape              JPG / PNG
 Evaluation system    Architecture (3 sub)   Smart file naming
 Feedback learning    Scene                  Prompt tags
 Cost tracking        Miscellaneous          Batch scripts
```

---

## Quick Start

### 1. Install

```bash
git clone https://github.com/ArtisanLabs/kie-ai-image-studio.git
cd kie-ai-image-studio
pip install -r requirements.txt
```

### 2. Run

```bash
python agent.py
```

On first run, you'll be guided through API key setup:

1. Create a free account at [kie.ai](https://kie.ai)
2. Go to [kie.ai/api-key](https://kie.ai/api-key) and create a key
3. Paste it when prompted — saved to `.env` (git-ignored)

To reconfigure later: `python agent.py --setup`

---

## Models

| Model | Best For | Max Refs | Prompt Limit | Max Res | Price |
|-------|----------|:--------:|:------------:|:-------:|------:|
| **Nano Banana 2** | Realism, multi-reference | 14 | 20K chars | 4K | $0.04/1K |
| **Nano Banana Pro** | Typography, max fidelity | 8 | 20K chars | 1K | $0.09/1K |
| **Seedream 4.0** | Budget quality, color accuracy | 10 | 5K chars | 4K | $0.025 |
| **Seedream 4.5** | Best value, spatial understanding | 14 | 3K chars | 3K | $0.032 |
| **Flux 2 Pro** | Fine detail, character consistency | 8 | 5K chars | 2K | $0.025/1K |

---

## The Prompt Engine

Every generation passes through a layered enhancement pipeline:

```
YOUR INPUT
    │
    ▼
┌─────────────────────────────────────────────┐
│  Layer 1   Mode prefix                      │
│  Layer 2   Shot type (category-specific)    │
│  Layer 3   Your description (enhanced)      │
│  Layer 4   Composition directives           │
│  Layer 5   Atmosphere amplifiers            │
│  Layer 6   Depth layers (FG/MG/BG)         │
│  Layer 7   Lighting behavior                │
│  Layer 8   Camera math (focal, f/, ISO)     │
│  Layer 9   Micro-details (textures)         │
│  Layer 10  Quality directives               │
│  Layer 11  Inline negatives                 │
│  Layer 12  Mode-specific negatives          │
└─────────────────────────────────────────────┘
    │
    ▼
FINAL PROMPT → Kie.ai API → Image
```

Three levels control how many layers fire:

| Level | Layers | Use Case |
|-------|:------:|----------|
| **Director's Cut** | All 12 | Maximum quality — every detail controlled |
| **Standard** | 6 | Professional results, faster iteration |
| **Minimal** | 4 | Quick tests, custom prompts you don't want overridden |

When a prompt exceeds a model's character limit, the **Prompt Fitter** re-engineers it by progressively dropping low-priority layers — never truncating.

---

## Image Modes

| Mode | What It Does | Images Required |
|------|-------------|:---------------:|
| **Generate** | Create from scratch | Optional |
| **Edit** | Modify mood, elements, colors, background, subject, style | 1+ |
| **Style Transfer** | Apply a reference style to a new scene | 1+ |
| **Remix** | Create a variation of an existing image | 1+ |
| **Consistency** | Same subject, new scene | 1+ (3-5 best) |

Edit mode supports 7 operation types including a specialized **3D render to photorealistic** conversion for architecture.

---

## Architecture Mode

Three specialized sub-categories with corrected verticals, human scale figures, botanical vegetation, construction-grade materials, and anti-CGI negatives:

| Sub-type | Camera | Lighting |
|----------|--------|----------|
| **Exterior** | 24mm tilt-shift, f/8 | Golden hour / blue hour |
| **Interior** | 17mm tilt-shift, f/8, HDR | Mixed natural + artificial |
| **Detail** | 90mm macro, f/5.6, focus-stacked | Raking sidelight 30-45 deg |

---

## Customer Projects

Isolate work by client with project-scoped images, prompts, evaluations, and cost tracking:

```
projects/
  client-name/
    project.json          # Defaults, instructions, cost tracking
    images/               # Generated images (git-ignored)
    prompts/              # Prompt configs (safe to commit)
    evaluations/          # Rating history
```

Project instructions (brand rules, dimensions, specs) are auto-injected into every prompt.

---

## Batch Scripts

Generate headlessly from saved prompt JSON:

```bash
python scripts/generate_kie.py prompts/portrait/hero-shot.json output.jpg "4:5"
```

Retrieve a completed task by ID:

```bash
python scripts/get_kie_image.py <taskId> output.jpg
```

---

## Project Structure

```
kie-ai-image-studio/
├── agent.py                     # Main interactive agent (~3K lines)
├── image_cache.py               # Reference image URL caching (3-day TTL)
├── projects.py                  # Customer project management
├── description_enhancer.py      # Rule-based description enhancement
├── prompt_history.py            # Prompt history browsing and reuse
├── prompt_fitter.py             # Intelligent prompt fitting for model limits
├── feedback_learner.py          # Feedback learning from evaluations
├── requirements.txt             # Python dependencies
├── .env.example                 # API key template
├── scripts/
│   ├── generate_kie.py          # Headless batch generation
│   └── get_kie_image.py         # Task retrieval by ID
├── images/                      # Generated images (git-ignored)
│   └── <category>/
├── prompts/                     # Saved prompt configs (safe to commit)
│   └── <category>/
├── evaluations/                 # Rating history
│   └── evaluation_log.json
└── projects/                    # Customer project folders
    └── <project-slug>/
```

---

## Dependencies

| Package | Purpose |
|---------|---------|
| [requests](https://pypi.org/project/requests/) | HTTP client for Kie.ai API |
| [rich](https://pypi.org/project/rich/) | Terminal UI — panels, tables, progress bars |
| [questionary](https://pypi.org/project/questionary/) | Interactive menus and prompts |

---

## Security

- API keys live in `.env` (git-ignored) or the `KIE_API_KEY` environment variable
- Prompt JSONs contain only prompts and settings — no secrets
- Generated images are git-ignored (binary files)
- Project images are git-ignored; prompts and evaluations are safe to commit

---

## License

MIT
