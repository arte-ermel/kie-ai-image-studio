---
name: Nano Banana Image Generation Master
description: A formalized skill for generating hyper-realistic, highly-controlled images using Nano Banana 2 (Gemini 3.1 Flash) and Nano Banana Pro (Gemini 3.0 Pro) through parameterized JSON prompting.
---

# Nano Banana Image Generation Master

## Models

### Integrated Models (agent.py)

| Model | API ID (T2I) | Edit Behavior | Prompt Limit | Max Res | Refs | Best For |
|-------|-------------|--------------|-------------|---------|------|----------|
| Nano Banana 2 | `nano-banana-2` | Native (`image_input`) | **20,000** chars | 4K | 14 | Fast iteration, realism, multi-ref |
| Nano Banana Pro | `nano-banana-pro` | none | **20,000** chars | 1K | 8 | Typography, logos, max fidelity |
| Seedream 4.0 (V4) | `bytedance/seedream-v4-text-to-image` | `bytedance/seedream-v4-edit` | 5,000 chars | 4K | 10 | Budget quality, color accuracy |
| Seedream V5 Lite | `seedream/4.5-text-to-image` | `seedream/4.5-edit` | **3,000** chars | 3K (high) | 14 | Best value, 2K/3K output, spatial |
| Flux 2 Pro | `flux-2/pro-text-to-image` | `flux-2/pro-image-to-image` | 5,000 chars | 2K | 8 | Fine detail, character consistency |

**When to use Pro:** logos, signage with precise text, multi-constraint scenes with 5+ simultaneous requirements, professional product shots needing maximum detail.

**When to use NB2:** general realism, portraits, landscapes, faster turnaround, reference image compositions (up to 14 refs).

### Nano Banana Family

There is no "Nano Banana 3.1" — the "3.1" refers to the underlying Gemini version (Gemini 3.1 Flash), not a NB version.

| Kie.ai Name | Model ID | Google Model | Status |
|------------|----------|-------------|--------|
| Nano Banana (v1) | `google/nano-banana` | Gemini 2.5 Flash | Legacy |
| Nano Banana 2 | `nano-banana-2` | Gemini 3.1 Flash | Current default |
| Nano Banana Pro | `nano-banana-pro` | Gemini 3.0 Pro | Best quality |
| Nano Banana Edit | `google/nano-banana-edit` | Gemini Edit | Legacy — avoid, use NB2 with `image_input` |

### Available via MCP (Not in agent.py)

MCP-verified models available through `kie-ai-mcp` tools:

| Model | MCP Tool | Modes | Max Refs | Key Feature |
|-------|----------|-------|----------|-------------|
| Midjourney v5-7 | `midjourney_generate` | T2I, I2I, style ref, omni ref, video | 10 | Full MJ access + video |
| GPT-4o Image | `openai_4o_image` | T2I, mask edit, variants | 5 | Mask-based editing, 1-4 variants |
| Grok Imagine | `grok_imagine` | T2I, T2V, I2V, upscale | 1 | 4-in-1 (image+video+upscale) |
| Qwen | `qwen_image` | T2I, edit | 1 | CFG scale, inference steps control |
| Flux Kontext | `flux_kontext_image` | T2I, edit | 1 | Pro/Max tiers, prompt upsampling |
| Flux 2 Flex | `flux2_image` (flex) | T2I, I2I | 8 | $0.07/1K, $0.12/2K |
| Z-Image | `z_image` | T2I only | 0 | Ultra-cheap ~$0.004, bilingual text |
| Ideogram V3 | `ideogram_reframe` | Reframe only | 1 | Turbo/balanced/quality speeds |
| Recraft | `recraft_remove_background` | BG removal | 1 | Max 5MB, 16MP input |
| Topaz | `topaz_upscale_image` | 1-8x upscale | 1 | Max 20,000px output |
| Imagen 4 | docs only (no MCP) | T2I | - | Fast/standard/ultra tiers |

## API Parameters (per model family)

**NB2 / NB Pro:**

