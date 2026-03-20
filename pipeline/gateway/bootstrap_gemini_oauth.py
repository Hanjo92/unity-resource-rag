#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path


DEFAULT_TOKEN_OUTPUT = Path("~/.config/unity-resource-rag/gemini-oauth-token.json").expanduser()
DEFAULT_SCOPES = (
    "https://www.googleapis.com/auth/cloud-platform",
    "https://www.googleapis.com/auth/generative-language.retriever",
)


def _die(message: str) -> None:
    raise SystemExit(message)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Bootstrap a reusable Gemini OAuth token file for the local gateway."
    )
    parser.add_argument(
        "--client-secret",
        type=Path,
        required=True,
        help="Path to the Google OAuth desktop client_secret.json file.",
    )
    parser.add_argument(
        "--token-output",
        type=Path,
        default=DEFAULT_TOKEN_OUTPUT,
        help=f"Path to write the authorized user token JSON. Default: {DEFAULT_TOKEN_OUTPUT}",
    )
    parser.add_argument(
        "--scope",
        action="append",
        default=[],
        help="OAuth scope to request. Can be repeated.",
    )
    parser.add_argument(
        "--project-id",
        help="Optional Google Cloud project id to echo in the success output for x-goog-user-project.",
    )
    parser.add_argument(
        "--no-browser",
        action="store_true",
        help="Do not open a browser automatically. Useful for remote terminals.",
    )
    args = parser.parse_args()

    client_secret_path = args.client_secret.expanduser().resolve()
    if not client_secret_path.exists():
        _die(f"Client secret file not found: {client_secret_path}")

    try:
        from google_auth_oauthlib.flow import InstalledAppFlow
    except ImportError as exc:
        _die(
            "google-auth-oauthlib is required. Install dependencies with "
            "`python3 -m pip install -r requirements.txt`."
        )

    scopes = tuple(args.scope or DEFAULT_SCOPES)
    token_output = args.token_output.expanduser().resolve()
    token_output.parent.mkdir(parents=True, exist_ok=True)

    flow = InstalledAppFlow.from_client_secrets_file(
        str(client_secret_path),
        scopes=list(scopes),
    )
    creds = flow.run_local_server(
        port=0,
        open_browser=not args.no_browser,
    )

    token_output.write_text(creds.to_json(), encoding="utf-8")

    payload = {
        "status": "ok",
        "tokenOutput": str(token_output),
        "scopes": list(scopes),
        "projectId": args.project_id,
        "nextEnv": {
            "GEMINI_AUTH_MODE": "oauth_token_file",
            "GEMINI_OAUTH_TOKEN_FILE": str(token_output),
            "GEMINI_PROJECT_ID": args.project_id,
        },
    }
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
