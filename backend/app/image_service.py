"""
LYFTR AI - Image Generation Service
Generates images using Pollinations.ai (free, no API key required).
Optionally uses Stability AI if STABILITY_API_KEY is configured.
"""
import os
import uuid
import time
import logging
import httpx
from urllib.parse import quote

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Style prompt modifiers
# ---------------------------------------------------------------------------

STYLE_PROMPTS = {
    "photorealistic": "photorealistic, ultra detailed, 8k, professional photography, natural lighting",
    "cinematic": "cinematic shot, movie scene, dramatic lighting, film grain, anamorphic lens",
    "anime": "anime style, detailed anime art, studio quality, vibrant colors, clean linework",
    "digital_art": "digital art, concept art, artstation trending, detailed illustration",
    "3d_rendering": "3D rendering, octane render, unreal engine 5, ultra photorealistic, ambient occlusion",
    "illustration": "professional illustration, vector art style, clean design, vibrant",
    "watercolor": "watercolor painting, artistic, soft washes, traditional media, paper texture",
    "fantasy": "fantasy art, magical, epic fantasy landscape, detailed, mystical atmosphere",
    "architecture": "architectural visualization, modern architecture, professional rendering, detailed",
    "product_photography": "product photography, studio lighting, white background, commercial quality",
}

# Aspect ratio → (width, height)
ASPECT_RATIOS = {
    "1:1":  (1024, 1024),
    "16:9": (1360, 768),
    "9:16": (768, 1360),
    "4:3":  (1024, 768),
    "3:2":  (1152, 768),
}

CONTENT_CATEGORIES = ["safe", "adult", "violent", "disturbing"]

# Blocked terms for application-level content moderation (backend-enforced)
BLOCKED_TERMS_SAFE = [
    "naked", "nude", "explicit", "pornographic", "porn", "xxx",
    "sexual", "nsfw", "genitals", "erotic", "hentai",
]

BLOCKED_TERMS_ALL_USERS = [
    "child abuse", "csam", "exploitation", "minor nude", "child nude",
    "gore", "beheading", "torture detailed",
]


def _build_prompt(prompt: str, style: str) -> str:
    """Combine user prompt with style modifier."""
    style_suffix = STYLE_PROMPTS.get(style, "")
    full_prompt = prompt.strip()
    if style_suffix:
        full_prompt = f"{full_prompt}, {style_suffix}"
    return full_prompt


def _check_content_policy(prompt: str, role: str, allowed_categories: list) -> str | None:
    """
    Check prompt against application content policy (backend-enforced).
    Returns an error string if blocked, None if allowed.
    """
    prompt_lower = prompt.lower()

    # Always blocked for everyone
    for term in BLOCKED_TERMS_ALL_USERS:
        if term in prompt_lower:
            return f"This prompt contains content that is never allowed: '{term}'."

    # Blocked for non-authorized_creator roles (or if 'adult' not in allowed_categories)
    if role not in ("authorized_creator", "admin") or "adult" not in allowed_categories:
        for term in BLOCKED_TERMS_SAFE:
            if term in prompt_lower:
                return (
                    "This prompt contains content restricted to Authorized Creators. "
                    "Contact an administrator to request elevated permissions."
                )

    return None


async def generate_image_pollinations(
    prompt: str,
    style: str = "photorealistic",
    aspect_ratio: str = "1:1",
    seed: int | None = None,
    nologo: bool = True,
) -> dict:
    """
    Generate an image via Pollinations.ai and return metadata.
    Returns a dict with image_url, provider, model, width, height, latency_ms.
    Note: Pollinations returns the image as a redirect/direct URL that the frontend
    can use directly — we return the URL rather than storing binary data in SQLite.
    """
    width, height = ASPECT_RATIOS.get(aspect_ratio, (1024, 1024))
    full_prompt = _build_prompt(prompt, style)
    encoded = quote(full_prompt, safe="")

    params = [
        f"width={width}",
        f"height={height}",
        "safe=true",          # Always request safe mode from provider
    ]
    if nologo:
        params.append("nologo=true")
    if seed is not None:
        params.append(f"seed={seed}")

    url = f"https://image.pollinations.ai/prompt/{encoded}?{'&'.join(params)}"
    headers = {"Accept": "image/*"}
    pollinations_key = os.getenv("POLLINATIONS_API_KEY", "").strip()
    if pollinations_key:
        headers["Authorization"] = f"Bearer {pollinations_key}"

    start = time.monotonic()
    # Verify the image URL generates successfully with a GET request.
    async with httpx.AsyncClient(timeout=60.0, follow_redirects=True) as client:
        try:
            resp = await client.get(url, headers=headers)
            if resp.status_code == 402:
                raise RuntimeError(
                    "Pollinations.ai returned HTTP 402 (provider quota/API key required). "
                    "Configure POLLINATIONS_API_KEY on the backend or try again later."
                )
            if resp.status_code != 200:
                raise RuntimeError(
                    f"Pollinations.ai returned HTTP {resp.status_code}. "
                    "The generation service may be temporarily unavailable."
                )
            final_url = str(resp.url)
        except httpx.TimeoutException:
            raise RuntimeError("Image generation timed out. Please try again.")
        except httpx.RequestError as e:
            raise RuntimeError(f"Image generation service unreachable: {e}")

    latency_ms = round((time.monotonic() - start) * 1000, 1)

    return {
        "image_url": url,          # Stable CDN URL with same params
        "final_url": final_url,
        "provider": "pollinations.ai",
        "model": "sana",
        "style": style,
        "aspect_ratio": aspect_ratio,
        "width": width,
        "height": height,
        "prompt_used": full_prompt,
        "latency_ms": latency_ms,
    }


async def generate_images(
    prompt: str,
    style: str = "photorealistic",
    aspect_ratio: str = "1:1",
    num_images: int = 1,
    user_role: str = "user",
    allowed_categories: list | None = None,
) -> dict:
    """
    Main entry point: check content policy, then generate 1-4 images.
    Returns dict with images list and metadata.
    """
    if allowed_categories is None:
        allowed_categories = ["safe"]

    # Validate inputs
    if not prompt or not prompt.strip():
        raise ValueError("Prompt must not be empty.")
    if len(prompt.strip()) > 2000:
        raise ValueError("Prompt must not exceed 2000 characters.")
    if style not in STYLE_PROMPTS and style != "":
        style = "photorealistic"
    if aspect_ratio not in ASPECT_RATIOS:
        aspect_ratio = "1:1"
    num_images = max(1, min(4, int(num_images)))

    # Backend content moderation
    policy_error = _check_content_policy(prompt.strip(), user_role, allowed_categories)
    if policy_error:
        raise PermissionError(policy_error)

    images = []
    errors = []

    for i in range(num_images):
        seed = uuid.uuid4().int % (2**31)
        try:
            result = await generate_image_pollinations(
                prompt=prompt.strip(),
                style=style,
                aspect_ratio=aspect_ratio,
                seed=seed,
            )
            result["variation_index"] = i + 1
            result["seed"] = seed
            images.append(result)
        except (RuntimeError, httpx.HTTPError) as e:
            errors.append(str(e))
            logger.warning("Image generation attempt %d failed: %s", i + 1, e)

    if not images and errors:
        raise RuntimeError(f"All {num_images} generation attempt(s) failed: {errors[0]}")

    return {
        "prompt": prompt.strip(),
        "style": style,
        "aspect_ratio": aspect_ratio,
        "images": images,
        "errors": errors,
        "total_requested": num_images,
        "total_generated": len(images),
    }
