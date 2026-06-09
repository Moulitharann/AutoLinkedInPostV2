import re
import time
from typing import Any

from .http_utils import get_session
from .settings import Settings, require

RETRYABLE_STATUS_CODES = {429, 500, 502, 503, 504}
TEXT_MODEL_FALLBACK = "gemini-2.5-flash-lite"


def extract_section(text: str, tag: str) -> str:
    """Extract a tagged Gemini section, tolerating missing closing tags."""
    pattern = rf"<{tag}>(.*?)(?:</{tag}>|<TITLE>|<DESCRIPTION>|<HASHTAGS>|<IMAGE_PROMPT>|$)"
    match = re.search(pattern, text, re.DOTALL | re.IGNORECASE)
    if not match:
        return ""
    return clean_section(match.group(1))


def clean_section(text: str) -> str:
    text = re.sub(r"```(?:\w+)?", "", text)
    text = re.sub(r"</?(?:TITLE|DESCRIPTION|HASHTAGS|IMAGE_PROMPT|POST_TEXT)>", "", text, flags=re.IGNORECASE)
    lines = []
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.upper() in {"TITLE", "DESCRIPTION", "HASHTAGS", "IMAGE_PROMPT", "/TITLE", "/DESCRIPTION"}:
            continue
        lines.append(stripped)
    return "\n".join(line for line in lines if line).strip()


def normalize_hashtags(hashtags: str, settings: Settings) -> str:
    if not hashtags:
        hashtags = "#SoftwareEngineering #AI #DevOps"
    return " ".join(
        f"#{token.lstrip('#')}" for token in re.split(r"\s+", hashtags.replace("\n", " ").strip()) if token
    )


def post_generate_content(settings: Settings, prompt: str):
    models = [settings.gemini_model]
    if settings.gemini_model != TEXT_MODEL_FALLBACK:
        models.append(TEXT_MODEL_FALLBACK)

    headers = {
        "Content-Type": "application/json",
        "X-goog-api-key": settings.gemini_api_key,
    }
    payload = {
        "contents": [
            {
                "parts": [
                    {"text": prompt.strip()}
                ]
            }
        ],
        "generationConfig": {
            "temperature": 0.7,
            "maxOutputTokens": 2048,
            "thinkingConfig": {
                "thinkingBudget": 0
            },
        }
    }

    last_error = ""
    for model in models:
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
        for attempt in range(1, 4):
            response = get_session().post(url, headers=headers, json=payload, timeout=60)
            if response.ok:
                if model != settings.gemini_model:
                    print(f"Gemini model {settings.gemini_model} was busy. Used fallback model {model}.")
                return response

            try:
                error_message = response.json().get("error", {}).get("message", response.text)
            except ValueError:
                error_message = response.text

            last_error = f"Gemini post generation failed ({response.status_code}): {error_message}"
            if response.status_code not in RETRYABLE_STATUS_CODES:
                raise SystemExit(last_error)

            if attempt < 3:
                wait_seconds = attempt * 5
                print(f"Gemini model {model} is temporarily unavailable. Retrying in {wait_seconds}s...")
                time.sleep(wait_seconds)

    raise SystemExit(last_error)


def generate_post(settings: Settings, source: dict[str, str] | None = None) -> tuple[str, str]:
    require(settings.gemini_api_key, "GEMINI_API_KEY")

    source_text = ""
    if source:
        source_text = f"""
Use this source content from my planning sheet:
Title: {source['title']}
Description: {source['description']}
"""

    prompt = f"""
Create a highly structured professional LinkedIn post for a software engineer and a corresponding image description.

Topic area: {settings.post_topic}
Tone: {settings.post_tone}
Audience: {settings.post_audience}
{source_text}

You must output four sections wrapped in XML-style tags:

<TITLE>
A concise professional headline that could appear as the first line of the post.
</TITLE>

<DESCRIPTION>
2 short, practical paragraphs of technical content. Include one clear lesson, insight, or takeaway.
</DESCRIPTION>

<HASHTAGS>
Exactly 3-5 relevant, professional hashtags in a single line.
</HASHTAGS>

<IMAGE_PROMPT>
A detailed, professional visual description for an AI image generator (Stable Diffusion).
It must be tightly related to the exact post content, not a generic AI or cloud illustration.
Use concrete software delivery visuals: a developer reviewing AI-suggested code in an IDE, a pull request review panel, automated test results, static analysis/security checks, CI/CD pipeline stages, and deployment gates.
Show AI as a practical assistant inside the SDLC workflow, with human engineers validating output before release.
Leave clean visual space for a readable editorial text overlay that will be added later.
Avoid abstract glowing cubes, random robots, floating circuit blocks, unreadable dashboards, logos, or generic futuristic backgrounds.
Prefer a professional LinkedIn-ready composition with clear workflow elements, realistic software engineering context, and modern but grounded styling.
</IMAGE_PROMPT>

Constraint: Post text must be under 900 characters. No hype, fluff, or generic motivational filler.
"""

    response = post_generate_content(settings, prompt)
    data = response.json()

    candidates = data.get("candidates", [])
    if not candidates:
        raise SystemExit("Gemini returned no candidates.")

    candidate = candidates[0]
    if candidate.get("finishReason") == "MAX_TOKENS":
        raise SystemExit("Gemini returned an incomplete post because it hit the token limit. Nothing was published.")

    content = candidate.get("content", {})
    parts = content.get("parts", [])

    if parts and isinstance(parts, list):
        full_text = "".join([str(part.get("text", "")) for part in parts]).strip()

        title = extract_section(full_text, "TITLE")
        description = extract_section(full_text, "DESCRIPTION")
        hashtags = extract_section(full_text, "HASHTAGS")
        image_prompt = extract_section(full_text, "IMAGE_PROMPT")

        if not title or not description or not image_prompt:
            post_match = re.search(r"<POST_TEXT>(.*?)</POST_TEXT>", full_text, re.DOTALL | re.IGNORECASE)
            if post_match:
                fallback = clean_section(post_match.group(1))
                return fallback, image_prompt or f"Professional tech illustration: {settings.post_topic}"

            raise SystemExit("Gemini returned an incomplete post or image prompt. Nothing was published.")

        hashtags = normalize_hashtags(hashtags, settings)

        post_text = title
        if description:
            post_text += "\n\n" + description
        if hashtags:
            post_text += "\n\n" + hashtags

        if not image_prompt:
            image_prompt = f"Professional tech illustration: {settings.post_topic}"

        return post_text, image_prompt

    raise SystemExit("Unexpected Gemini response format.")