```json
{
  "model": "nano-banana-2",
  "input": {
    "prompt": "string (required, max 20000 chars)",
    "negative_prompt": "string (optional)",
    "aspect_ratio": "1:1 | 1:4 | 1:8 | 2:3 | 3:2 | 3:4 | 4:1 | 4:3 | 4:5 | 5:4 | 8:1 | 9:16 | 16:9 | 21:9 | auto",
    "resolution": "1K | 2K | 4K",
    "output_format": "jpg | png",
    "image_input": ["array of image URLs — up to 14 for NB2, 8 for Pro"],
    "google_search": false
  }
}
```

**NB Edit (legacy — prefer NB2 with `image_input` instead):**

```json
{
  "model": "google/nano-banana-edit",
  "input": {
    "prompt": "string",
    "image_urls": ["array of image URLs"],
    "output_format": "png | jpg",
    "image_size": "1:1"
  }
}
```

> **Warning:** NB Edit does NOT support `resolution` or `negative_prompt`. Output defaults to ~1K.
> Use `nano-banana-2` with `image_input` for edit operations to preserve all parameters.

**Seedream 4.0:**

```json
{
  "model": "bytedance/seedream-v4-text-to-image",
  "input": {
    "prompt": "string (max 5000 chars — correct for Seedream 4.0)",
    "image_size": "square | square_hd | portrait_4_3 | portrait_3_2 | portrait_16_9 | landscape_4_3 | landscape_3_2 | landscape_16_9 | landscape_21_9",
    "image_resolution": "1K | 2K | 4K",
    "max_images": 1
  }
}
```

**Seedream V5 Lite (T2I + Edit):**

MCP names this "V5 Lite" (version=5-lite). Kie.ai docs call it "Seedream 4.5". Same model.

```json
{
  "model": "seedream/4.5-text-to-image",
  "input": {
    "prompt": "string (max 3000 chars — LOWER than other models!)",
    "aspect_ratio": "1:1 | 4:3 | 3:4 | 16:9 | 9:16 | 2:3 | 3:2 | 21:9",
    "quality": "basic (2K output) | high (3K output, max resolution)",
    "image_urls": ["up to 14 refs — only for edit mode"]
  }
}
```

**Flux 2 Pro (T2I, max 2K resolution):**

```json
{
  "model": "flux-2/pro-text-to-image",
  "input": {
    "prompt": "string (max 5000 chars)",
    "aspect_ratio": "1:1",
    "resolution": "1K | 2K"
  }
}
```

## Goal
The purpose of this skill is to provide a standardized, highly controlled method for generating images using Nano Banana 2 or Pro via the Kie.ai API. By strictly enforcing a structured JSON parameter schema, this skill neutralizes native model biases (like over-smoothing, dataset-averaging, or "plastic" AI styling) and ensures raw, unretouched, hyper-realistic outputs.

## Prerequisites
- Access to the `generate_image` tool.
- A clear understanding of the user's desired Subject, Lighting, and Camera characteristics.

## Core Schema Structure
When constructing a prompt for the `generate_image` tool, you **MUST** use the following JSON schema as the foundation. Fill in the string values with extreme, microscopic detail.

