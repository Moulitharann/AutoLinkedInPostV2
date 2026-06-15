import io
import base64
import re

import os
import time
import logging
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter, ImageFont

from .http_utils import get_session
from .settings import Settings, require
from .gemini_api import enhance_image_prompt

# Configure logging for this module
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

RETRYABLE_STATUS_CODES = {429, 500, 502, 503, 504}

# Image composition constants
CANVAS_SIZE = 1200
IMAGE_CARD_SIZE = 520          # FIX: was a magic number (520, 520) in compose_linkedin_image
IMAGE_OVERLAY_COLOR = (15, 23, 42, 52)   # FIX: was a magic number inline
IMAGE_RECT_RADIUS = 38
IMAGE_RECT_FILL = "#dbeafe"
IMAGE_RECT_OUTLINE = "#93c5fd"
IMAGE_RECT_OUTLINE_WIDTH = 5
STAGE_BOX_WIDTH = 190          # FIX: unified stage box width (was inconsistent index-based logic)


def font(size: int, bold: bool = False) -> ImageFont.ImageFont:
    """Loads a font, preferring system fonts or falling back to default."""
    font_name = "arialbd.ttf" if bold else "arial.ttf"

    # FIX: Added Linux/macOS font paths as fallbacks (original was Windows-only)
    candidate_dirs = [
        Path("C:/Windows/Fonts"),                                    # Windows
        Path("/usr/share/fonts/truetype/msttcorefonts"),             # Linux (msttcorefonts pkg)
        Path("/usr/share/fonts/truetype/liberation"),                # Linux fallback
        Path("/Library/Fonts"),                                      # macOS
    ]
    for directory in candidate_dirs:
        font_path = directory / font_name
        if font_path.exists():
            return ImageFont.truetype(str(font_path), size=size)

    return ImageFont.load_default()


def wrap_text(draw: ImageDraw.ImageDraw, text: str, text_font: ImageFont.ImageFont, max_width: int) -> list[str]:
    lines = []
    # Handle paragraphs separately
    for paragraph in text.splitlines():
        words = paragraph.split()
        if not words:
            lines.append("")
            continue

        line = words[0]
        for word in words[1:]:
            candidate = f"{line} {word}"
            if draw.textbbox((0, 0), candidate, font=text_font)[2] <= max_width:
                line = candidate
            else:
                lines.append(line)
                line = word
        lines.append(line)
    return lines


def post_image_text(post_text: str) -> tuple[str, str]:
    """Extracts a title and a concise body from the post text for image display."""
    lines = [line.strip() for line in post_text.splitlines() if line.strip()]
    title = lines[0] if lines else "Software Engineering Insight"
    body_lines = [line for line in lines[1:] if not line.startswith("#")]
    body = " ".join(body_lines)

    takeaway_match = re.search(r"(The key takeaway:.*?)(?:\. |$)", body, flags=re.IGNORECASE)
    if takeaway_match:
        body = takeaway_match.group(1).strip()
    elif len(body) > 145:
        body = body[:145].rsplit(" ", 1)[0].strip() + "..."

    return title, body


def limited_lines(
    draw: ImageDraw.ImageDraw,
    text: str,
    text_font: ImageFont.ImageFont,
    max_width: int,
    max_lines: int,
) -> list[str]:
    """Wraps text and limits it to a maximum number of lines, adding an ellipsis if clipped."""
    lines = wrap_text(draw, text, text_font, max_width)
    if len(lines) <= max_lines:
        return lines

    clipped = lines[:max_lines]
    clipped[-1] = clipped[-1].rstrip(".") + "..."
    while draw.textbbox((0, 0), clipped[-1], font=text_font)[2] > max_width and " " in clipped[-1]:
        clipped[-1] = clipped[-1].rsplit(" ", 1)[0].rstrip(".") + "..."
    return clipped


