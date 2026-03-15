"""
Rule-based description enhancement for Kie.ai Image Studio.

Transforms raw user input into richer, more specific descriptions
BEFORE they enter the 12-layer build_prompt() engine.

This module operates ONLY on the user's description text (layer 3).
It does NOT inject camera/lighting/composition terms — those are
handled by build_prompt() layers 4-12.

Enhancement techniques:
- Expand vague terms into specific sensory details
- Convert keyword lists into flowing narrative sentences
- Inject category-appropriate physical imperfections for realism
- Add material/texture specifics the user omitted
- Scale enhancement proportionally to input length
"""

import re

# ── Vague Term Expansions ────────────────────────────────────────────────────
# Maps common vague descriptors to specific, sensory-rich alternatives.
# Applied as whole-word case-insensitive replacements.

VAGUE_TERM_EXPANSIONS = {
    "nice lighting": "warm directional light with soft shadow gradients and natural falloff",
    "good lighting": "well-balanced natural light with defined shadow structure",
    "beautiful": "visually striking with natural proportions and subtle imperfections",
    "pretty": "naturally attractive with delicate features and visible skin texture",
    "handsome": "strong-featured with natural skin texture, defined bone structure, and subtle asymmetry",
    "realistic": "physically accurate with visible micro-texture, natural material variation, and imperfections",
    "high quality": "tack-sharp detail with physically accurate surface rendering and natural tonal range",
    "high-quality": "tack-sharp detail with physically accurate surface rendering and natural tonal range",
    "good looking": "naturally attractive with subtle facial asymmetry and visible skin texture",
    "nice background": "complementary background environment with depth and atmospheric perspective",
    "clean background": "uncluttered background with deliberate negative space",
    "blurry background": "background dissolving through progressive bokeh into diffused color and shape",
    "modern": "contemporary design language with clean geometries and minimal ornamentation",
    "old": "showing natural aging, patina, accumulated wear patterns, and character",
    "vintage": "carrying the marks of decades — faded surfaces, warm patina, and period-appropriate materials",
    "rustic": "rough-hewn natural materials with visible grain, knots, and weathering marks",
    "elegant": "refined proportions with deliberate simplicity and high-quality material presence",
    "dramatic": "high-contrast tonal range with deep shadows and selective highlight emphasis",
    "moody": "low-key atmosphere with rich shadow depth and muted, desaturated tones",
    "bright": "well-illuminated with even diffused light and lifted shadow detail throughout",
    "dark": "low-key illumination with deep shadows and controlled, selective highlight points",
    "warm": "warm color palette with amber, golden, and earth tones pervading the scene",
    "cool": "cool-toned atmosphere with blue-shifted ambient light and desaturated palette",
    "colorful": "rich chromatic saturation with a varied, vibrant color palette across the scene",
    "soft": "gentle gradations between tones, diffused edges, and smooth tonal transitions",
    "sharp": "crisp edge definition with high micro-contrast and resolved fine detail",
    "luxurious": "premium material presence — polished surfaces, rich textures, and meticulous craftsmanship",
    "minimalist": "restrained composition with deliberate negative space, few elements, and clean geometry",
    "cozy": "warm, intimate atmosphere with soft textures, gentle light, and inviting material warmth",
    "futuristic": "sleek geometric forms with luminous surfaces, clean edges, and advanced material finishes",
    "natural": "organic textures, irregular forms, and the uncontrolled beauty of real-world materials",
    "professional": "technically precise execution with controlled conditions and intentional composition",
    "cinematic": "wide-aspect composition with narrative depth, atmospheric perspective, and dramatic tonal range",
    "simple": "uncluttered composition with a single clear focal point and minimal visual elements",
    "detailed": "dense visual information with resolved micro-texture across all surfaces",
    "stunning": "visually arresting with strong compositional impact and tonal drama",
    "amazing": "striking visual presence with strong subject emphasis and technical precision",
    "perfect": "technically impeccable with precise geometry, balanced exposure, and resolved detail",
    "big": "imposing scale dominating the frame, conveying physical mass and presence",
    "small": "diminutive scale within a larger context, emphasizing delicacy and fine proportion",
    "tall": "pronounced vertical emphasis with height conveyed through scale references",
    "shiny": "highly reflective surface with crisp specular highlights and mirror-like material quality",
    "matte": "non-reflective surface with even light absorption and subtle micro-texture",
    "smooth": "continuous surface without visible texture interruption, even tonal gradation",
    "rough": "tactile surface texture with visible irregularity, grain, and material character",
    "glowing": "emanating soft luminosity from within, with light falloff into surrounding space",
    "transparent": "optically clear material showing refraction, internal caustics, and see-through depth",
    "foggy": "atmospheric moisture suspended in air, softening distant elements and diffusing light",
    "rainy": "wet surfaces with reflective sheen, visible droplets, and diffused ambient light",
    "sunny": "direct sunlight creating defined shadows, warm highlights, and strong directional contrast",
    "cloudy": "overcast sky providing even diffuse illumination without harsh shadows",
    "snowy": "fresh snow cover reflecting ambient light, creating high-key luminance with cool blue shadows",
}