```json
{
  "task": "string - High-level goal (e.g., 'sports_selfie_collage', 'single_macro_portrait')",
  
  "output": {
    "type": "string - e.g., 'single_image', '4-panel_collage'",
    "layout": "string - e.g., '1x1', '2x2_grid', 'side-by-side'",
    "aspect_ratio": "string - e.g., '3:4', '16:9', '4:5'",
    "resolution": "string - e.g., 'ultra_high', 'medium_low'",
    "camera_style": "string - e.g., 'smartphone_front_camera', 'professional_dslr'"
  },

  "image_quality_simulation": {
    "sharpness": "string - e.g., 'tack_sharp', 'slightly_soft_edges'",
    "noise": "string - e.g., 'unfiltered_sensor_grain', 'visible_film_grain', 'clean_digital'",
    "compression_artifacts": "boolean - true if attempting to simulate uploaded UGC",
    "dynamic_range": "string - e.g., 'limited', 'hdr_capable'",
    "white_balance": "string - e.g., 'slightly_warm', 'cool_fluorescent'",
    "lens_imperfections": [
      "array of strings - e.g., 'subtle chromatic aberration', 'minor lens distortion', 'vignetting'"
    ]
  },

  "subject": {
    "type": "string - e.g., 'human_portrait', 'nature_macro', 'infographic_flatlay'",
    "human_details": {
      "//": "Use this block ONLY for human subjects",
      "identity": "string",
      "appearance": "string - Extremely specific (e.g., visible pores, mild redness)",
      "outfit": "string"
    },
    "object_or_nature_details": {
      "//": "Use this block for non-human subjects",
      "material_or_texture": "string - e.g., 'brushed aluminum', 'dew-covered velvety petals'",
      "wear_and_tear": "string - e.g., 'subtle scratches on the anodized finish', 'browning edges on leaves'",
      "typography": "string - e.g., 'clean sans-serif overlaid text, perfectly legible'"
    }
  },

  "multi_panel_layout": {
    "grid_panels": [
      {
        "panel": "string - e.g., 'top_left', 'full_frame' (if not a grid)",
        "pose": "string - e.g., 'slight upward selfie angle, relaxed smile'",
        "action": "string - e.g., 'holding phone with one hand, casual posture'"
      }
    ]
  },

  "environment": {
    "location": "string - e.g., 'gym or outdoor sports area'",
    "background": "string - What is behind the subject (e.g., 'blurred gym equipment')",
    "lighting": {
      "type": "string - e.g., 'natural or overhead gym lighting', 'harsh direct sunlight'",
      "quality": "string - e.g., 'uneven, realistic, non-studio', 'high-contrast dramatic'"
    }
  },

  "embedded_text_and_overlays": {
    "text": "string (optional)",
    "location": "string (optional)"
  },

  "structural_preservation": {
    "preservation_rules": [
      "array of strings - e.g., 'Exact physical proportions must be preserved'"
    ]
  },

  "controlnet": {
    "pose_control": {
      "model_type": "string - e.g., 'DWPose'",
      "purpose": "string",
      "constraints": ["array of strings"],
      "recommended_weight": "number"
    },
    "depth_control": {
      "model_type": "string - e.g., 'ZoeDepth'",
      "purpose": "string",
      "constraints": ["array of strings"],
      "recommended_weight": "number"
    }
  },

  "explicit_restrictions": {
    "no_professional_retouching": "boolean - typically true for realism",
    "no_studio_lighting": "boolean - typically true for candid shots",
    "no_ai_beauty_filters": "boolean - mandatory true to avoid plastic look",
    "no_high_end_camera_look": "boolean - true if simulating smartphones"
  },

  "negative_prompt": {
    "forbidden_elements": [
      "array of strings - Massive list of 'AI style' blockers required for extreme realism. Example stack: 'anatomy normalization', 'body proportion averaging', 'dataset-average anatomy', 'wide-angle distortion not in reference', 'lens compression not in reference', 'cropping that removes volume', 'depth flattening', 'mirror selfies', 'reflections', 'beautification filters', 'skin smoothing', 'plastic skin', 'airbrushed texture', 'stylized realism', 'editorial fashion proportions', 'more realistic reinterpretation'"
    ]
  }
}
```

## Paradigm 2: The Dense Narrative Format (Optimized for APIs like Kie.ai)
When executing API calls to standard generation endpoints (which often only accept string prompts), it is incredibly powerful to condense the logic above into a dense, flat JSON string containing a massive descriptive text block.

