import base64
import json
import secrets
from http.server import BaseHTTPRequestHandler, HTTPServer
from typing import Any
from urllib.parse import parse_qs, urlencode, urlparse

from .http_utils import get_session
from .settings import Settings, require

LINKEDIN_AUTH_URL = "https://www.linkedin.com/oauth/v2/authorization"
LINKEDIN_TOKEN_URL = "https://www.linkedin.com/oauth/v2/accessToken"
LINKEDIN_USERINFO_URL = "https://api.linkedin.com/v2/userinfo"
LINKEDIN_POSTS_URL = "https://api.linkedin.com/rest/posts"
LINKEDIN_VERSION = "202605"


def build_auth_url(settings: Settings) -> str:
    require(settings.linkedin_client_id, "LINKEDIN_CLIENT_ID")
    state = secrets.token_urlsafe(24)
    return build_auth_url_with_state(settings, state)


def build_auth_url_with_state(settings: Settings, state: str) -> str:
    query = urlencode(
        {
            "response_type": "code",
            "client_id": settings.linkedin_client_id,
            "redirect_uri": settings.linkedin_redirect_uri,
            "scope": settings.linkedin_oauth_scopes,
            "state": state,
        }
    )
    return f"{LINKEDIN_AUTH_URL}?{query}"


def extract_code(callback_url: str) -> str:
    parsed = urlparse(callback_url)
    params = parse_qs(parsed.query)
    error = params.get("error", [""])[0]
    if error:
        description = params.get("error_description", [""])[0]
        raise SystemExit(f"LinkedIn returned error: {error} {description}".strip())
    code = params.get("code", [""])[0]
    if not code:
        raise SystemExit("Could not find ?code= in the callback URL.")
    return code


def exchange_code_for_token(settings: Settings, callback_url: str) -> tuple[str, str]:
    require(settings.linkedin_client_id, "LINKEDIN_CLIENT_ID")
    require(settings.linkedin_client_secret, "LINKEDIN_CLIENT_SECRET")

    response = get_session().post(
        LINKEDIN_TOKEN_URL,
        data={
            "grant_type": "authorization_code",
            "code": extract_code(callback_url),
            "redirect_uri": settings.linkedin_redirect_uri,
            "client_id": settings.linkedin_client_id,
            "client_secret": settings.linkedin_client_secret,
        },
        timeout=30,
    )
    response.raise_for_status()
    token_data = response.json()
    access_token = token_data["access_token"]
    person_urn = person_urn_from_token_data(token_data, access_token)
    return access_token, person_urn


def exchange_raw_code_for_token(settings: Settings, code: str) -> tuple[str, str]:
    require(settings.linkedin_client_id, "LINKEDIN_CLIENT_ID")
    require(settings.linkedin_client_secret, "LINKEDIN_CLIENT_SECRET")

    response = get_session().post(
        LINKEDIN_TOKEN_URL,
        data={
            "grant_type": "authorization_code",
            "code": code,
            "redirect_uri": settings.linkedin_redirect_uri,
            "client_id": settings.linkedin_client_id,
            "client_secret": settings.linkedin_client_secret,
        },
        timeout=30,
    )
    response.raise_for_status()
    token_data = response.json()
    access_token = token_data["access_token"]
    person_urn = person_urn_from_token_data(token_data, access_token)
    return access_token, person_urn


def person_urn_from_token_data(token_data: dict[str, Any], access_token: str) -> str:
    id_token = token_data.get("id_token", "")
    if id_token:
        subject = subject_from_id_token(id_token)
        if subject:
            return f"urn:li:person:{subject}"
    if "openid" not in token_data.get("scope", ""):
        return ""
    return fetch_person_urn(access_token)


def subject_from_id_token(id_token: str) -> str:
    try:
        payload = id_token.split(".")[1]
        padded_payload = payload + "=" * (-len(payload) % 4)
        decoded = base64.urlsafe_b64decode(padded_payload.encode("utf-8"))
        claims = json.loads(decoded)
        return claims.get("sub", "")
    except (IndexError, ValueError, json.JSONDecodeError):
        return ""