# ── Category-Specific Enrichments ────────────────────────────────────────────
# Details appended to the description if not already present, based on category.
# These focus on physical imperfections and material specifics for realism.

CATEGORY_ENRICHMENTS = {
    "portrait": {
        "imperfections": (
            "Visible skin pores varying in size across facial zones, natural under-eye texture, "
            "subtle asymmetry in brow arch, individual strand hair detail catching light, "
            "fine vellus hair along jawline and temples"
        ),
        "check_terms": ["pore", "skin texture", "asymmetr", "vellus", "strand"],
    },
    "product": {
        "imperfections": (
            "Surface micro-texture at forensic detail level — material grain visible, "
            "subtle manufacturing marks, natural color variation across the surface, "
            "light interaction revealing material properties"
        ),
        "check_terms": ["micro-texture", "grain", "manufacturing", "material"],
    },
    "landscape": {
        "imperfections": (
            "Individual leaf detail in near vegetation, bark texture showing lichen and weathering, "
            "geological stratification visible in rock surfaces, soil showing organic matter variation"
        ),
        "check_terms": ["leaf detail", "bark", "lichen", "geological", "soil"],
    },
    "architecture-exterior": {
        "imperfections": (
            "Natural material weathering visible on exposed surfaces — hairline cracking, "
            "water staining at drip edges, mortar joint variation between brick units, "
            "paving joints with accumulated debris, vegetation responding to ambient breeze"
        ),
        "check_terms": ["weathering", "cracking", "mortar", "staining", "paving"],
    },
    "architecture-interior": {
        "imperfections": (
            "Material surfaces at intimate viewing distance — wood grain following natural growth rings, "
            "subtle scuff marks on flooring from daily use, dust settling in recessed joints, "
            "fingerprint traces on polished surfaces"
        ),
        "check_terms": ["wood grain", "scuff", "dust", "fingerprint", "growth ring"],
    },
    "architecture-detail": {
        "imperfections": (
            "Forensic construction detail — formwork imprints in concrete, aggregate exposure, "
            "fastener heads in metal cladding, sealant lines at joints, "
            "patina of time and weather on every edge"
        ),
        "check_terms": ["formwork", "aggregate", "fastener", "sealant", "patina"],
    },
    "scene": {
        "imperfections": (
            "Environmental surfaces showing wear from regular use — scuffed floors, "
            "paint texture and aging on walls, objects carrying patina of daily handling, "
            "dust settling in corners and crevices"
        ),
        "check_terms": ["wear", "scuff", "patina", "aging", "dust"],
    },
    "miscellaneous": {
        "imperfections": (
            "Physical-world imperfections appropriate to the subject — natural material variation, "
            "subtle asymmetry, surface micro-texture, and evidence of real-world interaction"
        ),
        "check_terms": ["imperfection", "variation", "asymmetry", "micro-texture"],
    },
}

# Terms that belong to layers 4-12 — never inject these in the enhancer
_LAYER_EXCLUSION_TERMS = {
    "rule of thirds", "golden ratio", "leading line", "visual hierarchy",  # composition
    "bokeh", "depth of field", "focal plane",  # camera
    "iso", "aperture", "shutter speed", "f/", "mm lens",  # camera math
    "key light", "fill light", "rim light", "softbox",  # lighting
    "three-point", "butterfly lighting", "rembrandt",  # lighting setups
}