```json
{
  "prompt": "string - A dense, ultra-descriptive narrative. Use specific camera math (85mm lens, f/1.8, ISO 200), explicit flaws (visible pores, mild redness, subtle freckles, light acne marks), lighting behavior (direct on-camera flash creating sharp highlights), and direct negative commands (Do not beautify or alter facial features).",
  "negative_prompt": "string - A comma-separated list of explicit realism blockers (no plastic skin, no CGI).",
  "image_input": [
    "array of strings (URLs) - Optional. Input images to transform or use as reference (up to 14). Formatting: URL to jpeg, png, or webp. Max size: 30MB."
  ],
  "api_parameters": {
    "google_search": "boolean - Optional. Use Google Web Search grounding",
    "resolution": "string - Optional. '1K', '2K', or '4K' (default 1K)",
    "output_format": "string - Optional. 'jpg' or 'png' (default jpg)",
    "aspect_ratio": "string - Optional. Overrides CLI aspect_ratio (e.g., '16:9', '4:5', 'auto')"
  },
  "settings": {
    "resolution": "string",
    "style": "string - e.g., 'documentary realism'",
    "lighting": "string - e.g., 'direct on-camera flash'",
    "camera_angle": "string",
    "depth_of_field": "string - e.g., 'shallow depth of field'",
    "quality": "string - e.g., 'high detail, unretouched skin'"
  }
}
```

## Best Practices & Natural Language Hacks

1.  **Camera Mathematics:** Always define exact focal length, aperture, and ISO (e.g., `85mm lens, f/2.0, ISO 200`). This forces the model to mimic optical physics rather than digital rendering.
2.  **Explicit Imperfections:** Words like "realistic" are not enough. Dictate flaws: `mild redness`, `subtle freckles`, `light acne marks`, `unguided grooming`.
3.  **Direct Commands:** Use imperative negative commands *inside* the positive prompt paragraph: `Do not beautify or alter facial features. No makeup styling.`
4.  **Lighting Behavior:** Don't just name the light, name what it does: `direct flash photography, creating sharp highlights on skin and a slightly shadowed background.`
5.  **Non-Human Materials (Products/Nature):** When generating non-humans, replace skin/outfit logic with extreme material physics. Define surface scoring (e.g., "micro-scratches on anodized aluminum"), light scattering (e.g., "subsurface scattering through dew-covered petals"), or graphic layouts (e.g., "flat-lay composition, clean sans-serif typography").
6.  **Mandatory Negative Stack:** You MUST include the extensive negative prompt block (e.g., forbidding "skin smoothing" and "anatomy normalization").
7.  **Avoid Over-Degradation (The Noise Trap):** While simulating camera flaws (like `compression artifacts`) can help realism, pushing extreme `ISO 3200` or `heavy film grain` in complex, contrast-heavy environments (like neon night streets) actually triggers the model's "digital art/illustration" biases. Keep ISO settings below 800 and rely on *physical subject imperfections* (like peach fuzz or asymmetrical pores) rather than heavy camera noise to sell the realism.

## Master Reference Guide
If you require the absolute full schema breakdown, parameter options, or the complex JSON structing for multi-panel grids, refer to the root project document:
[Master Prompt Reference Guide](master_prompt_reference.md)

## Execution via Kie.ai (Python Workflow)

When executing Nano Banana 2 prompts against the Kie.ai API, bypass the standard `generate_image` tool and use the dedicated Python pipeline.

**Prerequisites:**
1. Your `.env` file must contain `KIE_API_KEY="your_key"`.
2. A JSON prompt file matching the **Dense Narrative Format** saved in `/prompts/`.

**Interactive agent (recommended):**
```bash
python agent.py
```

**Batch / headless execution:**
```bash
python scripts/generate_kie.py ./prompts/your_prompt.json ./images/output_image.jpg "4:5"
```
*(The aspect ratio parameter defaults to "auto" if omitted).*

**Retrieve an existing task by ID:**
```bash
python scripts/get_kie_image.py <taskId> ./images/output_image.jpg
```

## How to use this skill
When a user asks you to generate a highly detailed, realistic, or complex image, you must construct the prompt string formatted EXACTLY like the JSON schema above. Pass that entire JSON string as the `Prompt` argument to the `generate_image` tool.

---

## Updated Best Practices (Gemini 3.1 Flash / 3.0 Pro — 2026 Research)

### Core Principle: Narrative Over Keywords
**Always write a descriptive paragraph, never a keyword list.** Google's official guidance confirms narrative-based prompting increases output quality 3.2x and reduces generation failures by 68% compared to keyword dumps.

### Optimal Prompt Structure
```
[Shot type] + [Subject + action/state] + [Environment + setting] + [Lighting behavior] + [Camera/lens math] + [Texture/material detail] + [Inline negative commands]
```

