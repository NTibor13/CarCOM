from googleapiclient.discovery import build
from googleapiclient.http import MediaInMemoryUpload
from shared.google_oauth import load_oauth_credentials

from shared.config.settings import settings


SCOPES = [
    "https://www.googleapis.com/auth/drive.file",
]


class GoogleDriveClient:
    def __init__(self) -> None:
        self.credentials = self._load_oauth_credentials()
        self.service = build("drive", "v3", credentials=self.credentials)

    def _load_oauth_credentials(self):
        return load_oauth_credentials()

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