def enhance_description(raw_text: str, category: str, style: str = "photorealistic") -> str:
    """Transform raw user input into a richer description.

    Operates on layer 3 only. Does NOT add camera/lighting/composition
    (those are handled by build_prompt layers 4-12).

    Returns the enhanced description string.
    """
    if not raw_text or not raw_text.strip():
        return raw_text

    text = raw_text.strip()

    # Step 1: Detect and convert keyword-list input to narrative
    text = _keywords_to_narrative(text)

    # Step 2: Expand vague terms
    text = _expand_vague_terms(text)

    # Step 3: Add category-specific imperfections (if not already present)
    text = _inject_imperfections(text, category)

    # Step 4: Ensure sensory grounding for short inputs
    if len(raw_text.strip()) < 100:
        text = _ensure_sensory_details(text, category, style)

    return text


def _expand_vague_terms(text: str) -> str:
    """Replace vague descriptors with specific sensory details."""
    result = text
    for vague, specific in VAGUE_TERM_EXPANSIONS.items():
        # Whole-word, case-insensitive replacement
        pattern = re.compile(r'\b' + re.escape(vague) + r'\b', re.IGNORECASE)
        result = pattern.sub(specific, result)
    return result


def _keywords_to_narrative(text: str) -> str:
    """Detect comma-separated keyword lists and convert to flowing narrative.

    'sunset, beach, woman, red dress' ->
    'A scene featuring a sunset, a beach, a woman, and a red dress'
    """
    # Heuristic: 3+ comma-separated segments, each under 5 words, no verbs detected
    segments = [s.strip() for s in text.split(",")]
    if len(segments) < 3:
        return text

    # Check if segments are short (keyword-like)
    avg_words = sum(len(s.split()) for s in segments) / len(segments)
    if avg_words > 4:
        return text  # Too long to be keywords, probably already narrative

    # Check for verb indicators (likely already a sentence)
    verb_indicators = r'\b(is|are|was|were|has|have|had|stands?|sits?|walks?|runs?|looks?|wears?|holds?|shows?)\b'
    if re.search(verb_indicators, text, re.IGNORECASE):
        return text

    # Convert to narrative
    if len(segments) == 2:
        return f"A scene featuring {segments[0]} and {segments[1]}"
    items = ", ".join(segments[:-1]) + f", and {segments[-1]}"
    return f"A scene featuring {items}"


def _inject_imperfections(text: str, category: str) -> str:
    """Add category-appropriate physical imperfections if not already present."""
    enrichment = CATEGORY_ENRICHMENTS.get(category, CATEGORY_ENRICHMENTS.get("miscellaneous", {}))
    if not enrichment:
        return text

    # Check if any enrichment terms are already present
    text_lower = text.lower()
    check_terms = enrichment.get("check_terms", [])
    already_present = sum(1 for term in check_terms if term in text_lower)
    if already_present >= 2:
        return text  # User already described enough detail

    imperfections = enrichment.get("imperfections", "")
    if imperfections:
        text = f"{text}. {imperfections}"
    return text


def _ensure_sensory_details(text: str, category: str, style: str) -> str:
    """For short inputs, add sensory grounding details."""
    text_lower = text.lower()

    # Check if text already has sensory modifiers
    sensory_terms = ["texture", "temperature", "feel", "touch", "weight",
                     "surface", "material", "tangible", "tactile"]
    has_sensory = any(term in text_lower for term in sensory_terms)
    if has_sensory:
        return text

    # Add a brief sensory grounding based on style
    sensory_additions = {
        "photorealistic": "Every surface carries tangible physical presence and material authenticity.",
        "documentary": "The scene captured with unfiltered, candid authenticity.",
        "editorial": "Every element precisely composed with intentional visual clarity.",
        "artistic": "The scene imbued with expressive tonal depth and deliberate visual tension.",
        "product mockup": "Every material surface rendered with precise physical accuracy.",
    }
    addition = sensory_additions.get(style, sensory_additions.get("photorealistic", ""))
    if addition:
        text = f"{text}. {addition}"
    return text
