# Kie.ai Image Generation Studio

This document tracks our progress, generated assets, and custom scripts for the Kie.ai image generation project. Supports 5 models (NB2, NB Pro, Seedream 4.0, Seedream 4.5, Flux 2 Pro) with a 12-layer prompt enhancement engine.

## Project Structure

It is critical to **always keep prompts and images organized** within the project directory.

- `/images/<category>/` - All generated images, organized by category. Categories: `portrait`, `product`, `landscape`, `architecture-exterior`, `architecture-interior`, `architecture-detail`, `scene`, `miscellaneous`. **Git-ignored** (binary files, not tracked).
- `/prompts/<category>/` - Saved JSON prompt configurations, mirroring the exact same subfolder structure as images. Safe to commit — contains no secrets.
- `/projects/<name>/` - Customer project folders with project-specific `project.json`, `images/`, `prompts/`, and `evaluations/`. Project images are git-ignored; prompts/evaluations are safe to commit.
- `/scripts/` - Utility scripts for batch processing, API interaction, or prompt generation.
- `image_cache.py` - Reference image URL caching module (3-day TTL).
- `projects.py` - Project management module (create, load, save projects).
- `description_enhancer.py` - Rule-based description enhancement module.
- `prompt_history.py` - Prompt history browsing and reuse module.
- `prompt_fitter.py` - Intelligent prompt fitting module — re-engineers prompts to fit model character limits by progressively dropping low-priority layers and condensing remaining ones.
- `feedback_learner.py` - Feedback learning module — analyzes evaluation history to recommend optimal models, enhancement levels, and flag quality patterns.
- `master_prompt_reference.md` - The compiled JSON schema and guide.
- `.env` - API key storage. **Must never be committed to git. Never log, print, or expose this value.**
- `image_cache.json` - Cached upload URLs. **Git-ignored** (auto-generated state).
- `last_used.json` - Last-used settings per category. **Git-ignored** (auto-generated state).
- `learned_preferences.json` - Learned model/category preferences from evaluation history. **Git-ignored** (auto-generated state).

## Image Generation Workflow

Whenever the user requests to generate an image, you must use the **Nano Banana image generation skill**.

1. Use the skill to generate the image based on the user's requirements.
2. Save the resulting image to the correctly categorized subfolder inside the `/images/` directory (e.g., `/images/portrait/`, `/images/architecture-exterior/`). **If a specific category cannot be determined, save it to `/images/miscellaneous/`.** This is mandatory for every single generation.
3. Save the corresponding prompt configuration to the `/prompts/` directory, mirroring the exact same subfolder used for the image (e.g., `/prompts/portrait/` or `/prompts/miscellaneous/`).
4. **Parallel Processing:** When you are processing multiple images at the same time, you MUST run their generation commands in parallel to save time.

## Prompt Enhancement Engine

The agent uses a **12-layer prompt enhancement system** that transforms simple descriptions into professional-grade cinematic narratives. Three enhancement levels:

| Level | Layers | Best For |
|-------|--------|----------|
| **Director's Cut** | All 12 layers (composition, atmosphere, depth, micro-details, lighting, camera, quality, inline negatives) | Maximum quality output |
| **Standard** | Shot type, description, lighting, camera, quality, negatives | Solid professional results |
| **Minimal** | Shot type, description, camera basics, negatives | Fast iteration, custom prompts |

### Enhancement Layers
1. Mode prefix (edit/style/remix/consistency framing)
2. Shot type declaration (category-specific)
3. User description (raw creative input)
4. Composition directives (rule of thirds, visual hierarchy, framing)
5. Atmosphere amplifiers (environmental presence, air quality, temperature)
6. Depth layers (foreground/midground/background separation)
7. Lighting behavior (what light DOES — shadows, specular, color temperature)
8. Camera math (focal length, aperture, ISO, shutter speed)
9. Micro-details (forensic-level texture and material specifics)
10. Quality directives (rendering fidelity, processing rules)
11. Inline negatives (imperative "do not" commands in positive prompt)
12. Mode-specific negatives (preservation commands per mode)

## Image Modes

The agent supports 5 image modes:

| Mode | Purpose | Requires Images |
|------|---------|-----------------|
| **Generate** | Create from scratch | Optional (reference) |
| **Edit** | Modify existing image (mood, elements, colors, background, subject, style) | Required (1+) |
| **Style Transfer** | Apply reference style to new scene | Required (1+) |
| **Remix** | Create variation of existing image | Required (1+) |
| **Consistency** | Same subject in new scene | Required (1+, 3-5 recommended) |

### Edit Operations
When in Edit mode, choose from: mood/atmosphere, add/remove elements, color/grading, background, subject details, artistic style, or custom instructions.

## Models (Integrated in agent.py)

| Model | T2I Model ID | Edit Behavior | Best For | Refs | Prompt | Max Res | Price |
| ----- | ------------ | -------------- | -------- | ---- | ------ | ------- | ----- |
| **Nano Banana 2** | `nano-banana-2` | Native (`image_input`) | Realism, multi-ref | 14 | 20K | 4K | $0.04/1K |
| **Nano Banana Pro** | `nano-banana-pro` | none | Typography, max fidelity | 8 | 20K | 1K | $0.09/1K |
| **Seedream 4.0** | `bytedance/seedream-v4-text-to-image` | `seedream-v4-edit` | Budget quality | 10 | 5K | 4K | $0.025 |
| **Seedream 4.5** | `seedream/4.5-text-to-image` | `seedream/4.5-edit` | Best value, spatial | 14 | **3K** | 3K | $0.032 |
| **Flux 2 Pro** | `flux-2/pro-text-to-image` | `flux-2/pro-image-to-image` | Detail, consistency | 8 | 5K | 2K | $0.025/1K |

**Prompt limits verified from kie.ai playground** (MCP server reports 5,000 for all — this is wrong). See `mcp_prompt_limits_correction.md`.

NB2 handles edits natively via `image_input` — no model switch, preserving resolution, negative_prompt, and output_format. Seedream/Flux models auto-switch to edit variant in Edit/Remix modes. NB Pro has no edit variant.

### Nano Banana Family (Kie.ai naming)

There is no "Nano Banana 3.1". The "3.1" refers to the underlying Gemini model version, not a NB version.

| Kie.ai Name | Model ID | Underlying Google Model | Notes |
|------------|----------|------------------------|-------|
| Nano Banana (v1) | `google/nano-banana` | Gemini 2.5 Flash Image | Legacy, simple params (`image_size` only) |
| Nano Banana 2 | `nano-banana-2` | Gemini 3.1 Flash Image | Current default, full params, `google_search` |
| Nano Banana Pro | `nano-banana-pro` | Gemini 3.0 Pro Image | Best quality, typography, 1K only |
| Nano Banana Edit | `google/nano-banana-edit` | Gemini Edit | Legacy — no resolution/negative_prompt. Use NB2 with `image_input` instead |

### Available on Kie.ai (MCP-verified, Not Integrated in agent.py)

| Model | MCP Tool | Modes | Refs/Edit | Aspect Ratios | Price |
|-------|----------|-------|-----------|---------------|-------|
| **Midjourney** | `midjourney_generate` | T2I, I2I, style ref, omni ref, video | 10 URLs | 1:2 to 2:1 (11 options) | varies by speed |
| **GPT-4o Image** | `openai_4o_image` | T2I, edit (mask), variants | 5 URLs + mask | 1:1, 3:2, 2:3 | ~$0.10 |
| **Grok Imagine** | `grok_imagine` | T2I, T2V, I2V, upscale | 1 URL | 2:3, 3:2, 1:1 only | ~$0.10/video |
| **Qwen** | `qwen_image` | T2I, edit | 1 URL | square to landscape_16_9 | varies |
| **Flux Kontext** | `flux_kontext_image` | T2I, edit | 1 URL | 21:9 to 9:16 | pro/max tiers |
| **Flux 2 Flex** | `flux2_image` (model_type=flex) | T2I, I2I | 8 URLs | 1:1 to auto | $0.07/1K, $0.12/2K |
| **Seedream V5 Lite** | `bytedance_seedream_image` (version=5-lite) | T2I, edit | 14 URLs | 1:1 to 21:9 | basic=2K, high=3K |
| **Z-Image** | `z_image` | T2I only | none | 1:1 to 9:16 | ~$0.004/image |
| **Ideogram V3 Reframe** | `ideogram_reframe` | reframe only | 1 URL | square to landscape_16_9 | varies |
| **Recraft Remove BG** | `recraft_remove_background` | BG removal | 1 URL | - | varies |
| **Topaz Upscale** | `topaz_upscale_image` | upscale 1-8x | 1 URL | - | 10-40 credits |
| Imagen 4 Fast | docs only | T2I | - | - | TBD |
| Imagen 4 | docs only | T2I | - | - | TBD |
| Imagen 4 Ultra | docs only | T2I | - | - | TBD |

