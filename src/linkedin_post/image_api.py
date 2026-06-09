import io
import base64
import re
import sys
import time
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter, ImageFont

from .http_utils import get_session
from .settings import Settings, require

RETRYABLE_STATUS_CODES = {429, 500, 502, 503, 504}


def font(size: int, bold: bool = False) -> ImageFont.ImageFont:
    font_name = "arialbd.ttf" if bold else "arial.ttf"
    font_path = Path("C:/Windows/Fonts") / font_name
    if font_path.exists():
        return ImageFont.truetype(str(font_path), size=size)
    return ImageFont.load_default()


def wrap_text(draw: ImageDraw.ImageDraw, text: str, text_font: ImageFont.ImageFont, max_width: int) -> list[str]:
    lines = []
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
    lines = wrap_text(draw, text, text_font, max_width)
    if len(lines) <= max_lines:
        return lines

    clipped = lines[:max_lines]
    clipped[-1] = clipped[-1].rstrip(".") + "..."
    while draw.textbbox((0, 0), clipped[-1], font=text_font)[2] > max_width and " " in clipped[-1]:
        clipped[-1] = clipped[-1].rsplit(" ", 1)[0].rstrip(".") + "..."
    return clipped


def compose_linkedin_image(base_image: Image.Image, post_text: str) -> bytes:
    title, body = post_image_text(post_text)
    canvas_size = 1200
    canvas = Image.new("RGB", (canvas_size, canvas_size), "#eef6ff")

    generated = base_image.convert("RGB").resize((520, 520)).filter(ImageFilter.GaussianBlur(radius=0.6))
    generated_overlay = Image.new("RGBA", generated.size, (15, 23, 42, 52))
    generated = Image.alpha_composite(generated.convert("RGBA"), generated_overlay)

    draw = ImageDraw.Draw(canvas)
    draw.rounded_rectangle((640, 145, 1120, 625), radius=38, fill="#dbeafe")
    canvas.paste(generated, (620, 125), generated)
    draw.rounded_rectangle((620, 125, 1140, 645), radius=42, outline="#93c5fd", width=5)

    eyebrow_font = font(32, bold=True)
    title_font = font(58, bold=True)
    body_font = font(34)
    label_font = font(27, bold=True)
    footer_font = font(28)

    x = 74
    y = 100
    max_width = 510

    draw.text((x, y), "AI IN THE SDLC", fill="#1d4ed8", font=eyebrow_font)
    y += 66

    for line in limited_lines(draw, title, title_font, max_width, 3):
        draw.text((x, y), line, fill="#111827", font=title_font)
        y += 68

    y += 20
    draw.rounded_rectangle((x, y, x + 142, y + 9), radius=4, fill="#16a34a")
    y += 44

    for line in limited_lines(draw, body, body_font, max_width, 3):
        draw.text((x, y), line, fill="#1f2937", font=body_font)
        y += 48

    stages = ["AI suggestion", "Code review", "CI tests", "Security gate", "Deploy"]
    stage_y = 750
    stage_x = 74
    for index, stage in enumerate(stages):
        box_width = 190 if index != 0 else 214
        fill = "#ffffff" if index % 2 == 0 else "#e0f2fe"
        draw.rounded_rectangle((stage_x, stage_y, stage_x + box_width, stage_y + 74), radius=18, fill=fill)
        draw.text((stage_x + 18, stage_y + 22), stage, fill="#0f172a", font=label_font)
        if index < len(stages) - 1:
            draw.line((stage_x + box_width + 12, stage_y + 37, stage_x + box_width + 48, stage_y + 37), fill="#2563eb", width=5)
        stage_x += box_width + 56

    draw.text((74, 940), "Human review before release", fill="#475569", font=footer_font)

    output = io.BytesIO()
    canvas.save(output, format="PNG")
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
    return output.getvalue()


def generate_image(settings: Settings, prompt: str, post_text: str = "") -> bytes | None:
    """Generate an image using Gemini image generation."""
    require(settings.gemini_api_key, "GEMINI_API_KEY")

    try:
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{settings.gemini_image_model}:generateContent"
        headers = {
            "Content-Type": "application/json",
            "X-goog-api-key": settings.gemini_api_key,
        }
        payload = {
            "contents": [
                {
                    "parts": [
                        {"text": prompt}
                    ]
                }
            ],
            "generationConfig": {
                "responseModalities": ["IMAGE"]
            },
        }

        response = None
        for attempt in range(1, 4):
            response = get_session().post(url, headers=headers, json=payload, timeout=120)
            if response.ok:
                break
            if response.status_code not in RETRYABLE_STATUS_CODES or attempt == 3:
                response.raise_for_status()

            wait_seconds = attempt * 10
            print(f"Gemini image model is temporarily unavailable. Retrying in {wait_seconds}s...")
            time.sleep(wait_seconds)

        if response is None:
            raise RuntimeError("Gemini image generation did not return a response.")

        data = response.json()

        image_data = None
        for candidate in data.get("candidates", []):
            for part in candidate.get("content", {}).get("parts", []):
                inline_data = part.get("inlineData") or part.get("inline_data")
                if inline_data and inline_data.get("data"):
                    image_data = base64.b64decode(inline_data["data"])
                    break
            if image_data:
                break

        if not image_data:
            raise RuntimeError("Gemini returned no image data.")

        image = Image.open(io.BytesIO(image_data))
        if post_text:
            return compose_linkedin_image(image, post_text)

        output = io.BytesIO()
        image.save(output, format="PNG")
        return output.getvalue()
    except Exception as e:
        print(f"Warning: Image generation failed: {e}", file=sys.stderr)
        print("Using local fallback image.")
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

        return image_urn
    except Exception as e:
        print(f"Warning: Image upload failed: {e}", file=sys.stderr)
        return None