def login(settings: Settings) -> None:
    parsed_redirect = urlparse(settings.linkedin_redirect_uri)
    if parsed_redirect.hostname != "localhost":
        raise SystemExit("The login command requires LINKEDIN_REDIRECT_URI to use localhost.")

    port = parsed_redirect.port or 80
    path = parsed_redirect.path or "/"
    state = secrets.token_urlsafe(24)
    result: dict[str, str] = {}

    class CallbackHandler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:
            parsed = urlparse(self.path)
            params = parse_qs(parsed.query)

            if parsed.path != path:
                self.send_response(404)
                self.end_headers()
                return

            if params.get("state", [""])[0] != state:
                result["error"] = "OAuth state did not match."
            elif params.get("error", [""])[0]:
                result["error"] = params.get("error_description", params.get("error", ["Unknown error"]))[0]
            else:
                result["code"] = params.get("code", [""])[0]

            has_error = bool(result.get("error"))
            self.send_response(400 if has_error else 200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.end_headers()
            if has_error:
                message = result["error"].encode("utf-8", errors="replace")
                self.wfile.write(
                    b"<html><body><h2>LinkedIn authorization failed.</h2><p>"
                    + message
                    + b"</p><p>You can close this tab and return to the terminal.</p></body></html>"
                )
            else:
                self.wfile.write(
                    b"<html><body><h2>LinkedIn authorization captured.</h2>"
                    b"<p>You can close this tab and return to the terminal.</p></body></html>"
                )

        def log_message(self, format: str, *args: Any) -> None:
            return

    auth_url = build_auth_url_with_state(settings, state)
    print("Open this URL in your browser and approve access:")
    print(auth_url)
    print()
    print(f"Waiting for LinkedIn callback on {settings.linkedin_redirect_uri} ...")

    server = HTTPServer(("localhost", port), CallbackHandler)
    server.handle_request()

    if result.get("error"):
        raise SystemExit(result["error"])
    if not result.get("code"):
        raise SystemExit("LinkedIn callback did not include an authorization code.")

    access_token, person_urn = exchange_raw_code_for_token(settings, result["code"])
    print(f"LINKEDIN_ACCESS_TOKEN={access_token}")
    print(f"LINKEDIN_PERSON_URN={person_urn}")


def fetch_person_urn(access_token: str) -> str:
    response = get_session().get(
        LINKEDIN_USERINFO_URL,
        headers={"Authorization": f"Bearer {access_token}"},
        timeout=30,
    )
    response.raise_for_status()
    subject = response.json()["sub"]
    return f"urn:li:person:{subject}"


def publish_post(settings: Settings, text: str, image_urn: str | None = None) -> dict[str, Any]:
    access_token = require(settings.linkedin_access_token, "LINKEDIN_ACCESS_TOKEN")
    author = require(settings.linkedin_person_urn, "LINKEDIN_PERSON_URN")

    payload = {
        "author": author,
        "commentary": text,
        "visibility": settings.post_visibility,
        "distribution": {
            "feedDistribution": "MAIN_FEED",
            "targetEntities": [],
            "thirdPartyDistributionChannels": [],
        },
        "lifecycleState": "PUBLISHED",
        "isReshareDisabledByAuthor": False,
    }

    if image_urn:
        payload["content"] = {
            "media": {
                "id": image_urn,
            }
        }

    response = get_session().post(
        LINKEDIN_POSTS_URL,
        headers={
            "Authorization": f"Bearer {access_token}",
            "Content-Type": "application/json",
            "LinkedIn-Version": LINKEDIN_VERSION,
            "X-Restli-Protocol-Version": "2.0.0",
        },
        json=payload,
        timeout=30,
    )
    response.raise_for_status()
    return {"status_code": response.status_code, "post_id": response.headers.get("x-restli-id")}