**Example (portrait):**
> "Close-up portrait photograph of a 28-year-old man sitting at a wooden café table, slightly leaning forward with a casual relaxed expression. Warm late-afternoon light streaming through a window to camera-left, creating natural side-lighting with gentle shadow on the right cheek. Shot on a Sony A7 IV, 85mm f/1.8 lens, ISO 200, 1/250s. Skin shows natural texture with visible pores, subtle five o'clock shadow, slight redness around the nose. No beauty filters. Do not smooth skin."

### Gemini 3.1 Flash Specific Improvements
- **Multi-step instructions** — NB2 handles 5+ simultaneous constraints reliably. Stack them: lighting + pose + texture + environment + mood simultaneously.
- **Physical plausibility** — Exploit NB2's improved physics understanding: `"the glass casting a distorted refraction pattern on the table"`, `"steam rising from the mug, slightly backlit"`.
- **Better text rendering** — For in-image text, be explicit: `"the words 'OPEN 24H' in a worn neon font, slightly flickering, mounted above the door"`. Use Pro model for precision typography.
- **Multilingual** — NB2 understands prompts in multiple languages natively.
- **Inline negative commands are more effective** than separate `negative_prompt` for these models: `"Do not add makeup. No retouching. Do not idealize proportions."` inside the positive prompt.

### Style Presets — Prompt Injections

**Photorealistic:**
> Shot on [camera body], [lens] f/[aperture], ISO [value]. Hyper-realistic, unretouched. Natural skin texture with visible pores, subtle micro-imperfections. No beauty filters. No plastic look. Documentary realism. Do not smooth skin.

**Documentary:**
> Candid, unposed, available light only. 35mm lens, f/5.6, ISO 800. Raw, reportage style. Gritty texture, true-to-life colors. No post-processing gloss.

**Editorial:**
> Clean, sharp, magazine-quality. Hasselblad medium format, 80mm f/2.8, ISO 100. High contrast, precise composition. Color-graded but naturalistic.

**Product Mockup:**
> Commercial studio photography. 50mm macro lens, f/11, ISO 50. Three-point softbox lighting, no harsh shadows. Clean neutral background. Crisp material detail. No lens distortion.

**Artistic:**
> Painterly rendering with expressive composition. Rich tonal contrast, deliberate stylistic choices. Inspired by [specific artistic movement or photographer].

### Mandatory Negative Prompt Stack (2026)
Always include these as a baseline. Add subject-specific blockers on top.

```
blurry, low resolution, distorted, extra fingers, extra limbs,
anatomy normalization, body proportion averaging, dataset-average anatomy,
skin smoothing, plastic skin, airbrushed texture, beauty filters,
stylized realism, editorial fashion proportions, depth flattening,
lens compression not in reference, wide-angle distortion not in reference,
overexposed, underexposed, heavy makeup, unrealistic skin,
cartoon, CGI, oversaturated colors, more realistic reinterpretation,
cropping that removes volume, reflections, mirror artifacts,
watermark, text overlay, signature
```

### Reference Images
- **NB2:** up to 14 reference images (JPEG, PNG, WEBP, max 30MB total)
- **Pro:** up to 8 reference images
- For character consistency: provide 3-5 reference angles. State: `"maintain exact facial structure and proportions from the reference images"`
- For style transfer: provide 1-2 style reference images. State: `"apply the lighting and color grading from the reference image to the new scene"`

### Resolution & Cost Guide
| Resolution | Use Case | NB2 Cost | Pro Cost |
|------------|----------|----------|----------|
| 1K | Drafting, iteration | $0.025 | $0.04 |
| 2K | Final assets, social media | $0.04 | — |
| 4K | Print, hero images | $0.06 | — |

### Agent Workflow
Use `agent.py` in the project root for the interactive terminal agent. It handles:
- Model selection (NB2 vs Pro)
- Resolution and aspect ratio selection
- Category-aware prompt building
- Automatic negative prompt injection
- Image + prompt organized saving to `/images/<category>/` and `/prompts/<category>/` (architecture sub-categories each get their own folder)