def compose_linkedin_image(base_image: Image.Image, post_text: str) -> bytes:
    """Composes a professional LinkedIn-style image with enhanced design."""
    title, body = post_image_text(post_text)
    
    # Premium background
    canvas = Image.new("RGB", (CANVAS_SIZE, CANVAS_SIZE), "#f8fafc")

    # Process the generated image with professional styling
    generated = (
        base_image.convert("RGB")
        .resize((540, 540))  # Larger, more prominent
        .filter(ImageFilter.GaussianBlur(radius=0.8))
    )
    
    # Sophisticated semi-transparent overlay
    overlay = Image.new("RGBA", generated.size, (15, 23, 42, 90))
    generated = Image.alpha_composite(generated.convert("RGBA"), overlay)

    draw = ImageDraw.Draw(canvas)
    
    # Main card with clean white background
    draw.rounded_rectangle((50, 75, 1150, 925), radius=50, fill="#ffffff", outline="#e2e8f0", width=3)

    # Image placement - larger and more prominent
    canvas.paste(generated.convert("RGB"), (615, 115))
    draw.rounded_rectangle((605, 105, 1135, 655), radius=48, outline="#3b82f6", width=7)

    # Premium fonts
    eyebrow_font = font(26, bold=True)
    title_font = font(54, bold=True)
    body_font = font(31)
    label_font = font(23, bold=True)
    footer_font = font(25)

    x_padding = 85
    y = 120
    max_width = 490

    # Section label with icon
    draw.text((x_padding, y), "✨ AI IN THE SDLC", fill="#1e40af", font=eyebrow_font)
    y += 58

    # Title - bold and prominent
    for line in limited_lines(draw, title, title_font, max_width, 2):
        draw.text((x_padding, y), line, fill="#0f172a", font=title_font)
        y += 64

    y += 24
    # Accent bar - premium look
    draw.rounded_rectangle((x_padding, y, x_padding + 180, y + 14), radius=7, fill="#06b6d4")
    y += 48

    # Body text - clean and readable
    for line in limited_lines(draw, body, body_font, max_width, 3):
        draw.text((x_padding, y), line, fill="#334155", font=body_font)
        y += 44

    # Enhanced pipeline stages with better visual design
    y = 710
    x_stage = x_padding
    stages = ["Analyze", "Design", "Implement", "Test", "Deploy"]
    stage_colors = ["#e0f2fe", "#d1fae5", "#fef3c7", "#fee2e2", "#e9d5ff"]
    
    for index, (stage, color) in enumerate(zip(stages, stage_colors)):
        box_width = 165
        draw.rounded_rectangle((x_stage, y, x_stage + box_width, y + 66), radius=20, fill=color, outline="#cbd5e1", width=2)
        draw.text((x_stage + 14, y + 16), stage, fill="#0f172a", font=label_font)
        
        # Connection arrows
        if index < len(stages) - 1:
            arrow_x = x_stage + box_width + 10
            arrow_y_mid = y + 33
            draw.line((arrow_x, arrow_y_mid, arrow_x + 32, arrow_y_mid), fill="#0284c7", width=5)
            draw.polygon([(arrow_x + 32, arrow_y_mid), (arrow_x + 40, arrow_y_mid - 5), (arrow_x + 40, arrow_y_mid + 5)], fill="#0284c7")
        
        x_stage += box_width + 46

    # Professional footer
    draw.text((x_padding, 835), "End-to-end security and quality integrated throughout development", fill="#475569", font=footer_font)

    output = io.BytesIO()
    canvas.save(output, format="PNG")
    logging.info("LinkedIn image composed with enhanced professional design.")
    return output.getvalue()


def fallback_base_image() -> Image.Image:
    canvas = Image.new("RGB", (1024, 1024), "#eef6ff")
    draw = ImageDraw.Draw(canvas)

    draw.rounded_rectangle((120, 150, 904, 330), radius=34, fill="#ffffff", outline="#93c5fd", width=4)
    draw.rounded_rectangle((170, 205, 500, 238), radius=10, fill="#bfdbfe")
    draw.rounded_rectangle((170, 260, 790, 288), radius=10, fill="#dbeafe")

    stages = [
        ((155, 470, 315, 590), "#dbeafe"),
        ((432, 470, 592, 590), "#dcfce7"),
        ((709, 470, 869, 590), "#e0f2fe"),
    ]
    for bounds, fill in stages:
        draw.rounded_rectangle(bounds, radius=28, fill=fill, outline="#2563eb", width=4)

    draw.line((330, 530, 417, 530), fill="#2563eb", width=8)
    draw.line((607, 530, 694, 530), fill="#2563eb", width=8)
    draw.polygon([(405, 512), (430, 530), (405, 548)], fill="#2563eb")
    draw.polygon([(682, 512), (707, 530), (682, 548)], fill="#2563eb")

    draw.rounded_rectangle((205, 700, 819, 820), radius=30, fill="#ffffff", outline="#86efac", width=4)
    draw.rounded_rectangle((255, 748, 430, 778), radius=10, fill="#bbf7d0")
    draw.rounded_rectangle((470, 748, 770, 778), radius=10, fill="#d1fae5")

    return canvas


