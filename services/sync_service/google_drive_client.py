import os

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.http import MediaInMemoryUpload
from google_auth_oauthlib.flow import InstalledAppFlow

from shared.config.settings import settings


SCOPES = [
    "https://www.googleapis.com/auth/drive.file",
]


class GoogleDriveClient:
    def __init__(self) -> None:
        self.credentials = self._load_oauth_credentials()
        self.service = build("drive", "v3", credentials=self.credentials)

    def load_oauth_credentials(scopes):
        token_file = os.getenv("GOOGLE_OAUTH_TOKEN_FILE", "google_oauth_token.json")

        if not os.path.exists(token_file):
            raise GoogleAuthenticationRequiredError(
                "Google OAuth token hiányzik. Újraautentikálás szükséges."
            )

        try:
            creds = Credentials.from_authorized_user_file(token_file, scopes)
        except Exception as exc:
            raise GoogleAuthenticationRequiredError(
                "Google OAuth token nem olvasható vagy sérült. Újraautentikálás szükséges."
            ) from exc

        if creds.valid:
            return creds

        if creds.expired and creds.refresh_token:
            try:
                creds.refresh(Request())

                with open(token_file, "w", encoding="utf-8") as token:
                    token.write(creds.to_json())

                return creds

            except Exception as exc:
                raise GoogleAuthenticationRequiredError(
                    "Google OAuth token lejárt, és nem sikerült automatikusan frissíteni. "
                    "Újraautentikálás szükséges."
                ) from exc

        raise GoogleAuthenticationRequiredError(
            "Google OAuth token érvénytelen vagy nincs refresh_token. "
            "Újraautentikálás szükséges."
        )

    def _save_credentials(self, credentials: Credentials) -> None:
        token_file = settings.google_oauth_token_file
        token_dir = os.path.dirname(token_file)

        if token_dir:
            os.makedirs(token_dir, exist_ok=True)

        with open(token_file, "w", encoding="utf-8") as token:
            token.write(credentials.to_json())

    def upload_pdf(
        self,
        file_name: str,
        content: bytes,
        folder_id: str,
    ) -> dict:
        if not folder_id:
            raise ValueError("Missing BILLINGO_INVOICE_DRIVE_FOLDER_ID")

        media = MediaInMemoryUpload(
            content,
            mimetype="application/pdf",
            resumable=False,
        )

        metadata = {
            "name": file_name,
            "parents": [folder_id],
        }

        file = (
            self.service.files()
            .create(
                body=metadata,
                media_body=media,
                fields="id,name,webViewLink,webContentLink",
                supportsAllDrives=True,
            )
            .execute()
        )

        service_account_email = settings.google_service_account_email.strip()

        if not service_account_email:
            raise ValueError("Missing GOOGLE_SERVICE_ACCOUNT_EMAIL")

        self.service.permissions().create(
            fileId=file["id"],
            body={
                "type": "user",
                "role": "reader",
                "emailAddress": service_account_email,
            },
            fields="id",
            sendNotificationEmail=False,
        ).execute()

        return file