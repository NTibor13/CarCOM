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

    def _load_oauth_credentials(self) -> Credentials:
        credentials = None

        token_file = settings.google_oauth_token_file
        client_file = settings.google_oauth_client_file

        if os.path.exists(token_file):
            credentials = Credentials.from_authorized_user_file(
                token_file,
                SCOPES,
            )

        if credentials and credentials.valid:
            return credentials

        if credentials and credentials.expired and credentials.refresh_token:
            credentials.refresh(Request())
            self._save_credentials(credentials)
            return credentials

        if not os.path.exists(client_file):
            raise FileNotFoundError(
                f"Google OAuth client file not found: {client_file}"
            )

        flow = InstalledAppFlow.from_client_secrets_file(
            client_file,
            SCOPES,
        )

        credentials = flow.run_local_server(
            port=0,
            prompt="consent",
        )

        self._save_credentials(credentials)
        return credentials

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