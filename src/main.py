import argparse
from datetime import date, datetime
from zoneinfo import ZoneInfo
import logging

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

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')


def _get_content_source(settings):
    """Helper to get the next content row if a source URL is configured."""
    if settings.content_source_url and "PASTE_" not in settings.content_source_url:
        return next_content_row(settings)
    return None, ""


def preview(settings):
    """Generates and prints a preview of the post and image prompt."""
    source, _ = _get_content_source(settings)
    if source:
        logging.info(f"Source title: {source['title']}")

    text, image_prompt = generate_post(settings, source)
    logging.info("--- POST PREVIEW ---")
    logging.info(text)
    logging.info("\n--- IMAGE PROMPT PREVIEW ---")
    logging.info(image_prompt)


def prepare_image(settings, image_prompt, post_text, require_image=None):
    require_image = settings.post_require_image if require_image is None else require_image

    if not settings.cloudflare_api_token or not settings.cloudflare_account_id:
        if require_image:
            logging.error("Image generation is required before publishing. Missing Cloudflare AI credentials.")
            raise ImagePreparationError("Image generation is required before publishing. Missing Cloudflare AI credentials.")
        logging.warning("Image generation skipped. Missing Cloudflare AI credentials; publishing text-only.")
        return None

    image_data = generate_image(settings, image_prompt, post_text)
    if not image_data:
        if require_image:
            logging.error("Image generation failed. Nothing was published.")
            raise ImagePreparationError("Image generation failed. Nothing was published.")
        logging.warning("Image generation failed. Publishing text-only.")
        return None

    image_urn = upload_image_to_linkedin(settings, image_data)
    if not image_urn:
        if require_image:
            logging.error("Image upload to LinkedIn failed. Nothing was published.")
            raise ImagePreparationError("Image upload to LinkedIn failed. Nothing was published.")
        logging.warning("Image upload to LinkedIn failed. Publishing text-only.")
        return None

    return image_urn


def test_image(settings):
    """Generates and uploads an image to LinkedIn for testing purposes."""
    source, _ = _get_content_source(settings)

    text, image_prompt = generate_post(settings, source)
    image_urn = prepare_image(settings, image_prompt, text, require_image=True)
    if image_urn:
        logging.info("Image generation and LinkedIn upload test passed.")
        logging.info(f"Image URN: {image_urn}")
    else:
        logging.error("Image generation and LinkedIn upload test failed.")


def post(settings):
    """Generates and publishes a post to LinkedIn."""
    source, source_key = _get_content_source(settings)

    text, image_prompt = generate_post(settings, source)
    image_urn = prepare_image(settings, image_prompt, text)

    result = publish_post(settings, text, image_urn)
    if source_key:
        mark_posted(settings, source_key)

    logging.info(text)
    logging.info(f"Published to LinkedIn. Status: {result['status_code']}. Post ID: {result.get('post_id')}")


def scheduled_post(settings):
    """Posts only when the configured interval has passed since the last successful post."""
    today = datetime.now(ZoneInfo("Asia/Kolkata")).date()
    state = load_scheduler_state(settings)
    last_posted_on = parse_date(state.get("last_posted_on", ""))

    if last_posted_on and (today - last_posted_on).days < settings.post_interval_days:
        logging.info(f"Skipping scheduled post. Last successful post was on {last_posted_on.isoformat()}.")
        return

    try:
        post(settings)
    except AllRowsPostedError as exc:
        logging.info(f"Skipping scheduled post: {exc}")
        return
    except ImagePreparationError as exc:
        logging.error(f"Skipping scheduled post due to image preparation error: {exc}")
        return
    except Exception as exc:
        logging.critical(f"An unexpected error occurred during scheduled post: {exc}", exc_info=True)

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
            logging.info(build_auth_url(settings))
        elif args.command == "login":
            login(settings)
        elif args.command == "exchange":
            access_token, person_urn = exchange_code_for_token(settings, args.callback_url)
            logging.info(f"LINKEDIN_ACCESS_TOKEN={access_token}")
            logging.info(f"LINKEDIN_PERSON_URN={person_urn}")
        elif args.command == "preview":
            preview(settings)
        elif args.command == "test-image":
            test_image(settings)
        elif args.command == "post":
            post(settings)
        elif args.command == "scheduled-post":
            scheduled_post(settings)
    except Exception as exc:
        logging.critical(f"An error occurred during command '{args.command}': {exc}", exc_info=True)
        sys.exit(1) # Exit with a non-zero status code to indicate failure


if __name__ == "__main__":
    main()