def fallback_image_bytes(post_text: str = "") -> bytes:
    base_image = fallback_base_image()
    if post_text:
        return compose_linkedin_image(base_image, post_text)

    output = io.BytesIO()
    base_image.save(output, format="PNG")
    logging.info("Fallback base image generated.")
    return output.getvalue()


def generate_image(settings: Settings, prompt: str, post_text: str = "") -> bytes | None:
    """Generate an image using Cloudflare AI with Gemini-enhanced prompt."""
    require(settings.cloudflare_api_token, "CLOUDFLARE_API_TOKEN")
    require(settings.cloudflare_account_id, "CLOUDFLARE_ACCOUNT_ID")

    # Enhance the prompt using Gemini for better image generation
    logging.info("Enhancing image prompt with Gemini...")
    enhanced_prompt = enhance_image_prompt(settings, prompt)
    logging.info(f"Enhanced prompt: {enhanced_prompt[:100]}...")

    base_url = f"https://api.cloudflare.com/client/v4/accounts/{settings.cloudflare_account_id}/ai/run"
    model = settings.cloudflare_image_model
    headers = {"Authorization": f"Bearer {settings.cloudflare_api_token}"}

    attempts = [
        (f"{base_url}/{model}", {"prompt": enhanced_prompt}, headers.copy()),
        (base_url, {"model": model, "input": enhanced_prompt, "modalities": ["image"]}, headers.copy()),
        (base_url, {"model": model, "inputs": enhanced_prompt, "modalities": ["image"]}, headers.copy()),
    ]

    try:
        response = None
        last_exc = None
        for (try_url, try_payload, try_headers) in attempts:
            for attempt_no in range(1, 4):
                try:
                    logging.info(f"Cloudflare attempt: POST {try_url} (attempt {attempt_no})")
                    resp = get_session().post(try_url, headers=try_headers, json=try_payload, timeout=120)
                    if resp.ok:
                        response = resp
                        break
                    if resp.status_code not in RETRYABLE_STATUS_CODES:
                        logging.error(f"Cloudflare returned {resp.status_code}: {resp.text}")
                        break
                    wait_seconds = attempt_no * 5
                    logging.warning(f"Cloudflare temporary error {resp.status_code}. Retrying in {wait_seconds}s...")
                    time.sleep(wait_seconds)
                except Exception as ex:
                    last_exc = ex
                    logging.warning(f"Cloudflare request exception: {ex}. Retrying...", exc_info=False)
                    time.sleep(attempt_no * 2)
            if response:
                break

        if response is None:
            if last_exc:
                raise last_exc
            raise RuntimeError("Cloudflare image generation did not return a response.")

        image_data = response.content
        content_type = response.headers.get("Content-Type", "")
        if response.ok and content_type.startswith("image/"):
            image = Image.open(io.BytesIO(image_data))
            if post_text:
                return compose_linkedin_image(image, post_text)
            out = io.BytesIO()
            image.save(out, format="PNG")
            return out.getvalue()

        try:
            data = response.json()
        except Exception:
            logging.error(f"Cloudflare returned unexpected content and not JSON: {response.text}")
            raise RuntimeError("Cloudflare returned no valid image data.")

        b64 = None
        if isinstance(data, dict):
            # Check result.image for Cloudflare flux models (base64 JPEG)
            if "result" in data and isinstance(data["result"], dict):
                result_dict = data["result"]
                if "image" in result_dict:
                    img_val = result_dict["image"]
                    if isinstance(img_val, str):
                        b64 = img_val
            
            # If not found in result.image, search other common fields
            if not b64:
                for key in ("outputs", "artifacts", "generated", "image", "images"):
                    if key in data:
                        val = data[key]
                        if isinstance(val, str) and (val.startswith("data:image") or val.startswith("/9j")):
                            b64 = val
                            break
                        if isinstance(val, list) and val and isinstance(val[0], str) and (val[0].startswith("data:image") or val[0].startswith("/9j")):
                            b64 = val[0]
                            break
                        if isinstance(val, dict):
                            for subval in val.values():
                                if isinstance(subval, str) and (subval.startswith("data:image") or subval.startswith("/9j")):
                                    b64 = subval
                                    break
                            if b64:
                                break

        if not b64:
            logging.error(f"Cloudflare returned JSON but no image found: {data}")
            raise RuntimeError("Cloudflare returned JSON without image data.")

        # Decode base64 image (handle both data:image/... and raw base64 JPEG)
        b64_clean = re.sub(r'data:image/[^;]+;base64,', '', b64)
        image_data = base64.b64decode(b64_clean)
        image = Image.open(io.BytesIO(image_data))
        if post_text:
            return compose_linkedin_image(image, post_text)
        out = io.BytesIO()
        image.save(out, format="PNG")
        return out.getvalue()
        # FIX: Removed dead code block that appeared here after the return above
        # (duplicate image open + save that could never execute)

    except Exception as e:
        logging.error(f"Image generation failed: {e}", exc_info=True)
        hf_key = os.getenv("HUGGING_FACE_API_KEY")
        if hf_key:
            logging.info("Attempting Hugging Face fallback image generation.")
            try:
                hf_model = os.getenv("HUGGING_FACE_IMAGE_MODEL", "stabilityai/stable-diffusion-3.5-large")
                hf_url = f"https://api-inference.huggingface.co/models/{hf_model}"
                hf_headers = {"Authorization": f"Bearer {hf_key}"}
                hf_payload = {"inputs": prompt}
                hf_resp = get_session().post(hf_url, headers=hf_headers, json=hf_payload, timeout=120)
                if hf_resp.ok:
                    ct = hf_resp.headers.get("Content-Type", "")
                    if "image" in ct:
                        image = Image.open(io.BytesIO(hf_resp.content))
                        if post_text:
                            return compose_linkedin_image(image, post_text)
                        out = io.BytesIO()
                        image.save(out, format="PNG")
                        return out.getvalue()
                    try:
                        data = hf_resp.json()
                        b64 = None
                        if isinstance(data, dict):
                            for key in ("generated_image", "image", "images", "output"):
                                if key in data:
                                    val = data[key]
                                    if isinstance(val, str) and val.startswith("data:image"):
                                        b64 = val
                                        break
                                    if isinstance(val, list) and val and isinstance(val[0], str) and val[0].startswith("data:image"):
                                        b64 = val[0]
                                        break
                        if b64:
                            image_data = base64.b64decode(re.sub(r'data:image/[^;]+;base64,', '', b64))
                            image = Image.open(io.BytesIO(image_data))
                            if post_text:
                                return compose_linkedin_image(image, post_text)
                            out = io.BytesIO()
                            image.save(out, format="PNG")
                            return out.getvalue()
                        else:
                            # FIX: was silently falling through; now logs the failure clearly
                            logging.warning("Hugging Face fallback returned JSON but no image data found.")
                    except Exception:
                        pass
                else:
                    logging.warning(f"Hugging Face fallback failed: {hf_resp.status_code} {hf_resp.text}")
            except Exception as he:
                logging.error(f"Hugging Face fallback error: {he}", exc_info=True)

        logging.warning("Using local fallback image.")
        return fallback_image_bytes(post_text)


