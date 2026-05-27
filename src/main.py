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

    # -----------------------------
    # Extract POST_TEXT
    # -----------------------------

    post_match = re.search(
        r"<POST_TEXT>(.*?)</POST_TEXT>",
        full_text,
        re.DOTALL | re.IGNORECASE
    )

    if post_match:
        raw_post = post_match.group(1).strip()
    else:
        raw_post = full_text

    # -----------------------------
    # Extract IMAGE_PROMPT
    # -----------------------------

    image_match = re.search(
        r"<IMAGE_PROMPT>(.*?)</IMAGE_PROMPT>",
        full_text,
        re.DOTALL | re.IGNORECASE
    )

    if image_match:
        image_prompt = image_match.group(1).strip()
    else:
        image_prompt = f"Professional tech illustration about {settings.post_topic}"

    # -----------------------------
    # Remove unwanted XML tags
    # -----------------------------

    raw_post = re.sub(
        r"</?(POST_TEXT|IMAGE_PROMPT)>",
        "",
        raw_post,
        flags=re.IGNORECASE
    ).strip()

    # -----------------------------
    # Extract title
    # -----------------------------

    title_match = re.search(
        r"TITLE:\s*(.*?)(?=DESCRIPTION:|$)",
        raw_post,
        re.DOTALL | re.IGNORECASE
    )

    title = title_match.group(1).strip() if title_match else ""

    # -----------------------------
    # Extract description
    # -----------------------------

    desc_match = re.search(
        r"DESCRIPTION:\s*(.*?)(?=HASHTAGS:|$)",
        raw_post,
        re.DOTALL | re.IGNORECASE
    )

    description = desc_match.group(1).strip() if desc_match else ""

    # -----------------------------
    # Extract hashtags
    # -----------------------------

    hash_match = re.search(
        r"HASHTAGS:\s*(.*)",
        raw_post,
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

    return final_post, image_prompt