import os

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow

import os

from shared.config.settings import Settings
from shared.google_auth_errors import GoogleAuthenticationRequiredError

settings = Settings()
GOOGLE_OAUTH_SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive",
]


def load_oauth_credentials(scopes: list[str] | None = None) -> Credentials:
    scopes = scopes or GOOGLE_OAUTH_SCOPES

    credentials = None

    token_file = settings.google_oauth_token_file
    client_file = settings.google_oauth_client_file

    if os.path.exists(token_file):
        try:
            credentials = Credentials.from_authorized_user_file(
                token_file,
                scopes,
            )
        except Exception as exc:
            raise GoogleAuthenticationRequiredError(
                "Google OAuth token nem olvasható vagy sérült. "
                "Újraautentikálás szükséges."
            ) from exc

    if credentials and credentials.valid:
        return credentials

    if credentials and credentials.expired and credentials.refresh_token:
        try:
            credentials.refresh(Request())

            with open(token_file, "w", encoding="utf-8") as token:
                token.write(credentials.to_json())

            return credentials
        except Exception as exc:
            raise GoogleAuthenticationRequiredError(
                "Google OAuth token lejárt, és nem sikerült automatikusan frissíteni. "
                "Újraautentikálás szükséges."
            ) from exc

    if credentials:
        raise GoogleAuthenticationRequiredError(
            "Google OAuth token érvénytelen vagy nincs refresh_token. "
            "Újraautentikálás szükséges."
        )

    if not os.path.exists(client_file):
        raise GoogleAuthenticationRequiredError(
            f"Google OAuth client file nem található: {client_file}"
        )

    try:
        flow = InstalledAppFlow.from_client_secrets_file(
            client_file,
            scopes,
        )
        credentials = flow.run_local_server(
            port=0,
            prompt="consent",
        )

        with open(token_file, "w", encoding="utf-8") as token:
            token.write(credentials.to_json())

        return credentials

    except Exception as exc:
        raise GoogleAuthenticationRequiredError(
            "Google OAuth bejelentkezés nem sikerült. "
            "Újraautentikálás szükséges."
        ) from exc