## Architecture Category

Three sub-categories with specialized prompt engineering:

| Sub-category | Camera | Lighting | Best For |
|-------------|--------|----------|----------|
| **architecture-exterior** | 24mm tilt-shift, f/8, corrected verticals | Golden hour / blue hour | Building facades, site context |
| **architecture-interior** | 17mm tilt-shift, f/8, HDR bracketed | Mixed natural + artificial | Room volumes, material showcase |
| **architecture-detail** | 90mm macro, f/5.6, focus-stacked | Raking sidelight at 30-45 deg | Materials, joints, textures |

Architecture prompts include: corrected verticals, human scale figures, botanical vegetation names, construction-grade material descriptions, anti-CGI/anti-render negatives. All architecture categories include a **NANO-PRECISION MANDATE** — measurement-grade fidelity for all dimensions, proportions, element counts, placement accuracy, and spatial geometry. Each sub-category saves to its own folder (e.g., `/images/architecture-exterior/`).

## Agent Features

### Help Menu

Built-in help accessible from the main menu. Displays Rich-formatted tables covering all image modes, enhancement levels, model comparison with pricing, categories, and 10 best-practice tips from SKILL.md research.

### Cost Estimation

Before each generation, the agent displays the estimated API cost based on model + resolution selection. Uses the `MODEL_DETAILS` pricing data.

### Noise Trap Warning

After prompt building, the agent checks for ISO >= 800 in the generated prompt and warns the user about potential illustration biases. Recommends relying on subject imperfections over camera noise for realism.

### Reference Image Tips

Contextual tips displayed before image URL collection:

- Consistency mode: "Provide 3-5 reference angles for best consistency"
- Style transfer: "1-2 style reference images work best"

### Evaluation System

After each generation, the user can rate the result (1-5 stars) and add optional notes. Evaluations are:

- Saved to the prompt JSON file (under `evaluation` key)
- Appended to `/evaluations/evaluation_log.json`
- Viewable via "View evaluation history" from the main menu
- Statistics include: overall average, by-model breakdown, by-category breakdown, last 10 entries
- Fed into the **Feedback Learning** system to improve future recommendations

## Reference Image Cache

Uploaded image URLs (which expire after 3 days on Kie.ai servers) are cached locally in `image_cache.json`. When a local file is provided as reference, the agent checks the cache first — if the URL is still valid and the file hasn't changed, it reuses the cached URL instead of re-uploading.

- Cache keyed by absolute file path + modification time + file size
- TTL: 3 days (259200 seconds)
- Manageable from the main menu: view stats, clear cache
- Cache stored atomically (temp file + rename) to prevent corruption

## Customer Projects

Create isolated project folders for different clients or use cases. Each project has:

- **`project.json`** — Name, description, default settings, custom instructions, cost tracking
- **`images/<category>/`** — Project-scoped generated images
- **`prompts/<category>/`** — Project-scoped prompt configs
- **`evaluations/evaluation_log.json`** — Project-scoped evaluation history

Project instructions (e.g., product dimensions, brand rules, architectural measurements) are injected into the prompt as layer 3c, between the user description and composition directives.

Project defaults pre-fill the settings menus (model, resolution, category, etc.) but can always be overridden per generation.

### Project Workflow

1. Select "Select / Create project" from main menu
2. Create a new project or select an existing one
3. Set project instructions and default settings
4. Generate images — they save to the project folder
5. Evaluations are tracked per-project
6. Cost is tracked per-project automatically

## Description Enhancement

