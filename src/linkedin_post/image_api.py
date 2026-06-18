import base64
import logging
from pathlib import Path
from typing import Optional

from .settings import Settings

try:
    # Lazy import; will raise if not installed
    from google import genai  # type: ignore
except Exception:  # pragma: no cover - handled at runtime
    genai = None  # type: ignore

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')


def generate_image_with_gemini(settings: Settings, prompt: str, save_path: Optional[str] = None) -> Optional[bytes]:
    """Generate an image from a raw text prompt using Gemini and return image bytes.

    This function sends the exact `prompt` string to Gemini's image API (no
    extra wrapping or templates) and returns decoded image bytes. If
    `save_path` is provided the bytes are also written to that path.

    Returns `None` on failure.
    """
    if not prompt:
        logging.error("No prompt provided for image generation.")
        return None

    if not getattr(settings, "gemini_api_key", None):
        logging.error("Gemini API key not configured on settings.")
        return None

    if genai is None:
        logging.error("google.genai SDK not available in environment.")
        return None

    try:
        client = genai.Client(api_key=settings.gemini_api_key)  # type: ignore[arg-type]

        # Try a couple of common SDK entry points for image generation.
        resp = None
        if hasattr(client, "images") and hasattr(client.images, "generate"):
            resp = client.images.generate(model=getattr(settings, "gemini_image_model", None) or "image-alpha-001", prompt=prompt)

        if resp is None and hasattr(genai, "Image") and hasattr(genai.Image, "create"):
            resp = genai.Image.create(model=getattr(settings, "gemini_image_model", None) or "image-alpha-001", prompt=prompt)

        # Attempt to extract base64 payload from common response shapes
        b64 = None
        if resp is None:
            logging.error("Gemini image call returned no response object.")
            return None

        # resp may be SDK object or dict-like
        data = getattr(resp, "data", None) or (resp.get("data") if isinstance(resp, dict) else None)
        if not data:
            data = getattr(resp, "output", None) or (resp.get("output") if isinstance(resp, dict) else None)
        if not data:
            data = getattr(resp, "image", None) or (resp.get("image") if isinstance(resp, dict) else None)

        item = None
        if isinstance(data, (list, tuple)) and data:
            item = data[0]
        else:
            item = data

        if isinstance(item, dict):
            b64 = item.get("b64") or item.get("b64_json") or item.get("base64")
        elif isinstance(item, str):
            b64 = item
        else:
            b64 = getattr(item, "b64", None) or getattr(item, "base64", None)

        if not b64:
            logging.error("Could not find base64 image payload in Gemini response.")
            return None

        image_bytes = base64.b64decode(b64)

        if save_path:
            Path(save_path).parent.mkdir(parents=True, exist_ok=True)
            with open(save_path, "wb") as fh:
                fh.write(image_bytes)
            logging.info(f"Saved image to {save_path}")

        return image_bytes
    except Exception as e:
        logging.error(f"Gemini image generation failed: {e}", exc_info=True)
        return None
