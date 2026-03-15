# MCP Server Prompt Limit Corrections

The `@felores/kie-ai-mcp-server` reports `maxLength: 5000` for ALL models.
This is **incorrect**. The actual limits (verified from kie.ai playground `maxLength` values) differ per model.

## Verified Actual Limits (from kie.ai playground, March 2026)

| Model | API Model ID | MCP Says | Actual Limit | Source |
|-------|-------------|----------|-------------|--------|
| **Nano Banana 2** | `nano-banana-2` | 5,000 | **20,000** | kie.ai/nano-banana-2 playground `maxLength:20000` |
| **Nano Banana Pro** | `nano-banana-pro` | 5,000 | **20,000** | kie.ai/nano-banana-pro playground `maxLength:20000` |
| **Nano Banana Edit** | `google/nano-banana-edit` | 5,000 | **20,000** | kie.ai/nano-banana playground (edit tab) `maxLength:20000` |
| **Nano Banana (v1)** | `google/nano-banana` | 5,000 | **20,000** | kie.ai/nano-banana playground `maxLength:20000` |
| **Seedream 4.0 T2I** | `bytedance/seedream-v4-text-to-image` | 5,000 | **5,000** | kie.ai/seedream-api playground `maxLength:5000` (correct) |
| **Seedream 4.0 Edit** | `bytedance/seedream-v4-edit` | 5,000 | **5,000** | kie.ai/seedream-api playground (edit tab) `maxLength:5000` (correct) |
| **Seedream 4.5 T2I** | `seedream/4.5-text-to-image` | 5,000 | **3,000** | kie.ai/seedream-4-5 playground `maxLength:3000` |
| **Seedream 4.5 Edit** | `seedream/4.5-edit` | 5,000 | **3,000** | kie.ai/seedream-4-5 playground (edit tab) `maxLength:3000` |
| **Seedream V5 Lite T2I** | (via bytedance_seedream_image, version=5-lite) | 5,000 | **~3,000** | kie.ai/seedream5-0-lite playground `maxLength:2995` |
| **Flux 2 Pro T2I** | `flux-2/pro-text-to-image` | 5,000 | **5,000** | kie.ai/flux-2 playground `maxLength:5000` (correct) |
| **Flux 2 Pro I2I** | `flux-2/pro-image-to-image` | 5,000 | **5,000** | kie.ai/flux-2 playground (i2i tab) `maxLength:5000` (correct) |
| **Seedream 3.0** | `bytedance/seedream` | N/A | **5,000** | docs.kie.ai `maxLength:5000` |

## Summary of Errors in MCP Server

1. **Nano Banana family (all variants)**: MCP says 5,000 but actual is **20,000** -- MCP is too restrictive
2. **Seedream 4.5 / V5 Lite**: MCP says 5,000 but actual is **3,000** -- MCP is too permissive (causes API errors)

## Bug Report

Error encountered when sending 4,958 char prompt to `seedream/4.5-edit`:
```
ERROR: No taskId returned. API response:
{
  "code": 500,
  "msg": "The text length cannot exceed the maximum limit",
  "data": null
}
```

## Additional API Parameter Issues (March 2026)

### 1. NB Edit `output_format` — wrong enum value

MCP tool `nano_banana_image` reports `output_format` enum: `["png", "jpg"]`.
But when using `google/nano-banana-edit` directly, the API also accepts `"jpg"` (not `"jpeg"`).

Error encountered when sending `output_format: "jpeg"`:
```
ERROR: No taskId returned. API response:
{
  "code": 500,
  "msg": "output_format is not within the range of allowed options",
  "data": null
}
```

**Fix**: Use `"jpg"` not `"jpeg"`.

### 2. NB Edit missing `resolution` parameter

The `google/nano-banana-edit` model does NOT support `resolution`. It only accepts:
`prompt`, `image_urls`, `image_size`, `output_format`.

When 4K resolution is selected by the user and the API switches to NB Edit,
resolution is silently dropped and the output defaults to ~1K (1344x768).

**Workaround**: Use `nano-banana-2` with `image_input` instead of switching to
`google/nano-banana-edit`. NB2 natively handles edit operations via `image_input`
and preserves `resolution`, `negative_prompt`, `aspect_ratio`, and `output_format`.

### 3. Seedream 4.5 `quality` mapping

Seedream 4.5 / V5 Lite does NOT use `resolution`. Instead it uses `quality`:

- `"basic"` = 2K output
- `"high"` = 3K output (maximum — no 4K support)

MCP tool correctly documents this, but calling code must map user resolution to quality.

### 4. Flux 2 Pro max resolution

MCP reports `resolution` enum: `["1K", "2K"]` — Flux 2 Pro maxes out at 2K, not 4K.

## Recommended Fix for MCP Server

In the tool schema definitions, update `maxLength` per model:

```javascript
// nano_banana_image tool
prompt: { maxLength: 20000 }  // was 5000

// bytedance_seedream_image tool (version-dependent)
// version "4": maxLength 5000 (correct already)
// version "5-lite": maxLength 3000 (was 5000)

// flux2_image tool
prompt: { maxLength: 5000 }  // correct, no change needed
```

## How to Use This File

You can share this file with the MCP server maintainer (@felores) as a bug report,
or reference it when configuring your own prompt truncation logic.
