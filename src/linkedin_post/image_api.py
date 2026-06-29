import base64
import logging
from pathlib import Path
from typing import Optional

from .http_utils import get_session
from .settings import Settings

try:
    # Lazy import; will raise if not installed
    from google import genai  # type: ignore
except Exception:  # pragma: no cover - handled at runtime
    genai = None  # type: ignore

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

CLOUDFLARE_AI_URL = "https://api.cloudflare.com/client/v4/accounts/{account_id}/ai/run/{model}"
LINKEDIN_IMAGES_URL = "https://api.linkedin.com/rest/images"
LINKEDIN_VERSION = "202605"


def _extract_image_bytes_from_json(payload: object) -> Optional[bytes]:
    """Handle common JSON response shapes that wrap a base64 image payload."""
    candidates: list[object] = [payload]

    if isinstance(payload, dict):
        for key in ("result", "data", "image", "output"):
            value = payload.get(key)
            if value is not None:
                candidates.append(value)

    while candidates:
        item = candidates.pop(0)
        if isinstance(item, dict):
            for key in ("image", "b64", "b64_json", "base64"):
                value = item.get(key)
                if isinstance(value, str):
                    return base64.b64decode(value)
            candidates.extend(item.values())
        elif isinstance(item, list):
            candidates.extend(item)
        elif isinstance(item, str):
            try:
                return base64.b64decode(item)
            except Exception:
                continue

    return None


def generate_image(
    settings: Settings,
    image_prompt: str,
    post_text: str | None = None,
    save_path: Optional[str] = None,
) -> Optional[bytes]:
    """Generate image bytes with Cloudflare Workers AI."""
    if not image_prompt:
        logging.error("No image prompt provided.")
        return None

    if not settings.cloudflare_api_token or not settings.cloudflare_account_id:
        logging.error("Cloudflare AI credentials are not configured.")
        return None

    prompt = image_prompt
    if post_text:
        prompt = f"{image_prompt}\n\nContext from LinkedIn post:\n{post_text[:1200]}"

    url = CLOUDFLARE_AI_URL.format(
        account_id=settings.cloudflare_account_id,
        model=settings.cloudflare_image_model,
    )
    response = get_session().post(
        url,
        headers={"Authorization": f"Bearer {settings.cloudflare_api_token}"},
        json={"prompt": prompt},
        timeout=120,
    )
    response.raise_for_status()

    content_type = response.headers.get("Content-Type", "")
    if content_type.startswith("image/"):
        image_bytes = response.content
    else:
        image_bytes = _extract_image_bytes_from_json(response.json())

    if not image_bytes:
        logging.error("Cloudflare image response did not contain image bytes.")
        return None

    if save_path:
        Path(save_path).parent.mkdir(parents=True, exist_ok=True)
        with open(save_path, "wb") as fh:
            fh.write(image_bytes)
        logging.info(f"Saved image to {save_path}")

    return image_bytes


def upload_image_to_linkedin(settings: Settings, image_data: bytes) -> Optional[str]:
    """Upload image bytes to LinkedIn and return the image URN."""
    if not image_data:
        logging.error("No image data provided for LinkedIn upload.")
        return None

    if not settings.linkedin_access_token or not settings.linkedin_person_urn:
        logging.error("LinkedIn upload credentials are not configured.")
        return None

    session = get_session()
    init_response = session.post(
        f"{LINKEDIN_IMAGES_URL}?action=initializeUpload",
        headers={
            "Authorization": f"Bearer {settings.linkedin_access_token}",
            "Content-Type": "application/json",
            "LinkedIn-Version": LINKEDIN_VERSION,
            "X-Restli-Protocol-Version": "2.0.0",
        },
        json={"initializeUploadRequest": {"owner": settings.linkedin_person_urn}},
        timeout=30,
    )
    init_response.raise_for_status()
    init_data = init_response.json()
    value = init_data.get("value", {})
    upload_url = value.get("uploadUrl")
    image_urn = value.get("image")

    if not upload_url or not image_urn:
        logging.error("LinkedIn initialize upload response was missing uploadUrl or image URN.")
        return None

    upload_response = session.put(
        upload_url,
        headers={
            "Authorization": f"Bearer {settings.linkedin_access_token}",
            "Content-Type": "image/png",
        },
        data=image_data,
        timeout=120,
    )
    upload_response.raise_for_status()
    return image_urn


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
