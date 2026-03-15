"""
Intelligent prompt fitting for model-specific character limits.

Instead of naive truncation, this module progressively drops low-priority
enhancement layers and condenses remaining ones to fit within a model's
prompt limit while preserving creative intent and quality control.
"""

import re


# Layer priority: ordered from MOST expendable to LEAST expendable.
# When we need to shed characters, we drop from the top of this list first.
DROPPABLE_LAYERS = [
    "depth",
    "atmosphere",
    "composition",
    "micro_details",
    "arch_precision",
    "render_negatives",
]

# These layers are condensed (shortened) if dropping all droppable layers
# is still not enough. Ordered from least to most critical.
CONDENSABLE_LAYERS = [
    "lighting",
    "camera",
    "quality",
    "mode_negatives",
    "inline_negatives",
]

# Priority 1 layers: never dropped, only trimmed as last resort.
CORE_LAYERS = [
    "mode_prefix",
    "shot_type",
    "description",
    "text_placement",
    "project_instructions",
]

# The canonical order in which layers are joined to form the final prompt.
# This must match the order used in build_prompt().
LAYER_ORDER = [
    "mode_prefix",
    "shot_type",
    "description",
    "text_placement",
    "project_instructions",
    "composition",
    "atmosphere",
    "depth",
    "lighting",
    "camera",
    "micro_details",
    "arch_precision",
    "quality",
    "inline_negatives",
    "render_negatives",
    "mode_negatives",
]

# Regex condensation rules applied to priority-2 layers when dropping
# alone isn't enough. Each tuple is (pattern, replacement).
CONDENSE_RULES = [
    # Remove camera brand/model attribution (keep the lens specs)
    (r"Shot on a [A-Z][A-Za-z0-9 ]+?,\s*", ""),
    (r"Shot with vintage [A-Za-z0-9 ]+? lens on [A-Za-z0-9 ]+?,\s*", ""),
    # Shorten "Do not" to "No"
    (r"Do not\b", "No"),
    # Remove filler phrases
    (r"with zero tolerance for deviation\.?\s*", ""),
    (r"at measurement-grade fidelity\.?\s*", ""),
    (r"indistinguishable from work published in [^.]+\.\s*", ""),
    # Shorten common verbose patterns
    (r"Hyper-realistic,?\s*", ""),
    (r"zero post-processing\.?\s*", "No post-processing. "),
    (r"No retouching whatsoever\.?", "No retouching."),
    # Compress double spaces left by removals
    (r"  +", " "),
]


def _join_layers(layer_parts, exclude=None):
    """Join layer parts in canonical order, optionally excluding some."""
    exclude = exclude or set()
    parts = []
    for name in LAYER_ORDER:
        if name in exclude:
            continue
        text = layer_parts.get(name, "")
        if text and text.strip():
            parts.append(text.strip())
    return " ".join(parts)


def _condense_text(text):
    """Apply condensation rules to shorten text without losing meaning."""
    result = text
    for pattern, replacement in CONDENSE_RULES:
        result = re.sub(pattern, replacement, result)
    return result.strip()


def fit_prompt(layer_parts, char_limit):
    """
    Fit a prompt to a character limit by intelligently dropping and condensing layers.

    Args:
        layer_parts: dict mapping layer names to their text content.
                     Keys should match LAYER_ORDER names.
        char_limit: maximum character count for the final prompt.

    Returns:
        (fitted_prompt, dropped_layers): the fitted prompt string and a list
        of layer names that were dropped to fit.
    """
    # Fast path: everything fits
    full = _join_layers(layer_parts)
    if len(full) <= char_limit:
        return full, []

    # Phase 1: Progressive layer dropping (lowest priority first)
    dropped = []
    excluded = set()
    for layer_name in DROPPABLE_LAYERS:
        if not layer_parts.get(layer_name, "").strip():
            continue  # Already empty, skip
        excluded.add(layer_name)
        dropped.append(layer_name)
        candidate = _join_layers(layer_parts, exclude=excluded)
        if len(candidate) <= char_limit:
            return candidate, dropped

    # Phase 2: Condense remaining layers (priority 2)
    condensed_parts = dict(layer_parts)
    for layer_name in CONDENSABLE_LAYERS:
        text = condensed_parts.get(layer_name, "")
        if text:
            condensed_parts[layer_name] = _condense_text(text)

    candidate = _join_layers(condensed_parts, exclude=excluded)
    if len(candidate) <= char_limit:
        return candidate, dropped

    # Phase 3: Also condense core layers (except description)
    for layer_name in CORE_LAYERS:
        if layer_name == "description":
            continue
        text = condensed_parts.get(layer_name, "")
        if text:
            condensed_parts[layer_name] = _condense_text(text)

    candidate = _join_layers(condensed_parts, exclude=excluded)
    if len(candidate) <= char_limit:
        return candidate, dropped

    # Phase 4: Last resort — trim the user description
    # Calculate how much space the non-description layers take
    desc_backup = condensed_parts.get("description", "")
    condensed_parts["description"] = ""
    overhead = len(_join_layers(condensed_parts, exclude=excluded))
    available = char_limit - overhead - 1  # -1 for the joining space

    if available > 0 and desc_backup:
        # Preserve the first sentence, then trim
        first_sentence_match = re.match(r"^[^.!?]+[.!?]", desc_backup)
        if first_sentence_match and len(first_sentence_match.group(0)) <= available:
            # Fit as much as possible after the first sentence
            trimmed = desc_backup[:available].rstrip()
            # Don't cut mid-word
            last_space = trimmed.rfind(" ", len(first_sentence_match.group(0)))
            if last_space > 0:
                trimmed = trimmed[:last_space] + "..."
            condensed_parts["description"] = trimmed
        else:
            # Even first sentence is too long — hard trim
            trimmed = desc_backup[:available].rstrip()
            last_space = trimmed.rfind(" ")
            if last_space > 20:
                trimmed = trimmed[:last_space] + "..."
            condensed_parts["description"] = trimmed

    candidate = _join_layers(condensed_parts, exclude=excluded)
    return candidate, dropped
