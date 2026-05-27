def generate_post(settings: Settings, source: dict[str, str] | None = None) -> tuple[str, str]:
    require(settings.gemini_api_key, "GEMINI_API_KEY")

    source_text = ""
    if source:
        source_text = f"""
Use this source content from my planning sheet:
Title: {source["title"]}
Description: {source["description"]}
"""

    prompt = f"""
Create a professional LinkedIn post for software engineers.

Topic: {settings.post_topic}
Tone: {settings.post_tone}
Audience: {settings.post_audience}

{source_text}

STRICT FORMAT:

<POST_TEXT>
TITLE:
Write one strong professional title.

DESCRIPTION:
Write 2 short engaging paragraphs.
Keep it practical and technical.
End with one thoughtful question.

HASHTAGS:
Add exactly 3 to 5 hashtags.
</POST_TEXT>

<IMAGE_PROMPT>
Professional futuristic tech illustration.
Modern AI themed design.
Clean 3D isometric style.
No text inside image.
</IMAGE_PROMPT>

RULES:
- Do not add extra XML tags
- Do not explain anything
- Keep post under 1200 characters
- Output must strictly follow format
"""

    url = f"https://generativelanguage.googleapis.com/v1beta/models/{settings.gemini_model}:generateContent"

    headers = {
        "Content-Type": "application/json",
        "X-goog-api-key": settings.gemini_api_key,
    }

    payload = {
        "contents": [
            {
                "parts": [
                    {
                        "text": prompt.strip()
                    }
                ]
            }
        ],
        "generationConfig": {
            "temperature": 0.7,
            "maxOutputTokens": 1024,
        }
    }

    response = get_session().post(
        url,
        headers=headers,
        json=payload,
        timeout=60
    )

    response.raise_for_status()

    data = response.json()

    candidates = data.get("candidates", [])

    if not candidates:
        raise SystemExit("Gemini returned no response.")

    candidate = candidates[0]

    content = candidate.get("content", {})

    parts = content.get("parts", [])

    if not parts:
        raise SystemExit("Gemini returned empty content.")

    full_text = "".join(
        [str(part.get("text", "")) for part in parts]
    ).strip()

    # Remove Markdown code block wrappers if Gemini added them
    full_text = re.sub(r"```[a-z]*\n?", "", full_text, flags=re.IGNORECASE)
    full_text = full_text.replace("```", "").strip()

    post_text_content = ""
    image_prompt_content = ""

    # -------------------------------------------------------------------------
    # Robust Extraction of POST_TEXT content
    # Tries to get content between tags, then everything after opening tag,
    # then falls back to full text, always cleaning up stray XML tags.
    # -------------------------------------------------------------------------
    post_match = re.search(r"<POST_TEXT>(.*?)</POST_TEXT>", full_text, re.DOTALL | re.IGNORECASE)
    if post_match:
        post_text_content = post_match.group(1).strip()
    else:
        # Fallback: if closing tag is missing, try to get everything after opening tag
        post_start_match = re.search(r"<POST_TEXT>(.*)", full_text, re.DOTALL | re.IGNORECASE)
        if post_start_match:
            post_text_content = post_start_match.group(1).strip()
            # If there's an <IMAGE_PROMPT> tag after it, cut it off
            post_text_content = re.split(r"<IMAGE_PROMPT>", post_text_content, 1, re.IGNORECASE)[0].strip()
        else:
            # Last resort: assume the whole text is the post content
            post_text_content = full_text

    # -------------------------------------------------------------------------
    # Robust Extraction of IMAGE_PROMPT content
    # -------------------------------------------------------------------------
    image_prompt_content = ""
    image_match = re.search(r"<IMAGE_PROMPT>(.*?)</IMAGE_PROMPT>", full_text, re.DOTALL | re.IGNORECASE)
    if image_match:
        image_prompt_content = image_match.group(1).strip()
    else:
        # Fallback: if closing tag is missing, try to get everything after opening tag
        image_start_match = re.search(r"<IMAGE_PROMPT>(.*)", full_text, re.DOTALL | re.IGNORECASE)
        if image_start_match:
            image_prompt_content = image_start_match.group(1).strip()
            # If there's a <POST_TEXT> tag after it (unlikely but for robustness), cut it off
            image_prompt_content = re.split(r"<POST_TEXT>", image_prompt_content, 1, re.IGNORECASE)[0].strip()
        else:
            image_prompt_content = f"Professional tech illustration about {settings.post_topic}"

    # CRITICAL CLEANUP: Remove ANY tag-like structures and HTML entities
    post_text_content = post_text_content.replace("&lt;", "<").replace("&gt;", ">")
    post_text_content = re.sub(r"<[^>]+>", "", post_text_content).strip()
    image_prompt_content = image_prompt_content.replace("&lt;", "<").replace("&gt;", ">")
    image_prompt_content = re.sub(r"<[^>]+>", "", image_prompt_content).strip()

    # -----------------------------
    # Extract title, description, and hashtags
    # -----------------------------

    title_match = re.search(
        r"TITLE:\s*(.*?)(?=\n+DESCRIPTION:|$)", 
        post_text_content,
        re.DOTALL | re.IGNORECASE
    )

    title = title_match.group(1).strip() if title_match else ""

    # -----------------------------
    # Extract description
    # -----------------------------

    desc_match = re.search(
        r"DESCRIPTION:\s*(.*?)(?=\n+HASHTAGS:|$)",
        post_text_content,
        re.DOTALL | re.IGNORECASE
    )

    description = desc_match.group(1).strip() if desc_match else ""

    # -----------------------------
    # Extract hashtags
    # -----------------------------

    hash_match = re.search(
        r"HASHTAGS:\s*(.*)", # This should be at the end
        post_text_content,
        re.DOTALL | re.IGNORECASE
    )

    hashtags = hash_match.group(1).strip() if hash_match else ""

    # -----------------------------
    # Final LinkedIn Formatting
    # -----------------------------

    final_post = f"""🚀 {title}

{description}

{hashtags}
"""

    # Remove accidental duplicate spaces
    final_post = re.sub(r"\n{3,}", "\n\n", final_post).strip()

    return final_post, image_prompt_content


