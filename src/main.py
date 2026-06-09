import argparse
from datetime import date, datetime
from zoneinfo import ZoneInfo

from src.linkedin_post.content import (
    AllRowsPostedError,
    mark_posted,
    next_content_row,
    load_scheduler_state,
    save_scheduler_state,
)
from src.linkedin_post.gemini_api import generate_post
from src.linkedin_post.image_api import generate_image, upload_image_to_linkedin
from src.linkedin_post.linkedin_api import build_auth_url, exchange_code_for_token, login, publish_post
from src.linkedin_post.settings import load_settings
from src.linkedin_post.utils import parse_date


class ImagePreparationError(Exception):
    """Raised when image generation or upload prevents publishing."""


def preview(settings):
    source = None
    if settings.content_source_url and "PASTE_" not in settings.content_source_url:
        source, _ = next_content_row(settings)
        print(f"Source title: {source['title']}")

    text, image_prompt = generate_post(settings, source)
    print("--- POST PREVIEW ---")
    print(text)
    print("\n--- IMAGE PROMPT PREVIEW ---")
    print(image_prompt)


def prepare_image(settings, image_prompt, post_text):
    if not settings.gemini_api_key:
        raise ImagePreparationError("Image generation is required before publishing. Missing GEMINI_API_KEY.")

    image_data = generate_image(settings, image_prompt, post_text)
    if not image_data:
        raise ImagePreparationError("Image generation failed. Nothing was published.")

    image_urn = upload_image_to_linkedin(settings, image_data)
    if not image_urn:
        raise ImagePreparationError("Image upload to LinkedIn failed. Nothing was published.")

    return image_urn


def test_image(settings):
    source = None
    if settings.content_source_url and "PASTE_" not in settings.content_source_url:
        source, _ = next_content_row(settings)

    text, image_prompt = generate_post(settings, source)
    image_urn = prepare_image(settings, image_prompt, text)
    print("Image generation and LinkedIn upload test passed.")
    print(f"Image URN: {image_urn}")


def post(settings):
    source = None
    source_key = ""
    if settings.content_source_url and "PASTE_" not in settings.content_source_url:
        source, source_key = next_content_row(settings)

    text, image_prompt = generate_post(settings, source)
    image_urn = prepare_image(settings, image_prompt, text)

    result = publish_post(settings, text, image_urn)
    if source_key:
        mark_posted(settings, source_key)

    print(text)
    print()
    print(f"Published to LinkedIn. Status: {result['status_code']}. Post ID: {result.get('post_id')}")


def scheduled_post(settings):
    today = datetime.now(ZoneInfo("Asia/Kolkata")).date()
    state = load_scheduler_state(settings)
    last_posted_on = parse_date(state.get("last_posted_on", ""))

    if last_posted_on and (today - last_posted_on).days < settings.post_interval_days:
        print(f"Skipping. Last successful post was on {last_posted_on.isoformat()}.")
        return

    try:
        post(settings)
    except AllRowsPostedError as exc:
        print(f"Skipping. {exc}")
        return
    except ImagePreparationError as exc:
        print(f"Skipping. {exc}")
        return

    state["last_posted_on"] = today.isoformat()
    save_scheduler_state(settings, state)


def main():
    parser = argparse.ArgumentParser(description="Generate and publish technical LinkedIn posts.")
    subparsers = parser.add_subparsers(dest="command", required=True)
    subparsers.add_parser("auth-url", help="Print the LinkedIn OAuth authorization URL.")
    subparsers.add_parser("login", help="Start a local callback server and complete LinkedIn OAuth.")
    exchange_parser = subparsers.add_parser("exchange", help="Exchange callback URL for LinkedIn token.")
    exchange_parser.add_argument("callback_url", help="Full redirected callback URL containing ?code=...")
    subparsers.add_parser("preview", help="Generate a post but do not publish it.")
    subparsers.add_parser("test-image", help="Generate and upload an image but do not publish a post.")
    subparsers.add_parser("post", help="Generate and publish a post.")
    subparsers.add_parser("scheduled-post", help="Post only when the configured interval has passed.")

    args = parser.parse_args()
    settings = load_settings()

    try:
        if args.command == "auth-url":
            print(build_auth_url(settings))
        elif args.command == "login":
            login(settings)
        elif args.command == "exchange":
            access_token, person_urn = exchange_code_for_token(settings, args.callback_url)
            print(f"LINKEDIN_ACCESS_TOKEN={access_token}")
            print(f"LINKEDIN_PERSON_URN={person_urn}")
        elif args.command == "preview":
            preview(settings)
        elif args.command == "test-image":
            test_image(settings)
        elif args.command == "post":
            post(settings)
        elif args.command == "scheduled-post":
            scheduled_post(settings)
    except ImagePreparationError as exc:
        raise SystemExit(str(exc)) from exc


if __name__ == "__main__":
    main()