User input descriptions are automatically enhanced before entering the 12-layer `build_prompt()` engine. This is rule-based (no LLM calls) and operates only on layer 3 (the user's description text).

Enhancement techniques:

- **Vague term expansion**: "nice lighting" → "warm directional light with soft shadow gradients and natural falloff"
- **Keyword-to-narrative conversion**: "sunset, beach, woman, red dress" → "A scene featuring a sunset, a beach, a woman, and a red dress"
- **Category imperfection injection**: Adds realistic physical details (pores, weathering, material variation) appropriate to the category
- **Sensory grounding**: Adds tangible physical presence for short inputs

Enhancement is applied only for Director's Cut and Standard levels. The original description is preserved in the prompt JSON.

## Smart File Naming

Generated files are auto-named from the user's description instead of generic `category_timestamp` names:

- "A woman in a red dress on a beach at sunset" → `woman-red-dress-beach-sunset_20260315_103000.jpg`
- Stop words, camera terms, and bare numbers are filtered out
- Truncated to max 50 chars for filesystem safety

## Prompt Tags

Optional tags can be added to any generation (e.g., "hero", "v2", "client-review"). Tags are:

- Saved in the prompt JSON under the `"tags"` key
- Displayed in the result summary
- Filterable in the prompt history browser

## Prompt History

Browse and reuse past prompt configurations from the main menu. Supports:

- Project-scoped browsing (shows only the active project's prompts)
- Tag filtering
- Display of description, model, category, rating, and tags
- Re-generation with the same settings

## Smart Defaults

Last-used settings are saved per category in `last_used.json`. On the next generation, the agent pre-fills model, resolution, aspect ratio, format, and style from the last successful generation in that category. Project defaults take priority over last-used defaults.

## A/B Model Comparison

After generating an image, the agent offers to compare with another model. The prompt is **intelligently re-engineered** for the comparison model's character limit (instead of being truncated), preserving creative intent and quality directives. Dropped layers are reported to the user.

## Prompt Fitting

When a prompt exceeds a model's character limit, the system re-engineers it instead of truncating. This is critical for A/B comparisons where a Director's Cut prompt built for NB2 (20K limit) is sent to Seedream 4.5 (3K limit).

**3-tier layer priority:**

| Priority | Layers | Action |
| -------- | ------ | ------ |
| 1 — Must keep | Mode prefix, shot type, description, text placement, project instructions | Never dropped |
| 2 — Important | Inline negatives, mode negatives, quality, camera, lighting | Condensed if needed |
| 3 — Droppable | Depth, atmosphere, composition, micro-details, arch precision | Dropped first |

**Algorithm:** Drop priority-3 layers one at a time (depth first) until the prompt fits. If still over, condense priority-2 layers (shorten "Do not" to "No", remove camera brand attribution, trim filler phrases). Last resort: trim the user description preserving the first sentence.

The `layers_dropped` field in prompt JSON files records which layers were removed for traceability.

## Feedback Learning

The system analyzes evaluation history to provide data-driven recommendations. All recommendations are rule-based (no LLM calls) and displayed as optional hints.

**Minimum thresholds (no premature recommendations):**
- 10 total rated images before any recommendations activate
- 3+ ratings per model/category combination
- 0.5+ star difference before recommending one model over another

**Signals tracked:**
- Best model per category (model x category average rating)
- Best enhancement level per model (model x enhance_level average rating)
- Negative note patterns (keywords in low-rated feedback, e.g., "AI", "wrong")

**Where recommendations appear:**
- After category/style selection: model and enhancement recommendations
- Before generation: negative pattern warnings from past feedback

Preferences are stored in `learned_preferences.json` (git-ignored, auto-generated). Project-scoped preferences are stored in `projects/<slug>/learned_preferences.json`.

## Scripts Log

| Script Name | Purpose | Status |
| ----------- | ------- | ------ |
| `agent.py` | Interactive terminal agent v3 — 12-layer prompt engine, 5 image modes, projects, prompt enhancement, Rich UI | Active |
| `image_cache.py` | Reference image URL caching with 3-day TTL | Active |
| `projects.py` | Customer project management (create, load, save, stats) | Active |
| `description_enhancer.py` | Rule-based description enhancement (vague terms, keywords, imperfections) | Active |
| `prompt_history.py` | Prompt history browsing and reuse with tag filtering | Active |
| `prompt_fitter.py` | Intelligent prompt fitting — progressive layer dropping + condensation for model limits | Active |
| `feedback_learner.py` | Feedback learning — analyzes evaluations to recommend models, enhancement levels | Active |
| `scripts/generate_kie.py` | Headless batch script — takes a JSON prompt file, calls Kie.ai API, polls, downloads image | Active |
| `scripts/get_kie_image.py` | Retrieves an already-submitted task by ID and downloads the result | Active |