def generate_image(settings: Settings, prompt: str) -> bytes | None:
    """Generate an image using Hugging Face Stable Diffusion API."""
    if not settings.hugging_face_api_key:
        print("Hugging Face API key not provided. Skipping image generation.")
        return None

    try:
        print(f"Attempting to generate image with prompt: '{prompt}'")
        url = "https://api-inference.huggingface.co/models/stabilityai/stable-diffusion-3.5-large"
        headers = {"Authorization": f"Bearer {settings.hugging_face_api_key}"}
        payload = {"inputs": prompt}

        response = get_session().post(url, headers=headers, json=payload, timeout=120)

        # Check for non-200 status codes
        if response.status_code != 200:
            print(f"Hugging Face API returned status code: {response.status_code}")
            # Try to parse JSON error if available
            if "application/json" in response.headers.get("Content-Type", ""):
                error_info = response.json()
                print(f"Hugging Face API error details: {error_info.get('error', 'Unknown error')}")
                if "loading" in error_info.get('error', '').lower():
                    print("Model is likely still loading. Consider retrying later or using a different model.")
            else:
                print(f"Hugging Face API returned non-JSON error: {response.text}")
            return None

        # If we reach here, status code is 200, so it should be image data
        print(f"Image generation successful. Received {len(response.content)} bytes.")
        return response.content
    except requests.exceptions.RequestException as req_e:
        if "getaddrinfo failed" in str(req_e) or "NameResolutionError" in str(req_e):
            print("❌ Network Error: Cannot resolve Hugging Face. Check your DNS/VPN settings.", file=sys.stderr)
        else:
            print(f"Warning: Network or HTTP error during image generation: {req_e}", file=sys.stderr)
        print("Image generation failed. Returning None.")
        return None
    except Exception as e:
        print(f"Warning: Unexpected error during image generation: {e}", file=sys.stderr)
        print("Image generation failed. Returning None.")
        return None