import os
from dataclasses import dataclass

from dotenv import load_dotenv


@dataclass(frozen=True)
class Settings:
    gemini_api_key: str
    gemini_model: str
    gemini_image_model: str
    cloudflare_api_token: str
    cloudflare_account_id: str
    cloudflare_image_model: str
    linkedin_client_id: str
    linkedin_client_secret: str
    linkedin_redirect_uri: str
    linkedin_oauth_scopes: str
    linkedin_access_token: str
    linkedin_person_urn: str
    content_source_url: str
    content_source_type: str
    post_history_file: str
    scheduler_state_file: str
    post_interval_days: int
    post_topic: str
    post_tone: str
    post_audience: str
    post_visibility: str
    post_require_image: bool


def load_settings() -> Settings:
    load_dotenv()
    return Settings(
        gemini_api_key=os.getenv("GEMINI_API_KEY", ""),
        gemini_model=os.getenv("GEMINI_MODEL", "gemini-2.5-flash"),
        gemini_image_model=os.getenv("GEMINI_IMAGE_MODEL", "gemini-2.5-flash-image"),
        cloudflare_api_token=os.getenv("CLOUDFLARE_API_TOKEN", ""),
        cloudflare_account_id=os.getenv("CLOUDFLARE_ACCOUNT_ID", ""),
        cloudflare_image_model=os.getenv("CLOUDFLARE_IMAGE_MODEL", "@cf/stabilityai/stable-diffusion-xl-lightning"),
        linkedin_client_id=os.getenv("LINKEDIN_CLIENT_ID", ""),
        linkedin_client_secret=os.getenv("LINKEDIN_CLIENT_SECRET", ""),
        linkedin_redirect_uri=os.getenv("LINKEDIN_REDIRECT_URI", "http://localhost:8000/callback"),
        linkedin_oauth_scopes=os.getenv("LINKEDIN_OAUTH_SCOPES", "openid profile w_member_social"),
        linkedin_access_token=os.getenv("LINKEDIN_ACCESS_TOKEN", ""),
        linkedin_person_urn=os.getenv("LINKEDIN_PERSON_URN", ""),
        content_source_url=os.getenv("CONTENT_SOURCE_URL", ""),
        content_source_type=os.getenv("CONTENT_SOURCE_TYPE", "auto").lower(),
        post_history_file=os.getenv("POST_HISTORY_FILE", "posts_history.json"),
        scheduler_state_file=os.getenv("SCHEDULER_STATE_FILE", "scheduler_state.json"),
        post_interval_days=int(os.getenv("POST_INTERVAL_DAYS", "2")),
        post_topic=os.getenv("POST_TOPIC", "software engineering"),
        post_tone=os.getenv("POST_TONE", "clear, practical, senior software engineer"),
        post_audience=os.getenv("POST_AUDIENCE", "software engineers"),
        post_visibility=os.getenv("POST_VISIBILITY", "PUBLIC"),
        post_require_image=os.getenv("POST_REQUIRE_IMAGE", "false").lower() in {"1", "true", "yes", "on"},
    )


def require(value: str, name: str) -> str:
    if not value:
        raise SystemExit(f"Missing {name}. Add it to .env and try again.")
    return value