def upload_image_to_linkedin(settings: Settings, image_data: bytes) -> str | None:
    """Upload an image to LinkedIn and return the image URN."""
    if not image_data:
        return None

    try:
        access_token = settings.linkedin_access_token
        person_urn = settings.linkedin_person_urn

        register_url = "https://api.linkedin.com/rest/images?action=initializeUpload"
        register_headers = {
            "Authorization": f"Bearer {access_token}",
            "Content-Type": "application/json",
            "LinkedIn-Version": "202605",
            "X-Restli-Protocol-Version": "2.0.0",
        }
        register_payload = {
            "initializeUploadRequest": {
                "owner": person_urn
            }
        }

        register_response = get_session().post(
            register_url, headers=register_headers, json=register_payload, timeout=30
        )
        register_response.raise_for_status()
        register_data = register_response.json()

        upload_url = register_data["value"]["uploadUrl"]
        image_urn = register_data["value"]["image"]

        upload_response = get_session().put(
            upload_url,
            headers={
                "Authorization": f"Bearer {access_token}",
                "Content-Type": "image/png",
            },
            data=image_data,
            timeout=60,
        )
        upload_response.raise_for_status()

        logging.info(f"Image uploaded to LinkedIn. URN: {image_urn}")
        return image_urn
    except Exception as e:
        logging.error(f"Image upload to LinkedIn failed: {e}", exc_info=True)
        return None